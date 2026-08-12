"""Independent opaque stream pumps."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from commercialrchproxy.capture.jobs import CLIENT_TO_RCH
from commercialrchproxy.capture.recorder import JobCaptureManager
from commercialrchproxy.config import Config
from commercialrchproxy.logging.structured import event
from commercialrchproxy.metrics import Metrics

BUFFER_SIZE = 64 * 1024


@dataclass(frozen=True, slots=True)
class PumpResult:
    direction: str
    bytes_local_write_drain_completed: int
    ended_by: str
    error: str | None = None


async def _half_close(writer: asyncio.StreamWriter) -> str | None:
    try:
        if writer.can_write_eof():
            writer.write_eof()
            await writer.drain()
        return None
    except (ConnectionError, OSError, RuntimeError) as exc:
        # FIN propagation is part of the transport outcome.  Never turn a
        # failed half-close into a clean stream completion.
        return f"{type(exc).__name__}: {exc}"


def _debug_hex(data: bytes, limit: int = 4096) -> str:
    shown = data[:limit].hex(" ")
    return shown + (" ...[truncated]" if len(data) > limit else "")


async def pump(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    direction: str,
    recorder: JobCaptureManager,
    config: Config,
    logger: logging.Logger,
    metrics: Metrics,
    session_id: str,
) -> PumpResult:
    total = 0
    metric_name = "bytes_to_rch" if direction == CLIENT_TO_RCH else "bytes_from_rch"
    try:
        while True:
            data = await reader.read(BUFFER_SIZE)
            if not data:
                half_close_error = await _half_close(writer)
                if half_close_error is not None:
                    return PumpResult(direction, total, "half_close_error", half_close_error)
                return PumpResult(direction, total, "eof")

            # Queue opaque bytes toward the peer before doing any capture or
            # boundary-hint work.  The parser only sees a copy and can fail
            # without changing the forwarded stream.
            writer.write(data)
            token = None
            try:
                token = await recorder.record(direction, data)
            except Exception as exc:
                logger.exception(
                    "Capture failed; opaque byte-copy path continues",
                    extra={
                        "event": "capture_error",
                        "fields": {"session_id": session_id, "direction": direction, "error": str(exc)},
                    },
                )
            local_drain_completed = False
            try:
                await asyncio.wait_for(writer.drain(), timeout=config.connection_timeout_sec)
                local_drain_completed = True
            finally:
                if token is not None:
                    await recorder.mark_local_write_drain(token, local_drain_completed)
            total += len(data)
            metrics.increment(metric_name, len(data))
            event(
                logger,
                "stream_local_write_drain",
                "Local stream writer drain completed; remote delivery unconfirmed",
                session_id=session_id,
                direction=direction,
                bytes=len(data),
                total_bytes=total,
            )
            if config.debug and config.debug_hexdump and config.log_payload:
                logger.debug(
                    "Debug payload hexdump",
                    extra={
                        "event": "payload_hexdump",
                        "fields": {
                            "session_id": session_id,
                            "direction": direction,
                            "bytes": len(data),
                            "hexdump": _debug_hex(data),
                        },
                    },
                )
    except asyncio.CancelledError:
        return PumpResult(direction, total, "cancelled", "cancelled_by_session_tail_timeout_or_shutdown")
    except (TimeoutError, ConnectionError, OSError) as exc:
        return PumpResult(direction, total, "transport_error", f"{type(exc).__name__}: {exc}")
