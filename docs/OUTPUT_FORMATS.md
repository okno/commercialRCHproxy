# Output formats

## Naming and layout

Artifacts remain backward-compatible with the existing per-capture-job layout:

```text
<OUTPUT_DIR>/<printer-ip>/YYYY/MM/DD/
  <UTC timestamp>_<job-id>.raw
  <UTC timestamp>_<job-id>.response.raw
  <UTC timestamp>_<job-id>.txt
  <UTC timestamp>_<job-id>.timeline.jsonl
  <UTC timestamp>_<job-id>.PULITO.txt
  <UTC timestamp>_<job-id>.receipt.txt
  <UTC timestamp>_<job-id>.parsed.json
  <UTC timestamp>_<job-id>.pdf                  # one document, or legacy first-document view
  <UTC timestamp>_<job-id>.document-001.pdf     # multi-document capture
  <UTC timestamp>_<job-id>.document-002.pdf
  <UTC timestamp>_<job-id>.json
```

Names are generated internally; network payload does not become a path
component. Files are published atomically with restrictive permissions. The
final `.json` is the metadata/manifest file; `.parsed.json` is the protocol and
receipt reconstruction.

The forensic chain is mandatory; presentation sidecars remain configurable:

- `SAVE_RAW=true` is required for directional RAW files;
- `SAVE_TECHNICAL_TXT=true` is required for technical TXT and the JSONL timeline;
- `SAVE_CLEAN_TXT` controls both clean-text names;
- `SAVE_PDF` controls one proxy-rendered PDF per reconstructed document plus
  the backward-compatible base/first-document PDF in a multi-document capture;
- `SAVE_JSON` is mandatory and controls manifest plus parsed JSON.

## Immutable directional RAW

### `<job>.raw`

The exact locally captured client-to-printer bytes, in directional stream
order, up to `MAX_PAYLOAD_BYTES`.

### `<job>.response.raw`

The exact locally captured printer-to-client bytes. Standalone ACK events never
enter human receipt text. One sequence-matched, BCC-valid response to the
post-payment query may produce an
explicitly `INFERRED`, suffix-only annotation; all raw response bytes remain
separate.

Validate a stored copy with:

```bash
sha256sum <job>.raw <job>.response.raw
```

and compare against `raw_sha256` and `response_raw_sha256` in the manifest.
`raw_complete=true` means only that this local capture job was not truncated by
the configured memory limit. It does not prove delivery, application
acceptance, print completion or fiscal success.

## Technical TXT

`<job>.txt` combines:

- transport/evidence caveats;
- timestamped receive observations with direction, offsets, hexadecimal and
  printable views;
- capture-confirmed frame/event counts and framing issues;
- each protocol event's direction, kind, role, evidence label and offsets;
- literal frame `DATA` views;
- generic-XML candidate analysis for unrelated/new stream shapes;
- parser, classification and unknown response-status fields.

The receive-observation section remains deliberately labelled as chunks. A
`recv()` result is not a frame. The separate application-event section is
produced by the incremental length/BCC framer.

Technical output can contain sensitive payload. Keep production permissions
and retention controls in place; do not attach it to public issues without
structural anonymization.

## Raw event timeline

`<job>.timeline.jsonl` contains one JSON object per copied receive event:

```json
{
  "byte_count": 37,
  "direction": "CLIENT -> RCH",
  "job_offset": 0,
  "local_write_drain_completed": true,
  "monotonic_ns": 123456789,
  "remote_arrival": null,
  "sequence": 1,
  "session_offset": 0,
  "sha256": "<event-sha256>",
  "timestamp": "<ISO-8601 timestamp>"
}
```

The example values are synthetic. `job_offset` indexes the current directional
RAW file; `session_offset` preserves continuity across fallback archive jobs in
one TCP session. The event SHA-256 checks that the referenced byte range still
matches. `local_write_drain_completed=true` is local asyncio progress only;
`remote_arrival` remains null without independent packet evidence.

