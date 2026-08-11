"""Captured stream-copy data structures."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

CLIENT_TO_RCH = "CLIENT -> RCH"
RCH_TO_CLIENT = "RCH -> CLIENT"


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class CapturedChunk:
    direction: str
    timestamp: str
    offset: int
    data: bytes
    local_write_drain_completed: bool | None = None


@dataclass(frozen=True, slots=True)
class CaptureToken:
    job_id: str
    chunk_index: int | None
    direction: str
    byte_count: int


@dataclass(slots=True)
class CapturedJob:
    session_id: str
    client_ip: str
    client_port: int | None
    proxy_ip: str
    proxy_port: int
    printer_ip: str
    printer_port: int
    max_payload_bytes: int
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_at: datetime = field(default_factory=utc_now)
    ended_at: datetime | None = None
    request: bytearray = field(default_factory=bytearray)
    response: bytearray = field(default_factory=bytearray)
    chunks: list[CapturedChunk] = field(default_factory=list)
    bytes_captured_from_client: int = 0
    bytes_captured_from_printer: int = 0
    bytes_local_write_drain_to_printer: int = 0
    bytes_local_write_drain_to_client: int = 0
    capture_complete: bool = True
    capture_error: str | None = None
    boundary_source: str = "fallback_inactivity"
    boundary_confidence: float = 0.20
    transport_status: str = "captured_delivery_unconfirmed"

    def append(self, direction: str, data: bytes) -> int | None:
        if not data:
            return None
        if direction == CLIENT_TO_RCH:
            self.bytes_captured_from_client += len(data)
        else:
            self.bytes_captured_from_printer += len(data)
        target = self.request if direction == CLIENT_TO_RCH else self.response
        offset = len(target)
        remaining = self.max_payload_bytes - (len(self.request) + len(self.response))
        stored = data[: max(0, remaining)]
        if stored:
            target.extend(stored)
            self.chunks.append(
                CapturedChunk(
                    direction=direction,
                    timestamp=utc_now().isoformat(),
                    offset=offset,
                    data=bytes(stored),
                )
            )
            chunk_index: int | None = len(self.chunks) - 1
        else:
            chunk_index = None
        if len(stored) != len(data):
            self.capture_complete = False
            self.capture_error = "MAX_PAYLOAD_BYTES exceeded; stream copy remained active but capture is partial"
        return chunk_index

    def mark_local_write_drain(self, token: CaptureToken, completed: bool) -> None:
        """Record only that the local asyncio writer drain returned.

        This is not evidence that bytes reached the remote application or were
        accepted by the fiscal device.  Arrival remains unknown without PCAP.
        """
        if token.chunk_index is not None and token.chunk_index < len(self.chunks):
            self.chunks[token.chunk_index].local_write_drain_completed = completed
        if completed:
            if token.direction == CLIENT_TO_RCH:
                self.bytes_local_write_drain_to_printer += token.byte_count
            else:
                self.bytes_local_write_drain_to_client += token.byte_count
        else:
            self.transport_status = "local_write_failed_or_cancelled_delivery_unknown"

    def finish(self, transport_status: str | None = None) -> None:
        self.ended_at = utc_now()
        if transport_status:
            self.transport_status = transport_status
        elif self.transport_status != "local_write_failed_or_cancelled_delivery_unknown":
            all_local_drains_completed = (
                self.bytes_captured_from_client == self.bytes_local_write_drain_to_printer
                and self.bytes_captured_from_printer == self.bytes_local_write_drain_to_client
            )
            self.transport_status = (
                "all_local_write_drains_completed_delivery_and_application_status_unknown"
                if all_local_drains_completed
                else "captured_delivery_unconfirmed"
            )

    @property
    def request_bytes(self) -> bytes:
        return bytes(self.request)

    @property
    def response_bytes(self) -> bytes:
        return bytes(self.response)
