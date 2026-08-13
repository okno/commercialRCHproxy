# Receipt Parser

The 0.3 Parser is a process independent from the Dumper. It consumes complete
directional RAW copies from atomically ready spool jobs; it never participates
in or delays the relay.

## Layers

```text
immutable request/response/timeline
  -> path/schema/hash validation
  -> complete directional streams
  -> incremental framing + standalone ACK events
  -> inferred request/response correlation
  -> inferred commercial/management document states
  -> fresh DocumentModel per candidate
  -> C/G and subtype classification
  -> TXT/PDF + parsed.json
```

Framing works across arbitrary chunk boundaries. `recv()` boundaries from the
timeline are used for time/forensics, not document segmentation or per-chunk
decoding.

## Evidence rules

- Literal frame bytes, offsets, lengths, and BCC results can be confirmed from
  the capture.
- Command roles, close transitions, styles, type, subtype, and copy
  relationships are explicitly inferred unless a literal marker supports them.
- Unknown commands remain protocol messages.
- Missing fields remain absent/null.
- Photographs validate comparisons only and never populate the model.
- ACK/response presence cannot set fiscal/application success.

## Document isolation

Every inferred opener allocates a fresh model with independent lines, items,
amounts, taxes, payments, totals, metadata, and issues. Finishing or abandoning
a candidate clears that builder before another begins. A conforming-copy
relationship records `copy_of` metadata but never inherits/copies the previous
commercial model.

This is the core defense against an earlier pre-account value leaking into a
later commercial document or an updated value leaking backwards.

## Classification

- Commercial lifecycle -> `C / DOCUMENTO COMMERCIALE`.
- Management lifecycle -> `G`.
- Management subtype candidates: `COMANDA`, `PRECONTO`, `COPIA CONFORME`, or
  `DOCUMENTO GESTIONALE GENERICO`.

Price/total presence alone never creates `C`. A conforming copy remains `G` and
requires captured same-stream relationship evidence or a literal marker.

## Incomplete input

A truncated frame produces a framing issue. A semantic candidate without the
inferred close becomes `incomplete`; captured fields can still be rendered with
that status, but no close/fiscal result is invented.

The newly supplied private job contains one such incomplete commercial
candidate. Three separately photographed management documents have no supplied
payload and cannot be reconstructed.

## Resource and safety bounds

The Parser bounds input size, timeline records/line length, frame/events,
diagnostic issues, messages, documents, and derived semantic fields. It rejects
unsafe paths, symlinks, malformed ready/manifest bindings, and hash mismatch.
These limits affect derived diagnostics/output, never authorize rewriting RAW.

For detailed transitions see
[PARSER_STATE_MACHINE.md](PARSER_STATE_MACHINE.md); for byte evidence see
[RCH_PROTOCOL_FINDINGS.md](RCH_PROTOCOL_FINDINGS.md); for outputs see
[OUTPUT_FORMATS.md](OUTPUT_FORMATS.md).
