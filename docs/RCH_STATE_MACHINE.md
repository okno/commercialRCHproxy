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
| OPAQUE_SESSION | INFERRED | Application bytes exist but no framing rule is confirmed |
| CANDIDATE_REQUEST_BYTES | OBSERVED | One or more literal client-to-printer byte ranges were captured |
| CANDIDATE_RESPONSE_BYTES | OBSERVED | One or more literal printer-to-client byte ranges were captured |
| GENERIC_XML_CANDIDATE | INFERRED | A copied byte range was selected heuristically for generic-XML inspection; this does not identify XML7 |
| ANALYSIS_PENDING | INFERRED | Passive worker has not completed |
| ANALYSIS_BEST_EFFORT | INFERRED | Technical candidate output was produced without protocol authority; production PULITO/PDF human content remains unavailable |
| ANALYSIS_UNCONFIRMED | INFERRED | No documented/observed semantic boundary was found |

[INFERRED] A socket read is an observation chunk, not an application frame.

[INFERRED] Candidate request and response bytes may interleave in time and must retain independent direction-specific offsets.

[INFERRED] Passive-analysis failure must not alter forwarding state.

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
| Is the actual port-23 transport TCP? | UNCONFIRMED |
| Is the connection raw or Telnet-aware? | UNCONFIRMED |
| Does the management system keep one connection open? | UNCONFIRMED |
| Can several documents share one connection? | UNCONFIRMED |
| Can Print! F send unsolicited status? | UNCONFIRMED |
| Can responses arrive after client input closes? | UNCONFIRMED |
| Does a final response close the connection? | UNCONFIRMED |
| Does idle time separate documents? | UNCONFIRMED |
| Does XML delimit a complete job? | UNCONFIRMED |

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
| request_frames/response_frames | UNCONFIRMED; null until FRAME-1 |
| document_type | UNCONFIRMED; `null` until authoritative classifier gate |
| candidate_printed_class / candidate_observed_variant | INFERRED heuristic labels only; nullable and non-authoritative |
| protocol_status | UNCONFIRMED; `null` |
| printer_status | UNCONFIRMED; `null` |
| application_success | UNCONFIRMED; `null`, never inferred from transport closure |
| job_boundary_source / job_boundary_confidence | INFERRED fallback segmentation metadata; not official RCH job markers |

## Current verdict

[OBSERVED] No direct or proxied Print! F PCAP exists in this workspace.

[UNCONFIRMED] No official application state diagram is anonymously accessible.

[INFERRED] The implemented state machine is transport-scoped and semantically opaque, and it passes opaque TCP fixture tests. Installed-device transport compatibility, end-to-end byte preservation, and production safety remain `UNCONFIRMED` until NET-2 and C-4 pass.