The timeline does not duplicate payload bytes. RAW remains the immutable
source.

## Human-readable receipt text

`<job>.receipt.txt` is the explicit human-readable output.
`<job>.PULITO.txt` contains the same bytes as a backward-compatible name.

For a recognized commercial or management command sequence, the file contains
human-visible values derived from client-to-printer `DATA` plus explicitly
`INFERRED` presentation labels/prefixes such as `#`, `TOTALE`, `IMPORTO
PAGAMENTO` and the suffix-only document annotation. It never
contains frame headers, ACKs, response fields, BCCs, hexdumps or parser labels.
If one archive job contains several reconstructed documents, the text views
are separated with a form-feed boundary.

Missing merchant header, printed heading, payment method, VAT fields, printer
footer, device identifier or date are not copied from photographs or
synthesized. A total-derived payment amount and a correlated post-payment
counter suffix may be rendered only with `INFERRED` evidence; the method and
counter prefix remain null. Unsupported streams may therefore produce an empty file;
recognized but truncated streams may produce partial text with incompleteness
recorded in structured output.

The clean text is a forensic reconstruction candidate, not an official fiscal
document.

## Parsed reconstruction JSON

`<job>.parsed.json` uses schema identifier
`commercialrchproxy.parsed.v1`. Its top-level fields include:

```json
{
  "schema": "commercialrchproxy.parsed.v1",
  "parser_version": "<version>",
  "job_id": "<generated-id>",
  "session_id": "<generated-id>",
  "timestamp_start": "<ISO-8601 timestamp>",
  "timestamp_end": "<ISO-8601 timestamp>",
  "request_sha256": "<sha256>",
  "response_sha256": "<sha256-or-null>",
  "parser_status": "<status>",
  "parser_error": null,
  "protocol": {}
}
```

`protocol` contains:

- every reconstructed document and its receipt text;
- literal source-frame IDs and stream-offset ranges;
- structured candidate items, quantities, amounts, taxes, payments, totals,
  date/time/reference and metadata;
- every retained request frame, response frame and standalone ACK event up to
  the documented diagnostic caps;
- ordinal request/ACK/response candidate correlations and the independently
  checked inferred sequence relationship;
- original event/frame hex, literal one-byte `DATA` view and BCC result;
- request/response framing issues;
- evidence policy: framing/literal bytes `CONFIRMED`, command roles
  `INFERRED`, absent values `UNKNOWN`.

`complete=true` in a document means that the inferred request close sequence
was captured. It never means fiscal or printer success. Fields absent from the
stream are null/empty rather than guessed.

A response counter-like payload may contribute an `INFERRED`, suffix-only
document-number candidate. Its prefix remains null, its response source is
recorded, and receipt text labels it explicitly as `DOCUMENTO N. (solo
suffisso)` rather than presenting a complete document number.

## Metadata manifest

`<job>.json` retains the operational and integrity summary. In addition to
existing endpoints, counts, timestamps, hashes, transport status and file
paths, it records:

- capture-confirmed request/response frame counts and response ACK count;
- `framing_confirmed` for the observed directional profile;
- inferred `document_type` (`commerciale`, `gestionale`, or null);
- an ordered document summary with completeness and source ranges;
- `receipt_txt_sha256` and `parsed_json_sha256`;
- `rendered_pdf_files` and `rendered_pdf_sha256`, keyed per document when a
  capture contains more than one;
- retained and observed raw event counts, timeline completeness/error, and
  first/last retained event timestamps;
- parser status/error and render errors.

The response analyzer still leaves `application_success`, printer status and
RCH error meaning null/unknown. Local writer drain, ACK presence, a valid BCC,
an inferred close, or an empty error list must not populate those fields.
For a multi-document capture, the top-level singular `document_type` describes
the first reconstructed model for backward compatibility; the `documents`
array and numbered PDFs are authoritative for the complete ordered set.

## Proxy-rendered PDF

