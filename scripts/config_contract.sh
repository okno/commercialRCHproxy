#!/usr/bin/env bash

# Trusted operations helper.  Configuration files are parsed as data and are
# never sourced or evaluated by a shell.

readonly CRCH_DEFAULT_SERVICE_USER="commercialrchproxy"
readonly CRCH_DEFAULT_SERVICE_GROUP="commercialrchproxy"
readonly CRCH_DEFAULT_OUTPUT_DIR="/var/lib/commercialrchproxy/jobs"
readonly CRCH_DEFAULT_LOG_DIR="/var/log/commercialrchproxy"

crch_contract_error() {
    printf 'ERROR: %s\n' "$*" >&2
    return 1
}

crch_config_value() {
    local config_path="$1"
    local wanted="$2"
    local fallback="$3"

    awk -v wanted="${wanted}" -v fallback="${fallback}" '
        function trim(value) {
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
            return value
        }
        /^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
        {
            separator = index($0, "=")
            if (!separator) {
                printf "%s:%d: expected KEY=VALUE\n", FILENAME, FNR > "/dev/stderr"
                invalid = 1
                next
            }
            key = trim(substr($0, 1, separator - 1))
            value = trim(substr($0, separator + 1))
            if (key !~ /^[A-Z0-9][A-Z0-9_]*$/) {
                printf "%s:%d: invalid configuration key\n", FILENAME, FNR > "/dev/stderr"
                invalid = 1
                next
            }
            if (seen[key]++) {
                printf "%s:%d: duplicate configuration key %s\n", FILENAME, FNR, key > "/dev/stderr"
                invalid = 1
                next
            }
            if ((substr(value, 1, 1) == "\"" && substr(value, length(value), 1) == "\"") ||
                (substr(value, 1, 1) == "\047" && substr(value, length(value), 1) == "\047")) {
                value = substr(value, 2, length(value) - 2)
            }
            if (key == wanted) {
                result = value
                found = 1
            }
        }
        END {
            if (invalid) exit 2
            print found ? result : fallback
        }
    ' "${config_path}"
}

