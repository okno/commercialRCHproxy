# Receipt parser

The receipt parser reconstructs only human-visible values supported by copied
client-to-printer frames. It does not try to reproduce values that the printer
adds from its own configuration or fiscal state.

## Evidence boundary

| Layer | Status | Consequence |
|---|---|---|
| Delimiters, length, literal `DATA`, sequence position and XOR BCC | `CONFIRMED` | May drive framing and source offsets. |
| Observed directional profile (`00`/`z` request, `01`/`N` response) | `CONFIRMED` for the supplied corpus | Only BCC-valid frames with this profile may drive inferred receipt semantics. Other profiles remain diagnostic messages. |
| Standalone ACK byte | `CONFIRMED` | Preserve as protocol evidence; never render as receipt content. |
| Candidate command roles and document lifecycles | `INFERRED` | May produce explicitly evidence-labelled receipt candidates. |
| Official command names and fiscal meanings | `UNKNOWN` | Do not call an inferred close fiscal success. |
| Fields absent from copied streams | `UNKNOWN` | Keep `null`/absent; never copy them from a photograph. |
| Ethernet port 23 | `DOCUMENTED` | Relevant to configuration only; it does not define the parser. |

The supplied photographs are validation ground truth for values that also
occur in the stream. They are not a secondary data source for generated
receipts.

## Processing chain

```text
immutable request/response copies
        |
        +-- directional stream framing
        |       |-- frames
        |       |-- standalone ACK events
        |       `-- byte-range issues
        |
        +-- client command classification (INFERRED)
        |       `-- per-document state machine
        |
        +-- printer response messages (metadata only)
        |
        `-- ParsedReceipt
                |-- receipt text
                |-- structured JSON-ready dictionary
                `-- frame ids and source offsets
```

The public programmatic entry point is:

```python
from commercialrchproxy.rch.receipt_parser import parse_protocol_chunks, parse_protocol_copies

result = parse_protocol_copies(request_bytes, response_bytes)
# Equivalent incremental entry point for arbitrary receive segmentation:
result = parse_protocol_chunks(request_chunks, response_chunks)
```

`ProtocolCopiesResult` exposes:

- `documents`: ordered `ParsedReceipt` candidates;
- `messages`: bounded retained framed request/response messages and standalone
  ACK events;
- `correlations`: ordinal request/ACK/response candidates with an independent
  observed sequence check;
- `issues`: framing, incompleteness and reconstruction issues;
- `request_framing` and `response_framing`: exact directional results;
- `receipt_texts`, `parsed_documents` and `to_dict()` convenience views.

`ParsedReceipt` exposes `receipt_text` (also `text`), `parsed_dict` (also
`to_dict()`), candidate document type, completeness, evidence label, source
frame identifiers, and start/end offsets.

## Candidate document families

The parser does not inspect filenames. It uses command patterns and ordering.
All roles in this section are `INFERRED` from one private correlated corpus.

### Commercial document candidate

Observed order:

```text
<</?s              opening preamble candidate
=K                 document-start candidate
=C...              retained protocol command, semantics unknown
=R...              item candidate
="/?A/(...)        printable free line candidate
=T...              total-like candidate
=D1/(...)          auxiliary display, not receipt text
=D2/(...)          auxiliary display, not receipt text
<</?s
<</?7              close-sequence candidate
```

The parser extracts only literal fields demonstrated by the corpus:

- description from the parenthesized item field;
- integer minor-unit amount from the `$` field;
- quantity when the observed `/*` field is present;
- printable free-line text; the paper-correlated `#` prefix is absent from
  `DATA` and is therefore added only as an `INFERRED` rendering rule;
- total-like minor-unit amount;
- order/reference text when it occurs as a captured free line.

The observed `T1` total also produces a payment-value candidate whose
`method` remains null. The parser does not turn it into cash merely because the
paper print uses a cash label.

It does not infer merchant header, VAT summary, payment method, printer
identifier, complete fiscal counter/number or printer-generated timestamp when
those values are absent. A correlated response may contribute only the
explicitly qualified suffix candidate described below.

### Management document candidate

Observed order:

```text
=o                 opening-envelope candidate
="/(...)           printable line candidates
...
=o                 closing-envelope candidate (distinguished by state)
```

The line payloads already contain spacing and labels intended for the printed
body. The parser preserves their order and literal text. It additionally emits
structured candidates when an observed line shape provides enough evidence:

- item-like line before the primary total;
- total line;
- cash/payment line;
- change line;
- VAT-summary line;
- order/reference line;
- printed date, time and document-reference substring.

These structured roles are `INFERRED`; the original line and source trace stay
authoritative. Formatting flags such as a trailing style selector are retained
through conservative bold/double-width/double-height hints only where
observed.

### Auxiliary display exchanges

Frames whose data starts with `=D1/(` or `=D2/(` are classified as display
updates. They remain in `messages` and in RAW evidence but do not open a
receipt and do not become receipt lines.

This distinction prevents the four genuine repeated display sessions in the
private corpus from becoming four false receipts.

## Completeness is not fiscal success

`complete=true` means only that the inferred opening/body/closing sequence was
present in the copied request stream. It does not mean:

- that every byte arrived at the device;
- that the device accepted the command;
- that paper was available;
- that the document was memorized, transmitted or fiscally valid;
- that a printer response indicated success.

