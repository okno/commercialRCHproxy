# Installation on Debian/Ubuntu

## Preconditions

- Dedicated Debian/Ubuntu host on the authorized hotel LAN.
- Python version supported by `pyproject.toml`.
- Physical RCH Print! F remains at its approved private address (`192.0.2.251` is the public documentation placeholder).
- Approved private proxy address assigned to the host, or approval to add it with the explicit secondary-address helper (`192.0.2.231` is the public documentation placeholder).
- Management software change window and rollback plan.
- Enough protected disk space for receipt archives.
- Packet-capture plan from `PACKET_CAPTURE.md`.

Do not install this pre-production release inline with fiscal operations until the hardware/PCAP gates in `COMPATIBILITY.md` pass.

## Install

```bash
git clone https://github.com/okno/commercialRCHproxy.git
cd commercialRCHproxy
cp .env.example commercialrchproxy.conf
nano commercialrchproxy.conf
sudo apt-get update
sudo apt-get install -y iputils-arping
sudo ./scripts/manage_secondary_ip.sh install --config "$PWD/commercialrchproxy.conf"
sudo ./scripts/manage_secondary_ip.sh check --config "$PWD/commercialrchproxy.conf"
sudo ./scripts/install.sh --config "$PWD/commercialrchproxy.conf"
```

The copied file is ignored by Git. Replace both RFC 5737 documentation
addresses with the approved private site values before running the installer.
The two helper commands are needed only when `LISTEN_IP` is not already
assigned persistently by the host network manager. The helper prints its
derived interface/prefix plan and requires the exact confirmation `INSTALL`.
Read [secondary network address](NETWORK_ADDRESS.md) before approving it.
On later runs the installer preserves `/etc/commercialrchproxy/commercialrchproxy.conf`
and rejects `--config`, so configuration cannot be overwritten accidentally.

The installer creates:

- system user/group `commercialrchproxy` with no interactive login;
- `/opt/commercialrchproxy` application and virtual environment;
- `/etc/commercialrchproxy/commercialrchproxy.conf` (preserved if already present);
- `/var/lib/commercialrchproxy/jobs` with mode `0750`;
- `/var/log/commercialrchproxy` with mode `0750`;
- hardened `commercialrchproxy.service`.

The application installer never configures an IP address, firewall, route,
management software, RCH device, or Wazuh agent. Only the separately invoked,
opt-in secondary-address helper changes an address, and it does not run from
install, update, start, or application service code.

## Privileged port

The service runs as the dedicated user. systemd grants only:

```ini
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
```

The process is not run as root.

If installed, `commercialrchproxy-secondary-ip.service` is a distinct root
oneshot unit with only the network capabilities required for address and ARP
operations. Those capabilities are never added to `commercialrchproxy.service`.

Python build/runtime dependencies are installed into the isolated release
virtual environment from `requirements-deployment.lock` with exact versions,
artifact hashes, and binary-only resolution. Updating that lock is a reviewed
source change; the application itself is then installed with `--no-deps`.
The isolated test runner and CI use the separate `requirements-dev.lock` under
the same hash and binary-only policy, then install the project with dependency
resolution and build isolation disabled.

Activation is rollback-protected. A post-switch failure restores the prior
release symlink, unit file, installed operations scripts, enabled state, and
active state; a failed first installation removes those newly installed
runtime components. Configuration and archived data are never overwritten by
that rollback.

## Configure and start

```bash
sudoedit /etc/commercialrchproxy/commercialrchproxy.conf
sudo ./scripts/manage_secondary_ip.sh check
sudo ./scripts/check_config.sh
sudo systemctl restart commercialrchproxy
sudo ./scripts/healthcheck.sh
```

Confirm the listener through `ss`/systemd, not by connecting to the proxy. A proxy connection opens an upstream RCH session.

## Rollback during acceptance

1. Stop the proxy: `sudo systemctl stop commercialrchproxy`.
2. Restore the management software target to the physical device's approved private address on port 23.
3. Confirm direct operation under the site's fiscal procedure.
4. Preserve logs, manifests, and PCAPs in protected storage.
5. Do not replay captured request bytes.
