# RCH Print! F compatibility

[OBSERVED] Evidence cut-off: 2026-08-11.

## Scope

[INFERRED] Compatibility is defined by exact device model, firmware, protocol-manual revision, configured communication profile, transport observation and verified operation.

[INFERRED] Product-family similarity is not sufficient for a compatibility claim.

## Target deployment record

| Attribute | Status | Value |
|---|---|---|
| Requested device | OBSERVED | RCH Print! F |
| Exact hardware revision | UNCONFIRMED | Not supplied |
| Serial identifier | UNCONFIRMED | Not supplied |
| Installed firmware | UNCONFIRMED | Not supplied |
| Management profile | OBSERVED | RCH RT v.10 XML7, as reported by the deployment request |
| Meaning of profile string | UNCONFIRMED | Not defined in accessible official RCH material |
| Printer address | UNCONFIRMED | Public example 192.0.2.251; actual address is private configuration |
| Printer port | OBSERVED | 23, as reported |
| Official port | DOCUMENTED | 23 for Print! F in RCH XTools v4.0.0 §4.1.1 |
| Proxy address | UNCONFIRMED | Public example 192.0.2.231; actual address assignment is not verified |
| Direct PCAP | UNCONFIRMED | Not present |
| Proxy PCAP | UNCONFIRMED | Not present |
| Authenticated protocol manual | UNCONFIRMED | Not present |

## Official device compatibility evidence

| Feature | Status | Applicable evidence | Limitation |
|---|---|---|---|
| Serial connection | DOCUMENTED | Print! F brochure rev.00; XTools v4.0.0 compatibility table | Electrical/settings details beyond XTools UI are not assessed |
| Ethernet connection | DOCUMENTED | Print! F brochure rev.00; XTools v4.0.0 | IP protocol and framing remain unknown |
| Port 23 | DOCUMENTED | XTools v4.0.0 §4.1.1 | Does not imply Telnet or raw TCP |
| XTools device support | DOCUMENTED | Print! F firmware 9.0.2 or later | XTools minimum, not general protocol minimum |
| RCH protocol command sending | DOCUMENTED | XTools v4.0.0 §4.3.10 and compatibility table | Command syntax and response format remain gated |
| Electronic-receipt download through XTools | DOCUMENTED | Marked unavailable for Print! F over serial and Ethernet in XTools v4.0.0 table | No alternate retrieval capability may be inferred |
| PaDES-titled chapter in Print! F manual hierarchy | DOCUMENTED | Official Print! F protocol-manual hierarchy | The title alone does not establish installed availability, retrieval capability, transport format, or signature-validation behavior |
| Corrispettivi XML v.7 chapter | DOCUMENTED | Official Print! F protocol-manual hierarchy | Exact schema/envelope unknown |
| Commands introduced from firmware 8.0.8 | DOCUMENTED | Official chapter title | Hidden command list; no applicability conclusion |

## Rendering-related hardware baseline

| Property | Status | Brochure rev.00 value | Deployment rule |
|---|---|---|---|
| Roll width | DOCUMENTED | 79.5 mm ± 0.5 mm | Verify against installed unit before hard-coding |
| Print resolution | DOCUMENTED | 576 dots/line; 8 dots/mm | Verify hardware revision |
| Character cell | DOCUMENTED | 12 × 24 dots | Does not establish protocol text encoding |
| Characters per line | DOCUMENTED | Up to 48 | Treat as configurable rendering baseline |
| Cutter | DOCUMENTED | Automatic, partial cut | Does not establish a job boundary |
| Barcode/QR support | DOCUMENTED | Multiple 1D formats and QR | Does not establish on-wire commands |

[INFERRED] The 2018-02 rev.00 brochure is adequate for provisional layout defaults only after HW-1 matches the installed device.

## Compatibility status by protocol layer

| Layer | Status | Release position |
|---|---|---|
| Configurable port-23 TCP relay implementation | INFERRED | TCP is an implementation hypothesis; NET-2 must identify the installed-device IP transport |
| Bidirectional byte preservation | INFERRED | Fixture-tested design target; installed-device application-byte equality is `UNCONFIRMED` until C-4 |
| TCP-specific behavior | UNCONFIRMED | Do not claim compatibility until NET-2 observes TCP |
| Telnet behavior | UNCONFIRMED | Do not negotiate or strip Telnet bytes without documentation/observation |
| Application framing | UNCONFIRMED | Passive only |
| Command parser | UNCONFIRMED | No authoritative syntax available |
| Response parser | UNCONFIRMED | No authoritative response layout available |
| Error dictionary | UNCONFIRMED | No Print! F error codes available anonymously |
| XML7 parser | UNCONFIRMED | Generic-XML candidate discovery only; no XML7 root/schema/meaning is asserted |
| Fiscal document classifier | UNCONFIRMED | `document_type` remains `null`; heuristics may emit candidate labels only |
| Job boundary detector | UNCONFIRMED | Idle fallback may not assert completion |
| PaDES original extractor | UNCONFIRMED | Not implemented as a supported capability; requires PADES-1 before any promotion |
| Proxy-rendered PDF | INFERRED | Labeled sidecar only; production human body remains empty/unavailable until authoritative mapping and physical comparison pass |

