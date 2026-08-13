#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

readonly DUMPER_SERVICE="commercialrchproxy-dumper.service"
readonly PARSER_SERVICE="commercialrchproxy-parser.service"
readonly LEGACY_SERVICE="commercialrchproxy.service"
readonly SERVICES=("${DUMPER_SERVICE}" "${PARSER_SERVICE}" "${LEGACY_SERVICE}")
readonly CONFIG_DIR="/etc/commercialrchproxy"
readonly CONFIG_PATH="${CONFIG_DIR}/commercialrchproxy.conf"
readonly APP_ROOT="/opt/commercialrchproxy"
readonly RUNTIME_DIR="/run/commercialrchproxy"
readonly LIBEXEC_DIR="/usr/local/libexec/commercialrchproxy"
readonly UNIT_DIR="/etc/systemd/system"
readonly SECONDARY_UNIT_PATH="/etc/systemd/system/commercialrchproxy-secondary-ip.service"
readonly SECONDARY_CONFIG_PATH="${CONFIG_DIR}/secondary-ip.conf"
readonly SECONDARY_HELPER_PATH="/usr/local/libexec/commercialrchproxy-network/manage_secondary_ip.sh"
readonly SECONDARY_DROPIN_PATH="/etc/systemd/system/${DUMPER_SERVICE}.d/10-secondary-ip.conf"
readonly LEGACY_SECONDARY_DROPIN_PATH="/etc/systemd/system/${LEGACY_SERVICE}.d/10-secondary-ip.conf"
readonly PURGE_PHRASE="PURGE commercialRCHproxy"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
# shellcheck source=scripts/config_contract.sh
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/config_contract.sh"

PURGE=0
CONFIRM_PURGE=""

