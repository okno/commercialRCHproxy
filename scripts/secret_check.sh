#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

status=0

tracked_files() {
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git ls-files -z --cached --others --exclude-standard
  else
    find . -type f -not -path './.venv/*' -not -path './.git/*' -print0
  fi
}

file_list="$(mktemp "${TMPDIR:-/tmp}/commercialrchproxy-secret-files.XXXXXX")"
cleanup() {
  local rc=$?
  trap - EXIT INT TERM HUP
  case "${file_list}" in
    "${TMPDIR:-/tmp}"/commercialrchproxy-secret-files.*) rm -f -- "${file_list}" ;;
    *) printf 'WARNING: refusing to remove unexpected temporary path %s\n' "${file_list}" >&2 ;;
  esac
  exit "${rc}"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

if ! tracked_files >"${file_list}"; then
  printf 'ERROR: failed to enumerate files for the credential scan.\n' >&2
  exit 2
fi

files=()
while IFS= read -r -d '' file; do
  files+=("$file")
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
done <"${file_list}"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    printf 'ERROR: Python is required for the credential scan.\n' >&2
    exit 2
  fi
fi

set +e
"${PYTHON_BIN}" -c '
from pathlib import Path
import re
import sys

patterns = (
    re.compile(rb"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(
        rb"(?:password|api[_-]?key|secret[_-]?key|access[_-]?token)"
        rb"\s*=\s*[^\s#][^\s]{7,}",
        re.IGNORECASE,
    ),
)

found = False
for name in sys.argv[1:]:
    if name.replace("\\", "/") == "scripts/secret_check.sh":
        continue
    path = Path(name)
    try:
        lines = path.read_bytes().splitlines()
    except OSError as exc:
        print(f"ERROR: cannot scan {name}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    for line_number, line in enumerate(lines, 1):
        if any(pattern.search(line) for pattern in patterns):
            print(
                f"ERROR: possible credential material: {name}:{line_number}",
                file=sys.stderr,
            )
            found = True
raise SystemExit(1 if found else 0)
' "${files[@]}"
scan_status=$?
set -e
case "$scan_status" in
  0) ;;
  1) status=1 ;;
  *)
    printf 'ERROR: credential scan failed with status %s.\n' "$scan_status" >&2
    exit 2
    ;;
esac

if [[ "$status" -ne 0 ]]; then
  exit "$status"
fi

printf 'Secret/evidence-file guard: PASS\n'
