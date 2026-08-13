# Output formats

The authoritative 0.3 storage/naming contract is
[STORAGE_LAYOUT.md](STORAGE_LAYOUT.md). This page summarizes content semantics.

## Immutable capture layer

Each ready `CODICE_DOC` directory contains:

- `file_<seconds>.<9 digits>.raw`: exact client-to-device bytes;
- `response_<seconds>.<9 digits>.raw`: exact device-to-client bytes, present
  even when empty;
- `timeline_<seconds>.<9 digits>.jsonl`: receive/forward metadata without
  payload duplication;
- `manifest.json`: endpoints, sizes, SHA-256, completeness, errors, versions;
- `.ready`: atomic capture-commit marker bound to the manifest hash.

These files are owned by the Dumper and remain immutable to the Parser. Valid
BCC, ACK, local drain, or a ready marker does not prove fiscal success.

## Parsed layer

`PHARSED` contains one pair per reconstructed candidate:

```text
<CODICE_DOC>_<C|G>_<HH.MM.SS.mmm>[_NN].txt
<CODICE_DOC>_<C|G>_<HH.MM.SS.mmm>[_NN].pdf
```

and one technical `parsed.json`. `.parsed` in the job root commits the Parser
result and binds the `parsed.json` hash.

Unix timestamps are prohibited in human TXT/PDF filenames/content. Their time
comes from the source request timeline, converted through configured timezone.

## TXT

TXT is UTF-8 and begins with a clearly delimited Parser metadata section:

- primary type `C` or `G`;
- subtype and evidence label;
- parser state `STATO: COMPLETO` or `STATO: INCOMPLETO`;
- statement that the document is reconstructed from captured data.

The remaining text is rendered from one independent `DocumentModel`. It may
contain only captured human fields and explicitly qualified inferred
presentation. ACK, BCC, frame headers, hexdumps, JSON, and technical Unix time
never enter the operator document.

Fields absent from RAW remain absent. Photographs do not supply merchant
header, legal heading, payment method, tax values, document number, timestamp,
or footer.

## PDF

The PDF is generated from the same model as the matching TXT with configured
receipt width/line length. It is a readable proxy-rendered sidecar, not a
screen capture or hex dump. Normalized extracted PDF text should remain
semantically consistent with TXT.

It is not an original, signed, PaDES, fiscal, or legally equivalent RCH
document. Exact printer font/spacing/paper behavior remains an acceptance
limit.

## parsed.json

Schema `commercialrchproxy.pharsed.v1` records:

- capture manifest path/hash and Parser version/status;
- ordered document candidates;
- primary type, subtype, and evidence;
- candidate completeness and local capture time;
- source frame IDs and byte/timeline offsets;
- TXT/PDF names and SHA-256 values;
- semantic fields, framing/protocol issues, correlations, and evidence policy.

`complete` refers only to the inferred captured request lifecycle. It never
means printer/fiscal success.

## Parser failures

Parser-owned state is explicit:

- `.processing`: active exclusive claim;
- `.parse_attempts.json`: retry state;
- `.parse_failed`: terminal parser quarantine marker;
- `.parsed`: successful parse commit.

Partial Parser files without `.parsed` are not a committed output set. Capture
RAW/response/timeline/manifest/ready remain authoritative and unchanged.
Parser generation first uses a token-private
`.PHARSED.<claim-token>.partial` directory; only the current lease owner may
promote it to `PHARSED` and publish `.parsed` under `.parser.lock`.
