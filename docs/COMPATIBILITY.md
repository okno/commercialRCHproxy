# RCH Print! F compatibility status

## Current statement

0.3.0 is a provisional, evidence-gated TCP relay/Dumper and offline Parser. It
must not be described as fully transparent or compatible with an installed
fiscal device until identity, authenticated protocol applicability, and
direct-versus-proxy physical acceptance pass.

Accessible official RCH material documents Ethernet port 23 for the Print! F
family. It does not by itself establish TCP/UDP, raw/Telnet behavior, framing,
commands, status/errors, or fiscal success.

## Layer status

| Layer | Status | Release position |
|---|---|---|
| Exact installed hardware/firmware | `UNKNOWN` | record from an RCH-approved method |
| Configured TCP relay | `IMPLEMENTED` | deployment hypothesis; physical acceptance pending |
| Full-duplex byte copy | fixture-tested | direct/proxy device equality pending |
| Frame shape/length/XOR BCC | verified on supplied complete frames | official field names/variants unknown |
| ACK separation | verified on supplied stream | scope and success meaning unknown |
| Command/document semantics | inferred | conservative Parser output only |
| Application/fiscal status | unknown | never synthesized or asserted |
| Parser process independence | implemented | final target-host lifecycle result belongs in TEST_REPORT |
| Proxy TXT/PDF | derived sidecar | not original/signed/fiscal output |

The newly supplied evidence is one incomplete 235/202-byte job with 10 request
frames, 9 response frames, and 10 ACK events. It cannot validate three missing
photographed management documents.

## Acceptance gates

### C-1: identity

- record exact model, hardware revision, device identifier, and firmware;
- map the authenticated protocol-manual revision to that firmware.

### C-2: direct baseline

- obtain complete protected bidirectional captures for each approved operation;
- include normal close/tail timing, connection reuse, and naturally occurring
  error behavior;
- keep private values/hashes outside Git.

### C-3: proxied equality

- repeat the same operations through the Dumper;
- compare reassembled client-to-device and device-to-client bytes;
- confirm management completion and physical paper output;
- verify no new retry, truncation, delay, or error behavior.

### C-4: process/storage recovery

- run Dumper with Parser stopped and later drain backlog exactly once;
- stop/restart Parser during relay without affecting bytes;
- verify partial, hash-failure, stale-lock, disk-full, and host-reboot behavior
  on the target filesystem/systemd host.

### C-5: semantic evidence

- correlate complete bytes to each photographed document without using photos
  as Parser input;
- verify isolated earlier/updated price states and separate conforming copy;
- leave unsupported fields/types unknown;
- obtain authenticated official command/status material before promoting an
  inferred role to documented.

### C-6: rollback

- demonstrate direct-device bypass and release rollback without replaying
  unknown-state requests;
- preserve 0.3 spool/counter state for matching offline tools.

## Unsupported claims

Until the gates pass, do not claim:

- official Telnet/raw/TCP semantics;
- end-to-end byte delivery merely from local drain;
- fiscal acceptance from ACK/BCC/close/output;
- support for all command/document/error variants;
- exact thermal layout;
- PaDES/original PDF retrieval or signature validation;
- four-document real-corpus reconstruction from the supplied one-job evidence.

See [RCH_PROTOCOL_FINDINGS.md](RCH_PROTOCOL_FINDINGS.md),
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md), and
[TEST_REPORT.md](TEST_REPORT.md).
