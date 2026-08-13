# Known limitations

## Evidence and acceptance

- The newly supplied private dump contains one partial 235-byte request and
  202-byte response job, not four captures. It supports one incomplete
  commercial candidate only.
- The byte streams for the photographed management command, pre-account, and
  conforming copy are absent. Their real parsing, price isolation, type/subtype
  classification, TXT/PDF output, and byte/photo comparison are
  `NON VERIFICABILE`.
- Photographs are never Parser input. Printer-generated fields visible only on
  paper remain absent from reconstructed output.
- Synthetic tests demonstrate implementation behavior but cannot replace
  missing real evidence or physical-device acceptance.
- No final direct-versus-proxy PCAP comparison or installed-device fiscal
  acceptance is established by this repository.

## Protocol knowledge

- STX/ETX layout, decimal data length, standalone ACK events, and XOR BCC are
  verified for the supplied complete frames. This does not authenticate an
  official RCH protocol revision.
- Official meanings of the two-digit address-like field, class byte, sequence
  byte, response data, commands, statuses, and errors remain unknown or
  inferred.
- RCH documentation of Ethernet port 23 does not by itself establish TCP,
  UDP, raw mode, or Telnet negotiation. The configured TCP relay is an
  observed/deployment hypothesis.
- ACK scope is unknown. ACK, valid BCC, local drain, candidate close, and
  generated output do not prove business/fiscal success.
- NAK/error/retry behavior, paper-out, return, cancellation, discount,
  surcharge, non-cash payment, and other command variants lack adequate
  correlated evidence.
- The diagnostic one-byte text view is lossless for bytes but does not declare
  the device's general character encoding. Accented/multibyte fields outside
  the observed printable subset require new evidence.

## Capture and relay

- The Dumper is an application-level two-socket relay, not a layer-2/3
  transparent bridge. Source addresses, packets, timing, and TCP metadata
  necessarily change.
- Byte equality is tested against synthetic peers, not yet accepted against
  the physical deployed RCH device.
- Local `writer.drain()` records runtime progress only; remote arrival and
  device processing remain unconfirmed.
- A transport connection is the capture-container boundary, not a
  protocol-native document or fiscal boundary. One connection may yield zero,
  one, or multiple candidates.
- `RESPONSE_TIMEOUT_SEC` can cancel an opposite-direction tail after half-close.
  A value too short can leave capture transport-incomplete; it must be
  calibrated from authorized observations.
- Device sessions are serialized only inside one Dumper process. Running two
  Dumper instances against the same physical endpoint is unsupported and may
  bypass that lock.
- `MAX_CONNECTIONS` limits tasks, not authorized clients. Network ACLs remain
  required.
- With `STORAGE_FAILURE_POLICY=continue`, relay can continue while no complete
  durable job is published. A critical log/partial is evidence of loss risk.
  With `abort`, a storage failure can interrupt transport.
- `MAX_PAYLOAD_BYTES` and timeline limits intentionally bound resource usage;
  exceeding them produces incomplete evidence.

## Atomic storage and filesystem

- Atomic rename guarantees assume `OUTPUT_DIR` and each job's staging/final
  path are on the same filesystem with normal rename/fsync semantics.
  Filesystems or mounts with weaker durability guarantees require separate
  validation.
- A crash can leave a hidden `.partial` directory. It is reported and preserved
  but not automatically repaired, promoted, or deleted.
- The Parser verifies hashes while reading and before commit, but no mechanism
  can protect files against an administrator or storage layer that modifies
  them outside the service policy. Use protected backups and host controls.
- There is no automatic retention/pruning implementation in 0.3.0.
  `RETENTION_DAYS` remains a compatibility/configuration field.
- Disk capacity monitoring and backup scheduling are external operational
  responsibilities.
- The local counter is safe only when its `.state` directory is retained and
  all allocators coordinate on the same filesystem lock. Manual reset, copied
  split-brain roots, or unsupported network-filesystem locking can create
  collisions.

## Parser and classification

- Command/document meanings are reverse-engineered and explicitly inferred.
  A `C` candidate is not a legal/fiscal validity determination.
- Management subtype rules cover only observed/synthetic shapes. Generic or
  new layouts may remain `DOCUMENTO GESTIONALE GENERICO` or fail semantic
  reconstruction.
- A conforming-copy relationship requires same-stream evidence or a literal
  marker. A copy produced on another missing connection cannot be inferred
  merely from chronology or a photograph.
