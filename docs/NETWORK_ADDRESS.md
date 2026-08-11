# Secondary network address

`commercialRCHproxy` must listen on a local IPv4 address that the management
software can reach. On Linux this normally means a secondary address on the
existing LAN interface, not a separate `dummy` device. A dummy device does not
provide the expected layer-2 presence on the hotel LAN.

The application service never changes host networking. The repository includes
an optional, operator-invoked helper for sites that do not manage the address
through NetworkManager, `systemd-networkd`, ifupdown, or another native network
manager:

```bash
sudo ./scripts/manage_secondary_ip.sh install \
  --config /etc/commercialrchproxy/commercialrchproxy.conf
sudo ./scripts/manage_secondary_ip.sh check
```

For a fresh installation, the helper can read the same private, untracked file
that will be passed to the application installer:

```bash
sudo apt-get update
sudo apt-get install -y iputils-arping
sudo ./scripts/manage_secondary_ip.sh install \
  --config "$PWD/commercialrchproxy.conf"
sudo ./scripts/manage_secondary_ip.sh check \
  --config "$PWD/commercialrchproxy.conf"
sudo ./scripts/install.sh --config "$PWD/commercialrchproxy.conf"
```

Public examples use RFC 5737 documentation addresses. The private configuration
must contain the approved site addresses. Never commit it.

## Preconditions

Obtain all of the following from the network administrator before running
`install`:

- approval for `LISTEN_IP` and a DHCP/IPAM reservation excluding it from other
  allocations;
- confirmation that `PRINTER_IP` is directly on-link from this server;
- the correct LAN interface and prefix;
- a maintenance window and a rollback path.

ARP duplicate-address detection reduces risk at that instant, but it cannot
prove future uniqueness: ARP filtering, sleeping hosts, and the interval
between probe and add remain limitations.

## What the helper accepts

The helper parses only `LISTEN_IP` and `PRINTER_IP`; it never uses `source` or
`eval`. It then:

1. asks the local kernel for the route to `PRINTER_IP` without connecting to
   the device;
2. requires one existing, non-loopback, ARP-capable interface that is both
   administratively up and carrying link, plus a direct route with no gateway
   or multipath next hop;
3. finds an existing global IPv4 prefix on that interface that contains both
   endpoint addresses;
4. refuses ambiguous/missing prefixes, network/broadcast addresses, a local
   `PRINTER_IP`, or a conflicting assignment of `LISTEN_IP`;
5. runs duplicate-address detection with Debian `iputils-arping`;
6. adds only `LISTEN_IP/PREFIX` with `noprefixroute`.

It does not create/change routes, firewall rules, DNS, interface state, the RCH
device, or the port-23 protocol. It never assumes `/24` from the address text.
The displayed plan must be confirmed by typing exactly `INSTALL` unless
`--yes` was intentionally supplied for controlled automation.

If automatic selection fails and the approved values are already known, they
can be asserted explicitly:

```bash
sudo ./scripts/manage_secondary_ip.sh install \
  --interface <approved-interface> \
  --prefix-length <approved-prefix>
```

The overrides must still agree with the kernel route and an existing matching
prefix; they cannot force an otherwise rejected topology.

## Persistence and privileges

Installation creates:

- `/etc/commercialrchproxy/secondary-ip.conf`, root-only snapshot of the two
  endpoints and approved interface identity;
- `/usr/local/libexec/commercialrchproxy-network/manage_secondary_ip.sh`;
- `/etc/systemd/system/commercialrchproxy-secondary-ip.service`;
- `/etc/systemd/system/commercialrchproxy.service.d/10-secondary-ip.conf`.

The separate oneshot unit runs before and is bound to the application service.
It has `CAP_NET_ADMIN` and `CAP_NET_RAW` in its own bounding set. The non-root
proxy service retains only `CAP_NET_BIND_SERVICE`.

At each activation, the helper revalidates the route, prefix, interface name,
and interface index. Runtime ownership is recorded root-only below
`/run/commercialrchproxy-secondary-ip`. An exact address that already existed
is marked borrowed and is never removed by the helper.

A oneshot unit does not continuously fight the host network manager. If that
manager recreates the interface later, run `check`; use native persistent
configuration when post-boot interface recreation is normal.

## Passive check and removal

```bash
sudo ./scripts/manage_secondary_ip.sh check
```

`check` reads local route/address and systemd state only. It does not ping the
printer and does not connect to the proxy or RCH port 23.

To remove the optional service:

```bash
sudo ./scripts/manage_secondary_ip.sh uninstall
```

Type exactly `UNINSTALL`. The command first stops the dependent application,
then deletes only the exact helper-owned address if interface identity and
runtime state still match. It refuses uncertain/malformed state instead of
guessing. A borrowed address remains in place. Application uninstall/purge
never invokes this command implicitly; purge requires this helper to be
removed first.
