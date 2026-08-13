# Persistent spool and output layout

## Contract

`OUTPUT_DIR` is the only coordination channel between Dumper and Parser. The
Dumper owns capture artifacts and publication markers. The Parser may read
those artifacts but may write only Parser state and the `PHARSED` subtree.

Default root:

```text
/var/lib/commercialrchproxy/jobs
```

Public examples use RFC 5737 addresses:

```text
<OUTPUT_DIR>/
  .state/
    192.0.2.251/
      next-code
      next-code.lock
  192.0.2.251/
    YYYY/
      MM/
        DD/
          0001/
            file_<seconds>.<9 digits>.raw
            response_<seconds>.<9 digits>.raw
            timeline_<seconds>.<9 digits>.jsonl
            manifest.json
            .ready
            PHARSED/
              0001_C_HH.MM.SS.mmm.txt
              0001_C_HH.MM.SS.mmm.pdf
              0001_G_HH.MM.SS.mmm.txt
              0001_G_HH.MM.SS.mmm.pdf
              parsed.json
            .parsed
```

Actual directory dates use the capture opening time converted through
`TIMEZONE`. The printer path component is derived from configured device
identity and sanitized before use.

## CODICE_DOC

The supplied protocol evidence contains no proven collision-free job key, so
0.3.0 uses a persistent local counter per printer:

```text
<OUTPUT_DIR>/.state/<printer>/next-code
```

Allocation is serialized by `next-code.lock`. The next value is atomically
written before the allocated code is returned. `JOB_CODE_WIDTH` is a minimum,
not a modulus: after `9999`, a four-digit configuration produces `10000`, not
`0000`. Codes contain decimal digits only and are validated before use as a
path component.

Handwritten photo labels, inferred document numbers, and response suffixes are
not `CODICE_DOC`.

## RAW filenames

Request direction (management software to configured device):

```text
file_<Unix seconds>.<nanoseconds>.raw
```

Response direction (configured device to management software):

```text
response_<Unix seconds>.<nanoseconds>.raw
```

The fractional field always contains exactly nine digits. For example, a
synthetic timestamp would render as:

```text
file_1700000000.123456789.raw
```

This is an integer-nanosecond **representation**. The manifest explicitly
labels platform clock resolution as unverified; padding/truncating a runtime
timestamp does not prove physical nanosecond measurement.

The response file always exists. If no response bytes were received it is a
zero-byte regular file with the SHA-256 of empty content and a response size of
zero in the manifest. This makes absence deterministic without confusing it
with a missing artifact.

RAW files contain only original directional bytes. They do not contain
timeline JSON, hexdumps, decoded text, or payload from the opposite direction.

## Timeline JSONL

The timeline name follows the request capture start:

```text
timeline_<Unix seconds>.<nanoseconds>.jsonl
```

Each line describes one retained receive observation and does not duplicate
payload:

```json
{
  "byte_count": 12,
  "connection_id": "<generated>",
  "direction": "CLIENT -> RCH",
  "error": null,
  "forward_status": "local_write_drain_completed",
  "forwarded_unix_ns": 1700000000123456790,
  "job_offset": 0,
  "local_write_drain_completed": true,
  "local_write_drain_unix_ns": 1700000000123456791,
  "monotonic_ns": 123456789,
  "received_at": "<ISO-8601>",
  "received_unix_ns": 1700000000123456789,
  "remote_arrival": null,
  "sequence": 1,
  "session_id": "<generated>",
  "session_offset": 0,
  "sha256": "<event-byte-range-sha256>"
}
```

Values above are synthetic. `job_offset` addresses the corresponding
directional RAW. `local_write_drain_completed` records local runtime progress
only. `remote_arrival` remains null without independent capture evidence.
`MAX_CAPTURE_EVENTS` can bound timeline metadata while RAW capture status is
reported separately.

## Capture manifest

`manifest.json` uses schema `commercialrchproxy.capture.v1` and includes:

- `codice_doc`, generated job/session/connection identifiers;
- configured listen/device endpoints and observed client endpoint;
- opening/closing ISO timestamps and integer Unix-nanosecond technical values;
- request/response sizes and local byte counters;
- close reason and connection-lifecycle boundary evidence;
- final artifact basenames and SHA-256 values;
- raw/timeline completeness and errors;
- timeline observed/retained counts;
- remote-delivery fields left null/unconfirmed;
- Dumper version, configuration version, timezone, and publication status.

The manifest never turns successful local writes, a valid BCC, an ACK, or
absence of parser errors into proof of printer/fiscal success.

## Atomic Dumper publication

