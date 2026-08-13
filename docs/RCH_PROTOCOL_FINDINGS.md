# RCH protocol findings

## Evidence boundary

This is a reverse-engineering report, not an RCH protocol specification. It
describes the structure reproduced from the supplied private bytes without
publishing business literals or identifiers.

| Label | Meaning |
|---|---|
| `VERIFIED_DUMP` | Directly repeatable from the supplied byte stream. |
| `DOCUMENTED_RCH` | Stated by an identified official RCH source. |
| `INFERRED_HIGH` | Strong positional/photo/sequence correlation, not official semantics. |
| `HYPOTHESIS` | Plausible interpretation requiring more samples or official material. |
| `UNKNOWN` | Evidence does not establish the property. |

Official RCH material referenced in [RCH_SOURCES.md](RCH_SOURCES.md) documents
Ethernet port 23 for the Print! F family (`DOCUMENTED_RCH`). The accessible
material does not establish TCP versus UDP, raw stream versus Telnet, frame
layout, command semantics, ACK scope, or fiscal success (`UNKNOWN`). The
implementation uses TCP because that is the observed/deployed hypothesis; port
number 23 alone is not evidence of Telnet semantics.

## Capture-confirmed stream units

Complete observed frames have this layout:

```text
+------+----+-----+---+-----------+-----+-----+------+
| STX  | AA | LLL | C | DATA      | seq | BCC | ETX  |
+------+----+-----+---+-----------+-----+-----+------+
| 1 B  | 2  | 3   | 1 | LLL bytes | 1   | 2   | 1 B  |
+------+----+-----+---+-----------+-----+-----+------+
```

| Field | Hex/text representation | Observed rule | Meaning/confidence |
|---|---|---|---|
| `STX` | `02` | one leading byte | frame start, `VERIFIED_DUMP` |
| `AA` | two ASCII decimal bytes | exactly two digits | positional name only; business meaning `UNKNOWN` |
| `LLL` | three ASCII decimal bytes | byte length of `DATA` | `VERIFIED_DUMP` |
| `C` | one byte | observed direction-correlated values | official name/meaning `UNKNOWN` |
| `DATA` | `LLL` bytes | opaque to the framer | selected semantics below are `INFERRED_HIGH` |
| `seq` | one byte | immediately before BCC | sequence-like position; complete rules `UNKNOWN` |
| `BCC` | two ASCII hexadecimal bytes | XOR from STX through `seq`, inclusive | algorithm `VERIFIED_DUMP` |
| `ETX` | `03` | one trailing byte | frame end, `VERIFIED_DUMP` |

A frame with `N` data bytes occupies `N + 11` bytes. BCC validation is:

```text
bcc = 0
for each byte from STX through seq inclusive:
    bcc = bcc XOR byte
compare bcc with the two ASCII hexadecimal BCC digits
```

The following full frame is **synthetic** and contains no private data. It uses
address text `00`, class byte `z`, `DATA="=K"`, sequence text `0`, and a
recomputed BCC:

```text
02 30 30 30 30 32 7a 3d 4b 30 30 43 03
```

`0x06` outside a frame is retained as an independent ACK event
(`VERIFIED_DUMP`). It is not merged into a response frame or receipt body.
Its business scope and any relationship to fiscal success are `UNKNOWN`.

## Supplied-job counts

| Direction/event | Count | Validation |
|---|---:|---|
| client-to-device frames | 10 | all declared lengths and BCCs valid |
| device-to-client frames | 9 | all declared lengths and BCCs valid |
| device-to-client standalone ACK | 10 | byte `06` outside frames |
| complete frames total | 19 | 19/19 structurally valid |

There is one more ACK than framed responses. Request-to-response association is
therefore a bounded ordinal/sequence inference, not a guaranteed one-to-one
protocol rule. The final request cannot be assigned a framed response from the
supplied evidence.

## Sanitized marker register

Positions are request-frame ordinals in the single 235-byte request stream.
Hex values describe only fixed marker text, never redacted field values.

