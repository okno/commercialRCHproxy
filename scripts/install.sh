#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

readonly DUMPER_SERVICE="commercialrchproxy-dumper.service"
readonly PARSER_SERVICE="commercialrchproxy-parser.service"
readonly LEGACY_SERVICE="commercialrchproxy.service"
readonly MANAGED_SERVICES=("${DUMPER_SERVICE}" "${PARSER_SERVICE}")
readonly ALL_SERVICES=("${DUMPER_SERVICE}" "${PARSER_SERVICE}" "${LEGACY_SERVICE}")
readonly CONFIG_DIR="/etc/commercialrchproxy"
readonly CONFIG_PATH="${CONFIG_DIR}/commercialrchproxy.conf"
readonly APP_ROOT="/opt/commercialrchproxy"
readonly RELEASES_DIR="${APP_ROOT}/releases"
readonly CURRENT_LINK="${APP_ROOT}/current"
readonly LIBEXEC_DIR="/usr/local/libexec/commercialrchproxy"
readonly UNIT_DIR="/etc/systemd/system"
readonly SECONDARY_MARKER="# Managed by commercialRCHproxy manage_secondary_ip.sh"
readonly DUMPER_SECONDARY_DROPIN="${UNIT_DIR}/${DUMPER_SERVICE}.d/10-secondary-ip.conf"
readonly LEGACY_SECONDARY_DROPIN="${UNIT_DIR}/${LEGACY_SERVICE}.d/10-secondary-ip.conf"
readonly SECONDARY_HELPER="/usr/local/libexec/commercialrchproxy-network/manage_secondary_ip.sh"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
# shellcheck source=scripts/config_contract.sh
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/config_contract.sh"

START_SERVICE=1
INSTALL_SYSTEM_PACKAGES=1
PYTHON_BIN="${PYTHON_BIN:-}"
SITE_CONFIG=""
NEW_RELEASE=""
SWITCHED=0
INSTALL_STATE_DIRTY=0
PREVIOUS_TARGET=""
declare -A WAS_ACTIVE=()
declare -A PREVIOUS_ENABLE_STATE=()
ROLLBACK_DIR=""
TEMPORARY_LINK=""
CONFIG_INPUT=""

