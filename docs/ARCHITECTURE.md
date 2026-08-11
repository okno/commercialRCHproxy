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

The two pumps are independent coroutines. Relay writes and bounded capture bookkeeping are kept separate from semantic analysis; captured data is never transformed and fed back into the relay path. Generic-XML inspection, hashing, disk publication, and rendering run outside the forwarding pump.

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
- timestamp, direction, and per-direction stream offset for each copied chunk.

A completed local writer drain is not proof that the peer application accepted, processed, printed, or persisted the bytes. End-to-end byte delivery remains `UNCONFIRMED` until PCAP comparison and application/physical acceptance pass C-4.

No protocol-native document boundary is known. The current fallback:

- waits up to `RESPONSE_TIMEOUT_SEC` for the first response after request activity;
- after response activity, finalizes on `JOB_IDLE_TIMEOUT_MS` of bidirectional silence;
- finalizes any remaining copy at connection close.

Every manifest labels this as `fallback_inactivity` or `fallback_connection_close` with confidence at or below `0.20`. It is not suitable for fiscal conclusions. Persistent connections are supported and can yield multiple fallback jobs, but authenticated framing/job rules must replace the fallback after PCAP validation.

## Passive protocol intelligence

The passive analyzer has four independent results:

- implementation transport: TCP stream, with detected installed-device transport `null` and evidence `UNCONFIRMED` pending NET-2;
- framing: `confirmed=false`;
- secure generic-XML candidate copy: candidate offsets, generic well-formedness, literal root QName/local name and leaf paths, with `xml7_confirmed=false`;
- document classification: authoritative `document_type=null`; heuristics can emit only low-confidence `candidate_printed_class` and `candidate_observed_variant`.

The response analyzer always returns both application success and protocol status as `null` in `0.1.0`. Error and command dictionaries are intentionally empty.

## Intermediate document model

```text
captured request copy
        |
        +--> technical byte/candidate-XML inspection
        |
        +--> authoritative RCH field mapping (not available in 0.1.0)
                         |
                    DocumentModel
                     /       \
               clean         PDF_PROXY_RENDERED
          empty/unavailable   empty/unavailable
```

`DocumentModel` supports trace fields for byte offset, frame number, and XML path. Frame numbers remain `null` until framing is proven. Because no authoritative RCH-to-field mapping is available, production PULITO/PDF human content is intentionally empty/unavailable in 0.1.0. Photo-derived models are test fixtures for layout only. No absent tax, amount, document number, date, or fiscal field is invented.

## Storage

Artifacts are written to a random same-directory temporary name, flushed with `fsync`, chmodded, and atomically replaced. The containing directory is also flushed where supported. Application-controlled directory levels reject symlinks. JSON is written last so its presence means sidecar publication was attempted and its `render_errors` list is authoritative.

`MAX_PAYLOAD_BYTES` prevents unbounded capture memory. Forwarding continues if the cap is crossed, but `raw_complete=false`, `status=capture_incomplete`, and the error are recorded. A partial RAW must never be presented as byte-complete evidence.

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
- Protocol-aware frame/ACK/error decoder without evidence.
- Automatic/service-runtime interface or VIP changes. The optional operator-invoked secondary-address helper is a separate root oneshot service; the proxy process never receives its capabilities.
- Embedded PCAP capture.
- Database or remote upload.
