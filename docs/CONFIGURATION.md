# Configuration

Production configuration is `/etc/commercialrchproxy/commercialrchproxy.conf`. The format is strict UTF-8 `KEY=VALUE`; duplicate and unknown keys fail startup. Shell expansion is not supported.

| Key | Default | Meaning |
|---|---:|---|
| `LISTEN_IP` | `192.0.2.231` | RFC 5737 placeholder; replace with a specific local IPv4 address; wildcard/multicast is rejected |
| `LISTEN_PORT` | `23` | Management-facing port used by the TCP implementation, range 1-65535; TCP is `UNCONFIRMED` for the installed device pending NET-2 |
| `PRINTER_IP` | `192.0.2.251` | RFC 5737 placeholder; replace with the physical Print! F IPv4 address |
| `PRINTER_PORT` | `23` | Device-facing port used by the TCP implementation, range 1-65535; RCH documents Ethernet port 23 but not the IP transport in the accessible sources |
| `OUTPUT_DIR` | `/var/lib/commercialrchproxy/jobs` | Absolute archive root |
| `LOG_DIR` | `/var/log/commercialrchproxy` | Absolute structured-log directory |
| `CONNECTION_TIMEOUT_SEC` | `30` | Upstream connect and write-drain operational bound |
| `RESPONSE_TIMEOUT_SEC` | `10` | Tail-drain/first-response fallback bound; calibrate from PCAP |
| `JOB_IDLE_TIMEOUT_MS` | `1000` | Short archive fallback used only when no observed response/document/partial-frame state is pending; otherwise combined with `RESPONSE_TIMEOUT_SEC` |
| `SAVE_RAW` | `true` | Mandatory request and response RAW copies; `false` is rejected |
| `SAVE_TECHNICAL_TXT` | `true` | Mandatory directional technical transcript and machine-readable JSONL receive timeline; `false` is rejected |
| `SAVE_CLEAN_TXT` | `true` | Publish byte-identical `.PULITO.txt` and `.receipt.txt` sidecars; recognized streams contain captured human fields under inferred command semantics |
| `SAVE_PDF` | `true` | Publish a labelled proxy-rendered PDF sidecar from the same conservative captured-field model |
| `SAVE_JSON` | `true` | Mandatory forensic manifest; `false` is rejected in the current release |
| `HASH_ALGORITHM` | `sha256` | Only `sha256` is accepted in the current release |
| `DEBUG` | `false` | Enable debug-level application behavior |
| `DEBUG_HEXDUMP` | `false` | Request bounded payload hexdump logging |
| `DEBUG_PCAP` | `false` | Reserved; external PCAP tooling is still required |
| `LOG_PAYLOAD` | `false` | Second explicit gate required for hexdump output |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |
| `RETENTION_DAYS` | `0` | `0` means no deletion; 0.2.0 does not schedule pruning |
| `MAX_PAYLOAD_BYTES` | `67108864` | Per-fallback-job combined directional capture cap |
| `RENDERER_PAPER_WIDTH_MM` | `79.5` | Provisional brochure-derived PDF width; configure and verify on the installed device |
| `RENDERER_CHARACTERS_PER_LINE` | `48` | Provisional brochure maximum used for wrapping; physical fidelity remains unconfirmed |
| `SHUTDOWN_GRACE_SEC` | `15` | Graceful active-session drain before cancellation |

The proxy and printer endpoints may not be identical. Output and log paths must be absolute and may not be a filesystem root.

## Validate

```bash
sudo ./scripts/check_config.sh
```

This checks parsing, local IP assignment, directories, permissions, space, and service/socket state. It does not open a printer or proxy data connection. No live connect probe is provided: even an empty session has not been proven inert for the installed firmware or unknown transport behavior.

## Network address

The application never adds `LISTEN_IP`. Prefer the site's normal network
manager for native persistence. When an explicitly managed secondary address
is appropriate, the separate `manage_secondary_ip.sh` helper can add exactly
that address and install its own oneshot service. It does not run automatically
from application install/update/start.

```bash
sudo apt-get install -y iputils-arping
sudo ./scripts/manage_secondary_ip.sh install
sudo ./scripts/manage_secondary_ip.sh check
```

The helper requires an existing direct/on-link route to `PRINTER_IP`, derives
a unique prefix already present on that interface, and performs ARP duplicate
detection. It does not infer `/24`, alter routes/firewall/DNS, or establish that
the address plan is authorized or collision-free for the future. See
[secondary network address](NETWORK_ADDRESS.md).

Startup reports:

```text
Cannot bind 192.0.2.231:23. The IP address is not assigned to this host.
```

when the address is unavailable.
