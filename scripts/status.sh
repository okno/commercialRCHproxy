#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

readonly DUMPER_SERVICE="commercialrchproxy-dumper.service"
readonly PARSER_SERVICE="commercialrchproxy-parser.service"
readonly LEGACY_SERVICE="commercialrchproxy.service"
readonly SERVICES=("${DUMPER_SERVICE}" "${PARSER_SERVICE}" "${LEGACY_SERVICE}")
usage() {
    printf 'Usage: ./scripts/status.sh\n'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        *) printf 'ERROR: Unknown option: %s\n' "$1" >&2; exit 1 ;;
    esac
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
status_rc=0
for service_name in "${SERVICES[@]}"; do
    service_rc=0
    systemctl status "${service_name}" --no-pager --full || service_rc=$?
    # The compatibility unit is intentionally disabled/inactive on a direct
    # two-service installation, so it is informational rather than a failure.
    if [[ "${service_name}" != "${LEGACY_SERVICE}" && "${service_rc}" -ne 0 ]]; then
        status_rc="${service_rc}"
    fi
done

health_rc=0
"${SCRIPT_DIR}/healthcheck.sh" || health_rc=$?

if [[ "${health_rc}" -ne 0 ]]; then
    exit "${health_rc}"
fi
exit "${status_rc}"
