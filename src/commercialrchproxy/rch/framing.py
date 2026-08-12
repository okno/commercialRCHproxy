"""Incremental framing for the byte streams observed on the RCH connection.

The frame layout implemented here is capture-confirmed, not inferred from TCP
``recv()`` boundaries::

    STX | AA | LLL | class | DATA | seq | BCC | ETX

``AA`` is two decimal ASCII bytes, ``LLL`` is a three digit data length and
``BCC`` is the uppercase or lowercase hexadecimal representation of the XOR
of every byte from ``STX`` through ``seq`` (inclusive).  A complete frame is
therefore ``LLL + 11`` bytes.  ``ACK`` is a separate one-byte stream event.

This module deliberately assigns no meaning to a class or payload.  Semantic
interpretation lives in :mod:`commercialrchproxy.rch.receipt_parser` and is
marked as inferred there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypeAlias

STX = 0x02
ETX = 0x03
ACK = 0x06

_FRAME_OVERHEAD = 11
_HEX_DIGITS = frozenset(b"0123456789abcdefABCDEF")
_DEFAULT_MAX_EVENTS = 8192
_DEFAULT_MAX_ISSUES = 256
_DEFAULT_MAX_ISSUE_RAW_BYTES = 1024
_PLAUSIBLE_CONTROL_RE = re.compile(rb"\x06|\x02[0-9]{5}")


@dataclass(frozen=True, slots=True)
class FramingIssue:
    """Bytes which could not be accepted as a valid framed stream unit."""

    code: str
    stream_offset: int
    raw: bytes
    detail: str
    evidence: str = "CONFIRMED"
    span_length: int | None = None

    @property
    def end_offset(self) -> int:
        return self.stream_offset + (len(self.raw) if self.span_length is None else self.span_length)

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "stream_offset": self.stream_offset,
            "end_offset": self.end_offset,
            "raw_hex": self.raw.hex(),
            "byte_count": len(self.raw) if self.span_length is None else self.span_length,
            "raw_preview_truncated": self.span_length is not None and self.span_length > len(self.raw),
            "detail": self.detail,
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class AckEvent:
    """A standalone ACK byte observed outside an RCH frame."""

    event_id: int
    stream_offset: int
    raw: bytes = b"\x06"
    kind: str = "ack"
    evidence: str = "CONFIRMED"

    @property
    def end_offset(self) -> int:
        return self.stream_offset + 1

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "event_id": self.event_id,
            "stream_offset": self.stream_offset,
            "end_offset": self.end_offset,
            "raw_hex": self.raw.hex(),
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class RCHFrame:
    """One structurally complete observed frame.

    A frame with a bad BCC is retained as an :class:`RCHFrame` so callers can
    inspect its exact fields; the mismatch is also reported in ``issues``.
    """

    event_id: int
    frame_id: int
    stream_offset: int
    raw: bytes
    address: str
    data_length: int
    frame_class: str
    data: bytes
    sequence: str
    bcc: str
    expected_bcc: str
    bcc_valid: bool
    kind: str = "frame"
    evidence: str = "CONFIRMED"

    @property
    def end_offset(self) -> int:
        return self.stream_offset + len(self.raw)

    @property
    def aa(self) -> str:
        """The literal two-digit ``AA`` field; its business meaning is unknown."""

        return self.address

    @property
    def data_text(self) -> str:
        """Lossless one-byte text view; it is not an encoding assertion."""

        return self.data.decode("latin-1")

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "event_id": self.event_id,
            "frame_id": self.frame_id,
            "stream_offset": self.stream_offset,
            "end_offset": self.end_offset,
            "raw_hex": self.raw.hex(),
            "aa": self.aa,
            "address": self.address,
            "data_length": self.data_length,
            "class": self.frame_class,
            "data_hex": self.data.hex(),
            "data_text_latin1": self.data_text,
            "sequence": self.sequence,
            "bcc": self.bcc,
            "expected_bcc": self.expected_bcc,
            "bcc_valid": self.bcc_valid,
            "evidence": self.evidence,
        }


StreamEvent: TypeAlias = AckEvent | RCHFrame


@dataclass(frozen=True, slots=True)
class FramingResult:
    """Immutable result of framing one complete direction of a stream."""

    events: tuple[StreamEvent, ...]
    issues: tuple[FramingIssue, ...]
    bytes_seen: int
    total_frame_count: int = 0
    total_ack_count: int = 0
    events_truncated: bool = False
    omitted_issue_count: int = 0

    @property
    def frames(self) -> tuple[RCHFrame, ...]:
        return tuple(event for event in self.events if isinstance(event, RCHFrame))

    @property
    def acks(self) -> tuple[AckEvent, ...]:
        return tuple(event for event in self.events if isinstance(event, AckEvent))

    @property
    def valid(self) -> bool:
        return (
            bool(self.frames)
            and not self.issues
            and not self.events_truncated
            and not self.omitted_issue_count
            and all(frame.bcc_valid for frame in self.frames)
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "bytes_seen": self.bytes_seen,
            "events": [event.to_dict() for event in self.events],
            "issues": [issue.to_dict() for issue in self.issues],
            "frame_count": self.total_frame_count,
            "ack_count": self.total_ack_count,
            "retained_frame_count": len(self.frames),
            "retained_ack_count": len(self.acks),
            "events_truncated": self.events_truncated,
            "omitted_issue_count": self.omitted_issue_count,
            "valid": self.valid,
        }


@dataclass(frozen=True, slots=True)
class FramingAssessment:
    confirmed: bool = False
    frame_count: int | None = None
    evidence: str = "UNCONFIRMED"
    reason: str = "no complete checksum-valid RCH frame observed"


def calculate_bcc(prefix_through_sequence: bytes) -> int:
    """Return the capture-confirmed XOR BCC for ``STX .. seq`` bytes."""

    value = 0
    for byte in prefix_through_sequence:
        value ^= byte
    return value


def build_frame(
    data: bytes | str,
    *,
    address: str = "00",
    frame_class: bytes | str = b"z",
    sequence: bytes | str = b"0",
) -> bytes:
    """Build a frame, primarily for deterministic synthetic fixtures/tests."""

    encoded_data = data.encode("latin-1") if isinstance(data, str) else bytes(data)
    encoded_class = frame_class.encode("ascii") if isinstance(frame_class, str) else bytes(frame_class)
    encoded_sequence = sequence.encode("ascii") if isinstance(sequence, str) else bytes(sequence)
    if len(address) != 2 or not address.isascii() or not address.isdecimal():
        raise ValueError("address must contain exactly two ASCII decimal digits")
    if len(encoded_class) != 1:
        raise ValueError("frame_class must be exactly one byte")
    if len(encoded_sequence) != 1:
        raise ValueError("sequence must be exactly one byte")
    if len(encoded_data) > 999:
        raise ValueError("data is too long for the three-digit frame length")

    prefix = (
        bytes((STX,))
        + address.encode("ascii")
        + f"{len(encoded_data):03d}".encode("ascii")
        + encoded_class
        + encoded_data
        + encoded_sequence
    )
    return prefix + f"{calculate_bcc(prefix):02X}".encode("ascii") + bytes((ETX,))


class RCHStreamFramer:
    """Incrementally frame arbitrary TCP stream chunks.

    ``feed`` can be called with any segmentation.  Call ``finish`` once EOF or
    a capture boundary is known so a retained partial frame becomes a
    ``truncated_frame`` issue.
    """

    def __init__(
        self,
        *,
        max_data_length: int = 999,
        max_buffer_bytes: int = 4096,
        max_events: int = _DEFAULT_MAX_EVENTS,
        max_issues: int = _DEFAULT_MAX_ISSUES,
        max_issue_raw_bytes: int = _DEFAULT_MAX_ISSUE_RAW_BYTES,
        retain_history: bool = True,
    ) -> None:
        if not 0 <= max_data_length <= 999:
            raise ValueError("max_data_length must be between 0 and 999")
        if max_buffer_bytes < _FRAME_OVERHEAD:
            raise ValueError(f"max_buffer_bytes must be at least {_FRAME_OVERHEAD}")
        if max_buffer_bytes < max_data_length + _FRAME_OVERHEAD:
            raise ValueError("max_buffer_bytes must hold the largest accepted frame")
        if max_events < 1:
            raise ValueError("max_events must be positive")
        if max_issues < 1:
            raise ValueError("max_issues must be positive")
        if max_issue_raw_bytes < 0:
            raise ValueError("max_issue_raw_bytes cannot be negative")
        self.max_data_length = max_data_length
        self.max_buffer_bytes = max_buffer_bytes
        self.max_events = max_events
        self.max_issues = max_issues
        self.max_issue_raw_bytes = max_issue_raw_bytes
        self.retain_history = retain_history
        self._buffer = bytearray()
        self._cursor = 0
        self._buffer_offset = 0
        self._bytes_seen = 0
        self._event_count = 0
        self._frame_count = 0
        self._ack_count = 0
        self._events: list[StreamEvent] = []
        self._issues: list[FramingIssue] = []
        self._events_truncated = False
        self._omitted_issue_count = 0
        self._finished = False

    @property
    def events(self) -> tuple[StreamEvent, ...]:
        return tuple(self._events)

    @property
    def issues(self) -> tuple[FramingIssue, ...]:
        return tuple(self._issues)

    @property
    def buffered_bytes(self) -> bytes:
        return bytes(self._buffer[self._cursor :])

    @property
    def _available(self) -> int:
        return len(self._buffer) - self._cursor

    def feed(self, chunk: bytes | bytearray | memoryview) -> tuple[StreamEvent, ...]:
        if self._finished:
            raise RuntimeError("cannot feed a finished framer")
        view = memoryview(chunk)
        if not view:
            return ()
        before = len(self._events)
        position = 0
        while position < len(view):
            if not self._available:
                self._buffer.clear()
                self._cursor = 0
                self._buffer_offset = self._bytes_seen
            elif self._cursor:
                # Compact at most once per external slice, never once per
                # byte/event.  This keeps front consumption amortized O(n).
                del self._buffer[: self._cursor]
                self._cursor = 0
            capacity = self.max_buffer_bytes - self._available
            if capacity <= 0:
                # Constructor validation guarantees that a syntactically
                # possible frame fits.  This is a defensive fail-safe.
                self._issue("buffer_limit_exceeded", self._available, "framing buffer made no progress")
                capacity = self.max_buffer_bytes
            count = min(capacity, len(view) - position)
            self._buffer.extend(view[position : position + count])
            position += count
            self._bytes_seen += count
            self._process(final=False)
        emitted = tuple(self._events[before:])
        if not self.retain_history:
            self._events.clear()
            self._issues.clear()
            self._events_truncated = False
            self._omitted_issue_count = 0
        return emitted

    def finish(self) -> FramingResult:
        if not self._finished:
            self._process(final=True)
            self._finished = True
        self._finalize_omitted_issues()
        return FramingResult(
            tuple(self._events),
            tuple(self._issues),
            self._bytes_seen,
            self._frame_count,
            self._ack_count,
            self._events_truncated,
            self._omitted_issue_count,
        )

    # ``finalize`` is a discoverable synonym for users accustomed to parsers.
    finalize = finish

    def _consume(self, count: int) -> bytes:
        start = self._cursor
        raw = bytes(self._buffer[start : start + count])
        self._cursor += count
        self._buffer_offset += count
        if self._cursor == len(self._buffer):
            self._buffer.clear()
            self._cursor = 0
        return raw

    def _issue(self, code: str, count: int, detail: str) -> None:
        offset = self._buffer_offset
        if len(self._issues) < self.max_issues:
            preview_count = min(count, self.max_issue_raw_bytes)
            raw = bytes(self._buffer[self._cursor : self._cursor + preview_count])
            self._append_issue(
                FramingIssue(
                    code=code,
                    stream_offset=offset,
                    raw=raw,
                    detail=detail,
                    span_length=count,
                )
            )
        else:
            self._omitted_issue_count += 1
        self._cursor += count
        self._buffer_offset += count
        if self._cursor == len(self._buffer):
            self._buffer.clear()
            self._cursor = 0

    def _append_issue(self, issue: FramingIssue) -> None:
        if len(self._issues) < self.max_issues:
            self._issues.append(issue)
        else:
            self._omitted_issue_count += 1

    def _finalize_omitted_issues(self) -> None:
        if not self._omitted_issue_count:
            return
        omitted = self._omitted_issue_count
        summary = FramingIssue(
            code="issue_limit_exceeded",
            stream_offset=self._bytes_seen,
            raw=b"",
            detail=f"{omitted} additional framing issue(s) omitted by the diagnostic limit",
            span_length=0,
        )
        if len(self._issues) >= self.max_issues:
            # Reserve one bounded slot for the fact that diagnostics were
            # incomplete; the authoritative RAW remains untouched elsewhere.
            self._issues[-1] = summary
        else:
            self._issues.append(summary)

    def _append_event(self, stream_event: StreamEvent) -> None:
        if len(self._events) < self.max_events:
            self._events.append(stream_event)
            return
        self._note_event_limit(stream_event.stream_offset)

    def _note_event_limit(self, stream_offset: int) -> None:
        if self._events_truncated:
            return
        self._events_truncated = True
        self._append_issue(
            FramingIssue(
                code="event_limit_exceeded",
                stream_offset=stream_offset,
                raw=b"",
                detail=(
                    f"more than {self.max_events} stream events observed; "
                    "additional parsed events were not retained"
                ),
                span_length=0,
            )
        )

    def _next_control(self, start: int = 0) -> int | None:
        for relative in range(start, self._available):
            if self._buffer[self._cursor + relative] in (STX, ACK):
                return relative
        return None

    def _next_plausible_control(self, start: int = 0) -> int | None:
        """Find an ACK or an STX that can still begin a decimal header."""

        absolute_start = self._cursor + start
        match = _PLAUSIBLE_CONTROL_RE.search(self._buffer, absolute_start)
        if match is not None:
            return match.start() - self._cursor

        # A final incomplete STX may become a valid header after the next
        # feed.  Of overlapping tail candidates only the last can still do so,
        # because any earlier one's five-digit field already contains STX.
        tail_start = max(absolute_start, len(self._buffer) - 5)
        partial = self._buffer.rfind(bytes((STX,)), tail_start)
        if partial >= 0:
            return partial - self._cursor
        return None

    def _reject_candidate(self, code: str, detail: str, *, plausible_only: bool = False) -> None:
        # A malformed header can be a long run of hostile STX bytes.  Skip to
        # the next header that could actually be parsed so rejection remains
        # linear.  Once AA/LLL have parsed, however, the next literal control
        # byte is a distinct candidate and must retain its own diagnostic.
        finder = self._next_plausible_control if plausible_only else self._next_control
        next_control = finder(1)
        self._issue(code, next_control if next_control is not None else self._available, detail)

    def _process(self, *, final: bool) -> None:
        while self._available:
            base = self._cursor
            first = self._buffer[base]
            if first == ACK:
                offset = self._buffer_offset
                if len(self._events) >= self.max_events:
                    run_length = 1
                    while run_length < self._available and self._buffer[base + run_length] == ACK:
                        run_length += 1
                    self._consume(run_length)
                    self._event_count += run_length
                    self._ack_count += run_length
                    self._note_event_limit(offset)
                else:
                    raw = self._consume(1)
                    self._event_count += 1
                    self._ack_count += 1
                    self._append_event(AckEvent(event_id=self._event_count, stream_offset=offset, raw=raw))
                continue

            if first != STX:
                next_control = self._next_control(1)
                count = next_control if next_control is not None else self._available
                self._issue("unframed_bytes", count, "bytes outside an STX frame or standalone ACK")
                continue

            if self._available < 6:
                if final:
                    self._issue("truncated_frame", self._available, "stream ended inside the fixed frame header")
                break

            address_bytes = bytes(self._buffer[base + 1 : base + 3])
            length_bytes = bytes(self._buffer[base + 3 : base + 6])
            if not (address_bytes.isdigit() and length_bytes.isdigit()):
                self._reject_candidate(
                    "malformed_header",
                    "AA and LLL must be ASCII decimal digits",
                    plausible_only=True,
                )
                continue

            data_length = int(length_bytes)
            if data_length > self.max_data_length:
                self._reject_candidate(
                    "oversize_frame",
                    f"declared data length {data_length} exceeds configured limit {self.max_data_length}",
                )
                continue

            expected_size = data_length + _FRAME_OVERHEAD
            if self._available < expected_size:
                if final:
                    self._issue(
                        "truncated_frame",
                        self._available,
                        f"declared frame size {expected_size} bytes but only {self._available} remain",
                    )
                break

            if self._buffer[base + expected_size - 1] != ETX:
                self._reject_candidate(
                    "invalid_terminator",
                    f"expected ETX at relative offset {expected_size - 1}",
                )
                continue

            bcc_start = base + expected_size - 3
            bcc_bytes = bytes(self._buffer[bcc_start : bcc_start + 2])
            bcc_syntax_valid = len(bcc_bytes) == 2 and all(byte in _HEX_DIGITS for byte in bcc_bytes)
            bcc_value = 0
            for index in range(base, bcc_start):
                bcc_value ^= self._buffer[index]
            expected_bcc = f"{bcc_value:02X}"
            actual_bcc = bcc_bytes.decode("ascii", errors="replace")
            bcc_valid = bcc_syntax_valid and actual_bcc.upper() == expected_bcc

            offset = self._buffer_offset
            self._event_count += 1
            self._frame_count += 1
            retain_event = len(self._events) < self.max_events
            raw = bytes(self._buffer[base : base + expected_size]) if retain_event or not bcc_valid else b""
            frame_class = chr(self._buffer[base + 6])
            sequence = chr(self._buffer[base + 7 + data_length])
            self._consume(expected_size)
            if retain_event:
                frame = RCHFrame(
                    event_id=self._event_count,
                    frame_id=self._frame_count,
                    stream_offset=offset,
                    raw=raw,
                    address=address_bytes.decode("ascii"),
                    data_length=data_length,
                    frame_class=frame_class,
                    data=raw[7 : 7 + data_length],
                    sequence=sequence,
                    bcc=actual_bcc,
                    expected_bcc=expected_bcc,
                    bcc_valid=bcc_valid,
                )
                self._append_event(frame)
            else:
                self._note_event_limit(offset)
            if not bcc_valid:
                detail = (
                    f"BCC field {actual_bcc!r} is not two hexadecimal digits"
                    if not bcc_syntax_valid
                    else f"observed BCC {actual_bcc.upper()} does not match calculated {expected_bcc}"
                )
                self._append_issue(
                    FramingIssue(
                        code="invalid_bcc",
                        stream_offset=offset,
                        raw=raw[: self.max_issue_raw_bytes],
                        detail=detail,
                        span_length=expected_size,
                    )
                )

# Backwards/discoverability aliases without duplicating parser state.
IncrementalFramer = RCHStreamFramer


def frame_stream(
    payload: bytes,
    *,
    max_data_length: int = 999,
    max_buffer_bytes: int = 4096,
    max_events: int = _DEFAULT_MAX_EVENTS,
    max_issues: int = _DEFAULT_MAX_ISSUES,
    max_issue_raw_bytes: int = _DEFAULT_MAX_ISSUE_RAW_BYTES,
) -> FramingResult:
    framer = RCHStreamFramer(
        max_data_length=max_data_length,
        max_buffer_bytes=max_buffer_bytes,
        max_events=max_events,
        max_issues=max_issues,
        max_issue_raw_bytes=max_issue_raw_bytes,
    )
    framer.feed(payload)
    return framer.finish()


def assess_framing(payload: bytes) -> FramingAssessment:
    result = frame_stream(payload)
    frames = result.frames
    if not frames:
        return FramingAssessment()
    valid_count = sum(frame.bcc_valid for frame in frames)
    confirmed = valid_count == len(frames) and not result.issues
    return FramingAssessment(
        confirmed=confirmed,
        frame_count=len(frames),
        evidence="CONFIRMED" if confirmed else "OBSERVED",
        reason=(
            "all complete frames satisfy capture-confirmed length, delimiter and XOR BCC rules"
            if confirmed
            else f"{valid_count}/{len(frames)} complete frames have a valid XOR BCC; {len(result.issues)} issue(s)"
        ),
    )
