# Parser state machine

## Status of this model

The state machine is an evidence-labelled reverse-engineering model. Frame
boundaries and literal bytes are capture-verified where present; command roles
and document transitions are inferred. `complete=true` means only that the
inferred request close pattern was captured. It never means that the physical
device accepted, printed, memorized, or fiscally completed the operation.

The newly supplied private job reaches an incomplete commercial-payment state
and contains no management envelope. Management and complete-close transitions
below are covered by sanitized synthetic regression fixtures and historical
correlation, not by the missing three private captures.

## Pipeline states

The persistent worker lifecycle is separate from semantic document state:

```text
spool scan
   |
   +-- no .ready / any .partial ------------> ignore/reject
   |
   +-- .ready + manifest/hash valid
                  |
                  v
             exclusive claim
                  |
          +-------+--------+
          |                |
       already          .processing
       .parsed              |
          |                 v
        no-op        frame both directions
                            |
                            v
                    semantic state machine
                            |
                 +----------+----------+
                 |                     |
              success                failure
                 |                     |
        PHARSED + .parsed       retry state / .parse_failed
```

The Parser validates the `.ready` to manifest SHA-256 binding, safe contained
artifact names, capture schema, per-file sizes/hashes, and absence of partial
artifacts before semantic work. It validates immutable inputs again before
publishing `.parsed`.

## Framer state

Each direction has an independent incremental framer:

```text
SEEK_EVENT
  |-- 0x06 --------------------------> emit standalone ACK; SEEK_EVENT
  |-- 0x02 + incomplete header ------> BUFFER_FRAME
  |-- unrelated byte(s) ------------> bounded issue; resynchronize

BUFFER_FRAME
  |-- fewer than declared N+11 bytes -> retain buffer; await next chunk
  |-- bad terminator/field ----------> issue; seek next plausible event
  |-- complete frame ----------------> emit frame + BCC result; SEEK_EVENT
  `-- end of input ------------------> truncated-frame issue
```

TCP reads are not events. A frame may span any number of timeline chunks, and
one chunk may contain several frames and ACKs.

## Semantic document states

Implemented `DocumentAssemblyState` values are:

| State | Meaning |
|---|---|
| `idle` | no active semantic candidate |
| `commercial_body` | fresh commercial candidate accumulating item/free-text fields |
| `commercial_payment` | a total/payment-like command has been captured |
| `commercial_postlude` | a post-payment control marker was captured; close still pending |
| `management_body` | management envelope/printable-line candidate active |
| `complete` | inferred close captured |
| `incomplete` | input ended or a conflicting opener arrived before inferred close |

### Commercial transitions

```text
IDLE
  |  `<</?s`              remember pending control marker only
  |  `=K`
  v
COMMERCIAL_BODY
  |  `=R...`              add a sourced item candidate
  |  `="/?A/(...)`        add a sourced free-text candidate
  |  unrecognized command retain protocol event; do not invent a field
  |  `=T...`
  v
COMMERCIAL_PAYMENT
  |  `<</?s`              retain control, transition to postlude
  v
COMMERCIAL_POSTLUDE
  |  `<</?<digit>` or `<</?`
  v
COMPLETE

Any end/conflicting opener before the inferred close -> INCOMPLETE
```

Important rules:

- `<</?s` alone is not a close because it occurs in more than one lifecycle
  position.
- `=K` creates a fresh commercial builder and clears a pending start marker.
- An item or total without `=K` starts an explicitly incomplete/missing-start
  commercial candidate rather than attaching to an earlier document.
- `=D...` auxiliary display candidates stay in protocol diagnostics and do
  not enter receipt lines.
- A total-like command changes semantic state but does not prove payment
  method, fiscal success, or physical print completion.
- The newly supplied 10-frame request ends after its total-like command and is
  finalized `incomplete`.

### Management transitions

```text
IDLE
  |  `=o`
  v
MANAGEMENT_BODY
  |  `="/(...)`           add captured printable line and conservative fields
  |  `=o`
  v
COMPLETE

