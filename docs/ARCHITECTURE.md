# Architecture

## Scope and trust boundary

Version 0.3.0 is a two-process design:

1. **Dumper**: network relay, directional RAW acquisition, timeline capture,
   durable job publication, and no semantic receipt work.
2. **Parser**: offline validation, framing, document-state reconstruction,
   classification, TXT/PDF rendering, and no relay socket.

They run in separate operating-system processes, share no memory, and read the
same strict configuration. Their only coordination channel is the persistent
filesystem below `OUTPUT_DIR`.

The physical RCH device remains the only fiscal/RT device. A parser result is a
forensic reconstruction candidate, not an assertion that a document was
accepted, printed, memorized, signed, or transmitted.

## Data flow

```text
                                forwarding priority
 management software                                         physical device
          |                                                         |
          | request bytes                                           |
          +---------------> Dumper request pump -------------------->+
          |                                                         |
          | response bytes                                          |
          +<--------------- Dumper response pump <------------------+
                                    |
                                    | append-only directional copy
                                    v
                          hidden .partial job directory
                                    |
                   fsync files -> hashes -> manifest -> .ready
                                    |
                         atomic directory rename/fsync
                                    v
                         persistent immutable spool
                                    |
                     inotify wake-up and/or polling scan
                                    v
                                 Parser
                                    |
                        PHARSED/TXT, PDF, parsed.json
```

The two relay pumps are independent. Each writes received bytes to the
opposite socket in order and records the same directional bytes. Parser code is
not imported into the Dumper process. The Parser neither imports nor invokes
the proxy server and the installed Parser unit is denied IP networking.

## Process independence

| Condition | Dumper behavior | Parser behavior |
|---|---|---|
| Parser stopped | Relay and completed spool publication continue | Backlog remains on disk |
| Parser restarted | No relay action | Deterministic scan consumes old `.ready` jobs |
| Parser render failure | Unaffected | Retry state is recorded; capture evidence remains immutable |
| Dumper stopped | No new relay/capture | Existing ready backlog can still be processed |
| Host restart | Hidden incomplete jobs remain non-ready | Ready jobs are rediscovered; stale claims are recoverable |
| Disk/storage error, default policy | Relay is prioritized; critical error logged | No job exists unless atomic publication completed |

`commercialrchproxy-dumper.service` and
`commercialrchproxy-parser.service` have no `Requires`, `Wants`, `After`, or
`Before` relationship to each other. The compatibility
`commercialrchproxy.service` unit is only an operator convenience that starts
both; it is not an inter-process dependency.

## Dumper responsibilities

The Dumper:

- accepts one configured management-facing TCP connection and opens one
  configured device-facing TCP connection per session;
- relays both directions without payload interpretation or conversion;
- preserves byte order and propagates half-close where supported;
- applies socket backpressure through writer/drain handling;
- records receive, forwarding, and local drain timestamps without asserting
  remote receipt;
- creates at most one capture job per data-bearing transport connection; an
  empty connection produces no job;
- publishes request RAW, response RAW (including a deterministic empty file),
  JSONL timeline, manifest, and `.ready` atomically;
- never creates receipt TXT/PDF and never waits for the Parser.

It does not treat a `recv()` call, TCP packet, idle pause, frame, ACK, or
candidate document close as a capture-directory boundary. The transport
connection lifecycle is the capture boundary. A capture job may later produce
zero, one, or multiple semantic documents.

Forwarding cannot prove remote delivery: successful local `drain()` means only
that the local runtime accepted progress. Arrival, device processing, paper
printing, and fiscal status remain unknown without independent evidence.

## Capture memory and storage failure

`MAX_PAYLOAD_BYTES` bounds the combined retained capture. Timeline metadata is
separately bounded by `MAX_CAPTURE_EVENTS`. When a limit or storage operation
fails, the manifest/partial state must not be represented as complete.

`STORAGE_FAILURE_POLICY` is explicit:

- `continue` (default): prioritize the live relay and emit a critical structured
  log. The remaining or failed partial directory is never promoted to ready.
- `abort`: surface the storage failure to the session after best-effort
  preservation. This policy can interrupt the connection and therefore
  requires site approval.

Neither policy permits truncated bytes to be presented as complete evidence.

## Atomic spool protocol

For each connection the Dumper:

1. allocates a persistent per-printer `CODICE_DOC` under a cross-process lock;
2. creates a hidden, unique `.<code>.<job-id>.partial` directory;
3. writes request, response, and timeline `.partial` files;
4. flushes and `fsync`s file contents;
5. renames artifacts to final names inside the hidden directory;
6. calculates SHA-256 and writes `manifest.json` atomically;
7. writes `.ready`, binding the code and manifest SHA-256;
8. `fsync`s the directory;
9. atomically renames the hidden directory to `<CODICE_DOC>`;
10. `fsync`s the date parent.

The Parser rejects a job if it lacks `.ready`, contains a `.partial` artifact,
has an invalid manifest binding, has an unsafe/symlink path, or has a mismatched
RAW/timeline hash. Abandoned hidden partial directories are preserved for
operator inspection and are never auto-promoted.