crch_validate_identity() {
    local name="$1"
    local value="$2"
    if [[ ! "${value}" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; then
        crch_contract_error "${name} must be a conservative Unix account name."
        return 1
    fi
    if [[ "${value}" == "root" ]]; then
        crch_contract_error "${name} must not be root."
        return 1
    fi
}

crch_validate_managed_path() {
    local name="$1"
    local value="$2"
    local normalized

    [[ "${value}" == /* && "${value}" != "/" && "$(dirname -- "${value}")" != "/" ]] || {
        crch_contract_error "${name} must be an absolute dedicated path below a top-level directory."
        return 1
    }
    if printf '%s' "${value}" | LC_ALL=C grep -q '[[:cntrl:]]'; then
        crch_contract_error "${name} must not contain control characters."
        return 1
    fi
    if [[ ! "${value}" =~ ^/[A-Za-z0-9._/+:-]+$ ]]; then
        crch_contract_error "${name} must use conservative path characters (letters, digits, . _ / + : -)."
        return 1
    fi
    normalized="$(realpath -m -- "${value}")" || return 1
    if [[ "${normalized}" != "${value}" ]]; then
        crch_contract_error "${name} must be normalized (use ${normalized})."
        return 1
    fi

    # Protect operating-system, application and ephemeral trees from an
    # installer chown or an explicitly requested uninstall purge.
    case "${value}" in
        /bin|/bin/*|/boot|/boot/*|/dev|/dev/*|/etc|/etc/*|/home|/home/*|\
        /lib|/lib/*|/lib64|/lib64/*|/opt|/opt/*|/proc|/proc/*|/root|/root/*|\
        /run|/run/*|/sbin|/sbin/*|/sys|/sys/*|/tmp|/tmp/*|/usr|/usr/*|\
        /var|/var/backups|/var/backups/*|/var/cache|/var/cache/*|/var/lib|\
        /var/log|/var/spool|/var/spool/*|/var/tmp|/var/tmp/*)
            crch_contract_error "${name} is inside a protected or ephemeral tree: ${value}"
            return 1
            ;;
    esac
    if [[ -e "${value}" && ! -d "${value}" ]]; then
        crch_contract_error "${name} exists but is not a directory: ${value}"
        return 1
    fi
}

crch_validate_managed_ancestry() {
    local name="$1"
    local value="$2"
    local service_user="$3"
    local service_uid=""
    local ancestor owner mode

    if id -u "${service_user}" >/dev/null 2>&1; then
        service_uid="$(id -u "${service_user}")"
    fi
    if [[ -e "${value}" || -L "${value}" ]]; then
        [[ -d "${value}" && ! -L "${value}" ]] || {
            crch_contract_error "${name} must not be a symlink: ${value}"
            return 1
        }
        owner="$(stat -c '%u' -- "${value}")" || return 1
        if [[ "${owner}" != "0" && ( -z "${service_uid}" || "${owner}" != "${service_uid}" ) ]]; then
            crch_contract_error "${name} is not owned by root or SERVICE_USER: ${value}"
            return 1
        fi
    fi
    ancestor="$(dirname -- "${value}")"
    while :; do
        if [[ -e "${ancestor}" || -L "${ancestor}" ]]; then
            [[ -d "${ancestor}" && ! -L "${ancestor}" ]] || {
                crch_contract_error "${name} has a non-directory or symlink ancestor: ${ancestor}"
                return 1
            }
            owner="$(stat -c '%u' -- "${ancestor}")" || return 1
            if [[ "${owner}" != "0" && ( -z "${service_uid}" || "${owner}" != "${service_uid}" ) ]]; then
                crch_contract_error "${name} ancestor is not owned by root or SERVICE_USER: ${ancestor}"
                return 1
            fi
            mode="$(stat -c '%a' -- "${ancestor}")" || return 1
            if (( (8#${mode} & 8#022) != 0 )); then
                crch_contract_error "${name} ancestor is group/world writable: ${ancestor}"
                return 1
            fi
        fi
        [[ "${ancestor}" == "/" ]] && break
        ancestor="$(dirname -- "${ancestor}")"
    done
}

crch_load_config_contract() {
    local config_path="$1"
    local value

    [[ -f "${config_path}" && ! -L "${config_path}" && -r "${config_path}" ]] || {
        crch_contract_error "Configuration must be a readable regular non-symlink file: ${config_path}"
        return 1
    }

    value="$(crch_config_value "${config_path}" SERVICE_USER "${CRCH_DEFAULT_SERVICE_USER}")" || return 1
    CRCH_SERVICE_USER="${value}"
    value="$(crch_config_value "${config_path}" SERVICE_GROUP "${CRCH_DEFAULT_SERVICE_GROUP}")" || return 1
    CRCH_SERVICE_GROUP="${value}"
    value="$(crch_config_value "${config_path}" OUTPUT_DIR "${CRCH_DEFAULT_OUTPUT_DIR}")" || return 1
    CRCH_OUTPUT_DIR="${value}"
    value="$(crch_config_value "${config_path}" LOG_DIR "${CRCH_DEFAULT_LOG_DIR}")" || return 1
    CRCH_LOG_DIR="${value}"

    crch_validate_identity SERVICE_USER "${CRCH_SERVICE_USER}" || return 1
    crch_validate_identity SERVICE_GROUP "${CRCH_SERVICE_GROUP}" || return 1
    crch_validate_managed_path OUTPUT_DIR "${CRCH_OUTPUT_DIR}" || return 1
    crch_validate_managed_path LOG_DIR "${CRCH_LOG_DIR}" || return 1
    crch_validate_managed_ancestry OUTPUT_DIR "${CRCH_OUTPUT_DIR}" "${CRCH_SERVICE_USER}" || return 1
    crch_validate_managed_ancestry LOG_DIR "${CRCH_LOG_DIR}" "${CRCH_SERVICE_USER}" || return 1

    case "${CRCH_OUTPUT_DIR}/" in
        "${CRCH_LOG_DIR}/"*)
            crch_contract_error "OUTPUT_DIR and LOG_DIR must be separate, non-nested trees."
            return 1
            ;;
    esac
    case "${CRCH_LOG_DIR}/" in
        "${CRCH_OUTPUT_DIR}/"*)
            crch_contract_error "OUTPUT_DIR and LOG_DIR must be separate, non-nested trees."
            return 1
            ;;
    esac
}

crch_systemd_quote() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//%/%%}"
    printf '"%s"' "${value}"
}

crch_render_service_unit() {
    local source_path="$1"
    local destination="$2"
    local service_user="$3"
    local service_group="$4"
    local output_dir="$5"
    local log_dir="$6"
    local render_paths="$7"
    local quoted_output quoted_log line
    local user_count=0 group_count=0 working_count=0 write_count=0

    [[ -f "${source_path}" && ! -L "${source_path}" ]] || {
        crch_contract_error "Unit template must be a regular non-symlink file: ${source_path}"
        return 1
    }
    [[ "${render_paths}" == "true" || "${render_paths}" == "false" ]] || {
        crch_contract_error "Internal unit-render mode must be true or false."
        return 1
    }
    crch_validate_identity SERVICE_USER "${service_user}" || return 1
    crch_validate_identity SERVICE_GROUP "${service_group}" || return 1
    crch_validate_managed_path OUTPUT_DIR "${output_dir}" || return 1
    crch_validate_managed_path LOG_DIR "${log_dir}" || return 1

    quoted_output="$(crch_systemd_quote "${output_dir}")"
    quoted_log="$(crch_systemd_quote "${log_dir}")"
    {
        printf '# Rendered by commercialRCHproxy install.sh; do not edit in place.\n'
        while IFS= read -r line || [[ -n "${line}" ]]; do
            case "${line}" in
                User=*)
                    printf 'User=%s\n' "${service_user}"
                    user_count=$((user_count + 1))
                    ;;
                Group=*)
                    printf 'Group=%s\n' "${service_group}"
                    group_count=$((group_count + 1))
                    ;;
                WorkingDirectory=*)
                    if [[ "${render_paths}" == "true" ]]; then
                        printf 'WorkingDirectory=%s\n' "${quoted_output}"
                        working_count=$((working_count + 1))
                    else
                        printf '%s\n' "${line}"
                    fi
                    ;;
                ReadWritePaths=*)
                    if [[ "${render_paths}" == "true" ]]; then
                        printf 'ReadWritePaths=%s %s\n' "${quoted_output}" "${quoted_log}"
                        write_count=$((write_count + 1))
                    else
                        printf '%s\n' "${line}"
                    fi
                    ;;
                *) printf '%s\n' "${line}" ;;
            esac
        done <"${source_path}"
    } >"${destination}"

    if [[ "${user_count}" -ne 1 || "${group_count}" -ne 1 ]]; then
        crch_contract_error "Unit template must contain exactly one User and Group directive: ${source_path}"
        return 1
    fi
    if [[ "${render_paths}" == "true" && \
          ( "${working_count}" -ne 1 || "${write_count}" -ne 1 ) ]]; then
        crch_contract_error "Real-service unit template must contain exactly one WorkingDirectory and ReadWritePaths directive: ${source_path}"
        return 1
    fi
    chmod 0644 -- "${destination}"
}
