# commercialRCHproxy

`commercialRCHproxy` is a full-duplex relay and forensic receipt reconstructor
for traffic observed around **RCH Print! F**. It is **not** a replacement
virtual fiscal printer: the physical RCH Print! F remains the device that
performs fiscal/RT functions. Application-byte transparency on the installed
device remains an acceptance target until gate C-4 passes.

The current implementation accepts a TCP connection from the management software on the configured proxy endpoint, opens an independent TCP connection to the configured physical-device endpoint, and copies both streams without intentional protocol substitution. Public examples use RFC 5737 documentation addresses and must be replaced in the private site configuration:

```text
Gestionale  <-- implemented TCP hypothesis -->  commercialRCHproxy  <-- implemented TCP hypothesis -->  RCH Print! F
```

The supplied private artifacts now confirm an STX/ETX frame layout, decimal
length, standalone ACK events and XOR BCC for the two correlated document
cases. The receipt parser can reconstruct the human-visible fields that are
actually present in those request streams. Command roles and document
lifecycles remain reverse-engineered (`INFERRED`), not an authenticated RCH
specification. Production acceptance still requires installed firmware
identification, authenticated protocol semantics, direct/proxy PCAP comparison
and target-device testing.

The private corpus, photographs, business values, device identifiers, network
addresses and hashes are not committed. Public tests use structurally
equivalent anonymized fixtures with recomputed checksums.

## Safety position

- No ESC/POS, POS80BL, port-9100, cut-command, `ESC`, `GS`, `DLE`, or
  bitmap assumption is used. The relay never decodes inline bytes. The supplied
  payload subset is 7-bit; Latin-1 in protocol diagnostics is only a lossless
  byte view, and non-ASCII device encoding remains `UNKNOWN`.
- RCH documents Print! F Ethernet operation on port 23. Accessible RCH material does **not** establish TCP, UDP, raw mode, or Telnet. The supplied run contains TCP-session metadata, while TCP as a general official Print! F property remains `UNKNOWN`. Candidate Telnet IAC bytes are observed only as evidence and are not consumed.
- The proxy never creates `ACK`, `NAK`, `OK`, success, or fiscal-status responses.
- Forwarding is independent of XML parsing, classification, hashing, TXT, JSON, and PDF generation.
- Local write/drain completion is recorded only as implementation progress, never as proof of peer receipt. Application/fiscal success remains `null` until an authoritative RCH response decoder exists.
- Capture-confirmed framing is separated from `INFERRED` command roles and
  `UNKNOWN` response/fiscal meanings. Timeout and connection close remain
  low-confidence archive fallbacks, never fiscal-success markers.
- There is no test-print command and no replay/store-forward path.

See [RCH protocol assessment](docs/RCH_PROTOCOL_ASSESSMENT.md) and [compatibility gates](docs/COMPATIBILITY.md) before deployment.

## Implemented vertical slice

- Configurable IPv4 listener and printer endpoints.
- Independent client-to-RCH and RCH-to-client stream pumps.
- One active upstream session at a time for the configured device endpoint; queued client streams are not consumed by the application until the lock is acquired.
- Arbitrary-byte preservation across TCP fragmentation/coalescing in the opaque fixture tests; installed-device equality remains gated by C-4.
- Client and printer half-close handling with bounded response-tail draining.
- Printer-offline behavior without false positive replies.
- Directional `.raw` and `.response.raw` capture copies, with completeness and local-write status recorded separately from peer receipt.
- SHA-256 hashes and a JSON manifest with unknown values represented as `null`/`unknown`.
- Secure generic-XML candidate inspection using `defusedxml`; DTDs and entities are rejected, and `xml7_confirmed` remains false.
- Incremental directional framing across arbitrary receive segmentation:
  `STX | AA | LLL | C | DATA | seq | BCC | ETX`, with bounded recovery and
  XOR-BCC validation. All 77 complete private-corpus frames validate.
- Standalone ACK events are preserved separately from the 38 framed printer
  responses; ACK is never treated as a receipt line or success result.
- Evidence-labelled commercial/management candidate reconstruction with
  source frame IDs and offsets. Missing printer-generated fields remain null
  or absent.
- Technical TXT that labels `recv()` units as implementation stream chunks,
  plus a machine-readable JSONL receive timeline with session offsets and
  per-event hashes.
- Human TXT and a narrow-roll `PDF_PROXY_RENDERED` sidecar pipeline. Recognized
  streams render only captured human fields; unsupported/unknown streams
  remain empty or partial rather than acquiring guessed fiscal data.
