# RCH stream protocol analysis

Evidence cut-off: 2026-08-11. This document describes the private validation
corpus supplied for this investigation without reproducing its business data.
It is not an RCH protocol specification.

## Evidence vocabulary

| Label | Meaning in this document |
|---|---|
| `CONFIRMED` | Reproduced from the supplied byte streams, their capture metadata, or a deterministic test built from those observations. |
| `DOCUMENTED` | Stated by an identified official RCH source. |
| `INFERRED` | A reverse-engineering conclusion that fits the corpus but is not established as an official protocol meaning. |
| `UNKNOWN` | The available bytes and accessible documentation do not establish the value or meaning. |

A byte layout can therefore be `CONFIRMED` while the business meaning of one
of its fields remains `INFERRED` or `UNKNOWN`.

## Official-source boundary

- [`DOCUMENTED`] [RCH XTools v4.0.0](https://support.rch.it/download/28926/),
  section 4.1.1 (page 15), lists Ethernet port 23 for the Print! F family.
- [`UNKNOWN`] That statement does not identify TCP versus UDP, raw-stream
  versus Telnet semantics, framing, checksum, command meanings, or document
  boundaries. Port 23 by itself proves none of those properties.
- [`DOCUMENTED`] RCH publishes a Print! F protocol-manual hierarchy containing
  chapters for protocol structure, flows, commands, XML v.7, errors and PaDES.
  The relevant article bodies are authentication-gated. See
  [the official-source register](RCH_SOURCES.md).
- [`UNKNOWN`] No authenticated protocol revision applicable to the installed
  device was supplied. The field meanings below must not be presented as
  official RCH definitions.

## Corpus-level findings

| Finding | Status | Result |
|---|---|---|
| Significant application layer | `CONFIRMED` | Delimited byte frames plus standalone control bytes; not XML and not Base64. |
| Complete frames | `CONFIRMED` | 77 of 77 complete frames satisfy the observed delimiter, length and XOR-BCC rules. |
| Direction split | `CONFIRMED` | 39 client-to-printer frames and 38 printer-to-client frames. |
| Standalone ACK | `CONFIRMED` | 39 occurrences of byte `0x06`, all in the printer-to-client evidence. |
| Standalone NAK | `CONFIRMED` | No `0x15` event was observed in this corpus. This does not prove that NAK is unsupported. |
| Receive-call boundaries | `CONFIRMED` | Some controls and frames arrived in separate reads. Apparent alignment of many request reads with frames is incidental. |
| Text view | `CONFIRMED` | The observed business payload subset is printable in a one-byte view. Latin-1 is used for a lossless diagnostic mapping, not as a declared device encoding. |
| XML7 payload | `CONFIRMED` | No XML document, escaped XML envelope, hexadecimal XML or Base64 XML layer occurs in the supplied raw streams. |

### Aggregate byte profile

The following aggregates cover the seven private request copies and seven
private response copies. They contain no business literals or private hashes.

| Direction | Bytes | Shannon entropy (bits/byte) | Printable ASCII ratio | Control-byte counts |
|---|---:|---:|---:|---|
| Client to printer | 1,396 | 4.3662 | 94.4126% | STX 39, ETX 39; all controls listed below zero |
| Printer to client | 837 | 2.7905 | 86.2605% | STX 38, ETX 38, ACK 39; all controls listed below zero |

[`CONFIRMED`] Both directions contain zero NUL, CR, LF, EOT, NAK, ESC, FS,
GS, RS and US bytes. Every byte is in the 7-bit range, so UTF-8 decoding is
syntactically possible, but that fact alone does not declare UTF-8. ISO-8859-1
and Windows-1252 produce the same characters for this observed subset. The
fixed ASCII framing and absence of the expected NUL-byte pattern do not support
a UTF-16 interpretation for these messages.

[`CONFIRMED`] The streams are not JSON, XML, Base64 containers, whole-stream
hexadecimal text or URL-encoded envelopes. Hexadecimal characters have a
specific local role only in the two-byte BCC field. Parentheses, slashes,
currency markers and percentage signs inside `DATA` are literal command/text
syntax, not evidence of a second generic decode layer.

## Capture-confirmed frame layout

Every complete frame in both directions has this structural layout:

```text
+------+----+-----+---+----------+-----+-----+------+
| STX  | AA | LLL | C | DATA     | seq | BCC | ETX  |
+------+----+-----+---+----------+-----+-----+------+
| 1 B  | 2  | 3   | 1 | LLL bytes| 1   | 2   | 1 B  |
+------+----+-----+---+----------+-----+-----+------+
```

| Field | Status | Observed rule | Semantic meaning |
|---|---|---|---|
| `STX` | `CONFIRMED` | One byte, `0x02`. | Delimits the beginning of the observed frame. |
| `AA` | `CONFIRMED` | Two ASCII decimal digits. | `UNKNOWN`; values differ by direction in this corpus. |
| `LLL` | `CONFIRMED` | Three ASCII decimal digits. | Length of `DATA` in bytes. |
| `C` | `CONFIRMED` | One byte. | `UNKNOWN`; observed values correlate with direction, but the official name and meaning are unavailable. |
| `DATA` | `CONFIRMED` | Exactly the number of bytes declared by `LLL`. | Command/response semantics are only partly `INFERRED`. |
| `seq` | `CONFIRMED` | One byte before the BCC. | A sequence-like field by position; its rollover and correlation rules are `UNKNOWN`. |
| `BCC` | `CONFIRMED` | Two ASCII hexadecimal digits, case-insensitive in the corpus. | XOR of every byte from `STX` through `seq`, inclusive. |
| `ETX` | `CONFIRMED` | One byte, `0x03`. | Delimits the end of the observed frame. |

For a declared data length `N`, the complete frame occupies `N + 11` bytes.
The validation calculation is:

```text
bcc = 0
for byte in frame[STX .. seq]:
    bcc = bcc XOR byte
expected_field = two_hex_digits(bcc)
```

[`UNKNOWN`] The official names for `AA`, `C` and `seq` are unavailable. Their
neutral names in the parser describe position or observed shape, not RCH
semantics.

## ACK is not a response frame

[`CONFIRMED`] Byte `0x06` occurs outside `STX`/`ETX` frames. It is emitted by
the framer as an independent `ack` event and is preserved in the immutable
printer-to-client RAW stream. It is never added to human receipt text.

[`CONFIRMED`] The private corpus contains one more ACK event than framed
printer responses: the final management-envelope request has an ACK without a
following framed response in the capture. Separately, the old inactivity
archive boundary placed another ACK at the end of one file and its following
framed response at the start of the next file. Treating `ACK + following
recv()` as one response, or treating each `recv()` as a frame, therefore
produces incorrect associations.

[`INFERRED`] The byte behaves as an acknowledgment in these exchanges. Its
scope, whether it acknowledges transport acceptance or application execution,
and its relationship to fiscal success are `UNKNOWN`. The proxy must never
synthesize it.

## Document correlation

The table intentionally omits merchant identity, private addresses, device
identifiers, dates, counters, product text and monetary values.

| Evidence group | Status | Correlation and boundary conclusion |
|---|---|---|
| Four equal display exchanges | `CONFIRMED` | Four byte-identical request/response pairs came from four distinct TCP sessions and client ports. They are real repeated display operations, not TCP fragments and not duplicates to merge away. |
| Commercial request, first archive part | `CONFIRMED` | A 168-byte client stream contains eight valid request frames: an opening-pattern candidate, an item-like command, free-text lines and a total-like command. |
| Commercial request, second archive part | `CONFIRMED` | A 106-byte continuation contains four valid frames in the same TCP session, including display lines and close-pattern candidates. |
| Split of the two commercial parts | `CONFIRMED` | The recorder's one-second inactivity fallback closed the first archive job while the same connection and protocol exchange continued. This split was made by proxy archive policy, not by TCP framing and not by a confirmed end-of-document marker. |
| Management document | `CONFIRMED` | A separate 826-byte client stream contains 19 valid frames whose human-visible body lines correlate in order with the supplied management print. |
| Cross-session concatenation | `CONFIRMED` | Blind chronological concatenation would incorrectly fold the four display sessions into documents. Session identity, direction, frame validity and document state are required. |

### Candidate lifecycle patterns

The byte patterns and their order are `CONFIRMED`; the lifecycle labels are
`INFERRED` because the official command pages are not accessible.

| Observed `DATA` pattern | Inferred role | Basis and limitation |
|---|---|---|
| Starts with `=D1/(` or `=D2/(` | customer-display line | Four independent exchanges and the two display lines in the commercial continuation. Not receipt body by itself. |
| `<</?s` followed by exact `=K` | commercial-document opening candidate | `<</?s` occurs again near close, so `=K` is the state-opening discriminator used by the parser. One corpus case is insufficient for an official command claim. |
| Starts with `=R` and includes price/quantity/text fields | commercial item candidate | The extracted fields correlate with the printed item. Department, VAT and quantity-default semantics remain partly `UNKNOWN`. |
| Starts with `=\"/` and contains parenthesized text | free printable line candidate | Text correlates with photo-visible lines in both document families. Formatting flags are only partly understood. |
| Starts with `=T` and contains an amount field | commercial total/payment candidate | Its amount correlates with the print; the exact payment-method semantics are not established by the bytes alone. |
| `<</?s` followed by exact `<</?7` | commercial close candidate | These are the final control-like `DATA` values after the display continuation. `<</?7` closes the candidate; final fiscal success is still `UNKNOWN`. |
| Exact `=o` at both ends | management-document envelope candidate | The two equal commands surround the 17 human-visible body-line frames correlated with the management photo. Context/state distinguishes candidate open from candidate close. |

[`UNKNOWN`] A single TCP connection containing multiple complete physical
documents was not present in the private corpus. The parser must support that
case, but the deployed device's connection-reuse policy is not established.

## Ground-truth coverage and absent fields

Only values that occur in client-to-printer `DATA` may be reconstructed as
stream-derived receipt content. A photo can validate a value but cannot be
used to inject that value into parsed output.

| Printed information category | Commercial stream | Management stream | Rule |
|---|---|---|---|
| Item description and amount | Present in command fields (`CONFIRMED`) | Present as printable body text (`CONFIRMED`) | Preserve source frame and byte offsets. |
| Free order/reference line | Present (`CONFIRMED`) | Present (`CONFIRMED`) | Output only the captured text. |
| Total-like amount | Present (`CONFIRMED`) | Present as printable body text (`CONFIRMED`) | Business role is `INFERRED` unless the command mapping is documented. |
| VAT summary | Not explicitly present (`CONFIRMED`) | Present in printable body lines (`CONFIRMED`) | Commercial VAT values remain `null`/absent. |
| Payment amount/method | Total/payment candidate carries an amount; no method label is present (`CONFIRMED`) | Present as printable body text (`CONFIRMED`) | Commercial output may add the generic `INFERRED` label `IMPORTO PAGAMENTO`; structured `method` remains null and is never changed to cash from the photo. |
| Merchant header | Absent from both captured request bodies (`CONFIRMED`) | Absent (`CONFIRMED`) | Likely device-programmed (`INFERRED`); exact provenance is `UNKNOWN`. |
| Printed document heading | Absent (`CONFIRMED`) | Absent (`CONFIRMED`) | Likely selected/rendered by device state (`INFERRED`); do not synthesize it as captured text. |
| Footer, device identifier and fiscal metadata | Absent from request; a response contains a counter-like suffix (`CONFIRMED`) | Absent or only partly represented in body (`CONFIRMED`) | Full values remain null/absent. The response suffix may appear only as an explicitly `INFERRED`, `solo suffisso` annotation. |
| Printer-generated date/counter fields | Absent from the commercial request (`CONFIRMED`) | A reference line is present in the management body, while the printer footer is absent (`CONFIRMED`) | Do not copy photo-only values into output. |

The supplied commercial photo and the stream chronology also contain a
timestamp discrepancy. [`CONFIRMED`] The values are not byte-for-byte
consistent. [`UNKNOWN`] Whether this reflects a reprint, differing clocks, or
another device workflow cannot be resolved from the available evidence.

### Chain-of-reconstruction matrix

The byte patterns below are deliberately schematic; private literals are
replaced by field names.

| Paper region | Candidate field/command | Private artifact group | Original `DATA` shape | Decode/output |
|---|---|---|---|---|
| Commercial item description/amount | item candidate | 168-byte same-session first part | `=R<code>/$<minor-units>/*<quantity>/(<description>)` | Description, amount and optional quantity become a sourced item line/object (`INFERRED` role). |
| Commercial hash-only line | printable free line | 168-byte first part | `="/?A/()` | Empty literal text plus paper-correlated inferred `#` prefix yields `#`. |
| Commercial order/reference | printable free line | 168-byte first part | `="/?A/(<reference text>)` | Literal text is preserved; inferred `#` prefix is rendered and source offsets retained. |
| Commercial total/payment value | total candidate | 168-byte first part | `=T<code>/$<minor-units>` | Renders `TOTALE` and the explicitly inferred generic label `IMPORTO PAGAMENTO`; payment object keeps `method=null`. |
| Commercial display text | auxiliary display | 106-byte same-session continuation | `=D1/(...)`, `=D2/(...)` | Kept in protocol messages; deliberately excluded from receipt body. |
| Commercial response counter suffix | response candidate | framed printer response correlated to request | `s<digits>RE<suffix>` | Suffix-only structured candidate with unknown prefix; rendered only as `DOCUMENTO N. (solo suffisso)`, never as a full number. |
| Commercial header/VAT/payment method/printer footer | no request field | none | absent | Null/absent; photo does not inject it. The proxy's generic payment/suffix labels remain visibly qualified inferred annotations. |
| Management item/total/payment/change body | printable line | 826-byte separate session | `="/(<already spaced printed line>)` | Literal line order/spacing preserved; conservative item/total/payment/change objects added. |
| Management VAT summary | printable lines | 826-byte session | `="/(<VAT headings/values>)` | Literal lines preserved; taxable/tax amount candidates retain source. |
| Management order/reference | printable lines | 826-byte session | `="/(<reference text>)` | Literal text plus date/time/number substrings captured in the line become sourced candidates. |
| Management emphasis | printable-line style suffix | 826-byte session | `="/(... )/*2` | Double-width/height/bold hints are `INFERRED` from photo correlation. |
| Management header/heading/printer footer | no request field | none | absent | Null/absent; likely device-generated, exact provenance unknown. |

This matrix explains every important value that the reconstructor emits. It
also makes omissions auditable: if no frame/offset exists, the software does
not claim to have reconstructed the field.

## Root cause analysis

### Why were many files produced?

[`CONFIRMED`] Three different causes were mixed together:

1. four genuine, separate display TCP sessions;
2. one commercial exchange split into 168-byte and 106-byte archive jobs by
   `JOB_IDLE_TIMEOUT_MS=1000` despite remaining in the same TCP session;
3. one separate management-document session.

The program did not create one file per `recv()`. It accumulated receive
chunks into a fallback job. The problem was that inactivity was treated as a
storage boundary without preserving the logical document boundary.

### Was the split caused by TCP?

[`CONFIRMED`] The 168/106 split was caused by archive policy, not TCP packet or
receive segmentation. TCP can fragment or coalesce bytes arbitrarily, and the
parser must remain correct under either behavior, but no TCP boundary carries
document semantics.

### Why did the data look encoded or binary?

[`CONFIRMED`] The RAW includes `STX`, `ETX`, `ACK`, decimal length fields,
sequence bytes and hexadecimal BCC characters around printable payloads.
Hexdumps and technical renderings made that framing visible. There is no
Base64 or XML decode layer in these two cases.

### Which bytes belong in the human document?

[`CONFIRMED`] Candidate receipt content comes only from selected
client-to-printer frame `DATA`. Printer-to-client ACKs and response frames are
kept as protocol evidence and metadata, never mixed into `receipt.txt`.

### What are START and END DOCUMENT?

[`INFERRED`] The candidate command patterns are listed above. Their positions
and photo correlation are strong enough for an evidence-labelled parser, but
not for an official RCH semantic claim. Timeout and socket close remain
fallback flush conditions, not success markers.

## Remaining unknowns

- official names and meanings of `AA`, `C`, `seq` and response payload fields;
- installed firmware and applicable protocol-manual revision;
- TCP/raw/Telnet semantics as an official device property, despite the
  configured TCP relay and the supplied TCP-session metadata;
- ACK scope, errors, retry rules, and final fiscal-success response;
- exact command variants for returns, cancellations, discounts, non-cash
  payments, errors and paper-out;
- authoritative encoding outside the printable subset in this corpus;
- provenance and retrieval of printer-generated header, footer and fiscal
  fields absent from the request stream;
- multiple complete documents on one deployed TCP connection.

New captures must be decoded conservatively: preserve raw bytes, report
unknown commands, and expand semantic rules only with repeatable correlated
evidence or authenticated official documentation.