Printable management line without opener -> MANAGEMENT_BODY + missing-open issue
End/conflicting opener before closing `=o` -> INCOMPLETE
```

The same literal `=o` is interpreted contextually as opener when no management
builder exists and closer when one is active. This role is inferred, not an
official command definition.

## Independent model and price isolation

Every accepted opener allocates a new `DocumentModel`. Items, amounts,
quantities, totals, taxes, payments, metadata, source frames, and issues belong
only to that builder. `finish_active()` appends an immutable parsed candidate
and sets the active builder to `None` before another candidate starts.

Consequences tested with synthetic data:

- an earlier management pre-account retains its earlier captured value;
- a later commercial candidate uses only its own updated captured value;
- a following management conforming-copy candidate uses its own captured body;
- no builder copies item lists or amounts from a previous document;
- a copy relationship is metadata correlation, never model inheritance;
- repeated visible content is not deduplicated across distinct envelopes.

The supplied real job contains only the later value state. The four-document
real price-isolation scenario remains `NON VERIFICABILE` until the other three
directional captures are provided.

## Type and subtype decision

Primary type comes from the active lifecycle, not from price presence:

| Lifecycle | Primary type | Default subtype |
|---|---|---|
| commercial command sequence | `C` | `DOCUMENTO COMMERCIALE` |
| management envelope/printable lines | `G` | `DOCUMENTO GESTIONALE GENERICO` |

Management subtype evaluation uses this conservative order:

1. captured literal `COPIA CONFORME` marker -> `COPIA CONFORME` candidate;
2. captured command-style markers for course and covers, with no totals ->
   `COMANDA` candidate;
3. captured literal `PRECONTO` marker -> `PRECONTO` candidate;
4. same-stream management candidate after a distinct commercial candidate,
   matching captured item/total signature plus management payment/tax content
   -> `COPIA CONFORME` candidate with `copy_of` metadata;
5. management items/totals without payment/tax -> `PRECONTO` candidate;
6. otherwise -> `DOCUMENTO GESTIONALE GENERICO`.

All semantic subtype roles remain evidence-labelled. A photo label, temporal
proximity, total, or matching amount by itself is insufficient. A conforming
copy remains `G` and is never merged into or relabelled as the preceding `C`.

## Response association

Response frames and ACK events do not drive the primary request document
boundary in the current model. They are retained independently and correlated
by ordinal position plus an inferred sequence check.

A response-derived counter suffix may be attached only to a complete
commercial candidate when all of these are true:

1. the exact counter-query-like request occurs after the total;
2. an ordinal response candidate exists;
3. the inferred sequence relation matches;
4. response address/class and BCC match the observed profile;
5. response `DATA` matches the bounded suffix grammar.

Even then it is labelled suffix-only and inferred. The full number/prefix and
fiscal status remain unknown. This path cannot run for the newly supplied
incomplete candidate.

## Capture time and output names

For each candidate, the Parser locates the request timeline event covering its
start offset. The receive time is converted through configured `TIMEZONE` and
truncated to milliseconds:

```text
<CODICE_DOC>_<C|G>_<HH.MM.SS.mmm>.txt
<CODICE_DOC>_<C|G>_<HH.MM.SS.mmm>.pdf
```

If another candidate in the same job has the identical code/type/millisecond
stem, `_02`, `_03`, and later deterministic suffixes are appended. Unix epoch
values are never used in parsed names or operator-facing content.

## Claim state and crash recovery

| Marker | Owner | Meaning |
|---|---|---|
| `.ready` | Dumper | capture publication committed; immutable input candidate |
| `.parser.lock` | Parser | short advisory serialization for claim-state transitions |
| `.processing` | Parser | exclusive active claim with token/host/PID/heartbeat |
| `.processing.stale` | Parser | preserved displaced stale claim |
| `.parse_attempts.json` | Parser | bounded retry accounting and latest error |
| `.parse_failed` | Parser | terminal parser quarantine after retries are exceeded |
| `.parsed` | Parser | successful parsed-output commit metadata |

An active worker refreshes `.processing`. A later scan does not steal a marker
younger than `PARSER_STALE_LOCK_SEC`. An older marker is atomically displaced
under `.parser.lock`, after which a new exclusive marker is created.

Each claimant writes only to `.PHARSED.<claim-token>.partial`. Before promotion,
the worker reacquires `.parser.lock`, proves that `.processing` still contains
its exact token, revalidates capture and generated hashes, and only then
renames the staging directory to `PHARSED` and writes `.parsed`. A paused stale
worker therefore cannot publish over a takeover winner. Fenced recovery also
removes token-staging directories left by dead claims while preserving Dumper
RAW partials.

Successful repeated scans return `already_parsed`; they do not duplicate TXT
or PDF. Explicit force reparse removes only known Parser-owned output/state and
is guarded by capture revalidation. The reparse CLI can first rename existing
`PHARSED` to a human-time backup.

## Failure behavior

- Invalid ready/manifest/hash/path: reject without parsing or modifying RAW.
- No semantic document: retry, then terminal `.parse_failed` marker.
- PDF/TXT generation failure: retry state; no `.parsed` marker.
- Process death after claim: stale heartbeat becomes reclaimable.
- Process death during output: stale recovery removes the orphan token staging,
  regenerates deterministic Parser-owned files, and leaves immutable capture
  files unchanged.
- Capture ends mid-frame/document: preserve framing issue and incomplete
  candidate; never manufacture a close.

See [STORAGE_LAYOUT.md](STORAGE_LAYOUT.md) for the publication contract and
[RCH_PROTOCOL_FINDINGS.md](RCH_PROTOCOL_FINDINGS.md) for the evidence behind
the marker patterns.
