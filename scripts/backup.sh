#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 0077

readonly SERVICE_NAME="commercialrchproxy.service"
readonly CONFIG_DIR="/etc/commercialrchproxy"
readonly DATA_DIR="/var/lib/commercialrchproxy"
readonly LOG_DIR="/var/log/commercialrchproxy"
readonly APP_ROOT="/opt/commercialrchproxy"
readonly UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}"
readonly LIBEXEC_DIR="/usr/local/libexec/commercialrchproxy"

BACKUP_DIR="/var/backups/commercialrchproxy"
ONLINE=0
WAS_ACTIVE=0
SERVICE_RESTARTED=0
TEMPORARY_ARCHIVE=""
TEMPORARY_HASH=""

usage() {
    cat <<'EOF'
Usage: sudo ./scripts/backup.sh [--destination DIR] [--online]

By default the service is stopped briefly to capture a consistent archive,
then returned to its previous state. --online avoids downtime, but the archive
is labeled UNCONFIRMED because jobs can change while tar is reading them.

Configuration, captured jobs, logs, the unit, installed operations scripts,
and the active-release symlink are included. No network connection or protocol
probe is made.
EOF
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

acquire_mutation_lock() {
    local lock_path="/run/commercialrchproxy-mutation.lock"
    local inherited_target
    local previous_umask
    if [[ -e "${lock_path}" ]]; then
        [[ -f "${lock_path}" && ! -L "${lock_path}" && "$(stat -c '%u' -- "${lock_path}")" == "0" ]] || \
            die "Mutation lock must be a root-owned regular non-symlink file: ${lock_path}"
        chmod 0600 -- "${lock_path}"
    fi
    if [[ "${COMMERCIALRCHPROXY_MUTATION_LOCK_HELD:-0}" == "1" ]]; then
        [[ -e /proc/self/fd/9 ]] || die "Inherited mutation-lock descriptor 9 is unavailable."
        inherited_target="$(readlink -f -- /proc/self/fd/9)"
        [[ "${inherited_target}" == "${lock_path}" ]] || die "Inherited mutation lock points to an unexpected path."
    else
        previous_umask="$(umask)"
        umask 0077
        exec 9>"${lock_path}"
        umask "${previous_umask}"
        chmod 0600 -- "${lock_path}"
    fi
    flock -n 9 || die "Another commercialRCHproxy install, update, backup, or uninstall is running."
    export COMMERCIALRCHPROXY_MUTATION_LOCK_HELD=1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --destination)
            [[ $# -ge 2 ]] || die "--destination requires a directory"
            BACKUP_DIR="$2"
            shift 2
            ;;
        --destination=*) BACKUP_DIR="${1#*=}"; shift ;;
        --online) ONLINE=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown option: $1" ;;
    esac
done

[[ "${EUID}" -eq 0 ]] || die "Run as root (for example, with sudo)."
command -v flock >/dev/null 2>&1 || die "flock is required (package: util-linux)."
command -v realpath >/dev/null 2>&1 || die "realpath is required (package: coreutils)."
command -v sha256sum >/dev/null 2>&1 || die "sha256sum is required (package: coreutils)."

BACKUP_DIR="$(realpath -m -- "${BACKUP_DIR}")"
case "${BACKUP_DIR}" in
    /|/etc|/etc/*|/opt|/opt/commercialrchproxy|/opt/commercialrchproxy/*|\
    /var|/var/lib|/var/lib/commercialrchproxy|/var/lib/commercialrchproxy/*|\
    /var/log|/var/log/commercialrchproxy|/var/log/commercialrchproxy/*)
        die "Backup destination must be outside configuration, application, data, and log trees: ${BACKUP_DIR}"
        ;;
esac
[[ ! -L "${BACKUP_DIR}" ]] || die "Refusing symlinked backup directory: ${BACKUP_DIR}"
install -d -m 0700 -o root -g root -- "${BACKUP_DIR}"

acquire_mutation_lock

cleanup_on_exit() {
    local rc=$?
    trap - EXIT INT TERM HUP
    if [[ -n "${TEMPORARY_ARCHIVE}" ]]; then
        rm -f -- "${TEMPORARY_ARCHIVE}"
    fi
    if [[ -n "${TEMPORARY_HASH}" ]]; then
        rm -f -- "${TEMPORARY_HASH}"
    fi
    if [[ "${WAS_ACTIVE}" -eq 1 && "${SERVICE_RESTARTED}" -eq 0 ]]; then
        if systemctl start "${SERVICE_NAME}"; then
            SERVICE_RESTARTED=1
        else
            printf 'ERROR: backup cleanup could not restart %s.\n' "${SERVICE_NAME}" >&2
            rc=1
        fi
    fi
    exit "${rc}"
}
trap cleanup_on_exit EXIT INT TERM HUP

for source_path in "${CONFIG_DIR}" "${DATA_DIR}" "${LOG_DIR}"; do
    [[ ! -L "${source_path}" ]] || die "Refusing to back up symlinked managed directory: ${source_path}"
done

if systemctl is-active --quiet "${SERVICE_NAME}"; then
    WAS_ACTIVE=1
    if [[ "${ONLINE}" -eq 0 ]]; then
        printf '[commercialRCHproxy] Stopping service for a consistent backup.\n'
        systemctl stop "${SERVICE_NAME}"
    else
        printf 'UNCONFIRMED: online archive consistency; jobs may change during backup.\n' >&2
        SERVICE_RESTARTED=1
    fi
fi

archive_items=()
for source_path in \
    "${CONFIG_DIR}" "${DATA_DIR}" "${LOG_DIR}" "${UNIT_PATH}" \
    "${LIBEXEC_DIR}" "${APP_ROOT}/current"; do
    if [[ -e "${source_path}" || -L "${source_path}" ]]; then
        archive_items+=("${source_path#/}")
    fi
done

# Archive the active release itself, not only the current symlink. This keeps a
# pre-update backup independently recoverable if /opt is later damaged.
if [[ -L "${APP_ROOT}/current" ]]; then
    active_release="$(realpath -e -- "${APP_ROOT}/current")"
    case "${active_release}" in
        "${APP_ROOT}/releases/"*) ;;
        *) die "Active release resolves outside ${APP_ROOT}/releases: ${active_release}" ;;
    esac
    [[ -d "${active_release}" && ! -L "${active_release}" ]] || \
        die "Active release is not a regular directory: ${active_release}"
    archive_items+=("${active_release#/}")
fi
[[ "${#archive_items[@]}" -gt 0 ]] || die "Nothing is installed to back up."

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive_name="commercialrchproxy-${timestamp}.tar.gz"
final_archive="${BACKUP_DIR}/${archive_name}"
if [[ -e "${final_archive}" ]]; then
    archive_name="commercialrchproxy-${timestamp}-$$.tar.gz"
    final_archive="${BACKUP_DIR}/${archive_name}"
fi
TEMPORARY_ARCHIVE="${final_archive}.partial.$$"
TEMPORARY_HASH="${final_archive}.sha256.partial.$$"

tar --create --gzip --file "${TEMPORARY_ARCHIVE}" --directory / \
    --acls --xattrs --numeric-owner --one-file-system -- "${archive_items[@]}"
chmod 0600 -- "${TEMPORARY_ARCHIVE}"
mv -T -- "${TEMPORARY_ARCHIVE}" "${final_archive}"
TEMPORARY_ARCHIVE=""

(
    cd -- "${BACKUP_DIR}"
    sha256sum -- "${archive_name}"
) >"${TEMPORARY_HASH}"
chmod 0600 -- "${TEMPORARY_HASH}"
mv -T -- "${TEMPORARY_HASH}" "${final_archive}.sha256"
TEMPORARY_HASH=""

if [[ "${WAS_ACTIVE}" -eq 1 && "${ONLINE}" -eq 0 ]]; then
    systemctl start "${SERVICE_NAME}"
    SERVICE_RESTARTED=1
fi

trap - EXIT INT TERM HUP
printf 'PASS: backup created atomically at %s\n' "${final_archive}"
printf 'PASS: SHA-256 sidecar written to %s.sha256\n' "${final_archive}"
printf 'PASS: no listener or RCH-device connection probe was performed.\n'
