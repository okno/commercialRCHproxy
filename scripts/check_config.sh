#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

CONFIG_PATH="/etc/commercialrchproxy/commercialrchproxy.conf"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
# shellcheck source=scripts/config_contract.sh
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/config_contract.sh"
usage() {
    cat <<'EOF'
Usage: ./scripts/check_config.sh [--config PATH]

By default this validates all endpoint values, local bind availability, output
storage, service-account permissions, and disk space. A running listener is
checked passively with ss(8). It never connects to either the proxy listener or
the RCH device. RCH protocol reachability requires PCAP/manual evidence.
EOF
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --config)
            [[ $# -ge 2 ]] || die "--config requires a path"
            CONFIG_PATH="$2"
            shift 2
            ;;
        --config=*) CONFIG_PATH="${1#*=}"; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown option: $1" ;;
    esac
done

PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
readonly PROJECT_ROOT
readonly DUMPER_SERVICE="commercialrchproxy-dumper.service"
readonly INSTALLED_CLI="/opt/commercialrchproxy/current/venv/bin/commercialrchproxy-dumper"

select_python() {
    local candidate
    for candidate in python3.13 python3.12 python3.11 python3; do
        if command -v "${candidate}" >/dev/null 2>&1 && \
            "${candidate}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
            printf '%s\n' "$(command -v "${candidate}")"
            return 0
        fi
    done
    return 1
}

run_cli() {
    if [[ -x "${INSTALLED_CLI}" ]]; then
        "${INSTALLED_CLI}" "$@"
    elif command -v commercialrchproxy-dumper >/dev/null 2>&1; then
        commercialrchproxy-dumper "$@"
    elif [[ -d "${PROJECT_ROOT}/src/commercialrchproxy" ]]; then
        local python_bin
        python_bin="$(select_python)" || die "Python 3.11+ is required to validate the source tree."
        PYTHONPATH="${PROJECT_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" \
            "${python_bin}" -m commercialrchproxy.dumper.main "$@"
    else
        die "commercialrchproxy-dumper is not installed and no source tree was found."
    fi
}

[[ -f "${CONFIG_PATH}" && ! -L "${CONFIG_PATH}" ]] || \
    die "Configuration must be a regular, non-symlink file: ${CONFIG_PATH}"
crch_load_config_contract "${CONFIG_PATH}" || die "Unsafe operating-system configuration contract."
service_user="${CRCH_SERVICE_USER}"
service_group="${CRCH_SERVICE_GROUP}"

run_cli --config "${CONFIG_PATH}" --check-config --json
printf 'PASS: configuration syntax is valid and LISTEN_IP is assigned locally.\n'

python_bin="$(select_python)" || die "Python 3.11+ is required to inspect health output."
health_rc=0
health_report="$(run_cli --config "${CONFIG_PATH}" --healthcheck --json)" || health_rc=$?
printf '%s\n' "${health_report}"
[[ "${health_rc}" -eq 0 ]] || die "Output-directory or local-IP health validation failed."

output_dir="$(printf '%s\n' "${health_report}" | "${python_bin}" -c \
    'import json, sys; print(json.load(sys.stdin)["jobs_directory"]["path"])')"
log_dir="${CRCH_LOG_DIR}"
disk_free="$(printf '%s\n' "${health_report}" | "${python_bin}" -c \
    'import json, sys; value=json.load(sys.stdin)["jobs_directory"]["disk_free_bytes"]; print(-1 if value is None else value)')"
listen_endpoint="$(printf '%s\n' "${health_report}" | "${python_bin}" -c \
    'import json, sys; print(json.load(sys.stdin)["proxy"]["endpoint"])')"
listen_ip="${listen_endpoint%:*}"
listen_port="${listen_endpoint##*:}"

[[ -d "${output_dir}" && ! -L "${output_dir}" ]] || \
    die "OUTPUT_DIR must be an existing, non-symlink directory: ${output_dir}"
[[ -d "${log_dir}" && ! -L "${log_dir}" ]] || \
    die "LOG_DIR must be an existing, non-symlink directory: ${log_dir}"
[[ "${output_dir}" == "${CRCH_OUTPUT_DIR}" ]] || \
    die "Application OUTPUT_DIR differs from the installer contract: ${output_dir}"
[[ "${disk_free}" =~ ^[0-9]+$ && "${disk_free}" -gt 0 ]] || \
    die "Disk-free-space check failed for ${output_dir}."

verify_unit_contract() {
    local service_name="$1"
    local actual_user actual_group actual_working actual_writes
    local writable_paths=()
    local have_output=0 have_log=0 writable

    actual_user="$(systemctl show "${service_name}" --property=User --value --no-pager)" || return 1
    actual_group="$(systemctl show "${service_name}" --property=Group --value --no-pager)" || return 1
    actual_working="$(systemctl show "${service_name}" --property=WorkingDirectory --value --no-pager)" || return 1
    actual_writes="$(systemctl show "${service_name}" --property=ReadWritePaths --value --no-pager)" || return 1
    [[ "${actual_user}" == "${service_user}" ]] || \
        die "${service_name} User=${actual_user}, expected configured ${service_user}. Rerun install/update."
    [[ "${actual_group}" == "${service_group}" ]] || \
        die "${service_name} Group=${actual_group}, expected configured ${service_group}. Rerun install/update."
    [[ "${actual_working}" == "${output_dir}" ]] || \
        die "${service_name} WorkingDirectory=${actual_working}, expected ${output_dir}. Rerun install/update."
    IFS=' ' read -r -a writable_paths <<<"${actual_writes}"
    [[ "${#writable_paths[@]}" -eq 2 ]] || \
        die "${service_name} must expose exactly configured OUTPUT_DIR and LOG_DIR as writable paths."
    for writable in "${writable_paths[@]}"; do
        case "${writable}" in
            "${output_dir}") have_output=1 ;;
            "${log_dir}") have_log=1 ;;
            *) die "${service_name} exposes unexpected writable path: ${writable}" ;;
        esac
    done
    [[ "${have_output}" -eq 1 && "${have_log}" -eq 1 ]] || \
        die "${service_name} writable paths do not match OUTPUT_DIR and LOG_DIR."
}

