#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

readonly SERVICE_NAME="commercialrchproxy.service"

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

systemctl stop "${SERVICE_NAME}"
for _attempt in {1..10}; do
    if ! systemctl is-active --quiet "${SERVICE_NAME}"; then
        printf 'PASS: %s is stopped. No network probe was performed.\n' "${SERVICE_NAME}"
        exit 0
    fi
    sleep 1
done
printf 'ERROR: %s is still active.\n' "${SERVICE_NAME}" >&2
exit 1
