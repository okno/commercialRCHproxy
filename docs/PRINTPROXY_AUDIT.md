# Audit of `okno/printproxy`

Baseline reviewed: public `main`/`v2.0.0` commit `0ae6fc1b9249d822c3cb05a0e8a5e2e3512455e4`. The local checkout also contained substantial uncommitted user work and was treated as read-only.

## Generic design retained

- Independent bidirectional coroutines.
- Upstream open before client payload consumption.
- Opaque byte-preservation design and no synthetic ACK; installed-device equality remains gated by C-4.
- Half-close/FIN/RST/backpressure test concepts.
- Generated IDs, SHA-256, atomic publication, `fsync`, no-follow/symlink defenses.
- Dedicated service user, strict systemd sandbox, conservative uninstall.
- Strict/bounded passive analysis separated from rendering; production human output remains empty until authoritative RCH mapping exists.

The new implementation is packaged and independently written; no modified `printproxy` file is part of this repository.

## Explicitly rejected

- POS80BL, JetDirect, or port 9100 discovery/defaults.
- ESC/POS `ESC`, `GS`, `DLE`, DLE-EOT, cut scanning, code pages, bitmaps, barcode, QR, drawer, or test-print sequences.
- 42-column/80-mm/POS80 renderer assumptions.
- Store-forward/retry/replay.
- Health probes that connect to the proxy listener (which would create a real upstream session).
- Installer probes for LPR/IPP/RAW printing or hard-coded port 9100.
- Fake ESC/POS printer and real-source assets of unclear publication provenance.

## RCH-specific changes

- Both ports configurable, target defaults `23`.
- Non-root privileged bind through only `CAP_NET_BIND_SERVICE`.
- Full reverse RAW and timestamped directional transcript.
- JSON/Wazuh logs with application success distinct from transport forwarding.
- Secure generic-XML candidate observer with `xml7_confirmed=false`.
- Empty RCH command/error tables pending official/manual/capture evidence.
- Default health uses systemd/socket introspection and no printer connection.
