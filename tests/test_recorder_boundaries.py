from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest

from commercialrchproxy.capture.jobs import CLIENT_TO_RCH, RCH_TO_CLIENT, CapturedJob
from commercialrchproxy.capture.recorder import JobCaptureManager
from commercialrchproxy.metrics import Metrics
from commercialrchproxy.rch.framing import build_frame
from commercialrchproxy.storage.files import ArchiveResult
from tests.support import make_config, null_logger, unused_port


class _RecordingStorage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.jobs: list[CapturedJob] = []
        self._lock = threading.Lock()

    def archive(self, job: CapturedJob) -> ArchiveResult:
        with self._lock:
            self.jobs.append(job)
        return ArchiveResult(self.root / f"{job.job_id}.json", "complete", {})

    def snapshot(self) -> list[CapturedJob]:
        with self._lock:
            return list(self.jobs)


def _manager(tmp_path: Path, *, response_timeout_sec: float = 0.20) -> tuple[JobCaptureManager, _RecordingStorage]:
    config = make_config(
        tmp_path,
        unused_port(),
        unused_port(),
        response_timeout_sec=response_timeout_sec,
        job_idle_timeout_ms=50,
    )
    storage = _RecordingStorage(tmp_path)
    manager = JobCaptureManager(
        config,
        storage,  # type: ignore[arg-type]
        null_logger(),
        Metrics(),
        session_id="observed-session",
        client_ip="127.0.0.1",
        client_port=12345,
    )
    return manager, storage


async def _record_and_drain(manager: JobCaptureManager, direction: str, data: bytes) -> None:
    token = await manager.record(direction, data)
    if token is not None:
        await manager.mark_local_write_drain(token, completed=True)


async def _wait_for_jobs(storage: _RecordingStorage, count: int, timeout: float = 0.6) -> list[CapturedJob]:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        jobs = storage.snapshot()
        if len(jobs) >= count:
            return jobs
        await asyncio.sleep(0.005)
    return storage.snapshot()


@pytest.mark.asyncio
async def test_ack_does_not_split_request_from_observed_delayed_response(tmp_path: Path) -> None:
    manager, storage = _manager(tmp_path)
    # Request trailer sequence 7 correlates with response trailer sequence 5.
    request = build_frame("=T1/$137", sequence="7")
    response = build_frame("ON00000000", address="01", frame_class="N", sequence="5")

    # Exercise incremental framing in both directions.  The scaled 80 ms gap
    # exceeds the 50 ms idle fallback and represents the observed 1.372 s gap.
    await _record_and_drain(manager, CLIENT_TO_RCH, request[:6])
    await _record_and_drain(manager, CLIENT_TO_RCH, request[6:])
    await _record_and_drain(manager, RCH_TO_CLIENT, b"\x06")
    await asyncio.sleep(0.08)
    assert storage.snapshot() == []

    await _record_and_drain(manager, RCH_TO_CLIENT, response[:9])
    await _record_and_drain(manager, RCH_TO_CLIENT, response[9:])
    jobs = await _wait_for_jobs(storage, 1)
    await manager.wait_for_persistence()

    assert len(jobs) == 1
    assert jobs[0].request_bytes == request
    assert jobs[0].response_bytes == b"\x06" + response
    assert jobs[0].boundary_source == "fallback_inactivity"
    assert [chunk.sequence for chunk in jobs[0].chunks] == [1, 2, 3, 4, 5]
    assert [chunk.session_offset for chunk in jobs[0].chunks] == [0, 6, 0, 1, 10]


@pytest.mark.asyncio
async def test_response_after_bounded_fallback_is_retained_as_explicit_orphan_segment(tmp_path: Path) -> None:
    manager, storage = _manager(tmp_path, response_timeout_sec=0.05)
    request = build_frame("=T1/$137", sequence="7")
    late_response = build_frame("ON00000000", address="01", frame_class="N", sequence="5")

    await _record_and_drain(manager, CLIENT_TO_RCH, request)
    await _record_and_drain(manager, RCH_TO_CLIENT, b"\x06")
    jobs = await _wait_for_jobs(storage, 1)
    assert len(jobs) == 1
    assert jobs[0].request_bytes == request
    assert jobs[0].response_bytes == b"\x06"

    # Once the response window has elapsed, the immutable incomplete segment
    # cannot be extended.  Preserve the bytes in an explicitly classified
    # orphan segment rather than silently discarding them.
    await _record_and_drain(manager, RCH_TO_CLIENT, b"\x06")
    await asyncio.sleep(0.07)
    assert len(storage.snapshot()) == 1
    await _record_and_drain(manager, RCH_TO_CLIENT, late_response)
    jobs = await _wait_for_jobs(storage, 2)
    await manager.finalize()
    await manager.wait_for_persistence()
    assert len(jobs) == 2
    assert jobs[1].request_bytes == b""
    assert jobs[1].response_bytes == b"\x06" + late_response
    assert jobs[1].boundary_source == "orphan_late_response"


