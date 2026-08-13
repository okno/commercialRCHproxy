#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

readonly DUMPER_SERVICE="commercialrchproxy-dumper.service"
readonly PARSER_SERVICE="commercialrchproxy-parser.service"
readonly LEGACY_SERVICE="commercialrchproxy.service"
readonly SERVICES=("${DUMPER_SERVICE}" "${PARSER_SERVICE}")
usage() {
    printf 'Usage: sudo ./scripts/restart.sh\n'
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
systemctl disable "${LEGACY_SERVICE}" >/dev/null 2>&1 || true
systemctl stop "${LEGACY_SERVICE}" >/dev/null 2>&1 || true
if ! systemctl restart "${SERVICES[@]}"; then
    journalctl -u "${DUMPER_SERVICE}" -u "${PARSER_SERVICE}" -n 30 --no-pager >&2 || true
    die "The dumper/parser services could not be restarted."
fi

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
    die "The dumper/parser services did not become healthy after restart."
}

"${SCRIPT_DIR}/healthcheck.sh"
