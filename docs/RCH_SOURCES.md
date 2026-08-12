# Official RCH sources

[OBSERVED] Evidence cut-off: 2026-08-11.

## Source policy

[INFERRED] Protocol-critical claims use only official RCH-controlled sources or direct observations from the installed device.

[INFERRED] Search snippets, article titles and navigation trees establish only the text they expose. They do not establish hidden command bodies.

[INFERRED] Material for PRINT! RT, PRINT! 3.0 RT, APE, ONDA or other models is not a substitute for Print! F documentation unless the same official source explicitly groups Print! F with those devices for the cited behavior.

[INFERRED] Anonymous website update dates are not protocol-revision dates.

## Primary source register

| ID | Status | Source | Revision/date | Access | Supported claims | Explicit limitation |
|---|---|---|---|---|---|---|
| RCH-XT-2026 | DOCUMENTED | [RCH XTools User Manual / Quick Guide](https://support.rch.it/download/28926/) | v4.0.0; DE0054A0008; 07/2026 | Public PDF | Print! F minimum firmware for XTools; Ethernet/serial selection; port 23; RCH protocol command/response UI; compatibility table; V11 XML export context | XTools compatibility is not the Print! F wire-protocol specification |
| RCH-PF-BROCHURE-2018 | DOCUMENTED | [Print! F brochure](https://www.rch.it/wp-content/uploads/2021/07/PRINT-F_2018_02-vr00.pdf) | 2018-02 rev.00 | Public PDF | Interfaces, named communication families, printer width/resolution/character capacity | Old product brochure; no framing, transport, XML7 or firmware applicability |
| RCH-PF-MANUAL | DOCUMENTED | [Print! F protocol manual](https://support.rch.it/docs/print-f/manuale-protocollo/) | Web page updated 2023-12-13; actual manual revision UNCONFIRMED | Authentication required | Official chapter hierarchy and existence of subject areas | Anonymous body contains only a login message |
| RCH-PF-REV | DOCUMENTED | [Revision register](https://support.rch.it/docs/print-f/manuale-protocollo/registro-revisioni/) | Web page updated 2023-12-14; revision content UNCONFIRMED | Authentication required | Existence of a Print! F protocol revision register | No revision row is anonymously accessible |
| RCH-PF-STRUCT | DOCUMENTED | [Protocol structure](https://support.rch.it/docs/print-f/manuale-protocollo/struttura-del-protocollo/) | Web page updated 2023-12-13 | Authentication required | Existence of an official structure chapter | No framing field is accessible |
| RCH-PF-FLOW | DOCUMENTED | [Print! F protocol flows](https://support.rch.it/docs/print-f/manuale-protocollo/flussi-di-protocollo/) | Web page updated 2023-12-13 | Authentication required | Existence of an official flow chapter | No lifecycle or timing rule is accessible |
| RCH-PF-PAPER | DOCUMENTED | [Paper-out error handling](https://support.rch.it/docs/print-f/manuale-protocollo/gestione-errore-fine-carta/) | Web page updated 2023-12-13 | Authentication required | Existence of device-specific paper-out guidance | No response or recovery bytes are accessible |
| RCH-PF-CMDS | DOCUMENTED | [Hardware-independent fiscal-printer command structure](https://support.rch.it/docs/print-f/manuale-protocollo/struttura-comandi-stampante-fiscale-indipendenti-da-hardware/) | Web page updated 2023-12-13 | Authentication required | Command-family hierarchy | No syntax is accessible |
| RCH-PF-XML7 | DOCUMENTED | [Corrispettivi XML v.7](https://support.rch.it/docs/print-f/manuale-protocollo/corrispettivi-xml-v7/) | Web page updated 2023-12-13 | Authentication required | XML v.7 subject scope | No schema, namespace, envelope or field definition is accessible |
| RCH-PF-NEW | DOCUMENTED | [New commands from firmware 8.0.8](https://support.rch.it/docs/print-f/manuale-protocollo/nuovi-comandi/) | Web page updated 2023-12-13 | Authentication required | Chapter title establishes an 8.0.8 threshold for an unspecified command set | Command identities and applicability are hidden |
| RCH-PF-PADES | DOCUMENTED | [PDF digital documents with PaDES signature](https://support.rch.it/docs/print-f/manuale-protocollo/documenti-digitali-pdf-con-firma-pades/) | Web page updated 2023-12-13 | Authentication required | Existence and title of a Print! F PaDES/digital-receipt chapter only | Does not establish installed availability or retrieval capability; command, firmware, transfer and validation details are hidden |
| RCH-PF-ERRORS | DOCUMENTED | [Print! F error-message list](https://support.rch.it/docs/print-f/manuale-protocollo/elenco-dei-messaggi-di-errore/) | Web page updated 2023-12-13 | Authentication required | Existence of a device-specific error dictionary | No code or recovery rule is accessible |
| RCH-PF-FWLOG | DOCUMENTED | [PRINT! F firmware changelog](https://support.rch.it/docs/changelog-rch/firmware/print-f-2/) | Web page updated 2025-12-15 | Authentication required | Existence of the current firmware changelog | Firmware entries are hidden anonymously |

## Official Print! F manual directory

### Core transport and flow

- [DOCUMENTED] [Protocol structure](https://support.rch.it/docs/print-f/manuale-protocollo/struttura-del-protocollo/) exists; content is gated.
- [DOCUMENTED] [Protocol flows](https://support.rch.it/docs/print-f/manuale-protocollo/flussi-di-protocollo/) exists; content is gated.
- [DOCUMENTED] [Paper-out handling](https://support.rch.it/docs/print-f/manuale-protocollo/gestione-errore-fine-carta/) exists; content is gated.

### Command families

- [DOCUMENTED] [Fiscal-printer command list](https://support.rch.it/docs/print-f/manuale-protocollo/struttura-comandi-stampante-fiscale-indipendenti-da-hardware/lista-comandi-di-tipo-stampante-fiscale/) exists; content is gated.
- [DOCUMENTED] [Daily and periodic report commands](https://support.rch.it/docs/print-f/manuale-protocollo/struttura-comandi-stampante-fiscale-indipendenti-da-hardware/comandi-di-lettura-e-azzeramento-dei-report-giornalieri-e-periodici/) exists; content is gated.
- [DOCUMENTED] [Consolidated-data read layouts](https://support.rch.it/docs/print-f/manuale-protocollo/struttura-comandi-stampante-fiscale-indipendenti-da-hardware/tracciati-per-la-lettura-dei-dati-consolidati-nella-cassa/) exists; content is gated.
- [DOCUMENTED] [LOAD-SET command list](https://support.rch.it/docs/print-f/manuale-protocollo/struttura-comandi-stampante-fiscale-indipendenti-da-hardware/lista-comandi-di-tipo-load-set/) exists; content is gated.
- [DOCUMENTED] [DUMP-ENQ commands](https://support.rch.it/docs/print-f/manuale-protocollo/struttura-comandi-stampante-fiscale-indipendenti-da-hardware/comandi-di-tipo-dump-enq/) exists; content is gated.
- [DOCUMENTED] [Programming read layouts](https://support.rch.it/docs/print-f/manuale-protocollo/struttura-comandi-stampante-fiscale-indipendenti-da-hardware/tracciati-per-la-lettura-delle-programmazioni-della-cassa/) exists; content is gated.
- [DOCUMENTED] [Command and transmission examples](https://support.rch.it/docs/print-f/manuale-protocollo/struttura-comandi-stampante-fiscale-indipendenti-da-hardware/esempi-di-comandi-e-sequenze-di-trasmissione/) exists; content is gated.

### XML v.7

- [DOCUMENTED] [VAT rates and ATECO](https://support.rch.it/docs/print-f/manuale-protocollo/corrispettivi-xml-v7/aliquote-e-codice-ateco/) exists; content is gated.
- [DOCUMENTED] [Goods and services sales](https://support.rch.it/docs/print-f/manuale-protocollo/corrispettivi-xml-v7/vendite-di-beni-e-prestazioni-di-servizi/) exists; content is gated.
- [DOCUMENTED] [Uncollected payments and discount-to-pay](https://support.rch.it/docs/print-f/manuale-protocollo/corrispettivi-xml-v7/pagamenti-non-riscossi-e-sconto-a-pagare/) exists; content is gated.
- [DOCUMENTED] [Tickets, rounding, gifts, deposits and single-use vouchers](https://support.rch.it/docs/print-f/manuale-protocollo/corrispettivi-xml-v7/ticket-arrotondamenti-omaggi-acconti-buoni/) exists; content is gated.
- [DOCUMENTED] [Permanent-memory read enablement](https://support.rch.it/docs/print-f/manuale-protocollo/corrispettivi-xml-v7/abilitazione-lettura-delle-memorie-permanenti/) exists; content is gated.
- [DOCUMENTED] [External manual returns and cancellations](https://support.rch.it/docs/print-f/manuale-protocollo/corrispettivi-xml-v7/resi-e-annulli-di-documenti-esterni-manuali/) exists; content is gated.
- [DOCUMENTED] [VAT and payment layouts](https://support.rch.it/docs/print-f/manuale-protocollo/corrispettivi-xml-v7/tracciati-iva-e-pagamenti/) exists; content is gated.

## Authentication behavior

[OBSERVED] Anonymous requests to the gated pages return HTTP success with replacement text requiring login; they do not return the protected article.

[OBSERVED] The public WordPress representation also exposes only the restriction message for those bodies.

[INFERRED] A successful HTTP status therefore does not mean protocol content was obtained.

[UNCONFIRMED] No authorized RCH account content or locally supplied RCH protocol manual is present in this workspace.

## Claim-to-implementation traceability

| Feature | Status | Source or gate | Intended implementation location |
|---|---|---|---|
| Port default 23 | DOCUMENTED | RCH-XT-2026 §4.1.1 | Configuration defaults and RCH_PROTOCOL_ASSESSMENT.md |
| Transport classification | UNCONFIRMED | NET-1 and NET-2 | proxy/session diagnostics; not an RCH parser rule |
| Framing | CONFIRMED on supplied corpus / not officially documented | RCH-PF-STRUCT plus FRAME-1 | src/commercialrchproxy/rch/framing.py validates observed delimiter, length and XOR BCC |
| Command semantics | UNCONFIRMED | RCH-PF-CMDS plus DOC-1 | src/commercialrchproxy/rch/commands.py |
| Response semantics | UNCONFIRMED | RCH-PF-FLOW plus FLOW-1 | src/commercialrchproxy/rch/responses.py |
| Error mapping | UNCONFIRMED | RCH-PF-PAPER, RCH-PF-ERRORS and ERR-1 | src/commercialrchproxy/rch/errors.py |
| XML v.7 parsing | UNCONFIRMED | RCH-PF-XML7 and XML-1 through XML-4 | src/commercialrchproxy/rch/xml7.py |
| Job boundaries | INFERRED | RCH-PF-FLOW and JOB-1 | capture/recorder.py uses observed pending-state hints; timeout remains fallback |
| Document classification | INFERRED | authenticated protocol identifiers still unavailable; private raw/photo correlation available | rch/receipt_parser.py emits evidence-labelled `commerciale`/`gestionale` only for observed command lifecycles |
| PaDES extraction | UNCONFIRMED | RCH-PF-PADES chapter title plus PADES-1 | no supported capability; consider an isolated extractor only after installed applicability, transfer, and validation are established |
| Printer layout baseline | DOCUMENTED | RCH-PF-BROCHURE-2018 | renderer configuration, subject to HW-1 |

## Source-conflict rules

[INFERRED] Newer device-specific RCH documentation outranks an older brochure for compatibility.

[INFERRED] A device capture may reveal deployed behavior but cannot silently override an official fiscal meaning; conflicts must remain documented and implementation must fail closed for semantic interpretation.

[INFERRED] Search results or manuals for related RCH models may generate test hypotheses only.

[INFERRED] Current XTools v4.0.0 compatibility outranks the generic XTools 1.6.0 release-note wording for whether XTools can download a Print! F electronic receipt.

## Update checklist

- [UNCONFIRMED] Recheck all official links before release because RCH documentation and firmware may change.
- [UNCONFIRMED] Record the installed firmware and current protocol-manual revision.
- [INFERRED] Add a source row for every new semantic rule before merging its implementation.
- [INFERRED] Store only sanitized excerpts or fixtures in Git; keep credentials, unredacted receipts, PCAPs and signed originals outside the repository unless explicitly approved.
