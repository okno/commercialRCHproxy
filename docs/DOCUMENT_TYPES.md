# Document types

Parser types are evidence-labelled reconstruction classes, not fiscal/legal
status.

| Primary type | Meaning | Activation |
|---|---|---|
| `C` | commercial-document candidate | inferred commercial command lifecycle |
| `G` | management-document candidate | inferred management envelope/printable lifecycle |

Prices or totals alone never classify a candidate as `C`.

## Subtypes

| Primary | Subtype | Conservative evidence |
|---|---|---|
| `C` | `DOCUMENTO COMMERCIALE` | commercial lifecycle; still inferred |
| `G` | `COMANDA` | captured course/covers-like markers with no totals |
| `G` | `PRECONTO` | literal marker or management item/total shape without payment/tax |
| `G` | `COPIA CONFORME` | literal marker, or separate management candidate after a C with matching captured signature and supporting fields |
| `G` | `DOCUMENTO GESTIONALE GENERICO` | management lifecycle without stronger subtype evidence |

A conforming copy is always a separate `G` candidate. It is not concatenated
with, deduplicated against, or relabelled as the preceding `C`.

Photo annotations never activate a type/subtype. See
[PARSER_STATE_MACHINE.md](PARSER_STATE_MACHINE.md) and
[RECEIPT_CORRELATION_REPORT.md](RECEIPT_CORRELATION_REPORT.md).