- Atomic `fsync` + replace publication, generated job IDs, symlink rejection, `0750` directories and `0640` files.
- JSON structured logs suitable for Wazuh ingestion.
- Hardened non-root systemd service with only `CAP_NET_BIND_SERVICE`.
- Debian/Ubuntu install, update, uninstall, service, health, config-check, test, and backup scripts.
- Separate opt-in helper for a persistent secondary IPv4 address; the proxy service itself never receives `CAP_NET_ADMIN`.

## Evidence status

| Area | Status in 0.2.0 |
|---|---|
| RCH Ethernet and port 23 | `DOCUMENTED` in official RCH material, including XTools v4.0.0 (07/2026) |
| Deployment profile string | `OBSERVED` from the supplied request; its semantics remain `UNCONFIRMED` |
| Private deployed endpoints | `UNCONFIRMED` in the public repository; RFC 5737 placeholders are used instead |
| Supplied-run TCP sessions | `CONFIRMED` by private capture metadata; this is not an official transport specification |
| TCP vs UDP as a general device property | `UNKNOWN`; accessible RCH text establishes Ethernet and port 23, not the IP transport |
| Raw TCP vs Telnet | `UNKNOWN`; IAC is detected only as evidence and never consumed |
| RCH frame shape and BCC | `CONFIRMED` on 77/77 private-corpus frames; official field names/semantics remain `UNKNOWN` |
| XML7 in supplied cases | `CONFIRMED` absent; secure generic-XML candidate inspection remains available for other captures |
| Standalone ACK/NAK | `CONFIRMED`: 39 ACK and zero NAK events in the private corpus; ACK scope and all status/error meanings remain `UNKNOWN` |
| Document command roles | `INFERRED` from ordered byte/photo correlation; not official RCH semantics |
| Archive boundary bug | `CONFIRMED`: one-second inactivity split one same-session commercial exchange; corrected by stream-aware pending-state hints, with timeout still a low-confidence fallback |
| Two supplied photo layouts | Stream-present human fields correlate; printer-generated header/footer/fiscal fields absent from RAW are never invented |
| Real direct-vs-proxy PCAP | `UNKNOWN`; not performed |
| Real fiscal-device acceptance | `UNKNOWN`; not performed |

## Quick start

After the repository exists remotely:

```bash
git clone https://github.com/okno/commercialRCHproxy.git
cd commercialRCHproxy
cp .env.example commercialrchproxy.conf
nano commercialrchproxy.conf
sudo apt-get update
sudo apt-get install -y iputils-arping
sudo ./scripts/manage_secondary_ip.sh install --config "$PWD/commercialrchproxy.conf"
sudo ./scripts/manage_secondary_ip.sh check --config "$PWD/commercialrchproxy.conf"
sudo ./scripts/install.sh --config "$PWD/commercialrchproxy.conf"
```

The untracked `commercialrchproxy.conf` must contain the approved private site
addresses; the repository values below are documentation placeholders only.
After installation, later edits use:

```bash
sudo nano /etc/commercialrchproxy/commercialrchproxy.conf
```

Example shape (replace both addresses):

```ini
LISTEN_IP=192.0.2.231
LISTEN_PORT=23
PRINTER_IP=192.0.2.251
PRINTER_PORT=23
```

The network helper is explicit and separate from the application installer. It
adds `LISTEN_IP` as a second IPv4 address on the existing LAN interface; it
does not create a dummy device. It derives the interface from the local route
to `PRINTER_IP` and accepts only an existing on-link prefix containing both
addresses. It never assumes `/24`, changes a route/firewall/DNS setting, or
connects to port 23. Review the displayed plan and type `INSTALL` only during
an approved network change window.

If the address is already managed persistently by the host's normal network
manager, the helper is optional; skip its two commands and run the application
installer directly. See [secondary network address](docs/NETWORK_ADDRESS.md)
for safety checks, explicit overrides, rollback, and removal. Then:

```bash
sudo systemctl restart commercialrchproxy
sudo ./scripts/healthcheck.sh
```

The health check does **not** connect to the fiscal device or to the proxy listener. It uses service/socket introspection only. Even an empty connection has not been proven inert for this protocol, so no live connect-probe option is provided.

## Configuration

The shipped example is [.env.example](.env.example). Production uses:

```text
/etc/commercialrchproxy/commercialrchproxy.conf
```

Important controls:

