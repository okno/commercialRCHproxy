# RCH Print! F protocol assessment

[OBSERVED] Evidence cut-off: 2026-08-11.

## Evidence vocabulary

| Label | Meaning |
|---|---|
| DOCUMENTED | Stated by an official RCH source identified in RCH_SOURCES.md. |
| OBSERVED | Present in a supplied configuration, artifact, packet capture, device readout, or repeatable local test. |
| INFERRED | An engineering conclusion that is useful but is not an RCH protocol fact. |
| UNCONFIRMED | Not established by accessible official documentation or direct observation. |

[INFERRED] Only DOCUMENTED or OBSERVED evidence may drive protocol-critical behavior. INFERRED evidence may guide passive diagnostics and fallbacks. UNCONFIRMED behavior must not be encoded as a protocol rule.

For new reconstruction work, `CONFIRMED` is used instead of `OBSERVED` for a
finding reproduced from the supplied byte corpus, and `UNKNOWN` replaces
`UNCONFIRMED`. Older gate entries retain their original labels. The current
byte-level result is authoritative in
[RCH_PROTOCOL_ANALYSIS.md](RCH_PROTOCOL_ANALYSIS.md); this broader assessment
still tracks official-document and production-acceptance gaps.

## Identification

| Item | Status | Assessment |
|---|---|---|
| Device | OBSERVED | The deployment request identifies the device as RCH Print! F; its data plate has not been captured in this workspace. |
| Management profile | OBSERVED | The deployment request reports RCH RT v.10 XML7; the exact phrase was not found in accessible official RCH material. |
| Physical address | UNCONFIRMED | The public repository uses documentation placeholder 192.0.2.251; the deployed address belongs only in private configuration. |
| Configured service port | OBSERVED | The deployment request reports port 23. |
| Official service-port evidence | DOCUMENTED | RCH XTools User Manual v4.0.0, DE0054A0008, 07/2026, section 4.1.1 states that PRINT! 3.0 RT, PRINT! RT and PRINT! F use port 23 and that only the IP is configured. |
| Proxy address | UNCONFIRMED | The public repository uses documentation placeholder 192.0.2.231; assignment of the private deployed address has not been observed. |
| Installed firmware | UNCONFIRMED | No device status printout, authenticated protocol response, or service-menu record is available. |
| Serial/model identifiers | UNCONFIRMED | No data-plate image or device query is available. |

## What official RCH sources establish

| Topic | Status | Assessment |
|---|---|---|
| Physical interfaces | DOCUMENTED | Print! F brochure 2018-02 rev.00 lists RS-232, Ethernet and USB Device interfaces. |
| Communication families | DOCUMENTED | The same brochure lists RCH, XON-XOFF, UPOS and JavaPOS. It does not document ESC/POS for Print! F. |
| XTools compatibility floor | DOCUMENTED | RCH XTools v4.0.0 lists Print! F firmware 9.0.2 or later as the minimum supported by XTools. This is not a general protocol-version declaration. |
| Commands and responses | DOCUMENTED | XTools section 4.3.10 provides an RCH protocol-command field and a response field. The compatibility table marks protocol-command sending available to the grouped Print! F family through serial and Ethernet. |
| XML v.7 scope | DOCUMENTED | The official Print! F protocol-manual hierarchy includes Corrispettivi XML v.7 and chapters for VAT/ATECO, goods/services, payments, tickets, rounding, gifts, deposits, vouchers, returns, cancellations, and VAT/payment layouts. |
| Errors | DOCUMENTED | The official hierarchy includes dedicated paper-out handling and an error-message list. |
| PaDES-titled documentation area | DOCUMENTED | The official hierarchy includes a page titled Digital PDF documents with PaDES signature (digital receipt); the title alone does not establish a capability on the installed device. |
| Current XTools digital-download support | DOCUMENTED | XTools v4.0.0 describes digital-document download generically, but its compatibility table marks Electronic Receipt Download unavailable for the grouped Print! F / Print! RT / Print! 3.0 RT family over serial and Ethernet. |
| Newer command set | DOCUMENTED | The Print! F manual includes a chapter titled New commands (from firmware 8.0.8). Its command bodies are authentication-gated. |

