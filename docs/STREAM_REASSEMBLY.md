# Stream reassembly

This document separates three boundaries that the old output conflated:

```text
TCP receive chunk != protocol frame != logical document
```

The first is an implementation observation, the second is byte-framed, and
the third depends on an evidence-labelled command lifecycle.

## Required invariants

- [`CONFIRMED`] Bytes are forwarded before passive interpretation; the parser
  reads a copy and never rewrites the relay stream.
- [`CONFIRMED`] Client-to-printer and printer-to-client streams have separate
  offsets and separate incremental framers.
- [`CONFIRMED`] Directional recorder/framer hints are per connection/session,
  never global. Live semantic rendering remains per archived fallback job;
  the offline inspector performs full same-session cross-job reconstruction.
- [`CONFIRMED`] Any input chunking must produce the same ordered frame events:

  ```text
  parse(stream)
  == parse(split(stream, one_byte))
  == parse(split(stream, fixed_or_random_chunks))
  == parse(one_coalesced_chunk)
  ```

- [`INFERRED`] Logical document state may span a short idle interval. The
  recorder therefore delays its fallback while an observed response,
  candidate document or partial frame is pending. A fallback that still fires
  is not fiscal completion.
- [`UNKNOWN`] Whether the deployed application sends multiple complete
  documents over one TCP connection. The implementation must permit it even
  though the private corpus does not demonstrate it.

## Directional reconstruction

Each copied connection is represented conceptually as:

```text
session
|-- client_to_printer
|   |-- immutable byte stream
|   |-- incremental framer
|   `-- session-relative offsets
|-- printer_to_client
|   |-- immutable byte stream
|   |-- incremental framer
|   `-- session-relative offsets
`-- logical document assembler
```

`CapturedChunk.offset` locates a byte within the current archived job.
`CapturedChunk.session_offset` locates it within the whole directional session.
The distinction matters when an inactivity fallback produces more than one
archive job from the same connection.

The receive timeline records, for each observation:

- high-precision wall-clock timestamp;
- monotonic timestamp used for ordering and elapsed-time analysis;
- direction and sequence number;
- job-relative and session-relative offsets;
- byte count and per-chunk SHA-256;
- whether the local writer `drain()` completed;
- `remote_arrival=null`, because local drain is not peer acceptance.

The JSONL timeline points back to the directional RAW files rather than
duplicating their payload. The RAW files remain the immutable source of truth.

## Incremental framing algorithm

`commercialrchproxy.rch.framing.RCHStreamFramer` implements the
capture-confirmed frame shape described in
[RCH_PROTOCOL_ANALYSIS.md](RCH_PROTOCOL_ANALYSIS.md).

For every call to `feed(chunk)` it:

1. appends bytes to a bounded private buffer;
2. emits a standalone `AckEvent` for `0x06` outside a frame;
3. seeks `STX` without discarding a possible partial header;
4. validates the two-digit address and three-digit decimal data length;
5. waits until `LLL + 11` bytes are available;
6. validates `ETX` at the declared position;
7. emits an `RCHFrame` with exact raw bytes and source offsets;
8. calculates XOR BCC through the sequence byte and reports a mismatch as a
   `FramingIssue` without silently repairing the frame;
9. resumes at the next byte, allowing multiple frames in one input chunk.

`finish()` (also exposed as `finalize()`) turns retained bytes at a real input
boundary into an explicit truncation issue. It does not invent a terminator.

The convenience function `frame_stream(payload)` applies the same logic to an
already reassembled directional byte string. `build_frame()` exists for
sanitized deterministic tests; it is not used to transform production input.

### Resynchronization and limits

Malformed headers, impossible terminators, unframed bytes, oversize lengths
and BCC errors are retained as typed, bounded diagnostic previews with exact
byte ranges. The parser seeks
the next observed control candidate and continues when safe. Current frame
limits reflect the three-digit length field; they are resource bounds, not
claims about a documented RCH maximum.

The semantic layer additionally caps analyzed bytes (8 MiB per direction by
default), retained events, messages, issues and documents. The recorder keeps
only incremental carry-over history, bounds response hints and receive-event
metadata, and skips non-authoritative hint analysis for oversized read chunks.
All such limits affect diagnostics only: forwarding and the separately bounded
RAW capture remain unchanged and limitations are recorded explicitly.

[`CONFIRMED`] A malformed or unsupported copied stream cannot change bytes
already being relayed. [`INFERRED`] The semantic result may be partial, but the
RAW and issue offsets must remain sufficient for later re-analysis.

## ACK and response association

ACK is a stream event, not a frame and not a document line. Response framing
uses the same structural parser but a separate directional buffer.

The private corpus demonstrates why response association cannot depend on
receive calls or fallback job files:

- an ACK and its framed response can arrive in different reads;
- an ACK can be the last byte of one inactivity archive part while the framed
  response is the first event in the next part;
- there are 39 ACK events and 38 framed responses.

[`UNKNOWN`] The official correlation rule between request sequence, ACK and
response fields is unavailable. The implementation preserves ordering and
offsets, but it must not assert application or fiscal success from ACK alone.

## Logical document assembly

The protocol-copy parser exposes:

```python
result = parse_protocol_copies(request_bytes, response_bytes)
result.documents
result.messages
result.correlations
result.issues
```

`messages` retains the frame-level chain of reconstruction. Each parsed
document retains source frame identifiers and byte offsets. `documents` is
ordered by the candidate lifecycle in the client-to-printer stream; response
events are metadata and never receipt body text. `correlations` records
ordinal request/ACK/response candidates and separately checks the inferred
sequence relationship; it does not assert application success.

The lifecycle patterns currently implemented are reverse-engineered and are
therefore labelled `INFERRED`:

```text
IDLE
  |-- commercial start candidate --> COMMERCIAL_BODY
  |       `-- total candidate ------> COMMERCIAL_PAYMENT
  |               `-- tail control -> COMMERCIAL_POSTLUDE
  |                       `-- close -> COMPLETE_CANDIDATE
  `-- management start candidate --> MANAGEMENT_BODY
          `-- close candidate ------> COMPLETE_CANDIDATE
```

