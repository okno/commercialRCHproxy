# Output formats

## Naming and layout

```text
<OUTPUT_DIR>/<printer-ip>/YYYY/MM/DD/<UTC timestamp>_<UUID>.<suffix>
```

Names are generated internally; client data never becomes a path component.

## Request RAW

`<job>.raw` contains the bytes locally received on the client-facing side, in observed stream order, up to the capture limit. Validate the archive copy:

```bash
sha256sum <job>.raw
```

against `raw_sha256` in JSON. `raw_complete=true` means the local capture segment was not truncated by the configured capture limit; it does not prove peer receipt or fiscal processing. If the limit is exceeded, relay operation continues and the partial archive is explicitly marked.

## Response RAW

`<job>.response.raw` contains the bytes locally received on the configured-upstream-facing side and associated with the fallback job. Its hash is `response_raw_sha256`. Until NET-2 and C-4 pass, the endpoint is configured as RCH but not protocol-detected, and end-to-end delivery is not asserted.

## Technical TXT

The technical file contains:

- transport and evidence caveats;
- timestamped direction, stream offset, length, hex and printable view;
- secure generic-XML candidate result and optional reserialized technical view;
- candidate-classification source/confidence;
- unknown response semantics.

The label describes an implementation receive chunk, not an RCH frame. TCP is the current implementation transport and remains an `UNCONFIRMED` installed-device hypothesis pending NET-2; in any stream transport, receive-call segmentation has no application-protocol meaning.

## PULITO TXT

The clean file contains only human-visible lines supplied by an authoritative document model. No authoritative RCH field mapping exists in 0.1.0, so production PULITO content is intentionally empty/unavailable. It contains no `[FRAME]`, `[XML]`, `[BYTE]`, or other technical labels. Photo-derived fixture models test rendering only and are not protocol decodes. Missing totals, taxes, payment values, document numbers, dates, and fiscal fields are never created.

## Proxy-rendered PDF

The PDF metadata and JSON use `PDF_PROXY_RENDERED`. This means only that the proxy created the sidecar; it is not a fidelity or fiscal-validity claim. In production its human body is intentionally empty/unavailable until authoritative field mapping exists and physical comparison tests pass. Width `79.5 mm` and up to 48 characters per line are provisional brochure-derived defaults; installed paper, printable area, fonts, alignments, wrapping, and firmware behavior remain `UNCONFIRMED`.

An official manual hierarchy contains a PaDES-titled chapter, but the accessible title does not prove installed-device availability, retrieval, transfer format, or signature behavior. Only after PADES-1 passes may observed original bytes be saved as distinct `PDF_RCH_ORIGINAL`; those bytes must remain unchanged, be independently signature-validated, and never pass through the proxy renderer.

## JSON manifest

The manifest records configured/reported endpoints, timestamps, local capture and local-drain counts, hashes, candidate classification, generic-XML candidate status, boundary source/confidence, implementation transport outcome, unknown RCH/application status, filenames, and errors. It does not equate local `drain()` completion with peer or printer receipt.

Until the relevant authoritative gates pass, `document_type` is `null`. Heuristics may populate only `candidate_printed_class` and `candidate_observed_variant`, with an explicit evidence label and confidence. Likewise, a generic well-formed XML candidate never sets `xml7_confirmed=true`.

Unavailable values are `null`, `unknown`, or explicit `UNCONFIRMED`; they are never inferred into fiscal facts. JSON is UTF-8 and published last.