usage() {
    cat <<'EOF'
Usage: sudo ./scripts/install.sh [options]

Options:
  --python PATH              Python 3.11+ interpreter to use
  --config PATH              Site-edited configuration for a first install
  --skip-system-packages     Do not run apt-get
  --no-start                 Install and enable, but do not start Dumper/Parser
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

render_service_unit() {
    local service_name="$1"
    local destination="$2"
    local source_path="${UNIT_SOURCE_DIR}/${service_name}"
    local render_paths=true
    if [[ "${service_name}" == "${LEGACY_SERVICE}" ]]; then
        render_paths=false
    fi
    crch_render_service_unit "${source_path}" "${destination}" \
        "${SERVICE_USER}" "${SERVICE_GROUP}" "${OUTPUT_DIR}" "${LOG_DIR}" "${render_paths}" || \
        die "Could not safely render ${source_path}."
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

PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
readonly PROJECT_ROOT
readonly UNIT_SOURCE_DIR="${PROJECT_ROOT}/systemd"
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
for service_name in "${ALL_SERVICES[@]}"; do
    [[ -f "${UNIT_SOURCE_DIR}/${service_name}" ]] || \
        die "Missing systemd unit ${UNIT_SOURCE_DIR}/${service_name}"
done
[[ -f "${CONFIG_EXAMPLE}" ]] || die "Missing configuration example ${CONFIG_EXAMPLE}"
[[ -f "${DEPLOYMENT_LOCK}" ]] || die "Missing hashed deployment lock ${DEPLOYMENT_LOCK}"

required_scripts=(install update uninstall start stop restart status healthcheck run_tests check_config backup config_contract)
for script_name in "${required_scripts[@]}"; do
    [[ -f "${PROJECT_ROOT}/scripts/${script_name}.sh" ]] || die "Missing scripts/${script_name}.sh"
done
[[ -f "${PROJECT_ROOT}/scripts/manage_secondary_ip.sh" ]] || \
    die "Missing scripts/manage_secondary_ip.sh"

if [[ "${INSTALL_SYSTEM_PACKAGES}" -eq 1 ]]; then
    command -v apt-get >/dev/null 2>&1 || die "apt-get is required on Debian/Ubuntu."
    note "Installing base operating-system dependencies"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends \
        ca-certificates coreutils iproute2 python3 python3-pip python3-venv tar util-linux
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

if [[ -n "${SITE_CONFIG}" ]]; then
    CONFIG_INPUT="${SITE_CONFIG}"
else
    [[ -f "${CONFIG_PATH}" && ! -L "${CONFIG_PATH}" ]] || \
        die "Configuration must be a regular, non-symlink file: ${CONFIG_PATH}"
    CONFIG_INPUT="${CONFIG_PATH}"
fi

# Validate the complete application schema before creating accounts or paths.
# The file is parsed as UTF-8 KEY=VALUE data; it is never sourced/evaluated.
if ! PYTHONPATH="${PROJECT_ROOT}/src" "${PYTHON_BIN}" -c \
    'import sys; from commercialrchproxy.config import Config; Config.load(sys.argv[1], environ={})' \
    "${CONFIG_INPUT}"; then
    die "Configuration schema validation failed: ${CONFIG_INPUT}"
fi
crch_load_config_contract "${CONFIG_INPUT}" || die "Unsafe operating-system configuration contract."
SERVICE_USER="${CRCH_SERVICE_USER}"
SERVICE_GROUP="${CRCH_SERVICE_GROUP}"
OUTPUT_DIR="${CRCH_OUTPUT_DIR}"
LOG_DIR="${CRCH_LOG_DIR}"
readonly SERVICE_USER SERVICE_GROUP OUTPUT_DIR LOG_DIR

if ! getent group "${SERVICE_GROUP}" >/dev/null; then
    groupadd --system "${SERVICE_GROUP}"
fi
if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
    useradd --system --gid "${SERVICE_GROUP}" --home-dir "${OUTPUT_DIR}" \
        --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
fi
[[ "$(id -gn "${SERVICE_USER}")" == "${SERVICE_GROUP}" ]] || \
    die "Existing user ${SERVICE_USER} does not have ${SERVICE_GROUP} as its primary group."

for protected_path in "${CONFIG_DIR}" "${APP_ROOT}" "${OUTPUT_DIR}" "${LOG_DIR}" "${LIBEXEC_DIR}"; do
    [[ ! -L "${protected_path}" ]] || die "Refusing to manage symlinked path: ${protected_path}"
done

install -d -m 0750 -o root -g "${SERVICE_GROUP}" -- "${CONFIG_DIR}"
install -d -m 0755 -o root -g root -- "${APP_ROOT}" "${RELEASES_DIR}"
install -d -m 0750 -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -- "${OUTPUT_DIR}" "${LOG_DIR}"
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

ensure_services_stopped() {
    local service_name active=0
    systemctl stop "${ALL_SERVICES[@]}" >/dev/null 2>&1 || true
    for service_name in "${ALL_SERVICES[@]}"; do
        if systemctl is-active --quiet "${service_name}"; then
            active=1
        fi
    done
    [[ "${active}" -eq 0 ]]
}

ensure_service_not_enabled() {
    local service_name="$1" enabled_state
    systemctl disable "${service_name}" >/dev/null 2>&1 || true
    enabled_state="$(systemctl is-enabled "${service_name}" 2>/dev/null || true)"
    [[ "${enabled_state}" != "enabled" && "${enabled_state}" != "enabled-runtime" ]]
}

restore_enable_state() {
    local service_name="$1" state="${PREVIOUS_ENABLE_STATE[$1]:-not-found}"
    systemctl disable "${service_name}" >/dev/null 2>&1 || true
    case "${state}" in
        enabled) systemctl enable "${service_name}" ;;
        enabled-runtime) systemctl enable --runtime "${service_name}" ;;
        masked) systemctl mask "${service_name}" ;;
        masked-runtime) systemctl mask --runtime "${service_name}" ;;
        *) return 0 ;;
    esac
}

