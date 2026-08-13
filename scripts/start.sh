#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

readonly DUMPER_SERVICE="commercialrchproxy-dumper.service"
readonly PARSER_SERVICE="commercialrchproxy-parser.service"
readonly LEGACY_SERVICE="commercialrchproxy.service"
readonly SERVICES=("${DUMPER_SERVICE}" "${PARSER_SERVICE}")
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
# New installations operate the real services directly.  Keep the legacy
# coordinator disabled so systemd has one unambiguous owner for enablement.
systemctl disable "${LEGACY_SERVICE}" >/dev/null 2>&1 || true
if ! systemctl start "${SERVICES[@]}"; then
    journalctl -u "${DUMPER_SERVICE}" -u "${PARSER_SERVICE}" -n 30 --no-pager >&2 || true
    die "The dumper/parser services could not be started."
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
    die "The dumper/parser services did not become healthy."
}

"${SCRIPT_DIR}/healthcheck.sh"