## Transport assessment

| Property | Status | Assessment |
|---|---|---|
| Ethernet connectivity | DOCUMENTED | RCH sources document Ethernet connectivity to Print! F. |
| Port 23 | DOCUMENTED | RCH XTools v4.0.0 documents port 23 for Print! F. |
| TCP | OBSERVED / UNCONFIRMED as official property | The supplied proxy artifacts identify distinct TCP sessions. Accessible RCH sources still do not identify TCP; a port number and Ethernet UI are insufficient official proof. |
| UDP | UNCONFIRMED | Accessible RCH sources do not identify or exclude UDP. |
| Raw byte stream | UNCONFIRMED | No accessible official source calls the port a raw stream. |
| Telnet | UNCONFIRMED | No accessible official source documents Telnet negotiation or Telnet option handling. Port 23 alone is not evidence of Telnet. |
| Connection persistence | OBSERVED / UNCONFIRMED generally | One supplied TCP session continued across an application idle gap longer than the old archive threshold; the general reuse, keepalive and idle-close behavior is not documented. |
| Full-duplex protocol semantics | UNCONFIRMED | A response path is documented, but unsolicited responses and simultaneous application traffic have not been established. |
| Half-close behavior | UNCONFIRMED | No official or captured FIN/RST behavior is available. |
| Timeouts and retries | UNCONFIRMED | Connect, response, idle, retry and duplicate-suppression rules are unavailable. |
| Encryption or authentication on port 23 | UNCONFIRMED | No accessible source establishes plaintext, encryption, or application authentication. |

[INFERRED] Until NET-2 passes, the implementation may be described only as a configured TCP socket relay hypothesis, not as an implementation of a documented RCH transport.

## Framing and encoding assessment

| Property | Status | Assessment |
|---|---|---|
| Application frame boundary | CONFIRMED on supplied corpus | The layout in RCH_PROTOCOL_ANALYSIS.md uses STX, AA, LLL, class, DATA, sequence, BCC and ETX; `LLL` is the three-digit `DATA` byte length and total frame size is `LLL + 11`. Official field names are unavailable. |
| STX/ETX control bytes | CONFIRMED on supplied corpus | `0x02` and `0x03` delimit all 77 complete frames. This is observed, not anonymously documented by RCH. |
| Checksum | CONFIRMED on supplied corpus | Two hexadecimal BCC characters equal XOR of bytes from STX through the sequence byte for 77/77 frames. |
| Sequence or correlation identifier | CONFIRMED position / INFERRED meaning | A one-byte field occurs before BCC. Its official name and general correlation semantics remain UNKNOWN. |
| Character encoding | CONFIRMED printable subset / UNKNOWN generally | Observed business payload is printable in a lossless one-byte view. Latin-1 diagnostic mapping is not an encoding declaration. |
| Binary payload support | UNCONFIRMED | The PaDES-titled chapter does not reveal whether any bytes are transferred on this service, or in binary, encoded, or another form. |
| XML/Base64 in supplied cases | CONFIRMED absent | Neither supplied document stream contains XML, escaped XML, hexadecimal XML or Base64. This does not exclude other command families. |
| Network read boundary equals frame | INFERRED required parser rule / synthetically tested | Private receive observations often aligned with complete frames while ACK and framed responses were separate reads; TCP offers no framing guarantee. Whole/1-byte/7-byte/random synthetic segmentation produces identical end-to-end results. |

[INFERRED] A receive-call chunk must be archived with byte offsets and timing but must not be labeled an RCH frame.

## Request, response, errors, and job lifecycle

