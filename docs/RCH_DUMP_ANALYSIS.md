# Supplied RCH dump analysis

## Scope and privacy

This report covers the private dump directory supplied for the 0.3.0
reengineering task. It records structural facts but deliberately excludes
merchant identity, address, tax/device identifiers, private endpoints,
products, prices, transaction dates/times, document numbers, and source
hashes. The private files and generated private outputs remain outside Git.

Evidence labels:

| Label | Meaning |
|---|---|
| `VERIFIED_DUMP` | Reproduced directly from the supplied directional bytes or legacy metadata. |
| `VERIFIED_PHOTO` | Read directly from a supplied photograph; never Parser input. |
| `DOCUMENTED_RCH` | Supported by an identified official RCH source. |
| `INFERRED_HIGH` | Strong reverse-engineering fit, but not official semantics. |
| `HYPOTHESIS` | Plausible and awaiting more correlated evidence. |
| `NON VERIFICABILE` | The required bytes/evidence are absent. |

## Inventory result

The supplied dump directory contains exactly **one legacy capture job**, not
four captures and not four logical-document payloads.

| Artifact | Result | Evidence |
|---|---:|---|
| Client-to-device RAW | 235 bytes | `VERIFIED_DUMP` |
| Device-to-client RAW | 202 bytes | `VERIFIED_DUMP` |
| Complete request frames | 10 | `VERIFIED_DUMP` |
| Complete response frames | 9 | `VERIFIED_DUMP` |
| Standalone ACK events | 10 | `VERIFIED_DUMP` |
| Length-valid complete frames | 19/19 | `VERIFIED_DUMP` |
| BCC-valid complete frames | 19/19 | `VERIFIED_DUMP` |
| Legacy receive observations | 29 | `VERIFIED_DUMP`; a receive call is not a frame or document |
| Legacy clean text | empty | `VERIFIED_DUMP` |
| Legacy PDF | blank/no reconstructed document | `VERIFIED_DUMP` |
| Distinct captured documents | one incomplete candidate at most | `INFERRED_HIGH` |

Source SHA-256 values were calculated during private validation but are
intentionally omitted from the public repository. Public regression fixtures
have independent synthetic hashes.

## Stream-level reconstruction

The request stream contains 10 checksum-valid frames. The following table
uses sanitized field shapes; bracketed values are placeholders, not private
payload copies.

| Request frame ordinal | Sanitized `DATA` shape | Direction | Structural position | Interpretation | Confidence |
|---:|---|---|---|---|---|
| 1 | `<</?s` | client to device | start | control/query-like marker | bytes `VERIFIED_DUMP`; meaning `INFERRED_HIGH` |
| 2 | `=K` | client to device | after frame 1 | commercial opener candidate | bytes `VERIFIED_DUMP`; meaning `INFERRED_HIGH` |
| 3 | `=C1` | client to device | body setup | command retained; exact role unknown | bytes `VERIFIED_DUMP`; meaning `HYPOTHESIS` |
| 4-6 | `=R<code>/$<minor-units>/*<qty>/(<description>)` | client to device | body | three item-like records | shape `VERIFIED_DUMP`; role `INFERRED_HIGH` |
| 7 | `="/?A/()` | client to device | body | empty printable/free-text candidate | shape `VERIFIED_DUMP`; role `INFERRED_HIGH` |
| 8 | `="/?A/(<reference>)` | client to device | body | table/reference-like literal | shape `VERIFIED_DUMP`; role `INFERRED_HIGH` |
| 9 | `="/?A/()` | client to device | body | empty printable/free-text candidate | shape `VERIFIED_DUMP`; role `INFERRED_HIGH` |
| 10 | `=T<code>/$<minor-units>` | client to device | payment/total transition | total/payment-like record | shape `VERIFIED_DUMP`; role `INFERRED_HIGH` |

The response stream contains 10 standalone `0x06` events but only 9 framed
responses. Ordinal request/ACK/response association is therefore incomplete.
ACK presence is not promoted to business success.

