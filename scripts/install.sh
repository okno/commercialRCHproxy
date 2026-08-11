#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

readonly SERVICE_NAME="commercialrchproxy.service"
readonly SERVICE_USER="commercialrchproxy"
readonly SERVICE_GROUP="commercialrchproxy"
readonly CONFIG_DIR="/etc/commercialrchproxy"
readonly CONFIG_PATH="${CONFIG_DIR}/commercialrchproxy.conf"
readonly APP_ROOT="/opt/commercialrchproxy"
readonly RELEASES_DIR="${APP_ROOT}/releases"
readonly CURRENT_LINK="${APP_ROOT}/current"
readonly DATA_DIR="/var/lib/commercialrchproxy"
readonly LOG_DIR="/var/log/commercialrchproxy"
readonly LIBEXEC_DIR="/usr/local/libexec/commercialrchproxy"
readonly UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}"

START_SERVICE=1
INSTALL_SYSTEM_PACKAGES=1
PYTHON_BIN="${PYTHON_BIN:-}"
SITE_CONFIG=""
NEW_RELEASE=""
SWITCHED=0
INSTALL_STATE_DIRTY=0
PREVIOUS_TARGET=""
WAS_ACTIVE=0
PREVIOUS_ENABLE_STATE="not-found"
ROLLBACK_DIR=""
TEMPORARY_LINK=""

usage() {
    cat <<'EOF'
Usage: sudo ./scripts/install.sh [options]

Options:
  --python PATH              Python 3.11+ interpreter to use
  --config PATH              Site-edited configuration for a first install
  --skip-system-packages     Do not run apt-get
  --no-start                 Install and enable, but do not start the service
  -h, --help                 Show this help

This installer never creates, removes, or changes host IP addresses, routes,
firewall rules, or DNS settings. LISTEN_IP must already be assigned locally.
EOF
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

note() {
    printf '[commercialRCHproxy] %s\n' "$*"
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

config_value() {
    local wanted="$1"
    awk -v wanted="${wanted}" '
        /^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
        {
            separator = index($0, "=")
            if (!separator) next
            key = substr($0, 1, separator - 1)
            value = substr($0, separator + 1)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
            if (key == wanted) {
                if ((substr(value,1,1) == "\"" && substr(value,length(value),1) == "\"") ||
                    (substr(value,1,1) == "\047" && substr(value,length(value),1) == "\047")) {
                    value = substr(value, 2, length(value) - 2)
                }
                print value
                exit
            }
        }
    ' "${CONFIG_PATH}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --python)
            [[ $# -ge 2 ]] || die "--python requires a path"
            PYTHON_BIN="$2"
            shift 2
            ;;
        --python=*) PYTHON_BIN="${1#*=}"; shift ;;
        --config)
            [[ $# -ge 2 ]] || die "--config requires a path"
            SITE_CONFIG="$2"
            shift 2
            ;;
        --config=*) SITE_CONFIG="${1#*=}"; shift ;;
        --skip-system-packages) INSTALL_SYSTEM_PACKAGES=0; shift ;;
        --no-start) START_SERVICE=0; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown option: $1" ;;
    esac
done

[[ "${EUID}" -eq 0 ]] || die "Run this installer as root (for example, with sudo)."
[[ -r /etc/os-release ]] || die "Cannot identify this operating system."
os_id="$(awk -F= '$1 == "ID" {gsub(/^\"|\"$/, "", $2); print tolower($2); exit}' /etc/os-release)"
os_like="$(awk -F= '$1 == "ID_LIKE" {gsub(/^\"|\"$/, "", $2); print tolower($2); exit}' /etc/os-release)"
case " ${os_id} ${os_like} " in
    *" debian "*|*" ubuntu "*) ;;
    *) die "Supported operating systems are Debian and Ubuntu; detected ID=${os_id:-unknown}." ;;
esac

