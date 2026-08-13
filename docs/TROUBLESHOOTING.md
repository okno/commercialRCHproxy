# Troubleshooting

## Are the two services up?

```bash
systemctl is-active commercialrchproxy-dumper.service
systemctl is-active commercialrchproxy-parser.service
systemctl status commercialrchproxy-dumper.service --no-pager
systemctl status commercialrchproxy-parser.service --no-pager
journalctl -u commercialrchproxy-dumper.service \
  -u commercialrchproxy-parser.service --since today
```

The legacy `commercialrchproxy.service` is only a no-op launcher and is not a
substitute for checking both real units.

## Where are captured files?

Read `OUTPUT_DIR` from the shared config; default:

```text
/var/lib/commercialrchproxy/jobs/<printer>/YYYY/MM/DD/<CODICE_DOC>/
```

Find committed jobs without reading payload:

```bash
find /var/lib/commercialrchproxy/jobs -type f -name .ready -print
find /var/lib/commercialrchproxy/jobs -type f -name .parsed -print
```

See [STORAGE_LAYOUT.md](STORAGE_LAYOUT.md). Production files may contain
sensitive data; do not copy them into public issues.

## Listener IP not assigned

Symptom:

```text
Cannot bind 192.0.2.231:23. The IP address is not assigned to this host.
```

The Dumper never adds the IP. Check the host network manager or separately
installed helper:

```bash
sudo ./scripts/manage_secondary_ip.sh check
systemctl status commercialrchproxy-secondary-ip.service --no-pager
ip -4 address
```

Do not guess a prefix or add an address without network approval. See
[NETWORK_ADDRESS.md](NETWORK_ADDRESS.md).

## Permission denied on port 23

The Dumper should have only bind capability:

```bash
systemctl show commercialrchproxy-dumper.service \
  -p User -p Group -p AmbientCapabilities -p CapabilityBoundingSet
```

Do not work around it by running the application as root. The Parser should
have no capability.

## Listener already in use

```bash
sudo ss -ltnp 'sport = :23'
```

Identify ownership/business impact before stopping any process. Do not run a
second Dumper against the same physical endpoint.

## Device unreachable

Inspect approved infrastructure telemetry, route/VLAN/firewall, cabling, and
device state. The Dumper logs bounded connect attempts and closes the client
without creating a synthetic reply.

Do not use `telnet`, `nc`, or an empty guessed connection during business
operation. Health/config checks deliberately avoid a device connection.

## Management timeout or missing response tail

Inspect the Dumper journal and capture manifest `close_reason`. A
`tail_timeout...` status means the opposite pump did not finish within
`RESPONSE_TIMEOUT_SEC` after the first clean EOF. Compare authorized direct and
proxy PCAP timing before changing it. Never synthesize a response.

## Dumper active, Parser stopped

This is supported. Ready jobs should accumulate and relay should continue.
Check:

```bash
find /var/lib/commercialrchproxy/jobs -type f -name .ready -print
systemctl start commercialrchproxy-parser.service
journalctl -u commercialrchproxy-parser.service -f
```

Parser will scan backlog deterministically. A parsed job receives `.parsed`.

## Hidden `.partial` directory

A crash/storage error can leave:

```text
.<code>.<job-id>.partial/
```

It is intentionally invisible to Parser discovery and must not be renamed to
a final code or given a hand-made `.ready`. Preserve it and correlate the
Dumper's critical `capture_partial_recovery_required`/
`capture_spool_failed` log. Use protected offline analysis if recovery is
required. Do not delete it until retention/evidence owners approve.

## Ready job is not parsed

Inspect only metadata/markers first:

```bash
find <job-dir> -maxdepth 2 -printf '%P %y\n'
journalctl -u commercialrchproxy-parser.service --since today
```

Possible states:

- `.processing`: another worker owns the job; verify age/heartbeat before
  assuming it is stale;
- `.parse_attempts.json`: retries remain;
- `.parse_failed`: retries exhausted; inspect error and use explicit reparse;
- `.parsed`: already complete/no-op;
- no marker: not yet scanned, watcher/poll delay, unsafe/invalid ready job, or
  service failure.

Run one bounded scan when intended:

