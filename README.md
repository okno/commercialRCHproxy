# commercialRCHproxy

> [!IMPORTANT]
> **Repository autonomo congelato.** Questa codebase resta disponibile come
> ultima implementazione standalone di `commercialRCHproxy` e conserva la
> propria documentazione operativa, ma non riceverà nuove funzionalità.
> Correzioni, parser, deployment e sviluppo antifrode proseguono nel monorepo
> [RetailPrintGuard](https://github.com/okno/RetailPrintGuard), dove il proxy
> RCH rimane un processo indipendente dal database, dall'API e dalla web app.
> Per nuove installazioni usare RetailPrintGuard; mantenere questo repository
> soltanto per audit, rollback controllato e manutenzione di installazioni
> legacy già esistenti.

`commercialRCHproxy` 0.3.0 separates the network relay from receipt
reconstruction. The **Dumper** forwards an opaque full-duplex byte stream and
publishes immutable RAW jobs; the independent **Parser** consumes only
atomically completed jobs and creates human-readable TXT/PDF sidecars.

The physical RCH device remains the only fiscal/RT device. The project does
not emulate fiscal functions and does not treat a valid frame, ACK, local
socket drain, generated PDF, or parser result as proof of fiscal success.

## Evidence status

The supplied private evidence contains exactly **one partial capture job**, not
four captures: 235 request bytes, 202 response bytes, 10 structurally valid
request frames, 9 structurally valid response frames, and 10 standalone ACK
events. It supports one incomplete commercial candidate. It does not contain
separate byte streams for the photographed command, pre-account, or conforming
copy. Those three mappings are therefore `NON VERIFICABILE` from bytes.

Photographs are visual ground truth only. They are never parser input, and
photo-only merchant, fiscal, product, price, address, device, and timestamp
values are never injected into output. Private RAW, photographs, endpoints,
identifiers, values, hashes, and generated private outputs are not committed.
Public tests use synthetic, checksum-correct fixtures.

See [dump analysis](docs/RCH_DUMP_ANALYSIS.md) and the
[receipt correlation report](docs/RECEIPT_CORRELATION_REPORT.md) for the exact
evidence limits.

## Architecture

```text
management software                         physical RCH device
        |                                           |
        +---- opaque bytes --> [ Dumper ] --------->+
        +<--- opaque bytes ----[ Dumper ] <---------+
                                |
                                | atomic filesystem spool only
                                v
                    .partial -> fsync -> manifest
                              -> .ready -> rename
                                |
                                v
                            [ Parser ]
                                |
                                v
                         PHARSED/TXT + PDF
```

The processes:

- have separate entry points, logs, and systemd units;
- share no memory and communicate only through `OUTPUT_DIR`;
- read the same strict `KEY=VALUE` configuration file;
- can start, stop, fail, and restart independently;
- do not require the other process to be running;
- preserve a Parser backlog across process and host restarts.

One data-bearing transport connection produces at most one capture job. It may
contain zero, one, or several semantic documents; an empty connection produces
no misleading job. TCP `recv()` calls are timeline observations, never message
or document boundaries. Full details are in
[ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Safety properties

- The Dumper does not import the RCH semantic parser or PDF renderer.
- The Parser has no relay socket and never modifies request RAW, response RAW,
  timeline, capture manifest, or `.ready`.
- Forwarded bytes are not decoded, normalized, newline-converted, or
  re-encoded.
- Request and response streams remain separate and in directional order.
- The Dumper never synthesizes ACK, NAK, success, status, or error payloads.
- `STORAGE_FAILURE_POLICY=continue` prioritizes relay continuity and emits a
  critical storage error; `abort` is an explicit operator choice.
- Structured logs use a bounded non-blocking queue; slow log storage does not
  block the full-duplex pumps, while sustained saturation may drop older
  operational log records.
- Parser classification and command roles are evidence-labelled inferences,
  not authenticated RCH protocol definitions.
- The Parser service has no IP networking; the Dumper receives only
  `CAP_NET_BIND_SERVICE` for a privileged listen port.

No live test-print or network replay command is provided. The offline replay
tool imports RAW into the spool and performs no printer connection.

## Quick start on Debian

Public examples use RFC 5737 documentation addresses. Replace both addresses
with approved private site values before installation.

```bash
git clone https://github.com/okno/commercialRCHproxy.git
cd commercialRCHproxy
cp .env.example commercialrchproxy.conf
nano commercialrchproxy.conf
sudo ./scripts/install.sh --config "$PWD/commercialrchproxy.conf"
```

If `LISTEN_IP` is not already managed by the host network configuration, use
the separate, explicit secondary-address helper described in
[NETWORK_ADDRESS.md](docs/NETWORK_ADDRESS.md). The application installer does
not change interfaces, routes, firewall rules, or DNS.

The installed configuration remains:

```text
/etc/commercialrchproxy/commercialrchproxy.conf
```

Validate and inspect the services without opening a data connection:

```bash
sudo ./scripts/check_config.sh
sudo systemctl status commercialrchproxy-dumper.service
sudo systemctl status commercialrchproxy-parser.service
sudo journalctl -u commercialrchproxy-dumper.service -u commercialrchproxy-parser.service
```

The legacy `commercialrchproxy.service` name is a no-op compatibility launcher
that starts/stops both real units. Operate the two real units directly when
testing process independence. See [SYSTEMD.md](docs/SYSTEMD.md).

## Shared configuration

The existing `KEY=VALUE` format is retained. Both services load the same file
and reject duplicate or unknown keys. The public example begins:

```ini
LISTEN_IP=192.0.2.231
LISTEN_PORT=23
PRINTER_IP=192.0.2.251
PRINTER_PORT=23
OUTPUT_DIR=/var/lib/commercialrchproxy/jobs
LOG_DIR=/var/log/commercialrchproxy
TIMEZONE=Europe/Rome
```

0.3.0 adds durable spool, security, and Parser controls including
`JOB_CODE_START`, `JOB_CODE_WIDTH`, `PARSER_WORKERS`,
`PARSER_POLL_INTERVAL_SEC`, `PARSER_RETRY_COUNT`,
`PARSER_STALE_LOCK_SEC`, and `PARSER_USE_INOTIFY`. Mandatory evidence controls
(`SAVE_RAW`, `SAVE_TECHNICAL_TXT`, `SAVE_JSON`, `FSYNC_ON_CLOSE`,
`PRESERVE_TIMELINE`, and `CALCULATE_SHA256`) must remain true.

See the [configuration reference](docs/CONFIGURATION.md).

## Storage and naming

```text
<OUTPUT_DIR>/<printer>/YYYY/MM/DD/<CODICE_DOC>/
  file_<seconds>.<9-nanosecond-digits>.raw
  response_<seconds>.<9-nanosecond-digits>.raw
  timeline_<seconds>.<9-nanosecond-digits>.jsonl
  manifest.json
  .ready
  PHARSED/
    <CODICE_DOC>_<C|G>_<HH.MM.SS.mmm>.txt
    <CODICE_DOC>_<C|G>_<HH.MM.SS.mmm>.pdf
    parsed.json
  .parsed
```

The response RAW file is created even when empty. Unix timestamps are limited
to RAW filenames and technical metadata. Human TXT/PDF names use the configured
local timezone; exact millisecond collisions gain `_02`, `_03`, and so on.

`CODICE_DOC` is allocated by a persistent, atomic, per-printer local counter.
No reliable capture field in the supplied evidence can serve as the job key.
The code is at least four zero-padded decimal digits and continues beyond
`9999` without destructive rollover.

The intentionally literal directory name is `PHARSED`. See
[STORAGE_LAYOUT.md](docs/STORAGE_LAYOUT.md).

## Manual operation

Run each component against the same configuration:

```bash
commercialrchproxy-dumper --config /etc/commercialrchproxy/commercialrchproxy.conf
commercialrchproxy-parser --config /etc/commercialrchproxy/commercialrchproxy.conf
```

Useful Parser modes:

```bash
commercialrchproxy-parser --config /etc/commercialrchproxy/commercialrchproxy.conf --once
commercialrchproxy-parser --config /etc/commercialrchproxy/commercialrchproxy.conf \
  --job /var/lib/commercialrchproxy/jobs/192.0.2.251/YYYY/MM/DD/0001
```

Linux inotify is a wake-up optimization. A complete deterministic spool scan
always runs and periodic polling remains the correctness fallback.

## Offline tools

Inspect a RAW file or archive directory:

```bash
commercialrchproxy-inspect-dump /protected/path/file.raw --receipt --json
commercialrchproxy-inspect-dump /protected/archive --output-dir /protected/reconstruction
```

Import directional RAW into the spool without network activity:

```bash
commercialrchproxy-replay /protected/path/request.raw \
  --response /protected/path/response.raw \
  --config /etc/commercialrchproxy/commercialrchproxy.conf
```

Reparse an immutable ready job. Existing `PHARSED` output is never silently
overwritten:

```bash
commercialrchproxy-reparse /var/lib/commercialrchproxy/jobs/192.0.2.251/YYYY/MM/DD/0001 \
  --config /etc/commercialrchproxy/commercialrchproxy.conf --dry-run --code 0001

commercialrchproxy-reparse /var/lib/commercialrchproxy/jobs/192.0.2.251/YYYY/MM/DD/0001 \
  --config /etc/commercialrchproxy/commercialrchproxy.conf --backup-existing --code 0001
```

`replay` means offline spool import, never transmission to a printer. See
[MIGRATION.md](docs/MIGRATION.md) before using old 0.2 archives.

## Parser output and evidence labels

The primary type is:

- `C`: commercial-document candidate;
- `G`: management-document candidate.

Supported management subtype candidates are `COMANDA`, `PRECONTO`,
`COPIA CONFORME`, and `DOCUMENTO GESTIONALE GENERICO`. Commercial output uses
`DOCUMENTO COMMERCIALE`. These labels are conservative parser classifications;
they do not assert fiscal validity.

Every TXT/PDF begins with an explicit parser-metadata section and contains only
captured human-readable fields plus clearly labelled inferred presentation.
Missing merchant headers, VAT details, payment methods, fiscal identifiers,
and printer-generated footer fields remain absent rather than being copied
from photographs.

## Tests

```bash
./scripts/run_tests.sh
```

The suite covers configuration, byte-for-byte relay behavior, half-close and
slow streams, durable spool publication, persistent counters, Parser locking,
stale recovery, hash rejection, idempotency, process independence, framing
across arbitrary segmentation, document-state isolation, C/G/subtype
classification, TXT/PDF naming, and offline tools.

It uses a synthetic network peer and sanitized protocol fixtures. It does not
constitute a direct-versus-proxy PCAP comparison or physical RCH acceptance.
Current verified counts and platform-specific results are recorded only after
the final run in [TEST_REPORT.md](docs/TEST_REPORT.md).

## Update, migration, and rollback

Read [MIGRATION.md](docs/MIGRATION.md) before upgrading from 0.2.x. The storage
contract and service topology changed in 0.3.0. Preserve a protected backup of
the installed configuration, application, spool, and logs before activation.

An application rollback does not reverse-migrate 0.3 spool jobs. Never replay
captured fiscal traffic automatically. During an operational rollback, stop
the Dumper, restore the management software's approved direct-device target,
and validate direct operation under the site's fiscal procedure.

Known residual limits are explicit in
[KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md).

## Documentation map

- [Architecture](docs/ARCHITECTURE.md)
- [Storage contract](docs/STORAGE_LAYOUT.md)
- [Configuration](docs/CONFIGURATION.md)
- [Dump analysis](docs/RCH_DUMP_ANALYSIS.md)
- [Protocol findings](docs/RCH_PROTOCOL_FINDINGS.md)
- [Parser state machine](docs/PARSER_STATE_MACHINE.md)
- [Receipt/photo correlation](docs/RECEIPT_CORRELATION_REPORT.md)
- [Migration and rollback](docs/MIGRATION.md)
- [Known limitations](docs/KNOWN_LIMITATIONS.md)
- [Test report](docs/TEST_REPORT.md)
- [systemd operation](docs/SYSTEMD.md)

## License

MIT. See [LICENSE](LICENSE).
