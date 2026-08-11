# Test report

## Environment

- Build date: 2026-08-11
- Development host: Windows, Python 3.14.5 virtual environment
- Linux packaging runner: WSL Debian, Python 3.13.5
- Target runtime: Debian/Ubuntu, Python >=3.11
- Test device: opaque asyncio fixture server only
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
| Candidate document labels | Photo phrases populate candidate fields while authoritative `document_type` remains `null` | PASS |
| Renderer fixture | Photo-derived proxy PDF is readable; this does not establish production content or physical fidelity | PASS |
| Health/config check | No live network connection attempted | PASS |
| Tail timeout evidence | A stalled tail remains explicitly incomplete even after response bytes | PASS |
| Opposite-direction failure | A pump transport failure cancels the other pump immediately rather than waiting/forwarding further bytes | PASS |
| FIN propagation failure | Failed half-close is a transport error, never clean EOF | PASS |
| Slow archive isolation | Hash/render/fsync work does not hold transport sockets or the exclusive device-session lock | PASS |
| Mandatory manifest | `SAVE_JSON=false` is rejected | PASS |
| Static/security checks | Ruff, Bandit, compileall, Bash syntax, ShellCheck, secret/evidence guard | PASS |

## Validation snapshot

On 2026-08-11, `scripts/run_tests.sh` built an isolated wheel and virtual
environment under WSL from the hash-locked, binary-only development dependency
set, then reported `46 passed`. The same 46 tests passed under Windows Python
3.14.5. Both deployment and development locks resolved in binary-only dry runs
for CPython 3.11 on Linux x86_64 and aarch64. Ruff and Bandit returned no
findings, all 12 shell scripts passed `bash -n` and ShellCheck, and the
fail-closed secret/evidence guard passed. The operations audit also parsed the
service with `systemd-analyze security --offline=yes` at exposure `1.6 OK`;
target-host installation remains untested.

Run:

```bash
./scripts/run_tests.sh
```

## Not tested / blocking production completion

- Authenticated Print! F protocol revision and packet fields.
- Installed hardware/firmware identification.
- NET-2 identification of TCP versus UDP/another IP transport; TCP remains an implementation hypothesis.
- Direct and proxy PCAP comparison.
- Real XML7 envelope, namespaces, charset, and validation.
- Real ACK/NAK/status/error/paper-out sequences.
- Protocol-native job start/end and persistent-session behavior.
- Three real raw payloads corresponding to the photo.
- Authoritative field mapping; production PULITO/PDF human content therefore remains empty/unavailable.
- Physical-vs-PULITO-vs-PDF comparison and layout fidelity.
- Any installed-device PaDES availability, retrieval format, original-byte extraction, or signature validation.
- Debian/systemd privileged-port integration on the target host.
- Management software acceptance, retries, timing, and operational rollback.

These are recorded as gates, not silently marked passed.
