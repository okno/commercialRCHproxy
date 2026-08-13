from __future__ import annotations

import asyncio
import inspect
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from commercialrchproxy.capture.jobs import CLIENT_TO_RCH, RCH_TO_CLIENT
from commercialrchproxy.capture.recorder import JobCaptureManager
from commercialrchproxy.metrics import Metrics
from commercialrchproxy.storage.spool import RawSpoolStorage, discover_ready_jobs, load_spool_job
from tests.support import make_config, null_logger, unused_port


class _RecordingStorage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.jobs = []

    def archive(self, job):
        self.jobs.append(job)
        return SimpleNamespace(
            code="0001",
            status="ready",
            manifest_path=self.root / "manifest.json",
        )


class _FailingStorage(_RecordingStorage):
    def archive(self, job):
        raise OSError("synthetic storage outage")


class _FailingLiveCapture:
    def __init__(self) -> None:
        self.closed_incomplete = False

    def append(self, **_kwargs) -> None:
        raise OSError("synthetic live disk outage")

    def close_incomplete(self, *_args, **_kwargs) -> None:
        self.closed_incomplete = True


class _FailingLiveStorage:
    def __init__(self) -> None:
        self.live = _FailingLiveCapture()

    def begin_live(self, _job):
        return self.live


def _manager(tmp_path: Path, *, policy: str = "continue", storage=None):
    config = make_config(
        tmp_path,
        unused_port(),
        unused_port(),
        response_timeout_sec=0.05,
        job_idle_timeout_ms=50,
        storage_failure_policy=policy,
    )
    selected = storage or _RecordingStorage(tmp_path)
    manager = JobCaptureManager(
        config,
        selected,
        null_logger(),
        Metrics(),
        session_id="synthetic-session",
        connection_id="synthetic-connection",
        client_ip="127.0.0.1",
        client_port=12345,
    )
    return manager, selected


@pytest.mark.asyncio
async def test_idle_time_never_becomes_a_document_or_capture_boundary(tmp_path: Path) -> None:
    manager, storage = _manager(tmp_path)
    await manager.record(CLIENT_TO_RCH, b"first")
    await asyncio.sleep(0.15)
    await manager.record(CLIENT_TO_RCH, b"second")
    assert storage.jobs == []
    await manager.finalize()
    await manager.wait_for_persistence()
    assert len(storage.jobs) == 1
    assert storage.jobs[0].request_bytes == b"firstsecond"
    assert storage.jobs[0].boundary_source == "connection_lifecycle"


@pytest.mark.asyncio
async def test_late_reverse_bytes_remain_in_same_transport_capture(tmp_path: Path) -> None:
    manager, storage = _manager(tmp_path)
    await manager.record(CLIENT_TO_RCH, b"request")
    await asyncio.sleep(0.15)
    await manager.record(RCH_TO_CLIENT, b"delayed-response")
    await manager.finalize()
    await manager.wait_for_persistence()
    assert len(storage.jobs) == 1
    assert storage.jobs[0].request_bytes == b"request"
    assert storage.jobs[0].response_bytes == b"delayed-response"


@pytest.mark.asyncio
async def test_parser_or_protocol_logic_is_not_imported_by_dumper_recorder(tmp_path: Path) -> None:
    manager, storage = _manager(tmp_path)
    source = inspect.getsource(type(manager))
    assert "RCHStreamFramer" not in source
    assert "analyze_copies" not in source
    await manager.record(CLIENT_TO_RCH, b"\x02untrusted\x03")
    await manager.finalize()
    await manager.wait_for_persistence()
    assert storage.jobs[0].request_bytes == b"\x02untrusted\x03"


@pytest.mark.asyncio
async def test_default_storage_failure_policy_does_not_change_relay_outcome(tmp_path: Path) -> None:
    storage = _FailingStorage(tmp_path)
    manager, _ = _manager(tmp_path, policy="continue", storage=storage)
    await manager.record(CLIENT_TO_RCH, b"opaque")
    await manager.finalize()
    await manager.wait_for_persistence()