| Position | Direction | Fixed `DATA` marker | Marker hex | Parser role | Evidence | Associated candidate |
|---:|---|---|---|---|---|---|
| 1 | client to device | `<</?s` | `3c 3c 2f 3f 73` | pending control/query-like start | bytes `VERIFIED_DUMP`; role `INFERRED_HIGH` | commercial |
| 2 | client to device | `=K` | `3d 4b` | start fresh commercial builder | bytes `VERIFIED_DUMP`; role `INFERRED_HIGH` | commercial |
| 3 | client to device | `=C1` | `3d 43 31` | retained unknown/setup command | bytes `VERIFIED_DUMP`; role `HYPOTHESIS` | commercial context |
| 4-6 | client to device | prefix `=R` | `3d 52` | item-like field grammar | shape `VERIFIED_DUMP`; role `INFERRED_HIGH` | commercial body |
| 7-9 | client to device | prefix `="/?A/(` | `3d 22 2f 3f 41 2f 28` | printable/free-text candidate | shape `VERIFIED_DUMP`; role `INFERRED_HIGH` | commercial body |
| 10 | client to device | prefix `=T` | `3d 54` | total/payment transition candidate | shape `VERIFIED_DUMP`; role `INFERRED_HIGH` | commercial payment |
| multiple | device to client | standalone ACK | `06` | preserve independent event | byte `VERIFIED_DUMP`; scope `UNKNOWN` | request/response diagnostics only |

The current parser also recognizes the following patterns from the broader
sanitized regression model. They are implemented as inferred candidates and
are **not present as complete evidence in the newly supplied partial job**:

| `DATA` shape | Implemented role | Confidence/limit |
|---|---|---|
| `<</?<digit>` or bare `<</?` after commercial payment | commercial close candidate | `INFERRED_HIGH`; not fiscal success |
| exact `=o` | contextual management open/close envelope | `INFERRED_HIGH`; context decides transition |
| `="/(<printable line>)` | management printable line | `INFERRED_HIGH`; literal text retained |
| `=D<line>/(...)` | auxiliary display candidate | `INFERRED_HIGH`; excluded from receipt body |

These broader patterns are tested only with sanitized synthetic fixtures in the
public repository. They must not be presented as verified for a missing real
capture.

## Incremental framing

The framer consumes an arbitrary sequence of byte chunks and retains an
internal bounded buffer. It:

- recognizes standalone ACK separately;
- waits for the full decimal-length frame, even across chunk boundaries;
- validates ETX and XOR BCC;
- retains malformed/truncated evidence as bounded issues;
- resynchronizes on plausible next STX/ACK without treating a socket read as a
  message;
- produces equal results for whole-stream, byte-at-a-time, fixed-width, and
  deterministic arbitrary segmentation.

No per-chunk character decoding is used to determine frame boundaries. `DATA`
is exposed through a lossless one-byte diagnostic view; that view is not a
claim that the device's full encoding is Latin-1. Multibyte/accented behavior
outside the supplied printable subset remains `UNKNOWN`.

## Request/response correlation

The parser retains both directions independently. Candidate correlations use:

1. request-frame ordinal;
2. ACK ordinal;
3. response-frame ordinal;
4. an independently checked, inferred sequence relationship.

Missing ACK/response and sequence mismatch become explicit issues. They do not
delete, reorder, or rewrite events. ACK, valid BCC, or response presence never
populates application/fiscal success.

## Document semantics

The following distinction is mandatory:

- frame boundaries, field positions, literal `DATA`, lengths, and BCC results
  are `VERIFIED_DUMP` when found in the source;
- command roles, document types, lifecycle transitions, style hints, totals,
  payment labels, and copy relationships are `INFERRED_HIGH` or weaker;
- fields absent from bytes are `UNKNOWN` and remain absent.

The parser creates `C` only from the inferred commercial command lifecycle,
not merely from prices/totals. `G` requires a management lifecycle. A
conforming-copy candidate remains `G` and requires a literal marker or a
same-stream relationship to a separate preceding `C` with matching captured
item/total signature and supporting management fields.

## Unsupported conclusions

The supplied job does not establish:

- official names for `AA`, `C`, `seq`, or any command;
- the installed firmware or applicable authenticated manual revision;
- Telnet negotiation or raw-stream semantics;
- ACK/NAK retry policy or error meanings;
- fiscal acceptance, print completion, or legal validity;
- a complete commercial close sequence;
- real payloads for the photographed command, pre-account, or conforming copy;
- device encoding beyond the observed printable one-byte subset;
- general command variants for discount, return, cancellation, non-cash
  payment, paper-out, or device errors.

See [PARSER_STATE_MACHINE.md](PARSER_STATE_MACHINE.md) for implemented inferred
transitions and [RCH_DUMP_ANALYSIS.md](RCH_DUMP_ANALYSIS.md) for the exact
evidence inventory.