Those values remain `UNKNOWN` until authenticated response semantics and
device validation are available. If capture ends before a candidate close,
the parser returns the document with `complete=false` and an
`incomplete_document` issue instead of discarding it.

## Human-readable text

`receipt_to_text(document)` and `ParsedReceipt.receipt_text` render only
`DocumentModel` lines. Technical markers, frame headers, ACKs, response
payloads, BCCs and parser warnings do not appear in the human receipt.

For the commercial candidate, the renderer creates a conservative line from
the captured item description and amount, preserves captured free lines, and
adds `TOTALE` plus the visibly inferred generic label `IMPORTO PAGAMENTO` to
the captured total/payment amount. When a correlated response exposes only a
counter suffix, the footer says `DOCUMENTO N. (solo suffisso)` and never
supplies a missing prefix. For the management candidate, the renderer preserves
the captured printable body lines as they appear in the stream.

Blank captured printable lines may remain blank because they are part of the
observed layout. Missing header/footer fields are not replaced with decorative
or photo-derived text.

## Structured representation

`receipt_to_dict(document)` returns a JSON-ready object with this stable shape:

```json
{
  "document_id": "document-0001",
  "document_type": "commerciale | gestionale",
  "printed_class": "documento_commerciale | documento_gestionale",
  "evidence": "INFERRED",
  "complete": true,
  "source": {
    "direction": "request",
    "frame_ids": [],
    "start_offset": 0,
    "end_offset": 0
  },
  "receipt_text": "...",
  "lines": [],
  "parsed": {
    "items": [],
    "quantities": [],
    "descriptions": [],
    "amounts": [],
    "taxes": [],
    "payments": [],
    "totals": [],
    "date": null,
    "time": null,
    "document_number": null,
    "fiscal_fields": {},
    "metadata": {}
  },
  "issues": []
}
```

Every extracted line and the structured item/amount/tax/payment/total objects
carry source evidence. Compatibility arrays such as `quantities` and
`descriptions` contain primitive values; their originating item object retains
the source. Date/reference/order source details are kept in metadata. Values
not present in the stream remain `null`, an empty list or an empty object as
appropriate.

`ProtocolCopiesResult.to_dict()` also contains bounded protocol messages, framing
results and issues. This is the full chain-of-reconstruction view; a receipt
object alone is the human/semantic projection.

## Response handling

Printer-to-client data is framed and preserved separately. ACK events are
listed as `standalone_ack`.

[`INFERRED`] The private corpus supports an ordinal request/ACK/response
association and a response sequence candidate equal to request sequence plus
eight modulo ten. Every `RequestResponseCorrelation` records both the ordinal
association and whether that sequence check matched. A missing ACK/frame,
extra response or mismatch becomes an issue; correlation never fabricates a
response.

A sequence-matched, BCC-valid response to the exact post-payment `<</?s`
query matching the observed counter-like shape may
populate only a suffix candidate in structured `document_number` and
`fiscal_fields`. Metadata explicitly records `suffix_only`, keeps the unknown
prefix null and traces the response frame. Receipt text may render it only as
`DOCUMENTO N. (solo suffisso) <value>`; it is never promoted to a complete
fiscal document number.

Unknown response frames remain `UNKNOWN`. No response is rewritten and the
proxy never generates a response on the printer's behalf.

## Error handling and security

- Declared frame length, analyzed bytes (8 MiB per direction by default),
  retained events/messages/issues/documents, derived semantic fields, issue
  previews and parser buffers are bounded. Limit crossings are prioritized as
  explicit issues; immutable RAW is separate.
- Invalid BCC, malformed header, invalid terminator, unframed data and
  truncation become typed issues with exact byte ranges and bounded previews.
- Unknown commands remain protocol messages; their bytes are not discarded.
- A parsing exception is isolated from the forwarding path.
- No `errors="ignore"`, opportunistic Base64/XML decode or filename-derived
  document type is used.
- Human outputs are derived from copied bytes only and are not replayable
  commands.

## Fixture and privacy policy

The real corpus contains private business, network, device and transaction
data. It stays outside Git and is used only for authorized local validation.
Public regression fixtures are structurally anonymized:

1. replace every identifying or transactional literal with synthetic data;
2. preserve command families, frame ordering, byte lengths and split points;
3. recompute XOR BCC for each changed frame;
4. keep request and response directions separate;
5. verify one-byte, fixed-width, randomized and coalesced segmentation;
6. compare generated receipt text and structured fields with sanitized golden
   files;
7. run the private corpus locally as a separate, uncommitted acceptance check.

Never commit private RAW, response RAW, photographs, PCAPs, hashes, addresses,
merchant identifiers, fiscal numbers, device identifiers, dates, counters,
product text or real monetary values.

## Known limitations

- Command roles are reverse-engineered from two document examples, not an
  authenticated RCH command specification.
- Printer-generated header, heading, fiscal footer and device metadata cannot
  be reconstructed from bytes that are absent.
- The commercial payment method and VAT fields are not explicit in the
  supplied request stream.
- Response success/error semantics remain unknown.
- Encodings outside the observed one-byte printable subset remain unknown.
- More document types, discounts, returns, cancellations, non-cash payments
  and device-error flows require additional correlated evidence.
