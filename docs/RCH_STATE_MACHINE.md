# RCH session and job state assessment

[OBSERVED] Evidence cut-off: 2026-08-11.

## Boundary between transport and fiscal state

[DOCUMENTED] RCH XTools demonstrates that a Print! F RCH protocol command can have a response.

[UNCONFIRMED] Accessible RCH documentation does not expose the Print! F connection lifecycle, framing, intermediate states, final status or fiscal job lifecycle.

[INFERRED] The proxy may track transport events that it directly observes. It must not translate those events into fiscal success or document completion.

[UNCONFIRMED] TCP is the current implementation transport, not an RCH-documented installed-device fact; NET-2 must identify the actual IP transport before deployment.

## Transport/session states

[INFERRED] The following states are engineering states, not official RCH protocol states.

| State | Status | Entry evidence | Permitted meaning |
|---|---|---|---|
| ACCEPTED | INFERRED | Client-side connection accepted by the relay | A local transport endpoint exists |
| CONNECTING_PRINTER | INFERRED | Relay attempts the configured upstream endpoint | Upstream result pending |
| FORWARDING | INFERRED | Both relay endpoints exist and byte pumps are active | Local reads/writes may proceed independently in both directions; peer receipt is not established |
| DRAINING_RESPONSE | INFERRED | Either byte pump ended while the opposite pump remains active | Preserve the opposite direction for a bounded tail; the name does not assert an RCH response state |
| CLOSED | INFERRED | Both directions closed and pending local writes drained | Local implementation session ended; end-to-end delivery and fiscal result remain unknown |
| PRINTER_UNREACHABLE | INFERRED | Upstream connection attempt failed | Transport failure only |
| TRANSPORT_ERROR | INFERRED | Read/write/connection exception observed | Transport failure only |

## Permitted transport transitions

| From | Event | To | Status |
|---|---|---|---|
| ACCEPTED | Begin configured upstream connection | CONNECTING_PRINTER | INFERRED |
| CONNECTING_PRINTER | Upstream endpoint established | FORWARDING | INFERRED |
| CONNECTING_PRINTER | Attempt fails | PRINTER_UNREACHABLE | INFERRED |
| FORWARDING | Either pump ends while the opposite pump remains active | DRAINING_RESPONSE | INFERRED |
| FORWARDING | Transport exception | TRANSPORT_ERROR | INFERRED |
| DRAINING_RESPONSE | Opposite pump ends and local writes have drained | CLOSED | INFERRED |
| DRAINING_RESPONSE | Configured tail timeout expires | TRANSPORT_ERROR | INFERRED; recorded as incomplete |
| Any nonterminal state | Unrecoverable transport exception | TRANSPORT_ERROR | INFERRED |

[INFERRED] One direction closing must not immediately discard buffered or later-arriving bytes from the other direction.

[INFERRED] The relay must not send application ACK, NAK, OK, retry, cancel or synthetic status in any state.

[INFERRED] A transport timeout may end a stalled relay session according to configuration, but must be recorded as transport timeout rather than document completion.

## Opaque application observation states

[INFERRED] The following labels are deliberately non-semantic.

| State | Status | Meaning |
|---|---|---|
| OPAQUE_SESSION | INFERRED | Application bytes exist but do not match the capture-confirmed profile |
| CANDIDATE_REQUEST_BYTES | OBSERVED | One or more literal client-to-printer byte ranges were captured |
| CANDIDATE_RESPONSE_BYTES | OBSERVED | One or more literal printer-to-client byte ranges were captured |
| FRAMED_STREAM | CONFIRMED | One or more complete frames satisfy observed delimiters, length and XOR BCC |
| STANDALONE_ACK | CONFIRMED | Byte `0x06` occurred outside a frame; its application meaning remains unknown |
| DOCUMENT_CANDIDATE_OPEN | INFERRED | A correlated opening command pattern was observed; this is not an official fiscal state |
| DOCUMENT_CANDIDATE_COMPLETE | INFERRED | The corresponding inferred close pattern was captured; printer/fiscal result remains unknown |
| GENERIC_XML_CANDIDATE | INFERRED | A copied byte range was selected heuristically for generic-XML inspection; this does not identify XML7 |
| ANALYSIS_PENDING | INFERRED | Passive worker has not completed |
| ANALYSIS_BEST_EFFORT | INFERRED | Technical and captured-field human output was produced without claiming official command authority |
| ANALYSIS_UNCONFIRMED | INFERRED | No documented/observed semantic boundary was found |

