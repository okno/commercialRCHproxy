#!/usr/bin/env bash
# Managed by commercialRCHproxy manage_secondary_ip.sh
set -Eeuo pipefail
IFS=$'\n\t'
export LC_ALL=C
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset PYTHONHOME PYTHONPATH
export PYTHONNOUSERSITE=1
export PYTHONSAFEPATH=1
umask 0077

readonly APP_SERVICE="commercialrchproxy.service"
readonly ADDRESS_SERVICE="commercialrchproxy-secondary-ip.service"
readonly DEFAULT_CONFIG_PATH="/etc/commercialrchproxy/commercialrchproxy.conf"
readonly CONFIG_DIR="/etc/commercialrchproxy"
readonly MANAGED_CONFIG_PATH="/etc/commercialrchproxy/secondary-ip.conf"
readonly UNIT_PATH="/etc/systemd/system/${ADDRESS_SERVICE}"
readonly DROPIN_DIR="/etc/systemd/system/${APP_SERVICE}.d"
readonly DROPIN_PATH="${DROPIN_DIR}/10-secondary-ip.conf"
readonly HELPER_DIR="/usr/local/libexec/commercialrchproxy-network"
readonly HELPER_PATH="${HELPER_DIR}/manage_secondary_ip.sh"
readonly RUNTIME_DIR="/run/commercialrchproxy-secondary-ip"
readonly STATE_PATH="${RUNTIME_DIR}/state"
readonly MANAGER_LOCK="/run/commercialrchproxy-mutation.lock"
readonly RUNTIME_LOCK="${RUNTIME_DIR}/operation.lock"
readonly MARKER="# Managed by commercialRCHproxy manage_secondary_ip.sh"

CONFIG_PATH="${DEFAULT_CONFIG_PATH}"
INTERFACE_OVERRIDE=""
PREFIX_OVERRIDE=""
ASSUME_YES=0

ACTION="${1:-}"
if [[ -n "${ACTION}" ]]; then
    shift
fi

usage() {
    cat <<'EOF'
Usage:
  sudo ./scripts/manage_secondary_ip.sh install [OPTIONS]
  sudo ./scripts/manage_secondary_ip.sh check   [OPTIONS]
  sudo ./scripts/manage_secondary_ip.sh uninstall [--yes]

Explicitly installs, checks, or removes a persistent secondary IPv4 address
for commercialRCHproxy. This is a second address on the existing LAN interface,
not a dummy interface and not a protocol/device probe.

Options for install/check:
  --config PATH          Private site configuration (default: /etc/commercialrchproxy/commercialrchproxy.conf)
  --interface IFACE      Require this interface; otherwise derive it from the local route to PRINTER_IP
  --prefix-length N      Select a prefix already present on the interface; never inferred from IP spelling
  --yes                  Skip the interactive install/uninstall confirmation
  -h, --help             Show this help

The script never changes routes, firewall, DNS, interface state, or the RCH
device. It adds only LISTEN_IP/PREFIX with noprefixroute. Duplicate-address
detection requires Debian's iputils-arping package.

Internal commands `up` and `down` are reserved for the managed systemd unit.
The service uses a root-only snapshot of the two endpoint addresses; it never
sources the application configuration as shell code.
EOF
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

note() {
    printf '[commercialRCHproxy network] %s\n' "$*"
}

path_exists() {
    [[ -e "$1" || -L "$1" ]]
}

case "${ACTION}" in
    install|check)
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --config)
                    [[ $# -ge 2 ]] || die "--config requires a path"
                    CONFIG_PATH="$2"
                    shift 2
                    ;;
                --config=*) CONFIG_PATH="${1#*=}"; shift ;;
                --interface)
                    [[ $# -ge 2 ]] || die "--interface requires a name"
                    INTERFACE_OVERRIDE="$2"
                    shift 2
                    ;;
                --interface=*) INTERFACE_OVERRIDE="${1#*=}"; shift ;;
                --prefix-length)
                    [[ $# -ge 2 ]] || die "--prefix-length requires a number"
                    PREFIX_OVERRIDE="$2"
                    shift 2
                    ;;
                --prefix-length=*) PREFIX_OVERRIDE="${1#*=}"; shift ;;
                --yes) ASSUME_YES=1; shift ;;
                -h|--help) usage; exit 0 ;;
                *) die "Unknown option: $1" ;;
            esac
        done
        ;;
    uninstall)
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --yes) ASSUME_YES=1; shift ;;
                -h|--help) usage; exit 0 ;;
                *) die "Unknown uninstall option: $1" ;;
            esac
        done
        ;;
    up|down)
        [[ $# -eq 0 ]] || die "Internal command ${ACTION} accepts no options"
        ;;
    -h|--help|help) usage; exit 0 ;;
    "") usage >&2; exit 2 ;;
    *) die "Unknown action: ${ACTION}" ;;
esac

PYTHON_BIN="$(command -v python3 || true)"
IP_BIN="$(command -v ip || true)"
SYSTEMCTL_BIN="$(command -v systemctl || true)"
FLock_BIN="$(command -v flock || true)"
[[ -n "${PYTHON_BIN}" ]] || die "python3 is required"
[[ -n "${IP_BIN}" ]] || die "ip is required (Debian package: iproute2)"

require_root() {
    [[ "${EUID}" -eq 0 ]] || die "Run ${ACTION} as root (for example, with sudo)."
}

