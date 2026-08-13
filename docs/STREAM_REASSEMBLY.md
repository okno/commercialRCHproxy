# Stream reassembly

## Capture boundary versus document boundary

TCP preserves ordered bytes, not application message/document boundaries. A
single `recv()` may contain part of one frame, a complete frame, or several
frames/ACKs. The Dumper therefore stores whole directional connection streams
and records receive calls only in the timeline.

In 0.3:

- one data-bearing transport connection creates at most one atomic capture
  job; an empty connection creates none;
- request and response remain separate;
- no inactivity pause creates another capture directory;
- the Parser later reconstructs frames/documents from complete directional
  bytes;
- socket close is a capture-container boundary, not fiscal success or an
  authoritative RCH document terminator.

## Incremental framing

The framer retains buffered bytes between `feed()` calls and uses the observed
STX/decimal-length/ETX/BCC contract. Standalone ACK is a separate event. A
truncated final frame becomes an explicit issue at `finish()`.

Correctness must be invariant under:

- whole-stream input;
- one-byte chunks;
- fixed-size chunks;
- deterministic arbitrary chunks;
- several frames coalesced into one chunk.

The timeline's `job_offset`/direction maps each receive event to its exact RAW
range but does not control framing.

## Multiple documents

After framing the request direction, the semantic state machine may emit zero,
one, or several candidates from a single connection. Each opener creates a
fresh model and each inferred close finalizes it. A new conflicting opener
finishes the current candidate as incomplete before creating another.

Response ACK/frames are correlated independently; they are not concatenated
into request text and do not complete a document by themselves.

## Legacy 0.2 archives

Old archives can contain inactivity-split same-session segments. The offline
inspector may group only artifacts supported by reliable equal `session_id`
and chronological manifest evidence. It never merges files solely by timestamp,
similar payload, filename, or photograph.

Selected verified directional copies can be imported as a new 0.3 offline job
with `commercialrchproxy-replay`. Import does not connect to a device and does
not modify the legacy source. See [MIGRATION.md](MIGRATION.md).

## Supplied private job

The currently supplied private archive has one 235-byte request/202-byte
response job. It yields 10 request frames, 9 response frames, and 10 ACKs, and
ends before an inferred commercial close. There are no adjacent supplied
segments to reassemble and no payload for three other photographed documents.

See [RCH_DUMP_ANALYSIS.md](RCH_DUMP_ANALYSIS.md).