rollback_release() {
    ROLLBACK_FAILED=0
    set +e
    note "Activation failed; restoring the complete previous installed state"
    rollback_step "could not stop newly activated services" ensure_services_stopped

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
        for service_name in "${ALL_SERVICES[@]}"; do
            unit_path="${UNIT_DIR}/${service_name}"
            if [[ -f "${ROLLBACK_DIR}/units/${service_name}" ]]; then
                rollback_step "could not restore previous unit ${service_name}" \
                    cp -a -- "${ROLLBACK_DIR}/units/${service_name}" "${unit_path}"
            else
                rollback_step "could not remove new unit ${service_name}" rm -f -- "${unit_path}"
            fi
        done
        if [[ -f "${ROLLBACK_DIR}/secondary/legacy-dropin" ]]; then
            rollback_step "could not recreate legacy network drop-in directory" \
                install -d -m 0755 -o root -g root -- "$(dirname -- "${LEGACY_SECONDARY_DROPIN}")"
            rollback_step "could not restore legacy network drop-in" \
                cp -a -- "${ROLLBACK_DIR}/secondary/legacy-dropin" "${LEGACY_SECONDARY_DROPIN}"
        else
            rollback_step "could not remove migrated legacy network drop-in" rm -f -- "${LEGACY_SECONDARY_DROPIN}"
        fi
        if [[ -f "${ROLLBACK_DIR}/secondary/dumper-dropin" ]]; then
            rollback_step "could not recreate dumper network drop-in directory" \
                install -d -m 0755 -o root -g root -- "$(dirname -- "${DUMPER_SECONDARY_DROPIN}")"
            rollback_step "could not restore dumper network drop-in" \
                cp -a -- "${ROLLBACK_DIR}/secondary/dumper-dropin" "${DUMPER_SECONDARY_DROPIN}"
        else
            rollback_step "could not remove new dumper network drop-in" rm -f -- "${DUMPER_SECONDARY_DROPIN}"
        fi
        if [[ -f "${ROLLBACK_DIR}/secondary/network-helper" ]]; then
            rollback_step "could not restore secondary-IP helper" \
                cp -a -- "${ROLLBACK_DIR}/secondary/network-helper" "${SECONDARY_HELPER}"
        fi
    else
        printf 'ROLLBACK ERROR: rollback staging directory is unavailable.\n' >&2
        ROLLBACK_FAILED=1
    fi

    rollback_step "systemd daemon-reload failed after file restoration" systemctl daemon-reload
    for service_name in "${ALL_SERVICES[@]}"; do
        rollback_step "could not restore enablement for ${service_name}" restore_enable_state "${service_name}"
    done
    for service_name in "${ALL_SERVICES[@]}"; do
        if [[ "${WAS_ACTIVE[${service_name}]:-0}" -eq 1 ]]; then
            if [[ -f "${ROLLBACK_DIR}/units/${service_name}" ]]; then
                rollback_step "could not restart previously active ${service_name}" systemctl start "${service_name}"
            else
                printf 'ROLLBACK ERROR: %s was active but its unit backup is unavailable.\n' "${service_name}" >&2
                ROLLBACK_FAILED=1
            fi
        fi
    done

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
for executable_name in commercialrchproxy commercialrchproxy-dumper commercialrchproxy-parser; do
    [[ -x "${NEW_RELEASE}/venv/bin/${executable_name}" ]] || \
        die "Installed release is missing entry point ${executable_name}."
    "${NEW_RELEASE}/venv/bin/${executable_name}" --version
done

git_root="$(git -C "${PROJECT_ROOT}" rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -n "${git_root}" && "$(realpath -m -- "${git_root}")" == "${PROJECT_ROOT}" ]]; then
    git -C "${PROJECT_ROOT}" rev-parse HEAD >"${NEW_RELEASE}/SOURCE_REVISION"
fi

# This validates syntax and local IP assignment by binding an ephemeral local
# socket only. It does not connect to the listener or the RCH device.
if ! runuser -u "${SERVICE_USER}" -- \
    "${NEW_RELEASE}/venv/bin/commercialrchproxy-dumper" --config "${CONFIG_PATH}" --check-config --json; then
    die "Configuration validation failed. This installer will not alter networking; assign LISTEN_IP through the host's normal network configuration, correct ${CONFIG_PATH}, and rerun."
fi

if [[ -L "${CURRENT_LINK}" ]]; then
    PREVIOUS_TARGET="$(readlink -- "${CURRENT_LINK}")"
elif [[ -e "${CURRENT_LINK}" ]]; then
    die "Refusing to replace non-symlink path ${CURRENT_LINK}"
fi
for service_name in "${ALL_SERVICES[@]}"; do
    if systemctl is-active --quiet "${service_name}"; then
        WAS_ACTIVE["${service_name}"]=1
    else
        WAS_ACTIVE["${service_name}"]=0
    fi
    enable_state="$(systemctl is-enabled "${service_name}" 2>/dev/null || true)"
    PREVIOUS_ENABLE_STATE["${service_name}"]="${enable_state:-not-found}"
    unit_path="${UNIT_DIR}/${service_name}"
    [[ ! -L "${unit_path}" ]] || die "Refusing to replace symlinked or masked unit ${unit_path}."
done

ROLLBACK_DIR="$(mktemp -d /run/commercialrchproxy-install-rollback.XXXXXX)"
chmod 0700 -- "${ROLLBACK_DIR}"
install -d -m 0700 -- "${ROLLBACK_DIR}/libexec" "${ROLLBACK_DIR}/units" \
    "${ROLLBACK_DIR}/secondary" "${ROLLBACK_DIR}/rendered-units"
for service_name in "${ALL_SERVICES[@]}"; do
    unit_path="${UNIT_DIR}/${service_name}"
    if [[ -f "${unit_path}" ]]; then
        cp -a -- "${unit_path}" "${ROLLBACK_DIR}/units/${service_name}"
    elif [[ -e "${unit_path}" ]]; then
        die "Existing unit path is not a regular file: ${unit_path}"
    fi
done
for secondary_pair in \
    "${DUMPER_SECONDARY_DROPIN}:dumper-dropin" \
    "${LEGACY_SECONDARY_DROPIN}:legacy-dropin"; do
    secondary_path="${secondary_pair%%:*}"
    secondary_backup="${secondary_pair##*:}"
    if [[ -e "${secondary_path}" || -L "${secondary_path}" ]]; then
        [[ -f "${secondary_path}" && ! -L "${secondary_path}" ]] || \
            die "Secondary-IP drop-in must be a regular non-symlink file: ${secondary_path}"
        [[ "$(head -n 1 -- "${secondary_path}")" == "${SECONDARY_MARKER}" ]] || \
            die "Refusing to alter foreign secondary-IP drop-in: ${secondary_path}"
        cp -a -- "${secondary_path}" "${ROLLBACK_DIR}/secondary/${secondary_backup}"
    fi
done
if [[ -e "${SECONDARY_HELPER}" || -L "${SECONDARY_HELPER}" ]]; then
    [[ -f "${SECONDARY_HELPER}" && ! -L "${SECONDARY_HELPER}" ]] || \
        die "Secondary-IP helper must be a regular non-symlink file: ${SECONDARY_HELPER}"
    [[ "$(sed -n '2p' -- "${SECONDARY_HELPER}")" == "${SECONDARY_MARKER}" ]] || \
        die "Refusing to alter foreign secondary-IP helper: ${SECONDARY_HELPER}"
    cp -a -- "${SECONDARY_HELPER}" "${ROLLBACK_DIR}/secondary/network-helper"
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

for service_name in "${ALL_SERVICES[@]}"; do
    render_service_unit "${service_name}" \
        "${ROLLBACK_DIR}/rendered-units/${service_name}"
done

INSTALL_STATE_DIRTY=1
for script_name in "${required_scripts[@]}"; do
    install -m 0755 -o root -g root -- \
        "${PROJECT_ROOT}/scripts/${script_name}.sh" "${LIBEXEC_DIR}/${script_name}.sh"
done
for service_name in "${ALL_SERVICES[@]}"; do
    install -m 0644 -o root -g root -- \
        "${ROLLBACK_DIR}/rendered-units/${service_name}" "${UNIT_DIR}/${service_name}"
done

# A helper installed by older releases bound the address lifetime to the
# legacy coordinator.  Migrate only a marker-owned drop-in to the Dumper; the
# Parser deliberately remains independent of the virtual address.
if [[ -f "${LEGACY_SECONDARY_DROPIN}" ]]; then
    install -d -m 0755 -o root -g root -- "$(dirname -- "${DUMPER_SECONDARY_DROPIN}")"
    install -m 0644 -o root -g root -- "${LEGACY_SECONDARY_DROPIN}" "${DUMPER_SECONDARY_DROPIN}"
    rm -f -- "${LEGACY_SECONDARY_DROPIN}"
    rmdir -- "$(dirname -- "${LEGACY_SECONDARY_DROPIN}")" >/dev/null 2>&1 || true
    if [[ -f "${ROLLBACK_DIR}/secondary/network-helper" ]]; then
        install -m 0755 -o root -g root -- \
            "${PROJECT_ROOT}/scripts/manage_secondary_ip.sh" "${SECONDARY_HELPER}"
    fi
    note "Migrated the managed secondary-IP dependency to ${DUMPER_SERVICE} only."
fi

TEMPORARY_LINK="${APP_ROOT}/.current.$$"
rm -f -- "${TEMPORARY_LINK}"
ln -s -- "${NEW_RELEASE}" "${TEMPORARY_LINK}"
mv -Tf -- "${TEMPORARY_LINK}" "${CURRENT_LINK}"
TEMPORARY_LINK=""
SWITCHED=1
if ! ensure_services_stopped; then
    die "Could not stop the previous service generation before activation."
fi
systemctl daemon-reload
if ! "${LIBEXEC_DIR}/check_config.sh"; then
    die "Deployment configuration, local bind, storage, identity, sandbox, or permission checks failed."
fi
if command -v systemd-analyze >/dev/null 2>&1; then
    unit_paths=()
    for service_name in "${ALL_SERVICES[@]}"; do
        unit_paths+=("${UNIT_DIR}/${service_name}")
    done
    if ! systemd-analyze verify "${unit_paths[@]}"; then
        die "systemd rejected one or more commercialRCHproxy units"
    fi
fi
if ! systemctl disable "${LEGACY_SERVICE}" >/dev/null 2>&1; then
    die "Could not disable the legacy compatibility coordinator"
fi
if ! systemctl enable "${MANAGED_SERVICES[@]}"; then
    die "Could not enable both independent services"
fi

if [[ "${START_SERVICE}" -eq 1 ]]; then
    if ! systemctl start "${MANAGED_SERVICES[@]}"; then
        journalctl -u "${DUMPER_SERVICE}" -u "${PARSER_SERVICE}" -n 30 --no-pager >&2 || true
        die "The dumper/parser services failed to start; automatic rollback will be attempted."
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
        die "Post-start dumper/parser health checks failed; automatic rollback will be attempted."
    fi

    "${LIBEXEC_DIR}/healthcheck.sh"
    note "RCH protocol reachability: NOT PROBED (requires PCAP/manual evidence)."
else
    ensure_services_stopped || die "Could not leave all services stopped as requested."
    note "Installed and enabled ${DUMPER_SERVICE} and ${PARSER_SERVICE} without starting them (--no-start)."
    note "RCH protocol reachability: NOT PROBED (requires PCAP/manual evidence)."
fi

trap - EXIT
INSTALL_STATE_DIRTY=0
SWITCHED=2
if ! remove_rollback_dir; then
    printf 'WARNING: deployment succeeded but rollback staging could not be removed: %s\n' "${ROLLBACK_DIR}" >&2
fi
note "Installed release ${release_id} with independent Dumper and Parser services. Configuration, captured jobs, and logs were preserved."
note "No host network settings were changed."