| Property | Status | Assessment |
|---|---|---|
| Command can produce a response | DOCUMENTED | The current XTools manual exposes command input and response output. |
| Response format | CONFIRMED framing / UNKNOWN semantics | Printer responses use the same capture-confirmed frame shape. Payload status/error meanings remain inaccessible. |
| ACK/NAK bytes | CONFIRMED events / UNKNOWN semantics | 39 standalone `0x06` ACK events and no standalone `0x15` NAK occur in the corpus. ACK scope is unknown; the proxy must not synthesize ACK, NAK, OK or errors. |
| Intermediate and final status | UNCONFIRMED | No accessible flow definition distinguishes them. |
| Paper-out response | UNCONFIRMED | A dedicated official chapter exists, but its body is authentication-gated. |
| Error dictionary | UNCONFIRMED | A dedicated official list exists, but Print! F codes and recovery rules are unavailable. |
| Document start | INFERRED | Commercial and management opening patterns correlate with the supplied paper outputs; they are not official command definitions. |
| Document end | INFERRED | Candidate close patterns are repeatable within the supplied byte order. Fiscal completion remains UNKNOWN. |
| Multiple documents in one connection | UNCONFIRMED | Captured sessions exist, but none contains two complete physical documents. The parser nevertheless supports repeated candidate lifecycles. |
| Idle timeout as a job boundary | INFERRED | It may be used only as an explicitly marked fallback and may not establish fiscal completion. |
| Cut command as a job boundary | UNCONFIRMED | No Print! F cut command or relationship to fiscal completion is established. |

[INFERRED] Fiscal success, document completion and transport closure are separate states until the authenticated flow manual or repeatable packet evidence proves a relationship.

## XML7 assessment

[DOCUMENTED] The official chapter hierarchy establishes that XML v.7 is relevant to Print! F fiscal data.

[UNCONFIRMED] It does not expose the XML root, namespace, schema, encoding, envelope, length, terminator, checksum, response form, or relationship to the management profile RCH RT v.10 XML7.

[DOCUMENTED] XTools v4.0.0 separately offers Export V11 XML for fiscal-memory and DGFE reads.

[INFERRED] XTools V11 export and Print! F Corrispettivi XML v.7 are distinct contexts unless authenticated RCH documentation explicitly maps them.

[CONFIRMED] The supplied commercial and management streams are not XML. A
copied byte range from a future or unrelated capture may still be labelled a
generic XML candidate and, if accepted by a hardened parser, generically
well-formed. It must not be labelled RCH XML7 and `xml7_confirmed` must remain
false until XML-1 through XML-4 pass.

[INFERRED] See RCH_XML7.md for the parser gate used by this project.

## PaDES assessment

| Property | Status | Assessment |
|---|---|---|
| PaDES-titled chapter exists in the hierarchy | DOCUMENTED | This establishes the documentation subject only, not installed-device availability or a callable feature. |
| Available on the installed printer | UNCONFIRMED | Installed firmware and feature enablement are unknown. |
| Obtainable through XTools | DOCUMENTED | Current XTools v4.0.0 marks Electronic Receipt Download unavailable for the Print! F family. |
| Protocol command | UNCONFIRMED | Authentication-gated. |
| Transfer channel and encoding | UNCONFIRMED | Same connection, separate connection, binary, Base64, chunking and file naming are unknown. |
| Signature profile and certificate chain | UNCONFIRMED | No accessible validation details exist. |

[INFERRED] Only after PADES-1 passes may observed original PDF bytes be labeled PDF_RCH_ORIGINAL. Their exact bytes and hash must be preserved. A separately rendered PDF must be labeled PDF_PROXY_RENDERED and must never replace or rewrite the source.

## Authentication gate

[OBSERVED] Anonymous access to the Print! F protocol pages returns an RCH login message instead of article bodies.

[DOCUMENTED] The gated set includes the revision register, protocol structure, flows, paper-out handling, fiscal command list, LOAD-SET, DUMP-ENQ, command examples, XML v.7 details, new commands, PaDES details and error list.

[UNCONFIRMED] The current protocol-manual revision number and compatibility matrix cannot be recovered from anonymous page dates.

[INFERRED] Website updated dates must not be recorded as protocol revisions.

## Exact acceptance gates

[INFERRED] No gate is satisfied merely because code compiles or a synthetic fixture passes.

### Required photographed cases

