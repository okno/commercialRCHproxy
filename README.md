# commercialRCHproxy

`commercialRCHproxy` is a full-duplex relay designed for byte preservation around **RCH Print! F**. It is **not** a replacement virtual fiscal printer: the physical RCH Print! F remains the device that performs fiscal/RT functions. Application-byte transparency on the installed device is an acceptance target, not a current claim; it remains `UNCONFIRMED` until gate C-4 passes.

The current implementation accepts a TCP connection from the management software on the configured proxy endpoint, opens an independent TCP connection to the configured physical-device endpoint, and copies both streams without intentional protocol substitution. Public examples use RFC 5737 documentation addresses and must be replaced in the private site configuration:

```text
Gestionale  <-- implemented TCP hypothesis -->  commercialRCHproxy  <-- implemented TCP hypothesis -->  RCH Print! F
```

Version `0.1.0` provides a fixture-tested TCP relay and forensic archive foundation. It deliberately does **not** claim production acceptance for the installed fiscal device: authenticated protocol details, NET-2 transport identification, a direct PCAP, a proxy PCAP, installed firmware identification, and real tests of all three photographed document types are still required.

## Safety position

- No ESC/POS, POS80BL, port-9100, cut-command, `ESC`, `GS`, `DLE`, or bitmap assumption is used. The byte relay and authoritative rendering make no code-page assumption; a non-authoritative candidate classifier tries UTF-8 then CP1252 only to emit low-confidence `INFERRED` hints.
- RCH documents Print! F Ethernet operation on port 23. Accessible RCH material does **not** establish TCP, UDP, raw mode, or Telnet; the current TCP implementation is therefore `UNCONFIRMED` pending NET-2. Candidate Telnet IAC bytes are observed only as evidence and are not consumed.
- The proxy never creates `ACK`, `NAK`, `OK`, success, or fiscal-status responses.
- Forwarding is independent of XML parsing, classification, hashing, TXT, JSON, and PDF generation.
- Local write/drain completion is recorded only as implementation progress, never as proof of peer receipt. Application/fiscal success remains `null` until an authoritative RCH response decoder exists.
- Parsing and job boundaries that lack authenticated documentation or packet evidence are marked `UNCONFIRMED` or low-confidence fallback behavior.
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
- Technical TXT that labels `recv()` units as implementation stream chunks, never as RCH frames.
- Human TXT and a narrow-roll `PDF_PROXY_RENDERED` sidecar pipeline. With no authoritative RCH field mapping, production human content is intentionally unavailable/empty; photo-derived fixtures test layout only.
- Atomic `fsync` + replace publication, generated job IDs, symlink rejection, `0750` directories and `0640` files.
- JSON structured logs suitable for Wazuh ingestion.
- Hardened non-root systemd service with only `CAP_NET_BIND_SERVICE`.
- Debian/Ubuntu install, update, uninstall, service, health, config-check, test, and backup scripts.

## Evidence status

| Area | Status in 0.1.0 |
|---|---|
| RCH Ethernet and port 23 | `DOCUMENTED` in official RCH material, including XTools v4.0.0 (07/2026) |
| Deployment profile string | `OBSERVED` from the supplied request; its semantics remain `UNCONFIRMED` |
| Private deployed endpoints | `UNCONFIRMED` in the public repository; RFC 5737 placeholders are used instead |
| Full-duplex TCP implementation | `INFERRED`; fixture-tested only, which is not installed-device protocol evidence |
| TCP vs UDP on installed device | `UNCONFIRMED`; accessible RCH text establishes Ethernet and port 23, not the IP transport; TCP remains an implementation hypothesis pending NET-2 |
| Raw TCP vs Telnet | `UNCONFIRMED`; IAC is detected only as evidence and never consumed |
| RCH framing/checksum/sequence | `UNCONFIRMED`; no decoder enabled |
| XML7 root/schema/envelope | `UNCONFIRMED`; secure generic-XML candidate inspection only, with no XML7 semantic claim |
| RCH ACK/NAK/status/error codes | `UNCONFIRMED`; no semantic decoder enabled |
| Protocol-native job boundary | `UNCONFIRMED`; idle/connection close is explicitly a low-confidence fallback |
| Three photo layouts | Printed headings/layouts are `OBSERVED`; local candidate labels are `INFERRED`, `document_type` remains `null`, and no raw RCH payload fixture exists |
| Real direct-vs-proxy PCAP | `UNCONFIRMED`; not performed |
| Real fiscal-device acceptance | `UNCONFIRMED`; not performed |