[INFERRED] A socket read is an observation chunk, not an application frame.

[INFERRED] Candidate request and response bytes may interleave in time and must retain independent direction-specific offsets.

[INFERRED] Passive-analysis failure must not alter forwarding state.

## Inferred document-assembly states

`DocumentAssemblyState` is a reconstruction state machine, not an official RCH
or fiscal state machine. Frame boundaries and literal command bytes are
`CONFIRMED`; every transition meaning below is `INFERRED`.

| State | Entry candidate | Exit candidate | Output meaning |
|---|---|---|---|
| `idle` | No active recognized lifecycle | `=K` after an optional `<</?s`, or first `=o` | No document candidate is open |
| `commercial_body` | `=K` | total-like `=T...` | Item and free-text candidates accumulate |
| `commercial_payment` | total-like `=T...` | following commercial control sequence | Total and generic payment-amount candidate captured; method remains null |
| `commercial_postlude` | `<</?s` while a commercial payment candidate is active | exact `<</?7` | Auxiliary/control tail is retained without becoming receipt body |
| `management_body` | first `=o` | paired `=o` | Printable management lines accumulate |
| `complete` | inferred commercial or management close | terminal for that candidate | Request lifecycle captured; fiscal/printer result remains unknown |
| `incomplete` | EOF/fallback with an active candidate | terminal for that candidate | Partial fields and raw evidence retained with an issue |

The parser records every transition with source frame ID/offset in
`document_state_transitions` and the final state in document metadata. It then
returns to `idle`, allowing another document in the same application stream.
Display-only exchanges and unknown commands never open a document by
themselves.

## Fiscal/job states not yet permitted

| Proposed semantic state | Status | Missing gate |
|---|---|---|
| DOCUMENT_OPEN | UNCONFIRMED | DOC-1, FRAME-1 and JOB-1 |
| ITEMS_IN_PROGRESS | UNCONFIRMED | Official command/XML field mapping |
| PAYMENT_IN_PROGRESS | UNCONFIRMED | Official payment semantics and capture |
| DOCUMENT_CLOSE_SENT | UNCONFIRMED | Official close command |
| WAITING_FINAL_STATUS | UNCONFIRMED | Official flow and response correlation |
| DOCUMENT_COMPLETED | UNCONFIRMED | Official final-success evidence plus JOB-1 |
| DOCUMENT_REJECTED | UNCONFIRMED | Official error/status mapping |
| PAPER_OUT | UNCONFIRMED | Authenticated paper-out chapter plus ERR-1 |
| PRINTER_BUSY | UNCONFIRMED | Official status definition plus observation |
| FISCAL_ERROR | UNCONFIRMED | Official error definition plus observation |
| PDF_ORIGINAL_RECEIVED | UNCONFIRMED | PADES-1 |

[INFERRED] These names may appear only in design notes until their gates pass; persisted manifests must use null or unknown rather than asserting them.

## Session lifecycle questions

| Question | Status |
|---|---|
| Is the supplied proxy run represented as TCP sessions? | CONFIRMED by capture metadata |
| Is TCP an official/general Print! F transport property? | UNCONFIRMED |
| Is the connection raw or Telnet-aware? | UNCONFIRMED |
| Does the management system keep one connection open? | UNCONFIRMED |
| Can several documents share one connection? | UNCONFIRMED |
| Can Print! F send unsolicited status? | UNCONFIRMED |
| Can responses arrive after client input closes? | UNCONFIRMED |
| Does a final response close the connection? | UNCONFIRMED |
| Does idle time separate documents? | CONFIRMED false in the supplied commercial case; general timing remains UNCONFIRMED |
| Does XML delimit either supplied job? | CONFIRMED no; other workflows remain UNCONFIRMED |