| Capture case | Status | Acceptance identity |
|---|---|---|
| CASE-G1 | OBSERVED | Paper headed `DOCUMENTO GESTIONALE`, compact item/total/table layout, corresponding to the `compact_table_summary` local description in DOCUMENT_TYPES.md |
| CASE-C1 | OBSERVED | Paper headed `DOCUMENTO COMMERCIALE` / `di vendita o prestazione`, corresponding to the `sale_or_service` local description in DOCUMENT_TYPES.md |
| CASE-G2 | OBSERVED | Paper headed `DOCUMENTO GESTIONALE`, with payment/change and VAT detail, corresponding to the `payment_vat_detail` local description in DOCUMENT_TYPES.md |

[INFERRED] CASE-G1, CASE-C1 and CASE-G2 are test-case identifiers, not claimed RCH protocol type names; only the printed headings are OBSERVED.

### HW-1 — physical identity

- [UNCONFIRMED] Capture the data plate showing exact model and serial identifier.
- [UNCONFIRMED] Record firmware/version using an RCH-documented readout or printed configuration report.
- [UNCONFIRMED] Record whether the device reports RT state, protocol configuration, XML profile, and port.
- [INFERRED] Acceptance requires date-stamped evidence with sensitive identifiers redacted only in repository copies; an unredacted operational record must remain controlled outside Git.

### DOC-1 — authoritative manual

- [UNCONFIRMED] Access the official RCH Print! F protocol manual through an authorized account.
- [UNCONFIRMED] Record manual title, revision, publication/update date, applicable firmware range and exact section for every implemented protocol rule.
- [INFERRED] Acceptance requires a source row in RCH_SOURCES.md and no unresolved conflict with packet evidence.

### NET-1 — direct passive baseline

- [UNCONFIRMED] Capture a normal management-system-to-printer session before inserting the proxy.

      sudo tcpdump -i any -s 0 -nn -U \
        -w rch-direct.pcap \
        'host 192.0.2.251'

- [INFERRED] Record capture host, interface, UTC clock source, start/end time, management action, printer state and software version.
- [INFERRED] Compute and record SHA-256 before analysis.
- [INFERRED] Acceptance requires complete connection establishment/closure if present, both traffic directions, non-truncated payloads, and enough context to correlate one controlled operation.
- [INFERRED] The first baseline must not deliberately create a fiscal operation outside an authorized test workflow.

### NET-2 — transport classification

- [UNCONFIRMED] Determine the actual IP protocol from the packet headers.
- [UNCONFIRMED] If TCP is observed, record handshake, segmentation, retransmission, FIN/RST, half-close, connection reuse and timing.
- [UNCONFIRMED] If TCP is observed, search reconstructed payloads for candidate Telnet IAC negotiation sequences FF FB, FF FC, FF FD and FF FE.
- [INFERRED] Absence of IAC in one capture proves only that no negotiation was observed in that capture; it does not prove Telnet can never occur.
- [INFERRED] Acceptance requires repeatable classification across at least three ordinary sessions and explicit DOCUMENTED or OBSERVED evidence.

### FRAME-1 — framing

- [CONFIRMED] The supplied directional copies were reassembled independently; one frame rule validates all 77 complete frames and is invariant under synthetic receive segmentation.
- [INFERRED] Acceptance requires one rule to explain 100 percent of boundaries across captures with deliberately different network segmentation, at least three repetitions each of CASE-G1, CASE-C1 and CASE-G2, and all captured responses.
- [CONFIRMED] The decimal length and XOR-BCC rule validates every complete supplied frame; broader installed-device variants still require the repeated-case gate above.
- [INFERRED] A receive-call boundary, packet boundary or idle gap alone cannot pass FRAME-1.

### FLOW-1 — request/response

- [UNCONFIRMED] Correlate commands, immediate responses, delayed responses, unsolicited status and connection teardown.
- [INFERRED] Acceptance requires at least three identical controlled operations with the same semantic result and no unexplained response bytes.
- [INFERRED] No response may be generated by the proxy before FLOW-1 and DOC-1 pass.

