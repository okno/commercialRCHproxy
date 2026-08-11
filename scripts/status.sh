#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

readonly SERVICE_NAME="commercialrchproxy.service"
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
systemctl status "${SERVICE_NAME}" --no-pager --full || status_rc=$?

health_rc=0
"${SCRIPT_DIR}/healthcheck.sh" || health_rc=$?

if [[ "${health_rc}" -ne 0 ]]; then
    exit "${health_rc}"
fi
exit "${status_rc}"
