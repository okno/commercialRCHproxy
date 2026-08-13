# Test report for 0.3.0

## Reporting rule

This file deliberately does not carry forward 0.2 test counts. The architecture,
storage contract, entry points, and service units changed in 0.3.0. A result is
`PASS` only after the final pre-commit worktree was executed on the named
environment on 2026-08-13.

## Final validation snapshot

| Item | Result |
|---|---|
| Release under test | `0.3.0` |
| Commit | pre-commit worktree on base `76b02fa`; no release commit created in this task |
| Windows Python version | CPython `3.14.5` |
| Windows pytest | `200 passed, 15 skipped, 0 failed` (11 Linux-only shell-contract tests; 4 unavailable-symlink privilege tests) |
| Debian/WSL Python version | Debian 13 / CPython `3.13.5` |
| Debian/WSL pytest | `215 passed, 0 skipped, 0 failed` |
| Ruff | `PASS`, all `src` and `tests` |
| Bandit | `PASS`, recursive `src` with `pyproject.toml` policy |
| compileall | `PASS`, `src` and `tests` |
| Bash syntax/ShellCheck | `PASS`, all 14 shell scripts |
| systemd unit verification/security | `PASS` offline verification; Dumper/Parser hardening inspected on systemd 257; target Debian 12 boot remains not performed |
| dependency lock/wheel install | `PASS`: hash-required binary-only Linux 3.13 install; compatible 3.11 Linux wheel resolution; `pip check`/imports passed |
| secret/private-evidence guard | `PASS`; decoded public HEX also compared privately against all supplied RAW with no full-stream equality/containment |
| Physical RCH device | `NON VERIFICABILE` by automated suite |
| Direct-versus-proxy PCAP | `NON VERIFICABILE` |

## Automated scope present in the repository

The table describes assertions executed by the final Windows/Linux runs.
`COMPLETATO E TESTATO (sintetico)` is an implementation test and is not
physical-device proof.

| Area | Assertion | Final result |
|---|---|---|
| Shared configuration | strict known keys, IPv4/ports, paths, timezone, modes, non-root identity, mandatory evidence switches; installer renders configured identity/paths | `PASS` |
| CODICE_DOC | per-printer persistent counter, atomic lock, collision scan, concurrency uniqueness, minimum width, continuation beyond 9999 | `PASS` |
| Spool path/naming | printer/date/code hierarchy and exact nine-digit RAW epoch fraction | `PASS` |
| Empty response | response RAW created deterministically with zero bytes/hash | `PASS` |
| Atomic publication | partial staging excluded from discovery; manifest/hash/ready binding; final directory visibility | `PASS` |
| Corruption rejection | bad ready binding, malformed manifest, hash mismatch, unsafe path/symlink, size bound | `PASS` |
| Relay request equality | simulated client-to-Dumper-to-peer bytes, length, order, and hash unchanged | `COMPLETATO E TESTATO (sintetico)` |
| Relay response equality | simulated peer-to-Dumper-to-client bytes, length, order, and hash unchanged | `COMPLETATO E TESTATO (sintetico)` |
| Stream behavior | fragmentation/coalescing, slow directions, response tail, half-close, failure cancellation | `COMPLETATO E TESTATO (sintetico)` |
| Storage/log isolation | blocked/failed capture worker and blocked log sink do not backpressure the relay; partial preserved | `COMPLETATO E TESTATO (fault injection)` |
| Storage policy | default continue isolates storage failure; explicit abort surfaces failure; partial preserved | `PASS` |
| Process independence | Dumper captures with Parser absent; later Parser backlog; Parser code/socket absent from relay process | `COMPLETATO E TESTATO (sintetico)` |
| Framing | incremental STX/ETX/length/BCC/ACK parsing across whole, one-byte, and arbitrary chunks | `PASS` |
| Framing failures | truncation, malformed header/terminator, oversize, bad BCC, bounded resynchronization | `PASS` |
| Semantic isolation | independent management/commercial/copy models; changed value never leaks backward/forward | `COMPLETATO E TESTATO (sintetico)` |
| Classification | C/G primary type and management subtype candidate rules | `COMPLETATO E TESTATO (sintetico)` |
| Multiple documents | separate candidates in one reassembled stream; no concatenation/deduplication | `COMPLETATO E TESTATO (sintetico)` |
| Parser naming | local `HH.MM.SS.mmm`, C/G, deterministic `_02`, no Unix time in TXT/PDF names | `PASS` |
| Parser idempotency/fencing | claim heartbeat, stale takeover, token-private staging, lease-fenced commit, orphan cleanup, retries/failure state | `COMPLETATO E TESTATO (fault injection)` |
| Parser immutability | request/response/timeline/manifest/ready hashes unchanged through parse/reparse | `PASS` |
| PDF/TXT | one pair per model; normalized semantic text consistency; receipt-width readability | `PASS`; protected real partial render also inspected |
| Watcher | Linux inotify wake-up when available; unconditional polling fallback | `PASS` on WSL/Linux |
| Offline inspect | bounded direct/archive inspection, frame/document diagnostics, no unsafe overwrite | `PASS` |
| Offline replay | RAW-to-spool import, no network connection, manifest declares offline/no delivery | `PASS` |
| Reparse | dry-run, code/root guard, active claim rejection, crash-gap recovery, optional backup, immutable snapshot, nonzero failure exit | `PASS` |
| systemd | independent real units, rendered shared identity/paths, Dumper bind-only capability, Parser no capabilities/IP network | `PASS` offline; target-host boot not performed |
| Legacy launcher | no-op compatibility unit controls both real services without making them interdependent | `PASS` static/offline |