command -v flock >/dev/null 2>&1 || die "flock is required (package: util-linux)."
acquire_mutation_lock

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
readonly PROJECT_ROOT
readonly UNIT_SOURCE="${PROJECT_ROOT}/systemd/${SERVICE_NAME}"
readonly CONFIG_EXAMPLE="${PROJECT_ROOT}/.env.example"
readonly DEPLOYMENT_LOCK="${PROJECT_ROOT}/requirements-deployment.lock"

if [[ -n "${SITE_CONFIG}" ]]; then
    [[ -e "${SITE_CONFIG}" && -f "${SITE_CONFIG}" && ! -L "${SITE_CONFIG}" ]] || \
        die "--config must name a readable regular non-symlink file."
    SITE_CONFIG="$(realpath -e -- "${SITE_CONFIG}")"
    [[ -r "${SITE_CONFIG}" ]] || die "Cannot read site configuration: ${SITE_CONFIG}"
elif [[ ! -e "${CONFIG_PATH}" ]]; then
    die "First install requires a private site configuration. Copy .env.example outside Git, replace both RFC 5737 addresses, then rerun with --config PATH."
fi

[[ -f "${PROJECT_ROOT}/pyproject.toml" ]] || die "Missing ${PROJECT_ROOT}/pyproject.toml"
[[ -d "${PROJECT_ROOT}/src/commercialrchproxy" ]] || die "Missing application package under ${PROJECT_ROOT}/src"
[[ -f "${UNIT_SOURCE}" ]] || die "Missing systemd unit ${UNIT_SOURCE}"
[[ -f "${CONFIG_EXAMPLE}" ]] || die "Missing configuration example ${CONFIG_EXAMPLE}"
[[ -f "${DEPLOYMENT_LOCK}" ]] || die "Missing hashed deployment lock ${DEPLOYMENT_LOCK}"

required_scripts=(install update uninstall start stop restart status healthcheck run_tests check_config backup)
for script_name in "${required_scripts[@]}"; do
    [[ -f "${PROJECT_ROOT}/scripts/${script_name}.sh" ]] || die "Missing scripts/${script_name}.sh"
done

if [[ "${INSTALL_SYSTEM_PACKAGES}" -eq 1 ]]; then
    command -v apt-get >/dev/null 2>&1 || die "apt-get is required on Debian/Ubuntu."
    note "Installing base operating-system dependencies"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends \
        ca-certificates coreutils iproute2 python3 python3-pip python3-venv ripgrep tar util-linux
fi

select_python() {
    local candidate
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
    [[ -n "${PYTHON_BIN}" ]] || die "Python 3.11 or newer is required. Install it without adding an untrusted package repository, then rerun with --python=/path."
    "${PYTHON_BIN}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || \
        die "${PYTHON_BIN} is older than Python 3.11."
}
select_python
note "Using $(${PYTHON_BIN} --version 2>&1) at ${PYTHON_BIN}"

if ! getent group "${SERVICE_GROUP}" >/dev/null; then
    groupadd --system "${SERVICE_GROUP}"
fi
if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
    useradd --system --gid "${SERVICE_GROUP}" --home-dir "${DATA_DIR}" \
        --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
fi
[[ "$(id -gn "${SERVICE_USER}")" == "${SERVICE_GROUP}" ]] || \
    die "Existing user ${SERVICE_USER} does not have ${SERVICE_GROUP} as its primary group."

for protected_path in "${CONFIG_DIR}" "${APP_ROOT}" "${DATA_DIR}" "${LOG_DIR}" "${LIBEXEC_DIR}"; do
    [[ ! -L "${protected_path}" ]] || die "Refusing to manage symlinked path: ${protected_path}"
done

install -d -m 0750 -o root -g "${SERVICE_GROUP}" -- "${CONFIG_DIR}"
install -d -m 0755 -o root -g root -- "${APP_ROOT}" "${RELEASES_DIR}"
install -d -m 0750 -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -- "${DATA_DIR}" "${DATA_DIR}/jobs" "${LOG_DIR}"
install -d -m 0755 -o root -g root -- "${LIBEXEC_DIR}"

