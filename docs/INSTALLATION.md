# Installation on Debian/Ubuntu

## Preconditions

- approved dedicated host/LAN/change window;
- supported Python from `pyproject.toml`;
- approved private listener/device endpoints (RFC 5737 examples are not
  installable production values);
- protected disk/backup/monitoring for RAW evidence and counter state;
- direct-device rollback procedure;
- compatibility/PCAP plan from [COMPATIBILITY.md](COMPATIBILITY.md).

Do not place this pre-acceptance release inline with fiscal operations until
site/device gates pass.

## Install

```bash
git clone https://github.com/okno/commercialRCHproxy.git
cd commercialRCHproxy
cp .env.example commercialrchproxy.conf
nano commercialrchproxy.conf
sudo ./scripts/install.sh --config "$PWD/commercialrchproxy.conf"
```

The installer must preserve an existing
`/etc/commercialrchproxy/commercialrchproxy.conf`; review its backup behavior
before re-running. Never put the private config in Git.

Expected components:

- dedicated non-login user/group from shared configuration;
- `/opt/commercialrchproxy` releases/current virtual environment;
- `/etc/commercialrchproxy/commercialrchproxy.conf`;
- configured `OUTPUT_DIR` (`0750`), including durable `.state`;
- configured `LOG_DIR` (`0750`);
- `commercialrchproxy-dumper.service`;
- `commercialrchproxy-parser.service`;
- legacy no-op `commercialrchproxy.service` launcher.

Both real units use the same config and can start in either order. The legacy
unit is convenience only.

The repository units are valid default templates. During installation they
are rendered in private staging with configured `SERVICE_USER`,
`SERVICE_GROUP`, `OUTPUT_DIR`, and `LOG_DIR`, verified, and activated in the
same rollback transaction as the release. The configuration is parsed as
strict `KEY=VALUE` data and is never sourced by a shell.

The installer does not configure interfaces, routes, firewall, DNS, management
software, device settings, Wazuh, or PCAP. If a secondary listener address is
approved and not managed natively, invoke the separate helper exactly as
described in [NETWORK_ADDRESS.md](NETWORK_ADDRESS.md).

## Capabilities and sandbox

The Dumper runs non-root with only:

```ini
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_BIND_SERVICE
```

The Parser runs non-root with no capabilities and no IP network access. Both
have read-only config/application paths and writable job/log roots under the
systemd sandbox. Review [SYSTEMD.md](SYSTEMD.md).

## Validate before start

```bash
sudoedit /etc/commercialrchproxy/commercialrchproxy.conf
sudo ./scripts/check_config.sh
systemctl cat commercialrchproxy-dumper.service
systemctl cat commercialrchproxy-parser.service
```

The config check must not connect to the device. Confirm listener ownership
with `ss`/systemd, not `telnet`/`nc`; even an empty connection is not proven
inert.

## Start independently

Parser first (safe backlog scan, no IP network):

```bash
sudo systemctl enable --now commercialrchproxy-parser.service
```

Dumper only when the operational endpoint/change window is ready:

```bash
sudo systemctl enable --now commercialrchproxy-dumper.service
```

Inspect:

```bash
systemctl status commercialrchproxy-dumper.service
systemctl status commercialrchproxy-parser.service
journalctl -u commercialrchproxy-dumper.service \
  -u commercialrchproxy-parser.service --since today
```

Starting/stopping `commercialrchproxy.service` operates both real units for
legacy procedures but should not be used for independence testing.

## Initial acceptance

Before real fiscal traffic:

1. use a synthetic authorized peer to verify byte-for-byte bidirectional relay;
2. stop Parser and verify Dumper still publishes one ready job;
3. start Parser and verify exactly one `.parsed` result;
4. verify request/response/timeline/manifest hashes remain unchanged;
5. inspect file modes, component logs, disk monitoring, and backup coverage;
6. test direct-device bypass/rollback;
7. execute device/PCAP acceptance separately.

Never replay an unknown-state captured request to the physical device.

## Update and migration

Upgrading from 0.2 requires the non-destructive procedure in
[MIGRATION.md](MIGRATION.md). The old flat archive is not rewritten
automatically and 0.3 `CODICE_DOC/.state` must survive updates/rollback.

## Rollback during acceptance

1. Stop `commercialrchproxy-dumper.service`.
2. Restore the approved direct-device target in the management software.
3. Confirm direct operation under the site's fiscal procedure.
4. Preserve all partial/ready/parsed jobs, counter state, logs, and PCAP.
5. Stop Parser only if required for application/storage rollback.
6. Do not replay captured request bytes.
