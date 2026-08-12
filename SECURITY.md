# Security policy

## Supported release

The pre-production `0.2.x` line receives security fixes. It is not certified fiscal software and has not completed device acceptance.

## Reporting

Do not open a public issue containing receipt payloads, PCAPs, credentials, customer data, tax identifiers, signed PDFs, or hotel network details. Contact the repository owner privately and provide only the minimum reproducible, anonymized evidence.

## Trust boundaries

- The physical RCH device remains authoritative for fiscal operations.
- The LAN traffic is not authenticated or encrypted by this proxy.
- IP filtering is not client identity.
- The service identity owns its archive tree, and either a compromised service process or host root can rewrite artifacts and matching manifests/hashes. SHA-256 detects mismatches only relative to the available manifest; use protected off-host/WORM storage or an external signed anchor for stronger evidence.
- A proxy-rendered PDF is not an original RCH-signed document.

## Safe defaults

- Non-root service account with only `CAP_NET_BIND_SERVICE`.
- No synthetic commands, replies, test prints, replay, or store-forward.
- Payload logging disabled.
- Automatic retention deletion disabled.
- DTD/entity XML rejected; no external resource resolution.
- Output paths generated internally; symlink output directories rejected.
- Files `0640`, directories `0750`, atomic same-directory publication.
- Default health check opens no fiscal-device or proxy data connection.

## Deployment requirements

Before production, complete the PCAP/hardware gates in `docs/COMPATIBILITY.md`, restrict clients at the network layer, use a dedicated hardened host, protect backups, monitor disk space, and test restore/integrity procedures.