- Response frames are retained/correlated but do not drive authoritative
  document completion. Missing or delayed close evidence yields an incomplete
  candidate.
- Printer-programmed merchant header, legal heading, tax/payment fields,
  date/document number, fiscal footer, and device code may be absent from
  request RAW. The Parser does not synthesize them.
- Style/layout interpretation is provisional. Receipt paper width and character
  count are configurable, but visual similarity to the physical thermal print
  is not guaranteed.
- Parser PDFs are labelled proxy reconstructions. They are not original,
  signed, PaDES, fiscal, or legally equivalent RCH files.
- TXT/PDF semantic consistency is testable; exact fonts, glyph metrics,
  printer firmware formatting, cutting, and paper feed are not reproduced.
- Inotify is a latency optimization. Watch limits/errors fall back to polling,
  so processing may be delayed by `PARSER_POLL_INTERVAL_SEC`.
- Retry exhaustion produces `.parse_failed` in the job directory rather than
  moving immutable evidence to a separate quarantine tree. Operator reparse is
  explicit.
- A too-small `PARSER_STALE_LOCK_SEC` could permit recovery while a heavily
  stalled worker is still alive; active heartbeat and conservative values
  reduce but do not eliminate storage/clock anomaly risk. Token-fenced commit
  prevents that stale worker from publishing after a successful takeover.

## Logging

- Structured logging is decoupled from the relay by a bounded non-blocking
  queue. If the file/journal sinks remain slower than production, older queued
  operational records can be dropped to preserve relay progress.
- Component JSONL files rotate at a bounded size/backups inside the process.
  Journald/Wazuh rotation, retention, alerting, and off-host export remain host
  policy.

## Time and naming

- Nine fractional digits in RAW filenames represent integer nanoseconds; they
  do not prove the host clock physically measured at nanosecond resolution.
- Parsed names use the request timeline event covering the candidate opener,
  not a printer-generated printed timestamp. Device/POS/capture clocks can
  differ.
- Millisecond collisions are resolved only within the job's generated stem set
  with `_02`, `_03`, and later suffixes.
- Offline replay CLI uses import time for the new job. It does not import a
  historical timestamp from a legacy manifest.
- Changing `TIMEZONE` does not rename existing directories or outputs and can
  make later reparse names differ; preserve/back up old `PHARSED` first.

## Migration and rollback

- 0.2 flat archives are not automatically transformed. Explicit network-free
  import creates new jobs and preserves originals.
- The tools cannot infer missing captures or safely group legacy parts without
  reliable session metadata.
- Re-importing the same old RAW creates another new job unless an operator
  migration ledger prevents duplicates.
- 0.3 jobs are not reverse-compatible with the 0.2 layout. Application rollback
  must preserve the 0.3 spool and counter state for matching offline tools.
- Captured requests are never automatically replayed to the physical device;
  unknown fiscal outcome makes automatic replay unsafe.
- OS-account, service sandbox, output-root, or secondary-IP changes may require
  installer/network-manager actions beyond editing the shared config.

## Operations and security

- Port 23 is unencrypted. This project does not add transport authentication or
  confidentiality. Use an isolated authorized LAN, ACLs, host hardening, and
  protected storage.
- Payload/debug logs, RAW, timelines, manifests, parsed JSON, TXT, PDFs, and
  hashes can be sensitive. Repository privacy guards do not replace production
  data governance.
- The Parser service is network-isolated, but offline tools run with the
  caller's privileges and destination access. Use a protected output path.
- The secondary-IP helper is separate and privileged. Address authorization,
  VLAN/firewall/routing correctness, and long-term collision prevention remain
  operator/network responsibilities.
- Health/config checks intentionally avoid connecting to the device. They
  cannot prove live application behavior.

## Evidence required to reduce these limits

1. Complete, protected bidirectional captures for each intended document type,
   including delayed close/status traffic and session identity.
2. Correlated photos without using them as Parser input.
3. Authenticated official RCH protocol material for the installed firmware.
4. Direct and proxied PCAP comparison under an approved non-destructive plan.
5. Physical-device tests for normal flows, naturally occurring errors, slow
   responses, persistent connections, multiple documents, character encoding,
   and reboot/recovery.
6. Debian target-host validation of filesystem durability, systemd lifecycle,
   journal/SIEM rotation, backup/restore, disk-full behavior, and
   secondary-address boot.
