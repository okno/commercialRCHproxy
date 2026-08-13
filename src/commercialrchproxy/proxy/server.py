"""Listener and graceful service shutdown."""

from __future__ import annotations

import asyncio
import errno
import logging

from commercialrchproxy.config import Config
from commercialrchproxy.logging.structured import event
from commercialrchproxy.metrics import Metrics
from commercialrchproxy.proxy.session import ProxySession
from commercialrchproxy.storage.spool import RawSpoolStorage


class BindError(RuntimeError):
    pass


class ProxyServer:
    def __init__(self, config: Config, storage: RawSpoolStorage, logger: logging.Logger, metrics: Metrics) -> None:
        self.config = config
        self.storage = storage
        self.logger = logger
        self.metrics = metrics
        self._server: asyncio.AbstractServer | None = None
        self._sessions: set[asyncio.Task[None]] = set()
        self._persistence_tasks: set[asyncio.Task[None]] = set()
        self._device_session_lock = asyncio.Lock()

    async def start(self) -> None:
        try:
            self._server = await asyncio.start_server(
                self._accept,
                host=self.config.listen_ip,
                port=self.config.listen_port,
                start_serving=True,
            )
        except OSError as exc:
            if exc.errno in {errno.EADDRNOTAVAIL, 10049}:
                raise BindError(
                    f"Cannot bind {self.config.listen_ip}:{self.config.listen_port}. "
                    "The IP address is not assigned to this host."
                ) from exc
            if exc.errno in {errno.EACCES, 10013}:
                raise BindError(
                    f"Cannot bind privileged port {self.config.listen_port}; "
                    "grant only CAP_NET_BIND_SERVICE to the service"
                ) from exc
            raise BindError(f"Cannot bind {self.config.listen_ip}:{self.config.listen_port}: {exc}") from exc
        event(
            self.logger,
            "service_start",
            "commercialRCHproxy listener started",
            listen_ip=self.config.listen_ip,
            listen_port=self.config.listen_port,
            printer_ip=self.config.printer_ip,
            printer_port=self.config.printer_port,
            protocol_semantics="UNCONFIRMED",
        )
        recover_partials = getattr(self.storage, "recover_partials", None)
        abandoned = recover_partials() if callable(recover_partials) else []
        for path in abandoned:
            self.logger.critical(
                "Abandoned partial capture preserved for offline recovery",
                extra={
                    "event": "capture_partial_recovery_required",
                    "fields": {"path": str(path), "parser_visibility": "not_ready"},
                },
            )

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if len(self._sessions) >= self.config.max_connections:
            peer = writer.get_extra_info("peername")
            event(
                self.logger,
                "connection_limit_reached",
                "Client connection rejected before opening an upstream session",
                peer=str(peer),
                max_connections=self.config.max_connections,
            )
            writer.transport.abort()
            return
        session = ProxySession(
            reader,
            writer,
            self.config,
            self.storage,
            self.logger,
            self.metrics,
            self._device_session_lock,
            self._persistence_tasks,
        )
        task = asyncio.create_task(session.run(), name=f"session-{session.session_id}")
        self._sessions.add(task)
        task.add_done_callback(self._session_done)

    def _session_done(self, task: asyncio.Task[None]) -> None:
        self._sessions.discard(task)
        if not task.cancelled() and task.exception() is not None:
            self.logger.error(
                "Session task failed",
                extra={"event": "session_task_error", "fields": {"error": str(task.exception())}},
            )

    async def serve_forever(self) -> None:
        if self._server is None:
            raise RuntimeError("Server not started")
        async with self._server:
            await self._server.serve_forever()

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        if self._sessions:
            done, pending = await asyncio.wait(self._sessions, timeout=self.config.shutdown_grace_sec)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        if self._persistence_tasks:
            _done, pending_persistence = await asyncio.wait(
                self._persistence_tasks,
                timeout=self.config.shutdown_grace_sec,
            )
            for task in pending_persistence:
                task.cancel()
            if pending_persistence:
                await asyncio.gather(*pending_persistence, return_exceptions=True)
        event(self.logger, "service_stop", "commercialRCHproxy stopped", metrics=self.metrics.snapshot())
