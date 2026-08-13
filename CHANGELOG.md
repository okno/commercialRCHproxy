# Changelog

All notable changes follow Semantic Versioning.

## [0.3.0] - 2026-08-13

### Added

- Independent `commercialrchproxy-dumper` and `commercialrchproxy-parser`
  processes using one shared configuration and only a persistent filesystem
  spool for coordination.
- Connection-scoped, full-duplex RAW capture with separate request/response
  files, nanosecond-form Unix filenames, per-receive timeline metadata, an
  integrity manifest, and atomic `.ready` publication.
- Persistent, locked, per-printer `CODICE_DOC` allocation with configurable
  start/minimum width and no destructive rollover at four digits.
- Parser backlog scanning, optional Linux inotify wake-ups with unconditional
  polling fallback, configurable concurrency/retries, exclusive processing
  markers, stale-claim recovery, terminal parse-failure markers, and
  idempotent `.parsed` completion.
- Literal `PHARSED` output containing one human-named TXT/PDF pair per
  reconstructed semantic document and a `parsed.json` evidence record.
- Evidence-gated C/G classification and management subtype candidates for
  command, pre-account, conforming copy, and conservative generic management
  output.
- Separate hardened systemd units, component logs, and a legacy no-op launcher
  for the former service name.
- Offline dump inspection alias, network-free RAW-to-spool import, and safe
  reparse with dry-run, code filter, immutable-input verification, and optional
  human-timestamped `PHARSED` backup.
- Architecture, spool, dump, protocol, state-machine, evidence-correlation,
  migration, residual-limit, and updated test documentation.

### Changed

- One transport connection now creates one capture job. Semantic splitting is
  deferred to the independent Parser; neither a TCP `recv()` nor an idle pause
  is treated as a document boundary.
- The Dumper no longer imports document parsing or rendering code and never
  waits for TXT/PDF generation before relaying bytes.
- The storage layout is now
  `<printer>/YYYY/MM/DD/<CODICE_DOC>/`; Unix timestamps are confined to RAW
  filenames and technical metadata, while parsed names use configured local
  `HH.MM.SS.mmm` time with deterministic `_NN` collision suffixes.
- The existing strict `KEY=VALUE` configuration remains shared and compatible,
  with new durable-spool, identity, permission, counter, concurrency, watcher,
  and storage-failure controls.

### Evidence correction

- The newly supplied private artifact set contains exactly one partial
  235-byte request/202-byte response capture with 10 request frames, 9 response
  frames, and 10 standalone ACK events; all complete frames pass the observed
  length/BCC checks.
- That single capture supports one incomplete commercial candidate. It is not
  four captures and cannot byte-verify the separately photographed command,
  pre-account, and conforming-copy documents.
- Photographs remain ground truth for comparison only and are never Parser
  input. Private identities, values, endpoints, timestamps, hashes, RAW, and
  photographs remain outside the repository.

### Migration notes

- 0.2 parsed sidecars are not silently rewritten into the new spool contract.
  Preserve the old archive and import selected directional RAW explicitly with
  the offline replay tool.
- Rolling back application code does not convert 0.3 jobs to the 0.2 layout.
  Captured traffic is never automatically replayed to the fiscal device.

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
