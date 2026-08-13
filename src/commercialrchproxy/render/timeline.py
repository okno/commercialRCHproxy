"""Machine-readable receive timeline for forensic stream reconstruction."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Protocol


class TimelineChunk(Protocol):
    sequence: int
    direction: str
    timestamp: str
    monotonic_ns: int
    offset: int
    session_offset: int
    data: bytes
    byte_count: int | None
    data_sha256: str | None
    received_unix_ns: int | None
    forwarded_unix_ns: int | None
    drain_unix_ns: int | None
    local_write_drain_completed: bool | None
    forward_error: str | None


def render_timeline_event(
    chunk: TimelineChunk,
    *,
    session_id: str | None = None,
    connection_id: str | None = None,
) -> str:
    """Render one receive event without duplicating its payload bytes."""
    byte_count = len(chunk.data) if chunk.byte_count is None else chunk.byte_count
    digest = hashlib.sha256(chunk.data).hexdigest() if chunk.data_sha256 is None else chunk.data_sha256
    event = {
        "sequence": chunk.sequence,
        "received_at": chunk.timestamp,
        "received_unix_ns": chunk.received_unix_ns,
        "forwarded_unix_ns": chunk.forwarded_unix_ns,
        "local_write_drain_unix_ns": chunk.drain_unix_ns,
        "monotonic_ns": chunk.monotonic_ns,
        "direction": chunk.direction,
        "job_offset": chunk.offset,
        "session_offset": chunk.session_offset,
        "byte_count": byte_count,
        "connection_id": connection_id,
        "session_id": session_id,
        "sha256": digest,
        "local_write_drain_completed": chunk.local_write_drain_completed,
        "forward_status": (
            "local_write_drain_completed"
            if chunk.local_write_drain_completed
            else "local_write_failed_or_not_observed"
        ),
        "error": chunk.forward_error,
        "remote_arrival": None,
    }
    return json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def render_timeline_jsonl(
    chunks: Iterable[TimelineChunk],
    *,
    session_id: str | None = None,
    connection_id: str | None = None,
) -> str:
    """Describe every copied receive event without duplicating payload bytes.

    Direction plus ``session_offset`` locates the exact bytes in the immutable
    directional RAW file.  The per-event digest detects accidental mismatch
    between the timeline and those bytes.
    """
    return "".join(
        render_timeline_event(chunk, session_id=session_id, connection_id=connection_id)
        for chunk in chunks
    )
