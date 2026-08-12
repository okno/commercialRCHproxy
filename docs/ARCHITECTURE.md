# Architecture

## Scope

`commercialRCHproxy` currently terminates two separate TCP connections and is designed to copy application bytes between them. TCP is an `UNCONFIRMED` implementation hypothesis for the installed Print! F pending NET-2. Application-byte transparency is likewise an acceptance target pending the direct-versus-proxy C-4 comparison, not a production claim. The design can never be a layer-2/3 transparent bridge: source IPs, packet metadata, packet boundaries, and timing necessarily change.

The physical RCH Print! F remains the only fiscal/RT device. The proxy cannot declare a document valid, memorized, transmitted, or printed without a documented/observed RCH response interpretation.

## Data path

```text
                     passive copies only
                  +------------------------+
                  | capture/job coordinator|
                  +------------+-----------+
                               |
Gestionale --implemented TCP--> pump C->RCH +--implemented TCP--> RCH Print! F
Gestionale <--implemented TCP-- pump RCH->C +<--implemented TCP-- RCH Print! F
                               |
                        background archive
                         RAW/TXT/PDF/JSON
```

The two pumps are independent coroutines. Each opaque `writer.write()` is
queued before bounded capture/boundary-hint bookkeeping; captured data is
never transformed and fed back into the relay path. Generic-XML inspection,
semantic reconstruction, hashing, disk publication, and rendering run outside
the forwarding pump.

Implementation receive-call boundaries are never treated as RCH frames or protocol evidence.

## Connection lifecycle

1. Accept the management connection.
2. Open the configured printer endpoint before reading application payload.
3. Start both opaque pumps.
4. On EOF in one direction, attempt `write_eof()` toward the other endpoint.
5. Keep the opposite direction alive for `RESPONSE_TIMEOUT_SEC` so a late tail response can return.
6. Close both writers and finalize any active capture copy.

If the printer connection fails, the client is closed/reset without a generated payload. The proxy does not send `OK`, ACK, NAK, or a fiscal error substitute.

`RESPONSE_TIMEOUT_SEC` is an operational bound, not a protocol fact. It must be calibrated from direct captures; a value that is too low can truncate late responses, while an unbounded value can pin sessions indefinitely.

An in-process exclusive lock permits only one active upstream connection to the configured device endpoint. Additional accepted clients wait without application-level stream consumption until the active upstream session closes. This limits accidental concurrent fiscal-device sessions; it is not an authorization boundary, so network ACLs remain required.

## Capture and job fallback

An active capture records local observations:

- client-side bytes received by the relay, up to `MAX_PAYLOAD_BYTES`;
- configured-upstream-side bytes received by the relay, within the same bound;
- wall-clock/monotonic timestamp, direction, ordered event number, job offset
  and session-relative directional offset for each copied chunk.

Receive-event metadata has a hard count ceiling. Crossing it leaves the
directional RAW intact, marks `timeline_complete=false`, and records why the
JSONL timeline is partial.

A completed local writer drain is not proof that the peer application accepted, processed, printed, or persisted the bytes. End-to-end byte delivery remains `UNCONFIRMED` until PCAP comparison and application/physical acceptance pass C-4.

No authenticated protocol-native document boundary is known. Capture-confirmed
envelopes and inferred lifecycle hints now prevent the known one-second split:

- keeps an incremental directional envelope tracker across receive chunks;
- tracks pending framed responses by the sequence relationship observed in the
  private corpus; standalone ACK does not complete that queue;
- tracks a lightweight commercial/management candidate and any partial frame;
- accepts only BCC-valid observed `00/z` request and `01/N` response profiles
  for those non-authoritative hints;
- bounds hint queues/history and skips hint parsing for oversized read chunks;
- uses the short `JOB_IDLE_TIMEOUT_MS` only when none of those states is pending;
- otherwise waits `RESPONSE_TIMEOUT_SEC + JOB_IDLE_TIMEOUT_MS`;
- finalizes any remaining copy at connection close.