secure_lock() {
    local lock_path="$1"
    local fd="$2"
    local previous_umask
    if path_exists "${lock_path}"; then
        [[ -f "${lock_path}" && ! -L "${lock_path}" && "$(stat -c '%u' -- "${lock_path}")" == "0" ]] || \
            die "Lock must be a root-owned regular non-symlink file: ${lock_path}"
    fi
    previous_umask="$(umask)"
    umask 0077
    if [[ "${fd}" == "9" ]]; then
        exec 9>"${lock_path}"
        chmod 0600 -- "${lock_path}"
        flock -n 9 || die "Another commercialRCHproxy lifecycle operation is running."
    else
        exec 8>"${lock_path}"
        chmod 0600 -- "${lock_path}"
        flock -n 8 || die "Another secondary-IP operation is running."
    fi
    umask "${previous_umask}"
}

validate_privileged_file() {
    local path="$1"
    local mode
    [[ -f "${path}" && ! -L "${path}" ]] || die "Expected a regular non-symlink file: ${path}"
    [[ "$(stat -c '%u' -- "${path}")" == "0" ]] || die "File must be owned by root: ${path}"
    mode="$(stat -c '%a' -- "${path}")"
    (( (8#${mode} & 8#022) == 0 )) || die "File must not be group/world writable: ${path}"
}

ensure_privileged_directory() {
    local path="$1"
    local create_mode="$2"
    local mode
    if path_exists "${path}"; then
        [[ -d "${path}" && ! -L "${path}" ]] || die "Expected a regular directory: ${path}"
        [[ "$(stat -c '%u' -- "${path}")" == "0" ]] || die "Directory must be owned by root: ${path}"
        mode="$(stat -c '%a' -- "${path}")"
        (( (8#${mode} & 8#022) == 0 )) || die "Directory must not be group/world writable: ${path}"
    else
        install -d -m "${create_mode}" -o root -g root -- "${path}"
    fi
}

load_site_config() {
    local parsed
    [[ -f "${CONFIG_PATH}" && ! -L "${CONFIG_PATH}" ]] || \
        die "Configuration must be a readable regular non-symlink file: ${CONFIG_PATH}"
    parsed="$("${PYTHON_BIN}" - "${CONFIG_PATH}" <<'PY'
from ipaddress import IPv4Address
from pathlib import Path
import sys

path = Path(sys.argv[1])
values: dict[str, list[str]] = {"LISTEN_IP": [], "PRINTER_IP": []}
for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if "=" not in line:
        raise SystemExit(f"{path}:{number}: expected KEY=VALUE")
    key, value = (part.strip() for part in line.split("=", 1))
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    if key in values:
        values[key].append(value)
for key, found in values.items():
    if len(found) != 1:
        raise SystemExit(f"{path}: expected exactly one {key}, found {len(found)}")
listen = IPv4Address(values["LISTEN_IP"][0])
printer = IPv4Address(values["PRINTER_IP"][0])
if listen == printer:
    raise SystemExit("LISTEN_IP and PRINTER_IP must differ")
if any(address.is_unspecified or address.is_loopback or address.is_multicast for address in (listen, printer)):
    raise SystemExit("LISTEN_IP and PRINTER_IP must be usable unicast IPv4 addresses")
print(f"{listen}\t{printer}")
PY
    )" || die "Cannot parse LISTEN_IP/PRINTER_IP from ${CONFIG_PATH}"
    IFS=$'\t' read -r LISTEN_IP PRINTER_IP <<<"${parsed}"
    [[ -n "${LISTEN_IP}" && -n "${PRINTER_IP}" ]] || die "Configuration parsing returned empty endpoints"
}

reject_documentation_addresses() {
    local address
    for address in "$@"; do
        case "${address}" in
            192.0.2.*|198.51.100.*|203.0.113.*)
                die "Configuration contains an RFC 5737 documentation address; replace it with an approved private site address."
                ;;
        esac
    done
}

build_plan() {
    local route_json address_json parsed
    route_json="$("${IP_BIN}" -4 -j route get "${PRINTER_IP}")" || \
        die "No IPv4 route to configured PRINTER_IP; no change was made."
    address_json="$("${IP_BIN}" -4 -j address show)" || die "Cannot inspect local IPv4 addresses"
    parsed="$("${PYTHON_BIN}" - \
        "${LISTEN_IP}" "${PRINTER_IP}" "${INTERFACE_OVERRIDE}" "${PREFIX_OVERRIDE}" \
        "${route_json}" "${address_json}" <<'PY'
from ipaddress import IPv4Address, IPv4Interface, IPv4Network
import json
import re
import sys

listen = IPv4Address(sys.argv[1])
printer = IPv4Address(sys.argv[2])
interface_override = sys.argv[3]
prefix_override = sys.argv[4]
routes = json.loads(sys.argv[5])
addresses = json.loads(sys.argv[6])

if len(routes) != 1 or not isinstance(routes[0], dict):
    raise SystemExit("route lookup is missing or ambiguous")
route = routes[0]
if route.get("gateway") or route.get("via") or route.get("nexthops"):
    raise SystemExit("route to PRINTER_IP uses a gateway/multipath; refusing to infer an on-link address")
interface = route.get("dev")
if not isinstance(interface, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,15}", interface):
    raise SystemExit("route returned an unsafe or missing interface name")
if interface == "lo":
    raise SystemExit("route to PRINTER_IP resolves to loopback")
if interface_override and interface_override != interface:
    raise SystemExit(f"--interface {interface_override} disagrees with route interface {interface}")

selected = [entry for entry in addresses if entry.get("ifname") == interface]
if len(selected) != 1:
    raise SystemExit(f"interface {interface} is missing or ambiguous")
entry = selected[0]
flags = set(entry.get("flags") or [])
if "UP" not in flags:
    raise SystemExit(f"interface {interface} is not administratively UP")
if "LOWER_UP" not in flags:
    raise SystemExit(f"interface {interface} has no active lower-layer carrier")
if "NOARP" in flags:
    raise SystemExit(f"interface {interface} does not support ARP duplicate-address detection")
ifindex = entry.get("ifindex")
if not isinstance(ifindex, int) or ifindex <= 0:
    raise SystemExit("interface has no valid ifindex")

local_ips: list[tuple[str, int, str, str]] = []
candidates: set[tuple[str, int]] = set()
for device in addresses:
    for info in device.get("addr_info") or []:
        if info.get("family") != "inet":
            continue
        local = info.get("local")
        prefix = info.get("prefixlen")
        if not isinstance(local, str) or not isinstance(prefix, int):
            continue
        local_ips.append(
            (local, prefix, str(device.get("ifname", "")), str(info.get("scope", "")))
        )
        if device.get("ifname") == interface and info.get("scope") == "global":
            network = IPv4Interface(f"{local}/{prefix}").network
            if listen in network and printer in network:
                candidates.add((network.with_prefixlen, prefix))

if any(local == str(printer) for local, _, _, _ in local_ips):
    raise SystemExit("PRINTER_IP is assigned locally; refusing an unsafe topology")
assignments = [
    (prefix, device, scope)
    for local, prefix, device, scope in local_ips
    if local == str(listen)
]

if not candidates:
    raise SystemExit(
        "no existing global interface network contains both LISTEN_IP and PRINTER_IP; "
        "configure the LAN correctly before adding a secondary address"
    )
if prefix_override:
    if not prefix_override.isdecimal() or not 1 <= int(prefix_override) <= 30:
        raise SystemExit("--prefix-length must be an integer from 1 through 30")
    prefix = int(prefix_override)
    if prefix not in {candidate_prefix for _, candidate_prefix in candidates}:
        raise SystemExit("requested prefix is not an existing matching network on the selected interface")
else:
    prefix = max(candidate_prefix for _, candidate_prefix in candidates)
    most_specific = {network for network, candidate_prefix in candidates if candidate_prefix == prefix}
    if len(most_specific) != 1:
        raise SystemExit("multiple equally specific matching networks exist; use --prefix-length")

if not 1 <= prefix <= 30:
    raise SystemExit("selected existing prefix must be from /1 through /30 for this LAN address")
network = IPv4Network((listen, prefix), strict=False)
if printer not in network:
    raise SystemExit("selected prefix does not place LISTEN_IP and PRINTER_IP in the same network")
if listen in {network.network_address, network.broadcast_address} or printer in {
    network.network_address,
    network.broadcast_address,
}:
    raise SystemExit("LISTEN_IP/PRINTER_IP cannot be the selected network or broadcast address")

exact = assignments == [(prefix, interface, "global")]
if assignments and not exact:
    rendered = ", ".join(
        f"{device}/{candidate_prefix} scope={scope}"
        for candidate_prefix, device, scope in assignments
    )
    raise SystemExit(f"LISTEN_IP is already assigned with a conflicting interface/prefix: {rendered}")
print(f"{interface}\t{prefix}\t{ifindex}\t{1 if exact else 0}")
PY
    )" || die "Cannot derive a unique safe secondary-address plan; no change was made."
    IFS=$'\t' read -r INTERFACE PREFIX_LENGTH IFINDEX ADDRESS_PRESENT <<<"${parsed}"
    [[ "${INTERFACE}" =~ ^[A-Za-z0-9_.:-]{1,15}$ ]] || die "Unsafe derived interface"
    [[ "${PREFIX_LENGTH}" =~ ^[0-9]+$ ]] || die "Unsafe derived prefix"
    [[ "${IFINDEX}" =~ ^[1-9][0-9]*$ ]] || die "Unsafe derived ifindex"
    [[ "${ADDRESS_PRESENT}" == "0" || "${ADDRESS_PRESENT}" == "1" ]] || die "Unsafe address state"
    CIDR="${LISTEN_IP}/${PREFIX_LENGTH}"
}

require_iputils_arping() {
    ARPING_BIN="$(command -v arping || true)"
    [[ -n "${ARPING_BIN}" ]] || \
        die "Duplicate-address detection requires: apt-get install iputils-arping"
    "${ARPING_BIN}" -V 2>&1 | grep -qi 'iputils' || \
        die "Unsupported arping implementation. Install Debian package iputils-arping."
}

dad_check() {
    [[ "${ADDRESS_PRESENT}" == "0" ]] || return 0
    require_iputils_arping
    note "Checking that ${LISTEN_IP} is unused on ${INTERFACE} (ARP DAD only; no port-23 connection)"
    "${ARPING_BIN}" -D -q -c 3 -w 5 -I "${INTERFACE}" "${LISTEN_IP}" || \
        die "Duplicate-address detection failed or another host answered for ${LISTEN_IP}."
}

confirm_action() {
    local verb="$1"
    local answer
    [[ "${ASSUME_YES}" -eq 0 ]] || return 0
    [[ -t 0 ]] || die "Non-interactive ${verb} requires --yes"
    printf '%s secondary address %s on %s (existing connected prefix /%s).\n' \
        "${verb}" "${CIDR}" "${INTERFACE}" "${PREFIX_LENGTH}" >&2
    printf 'Type exactly "%s" to continue: ' "${verb}" >&2
    IFS= read -r answer
    [[ "${answer}" == "${verb}" ]] || die "Confirmation did not match; nothing was changed."
}

managed_file() {
    local path="$1"
    local mode
    [[ -f "${path}" && ! -L "${path}" ]] || return 1
    [[ "$(stat -c '%u' -- "${path}")" == "0" ]] || return 1
    mode="$(stat -c '%a' -- "${path}")"
    (( (8#${mode} & 8#022) == 0 )) || return 1
    [[ "$(head -n 1 -- "${path}")" == "${MARKER}" ]]
}

managed_script() {
    local path="$1"
    local mode
    [[ -f "${path}" && ! -L "${path}" ]] || return 1
    [[ -x "${path}" && "$(stat -c '%u' -- "${path}")" == "0" ]] || return 1
    mode="$(stat -c '%a' -- "${path}")"
    (( (8#${mode} & 8#022) == 0 )) || return 1
    [[ "$(sed -n '2p' -- "${path}")" == "${MARKER}" ]]
}

write_state() {
    local ownership="$1"
    local temporary
    install -d -m 0700 -o root -g root -- "${RUNTIME_DIR}"
    temporary="$(mktemp "${RUNTIME_DIR}/.state.XXXXXX")"
    {
        printf '%s\n' "${MARKER}"
        printf 'INTERFACE=%s\n' "${INTERFACE}"
        printf 'IFINDEX=%s\n' "${IFINDEX}"
        printf 'ADDRESS=%s\n' "${LISTEN_IP}"
        printf 'PREFIX_LENGTH=%s\n' "${PREFIX_LENGTH}"
        printf 'OWNED=%s\n' "${ownership}"
    } >"${temporary}"
    chmod 0600 -- "${temporary}"
    mv -Tf -- "${temporary}" "${STATE_PATH}"
}

load_key_file() {
    local path="$1"
    local expected_keys="$2"
    "${PYTHON_BIN}" - "${path}" "${MARKER}" "${expected_keys}" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
marker = sys.argv[2]
expected = sys.argv[3].split(",")
if not path.is_file() or path.is_symlink():
    raise SystemExit(f"unsafe managed file: {path}")
lines = path.read_text(encoding="utf-8").splitlines()
if not lines or lines[0] != marker:
    raise SystemExit(f"managed marker missing: {path}")
values: dict[str, str] = {}
for number, line in enumerate(lines[1:], 2):
    if not line:
        continue
    if "=" not in line:
        raise SystemExit(f"{path}:{number}: expected KEY=VALUE")
    key, value = line.split("=", 1)
    if key not in expected or key in values or not value:
        raise SystemExit(f"{path}:{number}: unexpected/duplicate/empty key {key}")
    values[key] = value
if set(values) != set(expected):
    raise SystemExit(f"{path}: missing managed keys")
print("\t".join(values[key] for key in expected))
PY
}

load_managed_config() {
    local parsed
    validate_privileged_file "${MANAGED_CONFIG_PATH}"
    parsed="$(load_key_file "${MANAGED_CONFIG_PATH}" \
        'LISTEN_IP,PRINTER_IP,INTERFACE,PREFIX_LENGTH')" || \
        die "Cannot parse ${MANAGED_CONFIG_PATH}"
    IFS=$'\t' read -r MANAGED_LISTEN_IP MANAGED_PRINTER_IP MANAGED_INTERFACE \
        MANAGED_PREFIX <<<"${parsed}"
    [[ "${MANAGED_INTERFACE}" =~ ^[A-Za-z0-9_.:-]{1,15}$ ]] || die "Unsafe managed interface"
    if [[ ! "${MANAGED_PREFIX}" =~ ^[0-9]+$ ]] || \
       (( MANAGED_PREFIX < 1 || MANAGED_PREFIX > 30 )); then
        die "Unsafe managed prefix"
    fi
    "${PYTHON_BIN}" - "${MANAGED_LISTEN_IP}" "${MANAGED_PRINTER_IP}" <<'PY' || \
        die "Unsafe managed endpoint values"
from ipaddress import IPv4Address
import sys

listen, printer = (IPv4Address(value) for value in sys.argv[1:])
if listen == printer:
    raise SystemExit("managed endpoints must differ")
if any(address.is_unspecified or address.is_loopback or address.is_multicast for address in (listen, printer)):
    raise SystemExit("managed endpoints must be usable unicast IPv4 addresses")
PY
    reject_documentation_addresses "${MANAGED_LISTEN_IP}" "${MANAGED_PRINTER_IP}"
}

load_state() {
    local parsed
    path_exists "${STATE_PATH}" || return 1
    validate_privileged_file "${STATE_PATH}"
    parsed="$(load_key_file "${STATE_PATH}" \
        'INTERFACE,IFINDEX,ADDRESS,PREFIX_LENGTH,OWNED')" || die "Cannot parse runtime ownership state"
    IFS=$'\t' read -r STATE_INTERFACE STATE_IFINDEX STATE_ADDRESS STATE_PREFIX STATE_OWNED <<<"${parsed}"
    [[ "${STATE_INTERFACE}" =~ ^[A-Za-z0-9_.:-]{1,15}$ ]] || die "Unsafe state interface"
    [[ "${STATE_IFINDEX}" =~ ^[1-9][0-9]*$ ]] || die "Unsafe state ifindex"
    [[ "${STATE_PREFIX}" =~ ^[0-9]+$ ]] || die "Unsafe state prefix"
    [[ "${STATE_OWNED}" == "0" || "${STATE_OWNED}" == "1" || "${STATE_OWNED}" == "pending" ]] || \
        die "Unsafe ownership state"
}

state_matches_plan() {
    [[ "${STATE_INTERFACE}" == "${INTERFACE}" && \
       "${STATE_IFINDEX}" == "${IFINDEX}" && \
       "${STATE_ADDRESS}" == "${LISTEN_IP}" && \
       "${STATE_PREFIX}" == "${PREFIX_LENGTH}" ]]
}

address_status() {
    local address="$1" interface="$2" prefix="$3" address_json
    address_json="$("${IP_BIN}" -4 -j address show)" || return 2
    "${PYTHON_BIN}" - "${address}" "${interface}" "${prefix}" "${address_json}" <<'PY'
import json
import sys

address, interface, prefix, raw = sys.argv[1:]
matches = []
for device in json.loads(raw):
    for info in device.get("addr_info") or []:
        if info.get("family") == "inet" and info.get("local") == address:
            matches.append(
                (
                    str(device.get("ifname", "")),
                    str(info.get("prefixlen", "")),
                    str(info.get("scope", "")),
                )
            )
if not matches:
    print("absent")
elif matches == [(interface, prefix, "global")]:
    print("exact")
else:
    print("conflict")
PY
}

internal_up() {
    local added_by_this_run=0 status
    require_root
    ensure_privileged_directory "${RUNTIME_DIR}" 0700
    secure_lock "${RUNTIME_LOCK}" 8
    load_managed_config
    LISTEN_IP="${MANAGED_LISTEN_IP}"
    PRINTER_IP="${MANAGED_PRINTER_IP}"
    INTERFACE_OVERRIDE="${MANAGED_INTERFACE}"
    PREFIX_OVERRIDE="${MANAGED_PREFIX}"
    build_plan
    [[ "${INTERFACE}" == "${MANAGED_INTERFACE}" ]] || \
        die "Managed interface changed; refusing to add the address."
    require_iputils_arping
    if [[ "${ADDRESS_PRESENT}" == "1" ]]; then
        if load_state; then
            state_matches_plan || \
                die "Runtime ownership state does not match the managed address plan; refusing to overwrite it."
            case "${STATE_OWNED}" in
                1) note "${CIDR} is still present and remains helper-owned." ;;
                0) note "${CIDR} is still present and remains borrowed/pre-existing." ;;
                *) die "Runtime ownership is pending/uncertain; refusing to relabel the present address." ;;
            esac
        else
            write_state 0
            note "${CIDR} already exists on ${INTERFACE}; recorded as borrowed and will not be removed."
        fi
        return 0
    fi
    if load_state; then
        state_matches_plan || \
            die "Stale runtime ownership state does not match the managed address plan."
        rm -f -- "${STATE_PATH}"
        note "Cleared matching stale ownership state for an address that is currently absent."
    fi
    dad_check
    write_state pending
    rollback_up() {
        local rc=$? rollback_status rollback_delete_status
        trap - EXIT INT TERM HUP
        set +e
        if [[ "${rc}" -ne 0 && "${added_by_this_run}" -eq 1 ]]; then
            rollback_status="$(address_status "${LISTEN_IP}" "${INTERFACE}" "${PREFIX_LENGTH}")"
            if [[ "${rollback_status}" == "exact" ]]; then
                "${IP_BIN}" address del "${CIDR}" dev "${INTERFACE}" >/dev/null 2>&1
                rollback_delete_status=$?
                if [[ "${rollback_delete_status}" -eq 0 && \
                      "$(address_status "${LISTEN_IP}" "${INTERFACE}" "${PREFIX_LENGTH}")" == "absent" ]]; then
                    rm -f -- "${STATE_PATH}"
                else
                    printf 'ERROR: rollback could not prove removal of %s; preserving pending state at %s.\n' \
                        "${CIDR}" "${STATE_PATH}" >&2
                fi
            elif [[ "${rollback_status}" == "absent" ]]; then
                rm -f -- "${STATE_PATH}"
            else
                printf 'ERROR: rollback found an uncertain address state; preserving %s for manual review.\n' \
                    "${STATE_PATH}" >&2
            fi
        elif [[ "${rc}" -ne 0 ]]; then
            printf 'ERROR: address addition did not report success; preserving pending state to avoid deleting a concurrent assignment.\n' >&2
        fi
        exit "${rc}"
    }
    trap rollback_up EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    trap 'exit 129' HUP
    "${IP_BIN}" address add "${CIDR}" dev "${INTERFACE}" noprefixroute
    added_by_this_run=1
    status="$(address_status "${LISTEN_IP}" "${INTERFACE}" "${PREFIX_LENGTH}")" || \
        die "Cannot verify the newly added address"
    [[ "${status}" == "exact" ]] || die "New address verification returned ${status}"
    write_state 1
    if ! "${ARPING_BIN}" -U -q -c 2 -I "${INTERFACE}" "${LISTEN_IP}"; then
        printf 'WARNING: gratuitous ARP announcement failed; address remains installed.\n' >&2
    fi
    trap - EXIT INT TERM HUP
    note "Activated owned secondary address ${CIDR} on ${INTERFACE}."
}

internal_down() {
    local status
    require_root
    ensure_privileged_directory "${RUNTIME_DIR}" 0700
    secure_lock "${RUNTIME_LOCK}" 8
    if ! load_state; then
        note "No runtime ownership state exists; no address was removed."
        return 0
    fi
    load_managed_config
    [[ "${STATE_INTERFACE}" == "${MANAGED_INTERFACE}" && \
       "${STATE_ADDRESS}" == "${MANAGED_LISTEN_IP}" && \
       "${STATE_PREFIX}" == "${MANAGED_PREFIX}" ]] || \
        die "Runtime ownership state does not match the root-only managed plan; refusing removal."
    if [[ "${STATE_OWNED}" == "pending" ]]; then
        die "Ownership state is pending/uncertain; refusing automatic address removal."
    fi
    if [[ "${STATE_OWNED}" == "1" ]]; then
        [[ -e "/sys/class/net/${STATE_INTERFACE}" ]] || die "Owned interface disappeared; preserving state for manual review."
        [[ "$(cat "/sys/class/net/${STATE_INTERFACE}/ifindex")" == "${STATE_IFINDEX}" ]] || \
            die "Interface ifindex changed; refusing to remove an address from a replacement interface."
        status="$(address_status "${STATE_ADDRESS}" "${STATE_INTERFACE}" "${STATE_PREFIX}")" || \
            die "Cannot inspect the owned address during removal"
        case "${status}" in
            exact)
                "${IP_BIN}" address del "${STATE_ADDRESS}/${STATE_PREFIX}" dev "${STATE_INTERFACE}"
                status="$(address_status "${STATE_ADDRESS}" "${STATE_INTERFACE}" "${STATE_PREFIX}")" || \
                    die "Cannot verify address removal; preserving ownership state."
                [[ "${status}" == "absent" ]] || \
                    die "Address removal could not be proven; preserving ownership state."
                ;;
            absent) note "Owned address was already absent." ;;
            *) die "Address now has a conflicting location/prefix; refusing automatic removal." ;;
        esac
    else
        note "Address was borrowed/pre-existing and was not removed."
    fi
    rm -f -- "${STATE_PATH}"
}

render_files() {
    local stage="$1"
    {
        printf '%s\n' "${MARKER}"
        printf 'LISTEN_IP=%s\n' "${LISTEN_IP}"
        printf 'PRINTER_IP=%s\n' "${PRINTER_IP}"
        printf 'INTERFACE=%s\n' "${INTERFACE}"
        printf 'PREFIX_LENGTH=%s\n' "${PREFIX_LENGTH}"
    } >"${stage}/secondary-ip.conf"
    cat >"${stage}/${ADDRESS_SERVICE}" <<EOF
${MARKER}
[Unit]
Description=commercialRCHproxy managed secondary IPv4 address
Wants=network-online.target
After=network-online.target
Before=${APP_SERVICE}

[Service]
Type=oneshot
ExecStart=${HELPER_PATH} up
ExecStop=${HELPER_PATH} down
RemainAfterExit=yes
RuntimeDirectory=commercialrchproxy-secondary-ip
RuntimeDirectoryMode=0700
RuntimeDirectoryPreserve=yes
UMask=0077
NoNewPrivileges=true
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_RAW
RestrictAddressFamilies=AF_UNIX AF_INET AF_NETLINK AF_PACKET
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true

[Install]
WantedBy=multi-user.target
EOF
    cat >"${stage}/10-secondary-ip.conf" <<EOF
${MARKER}
[Unit]
BindsTo=${ADDRESS_SERVICE}
After=${ADDRESS_SERVICE}
EOF
}

show_plan() {
    printf 'Configuration: %s\n' "${CONFIG_PATH}"
    printf 'Secondary address: %s\n' "${CIDR}"
    printf 'Existing LAN interface: %s (ifindex %s)\n' "${INTERFACE}" "${IFINDEX}"
    printf 'Route to configured printer: direct/on-link via %s\n' "${INTERFACE}"
    printf 'Address currently assigned: %s\n' "$([[ "${ADDRESS_PRESENT}" == "1" ]] && printf yes || printf no)"
}

run_check() {
    local failed=0
    require_root
    load_site_config
    build_plan
    show_plan
    if [[ "${ADDRESS_PRESENT}" == "1" ]]; then
        printf 'Runtime address: PASS\n'
    else
        printf 'Runtime address: ABSENT\n' >&2
        failed=1
    fi
    if managed_file "${UNIT_PATH}" && managed_file "${DROPIN_PATH}" && \
       managed_file "${MANAGED_CONFIG_PATH}" && managed_script "${HELPER_PATH}"; then
        load_managed_config
        if [[ "${MANAGED_LISTEN_IP}" != "${LISTEN_IP}" || \
              "${MANAGED_PRINTER_IP}" != "${PRINTER_IP}" || \
              "${MANAGED_INTERFACE}" != "${INTERFACE}" || \
              "${MANAGED_PREFIX}" != "${PREFIX_LENGTH}" ]]; then
            printf 'Persistent systemd service: PLAN MISMATCH; uninstall and reinstall the helper\n' >&2
            failed=1
        elif [[ -n "${SYSTEMCTL_BIN}" ]] && \
             "${SYSTEMCTL_BIN}" is-enabled --quiet "${ADDRESS_SERVICE}" && \
             "${SYSTEMCTL_BIN}" is-active --quiet "${ADDRESS_SERVICE}"; then
            if ! load_state; then
                printf 'Persistent systemd service: ACTIVE BUT OWNERSHIP STATE IS MISSING\n' >&2
                failed=1
            elif ! state_matches_plan; then
                printf 'Persistent systemd service: OWNERSHIP STATE MISMATCH\n' >&2
                failed=1
            elif [[ "${STATE_OWNED}" == "pending" ]]; then
                printf 'Persistent systemd service: OWNERSHIP STATE IS PENDING/UNCERTAIN\n' >&2
                failed=1
            else
                printf 'Persistent systemd service: PASS (enabled, active, matching plan; ownership=%s)\n' \
                    "$([[ "${STATE_OWNED}" == "1" ]] && printf owned || printf borrowed)"
            fi
        else
            printf 'Persistent systemd service: INSTALLED BUT NOT ENABLED/ACTIVE\n' >&2
            failed=1
        fi
    else
        printf 'Persistent systemd service: NOT INSTALLED\n' >&2
        failed=1
    fi
    printf 'RCH protocol/device connection: NOT ATTEMPTED\n'
    return "${failed}"
}

rollback_new_install() {
    local failed=0
    set +e
    if "${SYSTEMCTL_BIN}" is-active --quiet "${ADDRESS_SERVICE}"; then
        "${SYSTEMCTL_BIN}" stop "${ADDRESS_SERVICE}" >/dev/null 2>&1
        if "${SYSTEMCTL_BIN}" is-active --quiet "${ADDRESS_SERVICE}"; then
            failed=1
        fi
    fi
    "${SYSTEMCTL_BIN}" disable "${ADDRESS_SERVICE}" >/dev/null 2>&1
    if "${SYSTEMCTL_BIN}" is-enabled --quiet "${ADDRESS_SERVICE}"; then
        failed=1
    fi
    if path_exists "${STATE_PATH}"; then
        if [[ -x "${HELPER_PATH}" ]]; then
            "${HELPER_PATH}" down >/dev/null 2>&1 || failed=1
        else
            failed=1
        fi
    fi
    if path_exists "${STATE_PATH}" || [[ "${failed}" -ne 0 ]]; then
        printf 'ERROR: secondary-IP rollback is incomplete; preserving helper files and state for recovery.\n' >&2
        set -e
        return 1
    fi
    if ! rm -f -- "${DROPIN_PATH}" "${UNIT_PATH}" "${MANAGED_CONFIG_PATH}" "${HELPER_PATH}"; then
        failed=1
    fi
    if ! rm -f -- "${RUNTIME_LOCK}"; then
        failed=1
    fi
    rmdir -- "${RUNTIME_DIR}" "${DROPIN_DIR}" "${HELPER_DIR}" "${CONFIG_DIR}" >/dev/null 2>&1 || true
    if ! "${SYSTEMCTL_BIN}" daemon-reload >/dev/null 2>&1; then
        failed=1
    fi
    set -e
    return "${failed}"
}

run_install() {
    local address_load_state stage existing=0 new_install_started=0
    require_root
    [[ -n "${SYSTEMCTL_BIN}" && -n "${FLock_BIN}" ]] || die "systemctl and flock are required"
    command -v systemd-analyze >/dev/null 2>&1 || die "systemd-analyze is required"
    secure_lock "${MANAGER_LOCK}" 9
    load_site_config
    reject_documentation_addresses "${LISTEN_IP}" "${PRINTER_IP}"
    build_plan
    require_iputils_arping
    show_plan

    for path in "${UNIT_PATH}" "${DROPIN_PATH}" "${MANAGED_CONFIG_PATH}" "${HELPER_PATH}"; do
        if path_exists "${path}"; then
            existing=1
        fi
    done
    address_load_state="$("${SYSTEMCTL_BIN}" show "${ADDRESS_SERVICE}" -p LoadState --value 2>/dev/null || true)"
    if path_exists "${RUNTIME_DIR}" || [[ "${address_load_state}" != "not-found" ]] || \
       "${SYSTEMCTL_BIN}" is-active --quiet "${ADDRESS_SERVICE}" || \
       "${SYSTEMCTL_BIN}" is-enabled --quiet "${ADDRESS_SERVICE}"; then
        existing=1
    fi
    if [[ "${existing}" -eq 1 ]]; then
        if ! managed_file "${UNIT_PATH}" || ! managed_file "${DROPIN_PATH}" || \
           ! managed_file "${MANAGED_CONFIG_PATH}" || ! managed_script "${HELPER_PATH}"; then
            die "Partial or foreign secondary-IP installation exists; refusing to overwrite it."
        fi
        load_managed_config
        [[ "${MANAGED_LISTEN_IP}" == "${LISTEN_IP}" && "${MANAGED_PRINTER_IP}" == "${PRINTER_IP}" && \
           "${MANAGED_INTERFACE}" == "${INTERFACE}" && "${MANAGED_PREFIX}" == "${PREFIX_LENGTH}" ]] || \
            die "Managed plan differs. Run uninstall, review the new plan, then install again."
        "${SYSTEMCTL_BIN}" enable --now "${ADDRESS_SERVICE}"
        run_check
        note "Secondary-IP service was already installed; verified idempotently."
        return 0
    fi

    confirm_action INSTALL
    dad_check
    stage="$(mktemp -d /run/commercialrchproxy-secondary-ip-install.XXXXXX)"
    cleanup_stage() {
        local rc=$?
        trap - EXIT INT TERM HUP
        if [[ "${rc}" -ne 0 && "${new_install_started}" -eq 1 ]]; then
            if rollback_new_install; then
                printf 'WARNING: failed installation changes were rolled back.\n' >&2
            else
                printf 'ERROR: automatic rollback was incomplete; inspect %s and %s before retrying.\n' \
                    "${UNIT_PATH}" "${STATE_PATH}" >&2
            fi
        fi
        case "${stage}" in
            /run/commercialrchproxy-secondary-ip-install.*) rm -rf -- "${stage}" ;;
            *) printf 'WARNING: refusing unexpected staging cleanup: %s\n' "${stage}" >&2 ;;
        esac
        exit "${rc}"
    }
    trap cleanup_stage EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    trap 'exit 129' HUP
    render_files "${stage}"
    new_install_started=1
    ensure_privileged_directory "${CONFIG_DIR}" 0750
    ensure_privileged_directory "${HELPER_DIR}" 0755
    ensure_privileged_directory "${DROPIN_DIR}" 0755
    install -m 0755 -o root -g root -- "$(readlink -f -- "${BASH_SOURCE[0]}")" "${HELPER_PATH}"
    install -m 0600 -o root -g root -- "${stage}/secondary-ip.conf" "${MANAGED_CONFIG_PATH}"
    install -m 0644 -o root -g root -- "${stage}/${ADDRESS_SERVICE}" "${UNIT_PATH}"
    install -m 0644 -o root -g root -- "${stage}/10-secondary-ip.conf" "${DROPIN_PATH}"
    if ! systemd-analyze verify "${UNIT_PATH}" >/dev/null; then
        die "Generated systemd service failed validation; rollback will be attempted."
    fi
    "${SYSTEMCTL_BIN}" daemon-reload
    if ! "${SYSTEMCTL_BIN}" enable --now "${ADDRESS_SERVICE}"; then
        die "Could not activate ${ADDRESS_SERVICE}; rollback will be attempted."
    fi
    if ! run_check; then
        die "Post-install secondary-IP check failed; rollback will be attempted."
    fi
    new_install_started=0
    trap - EXIT INT TERM HUP
    case "${stage}" in
        /run/commercialrchproxy-secondary-ip-install.*)
            if ! rm -rf -- "${stage}"; then
                printf 'WARNING: installation succeeded but staging cleanup failed: %s\n' "${stage}" >&2
            fi
            ;;
        *) die "Refusing unexpected staging cleanup path: ${stage}" ;;
    esac
    note "Installed persistent secondary address service. Rerun commercialRCHproxy installation now."
}

