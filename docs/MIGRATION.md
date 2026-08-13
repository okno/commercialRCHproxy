# Migration to 0.3.0

## What changed

0.3.0 is an architectural and storage-contract change:

- one combined relay/parser process became independent Dumper and Parser
  processes;
- one service became two real service units plus a no-op compatibility
  launcher;
- idle/fallback segments became one capture directory per transport connection;
- flat timestamp/job sidecars became a `CODICE_DOC` directory with immutable
  RAW/timeline/manifest/`.ready` and Parser-owned `PHARSED` output;
- Parser completion/retry/claim markers are persistent;
- a local per-printer counter now allocates codes.

The strict `KEY=VALUE` configuration format and default installed path are
retained. Existing private configuration must be preserved, not overwritten.

## Non-destructive migration policy

There is no automatic in-place rewrite of a 0.2 archive. Old artifacts may
contain incomplete inactivity segments, different manifests, and already
derived sidecars. Guessing their grouping or deleting them would damage the
evidence chain.

Migration therefore follows two rules:

1. preserve the complete old archive unchanged in a protected backup;
2. explicitly import selected verified directional RAW pairs into the new
   spool using the network-free replay tool.

The import creates a **new** 0.3 capture job and never deletes or modifies the
source. Its manifest states that no network delivery occurred.

## Pre-update checklist

Perform this during an approved management/fiscal change window.

1. Record the installed application version and service states.
2. Stop new proxy traffic or restore the management software's direct-device
   target under the site's procedure.
3. Stop the Dumper first, then the Parser/legacy launcher.
4. Verify that no active session or `.processing` marker is changing.
5. Back up, with restrictive permissions:
   - `/etc/commercialrchproxy`;
   - `/opt/commercialrchproxy` or the repository/release checkout;
   - the full `OUTPUT_DIR`, including hidden `.state` and partial directories;
   - `LOG_DIR` and relevant journals;
   - installed systemd units/drop-ins and optional secondary-IP ownership
     state.
6. Calculate and retain backup hashes in protected storage; do not publish
   production hashes in Git or tickets.
7. Verify restore access before changing the release.

Example backup commands depend on the site's backup system. Avoid broad
unreviewed recursive deletion/move operations and never omit hidden `.state`.

## Configuration migration

0.2 keys remain accepted. Missing 0.3 keys receive safe documented defaults,
so an existing valid file can start without conversion. For auditability,
compare it to [.env.example](../.env.example) and add explicit values for:

```ini
TIMEZONE=Europe/Rome
CONFIG_VERSION=1
BUFFER_SIZE=65536
MAX_CONNECTIONS=32
PRINTER_CONNECT_ATTEMPTS=1
PRINTER_CONNECT_RETRY_DELAY_SEC=1
STORAGE_FAILURE_POLICY=continue

JOB_CODE_START=1
JOB_CODE_WIDTH=4
PHARSED_DIRNAME=PHARSED
FILE_MODE=0640
DIRECTORY_MODE=0750
SERVICE_USER=commercialrchproxy
SERVICE_GROUP=commercialrchproxy
FSYNC_ON_CLOSE=true
PRESERVE_TIMELINE=true
CALCULATE_SHA256=true
MAX_CAPTURE_EVENTS=65536

PARSER_WORKERS=2
PARSER_POLL_INTERVAL_SEC=5
PARSER_RETRY_COUNT=3
PARSER_STALE_LOCK_SEC=300
PARSER_USE_INOTIFY=true
```

Do not replace private endpoint values with the RFC 5737 examples. Do not
change `CONFIG_VERSION` from `1` or `PHARSED_DIRNAME` from the literal
`PHARSED`.

`JOB_IDLE_TIMEOUT_MS` is accepted for compatibility but no longer divides
capture jobs. 0.3 uses the transport connection lifecycle.

Before the **first** 0.3 live capture, choose `JOB_CODE_START` so it cannot
collide with any manually created/new-format code directory for that printer.
After allocation begins, the authoritative state is:

```text
<OUTPUT_DIR>/.state/<printer>/next-code
```

Never reset/delete/edit that file during update or rollback.

## Application update

From the trusted checkout, after reviewing the branch/tag and dependency-lock
changes:

```bash
cd commercialRCHproxy
sudo ./scripts/update.sh
```

Then verify that installation contains both real units:

```bash
systemctl cat commercialrchproxy-dumper.service
systemctl cat commercialrchproxy-parser.service
systemctl cat commercialrchproxy.service
```

The legacy unit is only a compatibility launcher. Process-independence checks
must operate the two real services directly.

Validate without connecting to the physical device:

```bash
sudo ./scripts/check_config.sh
sudo systemctl start commercialrchproxy-parser.service
sudo systemctl start commercialrchproxy-dumper.service
sudo systemctl status commercialrchproxy-dumper.service
sudo systemctl status commercialrchproxy-parser.service
sudo journalctl -u commercialrchproxy-dumper.service \
  -u commercialrchproxy-parser.service --since today
```

Starting the Parser first is safe and demonstrates there is no required order.
Starting the Dumper can accept real management connections; do so only after
the endpoint/change window is ready.

Review [SYSTEMD.md](SYSTEMD.md) for unit/drop-in handling. The separate
secondary-address helper remains an explicit network operation; application
update must not silently add/remove an address.

## Inspect old evidence before import

