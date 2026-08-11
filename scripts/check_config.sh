#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

CONFIG_PATH="/etc/commercialrchproxy/commercialrchproxy.conf"
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

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly PROJECT_ROOT
readonly INSTALLED_CLI="/opt/commercialrchproxy/current/venv/bin/commercialrchproxy"

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
    elif command -v commercialrchproxy >/dev/null 2>&1; then
        commercialrchproxy "$@"
    elif [[ -d "${PROJECT_ROOT}/src/commercialrchproxy" ]]; then
        local python_bin
        python_bin="$(select_python)" || die "Python 3.11+ is required to validate the source tree."
        PYTHONPATH="${PROJECT_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" \
            "${python_bin}" -m commercialrchproxy "$@"
    else
        die "commercialrchproxy is not installed and no source tree was found."
    fi
}

config_value() {
    local wanted="$1"
    local fallback="$2"
    local found
    found="$(awk -v wanted="${wanted}" '
        /^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
        {
            separator = index($0, "=")
            if (!separator) next
            key = substr($0, 1, separator - 1)
            value = substr($0, separator + 1)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
            if (key == wanted) {
                if ((substr(value,1,1) == "\"" && substr(value,length(value),1) == "\"") ||
                    (substr(value,1,1) == "\047" && substr(value,length(value),1) == "\047")) {
                    value = substr(value, 2, length(value) - 2)
                }
                print value
                exit
            }
        }
    ' "${CONFIG_PATH}")"
    printf '%s\n' "${found:-${fallback}}"
}

[[ -f "${CONFIG_PATH}" && ! -L "${CONFIG_PATH}" ]] || \
    die "Configuration must be a regular, non-symlink file: ${CONFIG_PATH}"

run_cli --config "${CONFIG_PATH}" --check-config --json
printf 'PASS: configuration syntax is valid and LISTEN_IP is assigned locally.\n'

python_bin="$(select_python)" || die "Python 3.11+ is required to inspect health output."
health_rc=0
health_report="$(run_cli --config "${CONFIG_PATH}" --healthcheck --json)" || health_rc=$?
printf '%s\n' "${health_report}"
[[ "${health_rc}" -eq 0 ]] || die "Output-directory or local-IP health validation failed."

output_dir="$(printf '%s\n' "${health_report}" | "${python_bin}" -c \
    'import json, sys; print(json.load(sys.stdin)["jobs_directory"]["path"])')"
log_dir="$(config_value LOG_DIR /var/log/commercialrchproxy)"
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
case "${output_dir}" in
    /var/lib/commercialrchproxy|/var/lib/commercialrchproxy/*) ;;
    *) die "The hardened unit only permits OUTPUT_DIR below /var/lib/commercialrchproxy: ${output_dir}" ;;
esac
case "${log_dir}" in
    /var/log/commercialrchproxy|/var/log/commercialrchproxy/*) ;;
    *) die "The hardened unit only permits LOG_DIR below /var/log/commercialrchproxy: ${log_dir}" ;;
esac
[[ "${disk_free}" =~ ^[0-9]+$ && "${disk_free}" -gt 0 ]] || \
    die "Disk-free-space check failed for ${output_dir}."

if [[ "${EUID}" -eq 0 ]] && id -u commercialrchproxy >/dev/null 2>&1; then
    runuser -u commercialrchproxy -- test -r "${CONFIG_PATH}" || \
        die "The commercialrchproxy service account cannot read ${CONFIG_PATH}."
    runuser -u commercialrchproxy -- test -x "${output_dir}" || \
        die "The commercialrchproxy service account cannot traverse ${output_dir}."
    runuser -u commercialrchproxy -- test -w "${output_dir}" || \
        die "The commercialrchproxy service account cannot write ${output_dir}."
    runuser -u commercialrchproxy -- test -x "${log_dir}" || \
        die "The commercialrchproxy service account cannot traverse ${log_dir}."
    runuser -u commercialrchproxy -- test -w "${log_dir}" || \
        die "The commercialrchproxy service account cannot write ${log_dir}."
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
if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet commercialrchproxy.service; then
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
