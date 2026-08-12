# Test report

## Environment

- Build date: 2026-08-11
- Development host: Windows, Python 3.14.5 virtual environment
- Linux packaging runner: WSL Debian, Python 3.13.5
- Target runtime: Debian/Ubuntu, Python >=3.11
- Test devices: opaque asyncio relay server plus sanitized offline protocol fixtures
- Physical RCH Print! F: not connected by the test suite

## Automated scope

| Test area | Expected | Current result |
|---|---|---|
| Config validation | Strict keys, IPv4/ports/paths, no ESC/POS keys | PASS |
| Arbitrary request bytes | Opaque TCP fixture receives byte-identical stream | PASS (fixture only; not C-4) |
| Reverse response bytes | Fixture client receives byte-identical stream | PASS (fixture only; not C-4) |
| Fragmentation/coalescing | No `recv()` boundary assumptions | PASS |
| Client half-close | Delayed response still returns within bound | PASS |
| Server-first/IAC bytes | Relayed unchanged, never negotiated/consumed | PASS |
| Persistent connection | Multiple low-confidence idle jobs supported | PASS |
| Concurrent clients | Exclusive configured-device lock prevents overlapping upstream sessions | PASS |
| Printer offline | Client receives no false success payload | PASS |
| RAW/response archive | Exact bytes and SHA-256 | PASS |
| Atomic storage | No final partial/temp files after success | PASS |
| Generic-XML candidate security | DTD/entity rejected; malformed candidate nonfatal; XML7 never asserted | PASS |
| Candidate document labels | Photo-only phrases stay non-authoritative; recognized observed command lifecycles set an explicitly `INFERRED` document type | PASS |
| Renderer fixture | Photo-derived proxy PDF is readable; this does not establish production content or physical fidelity | PASS |
| Health/config check | No live network connection attempted | PASS |
| Secondary IPv4 helper | Route/prefix/scope validation, owned/borrowed/pending state, rollback, and no port-23 probe | PASS (isolated namespace; target-host activation remains untested) |
| Tail timeout evidence | A stalled tail remains explicitly incomplete even after response bytes | PASS |
| Opposite-direction failure | A pump transport failure cancels the other pump immediately rather than waiting/forwarding further bytes | PASS |
| FIN propagation failure | Failed half-close is a transport error, never clean EOF | PASS |
| Slow archive isolation | Hash/render/fsync work does not hold transport sockets or the exclusive device-session lock | PASS |
| Mandatory forensic chain | `SAVE_RAW=false`, `SAVE_TECHNICAL_TXT=false`, and `SAVE_JSON=false` are rejected | PASS |
| Observed RCH framing | STX/ETX, decimal length, sequence position and XOR BCC accepted without using `recv()` boundaries | PASS |
| Sanitized corpus shape | 77 complete frames, 39 standalone ACK events, every BCC valid | PASS |
| TCP segmentation invariance | Whole stream, one byte, seven bytes and deterministic random chunks produce equal frame, parsed JSON and receipt results | PASS |
| Framing recovery | Bad BCC, truncation, malformed header, invalid terminator and oversize length retained as bounded issues | PASS |
| Hostile-input bounds | Analysis bytes/events/messages/issues/documents, issue previews, recorder hints and timeline events remain bounded; RAW remains separate | PASS |
| Commercial reconstruction | Sanitized command stream matches golden receipt and structured fields; display lines excluded | PASS |
| Management reconstruction | Sanitized printable-line stream matches golden receipt and structured fields | PASS |
| Missing fields | Unsupported/uncaptured date, payment method, prefix and fiscal fields remain null/empty | PASS |
| Multiple documents | Two complete candidates in one application stream remain separate | PASS |
| Request/response correlation | Standalone ACK plus ordinal response and inferred sequence check; mismatch/missing events reported | PASS |
| Idle-gap regression | ACK does not close the job; delayed framed response remains with the same request | PASS |
| Very late response | Bytes remain archived in explicit `orphan_late_response` segment | PASS |
| Receive timeline | Direction, event order, wall/monotonic time, job/session offsets and event hash persist in JSONL | PASS |
| Derived sidecars | Receipt/PULITO, parsed JSON, timeline, per-document PDF(s) and manifest hashes are published atomically | PASS |
| Inspector | Direct JSON, per-document forensic directory, exact 168+106/158+106 reassembly, traversal/symlink rejection, incomplete-capture warnings and overwrite refusal | PASS |
| Static/security checks | Ruff, Bandit, compileall, workflow/Bash syntax, ShellCheck, secret/evidence guard | PASS |

## Validation snapshot

