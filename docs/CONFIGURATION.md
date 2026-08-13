# Shared configuration reference

## Format and precedence

Both Dumper and Parser load the same configuration, normally:

```text
/etc/commercialrchproxy/commercialrchproxy.conf
```

The retained format is strict UTF-8 `KEY=VALUE`. Blank lines and `#` comments
are allowed. Duplicate keys, unknown keys, malformed values, unsupported
versions, or relative/root output paths fail startup. There is no shell
expansion.

Known process-environment variables override values from the file. The
configuration path can be selected with `--config` or
`COMMERCIALRCHPROXY_CONFIG`; an explicit CLI path is preferred for manual
diagnostics.

Public values in `.env.example` use RFC 5737 documentation addresses. They are
deliberately rejected by the production installer until replaced with
authorized private site values.

## Network and paths

| Key | Default | Validation and meaning |
|---|---|---|
| `LISTEN_IP` | `192.0.2.231` | Specific IPv4 listener address; wildcard, multicast, and IPv6 are rejected. Must already be assigned to the host. |
| `LISTEN_PORT` | `23` | Listener port, 1-65535. A port below 1024 requires only `CAP_NET_BIND_SERVICE`. |
| `PRINTER_IP` | `192.0.2.251` | Specific configured physical-device IPv4 address. |
| `PRINTER_PORT` | `23` | Device-facing port, 1-65535. RCH documentation of Ethernet port 23 does not by itself establish transport/Telnet semantics. |
| `OUTPUT_DIR` | `/var/lib/commercialrchproxy/jobs` | Absolute non-root persistent spool shared by both processes. The installer requires a normalized dedicated path, conservative path characters, safe ownership/ancestry, and a location outside protected/ephemeral OS trees. |
| `LOG_DIR` | `/var/log/commercialrchproxy` | Absolute non-root component log directory. The installer applies the same path safety checks and requires it to be separate from and non-nested with `OUTPUT_DIR`. |
| `TIMEZONE` | `Europe/Rome` | IANA timezone used for date hierarchy and human parsed names. Must exist in `zoneinfo`. |
| `CONFIG_VERSION` | `1` | Shared schema version. Only `1` is accepted in 0.3.0. |

Listen and device endpoint pairs may not be identical. The application never
adds `LISTEN_IP` to an interface. Use the host network manager or the separate
approved helper described in [NETWORK_ADDRESS.md](NETWORK_ADDRESS.md).

## Dumper transport controls

| Key | Default | Range/meaning |
|---|---:|---|
| `CONNECTION_TIMEOUT_SEC` | `30` | 0.05-3600 seconds; upstream connect and local writer-drain bound. Not an RCH application timeout. |
| `RESPONSE_TIMEOUT_SEC` | `10` | 0.05-3600 seconds; maximum opposite-direction tail after one pump reaches clean EOF. Timeout marks transport incomplete. |
| `JOB_IDLE_TIMEOUT_MS` | `1000` | 50-86400000; retained for 0.2 configuration compatibility. 0.3 capture publication uses the connection lifecycle, not idle time. |
| `BUFFER_SIZE` | `65536` | 512-4194304 bytes per stream read. Never a frame/document size. |
| `MAX_CONNECTIONS` | `32` | 1-4096 accepted session-task ceiling. The configured device still has a single exclusive upstream-session lock. |
| `PRINTER_CONNECT_ATTEMPTS` | `1` | 1-100 bounded upstream attempts before closing the client without a synthetic response. |
| `PRINTER_CONNECT_RETRY_DELAY_SEC` | `1` | 0-3600 seconds between configured attempts. No request replay/store-forward is performed. |
| `STORAGE_FAILURE_POLICY` | `continue` | `continue` prioritizes relay and logs critical capture failure; `abort` surfaces storage failure to the transport session. |
| `MAX_PAYLOAD_BYTES` | `67108864` | 1024-2147483647 combined capture/parser input bound. Crossing it makes evidence incomplete. |
| `MAX_CAPTURE_EVENTS` | `65536` | 1-100000 retained timeline-event bound shared by dumper and parser; RAW completeness is recorded separately. |
| `SHUTDOWN_GRACE_SEC` | `15` | 0.05-3600 seconds for active session tasks before cancellation. |

`MAX_CONNECTIONS` limits accepted tasks, but physical-device operations remain
serialized by one in-process lock. Network ACLs must still restrict who can
connect.

## Spool, code, and permissions

| Key | Default | Validation and meaning |
|---|---:|---|
| `JOB_CODE_START` | `1` | 0-9999999999999; first local per-printer code when no state file exists. |
| `JOB_CODE_WIDTH` | `4` | 4-32; minimum zero-padded decimal width, never a rollover modulus. |
| `PHARSED_DIRNAME` | `PHARSED` | Must remain the literal `PHARSED` in 0.3.0. |
| `FILE_MODE` | `0640` | Octal mode. Owner read/write required; no other-user or executable bits. |
| `DIRECTORY_MODE` | `0750` | Octal mode. Owner read/write/execute required; no other-user bits. |
| `SERVICE_USER` | `commercialrchproxy` | Conservative Unix account name; `root` is rejected. Installer/systemd identity contract. |
| `SERVICE_GROUP` | `commercialrchproxy` | Conservative Unix group name; `root` is rejected. |
| `FSYNC_ON_CLOSE` | `true` | Mandatory true; final publication is durability-gated. |
| `PRESERVE_TIMELINE` | `true` | Mandatory true; technical receive/forward evidence may not be disabled. |
| `CALCULATE_SHA256` | `true` | Mandatory true; ready jobs bind hashes. |

