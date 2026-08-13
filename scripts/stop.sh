#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

readonly DUMPER_SERVICE="commercialrchproxy-dumper.service"
readonly PARSER_SERVICE="commercialrchproxy-parser.service"
readonly LEGACY_SERVICE="commercialrchproxy.service"
readonly SERVICES=("${DUMPER_SERVICE}" "${PARSER_SERVICE}" "${LEGACY_SERVICE}")

if [[ $# -gt 0 ]]; then
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
        printf 'Usage: sudo ./scripts/stop.sh\n'
        exit 0
    fi
    printf 'ERROR: stop.sh accepts no options.\n' >&2
    exit 1
fi
[[ "${EUID}" -eq 0 ]] || {
    printf 'ERROR: Run as root (for example, with sudo).\n' >&2
    exit 1
}

systemctl stop "${SERVICES[@]}"
for _attempt in {1..10}; do
    active=0
    for service_name in "${SERVICES[@]}"; do
        if systemctl is-active --quiet "${service_name}"; then
            active=1
        fi
    done
    if [[ "${active}" -eq 0 ]]; then
        printf 'PASS: dumper, parser, and legacy coordinator are stopped. No network probe was performed.\n'
        exit 0
    fi
    sleep 1
done
printf 'ERROR: at least one commercialRCHproxy service is still active.\n' >&2
exit 1
