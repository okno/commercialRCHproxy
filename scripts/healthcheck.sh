#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

readonly DUMPER_SERVICE="commercialrchproxy-dumper.service"
readonly PARSER_SERVICE="commercialrchproxy-parser.service"
CONFIG_PATH="/etc/commercialrchproxy/commercialrchproxy.conf"
usage() {
    cat <<'EOF'
Usage: ./scripts/healthcheck.sh [--config PATH]

Default checks are passive: systemd state, an exact ss(8) listener match,
configuration/local-IP validation, job storage, and disk space. No network
connection is made. The proxy listener is always inspected with ss rather than
connected to, because opening it would also cause the implementation to open an
upstream port-23 session whose protocol behavior is not yet evidenced.
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
        python_bin="$(select_python)" || die "Python 3.11+ is required to inspect the source tree."
        PYTHONPATH="${PROJECT_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" \
            "${python_bin}" -m commercialrchproxy.dumper.main "$@"
    else
        die "commercialrchproxy-dumper is not installed and no source tree was found."
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

listen_ip="$(config_value LISTEN_IP 192.0.2.231)"
listen_port="$(config_value LISTEN_PORT 23)"

app_args=(--config "${CONFIG_PATH}" --healthcheck --json)

app_rc=0
app_report="$(run_cli "${app_args[@]}")" || app_rc=$?
printf '%s\n' "${app_report}"

overall_rc=0
if [[ "${app_rc}" -ne 0 ]]; then
    printf 'FAIL: application health report returned %d.\n' "${app_rc}" >&2
    overall_rc=1
fi

if command -v systemctl >/dev/null 2>&1; then
    for service_name in "${DUMPER_SERVICE}" "${PARSER_SERVICE}"; do
        if systemctl is-active --quiet "${service_name}"; then
            printf 'PASS: systemd reports %s active.\n' "${service_name}"
        else
            printf 'FAIL: systemd does not report %s active.\n' "${service_name}" >&2
            overall_rc=1
        fi
    done
else
    printf 'FAIL: systemctl is unavailable.\n' >&2
    overall_rc=1
fi

if ! command -v ss >/dev/null 2>&1; then
    printf 'FAIL: ss(8) is unavailable; install iproute2.\n' >&2
    overall_rc=1
elif ss -H -ltn | awk -v endpoint="${listen_ip}:${listen_port}" \
    '$1 == "LISTEN" && $4 == endpoint { found=1 } END { exit(found ? 0 : 1) }'; then
    printf 'PASS: ss reports the exact configured listener %s:%s.\n' "${listen_ip}" "${listen_port}"
else
    printf 'FAIL: ss does not report the exact configured listener %s:%s.\n' "${listen_ip}" "${listen_port}" >&2
    overall_rc=1
fi

printf 'RCH protocol reachability: NOT PROBED (requires PCAP/manual evidence).\n'
printf 'PASS: listener state was inspected passively; no listener or device connection was opened.\n'

exit "${overall_rc}"