Changing `JOB_CODE_START` does not reset an existing counter. To avoid
collision/loss, never manually edit/delete `.state` on a live spool. The
installer parses `SERVICE_USER`, `SERVICE_GROUP`, `OUTPUT_DIR`, and `LOG_DIR`
as data (the config is never sourced), creates the configured account/roots,
and renders both real systemd units with that identity, working directory, and
writable sandbox paths. After changing any of those four keys, rerun the
installer/update transaction; restarting a previously rendered unit is not
sufficient. Preserve/migrate ownership and the complete old spool before an
identity or path change.

## Parser controls

| Key | Default | Range/meaning |
|---|---:|---|
| `PARSER_WORKERS` | `2` | 1-64 worker threads for distinct ready jobs. One job remains exclusively claimed. |
| `PARSER_POLL_INTERVAL_SEC` | `5` | 0.1-3600 seconds between fallback scans/wake deadlines. |
| `PARSER_RETRY_COUNT` | `3` | 0-100 retries before terminal `.parse_failed`; terminal marker occurs when attempts exceed this value. |
| `PARSER_STALE_LOCK_SEC` | `300` | 1-86400 seconds; age after which `.processing` can be displaced/reclaimed. Active workers heartbeat the marker. |
| `PARSER_USE_INOTIFY` | `true` | Attempt Linux inotify wake-ups. Polling always remains the correctness fallback. |
| `SAVE_CLEAN_TXT` | `true` | Generate one human TXT per reconstructed candidate. |
| `SAVE_PDF` | `true` | Generate one proxy-rendered PDF from the same document model. |
| `RENDERER_PAPER_WIDTH_MM` | `79.5` | 40-120 mm receipt-sidecar page width; not evidence of physical printer fidelity. |
| `RENDERER_CHARACTERS_PER_LINE` | `48` | 16-96 wrapping/layout control. |

Setting `SAVE_CLEAN_TXT` or `SAVE_PDF` false suppresses that presentation
artifact but does not change RAW/manifest validation or semantic `parsed.json`.
Production acceptance expects both true unless an explicitly documented
degraded output mode is intended.

## Mandatory evidence switches

| Key | Default | Rule |
|---|---|---|
| `SAVE_RAW` | `true` | Must remain true. |
| `SAVE_TECHNICAL_TXT` | `true` | Must remain true; in 0.3 this protects the mandatory timeline evidence contract. |
| `SAVE_JSON` | `true` | Must remain true for manifest/parsed metadata. |
| `HASH_ALGORITHM` | `sha256` | Only `sha256` is accepted. |

These keys remain for backwards-compatible configuration but cannot disable
the immutable evidence chain.

## Logging and reserved controls

| Key | Default | Meaning |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. |
| `DEBUG` | `false` | Master debug behavior gate. |
| `DEBUG_HEXDUMP` | `false` | Second gate requesting bounded payload hexdumps. |
| `LOG_PAYLOAD` | `false` | Third explicit gate; all three debug/payload gates must be true before payload hex enters debug logs. |
| `DEBUG_PCAP` | `false` | Reserved. Packet capture remains an external privileged procedure. |
| `RETENTION_DAYS` | `0` | 0 means preserve indefinitely. 0.3.0 does not schedule automatic deletion for nonzero values either. |

The Dumper and Parser create distinct structured files in `LOG_DIR` and have
distinct journald identifiers. INFO logs carry identifiers/status/path data,
not receipt payload. Debug payload logging is sensitive and should be enabled
only briefly under an approved evidence-handling procedure.

## Minimal production shape

```ini
LISTEN_IP=<approved-local-private-ipv4>
LISTEN_PORT=23
PRINTER_IP=<approved-device-private-ipv4>
PRINTER_PORT=23

OUTPUT_DIR=/var/lib/commercialrchproxy/jobs
LOG_DIR=/var/log/commercialrchproxy
TIMEZONE=Europe/Rome
CONFIG_VERSION=1

STORAGE_FAILURE_POLICY=continue
JOB_CODE_START=1
JOB_CODE_WIDTH=4
PHARSED_DIRNAME=PHARSED
PARSER_WORKERS=2
PARSER_POLL_INTERVAL_SEC=5
PARSER_RETRY_COUNT=3
PARSER_STALE_LOCK_SEC=300
PARSER_USE_INOTIFY=true
```

Copy the full [.env.example](../.env.example); do not build a production file
from this abbreviated extract.

## Validation

Configuration-only checks do not connect to the physical device:

```bash
commercialrchproxy-dumper --config /etc/commercialrchproxy/commercialrchproxy.conf \
  --check-config --json

commercialrchproxy-parser --config /etc/commercialrchproxy/commercialrchproxy.conf \
  --once
```

The Dumper check validates parsing and local listen-IP assignment. Parser
`--once` is not a pure configuration check: it safely scans/processes eligible
ready backlog. Use it only when that is intended.

The operational wrapper may perform additional path, ownership, disk-space,
and service/socket inspection:

```bash
sudo ./scripts/check_config.sh
```

No health/config command sends an empty/test connection to the configured RCH
endpoint. Even an empty session has not been proven inert.

## Configuration changes

1. Back up the file with restrictive permissions.
2. Edit with `sudoedit`.
3. run the non-invasive configuration check;
4. restart only the component affected when possible;
5. inspect both component journals and backlog state.

Endpoint/relay changes require a Dumper restart. Parser worker, timezone, or
rendering changes require a Parser restart and affect new/reparsed output only.
Changing timezone does not rename existing jobs. Never delete RAW or reset
counter state as part of a configuration rollback.