# Existing production configuration is deliberately never overwritten.
install -m 0640 -o root -g "${SERVICE_GROUP}" -- "${CONFIG_EXAMPLE}" "${CONFIG_PATH}.example"
if [[ ! -e "${CONFIG_PATH}" ]]; then
    install -m 0640 -o root -g "${SERVICE_GROUP}" -- "${SITE_CONFIG}" "${CONFIG_PATH}"
    note "Installed the supplied private site configuration at ${CONFIG_PATH}."
else
    [[ -z "${SITE_CONFIG}" ]] || \
        die "${CONFIG_PATH} already exists and is never overwritten; edit it explicitly, then rerun without --config."
    [[ -f "${CONFIG_PATH}" && ! -L "${CONFIG_PATH}" ]] || die "Configuration must be a regular, non-symlink file: ${CONFIG_PATH}"
    chown root:"${SERVICE_GROUP}" -- "${CONFIG_PATH}"
    chmod 0640 -- "${CONFIG_PATH}"
    note "Preserved existing ${CONFIG_PATH}"
fi

configured_listen_ip="$(config_value LISTEN_IP)"
configured_printer_ip="$(config_value PRINTER_IP)"
[[ -n "${configured_listen_ip}" && -n "${configured_printer_ip}" ]] || \
    die "Configuration must explicitly set both LISTEN_IP and PRINTER_IP."
for configured_ip in "${configured_listen_ip}" "${configured_printer_ip}"; do
    case "${configured_ip}" in
        192.0.2.*|198.51.100.*|203.0.113.*)
            die "Configuration contains an RFC 5737 documentation address; replace it with an approved private site address."
            ;;
    esac
done