## Private supplied-evidence validation

No private artifact is committed. The following structural facts were
reproduced locally and can be rechecked only with the protected source:

| Check | Result |
|---|---|
| Inventory | verified exactly one legacy job, not four captures |
| Direction sizes | verified 235 request bytes and 202 response bytes |
| Framing | verified 10 request frames, 9 response frames, 10 standalone ACK |
| Integrity rules | verified all 19 complete frames satisfy declared length and observed XOR BCC |
| Segmentation independence | verified equal frame/candidate result for complete, one-byte, and deterministic arbitrary chunks |
| Semantic result | one incomplete commercial candidate only |
| Photo 3.1 | strong partial item/reference/total correlation; close and printer-generated regions absent |
| Photos 1, 2, 3.2 | `NON VERIFICABILE`: corresponding byte streams absent |
| Four-document price-state acceptance | `NON VERIFICABILE` from private bytes; only one price state captured |
| Final protected TXT/PDF render/visual check | verified one-page proxy PDF and matching TXT for the single incomplete C candidate; metadata visibly states `STATO: INCOMPLETO`; no clipping observed |

Source hashes were computed privately but are intentionally excluded from the
public repository and this report. The public suite must use synthetic
checksum-correct fixtures, never copied private payload.

## Commands for the final run

From a clean trusted checkout/virtual environment:

```bash
python -m pytest -q
python -m ruff check src tests
python -m bandit -c pyproject.toml -r src
python -m compileall -q src
```

Run the project wrapper as the authoritative combined check when finalized:

```bash
./scripts/run_tests.sh
```

On Debian/WSL additionally validate scripts and units using the exact commands
supported by the target image, for example:

```bash
find scripts -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n
find scripts -type f -name '*.sh' -print0 | xargs -0 shellcheck
systemd-analyze verify systemd/commercialrchproxy-dumper.service
systemd-analyze verify systemd/commercialrchproxy-parser.service
systemd-analyze verify systemd/commercialrchproxy.service
```

If `systemd-analyze security --offline=yes` is available, record each real
unit's exposure result separately. A parser unit should have no IP networking
or capabilities; the Dumper should have only `CAP_NET_BIND_SERVICE`.

Validate installed console entry points:

```bash
commercialrchproxy-dumper --version
commercialrchproxy-parser --version
commercialrchproxy-inspect-dump --help
commercialrchproxy-replay --help
commercialrchproxy-reparse --help
```

## Manual process-independence acceptance

Use only a synthetic authorized peer, never an unapproved fiscal operation:

1. start Dumper with Parser stopped;
2. send a known bidirectional fixture;
3. verify peer/client bytes and the ready spool job;
4. start Parser and verify one `.parsed` result;
5. repeat while stopping Parser mid-relay;
6. verify relay completion, one ready job, and exactly-once parse after restart;
7. compare immutable source hashes before/after.

Record commands, fixture hashes, service timestamps, and results privately or
with sanitized values. Do not put real endpoints/payload in the public report.

## Crash-recovery acceptance

The final run should explicitly demonstrate:

- Dumper termination leaves a hidden partial with no final `.ready` job;
- Parser ignores job directories without a valid `.ready` binding;
- malformed manifest and hash mismatch never produce `.parsed`;
- a killed Parser leaves `.processing`, which is reclaimed only after the
  configured stale threshold;
- interrupted Parser output is regenerated without touching capture files;
- a completed `.parsed` job is a no-op on restart;
- retry exhaustion produces `.parse_failed` and explicit reparse can recover.

Automated tests may use shortened thresholds and isolated temporary storage;
target-host behavior must still be validated with production filesystem/systemd.

## Non-claims

Passing this suite does not prove:

- official RCH command semantics;
- physical device byte equality, timing compatibility, or Telnet behavior;
- fiscal success/error interpretation;
- exact thermal-paper layout or original/signed PDF equivalence;
- correctness for document types/encodings absent from fixtures;
- the missing three private capture/photo mappings;
- production backup, disk-full, boot, network-address, firewall, or log-rotation
  behavior until target-host acceptance is completed.

## Final sign-off

```text
Commit: pre-commit worktree on base 76b02fa
Windows: CPython 3.14.5; pytest 200 passed/15 skipped; Ruff/Bandit/compile PASS
Debian/WSL: Debian 13; CPython 3.13.5; pytest 215 passed; full runner PASS
Packaging/locks: PASS, hashed/binary-only deployment and dev locks
Shell/systemd/security: PASS offline; 14 scripts; target Debian 12 boot NON VERIFICABILE
Secret/evidence guard: PASS; protected full-stream fixture collision scan PASS
Protected private replay/render: one incomplete C output COMPLETATO E TESTATO
Physical RCH/PCAP: NON VERIFICABILE
Residual blockers: missing three real captures; physical/device/PCAP acceptance
```
