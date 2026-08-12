"""Non-inline idle-fallback job recorder.

The idle timer is explicitly a fallback until a documented/observed RCH job
boundary is available.  Storage and parsing run in background tasks.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from time import monotonic_ns

from commercialrchproxy.capture.jobs import (
    CLIENT_TO_RCH,
    RCH_TO_CLIENT,
    CapturedJob,
    CaptureToken,
    utc_now,
)
from commercialrchproxy.config import Config
from commercialrchproxy.logging.structured import event
from commercialrchproxy.metrics import Metrics
from commercialrchproxy.rch.framing import RCHFrame, RCHStreamFramer
from commercialrchproxy.storage.files import ArchiveResult, JobStorage

_ACK = 0x06
_MAX_RESPONSE_HINTS = 4096
_MAX_HINT_BYTES_PER_CHUNK = 8192


def _decimal_sequence(frame: RCHFrame) -> int | None:
    return int(frame.sequence) if len(frame.sequence) == 1 and frame.sequence.isdecimal() else None


@dataclass(frozen=True, slots=True)
class _Observation:
    stale_response_matches: int = 0
    unmatched_response_frames: int = 0


class JobCaptureManager:
    def __init__(
        self,
        config: Config,
        storage: JobStorage,
        logger: logging.Logger,
        metrics: Metrics,
        *,
        session_id: str,
        client_ip: str,
        client_port: int | None,
    ) -> None:
        self.config = config
        self.storage = storage
        self.logger = logger
        self.metrics = metrics
        self.session_id = session_id
        self.client_ip = client_ip
        self.client_port = client_port
        self._active: CapturedJob | None = None
        self._lock = asyncio.Lock()
        self._idle_task: asyncio.Task[None] | None = None
        self._persist_tasks: set[asyncio.Task[None]] = set()
        self._generation = 0
        self._closed = False
        self._session_tail_active = False
        self._request_framer = RCHStreamFramer(retain_history=False)
        self._response_framer = RCHStreamFramer(retain_history=False)
        # These queues are only non-authoritative boundary hints.  Bound them
        # independently from the RAW capture so an unresponsive peer cannot
        # grow process memory indefinitely by sending valid request frames.
        self._pending_responses: deque[int] = deque(maxlen=_MAX_RESPONSE_HINTS)
        self._stale_pending_responses: deque[int] = deque(maxlen=_MAX_RESPONSE_HINTS)
        self._response_hint_limit_reported = False
        self._hint_budget_reported = False
        self._boundary_hints_degraded = False
        self._commercial_candidate_open = False
        self._management_candidate_open = False
        self._active_is_orphan_late_response = False
        self._chunk_sequence = 0
        self._session_offsets = {CLIENT_TO_RCH: 0, RCH_TO_CLIENT: 0}

    def _new_job(self) -> CapturedJob:
        self.metrics.increment("jobs_total")
        return CapturedJob(
            session_id=self.session_id,
            client_ip=self.client_ip,
            client_port=self.client_port,
            proxy_ip=self.config.listen_ip,
            proxy_port=self.config.listen_port,
            printer_ip=self.config.printer_ip,
            printer_port=self.config.printer_port,
            max_payload_bytes=self.config.max_payload_bytes,
        )

    async def record(self, direction: str, data: bytes) -> CaptureToken | None:
        if self._closed or not data:
            return None
        async with self._lock:
            observed_before_append = False
            observation = _Observation()
            suspected_orphan_ack = False
            # Classify, but never discard, a response which arrives after the
            # bounded fallback already archived its incomplete request.
            if self._active is None and direction == RCH_TO_CLIENT:
                observation = self._observe(direction, data)
                observed_before_append = True
                suspected_orphan_ack = bool(
                    self._stale_pending_responses and data and all(byte == _ACK for byte in data)
                )
            if self._active is None:
                self._active = self._new_job()
                self._reset_active_protocol_state()
                self._active_is_orphan_late_response = bool(
                    observation.stale_response_matches or suspected_orphan_ack
                )
            self._chunk_sequence += 1
            session_offset = self._session_offsets.get(direction, 0)
            observed_at = utc_now().isoformat()
            observed_monotonic_ns = monotonic_ns()
            chunk_index = self._active.append(
                direction,
                data,
                sequence=self._chunk_sequence,
                session_offset=session_offset,
                timestamp=observed_at,
                observed_monotonic_ns=observed_monotonic_ns,
            )
            self._advance_session_position(direction, len(data))
            if not observed_before_append:
                observation = self._observe(direction, data)
            if observation.stale_response_matches:
                self._active_is_orphan_late_response = True
                event(
                    self.logger,
                    "late_correlated_response_segment",
                    "A response arrived after its request segment timed out; RAW bytes were retained separately",
                    session_id=self.session_id,
                    job_id=self._active.job_id,
                    response_frames=observation.stale_response_matches,
                )
            token = CaptureToken(self._active.job_id, chunk_index, direction, len(data))
            self._generation += 1
            if self._idle_task is not None:
                self._idle_task.cancel()
                self._idle_task = None
            return token

    def _advance_session_position(self, direction: str, byte_count: int) -> None:
        self._session_offsets[direction] = self._session_offsets.get(direction, 0) + byte_count

    def _reset_active_protocol_state(self) -> None:
        self._pending_responses.clear()
        self._commercial_candidate_open = False
        self._management_candidate_open = False

    def _append_response_hint(self, queue: deque[int], sequence: int) -> None:
        if len(queue) == queue.maxlen and not self._response_hint_limit_reported:
            self._response_hint_limit_reported = True
            event(
                self.logger,
                "capture_boundary_hint_limit",
                "Response-correlation hint queue reached its bound; oldest hints will be discarded",
                session_id=self.session_id,
                max_hints=queue.maxlen,
            )
        queue.append(sequence)

    def _carry_pending_hints_to_stale(self) -> None:
        for sequence in self._pending_responses:
            self._append_response_hint(self._stale_pending_responses, sequence)

    def _observe(self, direction: str, data: bytes) -> _Observation:
        """Update only fallback-boundary hints; malformed input is fail-open."""
        try:
            if len(data) > _MAX_HINT_BYTES_PER_CHUNK:
                self._boundary_hints_degraded = True
                if direction == CLIENT_TO_RCH:
                    self._request_framer = RCHStreamFramer(retain_history=False)
                else:
                    self._response_framer = RCHStreamFramer(retain_history=False)
                if not self._hint_budget_reported:
                    self._hint_budget_reported = True
                    event(
                        self.logger,
                        "capture_boundary_hint_budget",
                        "Oversized receive chunk skipped by the non-authoritative boundary hint parser",
                        session_id=self.session_id,
                        max_hint_bytes_per_chunk=_MAX_HINT_BYTES_PER_CHUNK,
                    )
                return _Observation(unmatched_response_frames=1 if direction == RCH_TO_CLIENT else 0)
            if direction == CLIENT_TO_RCH:
                event_items = self._request_framer.feed(data)
                for event_item in event_items:
                    if (
                        not isinstance(event_item, RCHFrame)
                        or not event_item.bcc_valid
                        or event_item.address != "00"
                        or event_item.frame_class != "z"
                    ):
                        continue
                    sequence = _decimal_sequence(event_item)
                    if sequence is not None:
                        self._append_response_hint(self._pending_responses, (sequence + 8) % 10)
                    if event_item.data == b"=K":
                        self._commercial_candidate_open = True
                        self._management_candidate_open = False
                    elif event_item.data == b"<</?" or (
                        len(event_item.data) == 5
                        and event_item.data.startswith(b"<</?")
                        and event_item.data[-1:].isdigit()
                    ):
                        self._commercial_candidate_open = False
                    if event_item.data == b"=o":
                        self._commercial_candidate_open = False
                        self._management_candidate_open = not self._management_candidate_open
                if not self._request_framer.buffered_bytes:
                    # The public framer retains forensic history by design;
                    # the recorder only needs incremental carry-over bytes.
                    self._request_framer = RCHStreamFramer(retain_history=False)
                return _Observation()

            stale_matches = 0
            unmatched = 0
            event_items = self._response_framer.feed(data)
            for event_item in event_items:
                if (
                    not isinstance(event_item, RCHFrame)
                    or not event_item.bcc_valid
                    or event_item.address != "01"
                    or event_item.frame_class != "N"
                ):
                    continue
                sequence = _decimal_sequence(event_item)
                if sequence is None:
                    unmatched += 1
                    continue
                if self._pending_responses and sequence == self._pending_responses[0]:
                    self._pending_responses.popleft()
                elif not self._pending_responses and self._stale_pending_responses:
                    if sequence == self._stale_pending_responses[0]:
                        self._stale_pending_responses.popleft()
                        stale_matches += 1
                    else:
                        unmatched += 1
                else:
                    unmatched += 1
            if not self._response_framer.buffered_bytes:
                self._response_framer = RCHStreamFramer(retain_history=False)
            return _Observation(stale_response_matches=stale_matches, unmatched_response_frames=unmatched)
        except Exception as exc:
            # Capture and forwarding must never depend on the boundary hint.
            self.metrics.increment("parser_errors")
            event(
                self.logger,
                "capture_boundary_hint_error",
                "Observed-frame boundary hint failed; opaque capture continues",
                session_id=self.session_id,
                direction=direction,
                error=f"{type(exc).__name__}: {exc}",
            )
            return _Observation(unmatched_response_frames=1 if direction == RCH_TO_CLIENT else 0)

    def _needs_extended_idle(self) -> bool:
        return bool(
            self._pending_responses
            or self._commercial_candidate_open
            or self._management_candidate_open
            or (self._active_is_orphan_late_response and self._stale_pending_responses)
            or self._request_framer.buffered_bytes
            or self._response_framer.buffered_bytes
            or self._boundary_hints_degraded
        )

    async def mark_local_write_drain(self, token: CaptureToken, completed: bool) -> None:
        async with self._lock:
            if self._active is None or self._active.job_id != token.job_id:
                return
            self._active.mark_local_write_drain(token, completed)
            self._generation += 1
            generation = self._generation
            if self._idle_task is not None:
                self._idle_task.cancel()
            if self._session_tail_active:
                self._idle_task = None
                return
            # ACK (0x06) is transport/application chatter, not completion of
            # the queued request.  Keep the segment open through the response
            # window while an observed response or document close is pending.
            idle_delay = self.config.job_idle_timeout_ms / 1000.0
            delay = self.config.response_timeout_sec + idle_delay if self._needs_extended_idle() else idle_delay
            self._idle_task = asyncio.create_task(self._idle_watch(generation, delay))

    async def begin_session_tail(self) -> None:
        """Keep the active segment open once either stream direction ends.

        This ensures a later tail timeout is recorded on the segment instead
        of letting an inactivity timer archive it as a clean local close.
        """
        async with self._lock:
            self._session_tail_active = True
            if self._idle_task is not None:
                self._idle_task.cancel()
                self._idle_task = None

    async def _idle_watch(self, generation: int, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            async with self._lock:
                if generation != self._generation or self._active is None:
                    return
                job = self._active
                self._active = None
                self._idle_task = None
                self._carry_pending_hints_to_stale()
                self._reset_active_protocol_state()
                self._boundary_hints_degraded = False
                if self._active_is_orphan_late_response:
                    job.boundary_source = "orphan_late_response"
                    job.boundary_confidence = 0.10
                else:
                    job.boundary_source = "fallback_inactivity"
                    job.boundary_confidence = 0.20
                self._active_is_orphan_late_response = False
                job.finish()
            self._schedule_persist(job)
        except asyncio.CancelledError:
            return

    def _schedule_persist(self, job: CapturedJob) -> None:
        task = asyncio.create_task(self._persist(job))
        self._persist_tasks.add(task)
        task.add_done_callback(self._persist_tasks.discard)

    async def _persist(self, job: CapturedJob) -> None:
        try:
            result: ArchiveResult = await asyncio.to_thread(self.storage.archive, job)
            self.metrics.increment("jobs_completed")
            event(
                self.logger,
                "capture_segment_archived",
                "Fallback-bounded capture segment archived",
                session_id=job.session_id,
                job_id=job.job_id,
                status=result.status,
                manifest=str(result.manifest_path),
            )
        except Exception as exc:
            self.metrics.increment("jobs_failed")
            self.metrics.increment("render_errors")
            self.logger.exception(
                "Failed to archive captured job",
                extra={
                    "event": "capture_segment_archive_failed",
                    "fields": {"session_id": job.session_id, "job_id": job.job_id, "error": str(exc)},
                },
            )

    async def finalize(self, transport_status: str = "connection_closed") -> None:
        """Seal the active capture and schedule persistence without waiting."""
        self._closed = True
        async with self._lock:
            if self._idle_task is not None:
                self._idle_task.cancel()
                self._idle_task = None
            job = self._active
            self._active = None
            if job is not None:
                if self._active_is_orphan_late_response:
                    job.boundary_source = "orphan_late_response"
                    job.boundary_confidence = 0.10
                else:
                    job.boundary_source = "fallback_connection_close"
                    job.boundary_confidence = 0.15
                self._active_is_orphan_late_response = False
                job.finish(transport_status)
        if job is not None:
            self._schedule_persist(job)

    async def wait_for_persistence(self) -> None:
        """Wait for this session's already-scheduled archive tasks."""
        if self._persist_tasks:
            await asyncio.gather(*tuple(self._persist_tasks), return_exceptions=True)
