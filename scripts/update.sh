#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

PULL_SOURCE=1
RUN_BACKUP=1
START_SERVICE=1
INSTALL_SYSTEM_PACKAGES=0
PYTHON_BIN="${PYTHON_BIN:-}"
BACKUP_DIR="/var/backups/commercialrchproxy"

usage() {
    cat <<'EOF'
Usage: sudo ./scripts/update.sh [options]

Options:
  --python PATH              Python 3.11+ interpreter for tests/deployment
  --no-pull                  Deploy the current checkout without Git fetch/merge
  --skip-backup              Explicitly skip the pre-update backup
  --backup-destination DIR   Override /var/backups/commercialrchproxy
  --with-system-packages     Allow install.sh to refresh apt dependencies
  --no-start                 Leave both independent services stopped after deployment
  -h, --help                 Show this help

The updater accepts only a clean, dedicated Git checkout and a fast-forward
from its configured upstream. Release activation is atomic and install.sh
restores the previous active release if activation fails. Configuration,
captured jobs, and logs are never overwritten. No network settings are changed.
EOF
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

note() {
    printf '[commercialRCHproxy update] %s\n' "$*"
}

acquire_mutation_lock() {
    local lock_path="/run/commercialrchproxy-mutation.lock"
    local inherited_target
    local previous_umask
    if [[ -e "${lock_path}" ]]; then
        [[ -f "${lock_path}" && ! -L "${lock_path}" && "$(stat -c '%u' -- "${lock_path}")" == "0" ]] || \
            die "Mutation lock must be a root-owned regular non-symlink file: ${lock_path}"
        chmod 0600 -- "${lock_path}"
    fi
    if [[ "${COMMERCIALRCHPROXY_MUTATION_LOCK_HELD:-0}" == "1" ]]; then
        [[ -e /proc/self/fd/9 ]] || die "Inherited mutation-lock descriptor 9 is unavailable."
        inherited_target="$(readlink -f -- /proc/self/fd/9)"
        [[ "${inherited_target}" == "${lock_path}" ]] || die "Inherited mutation lock points to an unexpected path."
    else
        previous_umask="$(umask)"
        umask 0077
        exec 9>"${lock_path}"
        umask "${previous_umask}"
        chmod 0600 -- "${lock_path}"
    fi
    flock -n 9 || die "Another commercialRCHproxy install, update, backup, or uninstall is running."
    export COMMERCIALRCHPROXY_MUTATION_LOCK_HELD=1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --python)
            [[ $# -ge 2 ]] || die "--python requires a path"
            PYTHON_BIN="$2"
            shift 2
            ;;
        --python=*) PYTHON_BIN="${1#*=}"; shift ;;
        --no-pull) PULL_SOURCE=0; shift ;;
        --skip-backup) RUN_BACKUP=0; shift ;;
        --backup-destination)
            [[ $# -ge 2 ]] || die "--backup-destination requires a directory"
            BACKUP_DIR="$2"
            shift 2
            ;;
        --backup-destination=*) BACKUP_DIR="${1#*=}"; shift ;;
        --with-system-packages) INSTALL_SYSTEM_PACKAGES=1; shift ;;
        --no-start) START_SERVICE=0; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown option: $1" ;;
    esac
done

[[ "${EUID}" -eq 0 ]] || die "Run as root (for example, with sudo)."
command -v flock >/dev/null 2>&1 || die "flock is required (package: util-linux)."
acquire_mutation_lock

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly PROJECT_ROOT
for required in install backup run_tests; do
    [[ -f "${PROJECT_ROOT}/scripts/${required}.sh" ]] || die "Missing scripts/${required}.sh"
done
[[ -x /opt/commercialrchproxy/current/venv/bin/commercialrchproxy ]] || \
    die "No active installed release was found; use scripts/install.sh for the initial deployment."

source_uid="$(stat -c '%u' -- "${PROJECT_ROOT}")"
source_user="$(getent passwd "${source_uid}" | awk -F: 'NR == 1 {print $1}')"
[[ -n "${source_user}" ]] || die "Cannot map source owner UID ${source_uid} to a local user."

run_as_source_owner() {
    if [[ "${source_uid}" -eq 0 ]]; then
        "$@"
    else
        runuser -u "${source_user}" -- "$@"
    fi
}

git_source() {
    run_as_source_owner git -C "${PROJECT_ROOT}" "$@"
}

old_revision="not-a-git-checkout"
new_revision="not-a-git-checkout"

# Back up configuration, state, logs, and the complete active release before
# any source checkout or dependency is changed.
if [[ "${RUN_BACKUP}" -eq 1 ]]; then
    note "Creating a consistent pre-update backup"
    bash "${PROJECT_ROOT}/scripts/backup.sh" --destination "${BACKUP_DIR}"
else
    printf 'WARNING: pre-update backup explicitly skipped (--skip-backup).\n' >&2
fi

if [[ "${PULL_SOURCE}" -eq 1 ]]; then
    command -v git >/dev/null 2>&1 || die "git is required unless --no-pull is used."
    git_root="$(git_source rev-parse --show-toplevel 2>/dev/null || true)"
    [[ -n "${git_root}" && "$(realpath -m -- "${git_root}")" == "${PROJECT_ROOT}" ]] || \
        die "Default update requires commercialRCHproxy to be the root of its own Git checkout; use --no-pull to deploy an already prepared source tree."
    [[ -z "$(git_source status --porcelain=v1)" ]] || \
        die "Source checkout has tracked or untracked changes. Commit, stash, or remove them before update."
    branch="$(git_source symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
    [[ -n "${branch}" ]] || die "Detached HEAD updates are refused. Check out a branch or use --no-pull."
    upstream="$(git_source rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"
    [[ -n "${upstream}" ]] || die "Branch ${branch} has no configured upstream."
    old_revision="$(git_source rev-parse HEAD)"
    note "Fetching the configured upstream for ${branch}"
    git_source fetch --prune
    git_source merge-base --is-ancestor HEAD "${upstream}" || \
        die "Update is not a fast-forward from HEAD to ${upstream}; refusing to rewrite history."
    git_source pull --ff-only
    new_revision="$(git_source rev-parse HEAD)"
    [[ -z "$(git_source status --porcelain=v1)" ]] || die "Checkout became dirty after fast-forward."
else
    note "Skipping Git operations by explicit request (--no-pull)."
fi

test_args=()
install_args=(--skip-system-packages)
if [[ -n "${PYTHON_BIN}" ]]; then
    test_args+=(--python "${PYTHON_BIN}")
    install_args+=(--python="${PYTHON_BIN}")
fi
if [[ "${INSTALL_SYSTEM_PACKAGES}" -eq 1 ]]; then
    install_args=()
    if [[ -n "${PYTHON_BIN}" ]]; then
        install_args+=(--python="${PYTHON_BIN}")
    fi
fi
if [[ "${START_SERVICE}" -eq 0 ]]; then
    install_args+=(--no-start)
fi
note "Running the test suite as source owner ${source_user}"
run_as_source_owner bash "${PROJECT_ROOT}/scripts/run_tests.sh" "${test_args[@]}"

note "Building and atomically activating the new release"
bash "${PROJECT_ROOT}/scripts/install.sh" "${install_args[@]}"
printf 'PASS: update complete (source %s -> %s).\n' "${old_revision}" "${new_revision}"
printf 'PASS: configuration, captured jobs, and logs were preserved.\n'
printf 'PASS: no host network settings were changed.\n'
