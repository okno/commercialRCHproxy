from __future__ import annotations

import logging
import threading
from pathlib import Path
from queue import Queue
from time import monotonic

from commercialrchproxy.logging import structured


class _BlockedHandler(logging.Handler):
    def __init__(self, started: threading.Event, release: threading.Event) -> None:
        super().__init__()
        self.started = started
        self.release = release

    def emit(self, _record: logging.LogRecord) -> None:
        self.started.set()
        self.release.wait(timeout=2.0)


def test_slow_log_sink_never_blocks_relay_caller(monkeypatch: object, tmp_path: Path) -> None:
    started = threading.Event()
    release = threading.Event()
    blocked = _BlockedHandler(started, release)
    monkeypatch.setattr(structured, "RotatingFileHandler", lambda *_args, **_kwargs: blocked)  # type: ignore[attr-defined]

    logger = structured.configure_logging(tmp_path, component="dumper-test")
    try:
        structured.event(logger, "first", "occupy the logging worker")
        assert started.wait(timeout=1.0)

        before = monotonic()
        structured.event(logger, "relay", "must be queued without filesystem backpressure")
        elapsed = monotonic() - before

        assert elapsed < 0.05
        assert isinstance(logger.handlers[0], structured._NonBlockingQueueHandler)
    finally:
        release.set()
        structured.shutdown_logging(logger)


def test_full_log_queue_drops_oldest_without_waiting() -> None:
    queue: Queue[logging.LogRecord] = Queue(maxsize=1)
    handler = structured._NonBlockingQueueHandler(queue)
    first = logging.LogRecord("test", logging.INFO, __file__, 1, "first", (), None)
    second = logging.LogRecord("test", logging.CRITICAL, __file__, 2, "second", (), None)

    before = monotonic()
    handler.enqueue(first)
    handler.enqueue(second)

    assert monotonic() - before < 0.05
    assert handler.dropped_records == 1
    assert queue.get_nowait().getMessage() == "second"