@pytest.mark.asyncio
async def test_abort_storage_policy_reports_failure_after_transport_capture(tmp_path: Path) -> None:
    storage = _FailingStorage(tmp_path)
    manager, _ = _manager(tmp_path, policy="abort", storage=storage)
    await manager.record(CLIENT_TO_RCH, b"opaque")
    await manager.finalize()
    with pytest.raises(RuntimeError, match="spool publication failed"):
        await manager.wait_for_persistence()


@pytest.mark.asyncio
async def test_real_recorder_streams_to_hidden_partial_without_retaining_payload(tmp_path: Path) -> None:
    config = make_config(tmp_path, unused_port(), unused_port())
    manager = JobCaptureManager(
        config,
        RawSpoolStorage(config),
        null_logger(),
        Metrics(),
        session_id="live-session",
        connection_id="live-connection",
        client_ip="127.0.0.1",
        client_port=12345,
    )
    payload = b"opaque-live-payload" * 1024
    token = await manager.record(CLIENT_TO_RCH, payload)
    assert token is not None

    partials: list[Path] = []
    for _ in range(200):
        partials = list(config.output_dir.rglob("request.raw.partial"))
        if partials and partials[0].stat().st_size == len(payload):
            break
        await asyncio.sleep(0.005)
    assert partials[0].read_bytes() == payload
    assert manager._active is not None
    assert manager._active.request_bytes == b""
    assert manager._active.response_bytes == b""
    assert manager._stream_queue is not None
    assert manager._stream_queue.maxsize * config.buffer_size <= 8 * 1024 * 1024
    assert discover_ready_jobs(config.output_dir) == []

    await manager.mark_local_write_drain(token, True)
    await manager.finalize()
    await manager.wait_for_persistence()
    ready = discover_ready_jobs(config.output_dir)
    assert len(ready) == 1
    loaded = load_spool_job(ready[0], max_bytes=len(payload) + 1)
    assert loaded.request == payload


async def _wait_for_storage_error(manager: JobCaptureManager) -> None:
    for _ in range(200):
        if manager._persist_errors:
            return
        await asyncio.sleep(0.005)
    raise AssertionError("live storage failure was not observed")


@pytest.mark.asyncio
async def test_live_storage_failure_continue_preserves_relay_policy_and_releases_queue(tmp_path: Path) -> None:
    storage = _FailingLiveStorage()
    manager, _ = _manager(tmp_path, policy="continue", storage=storage)
    token = await manager.record(CLIENT_TO_RCH, b"first-forwarded-block")
    assert token is not None
    await _wait_for_storage_error(manager)
    await manager.mark_local_write_drain(token, True)
    assert await manager.record(CLIENT_TO_RCH, b"still-forwarded-after-storage-failure") is not None
    await manager.finalize()
    await manager.wait_for_persistence()
    assert storage.live.closed_incomplete is True


@pytest.mark.asyncio
async def test_live_storage_failure_abort_surfaces_before_next_relay_iteration(tmp_path: Path) -> None:
    storage = _FailingLiveStorage()
    manager, _ = _manager(tmp_path, policy="abort", storage=storage)
    token = await manager.record(CLIENT_TO_RCH, b"first-forwarded-block")
    assert token is not None
    await _wait_for_storage_error(manager)
    with pytest.raises(RuntimeError, match="live spool failed"):
        await manager.mark_local_write_drain(token, True)
    await manager.finalize()
    with pytest.raises(RuntimeError, match="spool publication failed"):
        await manager.wait_for_persistence()