- `CONNECTION_TIMEOUT_SEC`: upstream connect and write-drain bound, not an RCH application timeout claim.
- `RESPONSE_TIMEOUT_SEC`: maximum tail drain after one direction ends; calibrate using PCAP.
- `JOB_IDLE_TIMEOUT_MS`: short archive fallback only. While an observed framed
  response, candidate document or partial frame remains pending, the recorder
  extends it by `RESPONSE_TIMEOUT_SEC`; neither interval is an authoritative
  RCH document boundary.
- `MAX_PAYLOAD_BYTES`: capture-memory bound. Forwarding continues if exceeded, while the manifest marks the archive incomplete.
- `SAVE_RAW`, `SAVE_TECHNICAL_TXT`, and `SAVE_JSON` must remain `true`; the
  directional evidence, receive timeline, and manifest cannot be disabled.
- `RENDERER_PAPER_WIDTH_MM` and `RENDERER_CHARACTERS_PER_LINE`: provisional brochure-derived PDF settings; verify them on the installed device before any fidelity claim.
- `RETENTION_DAYS=0`: no automatic deletion. Version 0.2.0 does not schedule retention deletion.
- `DEBUG_HEXDUMP` and `LOG_PAYLOAD`: both must be true before bounded payload hex enters logs.
- `DEBUG_PCAP`: reserved configuration flag; packet capture remains an external privileged procedure.

See [configuration reference](docs/CONFIGURATION.md).

## Outputs

Each fallback-identified job is stored below the configured output root by printer and UTC date:

```text
jobs/192.0.2.251/YYYY/MM/DD/
  <timestamp>_<jobid>.raw
  <timestamp>_<jobid>.response.raw
  <timestamp>_<jobid>.txt
  <timestamp>_<jobid>.timeline.jsonl
  <timestamp>_<jobid>.PULITO.txt
  <timestamp>_<jobid>.receipt.txt
  <timestamp>_<jobid>.parsed.json
  <timestamp>_<jobid>.pdf               # single document or legacy first-document view
  <timestamp>_<jobid>.document-001.pdf  # authoritative set for multi-document capture
  <timestamp>_<jobid>.json
```

- `.raw` is the local copy of bytes received on the management-facing side; `raw_complete=true` means only that the capture segment was not locally truncated.
- `.response.raw` is the local copy of bytes received on the configured-upstream-facing side; neither file proves end-to-end receipt or fiscal processing.
- `.txt` is a technical directional transcript and framed-event analysis.
- `.timeline.jsonl` preserves each copied receive observation with high-precision
  time, direction, job/session offsets, byte count, per-event hash and local
  drain state.
- `.receipt.txt` is the human-readable reconstruction; `.PULITO.txt` is the
  byte-identical compatibility name. Only fields present in recognized request
  payloads are rendered.
- `.parsed.json` contains framed messages, ACK events, issues, evidence-labelled
  documents, structured candidate fields and their source offsets.
- proxy PDFs are always labelled `PDF_PROXY_RENDERED`, never official signed
  RCH documents. One-document captures keep `.pdf`; multi-document captures
  keep that legacy first-document PDF and also receive one authoritative
  numbered `.document-NNN.pdf` per reconstructed model.
- `.json` is the operational manifest: hashes, paths, byte/frame/event counts,
  inferred document summaries, unknown status fields, boundary source and
  render/parser errors.

The official, authentication-gated manual hierarchy contains a PaDES-titled chapter, but this does not establish availability, retrieval, transport, or signature validation on the installed device. Only if PADES-1 passes may observed original bytes be archived under a distinct `PDF_RCH_ORIGINAL` path; they must never be rewritten or replaced by the proxy PDF.

See [output formats](docs/OUTPUT_FORMATS.md),
[capture-confirmed protocol analysis](docs/RCH_PROTOCOL_ANALYSIS.md),
[stream reassembly](docs/STREAM_REASSEMBLY.md), and
[receipt parser](docs/RECEIPT_PARSER.md).

## Offline stream inspector

Inspect one saved request (the matching `.response.raw` is selected
automatically when present):

```bash
python -m commercialrchproxy.tools.inspect_stream /path/to/job.raw --receipt
```

The installed console command is equivalent:

```bash
commercialrchproxy-inspect /path/to/job.raw --hex --ascii --timeline
```

To reconstruct legacy inactivity-split jobs, pass their archive directory. The
tool reads manifests, verifies referenced RAW hashes, groups only equal
`session_id` values, and concatenates directional segments in manifest time
order. It never merges the four distinct display sessions merely because their
bytes or timestamps are similar.

