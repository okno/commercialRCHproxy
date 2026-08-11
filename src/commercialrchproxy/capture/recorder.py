"""Non-inline idle-fallback job recorder.

The idle timer is explicitly a fallback until a documented/observed RCH job
boundary is available.  Storage and parsing run in background tasks.
"""

from __future__ import annotations

import asyncio
import logging

from commercialrchproxy.capture.jobs import CapturedJob, CaptureToken
from commercialrchproxy.config import Config
from commercialrchproxy.logging.structured import event
from commercialrchproxy.metrics import Metrics
from commercialrchproxy.storage.files import ArchiveResult, JobStorage


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
            if self._active is None:
                self._active = self._new_job()
            chunk_index = self._active.append(direction, data)
            token = CaptureToken(self._active.job_id, chunk_index, direction, len(data))
            self._generation += 1
            if self._idle_task is not None:
                self._idle_task.cancel()
                self._idle_task = None
            return token

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
            # Do not cut a request away from a delayed response merely because
            # the 1 s rendering fallback elapsed.  Before any response copy is
            # observed, allow the configured response window.  Once response
            # bytes arrive, ordinary job-idle quiescence can close the copy.
            delay = (
                self.config.job_idle_timeout_ms / 1000.0
                if self._active.response
                else self.config.response_timeout_sec + self.config.job_idle_timeout_ms / 1000.0
            )
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
                job.boundary_source = "fallback_inactivity"
                job.boundary_confidence = 0.20
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
                job.boundary_source = "fallback_connection_close"
                job.boundary_confidence = 0.15
                job.finish(transport_status)
        if job is not None:
            self._schedule_persist(job)

    async def wait_for_persistence(self) -> None:
        """Wait for this session's already-scheduled archive tasks."""
        if self._persist_tasks:
            await asyncio.gather(*tuple(self._persist_tasks), return_exceptions=True)
