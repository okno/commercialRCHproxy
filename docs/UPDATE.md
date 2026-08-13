# Update

0.3.0 changes service topology and storage layout. Read
[MIGRATION.md](MIGRATION.md) before updating from 0.2.x.

## Before update

- schedule an approved management/fiscal change window;
- restore/direct traffic away from the proxy or otherwise prevent new sessions;
- stop Dumper first and record Parser/legacy unit states;
- back up configuration, releases, full spool including hidden `.state` and
  partials, logs/journals, units/drop-ins, and network-helper state;
- verify backup hashes/restore privately;
- inspect changelog, dependency locks, and unexplained worktree changes;
- never commit real RAW/PCAP/photo/PDF/config/hashes.

## Update command

From the trusted checkout:

```bash
cd commercialRCHproxy
sudo ./scripts/update.sh
```

The updater is expected to preserve configuration/data, install the reviewed
locked dependencies/release, install both real units and the compatibility
launcher, run its validation, activate, and health-check. A final target-host
test result must be recorded in [TEST_REPORT.md](TEST_REPORT.md); do not infer
success from script exit alone.

## Post-update checks

```bash
sudo ./scripts/check_config.sh
systemctl cat commercialrchproxy-dumper.service
systemctl cat commercialrchproxy-parser.service
systemctl status commercialrchproxy-dumper.service
systemctl status commercialrchproxy-parser.service
journalctl -u commercialrchproxy-dumper.service \
  -u commercialrchproxy-parser.service --since today
```

Verify the shared config path, service identities/capabilities, spool ownership,
counter state, and that old archive files remain untouched. Start Parser and
Dumper separately to establish independence.

If `SERVICE_USER`, `SERVICE_GROUP`, `OUTPUT_DIR`, or `LOG_DIR` changed, the
installer invoked by the updater recreates/renders the OS contract for both
real units. Verify effective `User`, `Group`, `WorkingDirectory`, and
`ReadWritePaths` with `systemctl show`; a service restart alone does not apply
those config changes.

## Failure/rollback

If activation or health fails:

1. stop Dumper to prevent new proxy sessions;
2. restore direct-device operation under the approved procedure;
3. preserve every 0.3 job/marker/log and never replay unknown-state bytes;
4. restore the previous release/config/units from the verified backup;
5. keep the 0.3 spool and `.state` for matching offline tools; do not point 0.2
   code at it or move the counter backwards.

An application rollback cannot undo bytes already forwarded and does not
reverse-migrate 0.3 jobs. See [MIGRATION.md](MIGRATION.md#rollback).