## Quick start

After the repository exists remotely:

```bash
git clone https://github.com/okno/commercialRCHproxy.git
cd commercialRCHproxy
cp .env.example commercialrchproxy.conf
nano commercialrchproxy.conf
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

The installer does not alter the host network. Assign the approved private proxy address explicitly using the site's Debian network configuration before installation. The following is only a documentation example (RFC 5737, not a production address):

```bash
sudo ip address add 192.0.2.231/24 dev <interface>
```

Confirm the interface and prefix with the network administrator; do not copy `/24` blindly into a different network. Then:

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
- `JOB_IDLE_TIMEOUT_MS`: renderer/archive fallback only, not an authoritative RCH document boundary.
- `MAX_PAYLOAD_BYTES`: capture-memory bound. Forwarding continues if exceeded, while the manifest marks the archive incomplete.
- `RENDERER_PAPER_WIDTH_MM` and `RENDERER_CHARACTERS_PER_LINE`: provisional brochure-derived PDF settings; verify them on the installed device before any fidelity claim.
- `RETENTION_DAYS=0`: no automatic deletion. Version 0.1.0 does not schedule retention deletion.
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
  <timestamp>_<jobid>.PULITO.txt
  <timestamp>_<jobid>.pdf
  <timestamp>_<jobid>.json
```

- `.raw` is the local copy of bytes received on the management-facing side; `raw_complete=true` means only that the capture segment was not locally truncated.
- `.response.raw` is the local copy of bytes received on the configured-upstream-facing side; neither file proves end-to-end receipt or fiscal processing.
- `.txt` is a technical directional transcript and passive-analysis report.
- `.PULITO.txt` is intentionally empty/unavailable for production captures until an authoritative RCH field mapping passes its gates; photo-derived fixture text is not a protocol decode.
- `.pdf` is always labeled `PDF_PROXY_RENDERED`, never an official signed RCH document. Its production body is intentionally empty/unavailable until authoritative field mapping and physical comparison tests pass.
- `.json` records hashes, paths, byte counts, evidence, null status fields, boundary source, candidate labels, and render errors. `document_type` remains `null`; heuristics may populate only `candidate_printed_class` and `candidate_observed_variant`.

The official, authentication-gated manual hierarchy contains a PaDES-titled chapter, but this does not establish availability, retrieval, transport, or signature validation on the installed device. Only if PADES-1 passes may observed original bytes be archived under a distinct `PDF_RCH_ORIGINAL` path; they must never be rewritten or replaced by the proxy PDF.

See [output formats](docs/OUTPUT_FORMATS.md) and [three observed documents](docs/DOCUMENT_TYPES.md).

## Tests

```bash
./scripts/run_tests.sh
```

The fixture server is only an opaque TCP behavior fixture. It does not emulate RCH and cannot satisfy NET-2 or C-4. Tests cover arbitrary binary equality, reverse-channel equality, fragmentation, delayed/fragmented replies, server-first bytes, half-close, persistent sessions, conservative idle segmentation, offline behavior, generic-XML candidate hardening, hashing, manifest null semantics, and renderer-file readability. Candidate photo classifications do not set authoritative `document_type`.

No real RCH payload is committed. Photo-derived clean-text fixtures are labeled as transcriptions, not protocol captures.

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

See [uninstall behavior](docs/UNINSTALL.md).

## Repository separation

This project is independent from [`okno/printproxy`](https://github.com/okno/printproxy). Generic duplex and durability design ideas were reviewed, but its POS80BL/ESC-POS protocol and rendering logic were not copied. See [printproxy audit](docs/PRINTPROXY_AUDIT.md).

## License

MIT. See [LICENSE](LICENSE).