if command -v systemctl >/dev/null 2>&1 && \
   [[ -f "/etc/systemd/system/commercialrchproxy-dumper.service" && \
      -f "/etc/systemd/system/commercialrchproxy-parser.service" ]]; then
    verify_unit_contract commercialrchproxy-dumper.service
    verify_unit_contract commercialrchproxy-parser.service
    printf 'PASS: both systemd units match configured identity, working directory, and writable paths.\n'
fi

if [[ "${EUID}" -eq 0 ]] && id -u "${service_user}" >/dev/null 2>&1; then
    [[ "$(id -gn "${service_user}")" == "${service_group}" ]] || \
        die "Configured service user ${service_user} does not have primary group ${service_group}."
    runuser -u "${service_user}" -- test -r "${CONFIG_PATH}" || \
        die "The configured service account cannot read ${CONFIG_PATH}."
    runuser -u "${service_user}" -- test -x "${output_dir}" || \
        die "The configured service account cannot traverse ${output_dir}."
    runuser -u "${service_user}" -- test -w "${output_dir}" || \
        die "The configured service account cannot write ${output_dir}."
    runuser -u "${service_user}" -- test -x "${log_dir}" || \
        die "The configured service account cannot traverse ${log_dir}."
    runuser -u "${service_user}" -- test -w "${log_dir}" || \
        die "The configured service account cannot write ${log_dir}."
    printf 'PASS: service-account configuration, output, and log permissions are usable.\n'
elif [[ -r "${CONFIG_PATH}" && -x "${output_dir}" && -w "${output_dir}" && -x "${log_dir}" && -w "${log_dir}" ]]; then
    printf 'PASS: configuration/output/log permissions are usable by the current account.\n'
else
    die "Cannot verify usable configuration/output/log permissions; run as root to test the service account."
fi
printf 'PASS: output directory has %s bytes free.\n' "${disk_free}"

# Never connect to the proxy listener. If it is already running, ss is the
# authoritative passive check. If it is stopped and this script is root, bind
# the configured endpoint without calling listen(2), then close immediately.
if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet "${DUMPER_SERVICE}"; then
    command -v ss >/dev/null 2>&1 || die "ss(8) is required (package: iproute2)."
    ss -H -ltn | awk -v endpoint="${listen_endpoint}" \
        '$1 == "LISTEN" && $4 == endpoint { found=1 } END { exit(found ? 0 : 1) }' || \
        die "The active service is not listening on exactly ${listen_endpoint}."
    printf 'PASS: ss reports the exact configured listener %s.\n' "${listen_endpoint}"
elif [[ "${EUID}" -eq 0 ]]; then
    "${python_bin}" - "${listen_ip}" "${listen_port}" <<'PY' || \
        die "Cannot bind the configured listener endpoint ${listen_endpoint}."
import socket
import sys

address, port = sys.argv[1], int(sys.argv[2])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    probe.bind((address, port))
PY
    printf 'PASS: configured endpoint %s can be bound locally (no listen/connect performed).\n' "${listen_endpoint}"
else
    printf 'NOTICE: exact privileged-port bind availability requires root or a running systemd service; LISTEN_IP assignment was validated.\n'
fi

printf 'RCH protocol reachability: NOT PROBED (requires PCAP/manual evidence).\n'
printf 'PASS: no listener or RCH-device connection was opened.\n'
