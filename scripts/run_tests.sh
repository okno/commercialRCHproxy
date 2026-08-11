#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

PYTHON_BIN="${PYTHON_BIN:-}"

usage() {
    cat <<'EOF'
Usage: ./scripts/run_tests.sh [--python PATH]

Creates an isolated temporary virtual environment, installs the project with
its declared development dependencies, runs pytest, and syntax-checks every
operations shell script. No production service or network configuration is
touched and no listener/device connection probe is made.
EOF
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --python)
            [[ $# -ge 2 ]] || die "--python requires a path"
            PYTHON_BIN="$2"
            shift 2
            ;;
        --python=*) PYTHON_BIN="${1#*=}"; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown option: $1" ;;
    esac
done

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly PROJECT_ROOT
[[ -f "${PROJECT_ROOT}/pyproject.toml" ]] || die "Missing ${PROJECT_ROOT}/pyproject.toml"
[[ -f "${PROJECT_ROOT}/requirements-dev.lock" ]] || \
    die "Missing ${PROJECT_ROOT}/requirements-dev.lock"
[[ -d "${PROJECT_ROOT}/tests" ]] || die "Missing test directory ${PROJECT_ROOT}/tests"

if [[ -n "${PYTHON_BIN}" ]]; then
    command -v -- "${PYTHON_BIN}" >/dev/null 2>&1 || die "Python interpreter not found: ${PYTHON_BIN}"
    PYTHON_BIN="$(command -v -- "${PYTHON_BIN}")"
else
    for candidate in python3.13 python3.12 python3.11 python3; do
        if command -v "${candidate}" >/dev/null 2>&1 && \
            "${candidate}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
            PYTHON_BIN="$(command -v "${candidate}")"
            break
        fi
    done
fi
[[ -n "${PYTHON_BIN}" ]] || die "Python 3.11 or newer is required."
"${PYTHON_BIN}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || \
    die "${PYTHON_BIN} is older than Python 3.11."

temporary_root="$(mktemp -d "${TMPDIR:-/tmp}/commercialrchproxy-tests.XXXXXX")"
cleanup() {
    local rc=$?
    trap - EXIT INT TERM HUP
    case "${temporary_root}" in
        "${TMPDIR:-/tmp}"/commercialrchproxy-tests.*) rm -rf -- "${temporary_root}" ;;
        *) printf 'WARNING: refusing to remove unexpected temporary path %s\n' "${temporary_root}" >&2 ;;
    esac
    exit "${rc}"
}
trap cleanup EXIT INT TERM HUP

"${PYTHON_BIN}" -m venv "${temporary_root}/venv"
"${temporary_root}/venv/bin/python" -m pip install --disable-pip-version-check \
    --require-hashes --only-binary=:all: -r "${PROJECT_ROOT}/requirements-dev.lock"
"${temporary_root}/venv/bin/python" -m pip install --disable-pip-version-check \
    --no-deps --no-build-isolation "${PROJECT_ROOT}"

export PYTHONDONTWRITEBYTECODE=1
installed_package="$("${temporary_root}/venv/bin/python" -c \
    'from pathlib import Path; import commercialrchproxy; print(Path(commercialrchproxy.__file__).parent)')"
"${temporary_root}/venv/bin/python" -m compileall -q "${installed_package}"
"${temporary_root}/venv/bin/python" -m ruff check --no-cache "${PROJECT_ROOT}/src" "${PROJECT_ROOT}/tests"
"${temporary_root}/venv/bin/python" -m bandit -q -r "${PROJECT_ROOT}/src" -c "${PROJECT_ROOT}/pyproject.toml"
"${temporary_root}/venv/bin/python" -m pytest -p no:cacheprovider "${PROJECT_ROOT}/tests"

for workflow_path in "${PROJECT_ROOT}"/.github/workflows/*.yml; do
    [[ -f "${workflow_path}" ]] || continue
    "${temporary_root}/venv/bin/python" -c \
        'from pathlib import Path; import sys, yaml; yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))' \
        "${workflow_path}"
done

for script_path in "${PROJECT_ROOT}"/scripts/*.sh; do
    bash -n "${script_path}"
done
if [[ -f "${PROJECT_ROOT}/scripts/secret_check.sh" ]]; then
    PYTHON_BIN="${temporary_root}/venv/bin/python" \
        bash "${PROJECT_ROOT}/scripts/secret_check.sh"
fi
printf 'PASS: compile, lint, security, Python tests, workflow/shell syntax, and evidence guards completed.\n'
printf 'RCH protocol reachability: NOT PROBED (requires PCAP/manual evidence).\n'