An explicit candidate close may complete one document while the TCP
connection remains open. The assembler then returns to `IDLE`, which permits
multiple documents in the same stream. At EOF or a fallback flush, an open
document is returned as incomplete rather than discarded or falsely marked
complete.

### Recorder boundary hint

[`CONFIRMED`] The previous one-second inactivity rule split the supplied
commercial exchange into 168-byte and 106-byte request artifacts in the same
TCP session. The corrected recorder uses small, session-level, directional
envelope trackers only to keep the archive boundary stream-safe; the full
semantic parser remains outside the forwarding path.

The boundary tracker keeps an ordered queue of response sequence candidates.
[`CONFIRMED`] In this corpus the framed response sequence is the request
sequence plus eight modulo ten. [`INFERRED`] This relationship is used only as
a conservative pending-response hint; it is not exposed as an official RCH
rule or an application-success result.

A short idle flush is allowed only when all of the following are false:

- a framed request still has an unmatched framed response candidate;
- the observed commercial candidate is between `=K` and the inferred numeric
  close control (remaining open through total, display and postlude traffic);
- the observed management envelope is open between its paired `=o` commands;
- either directional envelope tracker retains a partial frame.

Otherwise the recorder waits `RESPONSE_TIMEOUT_SEC` plus the configured idle
interval. Standalone ACK does not consume a pending framed response. If a
response arrives only after the extended timeout has already archived the
request, it is still forwarded and stored in a separate segment labelled
`orphan_late_response` with confidence `0.10`; it is not presented as a
standalone receipt.

Every rule above is fail-open for transport: a boundary-tracker exception is
logged, while opaque forwarding and RAW capture continue.

The original per-job artifacts remain valuable evidence and are not deleted.
Continuous session offsets allow old split parts to be correlated offline, but
the live recorder does not silently rewrite or concatenate previously archived
files. If an open candidate outlives `RESPONSE_TIMEOUT_SEC` plus the idle
fallback, live per-job semantic output can still be partial; archive-directory
inspection is the supported cross-job reconstruction path.

### Cross-session policy

Do not concatenate all files by timestamp. A new TCP session is a hard
correlation boundary unless an independently supported workflow says
otherwise. In particular, the four equal display sessions remain four
operations.

[`INFERRED`] A management print may refer to a preceding commercial document,
but it is a separately framed document/session in this corpus. Similar text,
amounts, counters or close timestamps may be recorded as correlation evidence;
they are not authority to merge two raw streams into one document.

## Storage boundary versus protocol boundary

| Event | May archive copied bytes? | May assert document complete? |
|---|---:|---:|
| Valid inferred close pattern | Yes | Candidate completion only; fiscal success remains `UNKNOWN`. |
| One-second inactivity | Yes, as fallback | No. |
| TCP EOF | Yes | No, unless a close pattern already completed the candidate. |
| Parser error or unknown command | Yes | No; mark partial and preserve evidence. |
| ACK alone | Yes | No. |
| Framed printer response | Yes | No until response semantics are documented/validated. |

## Forensic chain

The reconstruction chain is intentionally reversible:

```text
receipt text / structured document
        -> source frame id and DATA offsets
        -> parsed protocol message
        -> session-relative directional byte range
        -> immutable client/printer RAW
        -> capture timeline and hash metadata
```

No stage uses `errors="ignore"`, drops an unknown byte, copies photo-only data
into the model, or feeds decoded content back into the live connection.