```bash
commercialrchproxy-inspect /var/lib/commercialrchproxy/jobs \
  --output-dir /var/lib/commercialrchproxy/reconstructed
```

Each reconstructed document directory contains
`raw.bin` (client-direction compatibility alias),
`raw_client_to_printer.bin`, `raw_printer_to_client.bin`, `parsed.json`,
`receipt.txt`, `metadata.json`, and `raw_event_log.txt`. The directional raw
files cover the complete grouped session; the document metadata supplies its
frame IDs and byte range. Path references from manifests are containment-
checked and an existing reconstruction directory is never silently overwritten.

Additional flags are `--response` (repeatable), `--hex`, `--ascii`, `--xml`,
`--timeline`, `--json`, `--receipt`, `--max-display-bytes`,
`--max-input-bytes`, and `--max-total-input-bytes`. The last two bound each
direction/session and the complete offline run respectively. `--json` produces
the full machine-readable session analysis. Inspector output contains sensitive
transaction evidence; use a protected destination and do not commit real
reconstructions.

## Tests

```bash
./scripts/run_tests.sh
```

The network fixture server remains an opaque TCP behavior fixture; it does not
emulate RCH and cannot satisfy NET-2 or C-4. Tests cover arbitrary-byte relay
equality, reverse-channel equality, fragmentation, delayed replies,
half-close, persistent sessions, offline behavior, XML hardening, hashing,
atomic storage and rendering.

The protocol suite additionally covers:

- the sanitized 77-frame/39-ACK corpus shape and XOR BCC;
- whole-stream, one-byte, seven-byte and deterministic-random segmentation;
- malformed header/terminator, oversize, truncation and BCC mismatch recovery;
- commercial and management golden receipt/JSON reconstruction;
- auxiliary-display exclusion and unknown-command retention;
- two documents in one stream and incomplete-document preservation;
- ordinal ACK/response association and sequence-mismatch reporting;
- delayed framed response across an idle gap and explicit late orphan capture;
- inspector JSON, per-document forensic output and same-session legacy-part
  reassembly.

No real RCH payload, photograph or private hash is committed. Public protocol
fixtures use synthetic literals, preserve the observed framing/order/counts,
and recompute every BCC. The real corpus is validated only in a protected local
run; command/document roles remain `INFERRED` even when golden tests pass. See
[the sanitized-corpus note](tests/fixtures/rch_synthetic_corpus.README.md).

## Packet-capture acceptance gate

The critical next step is a passive direct baseline while the management software communicates with the physical Print! F:

```bash
sudo tcpdump -i <interface> -s 0 -nn \
  -w rch-direct.pcap 'host 192.0.2.251'
```

Only after the direct capture satisfies NET-2 by observing TCP, and proxy insertion is approved, capture both legs:

```bash
sudo tcpdump -i <interface> -s 0 -nn \
  -w rch-proxy.pcap '(host 192.0.2.231 or host 192.0.2.251)'
```

Start with the generic IP capture above, determine the IP transport from packet headers, and use TCP-specific reconstruction only if TCP is actually observed. Exercise ordinary successful operations and naturally occurring errors; induce an error only through a dealer-approved, non-destructive workflow. Do not commit real PCAPs. They can contain commercial or personal data. Follow [the packet-capture runbook](docs/PACKET_CAPTURE.md), anonymize fixtures structurally, and update protocol logic only from `DOCUMENTED` or repeatable `OBSERVED` evidence.

## Update

```bash
cd commercialRCHproxy
sudo ./scripts/update.sh
```

The script backs up the installed configuration/application, requires a fast-forward Git update, installs dependencies, runs tests, restarts, and health-checks. See [update procedure](docs/UPDATE.md).

## Uninstall

```bash
sudo ./scripts/uninstall.sh
```

The default removal preserves archived jobs, configuration, and logs. Destructive removal is explicit and interactive:

```bash
sudo ./scripts/uninstall.sh --purge
```

If the optional secondary-address service was installed, remove it separately
with `sudo ./scripts/manage_secondary_ip.sh uninstall`. Application purge
refuses while that service still depends on `/etc/commercialrchproxy`.

See [uninstall behavior](docs/UNINSTALL.md).

## Repository separation

This project is independent from [`okno/printproxy`](https://github.com/okno/printproxy). Generic duplex and durability design ideas were reviewed, but its POS80BL/ESC-POS protocol and rendering logic were not copied. See [printproxy audit](docs/PRINTPROXY_AUDIT.md).

## License

MIT. See [LICENSE](LICENSE).