## State-machine acceptance gates

### SM-1 — transport observation

- [UNCONFIRMED] Complete NET-1 and NET-2 from RCH_PROTOCOL_ASSESSMENT.md; if TCP is not observed, stop because the current implementation transport is incompatible with that evidence.
- [UNCONFIRMED] Observe establishment, both directions, idle periods, orderly closure, reset and at least one upstream connection failure in a non-fiscal test.
- [INFERRED] Acceptance requires transitions to be derived from packet/socket evidence without naming application semantics.

### SM-2 — half-close

- [UNCONFIRMED] Test client-first and printer-first half-close with a fake upstream.
- [UNCONFIRMED] Compare a real direct capture for whether either behavior occurs on Print! F.
- [INFERRED] Acceptance requires all already-received bytes to drain and no fabricated bytes.

### SM-3 — request/response

- [UNCONFIRMED] Complete FLOW-1 with at least three repetitions of the same controlled action.
- [UNCONFIRMED] Determine immediate, delayed and unsolicited response behavior.
- [INFERRED] Acceptance requires direction/timing correlations with no unexplained bytes.

### SM-4 — job lifecycle

- [UNCONFIRMED] Complete FRAME-1 and JOB-1 for at least three repetitions each of CASE-G1, CASE-C1 and CASE-G2 from RCH_PROTOCOL_ASSESSMENT.md.
- [UNCONFIRMED] Prove start, close and final outcome markers from official RCH sections and captures.
- [INFERRED] Acceptance requires correct handling of two back-to-back jobs and fragmented/coalesced delivery.

### SM-5 — errors

- [UNCONFIRMED] Complete ERR-1 from naturally occurring evidence where possible; induce an error only through an RCH/dealer-approved, non-destructive test.
- [UNCONFIRMED] Establish whether recovery stays in the same connection, starts a new connection or needs an operator action.
- [INFERRED] Acceptance requires byte-transparent behavior and exact official error meaning.

## Manifest rules

| Field | Status before semantic gates |
|---|---|
| transport_status | INFERRED summary derived from observed local socket/pump events; never a fiscal result |
| bytes_read_from_client / bytes_read_from_printer | OBSERVED local stream-read counts |
| bytes_stored_request / bytes_stored_response | OBSERVED locally archived byte counts |
| bytes_local_write_drain_to_printer / bytes_local_write_drain_to_client | OBSERVED local writer-drain counts; not peer receipt |
| bytes_arrived_at_printer / bytes_arrived_at_client | UNCONFIRMED end-to-end delivery; `null` until C-4 evidence supports it |
| timestamp_start / timestamp_end | OBSERVED local capture-segment timestamps; not official RCH session/job markers |
| capture_error | OBSERVED local capture error text when present; otherwise `null` |
| request_frames/response_frames | CONFIRMED structural counts when observed framing succeeds; null only after parser failure |
| response_ack_count | CONFIRMED count of standalone `0x06` events; not success |
| document_type | INFERRED `commerciale`/`gestionale` for a recognized observed lifecycle; otherwise `null` |
| documents | INFERRED candidate summaries with completeness and CONFIRMED source frame ranges |
| candidate_printed_class / candidate_observed_variant | INFERRED heuristic labels only; nullable and non-authoritative |
| protocol_status | UNCONFIRMED; `null` |
| printer_status | UNCONFIRMED; `null` |
| application_success | UNCONFIRMED; `null`, never inferred from transport closure |
| job_boundary_source / job_boundary_confidence | INFERRED fallback segmentation metadata; not official RCH job markers |

## Current verdict

[CONFIRMED] Private proxy-generated directional stream copies and correlated
photos exist for the two supplied cases; no direct/proxy PCAP comparison
exists.

[UNCONFIRMED] No official application state diagram is anonymously accessible.

[INFERRED] The implementation combines transport states, capture-confirmed
framing and a separate candidate document state machine. Candidate completion
must never be promoted to the prohibited fiscal states above. Installed-device
byte transparency and production safety remain `UNCONFIRMED` until NET-2 and
C-4 pass.
