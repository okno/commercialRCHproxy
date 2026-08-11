# Observed RCH document types

## Scope, evidence, and public-fixture redaction

This document records the structure of three paper documents visible in the
supplied photograph of output attributed to an RCH Print! F. It is a
conservative classification aid, not a protocol specification or legal
opinion.

The initial private working transcription captured literal values only long
enough to analyze the layouts. Before these repository fixtures were
published, all merchant identity, company, address, phone, tax identifier,
device identifier, product, monetary amount, table, document counter, date,
and time values were replaced with obvious format-preserving fictitious
placeholders. The values shown in this file and in `tests/fixtures/photo_*`
are therefore **not** values observed in the photograph.

Evidence labels used here:

- **OBSERVED STRUCTURE**: a heading, label, ordering, relationship, or layout
  feature directly visible in the photograph.
- **SYNTHETIC PLACEHOLDER**: a public-fixture value substituted during
  redaction. It carries no factual claim about the photographed transaction.
- **INFERRED**: a plausible interpretation of multiple observed structural
  facts, not established by the photograph alone.
- **UNCONFIRMED**: requires authenticated RCH documentation, a raw protocol
  capture, a printer response, or an operational test.

Important limits:

- Horizontal spacing and separator length remain approximate because of
  camera perspective.
- The photograph does not expose an RCH command identifier, XML7 field,
  response status, storage result, transmission result, or job boundary.
- A printed title identifies what the paper says. It does not prove fiscal
  validity, electronic memorization, transmission, authenticity, or the
  business operation that caused the print.
