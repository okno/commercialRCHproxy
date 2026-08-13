#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
umask 0077

readonly DUMPER_SERVICE="commercialrchproxy-dumper.service"
readonly PARSER_SERVICE="commercialrchproxy-parser.service"
readonly LEGACY_SERVICE="commercialrchproxy.service"
readonly SERVICES=("${DUMPER_SERVICE}" "${PARSER_SERVICE}" "${LEGACY_SERVICE}")
readonly CONFIG_DIR="/etc/commercialrchproxy"
readonly CONFIG_PATH="${CONFIG_DIR}/commercialrchproxy.conf"
readonly APP_ROOT="/opt/commercialrchproxy"
readonly UNIT_DIR="/etc/systemd/system"
readonly LIBEXEC_DIR="/usr/local/libexec/commercialrchproxy"
readonly NETWORK_LIBEXEC_DIR="/usr/local/libexec/commercialrchproxy-network"
readonly SECONDARY_UNIT_PATH="${UNIT_DIR}/commercialrchproxy-secondary-ip.service"
readonly DUMPER_DROPIN_PATH="${UNIT_DIR}/${DUMPER_SERVICE}.d/10-secondary-ip.conf"
readonly LEGACY_DROPIN_PATH="${UNIT_DIR}/${LEGACY_SERVICE}.d/10-secondary-ip.conf"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
# shellcheck source=scripts/config_contract.sh
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/config_contract.sh"

BACKUP_DIR="/var/backups/commercialrchproxy"
ONLINE=0
ACTIVE_BEFORE=()
SERVICES_RESTORED=0
TEMPORARY_ARCHIVE=""
TEMPORARY_HASH=""

usage() {
    cat <<'EOF'
Usage: sudo ./scripts/backup.sh [--destination DIR] [--online]

By default both independent services are stopped briefly to capture a
consistent archive, then each is returned to its previous state. --online
avoids downtime, but the archive
is labeled UNCONFIRMED because jobs can change while tar is reading them.

Configuration, captured jobs, logs, all service units, installed operations scripts,
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
crch_load_config_contract "${CONFIG_PATH}" || die "Cannot determine the configured backup roots safely."
OUTPUT_DIR="${CRCH_OUTPUT_DIR}"
LOG_DIR="${CRCH_LOG_DIR}"
readonly OUTPUT_DIR LOG_DIR

BACKUP_DIR="$(realpath -m -- "${BACKUP_DIR}")"
[[ "${BACKUP_DIR}" != "/" ]] || die "Backup destination must not be the filesystem root."
for managed_root in "${CONFIG_DIR}" "${APP_ROOT}" "${OUTPUT_DIR}" "${LOG_DIR}"; do
    case "${BACKUP_DIR}/" in
        "${managed_root}/"*)
            die "Backup destination must be outside configuration, application, output, and log trees: ${BACKUP_DIR}"
            ;;
    esac
done
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
    if [[ "${#ACTIVE_BEFORE[@]}" -gt 0 && "${SERVICES_RESTORED}" -eq 0 ]]; then
        if systemctl start "${ACTIVE_BEFORE[@]}"; then
            SERVICES_RESTORED=1
        else
            printf 'ERROR: backup cleanup could not restore the previously active services.\n' >&2
            rc=1
        fi
    fi
    exit "${rc}"
}
trap cleanup_on_exit EXIT INT TERM HUP

for source_path in "${CONFIG_DIR}" "${OUTPUT_DIR}" "${LOG_DIR}"; do
    [[ ! -L "${source_path}" ]] || die "Refusing to back up symlinked managed directory: ${source_path}"
done

for service_name in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "${service_name}"; then
        ACTIVE_BEFORE+=("${service_name}")
    fi
done
if [[ "${#ACTIVE_BEFORE[@]}" -gt 0 ]]; then
    if [[ "${ONLINE}" -eq 0 ]]; then
        printf '[commercialRCHproxy] Stopping active services for a consistent backup.\n'
        systemctl stop "${ACTIVE_BEFORE[@]}"
    else
        printf 'UNCONFIRMED: online archive consistency; jobs may change during backup.\n' >&2
        SERVICES_RESTORED=1
    fi
fi

archive_items=()
for source_path in \
    "${CONFIG_DIR}" "${OUTPUT_DIR}" "${LOG_DIR}" \
    "${LIBEXEC_DIR}" "${NETWORK_LIBEXEC_DIR}" "${SECONDARY_UNIT_PATH}" \
    "${DUMPER_DROPIN_PATH}" "${LEGACY_DROPIN_PATH}" "${APP_ROOT}/current"; do
    if [[ -e "${source_path}" || -L "${source_path}" ]]; then
        archive_items+=("${source_path#/}")
    fi
done
for service_name in "${SERVICES[@]}"; do
    unit_path="${UNIT_DIR}/${service_name}"
    if [[ -e "${unit_path}" || -L "${unit_path}" ]]; then
        archive_items+=("${unit_path#/}")
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

if [[ "${#ACTIVE_BEFORE[@]}" -gt 0 && "${ONLINE}" -eq 0 ]]; then
    systemctl start "${ACTIVE_BEFORE[@]}"
    SERVICES_RESTORED=1
fi

trap - EXIT INT TERM HUP
printf 'PASS: backup created atomically at %s\n' "${final_archive}"
printf 'PASS: SHA-256 sidecar written to %s.sha256\n' "${final_archive}"
printf 'PASS: no listener or RCH-device connection probe was performed.\n'
