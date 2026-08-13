"""Dumper-only capture manager.

This module intentionally performs no RCH framing, document boundary
inference, decoding, TXT generation or PDF rendering.  A complete transport
connection becomes one atomically published spool job; semantic documents are
split later by the independent parser process.
"""

from __future__ import annotations

import asyncio
import logging
from time import monotonic_ns, time_ns
from typing import Any

from commercialrchproxy.capture.jobs import CLIENT_TO_RCH, CapturedChunk, CapturedJob, CaptureToken
from commercialrchproxy.config import Config
from commercialrchproxy.logging.structured import event
from commercialrchproxy.metrics import Metrics
from commercialrchproxy.storage.spool import LiveSpoolCapture, RawSpoolStorage, SpoolArchiveResult

_CAPTURE_QUEUE_BYTE_BUDGET = 8 * 1024 * 1024


class JobCaptureManager:
    def __init__(
        self,
        config: Config,
        storage: RawSpoolStorage,
        logger: logging.Logger,
        metrics: Metrics,
        *,
        session_id: str,
        client_ip: str,
        client_port: int | None,
        connection_id: str | None = None,
    ) -> None:
        self.config = config
        self.storage = storage
        self.logger = logger
        self.metrics = metrics
        self.session_id = session_id
        self.connection_id = connection_id or session_id
        self.client_ip = client_ip
        self.client_port = client_port
        self._active: CapturedJob | None = None
        self._lock = asyncio.Lock()
        self._closed = False
        self._event_sequence = 0
        self._session_offsets = {"CLIENT -> RCH": 0, "RCH -> CLIENT": 0}
        self._persist_tasks: set[asyncio.Task[None]] = set()
        self._persist_errors: list[Exception] = []
        self._streaming = callable(getattr(storage, "begin_live", None))
        queue_items = max(1, min(256, _CAPTURE_QUEUE_BYTE_BUDGET // config.buffer_size))
        self._stream_queue: asyncio.Queue[tuple[Any, ...]] | None = (
            asyncio.Queue(maxsize=queue_items) if self._streaming else None
        )
        # Finalization must never depend on finding room in the bounded data
        # queue.  The unbounded control queue wakes a consumer that is waiting
        # on an empty data queue; the event remains authoritative if both
        # queues become ready in the same event-loop turn.
        self._stream_finalize_requested = asyncio.Event()
        self._stream_control: asyncio.Queue[None] = asyncio.Queue()
        self._stream_worker_task: asyncio.Task[None] | None = None
        self._capture_degraded = False
        self._capture_degrade_reason: str | None = None

    def _required_stream_queue(self) -> asyncio.Queue[tuple[Any, ...]]:
        queue = self._stream_queue
        if queue is None:
            raise RuntimeError("live capture queue is not initialized")
        return queue

    def _new_job(self, *, started_unix_ns: int) -> CapturedJob:
        from datetime import UTC, datetime

        return CapturedJob(
            session_id=self.session_id,
            connection_id=self.connection_id,
            client_ip=self.client_ip,
            client_port=self.client_port,
            proxy_ip=self.config.listen_ip,
            proxy_port=self.config.listen_port,
            printer_ip=self.config.printer_ip,
            printer_port=self.config.printer_port,
            max_payload_bytes=self.config.max_payload_bytes,
            max_capture_events=self.config.max_capture_events,
            started_at=datetime.fromtimestamp(started_unix_ns / 1_000_000_000, tz=UTC),
            started_unix_ns=started_unix_ns,
            boundary_source="connection_lifecycle",
            boundary_confidence=0.80,
        )

    async def record(
        self,
        direction: str,
        data: bytes,
        *,
        received_unix_ns: int | None = None,
        forwarded_unix_ns: int | None = None,
    ) -> CaptureToken | None:
        if not data:
            return None
        received_ns = time_ns() if received_unix_ns is None else received_unix_ns
        async with self._lock:
            if self._closed:
                return None
            if self._active is None:
                self._active = self._new_job(started_unix_ns=received_ns)
                if self._streaming:
                    self._start_live_worker(self._active)
            if self._persist_errors and self.config.storage_failure_policy == "abort":
                raise RuntimeError(f"RAW live spool failed: {self._persist_errors[-1]}")
            self._event_sequence += 1
            session_offset = self._session_offsets[direction]
            before_stored = (
                self._active.bytes_stored_from_client
                if direction == CLIENT_TO_RCH
                else self._active.bytes_stored_from_printer
            )
            chunk_index = self._active.append(
                direction,
                data,
                sequence=self._event_sequence,
                session_offset=session_offset,
                timestamp=None,
                observed_monotonic_ns=monotonic_ns(),
                received_unix_ns=received_ns,
                forwarded_unix_ns=forwarded_unix_ns,
                retain_payload=not self._streaming,
            )
            self._session_offsets[direction] += len(data)
            after_stored = (
                self._active.bytes_stored_from_client
                if direction == CLIENT_TO_RCH
                else self._active.bytes_stored_from_printer
            )
            stored = bytes(data[: after_stored - before_stored])
            if self._streaming and not self._persist_errors and not self._capture_degraded:
                chunk: CapturedChunk | None = (
                    self._active.chunks[chunk_index] if chunk_index is not None else None
                )
                await self._enqueue_stream(
                    self._active,
                    ("append", self._event_sequence, direction, stored, chunk),
                )
            return CaptureToken(
                self._active.job_id,
                chunk_index,
                direction,
                len(data),
                self._event_sequence,
            )

    async def mark_local_write_drain(
        self,
        token: CaptureToken,
        completed: bool,
        *,
        error: str | None = None,
    ) -> None:
        async with self._lock:
            if self._active is None or self._active.job_id != token.job_id:
                return
            drain_unix_ns = time_ns()
            self._active.mark_local_write_drain(
                token,
                completed,
                drain_unix_ns=drain_unix_ns,
                error=error,
            )
            if (
                self._streaming
                and token.sequence is not None
                and not self._persist_errors
                and not self._capture_degraded
            ):
                await self._enqueue_stream(
                    self._active,
                    ("drain", token.sequence, completed, drain_unix_ns, error),
                )
            if self._persist_errors and self.config.storage_failure_policy == "abort":
                raise RuntimeError(f"RAW live spool failed: {self._persist_errors[-1]}")

    async def begin_session_tail(self) -> None:
        """Compatibility no-op: transport tail handling belongs to the session."""

    def _schedule_persist(self, job: CapturedJob) -> None:
        task = asyncio.create_task(self._persist(job), name=f"spool-{job.job_id}")
        self._persist_tasks.add(task)
        task.add_done_callback(self._persist_tasks.discard)

    def _start_live_worker(self, job: CapturedJob) -> None:
        if self._stream_worker_task is not None:
            raise RuntimeError("live capture worker already exists")
        task = asyncio.create_task(self._live_worker(job), name=f"spool-live-{job.job_id}")
        self._stream_worker_task = task
        self._persist_tasks.add(task)
        task.add_done_callback(self._persist_tasks.discard)

    async def _enqueue_stream(self, job: CapturedJob, command: tuple[Any, ...]) -> bool:
        """Queue capture work without adding storage latency to relay traffic.

        ``continue`` is the availability-first default.  Once its bounded
        queue fills, this method records an explicit evidence gap and drops
        this and all later capture commands for the connection.  ``abort`` is
        intentionally allowed to apply backpressure and stop the session.
        """
        queue = self._required_stream_queue()
        if self.config.storage_failure_policy == "abort":
            await queue.put(command)
            return True
        try:
            queue.put_nowait(command)
        except asyncio.QueueFull:
            self._mark_capture_degraded(
                job,
                "live spool queue capacity exhausted; RAW/timeline evidence is partial "
                "from this point while relay traffic continued",
            )
            return False
        return True

    def _mark_capture_degraded(self, job: CapturedJob, reason: str) -> None:
        if self._capture_degraded:
            return
        self._capture_degraded = True
        self._capture_degrade_reason = reason
        job.capture_complete = False
        job.timeline_complete = False
        job.capture_error = f"{job.capture_error}; {reason}" if job.capture_error else reason
        job.timeline_error = f"{job.timeline_error}; {reason}" if job.timeline_error else reason
        self.metrics.increment("jobs_failed")
        self.logger.critical(
            "RAW capture degraded because the bounded spool queue is unavailable; relay continues",
            extra={
                "event": "capture_spool_backpressure_degraded",
                "fields": {
                    "session_id": job.session_id,
                    "connection_id": job.connection_id,
                    "job_id": job.job_id,
                    "storage_failure_policy": self.config.storage_failure_policy,
                    "error": reason,
                },
            },
        )

    async def _next_stream_command(self) -> tuple[Any, ...] | None:
        queue = self._required_stream_queue()
        while True:
            if self._stream_finalize_requested.is_set():
                try:
                    return queue.get_nowait()
                except asyncio.QueueEmpty:
                    return None

            data_ready = asyncio.create_task(queue.get())
            control_ready = asyncio.create_task(self._stream_control.get())
            done, pending = await asyncio.wait(
                {data_ready, control_ready},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            if data_ready in done:
                # If finalization raced with the data command, the persistent
                # event ensures that the next iteration still observes it.
                return data_ready.result()
            # A control wake-up carries no data.  Re-check the event and drain
            # all commands that were already accepted before publishing.

    async def _live_worker(self, job: CapturedJob) -> None:
        queue = self._required_stream_queue()
        live: LiveSpoolCapture | None = None
        try:
            live = await asyncio.to_thread(self.storage.begin_live, job)
            while True:
                command = await self._next_stream_command()
                if command is None:
                    if self._capture_degraded:
                        await asyncio.to_thread(
                            live.close_incomplete,
                            job,
                            reason=self._capture_degrade_reason,
                        )
                        return
                    result = await asyncio.to_thread(live.finalize, job)
                    self._log_ready(job, result)
                    return
                try:
                    operation = command[0]
                    if operation == "append":
                        _, sequence, direction, data, chunk = command
                        await asyncio.to_thread(
                            live.append,
                            sequence=sequence,
                            direction=direction,
                            data=data,
                            timeline_chunk=chunk,
                        )
                    elif operation == "drain":
                        _, sequence, completed, drain_unix_ns, error = command
                        await asyncio.to_thread(
                            live.mark_local_write_drain,
                            sequence=sequence,
                            completed=completed,
                            drain_unix_ns=drain_unix_ns,
                            error=error,
                        )
                    else:
                        raise RuntimeError(f"unknown live spool operation: {operation!r}")
                finally:
                    queue.task_done()
        except Exception as exc:
            await self._record_storage_failure(job, exc, live)

    async def _record_storage_failure(
        self,
        job: CapturedJob,
        exc: Exception,
        live: LiveSpoolCapture | None,
    ) -> None:
        self._persist_errors.append(exc)
        reason = f"live spool failure: {type(exc).__name__}: {exc}"
        job.capture_complete = False
        job.timeline_complete = False
        job.capture_error = f"{job.capture_error}; {reason}" if job.capture_error else reason
        job.timeline_error = f"{job.timeline_error}; {reason}" if job.timeline_error else reason
        self.metrics.increment("jobs_failed")
        if live is not None:
            try:
                await asyncio.to_thread(live.close_incomplete, job, reason=reason)
            except Exception as cleanup_exc:
                # The primary exception remains the authoritative failure.
                # Cleanup is best effort and must not suppress its CRITICAL
                # record or change the configured relay policy.
                self.logger.error(
                    "Failed to close incomplete RAW capture after storage error",
                    extra={
                        "event": "capture_spool_cleanup_failed",
                        "fields": {
                            "session_id": job.session_id,
                            "job_id": job.job_id,
                            "error": f"{type(cleanup_exc).__name__}: {cleanup_exc}",
                        },
                    },
                )
        self.logger.critical(
            "Failed to append RAW capture; relay policy remains explicit",
            exc_info=(type(exc), exc, exc.__traceback__),
            extra={
                "event": "capture_spool_failed",
                "fields": {
                    "session_id": job.session_id,
                    "connection_id": job.connection_id,
                    "job_id": job.job_id,
                    "storage_failure_policy": self.config.storage_failure_policy,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            },
        )

    def _log_ready(self, job: CapturedJob, result: SpoolArchiveResult) -> None:
        self.metrics.increment("jobs_completed")
        event(
            self.logger,
            "capture_job_ready",
            "Closed transport capture published to the parser spool",
            session_id=job.session_id,
            connection_id=job.connection_id,
            job_id=job.job_id,
            codice_doc=getattr(result, "code", None),
            status=result.status,
            manifest=str(result.manifest_path),
        )

    async def _persist(self, job: CapturedJob) -> None:
        try:
            result: SpoolArchiveResult = await asyncio.to_thread(self.storage.archive, job)
            self._log_ready(job, result)
        except Exception as exc:
            self._persist_errors.append(exc)
            self.metrics.increment("jobs_failed")
            self.logger.critical(
                "Failed to publish RAW capture; relay bytes were not modified",
                exc_info=True,
                extra={
                    "event": "capture_spool_failed",
                    "fields": {
                        "session_id": job.session_id,
                        "connection_id": job.connection_id,
                        "job_id": job.job_id,
                        "storage_failure_policy": self.config.storage_failure_policy,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                },
            )

    async def finalize(self, transport_status: str = "connection_closed") -> None:
        self._closed = True
        async with self._lock:
            job = self._active
            self._active = None
            if job is not None:
                job.finish(transport_status)
        if job is not None:
            if self._streaming:
                # Signalling is out-of-band: even a full queue or a blocked
                # begin_live()/append() cannot hold connection teardown.
                self._stream_finalize_requested.set()
                self._stream_control.put_nowait(None)
            else:
                self._schedule_persist(job)

    async def wait_for_persistence(self) -> None:
        if self._persist_tasks:
            await asyncio.gather(*tuple(self._persist_tasks), return_exceptions=True)
        if self._persist_errors and self.config.storage_failure_policy == "abort":
            raise RuntimeError(f"RAW spool publication failed: {self._persist_errors[-1]}")