The legacy job ends after the item/free-text/total sequence and lacks the
inferred commercial close/postlude captured in other historical evidence. The
old archive boundary was idle-based. No adjacent same-session continuation was
supplied with this job. The 0.3 parser consequently reconstructs, at most, one
**incomplete commercial candidate**; it must not mark the candidate complete
or invent its missing final fields.

## Why the old artifacts looked fragmented or encoded

Three concepts were conflated:

1. TCP is a byte stream and may split or coalesce writes arbitrarily.
2. A `recv()` observation is an implementation chunk, not a protocol frame.
3. The old archive policy could finalize after inactivity even while a logical
   exchange remained incomplete.

The payload also includes binary control bytes and framing fields around
mostly printable `DATA`: STX, ETX, standalone ACK, decimal length, sequence,
and hexadecimal BCC. A raw hexdump therefore looks mixed/binary without
implying Base64, XML, encryption, or an additional generic encoding layer.

The 0.3 design addresses the architectural problem by making the whole
transport connection the Dumper capture job and by postponing frame/document
reassembly to the independent Parser. It does not claim that socket close is a
protocol-native document terminator; it is only the capture-container boundary.

## Segmentation invariance

Private local analysis fed the same 235/202 directional streams to the framer
as:

- complete direction copies;
- one byte at a time;
- deterministic arbitrary segmentation.

The resulting frame/event structure and incomplete semantic candidate were
the same. This verifies that Parser framing does not depend on legacy receive
boundaries. It does not establish meanings for unknown RCH fields.

## Comparison with supplied photographs

Four photo labels describe an intended business sequence: a management
command, a management pre-account, a commercial document after a price change,
and a management conforming copy. The labels are operator annotations only;
they are not RCH identifiers or `CODICE_DOC` values.

| Photo label | Visual classification | Byte evidence in supplied job | Result |
|---|---|---|---|
| 1 | management command | no corresponding directional payload | `NON VERIFICABILE` |
| 2 | management pre-account | no payload with the photo's prior item state | `NON VERIFICABILE` |
| 3.1 | commercial document | request item/reference/total values correlate, but close and printer-generated regions are absent | partial `INFERRED_HIGH` correlation |
| 3.2 | management conforming copy | no distinct management payload after the commercial candidate | `NON VERIFICABILE` |

The photo clocks and capture clock are not equal. A difference of roughly two
minutes is observed, but its cause cannot be established from the available
evidence. Exact timestamp equality must not be a correlation requirement.

Only one captured price state exists in the supplied RAW. Therefore the real
evidence cannot execute the requested four-stage price-isolation acceptance
test. Synthetic tests can verify the implementation's state isolation, but
they cannot substitute for the three missing real directional captures.

See [RECEIPT_CORRELATION_REPORT.md](RECEIPT_CORRELATION_REPORT.md) for the
photo-by-photo matrix.

## What can and cannot be reconstructed

From this one partial request stream, the Parser can conservatively recover:

- three item-like descriptions and minor-unit values;
- quantity candidates present in those command fields;
- a table/reference-like literal;
- a total/payment-like amount;
- source frame IDs and byte offsets;
- an incomplete C candidate with evidence labels.

The request bytes do **not** contain a complete copy of the printed merchant
header, legal heading, VAT summary, explicit payment method, printer-generated
date/document number, or fiscal/device footer visible in the photograph. The
Parser must leave those fields absent. Photos are not a fallback data source.

## Evidence needed to complete acceptance

Capture and supply, under an authorized protected workflow, all four operations
with both directions and timeline/connection identity:

1. management command;
2. pre-account before the price change;
3. commercial document after the price change, including its complete
   close/postlude and delayed responses;
4. automatically generated management conforming copy.

For each operation preserve the unmodified request RAW, response RAW, timeline,
manifest, capture start/end, and photo label correlation. Do not use photos as
parser input. A direct/proxy PCAP comparison and authenticated protocol manual
remain separate acceptance evidence.