Normal fallback manifests remain `fallback_inactivity` or
`fallback_connection_close` with confidence at or below `0.20`. A response
that arrives only after an already-published timeout segment is preserved in
an `orphan_late_response` segment with confidence `0.10`. These are storage
boundaries, not fiscal conclusions. Tracker failure is fail-open for opaque
forwarding and capture.

## Passive protocol intelligence

The passive analyzer has four independent results:

- implementation transport: TCP stream, with detected installed-device transport `null` and evidence `UNCONFIRMED` pending NET-2;
- framing: capture-confirmed delimiter, decimal data length, sequence position
  and XOR BCC, with exact frame/issue offsets;
- standalone `0x06` ACK events separate from framed printer responses;
- secure generic-XML candidate copy: candidate offsets, generic well-formedness, literal root QName/local name and leaf paths, with `xml7_confirmed=false`;
- evidence-labelled receipt reconstruction: `document_type` is an `INFERRED`
  command-sequence classification (`commerciale` or `gestionale`) only when a
  correlated observed lifecycle is present; unknown streams remain null.

The response analyzer still returns application success, printer status and
protocol/error meaning as null. The official command/error dictionaries remain
empty; receipt roles are isolated reverse-engineering rules, not official RCH
definitions.

Live semantic reconstruction operates on each archived fallback job. The
session-scoped recorder hints prevent the observed 1.37-second split, while
the offline inspector groups immutable jobs by exact `session_id` when a
document still spans an extended fallback boundary.

## Intermediate document model

```text
directional request/response copies
        |
        +--> incremental framing + ACK events + issues
        |
        +--> inferred command/document state (request only)
        |              |
        |         DocumentModel(s)
        |          /      |       \
        |   receipt.txt parsed.json PDF_PROXY_RENDERED
        |
        `--> response events/metadata (never receipt body)
```

`DocumentModel` supports trace fields for byte offset, frame number and XML
path. Recognized observed command families populate only literal fields present
in request `DATA`; every semantic role is `INFERRED`. Unsupported streams stay
empty, and absent tax, payment, merchant, date, counter or fiscal fields are
never created. Photos validate captured values but never supply model data.

## Storage

Artifacts are written to a random same-directory temporary name, flushed with
`fsync`, chmodded, and atomically replaced. The containing directory is also
flushed where supported. Application-controlled directory levels reject
symlinks. Directional RAW and the JSONL receive timeline are attempted before
semantic parsing; parsed JSON, human text and PDF are derived sidecars. The
manifest JSON is written last so its presence means sidecar publication was
attempted and its `render_errors` list is authoritative.

`MAX_PAYLOAD_BYTES` prevents unbounded capture memory. Forwarding continues if
the cap is crossed, but `raw_complete=false`, `status=capture_incomplete`, and
the error are recorded. A separate capture-event ceiling bounds timeline
objects. Semantic analysis has lower byte/event/message/issue/document caps so
hostile input falls back to partial diagnostics without changing RAW. A
partial RAW must never be presented as byte-complete evidence.

## Failure isolation

- Parser failure: do not intentionally alter the relay path; record parser/render error if storage remains available. Installed-device byte equality remains subject to C-4.
- TXT/PDF failure: forward unchanged; publish other artifacts and manifest error.
- Capture limit: forward unchanged; explicitly mark partial archive.
- Disk/archive failure: forward unchanged when transport is still viable; emit structured `capture_segment_archive_failed`.
- Printer connect failure: no false response; structured `printer_unreachable`.
- Reverse channel failure: no false application success.

## Deliberately absent

- ESC/POS parsing or rendering.
- Synthetic status/test-print commands.
- Store-forward, retry, or replay.
- Official response/error or fiscal-success decoder; only observed framing and
  standalone ACK presence are decoded.
- Automatic/service-runtime interface or VIP changes. The optional operator-invoked secondary-address helper is a separate root oneshot service; the proxy process never receives its capabilities.
- Embedded PCAP capture.
- Database or remote upload.