An active job is invisible to the Parser under a hidden name:

```text
.<CODICE_DOC>.<generated-job-id>.partial/
```

It contains `.partial` artifacts and provisional metadata. The publication
sequence is:

1. create hidden directory with restrictive permissions and reject symlinks;
2. append request/response bytes and timeline records;
3. flush and `fsync` all active files;
4. close files and `fsync` the hidden directory;
5. rename artifacts to final basenames;
6. compute SHA-256 and atomically write `manifest.json`;
7. atomically write `.ready` containing schema, code, manifest SHA-256, and
   publication time;
8. `fsync` the hidden directory;
9. atomically rename the hidden directory to `<CODICE_DOC>`;
10. `fsync` the parent date directory.

Because `.ready` is created before the final directory rename, the final job
path appears as one committed directory tree. The Parser nevertheless validates
every part of the contract and rejects any remaining `.partial` file.

A crash can leave the hidden partial directory. Startup reports sufficiently
old partials for operator attention, but never automatically promotes or
deletes them. A partial does not prove complete capture.

## `.ready` binding

The ready marker is small JSON using the capture schema. It binds:

- its `CODICE_DOC` to the final directory name;
- `manifest_sha256` to the exact capture manifest;
- publication time for technical audit.

The Parser then validates the manifest's `files` and `sha256` maps and reads
only contained, regular, non-symlink files whose combined directional size is
within `MAX_PAYLOAD_BYTES`.

## PHARSED naming

The directory name is intentionally and literally:

```text
PHARSED
```

For every reconstructed candidate:

```text
<CODICE_DOC>_<TYPE>_<HH.MM.SS.mmm>.txt
<CODICE_DOC>_<TYPE>_<HH.MM.SS.mmm>.pdf
```

`TYPE` is `C` or `G`. Time comes from the request timeline event covering the
candidate start offset, converted through configured `TIMEZONE`. It is local
human time, not Unix time.

For an exact same-code/type/millisecond collision inside one job:

```text
0001_G_12.34.56.789.txt
0001_G_12.34.56.789_02.txt
0001_G_12.34.56.789_03.txt
```

The matching PDF uses the same stem. Unix timestamps are prohibited in parsed
TXT/PDF names and operator-facing document text.

`PHARSED/parsed.json` uses schema `commercialrchproxy.pharsed.v1` and records
the Parser version, capture-manifest hash, Parser status, ordered documents,
type/subtype/evidence, local capture time, source offsets/frame IDs, output
names/hashes, protocol issues, response correlations, and semantic data.

TXT/PDF are generated from the same `DocumentModel`. Each begins with an
explicit non-document parser metadata section so a reconstruction cannot be
mistaken for an original fiscal artifact. PDFs are proxy-rendered sidecars,
not original/signed RCH PDFs.

## Parser commit and intermediate visibility

Parser-owned output files are written through same-directory atomic replace.
The success commit marker is `.parsed`; consumers requiring a complete Parser
result should ignore `PHARSED` until `.parsed` exists and its `metadata_sha256`
matches `PHARSED/parsed.json`.

| State | Interpretation |
|---|---|
| `.ready`, no Parser marker | eligible/backlogged |
| `.processing` | claimed by one worker; heartbeat active or awaiting stale recovery |
| `.parse_attempts.json` | previous failure has retries remaining |
| `.parse_failed` | terminal Parser failure/quarantine marker |
| `.parsed` | Parser output committed |

`.parsed` does not supersede or modify `.ready`; capture and parse commits are
independent.

## Reparse backups

`commercialrchproxy-reparse --backup-existing` renames an existing `PHARSED`
directory before force parsing:

```text
PHARSED.backup-YYYY-MM-DD_HH.MM.SS.mmm
```

This is a human local-time backup name, not a Unix timestamp. The command
refuses symlinks, active non-stale processing state, destinations outside the
configured root, mismatched code filters, and overwriting a backup. It snapshots
capture hashes before/after reparse and raises an error if immutable evidence
changed.

## Permissions and retention

Default modes are:

- directories: `0750`;
- files: `0640`;
- process umask: `0027`;
- dedicated non-root user/group from shared configuration.

Other-user permission bits and executable capture-file modes are rejected.
`RETENTION_DAYS=0` means no deletion; 0.3.0 does not implement automatic spool
pruning even when a nonzero value is configured. Back up and retain evidence
under the site's privacy, fiscal, and incident-response policy.

Never commit production RAW, response RAW, timelines, manifests, PDFs, or
hashes. They can contain business, personal, network, and fiscal information.