## Firmware matrix

| Firmware range | Status | Known statement | Project support |
|---|---|---|---|
| Earlier than 8.0.8 | UNCONFIRMED | Official manual has a chapter for commands introduced from 8.0.8 | No semantic compatibility claim |
| 8.0.8 through 9.0.1 | UNCONFIRMED | Command changes exist; XTools v4 minimum is later | No semantic compatibility claim |
| 9.0.2 and later | DOCUMENTED | Supported by XTools v4.0.0 | XTools compatibility only; proxy semantics still require captures |
| Reported v.10 profile/device | OBSERVED | Deployment UI reports RCH RT v.10 XML7 | Exact firmware and protocol meaning unconfirmed |
| Installed firmware | UNCONFIRMED | No device evidence | Release must report unknown until HW-1 |

## Acceptance gates for a supported configuration

### C-1 — identity

- [UNCONFIRMED] Record data plate, model, hardware revision and serial identifier.
- [UNCONFIRMED] Record firmware using an RCH-documented method.
- [INFERRED] Acceptance requires a compatibility entry keyed by model plus firmware, not only Print! F.

### C-2 — official applicability

- [UNCONFIRMED] Obtain the authenticated protocol-manual revision and its firmware applicability.
- [UNCONFIRMED] Resolve whether RCH RT v.10 XML7 is an RCH-defined profile and record the defining section.
- [INFERRED] Acceptance requires direct source URLs and section references in RCH_SOURCES.md.

### C-3 — direct baseline

- [UNCONFIRMED] Capture at least three successful repetitions each of CASE-G1, CASE-C1 and CASE-G2, as defined from the supplied photograph in RCH_PROTOCOL_ASSESSMENT.md, directly between management system and printer.
- [UNCONFIRMED] Capture connection reuse, response timing and closure behavior.
- [INFERRED] Acceptance requires complete bidirectional payloads and hashes for controlled evidence copies.

### C-4 — application-byte transparency

- [UNCONFIRMED] Repeat the same cases through the proxy.
- [INFERRED] Acceptance requires byte equality in each direction after stream reconstruction, correct management-system completion, correct physical output, no new retries and no timeout regression.

### C-5 — negative behavior

- [UNCONFIRMED] Prefer naturally occurring error evidence. Induce an error only through a dealer-approved, non-destructive workflow.
- [INFERRED] Acceptance requires byte-transparent error forwarding and no autonomous response/retry from the proxy.

### C-6 — parser features

- [UNCONFIRMED] Pass DOC-1, FRAME-1, FLOW-1, JOB-1 and relevant XML/PADES gates before enabling a semantic feature.
- [INFERRED] A semantic feature that has not passed its gate must remain disabled or explicitly best-effort and non-authoritative.

## Regression record required per supported firmware

| Evidence | Status before real test | Acceptance |
|---|---|---|
| Exact device/firmware | UNCONFIRMED | Recorded and source-traceable |
| Direct capture hash | UNCONFIRMED | Present outside Git or sanitized |
| Proxy capture hash | UNCONFIRMED | Present outside Git or sanitized |
| Client-to-printer equality | UNCONFIRMED | 100 percent byte-equal |
| Printer-to-client equality | UNCONFIRMED | 100 percent byte-equal |
| Three photographed cases | UNCONFIRMED | Three repetitions each of CASE-G1, CASE-C1 and CASE-G2 |
| Error workflow | UNCONFIRMED | Dealer-approved case passed |
| Parser outputs | UNCONFIRMED | No fabricated fields; offsets traceable |
| Physical versus digital comparison | UNCONFIRMED | Reviewed and discrepancies documented |
| PaDES original | UNCONFIRMED | No capability claim; assess only if officially applicable, observed byte-exactly, and independently signature-validated |

## Current compatibility statement

[DOCUMENTED] Official RCH material supports using Print! F through Ethernet on port 23 and supports RCH command/response operations through XTools.

[OBSERVED] The requested deployment uses the same port and device family.

[UNCONFIRMED] The installed firmware, exact transport, application-byte transparency, framing, XML7 profile, job lifecycle and any PaDES availability are not yet known.

[INFERRED] The current project is a provisional, fixture-tested TCP relay implementation. It must not be called compatible or transparent for the installed device until C-1 through C-4 pass.
