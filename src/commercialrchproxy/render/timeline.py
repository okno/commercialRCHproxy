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
    local_write_drain_completed: bool | None


def render_timeline_jsonl(chunks: Iterable[TimelineChunk]) -> str:
    """Describe every copied receive event without duplicating payload bytes.

    Direction plus ``session_offset`` locates the exact bytes in the immutable
    directional RAW file.  The per-event digest detects accidental mismatch
    between the timeline and those bytes.
    """
    lines: list[str] = []
    for chunk in chunks:
        event = {
            "sequence": chunk.sequence,
            "timestamp": chunk.timestamp,
            "monotonic_ns": chunk.monotonic_ns,
            "direction": chunk.direction,
            "job_offset": chunk.offset,
            "session_offset": chunk.session_offset,
            "byte_count": len(chunk.data),
            "sha256": hashlib.sha256(chunk.data).hexdigest(),
            "local_write_drain_completed": chunk.local_write_drain_completed,
            "remote_arrival": None,
        }
        lines.append(json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return "\n".join(lines) + ("\n" if lines else "")
