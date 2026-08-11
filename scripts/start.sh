#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

readonly SERVICE_NAME="commercialrchproxy.service"
usage() {
    printf 'Usage: sudo ./scripts/start.sh\n'
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        *) die "Unknown option: $1" ;;
    esac
done
[[ "${EUID}" -eq 0 ]] || die "Run as root (for example, with sudo)."

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
"${SCRIPT_DIR}/check_config.sh"
systemctl start "${SERVICE_NAME}"

healthy=0
for _attempt in {1..10}; do
    if "${SCRIPT_DIR}/healthcheck.sh" >/dev/null 2>&1; then
        healthy=1
        break
    fi
    sleep 1
done
[[ "${healthy}" -eq 1 ]] || {
    "${SCRIPT_DIR}/healthcheck.sh" >&2 || true
    die "${SERVICE_NAME} did not become healthy."
}

"${SCRIPT_DIR}/healthcheck.sh"