### JOB-1 — document boundary

- [UNCONFIRMED] Capture at least three repetitions each of CASE-G1, CASE-C1 and CASE-G2; retain a photograph or scan of every corresponding paper output.
- [UNCONFIRMED] Identify the same protocol-level start and end evidence in every repetition.
- [INFERRED] Acceptance requires the boundary to survive coalesced and fragmented delivery and to distinguish back-to-back documents on one connection.
- [INFERRED] A timeout-only boundary may remain a best-effort archival fallback but cannot mark protocol_status as successful.

### ERR-1 — errors

- [UNCONFIRMED] Obtain the authenticated Print! F error table before mapping any numeric or textual code.
- [UNCONFIRMED] Capture naturally occurring error evidence where possible. Induce an error only through a dealer-approved, non-destructive workflow, preferably in an RCH-supported simulation/test environment.
- [INFERRED] Acceptance requires byte-exact forwarding, correct correlation, no proxy retry unless documented, and recovery matching the official manual.

### XML-1 through XML-4 — XML7

- [UNCONFIRMED] XML-1: obtain root, namespace, schema/version and charset from the authenticated RCH chapter.
- [UNCONFIRMED] XML-2: observe byte offsets and transport envelope in direct captures.
- [UNCONFIRMED] XML-3: validate at least three samples per photographed capture case without modifying relay bytes; authoritative `document_type` remains `null` until the official mapping gate passes.
- [UNCONFIRMED] XML-4: map each interpreted field to an official XML path and source offset.
- [INFERRED] XML7 parsing remains non-authoritative until all four gates pass.

### PADES-1 — original signed PDF

- [UNCONFIRMED] Obtain the official Print! F command, firmware prerequisite and transfer format.
- [UNCONFIRMED] Observe a controlled digital-document retrieval from the installed device; current XTools must not be assumed to provide it.
- [INFERRED] Acceptance requires a byte-exact extracted PDF, capture-offset traceability, SHA-256, successful PDF parsing, and an independent cryptographic signature-validation report.
- [INFERRED] No reconstructed proxy PDF may be labeled original or signed.

### PROXY-1 — comparison baseline

- [UNCONFIRMED] After relay deployment, capture both legs for the same controlled cases.

      sudo tcpdump -i any -s 0 -nn -U \
        -w rch-proxy.pcap \
        '(host 192.0.2.231 or host 192.0.2.251)'

- [UNCONFIRMED] Do not insert the current TCP implementation until NET-2 has observed TCP; stop if the direct capture establishes another transport.
- [INFERRED] If TCP is observed, acceptance requires client-to-proxy bytes to equal proxy-to-printer bytes and printer-to-proxy bytes to equal proxy-to-client bytes after stream reconstruction.
- [INFERRED] Acceptance also requires no new application bytes, no missing bytes, no reordered bytes, and no material timeout/retry regression.

## Current verdict

[DOCUMENTED] Ethernet connectivity, use of port 23, and an RCH command/response capability are established for Print! F. The accessible source does not identify the IP transport.

[CONFIRMED] Private raw request/response artifacts and receipt photographs are
available for the two supplied cases. They are proxy-generated stream copies,
not a direct/proxy PCAP comparison, and are intentionally excluded from Git.

[OBSERVED] No direct RCH PCAP, device firmware readout, or authenticated manual
body is present in this workspace as of 2026-08-11.

[CONFIRMED] The supplied run uses TCP-session capture metadata and the observed
frame/length/BCC rules validate all complete frames. XML and Base64 are absent
from both document cases. These facts are capture-specific.

[UNKNOWN] TCP as the official general transport, raw mode, Telnet, general
encoding, XML7 envelope for other workflows, official command/job meanings,
status/error semantics and PaDES transfer remain unresolved.

[INFERRED] The release provides a fixture-tested TCP relay,
capture-confirmed framing and conservative receipt reconstruction for the
observed command families. Installed-device byte transparency remains gated by
NET-2 and C-4/PROXY-1; fiscal success, authoritative command semantics and
signed-document extraction remain gated.