usage() {
    cat <<'EOF'
Usage: sudo ./scripts/uninstall.sh [--purge [--confirm-purge PHRASE]]

Default uninstall removes all application services, releases, and installed
operations scripts while preserving:
  /etc/commercialrchproxy
  configured OUTPUT_DIR
  configured LOG_DIR
  /var/backups/commercialrchproxy

--purge additionally deletes configuration, captured jobs, and logs. It always
requires the exact confirmation phrase "PURGE commercialRCHproxy", either at
an interactive prompt or via --confirm-purge. Backup archives are retained.
No host networking is changed and no network connection or protocol probe is made.
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
        --purge) PURGE=1; shift ;;
        --confirm-purge)
            [[ $# -ge 2 ]] || die "--confirm-purge requires the exact phrase"
            CONFIRM_PURGE="$2"
            shift 2
            ;;
        --confirm-purge=*) CONFIRM_PURGE="${1#*=}"; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown option: $1" ;;
    esac
done

[[ "${EUID}" -eq 0 ]] || die "Run as root (for example, with sudo)."
if [[ -n "${CONFIRM_PURGE}" && "${PURGE}" -ne 1 ]]; then
    die "--confirm-purge is only valid together with --purge."
fi
if [[ "${PURGE}" -eq 1 && -z "${CONFIRM_PURGE}" ]]; then
    if [[ -t 0 ]]; then
        printf 'DESTRUCTIVE: configuration, captured jobs, and logs will be deleted.\n' >&2
        printf 'Type exactly "%s" to continue: ' "${PURGE_PHRASE}" >&2
        IFS= read -r CONFIRM_PURGE
    else
        die "Non-interactive purge requires --confirm-purge='${PURGE_PHRASE}'"
    fi
fi
if [[ "${PURGE}" -eq 1 && "${CONFIRM_PURGE}" != "${PURGE_PHRASE}" ]]; then
    die "Purge confirmation did not exactly match '${PURGE_PHRASE}'. Nothing was removed."
fi

command -v flock >/dev/null 2>&1 || die "flock is required (package: util-linux)."
acquire_mutation_lock

CONTRACT_AVAILABLE=0
if [[ -e "${CONFIG_PATH}" || -L "${CONFIG_PATH}" ]]; then
    crch_load_config_contract "${CONFIG_PATH}" || \
        die "Cannot determine configured identity/output/log targets safely. Nothing was removed."
    SERVICE_USER="${CRCH_SERVICE_USER}"
    SERVICE_GROUP="${CRCH_SERVICE_GROUP}"
    OUTPUT_DIR="${CRCH_OUTPUT_DIR}"
    LOG_DIR="${CRCH_LOG_DIR}"
    readonly SERVICE_USER SERVICE_GROUP OUTPUT_DIR LOG_DIR
    CONTRACT_AVAILABLE=1
elif [[ "${PURGE}" -eq 1 ]]; then
    die "Purge requires the preserved regular configuration ${CONFIG_PATH} to resolve exact targets. Nothing was removed."
fi

# These literal guards make future edits fail closed before recursive removal.
[[ "${APP_ROOT}" == "/opt/commercialrchproxy" ]] || die "Unsafe APP_ROOT"
[[ "${LIBEXEC_DIR}" == "/usr/local/libexec/commercialrchproxy" ]] || die "Unsafe LIBEXEC_DIR"
[[ "${CONFIG_DIR}" == "/etc/commercialrchproxy" ]] || die "Unsafe CONFIG_DIR"
if [[ "${CONTRACT_AVAILABLE}" -eq 1 ]]; then
    [[ "${OUTPUT_DIR}" == "${CRCH_OUTPUT_DIR}" && "${LOG_DIR}" == "${CRCH_LOG_DIR}" ]] || \
        die "Configured purge-target validation failed."
    for managed_path in "${OUTPUT_DIR}" "${LOG_DIR}"; do
        [[ ! -L "${managed_path}" ]] || die "Refusing symlinked configured path: ${managed_path}"
    done
fi

if [[ "${PURGE}" -eq 1 ]] && \
   { [[ -e "${SECONDARY_UNIT_PATH}" || -L "${SECONDARY_UNIT_PATH}" || \
        -e "${SECONDARY_CONFIG_PATH}" || -L "${SECONDARY_CONFIG_PATH}" || \
        -e "${SECONDARY_HELPER_PATH}" || -L "${SECONDARY_HELPER_PATH}" || \
        -e "${SECONDARY_DROPIN_PATH}" || -L "${SECONDARY_DROPIN_PATH}" || \
        -e "${LEGACY_SECONDARY_DROPIN_PATH}" || -L "${LEGACY_SECONDARY_DROPIN_PATH}" ]] || \
     systemctl is-active --quiet commercialrchproxy-secondary-ip.service || \
     systemctl is-enabled --quiet commercialrchproxy-secondary-ip.service; }; then
    die "The optional secondary-IP service still depends on ${CONFIG_DIR}. Run /usr/local/libexec/commercialrchproxy-network/manage_secondary_ip.sh uninstall (or the checkout copy) first, then rerun the purge."
fi

systemctl disable --now "${SERVICES[@]}" >/dev/null 2>&1 || true
for service_name in "${SERVICES[@]}"; do
    rm -f -- "${UNIT_DIR}/${service_name}"
done
systemctl daemon-reload
systemctl reset-failed "${SERVICES[@]}" >/dev/null 2>&1 || true

rm -rf -- "${APP_ROOT}"
rm -rf -- "${LIBEXEC_DIR}"
rm -rf -- "${RUNTIME_DIR}"

if [[ "${PURGE}" -eq 1 ]]; then
    rm -rf -- "${OUTPUT_DIR}"
    rm -rf -- "${LOG_DIR}"
    rm -rf -- "${CONFIG_DIR}"
    if id -u "${SERVICE_USER}" >/dev/null 2>&1; then
        userdel "${SERVICE_USER}"
    fi
    if getent group "${SERVICE_GROUP}" >/dev/null 2>&1; then
        groupdel "${SERVICE_GROUP}" || \
            printf 'WARNING: group %s is still in use and was retained.\n' "${SERVICE_GROUP}" >&2
    fi
    printf 'PURGED: %s, %s, and %s were deleted and are not recoverable unless separately backed up.\n' \
        "${CONFIG_DIR}" "${OUTPUT_DIR}" "${LOG_DIR}"
    printf 'PRESERVED: /var/backups/commercialrchproxy (if present).\n'
else
    printf 'PRESERVED: configuration in %s\n' "${CONFIG_DIR}"
    if [[ "${CONTRACT_AVAILABLE}" -eq 1 ]]; then
        printf 'PRESERVED: captured jobs in %s\n' "${OUTPUT_DIR}"
        printf 'PRESERVED: logs in %s\n' "${LOG_DIR}"
        printf 'PRESERVED: service account %s so retained file ownership remains stable.\n' "${SERVICE_USER}"
    else
        printf 'PRESERVED: configured output/log trees and service account (configuration was unavailable).\n'
    fi
    printf 'PRESERVED: optional secondary-IP service/address state, if separately installed.\n'
fi
printf 'PASS: application, all three service units, and installed operations scripts were removed.\n'
printf 'PASS: no host network settings were changed and no network connection was opened.\n'
