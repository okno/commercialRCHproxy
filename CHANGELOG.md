# Changelog

All notable changes follow Semantic Versioning.

## [0.2.0] - 2026-08-11

### Added

- Incremental, segmentation-independent parsing of the capture-confirmed RCH
  STX/ETX frame, decimal length, sequence byte, standalone ACK and XOR BCC.
- Evidence-labelled commercial and management document state machines with
  source offsets, request/response correlation, structured JSON and readable
  receipt output.
- Machine-readable receive timeline and offline `commercialrchproxy-inspect`
  utility for grouping legacy segments by session and producing per-document
  forensic directories.
- Structurally equivalent anonymized 77-frame/39-ACK fixtures, golden receipts,
  malformed-stream tests, multi-document tests and arbitrary TCP segmentation
  tests.

### Fixed

- An ACK no longer causes the one-second idle fallback to archive a request
  before its delayed framed response. Candidate open documents, pending
  response frames and partial frames keep the capture window extended.
- Unexpected parser failures can no longer prevent RAW publication and an
  explicit forensic manifest; parsing remains a fail-open sidecar operation.
- Recorder hints reject invalid BCC/profile frames, stay open through the
  commercial postlude, and use bounded queues/history/work per receive call.
- Counter suffixes now require the correlated post-payment query; a previous
  or mismatched response cannot become the current document number.
- Inspector manifest paths are containment-checked, inputs/diagnostics are
  bounded, incomplete captures are warned, and existing forensic output is
  never silently overwritten.
- Framing diagnostics, offline archive aggregation and attacker-amplifiable
  semantic fields now have independent hard bounds with explicit limit issues.
- Directional RAW, timeline and manifest settings are mandatory; timeline
  event metadata is capped independently without truncating captured RAW.

### Evidence limits

- Command roles, document lifecycle and response-sequence meaning are
  reverse-engineered `INFERRED` behavior, not authenticated RCH semantics.
- Printer-generated headers, legal headings, full fiscal identifiers and
  footer data absent from captured request bytes are not synthesized.

## [0.1.0] - 2026-08-11

### Added

- Independent `commercialRCHproxy` Python project.
- Opaque full-duplex TCP relay hypothesis with half-close and explicitly incomplete response-tail timeout handling.
- Directional local capture, SHA-256, atomic sidecars, and forensic JSON without claiming remote delivery.
- Conservative XML inspection and evidence-ranked fallback classification.
- Proxy-rendered clean TXT/PDF sidecars separated from possible RCH originals; production human content remains empty until an authoritative mapping exists.
- Structured logging, metrics counters, systemd hardening, and Debian operations scripts.
- Explicit, reversible secondary-IPv4 helper with route/prefix validation, ARP duplicate detection, ownership state, and a separately hardened systemd unit.
- Automated transport, storage, XML-security, classification, and rendering tests.
- Official-source, photo, architecture, security, operations, and acceptance documentation.

### Known acceptance gates

- Current authenticated RCH Print! F protocol body is not available in this environment.
- No direct/proxy PCAP or real Print! F transaction was performed.
- RCH framing, XML7 wire schema, job boundaries, statuses, errors, and PaDES retrieval remain unconfirmed.
