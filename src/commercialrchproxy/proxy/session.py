"""Full-duplex session lifecycle with bounded post-half-close draining."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import asdict

from commercialrchproxy.capture.jobs import CLIENT_TO_RCH, RCH_TO_CLIENT
from commercialrchproxy.capture.recorder import JobCaptureManager
from commercialrchproxy.config import Config
from commercialrchproxy.logging.structured import event
from commercialrchproxy.metrics import Metrics
from commercialrchproxy.proxy.streams import PumpResult, pump
from commercialrchproxy.rch.state_machine import SessionState
from commercialrchproxy.storage.files import JobStorage


async def _close_writer(writer: asyncio.StreamWriter | None, *, abort: bool = False) -> None:
    if writer is None:
        return
    try:
        if abort:
            transport = writer.transport
            transport.abort()
        else:
            writer.close()
            await asyncio.wait_for(writer.wait_closed(), timeout=5.0)
    except (TimeoutError, ConnectionError, OSError, RuntimeError):
        return


class ProxySession:
    def __init__(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        config: Config,
        storage: JobStorage,
        logger: logging.Logger,
        metrics: Metrics,
        device_session_lock: asyncio.Lock,
    ) -> None:
        self.client_reader = client_reader
        self.client_writer = client_writer
        self.config = config
        self.storage = storage
        self.logger = logger
        self.metrics = metrics
        self.device_session_lock = device_session_lock
        self.session_id = uuid.uuid4().hex
        peer = client_writer.get_extra_info("peername") or ("unknown", None)
        self.client_ip = str(peer[0])
        self.client_port = int(peer[1]) if len(peer) > 1 and peer[1] is not None else None
        self.state = SessionState.ACCEPTED
        self._printer_writer: asyncio.StreamWriter | None = None

    async def run(self) -> None:
        self.metrics.increment("sessions_total")
        event(
            self.logger,
            "session_start",
            "Client session accepted",
            session_id=self.session_id,
            client=f"{self.client_ip}:{self.client_port}",
            proxy=f"{self.config.listen_ip}:{self.config.listen_port}",
            printer=f"{self.config.printer_ip}:{self.config.printer_port}",
        )
        recorder = JobCaptureManager(
            self.config,
            self.storage,
            self.logger,
            self.metrics,
            session_id=self.session_id,
            client_ip=self.client_ip,
            client_port=self.client_port,
        )
        transport_status = "stream_closed_application_status_unknown"
        abort_client = False
        tail_timed_out = False
        pump_tasks: set[asyncio.Task[PumpResult]] = set()
        device_lock_acquired = False
        try:
            event(
                self.logger,
                "device_session_queued",
                "Session waiting for exclusive access to the configured RCH endpoint",
                session_id=self.session_id,
            )
            await self.device_session_lock.acquire()
            device_lock_acquired = True
            self.state = SessionState.CONNECTING_PRINTER
            try:
                printer_reader, printer_writer = await asyncio.wait_for(
                    asyncio.open_connection(self.config.printer_ip, self.config.printer_port),
                    timeout=self.config.connection_timeout_sec,
                )
                self._printer_writer = printer_writer
            except (TimeoutError, ConnectionError, OSError) as exc:
                self.state = SessionState.PRINTER_UNREACHABLE
                self.metrics.increment("printer_connect_errors")
                transport_status = "printer_unreachable"
                abort_client = True
                event(
                    self.logger,
                    "printer_unreachable",
                    "Cannot connect to RCH printer",
                    session_id=self.session_id,
                    printer=f"{self.config.printer_ip}:{self.config.printer_port}",
                    error=f"{type(exc).__name__}: {exc}",
                )
                return

            self.state = SessionState.FORWARDING
            c2r = asyncio.create_task(
                pump(
                    self.client_reader,
                    printer_writer,
                    direction=CLIENT_TO_RCH,
                    recorder=recorder,
                    config=self.config,
                    logger=self.logger,
                    metrics=self.metrics,
                    session_id=self.session_id,
                ),
                name=f"{self.session_id}-client-to-rch",
            )
            r2c = asyncio.create_task(
                pump(
                    printer_reader,
                    self.client_writer,
                    direction=RCH_TO_CLIENT,
                    recorder=recorder,
                    config=self.config,
                    logger=self.logger,
                    metrics=self.metrics,
                    session_id=self.session_id,
                ),
                name=f"{self.session_id}-rch-to-client",
            )
            pump_tasks = {c2r, r2c}
            done, pending = await asyncio.wait(pump_tasks, return_when=asyncio.FIRST_COMPLETED)
            first_results = [task.result() for task in done]
            first_errors = [result for result in first_results if result.error]
            if first_errors:
                # Once either copy direction fails, continuing the opposite
                # direction could deliver additional application bytes after
                # the relay can no longer provide full-duplex behavior.
                for task in pending:
                    task.cancel()
                cancelled_results = await asyncio.gather(*pending, return_exceptions=False) if pending else []
                results = first_results + list(cancelled_results)
            elif pending:
                self.state = SessionState.DRAINING_RESPONSE
                await recorder.begin_session_tail()
                done_tail, still_pending = await asyncio.wait(
                    pending,
                    timeout=self.config.response_timeout_sec,
                    return_when=asyncio.ALL_COMPLETED,
                )
                results = first_results + [task.result() for task in done_tail]
                for task in still_pending:
                    task.cancel()
                if still_pending:
                    tail_timed_out = True
                    results.extend(await asyncio.gather(*still_pending, return_exceptions=False))
            else:
                results = first_results

            errors = [result for result in results if isinstance(result, PumpResult) and result.error]
            if errors:
                self.state = SessionState.TRANSPORT_ERROR
                transport_status = (
                    "tail_timeout_transport_incomplete_application_status_unknown"
                    if tail_timed_out
                    else "transport_error_application_status_unknown"
                )
                abort_client = any(result.direction == RCH_TO_CLIENT for result in errors)
            else:
                self.state = SessionState.CLOSED
                transport_status = "stream_closed_delivery_and_application_status_unknown"
            event(
                self.logger,
                "session_streams_complete",
                "Bidirectional stream pumps completed",
                session_id=self.session_id,
                results=[asdict(result) for result in results],
            )
        except asyncio.CancelledError:
            transport_status = "service_shutdown_application_status_unknown"
            raise
        except Exception as exc:
            self.state = SessionState.TRANSPORT_ERROR
            transport_status = "transport_error_application_status_unknown"
            abort_client = True
            self.logger.exception(
                "Unhandled proxy session error",
                extra={"event": "session_error", "fields": {"session_id": self.session_id, "error": str(exc)}},
            )
        finally:
            persistence_finalized = False
            try:
                try:
                    unfinished = [task for task in pump_tasks if not task.done()]
                    for task in unfinished:
                        task.cancel()
                    if unfinished:
                        await asyncio.gather(*unfinished, return_exceptions=True)
                    await recorder.finalize(transport_status)
                    persistence_finalized = True
                finally:
                    await _close_writer(self._printer_writer)
                    await _close_writer(self.client_writer, abort=abort_client)
            finally:
                if device_lock_acquired:
                    self.device_session_lock.release()
            # Persistence may start once finalize() seals the segment, but do
            # not await its hashing/rendering/fsync completion until transports
            # are closed and the exclusive device lock is released.  The server
            # still tracks this session task for graceful shutdown.
            if persistence_finalized:
                await recorder.wait_for_persistence()
            event(
                self.logger,
                "session_end",
                "Client session ended",
                session_id=self.session_id,
                state=self.state.value,
                transport_status=transport_status,
                application_success=None,
            )