release_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
NEW_RELEASE="${RELEASES_DIR}/${release_id}"
case "${NEW_RELEASE}" in
    "${RELEASES_DIR}"/*) ;;
    *) die "Internal release path validation failed." ;;
esac
[[ ! -e "${NEW_RELEASE}" ]] || die "Release path already exists: ${NEW_RELEASE}"
install -d -m 0755 -o root -g root -- "${NEW_RELEASE}"

remove_new_release() {
    [[ -n "${NEW_RELEASE}" && -d "${NEW_RELEASE}" ]] || return 0
    case "${NEW_RELEASE}" in
        "${RELEASES_DIR}"/*) rm -rf -- "${NEW_RELEASE}" || return 1 ;;
        *) return 1 ;;
    esac
    NEW_RELEASE=""
}

remove_rollback_dir() {
    [[ -n "${ROLLBACK_DIR}" && -d "${ROLLBACK_DIR}" ]] || return 0
    case "${ROLLBACK_DIR}" in
        /run/commercialrchproxy-install-rollback.*) rm -rf -- "${ROLLBACK_DIR}" || return 1 ;;
        *) return 1 ;;
    esac
    ROLLBACK_DIR=""
}

remove_temporary_link() {
    [[ -n "${TEMPORARY_LINK}" ]] || return 0
    case "${TEMPORARY_LINK}" in
        "${APP_ROOT}"/.current.*) rm -f -- "${TEMPORARY_LINK}" || return 1 ;;
        *) return 1 ;;
    esac
    TEMPORARY_LINK=""
}

rollback_step() {
    local description="$1"
    shift
    if ! "$@"; then
        printf 'ROLLBACK ERROR: %s\n' "${description}" >&2
        ROLLBACK_FAILED=1
    fi
}

ensure_service_stopped() {
    systemctl stop "${SERVICE_NAME}" >/dev/null 2>&1 || true
    ! systemctl is-active --quiet "${SERVICE_NAME}"
}

ensure_service_not_enabled() {
    local enabled_state
    systemctl disable "${SERVICE_NAME}" >/dev/null 2>&1 || true
    enabled_state="$(systemctl is-enabled "${SERVICE_NAME}" 2>/dev/null || true)"
    [[ "${enabled_state}" != "enabled" && "${enabled_state}" != "enabled-runtime" ]]
}

rollback_release() {
    ROLLBACK_FAILED=0
    set +e
    note "Activation failed; restoring the complete previous installed state"
    rollback_step "could not stop the newly activated service" ensure_service_stopped
    case "${PREVIOUS_ENABLE_STATE}" in
        enabled|enabled-runtime) ;;
        *) rollback_step "could not remove newly created enablement links" ensure_service_not_enabled ;;
    esac

    if [[ "${SWITCHED}" -eq 1 ]]; then
        if [[ -n "${PREVIOUS_TARGET}" ]]; then
            local rollback_link="${APP_ROOT}/.current.rollback.$$"
            rollback_step "could not clear the temporary rollback link" rm -f -- "${rollback_link}"
            rollback_step "could not create the previous-release rollback link" \
                ln -s -- "${PREVIOUS_TARGET}" "${rollback_link}"
            rollback_step "could not restore the previous current link" \
                mv -Tf -- "${rollback_link}" "${CURRENT_LINK}"
        else
            rollback_step "could not remove the first-install current link" rm -f -- "${CURRENT_LINK}"
        fi
    fi

    if [[ -n "${ROLLBACK_DIR}" ]]; then
        for script_name in "${required_scripts[@]}"; do
            if [[ -f "${ROLLBACK_DIR}/libexec/${script_name}.sh" ]]; then
                rollback_step "could not restore operations script ${script_name}.sh" \
                    cp -a -- "${ROLLBACK_DIR}/libexec/${script_name}.sh" "${LIBEXEC_DIR}/${script_name}.sh"
            else
                rollback_step "could not remove new operations script ${script_name}.sh" \
                    rm -f -- "${LIBEXEC_DIR}/${script_name}.sh"
            fi
        done
        if [[ -f "${ROLLBACK_DIR}/commercialrchproxy.service" ]]; then
            rollback_step "could not restore the previous systemd unit" \
                cp -a -- "${ROLLBACK_DIR}/commercialrchproxy.service" "${UNIT_PATH}"
        else
            rollback_step "could not remove the new systemd unit" rm -f -- "${UNIT_PATH}"
        fi
    else
        printf 'ROLLBACK ERROR: rollback staging directory is unavailable.\n' >&2
        ROLLBACK_FAILED=1
    fi

    rollback_step "systemd daemon-reload failed after file restoration" systemctl daemon-reload
    case "${PREVIOUS_ENABLE_STATE}" in
        enabled) rollback_step "could not restore persistent enablement" systemctl enable "${SERVICE_NAME}" ;;
        enabled-runtime) rollback_step "could not restore runtime enablement" systemctl enable --runtime "${SERVICE_NAME}" ;;
        masked) rollback_step "could not restore persistent mask" systemctl mask "${SERVICE_NAME}" ;;
        masked-runtime) rollback_step "could not restore runtime mask" systemctl mask --runtime "${SERVICE_NAME}" ;;
    esac
    if [[ "${WAS_ACTIVE}" -eq 1 && -f "${ROLLBACK_DIR}/commercialrchproxy.service" ]]; then
        rollback_step "could not restart the previously active service" systemctl restart "${SERVICE_NAME}"
    elif [[ "${WAS_ACTIVE}" -eq 1 ]]; then
        printf 'ROLLBACK ERROR: prior service was active but its unit backup is unavailable.\n' >&2
        ROLLBACK_FAILED=1
    else
        rollback_step "could not restore the inactive service state" ensure_service_stopped
    fi

    if [[ "${ROLLBACK_FAILED}" -eq 0 ]]; then
        remove_temporary_link || ROLLBACK_FAILED=1
    fi
    if [[ "${ROLLBACK_FAILED}" -eq 0 ]]; then
        remove_new_release || ROLLBACK_FAILED=1
    fi
    if [[ "${ROLLBACK_FAILED}" -eq 0 ]]; then
        remove_rollback_dir || ROLLBACK_FAILED=1
    fi
    if [[ "${ROLLBACK_FAILED}" -ne 0 ]]; then
        printf 'CRITICAL: rollback was incomplete. Preserve %s and %s for manual recovery.\n' \
            "${NEW_RELEASE:-<no-new-release-path>}" "${ROLLBACK_DIR:-<no-rollback-directory>}" >&2
        set -e
        return 1
    fi
    SWITCHED=0
    INSTALL_STATE_DIRTY=0
    set -e
    return 0
}

cleanup_on_exit() {
    local rc=$?
    trap - EXIT
    if [[ "${rc}" -ne 0 ]]; then
        if [[ "${INSTALL_STATE_DIRTY}" -eq 1 || "${SWITCHED}" -eq 1 ]]; then
            rollback_release || \
                printf 'CRITICAL: automatic rollback requires manual recovery.\n' >&2
        else
            remove_temporary_link || printf 'WARNING: failed to remove temporary activation link %s.\n' "${TEMPORARY_LINK}" >&2
            remove_new_release || printf 'WARNING: failed to remove incomplete release %s.\n' "${NEW_RELEASE}" >&2
            remove_rollback_dir || printf 'WARNING: failed to remove rollback staging %s.\n' "${ROLLBACK_DIR}" >&2
        fi
    fi
    exit "${rc}"
}
trap cleanup_on_exit EXIT

note "Building isolated release ${release_id}"
if ! "${PYTHON_BIN}" -m venv "${NEW_RELEASE}/venv"; then
    die "Could not create a virtual environment. Install the venv package matching ${PYTHON_BIN}."
fi
"${NEW_RELEASE}/venv/bin/python" -m pip install --disable-pip-version-check \
    --require-hashes --only-binary=:all: -r "${DEPLOYMENT_LOCK}"
"${NEW_RELEASE}/venv/bin/python" -m pip install --disable-pip-version-check \
    --no-deps --no-build-isolation "${PROJECT_ROOT}"
"${NEW_RELEASE}/venv/bin/commercialrchproxy" --version

git_root="$(git -C "${PROJECT_ROOT}" rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -n "${git_root}" && "$(realpath -m -- "${git_root}")" == "${PROJECT_ROOT}" ]]; then
    git -C "${PROJECT_ROOT}" rev-parse HEAD >"${NEW_RELEASE}/SOURCE_REVISION"
fi

# This validates syntax and local IP assignment by binding an ephemeral local
# socket only. It does not connect to the listener or the RCH device.
if ! runuser -u "${SERVICE_USER}" -- \
    "${NEW_RELEASE}/venv/bin/commercialrchproxy" --config "${CONFIG_PATH}" --check-config --json; then
    die "Configuration validation failed. This installer will not alter networking; assign LISTEN_IP through the host's normal network configuration, correct ${CONFIG_PATH}, and rerun."
fi

if [[ -L "${CURRENT_LINK}" ]]; then
    PREVIOUS_TARGET="$(readlink -- "${CURRENT_LINK}")"
elif [[ -e "${CURRENT_LINK}" ]]; then
    die "Refusing to replace non-symlink path ${CURRENT_LINK}"
fi
if systemctl is-active --quiet "${SERVICE_NAME}"; then
    WAS_ACTIVE=1
fi
PREVIOUS_ENABLE_STATE="$(systemctl is-enabled "${SERVICE_NAME}" 2>/dev/null || true)"
[[ -n "${PREVIOUS_ENABLE_STATE}" ]] || PREVIOUS_ENABLE_STATE="not-found"

[[ ! -L "${UNIT_PATH}" ]] || die "Refusing to replace symlinked or masked unit ${UNIT_PATH}."
ROLLBACK_DIR="$(mktemp -d /run/commercialrchproxy-install-rollback.XXXXXX)"
chmod 0700 -- "${ROLLBACK_DIR}"
install -d -m 0700 -- "${ROLLBACK_DIR}/libexec"
if [[ -f "${UNIT_PATH}" ]]; then
    cp -a -- "${UNIT_PATH}" "${ROLLBACK_DIR}/commercialrchproxy.service"
elif [[ -e "${UNIT_PATH}" ]]; then
    die "Existing unit path is not a regular file: ${UNIT_PATH}"
fi
for script_name in "${required_scripts[@]}"; do
    installed_script="${LIBEXEC_DIR}/${script_name}.sh"
    [[ ! -L "${installed_script}" ]] || die "Refusing to replace symlinked operations script: ${installed_script}"
    if [[ -f "${installed_script}" ]]; then
        cp -a -- "${installed_script}" "${ROLLBACK_DIR}/libexec/${script_name}.sh"
    elif [[ -e "${installed_script}" ]]; then
        die "Existing operations path is not a regular file: ${installed_script}"
    fi
done

INSTALL_STATE_DIRTY=1
for script_name in "${required_scripts[@]}"; do
    install -m 0755 -o root -g root -- \
        "${PROJECT_ROOT}/scripts/${script_name}.sh" "${LIBEXEC_DIR}/${script_name}.sh"
done
install -m 0644 -o root -g root -- "${UNIT_SOURCE}" "${UNIT_PATH}"

TEMPORARY_LINK="${APP_ROOT}/.current.$$"
rm -f -- "${TEMPORARY_LINK}"
ln -s -- "${NEW_RELEASE}" "${TEMPORARY_LINK}"
mv -Tf -- "${TEMPORARY_LINK}" "${CURRENT_LINK}"
TEMPORARY_LINK=""
SWITCHED=1
if ! "${LIBEXEC_DIR}/check_config.sh"; then
    die "Deployment configuration, local bind, storage, or permission checks failed."
fi
systemctl daemon-reload
if command -v systemd-analyze >/dev/null 2>&1; then
    if ! systemd-analyze verify "${UNIT_PATH}"; then
        die "systemd rejected ${UNIT_PATH}"
    fi
fi
if ! systemctl enable "${SERVICE_NAME}"; then
    die "Could not enable ${SERVICE_NAME}"
fi

if [[ "${START_SERVICE}" -eq 1 ]]; then
    if [[ "${WAS_ACTIVE}" -eq 1 ]]; then
        service_action=restart
    else
        service_action=start
    fi
    if ! systemctl "${service_action}" "${SERVICE_NAME}"; then
        journalctl -u "${SERVICE_NAME}" -n 30 --no-pager >&2 || true
        die "The service failed to ${service_action}; automatic rollback will be attempted."
    fi

    healthy=0
    for _attempt in {1..10}; do
        if "${LIBEXEC_DIR}/healthcheck.sh" >/dev/null 2>&1; then
            healthy=1
            break
        fi
        sleep 1
    done
    if [[ "${healthy}" -ne 1 ]]; then
        "${LIBEXEC_DIR}/healthcheck.sh" >&2 || true
        die "Post-start health checks failed; automatic rollback will be attempted."
    fi

    "${LIBEXEC_DIR}/healthcheck.sh"
    note "RCH protocol reachability: NOT PROBED (requires PCAP/manual evidence)."
else
    if [[ "${WAS_ACTIVE}" -eq 1 ]]; then
        systemctl stop "${SERVICE_NAME}"
    fi
    note "Installed and enabled ${SERVICE_NAME} without starting it (--no-start)."
    note "RCH protocol reachability: NOT PROBED (requires PCAP/manual evidence)."
fi

trap - EXIT
INSTALL_STATE_DIRTY=0
SWITCHED=2
if ! remove_rollback_dir; then
    printf 'WARNING: deployment succeeded but rollback staging could not be removed: %s\n' "${ROLLBACK_DIR}" >&2
fi
note "Installed release ${release_id}. Configuration, captured jobs, and logs were preserved."
note "No host network settings were changed."