On 2026-08-11, the version 0.2.0 Python suite reported `137 passed, 2 skipped`
under Windows Python 3.14.5. Both skips are symlink rejection cases (artifact
and candidate manifest) because the Windows account lacks symlink-creation
privilege; traversal, absolute-path and regular-file rejection still ran there.

The final WSL Debian runner, Python 3.13.5, built and installed the 0.2.0 wheel
from the hash-locked binary-only dependency set, then reported `139 passed`.
That Linux run exercised both symlink tests and also passed Ruff, Bandit,
compileall, workflow/Bash syntax and the fail-closed secret/evidence guard.

Both deployment and development locks also resolved in binary-only dry
runs for CPython 3.11 on Linux x86_64 and aarch64. Ruff and Bandit returned no
findings, all 13 shell scripts passed `bash -n` and ShellCheck, and the
fail-closed secret/evidence guard passed on that baseline. The operations audit
also parsed the service with `systemd-analyze security --offline=yes` at
exposure `1.6 OK`; target-host installation remains untested.

The secondary-address helper was exercised as root in isolated mount/network
namespaces on WSL Debian 13 (systemd 257): real `ip` operations covered owned,
borrowed, pending, repeated-up, scope, prefix, interface-replacement, and
post-delete behavior. Its generated unit passed real `systemd-analyze verify`;
controlled `systemctl` and `arping` doubles isolated service-manager and L2
effects. This does not replace Debian 12 boot, real systemd lifecycle, physical
link, or duplicate-host testing.

Run:

```bash
./scripts/run_tests.sh
```

## Private-corpus and photo validation

The uncommitted private validation corpus was used to derive and check the
public synthetic fixtures. No unredacted private artifact, photograph, source
hash, network value, merchant/device identifier, timestamp, counter, product
text or monetary literal is stored in Git. Capture-confirmed structural bytes
and command shapes are intentionally retained only in anonymized fixtures.

| Validation | Private evidence | Result |
|---|---|---|
| Frame structure | Both directions across all supplied artifacts | 77/77 frames satisfy delimiter, length and XOR BCC (`CONFIRMED`) |
| Control events | Printer-to-client copies | 39 standalone ACK, zero NAK; ACK semantics remain `UNKNOWN` |
| Commercial archive split | Two legacy jobs with equal session identity | 168-byte plus 106-byte request parts form one ordered document exchange; one-second split reproduced as recorder-policy defect |
| Repeated displays | Four equal request/response pairs | Four distinct TCP sessions; correctly excluded from receipt reconstruction |
| Commercial paper correlation | Captured item/free-text/total values | Stream-present fields reconstruct in order; display lines stay auxiliary |
| Management paper correlation | Captured printable body lines | Stream-present body, totals/payment/tax/reference candidates reconstruct in order |
| Printer-generated fields | Header/heading/footer/device/fiscal areas in photos | Absent from relevant request bytes; deliberately not invented |
| Encoding hypothesis | All supplied stream layers | Framed one-byte payload; no XML, escaped XML, hexadecimal XML or Base64 |

The document roles above are `INFERRED`, not authenticated official command
meanings. A paper value is considered reconstructed only when its source frame
and byte range exist; photo-only values remain null/absent.

## Not tested / blocking production completion

- Authenticated Print! F protocol revision, official field names and command semantics.
- Installed hardware/firmware identification.
- NET-2 identification of TCP versus UDP/another IP transport; TCP remains an implementation hypothesis.
- Direct and proxy PCAP comparison.
- XML7 envelope, namespaces, charset and validation for workflows that actually use XML; XML is absent from the supplied cases.
- Official ACK scope, NAK/status/error meanings and paper-out/recovery sequences.
- Broader protocol-native job start/end variants and repeated installed-device lifecycle tests.
- Multiple complete physical documents on one deployed TCP connection; only the synthetic state-machine case is tested.
- Authoritative semantics for discounts, returns, cancellations, non-cash payments and unsupported commands.
- Printer generation/retrieval of header, heading, footer, device and fiscal fields absent from the request stream.
- Full physical-vs-PULITO-vs-PDF typography/layout fidelity; semantic captured-field correlation is tested separately.
- Any installed-device PaDES availability, retrieval format, original-byte extraction, or signature validation.
- Debian/systemd privileged-port integration on the target host.
- Secondary-address boot/stop behavior on Debian 12/systemd 252, a real LAN
  interface, a real `iputils-arping` duplicate responder, and host network-manager reload.
- Management software acceptance, retries, timing, and operational rollback.

These are recorded as gates, not silently marked passed.
