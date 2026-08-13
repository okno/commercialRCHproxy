"""Wazuh-friendly structured logging without payloads by default."""

from __future__ import annotations

import json
import logging
import os
import re
from copy import copy
from datetime import UTC, datetime
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Lock
from typing import Any

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_LOG_QUEUE_CAPACITY = 8192
_RUNTIME_LOCK = Lock()
_RUNTIMES: dict[str, tuple[_NonBlockingQueueHandler, _BoundedQueueListener, tuple[logging.Handler, ...]]] = {}


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return _CONTROL.sub("?", value.replace("\r", "\\r").replace("\n", "\\n"))[:4096]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _clean(str(value))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", "log"),
            "message": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(_clean(payload), ensure_ascii=False, separators=(",", ":"))


class _NonBlockingQueueHandler(QueueHandler):
    """Move all formatting and I/O off the caller without waiting for space."""

    def __init__(self, log_queue: Queue[logging.LogRecord]) -> None:
        super().__init__(log_queue)
        self.dropped_records = 0

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        # QueueHandler.prepare normally formats exceptions/messages on the
        # caller.  This is an in-process thread queue, so a shallow copy is
        # sufficient and keeps even traceback rendering off the relay loop.
        return copy(record)

    def enqueue(self, record: logging.LogRecord) -> None:
        try:
            self.queue.put_nowait(record)
            return
        except Full:
            pass

        # Prefer the newest operational evidence when saturated.  Dropping a
        # queued record is explicit and bounded; logging must never apply
        # backpressure to either full-duplex pump.
        try:
            self.queue.get_nowait()
            self.dropped_records += 1
        except Empty:
            pass
        try:
            self.queue.put_nowait(record)
        except Full:
            self.dropped_records += 1


class _BoundedQueueListener(QueueListener):
    """QueueListener whose shutdown sentinel cannot fail on a full queue."""

    def enqueue_sentinel(self) -> None:
        while True:
            try:
                self.queue.put_nowait(self._sentinel)
                return
            except Full:
                try:
                    self.queue.get_nowait()
                except Empty:
                    continue

    def stop(self) -> None:
        thread = self._thread
        if thread is None:
            return
        self.enqueue_sentinel()
        # A dead or indefinitely slow filesystem must not prevent process
        # teardown forever.  The listener thread is daemonized by stdlib.
        thread.join(timeout=2.0)
        if not thread.is_alive():
            self._thread = None


def shutdown_logging(logger: logging.Logger) -> None:
    """Flush a configured logger when possible, without an unbounded wait."""

    with _RUNTIME_LOCK:
        runtime = _RUNTIMES.pop(logger.name, None)
        logger.handlers.clear()
    if runtime is None:
        return
    _queue_handler, listener, output_handlers = runtime
    listener.stop()
    if listener._thread is None:
        for handler in output_handlers:
            handler.close()


def configure_logging(log_dir: Path, level: str = "INFO", *, component: str = "service") -> logging.Logger:
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", component):
        raise ValueError(f"Invalid log component: {component!r}")
    if log_dir.exists() and log_dir.is_symlink():
        raise RuntimeError(f"Refusing symlink log directory: {log_dir}")
    log_dir.mkdir(mode=0o750, parents=True, exist_ok=True)
    if log_dir.is_symlink() or not log_dir.is_dir():
        raise RuntimeError(f"Unsafe log directory: {log_dir}")
    try:
        log_dir.chmod(0o750)
    except OSError:
        pass
    log_file = log_dir / f"commercialrchproxy-{component}.jsonl"
    if not log_file.exists():
        fd = os.open(log_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        os.close(fd)
    elif log_file.is_symlink():
        raise RuntimeError(f"Refusing symlink log file: {log_file}")

    logger = logging.getLogger(f"commercialrchproxy.{component}")
    shutdown_logging(logger)

    formatter = JsonFormatter()
    file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=7, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)

    log_queue: Queue[logging.LogRecord] = Queue(maxsize=_LOG_QUEUE_CAPACITY)
    queue_handler = _NonBlockingQueueHandler(log_queue)
    listener = _BoundedQueueListener(log_queue, file_handler, stream, respect_handler_level=True)
    listener.start()

    logger.propagate = False
    logger.setLevel(getattr(logging, level))
    logger.addHandler(queue_handler)
    with _RUNTIME_LOCK:
        _RUNTIMES[logger.name] = (queue_handler, listener, (file_handler, stream))
    return logger


def event(logger: logging.Logger, name: str, message: str, **fields: Any) -> None:
    logger.info(message, extra={"event": name, "fields": fields})