See [STORAGE_LAYOUT.md](STORAGE_LAYOUT.md) for the file contract.

## CODICE_DOC strategy

No reliable protocol field in the supplied capture was proven suitable as a
globally unique job-directory key. Version 0.3.0 therefore uses a local
allocator:

- state is separated by sanitized printer identifier;
- `next-code` is durable and atomically replaced;
- `next-code.lock` serializes processes;
- `JOB_CODE_START` selects the first value;
- `JOB_CODE_WIDTH` is a minimum display width of at least four digits;
- codes continue as five or more digits after `9999`; there is no destructive
  rollover;
- an existing destination is never overwritten.

Handwritten photo labels and printer-visible document numbers are never used
as `CODICE_DOC`.

## Parser pipeline

```text
ready capture
  -> commit/hash/path validation
  -> complete directional byte streams
  -> incremental STX/ETX framing and standalone ACK extraction
  -> inferred request/response correlation
  -> inferred document state machines
  -> independent DocumentModel per candidate
  -> C/G and subtype classification
  -> human TXT and matching receipt-style PDF
  -> PHARSED/parsed.json
  -> atomic .parsed marker
```

Framing is segmentation-independent: the same byte stream must produce the
same result when fed whole, byte-by-byte, or in arbitrary chunks. A `recv()`
record remains technical timeline evidence only.

Classification is evidence-gated:

- `C` is an inferred commercial command lifecycle;
- `G` is an inferred management lifecycle;
- management subtypes use observed literal markers and/or same-stream
  structural relationships;
- a management document is considered a conforming-copy candidate only when
  it follows a separate commercial candidate and its captured item/total
  signature matches with supporting payment/tax content, or a corresponding
  literal marker is captured;
- price or total presence alone never makes a document `C`.

Every opener creates a fresh model. Finishing or abandoning a candidate clears
the active builder before the next opener, preventing values from leaking
between pre-account, commercial, and conforming-copy candidates.

The detailed inferred transitions are in
[PARSER_STATE_MACHINE.md](PARSER_STATE_MACHINE.md).

## Parser claims, retries, and recovery

Ready-job discovery is deterministic. A worker uses `.parser.lock` to
serialize claim-state changes and creates `.processing` with exclusive-create
semantics. The marker contains a random token and heartbeat timestamp.

- a live non-stale marker returns `busy`;
- a marker older than `PARSER_STALE_LOCK_SEC` is atomically moved to
  `.processing.stale`, then the job can be reclaimed;
- a worker writes only to its token-private `.PHARSED.<token>.partial`;
- a successful run reacquires `.parser.lock`, proves ownership of the same
  token, revalidates immutable inputs and generated hashes, atomically promotes
  `PHARSED`, writes `.parsed`, and removes `.processing`;
- a stale worker that loses its lease cannot publish or record failure over the
  takeover winner; orphan parser staging is fenced and removed on recovery;
- repeated scans of `.parsed` jobs are no-ops;
- failures update `.parse_attempts.json`;
- after the configured retry budget is exceeded, `.parse_failed` becomes the
  terminal quarantine marker until an operator explicitly reparses;
- force reparse may replace Parser-owned state/output only; capture artifacts
  remain immutable.

Linux inotify only shortens wake-up latency. Directory watches can fail or be
exhausted; periodic polling remains enabled and provides correctness.

## Time model

RAW filenames and technical metadata use integer Unix nanoseconds represented
as `<seconds>.<nine digits>`. This is a representation contract, not a claim
that the platform clock physically measured nanoseconds.

Parsed names use the receive event associated with the candidate's start
offset, converted through configured `TIMEZONE` (default `Europe/Rome`) and
truncated to milliseconds. Unix time does not enter TXT/PDF names or
operator-facing content. Equal millisecond stems receive deterministic `_02`,
`_03`, and later suffixes within the job.

## Security boundaries

- Both services run under the dedicated non-root account and `UMask=0027`.
- Files default to `0640`; directories default to `0750`.
- The Dumper receives only `CAP_NET_BIND_SERVICE`.
- The Parser receives no capabilities and no IP networking.
- Configuration/application paths are read-only in the service mount
  namespace; only job/log roots are writable.
- Final and intermediate symlinks, traversal, unsafe codes, overlarge metadata,
  and manifest/hash mismatches are rejected.
- Receipt payload is excluded from INFO logs; bounded hexdump logging requires
  all explicit debug gates. Structured records use a bounded non-blocking
  in-process queue so a slow file/journal sink never backpressures relay pumps;
  saturation may drop older log records and must be monitored separately.
- Parser output never replaces or edits source RAW.

Systemd specifics are documented in [SYSTEMD.md](SYSTEMD.md); configuration
limits are in [CONFIGURATION.md](CONFIGURATION.md).

## Deliberately absent

- ESC/POS assumptions or conversion.
- Synthetic test-print/status/fiscal commands.
- Network replay or automatic store-and-forward.
- Official response/error/fiscal-success decoding.
- Photo/OCR values as parser input.
- Automatic promotion of crash partials.
- Automatic deletion or retention pruning in 0.3.0.
- Automatic migration or deletion of 0.2 artifacts.
- Embedded PCAP capture, database, or remote upload.
