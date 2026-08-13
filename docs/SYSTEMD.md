# systemd services

`commercialRCHproxy` runs as two independent operating-system processes.  They
share the validated configuration at
`/etc/commercialrchproxy/commercialrchproxy.conf` and communicate only through
the persistent job spool at configured `OUTPUT_DIR`.

| Unit | Executable | Responsibility | IP networking | Linux capabilities |
|---|---|---|---|---|
| `commercialrchproxy-dumper.service` | `commercialrchproxy-dumper` | Full-duplex relay and atomic RAW-job publication | IPv4 and IPv6 | `CAP_NET_BIND_SERVICE` only |
| `commercialrchproxy-parser.service` | `commercialrchproxy-parser` | Ready-job validation, parsing and `PHARSED` publication | Disabled | None |

Neither real unit has a `Requires=`, `Wants=`, `After=` or `Before=` relation
to the other.  The parser may be stopped for maintenance while the dumper
continues relaying and publishing ready jobs.  Starting the parser later must
process that backlog from the filesystem.  Likewise, a parser failure cannot
stop or restart the dumper.

## Normal operation

After the units and application release are installed:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now commercialrchproxy-dumper.service
sudo systemctl enable --now commercialrchproxy-parser.service
```

The order is intentionally irrelevant.  Operate and inspect them separately:

```bash
sudo systemctl status commercialrchproxy-dumper.service --no-pager --full
sudo systemctl status commercialrchproxy-parser.service --no-pager --full

sudo systemctl restart commercialrchproxy-dumper.service
sudo systemctl restart commercialrchproxy-parser.service

sudo journalctl -u commercialrchproxy-dumper.service -n 100 --no-pager
sudo journalctl -u commercialrchproxy-parser.service -n 100 --no-pager
```

The journald identifiers are respectively `commercialrchproxy-dumper` and
`commercialrchproxy-parser`.  Application JSONL logs also use component-aware
names below configured `LOG_DIR`; receipt payload is not an INFO-log
field.

## Permissions and isolation

Both services run as configured unprivileged `SERVICE_USER:SERVICE_GROUP` with
umask `0027`. Application code and configuration are read-only. Their only
persistent writable locations are configured `OUTPUT_DIR` and `LOG_DIR`.
The checked-in units contain default values and remain directly verifiable;
`install.sh` safely renders their `User`, `Group`, `WorkingDirectory`, and
`ReadWritePaths` directives before installing them. It creates the two paths
itself instead of relying on systemd's fixed-name `LogsDirectory=` facility.

The dumper receives only `CAP_NET_BIND_SERVICE`, needed when the configured
listener uses port 23.  Its address-family allow-list contains `AF_INET` and
`AF_INET6` (plus local `AF_UNIX`).  The parser has an empty capability bounding
set, a private network namespace, `IPAddressDeny=any`, and only `AF_UNIX`.
Both units retain the existing strict filesystem, device, kernel, namespace,
process and syscall protections.

The Parser template sets `TasksMax=256`. At the accepted maximum of 64 parser
workers, each active claim can use one executor thread plus one lease-heartbeat
thread; the remaining capacity is reserved for the main loop, watcher, bounded
logging worker, and orderly shutdown. The Dumper remains independently bounded
at `TasksMax=64`.

## Legacy unit

`commercialrchproxy.service` is a transitional compatibility launcher.  It
does not run a third proxy process: starting it starts the two real units and
then remains active as an unprivileged no-op; stopping it propagates a stop to
both.  New automation should address the dumper and parser units directly so
their independent state is visible.

Do not enable both the legacy launcher and the two real units in newly managed
installations.  Although systemd deduplicates the start jobs, using one model
avoids ambiguous operational ownership.

## Secondary listen address integration

Current releases of `manage_secondary_ip.sh` install the generated drop-in at:

```text
/etc/systemd/system/commercialrchproxy-dumper.service.d/10-secondary-ip.conf
```

The drop-in binds/orders only the dumper after
`commercialrchproxy-secondary-ip.service`; the parser has no dependency on
that address service.  During an upgrade from the legacy unit, reinstall the
secondary-address integration so the helper removes the obsolete legacy
drop-in and publishes the dumper drop-in:

```bash
sudo /usr/local/libexec/commercialrchproxy-network/manage_secondary_ip.sh install --yes
```

## Manual unit validation

On the target Debian host:

```bash
sudo systemd-analyze verify \
  /etc/systemd/system/commercialrchproxy-dumper.service \
  /etc/systemd/system/commercialrchproxy-parser.service \
  /etc/systemd/system/commercialrchproxy.service

sudo systemctl show commercialrchproxy-dumper.service \
  -p User -p Group -p WorkingDirectory -p CapabilityBoundingSet \
  -p AmbientCapabilities -p RestrictAddressFamilies -p ReadWritePaths

sudo systemctl show commercialrchproxy-parser.service \
  -p User -p Group -p WorkingDirectory -p CapabilityBoundingSet -p AmbientCapabilities \
  -p PrivateNetwork -p IPAddressDeny -p RestrictAddressFamilies \
  -p ReadWritePaths
```

`systemd-analyze verify` validates unit syntax and executable references; it
does not connect to the fiscal device and does not establish relay or fiscal
success.