The PDF metadata and manifest use `PDF_PROXY_RENDERED`. It is a sidecar created
from the same conservative `DocumentModel` as the clean text; it is not a
signed, original or fiscal RCH document. Paper width and character count are
configurable rendering parameters, not proof of physical fidelity. If one
live capture job contains multiple reconstructed documents, parsed JSON and
clean text retain all of them and the service publishes numbered
`.document-001.pdf`, `.document-002.pdf`, and so on. The backward-compatible
unnumbered `.pdf` is also retained and represents the first reconstructed
document; the numbered set is authoritative for all documents. Each remains a
proxy render, never an original fiscal PDF.

An official manual hierarchy contains a PaDES-titled chapter, but the public
title does not establish installed-device availability, retrieval format,
transfer commands or signature validation. If a later `PDF_RCH_ORIGINAL`
capability passes its own gate, original bytes must be stored separately,
never rewritten and independently signature-validated.

## Offline per-document reconstruction directory

`commercialrchproxy-inspect --output-dir <root>` writes one directory for each
reconstructed document:

```text
<bounded-session-id>-<source-hash>_<document-id>/
  raw.bin
  raw_client_to_printer.bin
  raw_printer_to_client.bin
  parsed.json
  receipt.txt
  metadata.json
  raw_event_log.txt
```

`raw.bin` is a compatibility alias of `raw_client_to_printer.bin`. The two
directional RAW files are the complete grouped session copies, not
trimmed or rewritten document payloads. `metadata.json` records
`raw_scope=full_directional_session_copy`, their hashes/counts, source
artifacts and the selected document's frame IDs/start/end offsets. In archive
directory mode it also carries the manifest-derived source client IP/port,
proxy IP/port and destination printer IP/port. Direct standalone file input
has no trustworthy network metadata, so those endpoint fields remain null.
`parsed.json` contains that document, direction correlations and all bounded
protocol diagnostics. `raw_event_log.txt` prefers the source JSONL receive
timelines (falling back to legacy technical transcripts); for direct file
input it is a minimal directional size/hash record. Metadata hashes the
receipt, parsed JSON, event log and directional RAW. Existing output
directories are refused rather than overwritten, even when empty.

Directory mode reads only valid commercialRCHproxy manifests, verifies
contained regular non-symlink artifact paths and referenced RAW hashes, then
groups segments by exact `session_id` in manifest
timestamp order. Direct-file mode concatenates positional request paths in the
order supplied and repeatable `--response` paths in their supplied order. This
is explicit offline reconstruction, not a change to immutable service
artifacts.

Offline loading is also bounded before semantic parsing: JSON candidate,
manifest-byte and session counts have hard caps; each direction/session
defaults to 64 MiB and the complete run defaults to 256 MiB. The latter two are
exposed as `--max-input-bytes` and `--max-total-input-bytes`. A manifest that
reports `raw_complete=false`, `timeline_complete=false`, or a capture/timeline
error produces an explicit reconstruction warning.

## Parser/storage failures

Directional RAW and timeline publication is attempted before semantic parsing.
An unexpected parser exception produces `parser_error_raw_preserved` and a
manifest/render error; it must not suppress already captured evidence or alter
forwarding. Derived outputs may be empty or partial and are never a substitute
for RAW.

Semantic diagnostics are separately bounded: at most 8 MiB per direction is
analyzed by default, frame/message/issue/document and derived-field counts have
hard caps, and issue payloads are previews. Crossing one of these semantic
bounds produces a prioritized explicit issue and a partial semantic result.
The live boundary-hint parser has a separate small per-read work budget; when
that budget is crossed it emits a structured warning and falls back to the
longer conservative timeout. Neither path truncates already stored RAW or
changes forwarded bytes.

See [receipt parser](RECEIPT_PARSER.md),
[stream reassembly](STREAM_REASSEMBLY.md), and
[protocol analysis](RCH_PROTOCOL_ANALYSIS.md).