```bash
commercialrchproxy-parser \
  --config /etc/commercialrchproxy/commercialrchproxy.conf --once
```

Do not manually remove `.processing` on a live worker. Stale recovery is token,
age, heartbeat, and lock protected.

## Hash/manifest mismatch

Parser rejects a `.ready` marker that does not authenticate `manifest.json`,
or any request/response/timeline whose SHA-256 differs from the manifest.
Treat this as altered/incomplete evidence:

1. stop reparse attempts;
2. preserve the full directory and storage logs;
3. compare against protected backup;
4. investigate disk/copy/administrator activity;
5. never edit RAW or manifest just to make parsing pass.

## No `PHARSED` or empty result

A valid framed stream may contain no supported document. The Parser retries and
eventually marks `.parse_failed`; it does not create fake receipt content.

Use the inspector on a protected copy/path:

```bash
commercialrchproxy-inspect-dump <request.raw> \
  --response <response.raw> --json --receipt
```

Check framing issues, candidate count/completeness, and unknown commands. The
new supplied private job legitimately yields one incomplete commercial
candidate; three other photographs have no supplied payload.

## TXT/PDF differs from paper

Trace a disputed field:

```text
TXT/PDF line
  -> PHARSED/parsed.json semantic/source
  -> request frame ID and offsets
  -> request RAW byte range
  -> timeline receive event
```

If the value exists in RAW but is mapped incorrectly, create a structurally
sanitized checksum-correct regression fixture. If it exists only on paper,
record it as printer-generated/unknown and keep it absent. Photos never fill
the model.

Capture and printed clocks can differ; parsed filenames use capture timeline
time in configured timezone, not the paper timestamp.

## Reparse safely

Validate first:

```bash
commercialrchproxy-reparse <job-dir> \
  --config /etc/commercialrchproxy/commercialrchproxy.conf \
  --code <CODICE_DOC> --dry-run
```

Preserve old output:

```bash
commercialrchproxy-reparse <job-dir> \
  --config /etc/commercialrchproxy/commercialrchproxy.conf \
  --code <CODICE_DOC> --backup-existing
```

Without `--backup-existing`, existing `PHARSED` is refused. Reparse validates
that immutable capture hashes did not change.

## Import legacy RAW without network replay

```bash
commercialrchproxy-replay <request.raw> --response <response.raw> \
  --config /etc/commercialrchproxy/commercialrchproxy.conf --json
```

This imports to spool and performs no network activity. It uses import time and
creates a new code, so keep a private migration ledger and never duplicate
imports to simulate missing evidence. See [MIGRATION.md](MIGRATION.md).

## Disk/archive failure

With default `STORAGE_FAILURE_POLICY=continue`, forwarding may continue while
capture publication fails. This protects relay continuity but can leave only a
critical log/partial. With `abort`, storage failure may terminate the session.

Check free space, inode usage, mount health, ownership/modes, and service
sandbox paths. Do not replay a request whose fiscal outcome is unknown.

## Unexpected parsed filename

Parsed names use configured local timezone and the candidate opener's request
timeline event:

```text
<code>_<C|G>_<HH.MM.SS.mmm>[_NN].txt|pdf
```

Unix time appears only in RAW names/technical metadata. If timezone changed,
back up `PHARSED` before explicit reparse; existing files are not renamed
automatically.

## Logs and payload privacy

```bash
journalctl -u commercialrchproxy-dumper.service --since today
journalctl -u commercialrchproxy-parser.service --since today
tail -f /var/log/commercialrchproxy/commercialrchproxy-dumper.jsonl
tail -f /var/log/commercialrchproxy/commercialrchproxy-parser.jsonl
```

Payload is absent from INFO logs. Bounded hexdump requires all of `DEBUG=true`,
`DEBUG_HEXDUMP=true`, and `LOG_PAYLOAD=true`; use only under approved handling.

## Sharing an example

Never publish real RAW, response, timeline, manifest, parsed JSON, TXT/PDF,
logs with payload, PCAP, photo, config, endpoints, source hash, merchant/device
identity, product, value, or timestamp. Create a synthetic fixture, recompute
length/BCC, and run the repository privacy/secret guard before committing.