Do not assume similarly named files belong to one transaction. Inspect an old
archive and verify session/direction/hash information first:

```bash
commercialrchproxy-inspect-dump /protected/legacy/archive \
  --json --output-dir /protected/legacy-analysis
```

For individual files:

```bash
commercialrchproxy-inspect-dump /protected/legacy/request.raw \
  --response /protected/legacy/response.raw --receipt --json
```

Never join captures solely by filename timestamp, proximity, photo label, or
similar business content. Where reliable legacy `session_id` and chronological
metadata exist, the inspector can reconstruct same-session segments for
forensic review; it does not rewrite the production spool.

## Import selected old RAW

After verifying one request/response pair:

```bash
commercialrchproxy-replay /protected/legacy/request.raw \
  --response /protected/legacy/response.raw \
  --config /etc/commercialrchproxy/commercialrchproxy.conf --json
```

Important properties:

- no socket connection or physical-printer transmission occurs;
- source files are opened as bounded regular non-symlink files;
- request and response must be different files;
- the combined size is bounded by `MAX_PAYLOAD_BYTES`;
- a new `CODICE_DOC` is allocated unless `--code` explicitly selects a safe,
  unused code;
- the response file in the new job exists even if `--response` is omitted;
- the new manifest reports offline supplied files and no network delivery;
- the Parser discovers the new `.ready` job normally.

The current CLI uses **import time** for the new technical timeline/date path
and parsed human filename. It does not preserve a legacy capture timestamp from
old metadata. Preserve the old archive/manifest as the authoritative historical
time record. This limitation prevents a falsely precise timestamp migration.

Keep an external protected migration ledger recording source paths/hashes and
new code. Do not commit that ledger.

## Parse or reparse a migrated job

Normal backlog processing:

```bash
commercialrchproxy-parser \
  --config /etc/commercialrchproxy/commercialrchproxy.conf --once
```

Validate an existing 0.3 ready job before reparse:

```bash
commercialrchproxy-reparse /var/lib/commercialrchproxy/jobs/192.0.2.251/YYYY/MM/DD/0001 \
  --config /etc/commercialrchproxy/commercialrchproxy.conf \
  --code 0001 --dry-run
```

Preserve existing Parser output and regenerate:

```bash
commercialrchproxy-reparse /var/lib/commercialrchproxy/jobs/192.0.2.251/YYYY/MM/DD/0001 \
  --config /etc/commercialrchproxy/commercialrchproxy.conf \
  --code 0001 --backup-existing
```

`reparse` accepts only new ready jobs below configured `OUTPUT_DIR`. It refuses
to overwrite `PHARSED` without `--backup-existing`, refuses a live processing
claim, and checks immutable capture hashes before/after.

## Supplied private legacy job

The supplied private directory has one 235-byte request/202-byte response job,
not four documents. Importing it once can produce at most one incomplete
commercial candidate. It cannot be used to create the missing management
command, pre-account, or conforming copy.

Keep its source hash/private backup outside Git. Do not duplicate-import it to
simulate missing documents. See [RCH_DUMP_ANALYSIS.md](RCH_DUMP_ANALYSIS.md).

## Operational acceptance after upgrade

Before routing normal management traffic through the Dumper, verify:

- both services run as the dedicated non-root identity;
- Dumper alone can be up while Parser is stopped;
- Parser alone can drain a prepared synthetic/offline backlog;
- listener ownership is visible through `ss`/systemd without an active connect
  probe;
- a synthetic authorized relay test preserves both directional hashes;
- a `.ready` directory never exposes `.partial` files;
- Parser restart processes exactly once and writes `.parsed`;
- logs are distinct and no INFO payload appears;
- disk monitoring/backup includes `.state`, hidden partials, RAW, and PHARSED.

A physical-device and direct/proxy PCAP acceptance remains separate. Do not
claim production byte transparency solely from a simulated peer.

## Rollback

### Operational bypass

1. Stop `commercialrchproxy-dumper.service` to prevent new proxy sessions.
2. Allow/handle any interrupted fiscal transaction under the site's procedure;
   never automatically replay its captured request.
3. Restore the management software's approved direct physical-device endpoint.
4. Verify direct operation under the authorized fiscal workflow.
5. Stop the Parser only if application rollback or storage work requires it;
   otherwise it may finish existing ready backlog.
6. Preserve all logs, `.partial`, `.ready`, `.processing`, `.parsed`, and
   `.parse_failed` evidence.

### Application rollback

Restore the previously backed-up release, units, and configuration according
to the deployment system, then run its non-invasive validation. Do not point
0.2 code at the 0.3 spool expecting compatibility.

Rollback limitations:

- 0.3 capture directories are not reverse-migrated to the 0.2 flat layout;
- `CODICE_DOC` counter state must not move backwards;
- 0.3 Parser markers and `PHARSED` are not understood by 0.2;
- derived output produced by a newer Parser is retained evidence, not deleted;
- changing application code cannot undo real bytes already forwarded;
- a capture with unknown fiscal outcome must never be resent automatically.

The safest rollback is application/network bypass plus preservation of the 0.3
spool for offline inspection with the matching 0.3 tool version.

## Data removal

Migration and rollback do not authorize deletion. The standard uninstall path
must preserve configuration, spool, logs, counter state, and backups unless an
explicit separately reviewed purge is requested. Fiscal/privacy retention
policy belongs to the site, not to an automatic parser cleanup.
