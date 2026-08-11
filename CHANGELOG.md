# Changelog

All notable changes follow Semantic Versioning.

## [0.1.0] - 2026-08-11

### Added

- Independent `commercialRCHproxy` Python project.
- Opaque full-duplex TCP relay hypothesis with half-close and explicitly incomplete response-tail timeout handling.
- Directional local capture, SHA-256, atomic sidecars, and forensic JSON without claiming remote delivery.
- Conservative XML inspection and evidence-ranked fallback classification.
- Proxy-rendered clean TXT/PDF sidecars separated from possible RCH originals; production human content remains empty until an authoritative mapping exists.
- Structured logging, metrics counters, systemd hardening, and Debian operations scripts.
- Automated transport, storage, XML-security, classification, and rendering tests.
- Official-source, photo, architecture, security, operations, and acceptance documentation.

### Known acceptance gates

- Current authenticated RCH Print! F protocol body is not available in this environment.
- No direct/proxy PCAP or real Print! F transaction was performed.
- RCH framing, XML7 wire schema, job boundaries, statuses, errors, and PaDES retrieval remain unconfirmed.