run_uninstall() {
    local address_load_state answer
    require_root
    [[ -n "${SYSTEMCTL_BIN}" && -n "${FLock_BIN}" ]] || die "systemctl and flock are required"
    secure_lock "${MANAGER_LOCK}" 9
    address_load_state="$("${SYSTEMCTL_BIN}" show "${ADDRESS_SERVICE}" -p LoadState --value 2>/dev/null || true)"
    if ! path_exists "${UNIT_PATH}" && ! path_exists "${DROPIN_PATH}" && \
       ! path_exists "${MANAGED_CONFIG_PATH}" && ! path_exists "${HELPER_PATH}" && \
       ! path_exists "${RUNTIME_DIR}" && [[ "${address_load_state}" == "not-found" ]] && \
       ! "${SYSTEMCTL_BIN}" is-active --quiet "${ADDRESS_SERVICE}" && \
       ! "${SYSTEMCTL_BIN}" is-enabled --quiet "${ADDRESS_SERVICE}"; then
        note "Secondary-IP helper is not installed; nothing was removed."
        return 0
    fi
    if path_exists "${STATE_PATH}" && [[ ! -x "${HELPER_PATH}" ]]; then
        die "Runtime ownership state exists but the installed helper is missing; restore the matching helper before recovery."
    fi
    if ! managed_file "${UNIT_PATH}" || ! managed_file "${DROPIN_PATH}" || \
       ! managed_file "${MANAGED_CONFIG_PATH}" || ! managed_script "${HELPER_PATH}"; then
        die "Foreign or partial network files exist; refusing automatic removal."
    fi
    if [[ "${ASSUME_YES}" -eq 0 ]]; then
        [[ -t 0 ]] || die "Non-interactive uninstall requires --yes"
        printf 'This stops the proxy dependency and removes only a helper-owned secondary address.\n' >&2
        printf 'Type exactly "UNINSTALL" to continue: ' >&2
        IFS= read -r answer
        [[ "${answer}" == "UNINSTALL" ]] || die "Confirmation did not match; nothing was removed."
    fi
    "${SYSTEMCTL_BIN}" disable --now "${ADDRESS_SERVICE}"
    if path_exists "${STATE_PATH}"; then
        "${HELPER_PATH}" down
    fi
    rm -f -- "${DROPIN_PATH}" "${UNIT_PATH}" "${MANAGED_CONFIG_PATH}" "${HELPER_PATH}"
    rm -f -- "${RUNTIME_LOCK}"
    rmdir -- "${RUNTIME_DIR}" "${DROPIN_DIR}" "${HELPER_DIR}" "${CONFIG_DIR}" >/dev/null 2>&1 || true
    "${SYSTEMCTL_BIN}" daemon-reload
    "${SYSTEMCTL_BIN}" reset-failed "${ADDRESS_SERVICE}" >/dev/null 2>&1 || true
    note "Removed the managed service. Borrowed/pre-existing addresses were preserved."
}

case "${ACTION}" in
    install) run_install ;;
    check) run_check ;;
    uninstall) run_uninstall ;;
    up)
        internal_up
        ;;
    down) internal_down ;;
esac
