#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

status=0

tracked_files() {
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git ls-files --cached --others --exclude-standard
  else
    find . -type f -not -path './.venv/*' -not -path './.git/*' -print
  fi
}

while IFS= read -r file; do
  case "$file" in
    *.pcap|*.pcapng|*.raw|*.pdf|*.key|*.pem|*.p12|*.pfx)
      printf 'ERROR: prohibited evidence/secret file: %s\n' "$file" >&2
      status=1
      ;;
  esac
  case "${file##*/}" in
    .env.example) ;;
    .env|.env.*|commercialrchproxy.conf)
      printf 'ERROR: prohibited private configuration file: %s\n' "$file" >&2
      status=1
      ;;
  esac
done < <(tracked_files)

command -v rg >/dev/null 2>&1 || {
  printf 'ERROR: ripgrep is required for the credential scan.\n' >&2
  exit 2
}
set +e
rg -n --hidden \
  --glob '!.git/**' --glob '!.venv/**' --glob '!scripts/secret_check.sh' \
  '(BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|(?i)(password|api[_-]?key|secret[_-]?key|access[_-]?token)[[:space:]]*=[[:space:]]*[^[:space:]#][^[:space:]]{7,})' .
scan_status=$?
set -e
case "$scan_status" in
  0)
    printf 'ERROR: possible credential material found; review every match.\n' >&2
    status=1
    ;;
  1) ;;
  *)
    printf 'ERROR: ripgrep credential scan failed with status %s.\n' "$scan_status" >&2
    exit 2
    ;;
esac

if [[ "$status" -ne 0 ]]; then
  exit "$status"
fi

printf 'Secret/evidence-file guard: PASS\n'