@pytest.mark.asyncio
async def test_response_timeout_plus_idle_remains_fallback_for_incomplete_request(tmp_path: Path) -> None:
    manager, storage = _manager(tmp_path, response_timeout_sec=0.05)
    request = build_frame("=T1/$137", sequence="7")

    await _record_and_drain(manager, CLIENT_TO_RCH, request)
    await _record_and_drain(manager, RCH_TO_CLIENT, b"\x06")
    await asyncio.sleep(0.06)
    assert storage.snapshot() == []

    jobs = await _wait_for_jobs(storage, 1)
    await manager.wait_for_persistence()
    assert len(jobs) == 1
    assert jobs[0].request_bytes == request
    assert jobs[0].response_bytes == b"\x06"
    assert jobs[0].boundary_source == "fallback_inactivity"
    assert jobs[0].boundary_confidence == 0.20


@pytest.mark.parametrize(
    ("open_data", "body_or_close_data", "close_data"),
    [
        ("=K", "=T1/$137", "<</?7"),
        ("=o", "=o", None),
    ],
)
@pytest.mark.asyncio
async def test_observed_document_candidate_holds_segment_until_close(
    tmp_path: Path,
    open_data: str,
    body_or_close_data: str,
    close_data: str | None,
) -> None:
    manager, storage = _manager(tmp_path)
    open_frame = build_frame(open_data, sequence="0")
    body_or_close_frame = build_frame(body_or_close_data, sequence="1")
    open_response = build_frame("ON00000000", address="01", frame_class="N", sequence="8")
    body_or_close_response = build_frame("ON00000000", address="01", frame_class="N", sequence="9")

    await _record_and_drain(manager, CLIENT_TO_RCH, open_frame)
    await _record_and_drain(manager, RCH_TO_CLIENT, b"\x06" + open_response)
    await asyncio.sleep(0.08)
    assert storage.snapshot() == []

    await _record_and_drain(manager, CLIENT_TO_RCH, body_or_close_frame)
    await _record_and_drain(manager, RCH_TO_CLIENT, b"\x06" + body_or_close_response)
    if close_data is not None:
        # A commercial total is not the observed end of the printed copy.
        await asyncio.sleep(0.08)
        assert storage.snapshot() == []
        close_frame = build_frame(close_data, sequence="2")
        close_response = build_frame("ON00000000", address="01", frame_class="N", sequence="0")
        await _record_and_drain(manager, CLIENT_TO_RCH, close_frame)
        await _record_and_drain(manager, RCH_TO_CLIENT, b"\x06" + close_response)
    else:
        close_frame = b""
    jobs = await _wait_for_jobs(storage, 1)
    await manager.wait_for_persistence()
    assert len(jobs) == 1
    assert jobs[0].request_bytes == open_frame + body_or_close_frame + close_frame


@pytest.mark.asyncio
async def test_response_correlation_hints_are_bounded(tmp_path: Path) -> None:
    manager, _ = _manager(tmp_path)
    frame = build_frame("=C1", sequence="0")

    for _ in range(4200):
        await manager.record(CLIENT_TO_RCH, frame)

    assert manager._pending_responses.maxlen == 4096  # noqa: SLF001 - regression invariant
    assert len(manager._pending_responses) == 4096  # noqa: SLF001 - regression invariant
    await manager.finalize()


@pytest.mark.asyncio
async def test_bad_bcc_cannot_close_document_boundary_hint(tmp_path: Path) -> None:
    manager, storage = _manager(tmp_path)
    open_frame = build_frame("=K", sequence="0")
    open_response = build_frame("ON00000000", address="01", frame_class="N", sequence="8")
    bad_close = bytearray(build_frame("<</?7", sequence="1"))
    bad_close[-2] = ord("0") if bad_close[-2] != ord("0") else ord("1")

    await _record_and_drain(manager, CLIENT_TO_RCH, open_frame)
    await _record_and_drain(manager, RCH_TO_CLIENT, b"\x06" + open_response)
    await _record_and_drain(manager, CLIENT_TO_RCH, bytes(bad_close))
    await asyncio.sleep(0.08)
    assert storage.snapshot() == []

    valid_close = build_frame("<</?7", sequence="2")
    valid_response = build_frame("ON00000000", address="01", frame_class="N", sequence="0")
    await _record_and_drain(manager, CLIENT_TO_RCH, valid_close)
    await _record_and_drain(manager, RCH_TO_CLIENT, b"\x06" + valid_response)
    jobs = await _wait_for_jobs(storage, 1)
    assert len(jobs) == 1


@pytest.mark.asyncio
async def test_bad_bcc_response_cannot_consume_pending_hint(tmp_path: Path) -> None:
    manager, storage = _manager(tmp_path)
    request = build_frame("=C1", sequence="7")
    bad_response = bytearray(build_frame("ON00000000", address="01", frame_class="N", sequence="5"))
    bad_response[-2] = ord("0") if bad_response[-2] != ord("0") else ord("1")

    await _record_and_drain(manager, CLIENT_TO_RCH, request)
    await _record_and_drain(manager, RCH_TO_CLIENT, b"\x06" + bytes(bad_response))
    await asyncio.sleep(0.08)
    assert storage.snapshot() == []

    valid_response = build_frame("ON00000000", address="01", frame_class="N", sequence="5")
    await _record_and_drain(manager, RCH_TO_CLIENT, valid_response)
    jobs = await _wait_for_jobs(storage, 1)
    assert len(jobs) == 1
