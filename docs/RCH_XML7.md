# RCH Print! F XML v.7 assessment

[OBSERVED] Evidence cut-off: 2026-08-11.

## Hard boundary

[DOCUMENTED] The official Print! F protocol-manual hierarchy contains a Corrispettivi XML v.7 chapter.

[OBSERVED] The deployment request names its management profile RCH RT v.10 XML7.

[UNCONFIRMED] Accessible official RCH sources do not define that exact profile string or map it to a schema, firmware, command family, transport envelope, or on-wire representation.

[INFERRED] Well-formed generic XML is not automatically RCH XML7. A parser may report `xml_candidate_found=true` and `xml_well_formed_generic=true` without setting `xml7_confirmed=true`.

## Documented subject scope

| Subject | Status | Official RCH page | What is established |
|---|---|---|---|
| XML v.7 parent chapter | DOCUMENTED | [Corrispettivi XML v.7](https://support.rch.it/docs/print-f/manuale-protocollo/corrispettivi-xml-v7/) | Print! F documentation has an XML v.7 fiscal-data area |
| VAT and ATECO | DOCUMENTED | [VAT rates and ATECO](https://support.rch.it/docs/print-f/manuale-protocollo/corrispettivi-xml-v7/aliquote-e-codice-ateco/) | The topic is covered; tags and rules are gated |
| Goods and services | DOCUMENTED | [Goods and services sales](https://support.rch.it/docs/print-f/manuale-protocollo/corrispettivi-xml-v7/vendite-di-beni-e-prestazioni-di-servizi/) | The topic is covered; tags and rules are gated |
| Uncollected payments | DOCUMENTED | [Uncollected payments and discount-to-pay](https://support.rch.it/docs/print-f/manuale-protocollo/corrispettivi-xml-v7/pagamenti-non-riscossi-e-sconto-a-pagare/) | The topic is covered; tags and rules are gated |
| Tickets and adjustments | DOCUMENTED | [Tickets, rounding, gifts, deposits and vouchers](https://support.rch.it/docs/print-f/manuale-protocollo/corrispettivi-xml-v7/ticket-arrotondamenti-omaggi-acconti-buoni/) | The topic is covered; tags and rules are gated |
| Permanent memory | DOCUMENTED | [Permanent-memory read enablement](https://support.rch.it/docs/print-f/manuale-protocollo/corrispettivi-xml-v7/abilitazione-lettura-delle-memorie-permanenti/) | The topic is covered; command and response are gated |
| Returns and cancellations | DOCUMENTED | [External manual returns and cancellations](https://support.rch.it/docs/print-f/manuale-protocollo/corrispettivi-xml-v7/resi-e-annulli-di-documenti-esterni-manuali/) | The topic is covered; identifiers and constraints are gated |
| VAT/payment layouts | DOCUMENTED | [VAT and payment layouts](https://support.rch.it/docs/print-f/manuale-protocollo/corrispettivi-xml-v7/tracciati-iva-e-pagamenti/) | Official layouts exist; their fields are gated |

## Unknown schema and wire properties

| Property | Status | Required evidence |
|---|---|---|
| Root element | UNCONFIRMED | Authenticated RCH chapter and matching capture |
| Namespace URI | UNCONFIRMED | Authenticated RCH schema/example |
| Schema version marker | UNCONFIRMED | Authenticated RCH schema/example |
| XSD location or formal schema | UNCONFIRMED | Official downloadable schema or manual |
| XML declaration | UNCONFIRMED | Direct capture |
| Character encoding | UNCONFIRMED | Official rule and captured byte declaration |
| Byte-order mark | UNCONFIRMED | Direct capture |
| Transport envelope | UNCONFIRMED | Protocol-structure manual and direct capture |
| Length or terminator | UNCONFIRMED | Protocol-structure manual and direct capture |
| Escaping outside XML | UNCONFIRMED | Protocol-structure manual and direct capture |
| Compression or Base64 | UNCONFIRMED | Official manual and direct capture |
| Request/response XML shape | UNCONFIRMED | Flow manual and correlated capture |
| Error XML | UNCONFIRMED | Error manual and correlated capture |
| Multiple XML documents per session | UNCONFIRMED | Reassembled direct capture |
| XML equals one fiscal job | UNCONFIRMED | Flow manual and repeated captures |
| Field cardinality and ordering | UNCONFIRMED | Official schema/layouts |
| Decimal/date formats | UNCONFIRMED | Official field definitions |
| Namespace-version compatibility | UNCONFIRMED | Official revision register |

## V7 versus V11

[DOCUMENTED] RCH XTools User Manual v4.0.0, DE0054A0008, 07/2026, offers Export V11 XML for fiscal-memory and DGFE reads.

[DOCUMENTED] The Print! F protocol manual separately names Corrispettivi XML v.7.

[INFERRED] These labels describe different functions or generations until an official RCH source explicitly relates them.

[INFERRED] An observed V11 export must not be parsed with an XML7 field map, and an observed XML payload must not be labeled V11 merely because current XTools can export V11.

## Safe passive inspection

[INFERRED] XML inspection must operate only on a copy of captured client-to-printer or printer-to-client bytes.

[INFERRED] Parser output must never be fed back into the forwarding path.

[INFERRED] The original capture must retain byte offsets, direction, session identifier and timestamps so every extracted field is traceable.

[INFERRED] Before XML7 confirmation, the only permissible generic-XML observations are:

- [INFERRED] `xml_candidate_found`, based on a non-authoritative byte-range heuristic;
- [OBSERVED] candidate start/end offsets in the local capture copy;
- [OBSERVED] `xml_well_formed_generic`, meaning only that a hardened generic parser accepted the copied candidate;
- [OBSERVED] the literal root QName/local name, namespace, paths, and values found in that copy;
- [OBSERVED] parsing errors and exact source offsets.

[INFERRED] Before XML7 confirmation, the following must remain false or null:

- [UNCONFIRMED] xml7_confirmed;
- [UNCONFIRMED] fiscal meaning of a tag;
- [UNCONFIRMED] document completion;
- [UNCONFIRMED] tax/payment semantics;
- [UNCONFIRMED] protocol success;
- [UNCONFIRMED] schema-valid status.

## Security controls

[INFERRED] XML parsing must reject DTD and entity declarations, disable external entities and network resolution, and impose size/depth/node/text limits.

[INFERRED] Pretty-printing is allowed only in technical output generated from a copy.

[INFERRED] Invalid or malicious XML must be recorded as an analysis error but must not intentionally alter relay behavior. Installed-device byte equality remains subject to C-4.

[INFERRED] Logs must omit full XML payloads by default because receipts may contain personal or commercial data.

[INFERRED] A schema validator must be offline and pinned to an authenticated official RCH schema before it can influence semantic status.

## Field traceability model

| Field | Status before XML gates | Required source |
|---|---|---|
| source_direction | OBSERVED | Capture metadata |
| source_stream_offset_start/end | OBSERVED | Reassembled capture |
| source_packet references | OBSERVED | PCAP index |
| source_xml_path | OBSERVED | Hardened parse of copied XML |
| literal_value | OBSERVED | Copied XML bytes |
| semantic_name | UNCONFIRMED | Official RCH field definition |
| document_type | UNCONFIRMED; `null` | Official identifier plus capture and semantic gate |
| candidate_printed_class | INFERRED | Low-confidence content heuristic only |
| candidate_observed_variant | INFERRED | Low-confidence content heuristic only |
| tax/payment meaning | UNCONFIRMED | Official XML v.7 layout |
| protocol/job status | UNCONFIRMED | Official flow/response definition |

[INFERRED] The technical transcript may display bounded literal candidate text. Production PULITO/PDF human content remains empty/unavailable until authoritative mapping passes; renderers must not manufacture fiscal semantics.

## XML acceptance gates

### XML-1 — authoritative definition

- [UNCONFIRMED] Obtain authorized access to the official XML v.7 chapter and record the protocol-manual revision and applicable firmware.
- [UNCONFIRMED] Obtain official root, namespace, version, encoding, field cardinality and field semantics.
- [INFERRED] Acceptance requires exact section references in RCH_SOURCES.md.

### XML-2 — wire extraction

- [UNCONFIRMED] Capture direct traffic for at least three repetitions each of the observed CASE-G1, CASE-C1 and CASE-G2 paper cases defined in RCH_PROTOCOL_ASSESSMENT.md.
- [UNCONFIRMED] Reassemble each direction without using packet or receive-call boundaries.
- [UNCONFIRMED] Identify XML start/end offsets and every non-XML envelope byte.
- [INFERRED] Acceptance requires the extraction rule to work for fragmented, coalesced and back-to-back messages with no dropped or invented bytes.

### XML-3 — validation

- [UNCONFIRMED] Validate observed samples against the authenticated official definition.
- [UNCONFIRMED] Verify namespace, declared encoding, character decoding, required elements, numeric formats and repetitions.
- [INFERRED] Acceptance requires all captured conforming samples to validate and all intentionally malformed offline fixtures to fail safely.

### XML-4 — semantic mapping

- [UNCONFIRMED] Map every interpreted field to official section, XML path and source offsets.
- [UNCONFIRMED] Correlate each parsed document with the physical output and printer response.
- [INFERRED] Acceptance requires no renderer heuristic to change parser meaning.

### XML-5 — job boundary

- [UNCONFIRMED] Establish whether an XML envelope, an outer frame, a closing command or a final response terminates the document.
- [INFERRED] Acceptance requires correct separation of two back-to-back documents and must not rely solely on idle time.

## Test matrix after gates pass

| Case | Status now | Required result |
|---|---|---|
| Fragmented XML across network packets | UNCONFIRMED | One copied XML document; forwarding unchanged |
| Two XML documents coalesced in one read | UNCONFIRMED | Two traced documents if official framing permits |
| XML with declared non-UTF-8 encoding | UNCONFIRMED | Decode only according to documented rule |
| Namespace variation | UNCONFIRMED | Accept/reject only according to revisioned schema |
| DTD/entity attempt | INFERRED | Analysis rejects safely; fixture relay bytes remain equal and installed-device equality awaits C-4 |
| Truncated XML | INFERRED | `xml_well_formed_generic=false`; no fiscal status fabricated |
| Binary data adjacent to XML | UNCONFIRMED | Preserve envelope and offsets; no lossy decoding |
| Unknown tag | INFERRED | Preserve literal path/value; semantic field remains unknown |

## Current verdict

[DOCUMENTED] XML v.7 subject matter exists in the official Print! F protocol manual.

[OBSERVED] No real XML7 payload or authenticated schema is present in this workspace.

[UNCONFIRMED] The exact profile RCH RT v.10 XML7, its envelope and all fiscal field mappings remain unresolved.

[INFERRED] Current code may perform hardened, non-inline generic-XML candidate discovery only; it must not claim XML7 identity, conformance, schema validity, or fiscal interpretation.