@pytest.mark.asyncio
async def test_continue_hung_begin_live_never_blocks_relay_or_finalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(
        tmp_path,
        unused_port(),
        unused_port(),
        buffer_size=8 * 1024 * 1024,
        storage_failure_policy="continue",
    )
    storage = RawSpoolStorage(config)
    original_begin_live = storage.begin_live
    begin_entered = threading.Event()
    begin_release = threading.Event()

    def blocked_begin_live(job):
        live = original_begin_live(job)
        begin_entered.set()
        if not begin_release.wait(2.0):
            raise TimeoutError("synthetic begin_live remained blocked")
        return live

    monkeypatch.setattr(storage, "begin_live", blocked_begin_live)
    manager = JobCaptureManager(
        config,
        storage,
        null_logger(),
        Metrics(),
        session_id="hung-begin-session",
        connection_id="hung-begin-connection",
        client_ip="127.0.0.1",
        client_port=12345,
    )
    try:
        assert await asyncio.wait_for(manager.record(CLIENT_TO_RCH, b"first"), 0.25) is not None
        assert await asyncio.wait_for(asyncio.to_thread(begin_entered.wait, 1.0), 1.25)
        assert await asyncio.wait_for(manager.record(CLIENT_TO_RCH, b"dropped"), 0.25) is not None
        job = manager._active
        assert job is not None
        assert job.capture_complete is False
        assert "queue capacity exhausted" in (job.capture_error or "")
        await asyncio.wait_for(manager.finalize(), 0.25)

        partials = list(config.output_dir.rglob("capture-meta.json.partial"))
        assert len(partials) == 1
        assert discover_ready_jobs(config.output_dir) == []
    finally:
        begin_release.set()
    await manager.wait_for_persistence()

    partial = partials[0].parent
    assert (partial / "request.raw.partial").read_bytes() == b"first"
    metadata = json.loads((partial / "capture-meta.json.partial").read_text(encoding="utf-8"))
    assert metadata["status"] == "live_capture_incomplete"
    assert metadata["raw_complete"] is False
    assert metadata["partial_sizes"]["request_raw"] == len(b"first")
    assert not (partial / ".ready").exists()


@pytest.mark.asyncio
async def test_continue_hung_append_degrades_nonblocking_and_preserves_written_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(
        tmp_path,
        unused_port(),
        unused_port(),
        buffer_size=8 * 1024 * 1024,
        storage_failure_policy="continue",
    )
    storage = RawSpoolStorage(config)
    original_begin_live = storage.begin_live
    append_entered = threading.Event()
    append_release = threading.Event()

    def begin_with_blocked_append(job):
        live = original_begin_live(job)
        original_append = live.append

        def blocked_append(**kwargs):
            original_append(**kwargs)
            if kwargs["sequence"] == 1:
                append_entered.set()
                if not append_release.wait(2.0):
                    raise TimeoutError("synthetic append remained blocked")

        live.append = blocked_append  # type: ignore[method-assign]
        return live

    monkeypatch.setattr(storage, "begin_live", begin_with_blocked_append)
    manager = JobCaptureManager(
        config,
        storage,
        null_logger(),
        Metrics(),
        session_id="hung-append-session",
        connection_id="hung-append-connection",
        client_ip="127.0.0.1",
        client_port=12345,
    )
    try:
        assert await asyncio.wait_for(manager.record(CLIENT_TO_RCH, b"first"), 0.25) is not None
        assert await asyncio.wait_for(asyncio.to_thread(append_entered.wait, 1.0), 1.25)
        assert await asyncio.wait_for(manager.record(CLIENT_TO_RCH, b"second"), 0.25) is not None
        assert await asyncio.wait_for(manager.record(CLIENT_TO_RCH, b"dropped"), 0.25) is not None
        job = manager._active
        assert job is not None
        assert job.capture_complete is False
        await asyncio.wait_for(manager.finalize(), 0.25)

        partial_raw = next(config.output_dir.rglob("request.raw.partial"))
        assert partial_raw.read_bytes() == b"first"
        assert discover_ready_jobs(config.output_dir) == []
    finally:
        append_release.set()
    await manager.wait_for_persistence()

    assert partial_raw.read_bytes() == b"firstsecond"
    metadata = json.loads((partial_raw.parent / "capture-meta.json.partial").read_text(encoding="utf-8"))
    assert metadata["status"] == "live_capture_incomplete"
    assert metadata["raw_complete"] is False
    assert metadata["partial_sizes"]["request_raw"] == len(b"firstsecond")
    assert "queue capacity exhausted" in metadata["incomplete_reason"]
    assert discover_ready_jobs(config.output_dir) == []
