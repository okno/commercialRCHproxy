# Security architecture

## Assets

- relay availability and intended directional byte integrity;
- confidentiality/integrity of request/response RAW and derived receipts;
- capture manifest/timeline traceability and persistent counter state;
- configuration/endpoints and service identity;
- rollback evidence for transactions with unknown fiscal outcome.

## Process separation

The Dumper and Parser share only the persistent spool:

- Dumper has network access and only `CAP_NET_BIND_SERVICE`; it contains no
  semantic Parser/PDF dependency;
- Parser has no capabilities and its systemd unit denies IP networking;
- both run non-root with `UMask=0027`, read-only config/application, and only
  job/log roots writable;
- distinct logs/journald identifiers reduce failure/audit ambiguity.

Compromise of either service identity can still affect files that identity owns;
SHA-256 is not an external/WORM integrity anchor. Export capture commitments to
protected off-host storage when a stronger boundary is required.

## Controls

- generated/sanitized path components and strict numeric `CODICE_DOC`;
- contained regular non-symlink artifacts and no-follow/exclusive creation;
- hidden partial staging, file/directory fsync, manifest hash, ready binding,
  atomic directory rename;
- Parser revalidation before `.parsed` and immutable snapshots around reparse;
- bounded payload, events, metadata, diagnostics, documents, and workers;
- no synthetic reply, network replay, automatic partial promotion, or RAW
  deletion during parsing;
- no INFO payload; bounded hexdump needs all three explicit debug gates;
- parser claim token/heartbeat/stale threshold, token-private staging, and
  lease-fenced promotion under the advisory lock;
- bounded non-blocking structured-log queue: slow sinks cannot stall relay,
  though saturation can drop operational records;
- file mode `0640`, directory `0750`, no other-user permissions.

## Residual threats

- Port 23 traffic has no added authentication/encryption. Use an isolated
  approved network and ACLs.
- ARP/routing/firewall/device compromise is outside the application boundary.
- Host root/storage administrator can alter local evidence and hashes.
- Application-level proxying necessarily changes TCP endpoints/timing/packets.
- Default storage-continue policy can preserve relay while losing complete
  capture publication; critical monitoring is required.
- Disk encryption, quota/capacity monitoring, off-host backup,
  retention/disposal, and WORM anchoring are external operations. Component
  JSONL files rotate internally by size with bounded backups; journald/Wazuh
  rotation and retention remain external.
- A hostile/idle client can consume connection/session resources; limits and
  ACLs reduce but do not remove denial-of-service risk.
- Two independently launched Dumper instances do not share the in-memory
  physical-device session lock and are unsupported.

## systemd verification

Review on the deployed Debian/systemd version:

```bash
systemd-analyze verify /etc/systemd/system/commercialrchproxy-dumper.service
systemd-analyze verify /etc/systemd/system/commercialrchproxy-parser.service
systemd-analyze security commercialrchproxy-dumper.service
systemd-analyze security commercialrchproxy-parser.service
```

The legacy launcher is no-op convenience, not the security boundary. See
[SYSTEMD.md](SYSTEMD.md).

## Sensitive evidence

RAW, timeline, manifest, parsed JSON, TXT/PDF, logs with debug payload, PCAP,
config, hashes, and photographs can contain business, personal, network,
device, and fiscal data. Restrict/encrypt/back up/dispose under applicable
policy. Never commit production artifacts.

`RETENTION_DAYS=0` disables deletion intent, and 0.3.0 has no automatic pruning
implementation. Parser/reparse never deletes capture evidence.
