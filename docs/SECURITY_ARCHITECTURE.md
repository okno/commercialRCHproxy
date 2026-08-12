# Security architecture

## Assets

- Availability and intended byte integrity of the management-to-configured-device flow; installed-device application-byte transparency remains gated by C-4.
- Receipt/document payload confidentiality.
- Directional archive integrity and traceability.
- RCH signed documents, if ever retrieved.
- Configuration and endpoint correctness.

## Threats addressed

- XML external entities/DTD expansion: rejected before secure parsing.
- Path traversal: generated names and sanitized device directory.
- Symlink output redirection: root/application directory checks and no-follow temporary creation.
- Partial sidecars: same-directory temp + `fsync` + atomic replace.
- Excessive payload memory: per-job bound with explicit incomplete evidence.
- Overprivileged port bind: dedicated account plus only `CAP_NET_BIND_SERVICE`.
- Accidental payload disclosure: no payload logging unless three debug gates are intentionally enabled.
- False success/replay: no synthetic response and no store-forward/retry path.

## Residual threats

- The current TCP implementation adds no server/client authentication or encryption. Accessible RCH evidence does not establish the installed-device IP transport or its application security; NET-2 and authenticated documentation remain required.
- ARP/DNS/routing attacks are outside the application trust boundary.
- The service identity owns its archive tree, so compromise of that process can alter artifacts and matching local hashes; host root can do the same. SHA-256 is not an external timestamp or WORM anchor. Export manifests/hashes to protected off-host or WORM storage for a stronger integrity boundary.
- Local disk is not encrypted by this project.
- Resource bounds are per job; deployment-level memory, file, process, and disk quotas remain necessary.
- An idle/hostile client can consume a printer session; network ACLs and monitoring are required.
- Application timing changes are inherent in a two-connection proxy.

## systemd containment

The unit uses strict filesystem protection, private temporary/device namespaces, kernel/control-group protection, address-family restriction, syscall filters where compatible, `NoNewPrivileges`, and explicit writable data/log paths.

Review directives against the deployed Debian/systemd version with:

```bash
systemd-analyze security commercialrchproxy.service
systemd-analyze verify /etc/systemd/system/commercialrchproxy.service
```

## Retention and backups

`RETENTION_DAYS=0` disables deletion. Version 0.2.0 does not run automated pruning. Backups can contain sensitive commercial/personal data; protect, encrypt, access-control, test, and dispose of them under applicable policy.