- The detailed Print! F protocol pages listed by the
  [official RCH protocol-manual index](https://support.rch.it/docs/print-f/manuale-protocollo/)
  require authentication. No inaccessible command or subtype identifier is
  invented here.

## Sanitized common header example

The photograph shows a centered merchant header with one larger first line
and smaller lines beneath it. The following literal values are all
**SYNTHETIC PLACEHOLDERS**; only the six-line structure and styling are
photo-derived:

```text
HOTEL ESEMPIO
SOCIETA ESEMPIO S.R.L.
VIA ESEMPIO N.4
00000 CITTA -XX-
TELEFONO 0000-0000000
C.F. - P.IVA 00000000000
```

## Candidate labels used by the proxy

Only the printed headings and layout markers are **OBSERVED STRUCTURE**. When
similar text is found in an unvalidated payload, the proxy may emit
low-confidence candidate labels. Such a heuristic result is **INFERRED**, is
not official RCH terminology, and must not populate authoritative
`document_type`.

| Printed heading/layout | `candidate_printed_class` | `candidate_observed_variant` | Status |
|---|---|---|---|
| `DOCUMENTO GESTIONALE`, compact/table markers | `documento_gestionale` | `compact_table_summary` | Heading/layout observed; candidate assignment inferred |
| `DOCUMENTO COMMERCIALE` / `di vendita o prestazione` | `documento_commerciale` | `sale_or_service` | Heading wording observed; candidate assignment inferred |
| `DOCUMENTO GESTIONALE`, payment/VAT-detail markers | `documento_gestionale` | `payment_vat_detail` | Heading/layout observed; candidate assignment inferred |

For all three rows in 0.1.0, authoritative `document_type` is `null`.
`preconto`, `ristampa`, `copia`, `duplicato`, and similar business-role labels
are deliberately not used as canonical types because the photograph does not
establish them.

## Document G1: compact management/table summary

### Identity and sanitized transcription

The printed title `DOCUMENTO GESTIONALE` and footer pattern
`DOC.GESTIONALE N. <counter>` are **OBSERVED STRUCTURE**. The candidate class
is `documento_gestionale`; the candidate variant is
`compact_table_summary`. A possible role such as a table bill is **INFERRED**
and **UNCONFIRMED**.

Every business or transaction value in this transcription is a
**SYNTHETIC PLACEHOLDER**:

```text
                  HOTEL ESEMPIO
             SOCIETA ESEMPIO S.R.L.
                VIA ESEMPIO N.4
                00000 CITTA -XX-
              TELEFONO 0000-0000000
             C.F. - P.IVA 00000000000

              DOCUMENTO GESTIONALE

                                         EURO
Prodotto di esempio                       0,00
TOT                                      0,00

Tavolo: 00-X

                 01-01-2026 12:00
          DOC.GESTIONALE N. 0001-0003

                    XXXXXXXXXXX
```

Observed structural characteristics:

- centered merchant header and document title;
- one item row, a currency heading, and a `TOT` row;
- a `Tavolo:` field;
- footer date/time and management-counter fields;
- an unlabelled terminal-shaped identifier line without an `RT` prefix;
- visibly larger/taller total and table lines;
- no payment, change, VAT-detail, QR, barcode, logo, or dashed separator.

The product, amount, table code, date/time, counter, and terminal-shaped string
above are placeholders, not observations.

### Conservative metadata

```json
{
  "document_type": null,
  "candidate_printed_class": "documento_gestionale",
  "candidate_observed_variant": "compact_table_summary",
  "candidate_classification_source": "content_keyword_fallback",
  "candidate_classification_confidence": 0.35,
  "candidate_classification_evidence": "INFERRED",
  "protocol_identifier": null,
  "business_role": null,
  "legal_status": "unverified"
}
```

## Document C1: commercial document for sale or service

### Identity and sanitized transcription

The two-line heading `DOCUMENTO COMMERCIALE` / `di vendita o prestazione` and
footer pattern `DOCUMENTO N. <counter>` are **OBSERVED STRUCTURE**. The
candidate class is `documento_commerciale`; the candidate variant is
`sale_or_service`. Legal validity, RT storage, and transmission status remain
**UNCONFIRMED**.

Every business or transaction value in this transcription is a
**SYNTHETIC PLACEHOLDER**:

```text
                  HOTEL ESEMPIO
             SOCIETA ESEMPIO S.R.L.
                VIA ESEMPIO N.4
                00000 CITTA -XX-
              TELEFONO 0000-0000000
             C.F. - P.IVA 00000000000

              DOCUMENTO COMMERCIALE
              di vendita o prestazione

DESCRIZIONE                         IVA   Prezzo(€)

Prodotto di esempio                  00%       0,00
#
#Tavolo: 00-X
#
------------------------------------------------
TOTALE COMPLESSIVO                            0,00
di cui IVA                                   0,00

Pagamento contante                            0,00
Importo pagato                                0,00

                 01-01-2026 12:00
              DOCUMENTO N. 0001-0001

                  RT XXXXXXXXXXX
```

Observed structural characteristics:

- two-line centered document heading;
- `DESCRIZIONE`, `IVA`, and `Prezzo(€)` columns;
- one item row with a percentage-shaped VAT field and price field;
- three literal hash lines, the middle one carrying `Tavolo:`;
- a dashed separator before totals;
- `TOTALE COMPLESSIVO`, `di cui IVA`, `Pagamento contante`, and
  `Importo pagato` rows;
- footer date/time and commercial-counter fields;
- a stylized `RT` immediately before a terminal-shaped identifier;
- no `RESTO`, QR, barcode, logo, or explicit quantity.

The item, rate, amounts, table, date/time, counter, and identifier above are
placeholders. The printed phrase is retained because replacing it with a
legal label such as "fiscal receipt" would add a claim the image does not
prove.

### Conservative metadata

```json
{
  "document_type": null,
  "candidate_printed_class": "documento_commerciale",
  "candidate_observed_variant": "sale_or_service",
  "candidate_classification_source": "content_keyword_fallback",
  "candidate_classification_confidence": 0.50,
  "candidate_classification_evidence": "INFERRED",
  "protocol_identifier": null,
  "business_role": null,
  "legal_status": "unverified"
}
```

## Document G2: management document with payment and VAT detail

### Identity and sanitized transcription

The title `DOCUMENTO GESTIONALE`, footer pattern
`DOC.GESTIONALE N. <counter>`, and a body reference pattern
`N. <counter>` are **OBSERVED STRUCTURE**. The candidate class is
`documento_gestionale`; the candidate variant is `payment_vat_detail`.
Possible roles such as a copy or post-payment detail remain **INFERRED** and
**UNCONFIRMED**.

Every business or transaction value in this transcription is a
**SYNTHETIC PLACEHOLDER**:

```text
                  HOTEL ESEMPIO
             SOCIETA ESEMPIO S.R.L.
                VIA ESEMPIO N.4
                00000 CITTA -XX-
              TELEFONO 0000-0000000
             C.F. - P.IVA 00000000000

              DOCUMENTO GESTIONALE

                                         EURO
Prodotto di esempio                       0,00 A
TOT                                      0,00

Contanti                                 0,00
RESTO                                    0,00
------------------------------------------------
Aliquota IVA             Imponibile         IVA
A 00% 00%                      0,00         0,00
------------------------------------------------
TOT                            0,00         0,00

Tavolo: 00-X

01\01\26          12:02             N. 0001-0001

                 01-01-2026 12:00
          DOC.GESTIONALE N. 0001-0004

                    XXXXXXXXXXX
```

Observed structural characteristics:

- an item amount followed by the opaque marker `A`, then a `TOT` row;
- `Contanti` and `RESTO` rows;
- `Aliquota IVA`, `Imponibile`, and `IVA` columns between separators;
- a VAT-detail row containing `A` and two percentage-shaped fields;
- a VAT totals row;
- a `Tavolo:` field;
- a body date using backslashes, a body time, and a body reference;
- a separate footer date/time and management counter;
- a terminal-shaped identifier without an `RT` prefix;
- no QR, barcode, or logo.

The placeholder row `A 00% 00%` deliberately retains two distinct
percentage-shaped positions. Neither should be discarded or assigned a tax
or department meaning without source-backed mapping. The placeholder body
time differs from the placeholder footer time to preserve the observed fact
that there were two distinct source timestamps; neither placeholder is the
original timestamp.

### Conservative metadata

```json
{
  "document_type": null,
  "candidate_printed_class": "documento_gestionale",
  "candidate_observed_variant": "payment_vat_detail",
  "candidate_classification_source": "content_keyword_fallback",
  "candidate_classification_confidence": 0.40,
  "candidate_classification_evidence": "INFERRED",
  "protocol_identifier": null,
  "business_role": null,
  "legal_status": "unverified"
}
```

## Cross-document structural comparison

All literal business/transaction values in this table are synthetic. They are
reused consistently to preserve observed equality and reference relationships
without publishing the source values.

| Feature | G1 compact management | C1 commercial | G2 detailed management |
|---|---|---|---|
| Printed class | `DOCUMENTO GESTIONALE` | `DOCUMENTO COMMERCIALE` / second heading | `DOCUMENTO GESTIONALE` |
| Item placeholder | `Prodotto di esempio` | Same | Same |
| Amount placeholder | `0,00` | `0,00` | `0,00` |
| Table placeholder | `Tavolo: 00-X` | `#Tavolo: 00-X` | `Tavolo: 00-X` |
| VAT shape | Not visible | one percentage field | literal `A <rate> <rate>` shape |
| VAT amount/base | Not visible | VAT amount row | VAT base, amount, and totals rows |
| Payment/change | Not visible | payment rows, no change | cash and `RESTO` rows |
| Footer placeholder | `01-01-2026 12:00` | Same | Same |
| Extra body time | None | None | distinct placeholder `01\01\26 12:02` |
| Counter placeholder | `0001-0003` | `0001-0001` | `0001-0004` |
| Body reference | None | None | matches C1 placeholder counter |
| Final identifier | `XXXXXXXXXXX` | `RT XXXXXXXXXXX` | `XXXXXXXXXXX` |

Observed relationships, represented by consistent placeholders:

- merchant header, item, amount, table identifier, and terminal-shaped string
  match across the three papers;
- the detailed management body reference matches the commercial document
  counter;
- two management counters and one commercial counter are distinct;
- only the commercial paper prefixes the final identifier with stylized `RT`;
- the detailed document has a body timestamp distinct from its footer time.

These correlations make a shared operational flow plausible, but that is
**INFERRED**. The print order, session grouping, business role, counter
namespace, marker meanings, and memorization/transmission status remain
**UNCONFIRMED**. The proxy must not merge papers solely because human-visible
fields correlate; a documented or observed protocol boundary must decide job
identity.

## Authoritative classification and candidate precedence

Authoritative `document_type` may be populated only after the applicable
protocol/XML/response gates pass and evidence is traceable to an official
identifier. Candidate evidence is considered from strongest to weakest:

1. documented RCH protocol command or document identifier;
2. documented XML7 element/attribute after XML validation gates pass;
3. documented printer response/status identifying the class;
4. observed request/response state and documented job boundary;
5. distinctive content structure;
6. printed keywords as a fallback;
7. `null` when evidence remains insufficient.

The classifier records at least:

```text
document_type
candidate_printed_class
candidate_observed_variant
candidate_classification_source
candidate_classification_confidence
candidate_classification_evidence
```

In 0.1.0, `document_type` remains `null`. A renderer heuristic must never
rewrite captured evidence or authoritative classification.

## Conservative keyword fallbacks

These rules recognize the photographed structures when stronger evidence is
unavailable. They are not fiscal or protocol assertions.

### Commercial fallback

Require both `DOCUMENTO COMMERCIALE` and `VENDITA O PRESTAZIONE`. Candidate:

```text
document_type=null
candidate_printed_class=documento_commerciale
candidate_observed_variant=sale_or_service
candidate_classification_source=content_keyword_fallback
candidate_classification_confidence=0.50
candidate_classification_evidence=INFERRED
```

### Detailed management fallback

Require `DOCUMENTO GESTIONALE` plus `RESTO`, `ALIQUOTA IVA`, and `IMPONIBILE`.
Candidate:

```text
document_type=null
candidate_printed_class=documento_gestionale
candidate_observed_variant=payment_vat_detail
candidate_classification_source=content_keyword_fallback
candidate_classification_confidence=0.40
candidate_classification_evidence=INFERRED
```

### Compact table-summary fallback

Require `DOCUMENTO GESTIONALE` plus table/summary structure such as `TAVOLO:`,
`TOT`, and the management-counter label, while the complete payment/VAT marker
set is absent. Candidate:

```text
document_type=null
candidate_printed_class=documento_gestionale
candidate_observed_variant=compact_table_summary
candidate_classification_source=content_keyword_fallback
candidate_classification_confidence=0.35
candidate_classification_evidence=INFERRED
```

`DOCUMENTO GESTIONALE` alone is insufficient to assign either photographed
subtype. If subtype markers are missing, authoritative `document_type` remains
`null`; at most emit `candidate_printed_class=documento_gestionale` with a
null candidate variant and low confidence.

## Fields that remain null or unverified

The following JSON is the exact conservative subset emitted by the `0.1.0`
manifest. Until supported by authenticated documentation or a real capture,
these values must not be fabricated:

```json
{
  "document_type": null,
  "protocol_identifier": null,
  "protocol_version_detected": null,
  "business_role": null,
  "legal_status": "unverified",
  "protocol_status": null,
  "printer_status": null,
  "application_success": null
}
```

Concepts such as an XML7 document type, official RCH subtype, fiscal validity,
electronic memorization/transmission status, source command, or printer
completion status are deliberately not manifest fields in `0.1.0`. Their
absence is not evidence that any of them is false.

Visual resemblance and arithmetic consistency are not substitutes for those
sources.

## Fixture-rendering requirements

These are photo-derived structural characteristics used only by the redacted
renderer fixtures. They do not authorize decoding arbitrary production
payloads or populating PULITO/PDF content:

- preserve centered header and document headings;
- preserve comma decimal shape and two fractional digits in placeholders;
- preserve the commercial document's literal hash lines;
- preserve enlarged/tall styles where the model carries them;
- preserve separators for C1 and G2 and do not add one to G1;
- preserve both G2 timestamp fields and both number-shaped fields;
- preserve the two percentage-shaped positions in the opaque `A` row;
- do not add QR, barcode, logo, quantity, payment, VAT, or `RT` fields to a
  structure that does not contain them;
- never reintroduce values from the source photograph into public fixtures.

Production PULITO/PDF human content remains empty or unavailable until an
authoritative field mapping and source traceability pass the relevant gates.
Paper width, printable width, exact font metrics, characters per line, and
printer formatting commands remain unconfirmed by the photograph.
