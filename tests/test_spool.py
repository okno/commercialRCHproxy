from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from commercialrchproxy.capture.jobs import CLIENT_TO_RCH, RCH_TO_CLIENT, CapturedJob, CaptureToken
from commercialrchproxy.storage.counter import JobCodeAllocator
from commercialrchproxy.storage.spool import RawSpoolStorage, discover_ready_jobs, epoch_stamp, load_spool_job
from tests.support import make_config, unused_port


def _job(config, *, response: bytes = b"ACK") -> CapturedJob:
    job = CapturedJob(
        session_id="synthetic-session",
        connection_id="synthetic-connection",
        client_ip="192.0.2.10",
        client_port=41000,
        proxy_ip=config.listen_ip,
        proxy_port=config.listen_port,
        printer_ip=config.printer_ip,
        printer_port=config.printer_port,
        max_payload_bytes=config.max_payload_bytes,
        started_at=datetime.fromtimestamp(1_700_000_000.123456789, tz=UTC),
        started_unix_ns=1_700_000_000_123_456_789,
    )
    request_index = job.append(
        CLIENT_TO_RCH,
        b"opaque-request\x00",
        received_unix_ns=1_700_000_000_123_456_789,
        forwarded_unix_ns=1_700_000_000_123_456_999,
    )
    assert request_index == 0
    job.mark_local_write_drain(
        CaptureToken(job.job_id, request_index, CLIENT_TO_RCH, len(b"opaque-request\x00")),
        True,
        drain_unix_ns=1_700_000_000_123_457_111,
    )
    if response:
        response_index = job.append(
            RCH_TO_CLIENT,
            response,
            received_unix_ns=1_700_000_000_223_456_789,
            forwarded_unix_ns=1_700_000_000_223_456_999,
        )
        assert response_index == 1
        job.mark_local_write_drain(
            CaptureToken(job.job_id, response_index, RCH_TO_CLIENT, len(response)),
            True,
            drain_unix_ns=1_700_000_000_223_457_111,
        )
    job.finish("synthetic_connection_close")
    return job


def test_epoch_stamp_has_seconds_and_exactly_nine_nanosecond_digits() -> None:
    assert epoch_stamp(1_700_000_000_123_456_789) == "1700000000.123456789"


def test_atomic_spool_layout_hashes_timeline_and_ready_marker(tmp_path: Path) -> None:
    config = make_config(tmp_path, unused_port(), unused_port())
    result = RawSpoolStorage(config).archive(_job(config), job_code="0042")

    assert result.job_dir.name == "0042"
    assert result.job_dir.parts[-5:-1] == (config.printer_ip, "2023", "11", "14")
    names = {path.name for path in result.job_dir.iterdir()}
    assert "file_1700000000.123456789.raw" in names
    assert "response_1700000000.223456789.raw" in names
    assert "timeline_1700000000.123456789.jsonl" in names
    assert {"manifest.json", ".ready"} <= names
    assert not any(name.endswith(".partial") for name in names)

    manifest = json.loads((result.job_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "commercialrchproxy.capture.v1"
    assert manifest["codice_doc"] == "0042"
    assert manifest["request_size"] == len(b"opaque-request\x00")
    assert manifest["response_size"] == 3
    assert "parser_status" not in manifest
    loaded = load_spool_job(result.job_dir, max_bytes=1024)
    assert loaded.request == b"opaque-request\x00"
    assert loaded.response == b"ACK"
    timeline = [json.loads(line) for line in loaded.timeline_path.read_text(encoding="utf-8").splitlines()]
    assert timeline[0]["connection_id"] == "synthetic-connection"
    assert timeline[0]["received_unix_ns"] == 1_700_000_000_123_456_789
    assert timeline[0]["forwarded_unix_ns"] == 1_700_000_000_123_456_999
    assert timeline[0]["local_write_drain_completed"] is True


def test_empty_response_is_created_and_hashed(tmp_path: Path) -> None:
    config = make_config(tmp_path, unused_port(), unused_port())
    result = RawSpoolStorage(config).archive(_job(config, response=b""), job_code="0043")
    manifest = json.loads((result.job_dir / "manifest.json").read_text(encoding="utf-8"))
    response = result.job_dir / manifest["files"]["response_raw"]
    assert response.is_file()
    assert response.read_bytes() == b""
    assert re.fullmatch(r"response_[0-9]+\.[0-9]{9}\.raw", response.name)
    assert manifest["response_size"] == 0


def test_counter_is_persistent_unique_and_does_not_roll_over_at_four_digits(tmp_path: Path) -> None:
    allocator = JobCodeAllocator(tmp_path, start=9998, width=4)
    assert allocator.allocate("192.0.2.251") == "9998"
    assert allocator.allocate("192.0.2.251") == "9999"
    assert JobCodeAllocator(tmp_path, start=1, width=4).allocate("192.0.2.251") == "10000"


def test_counter_serializes_threads(tmp_path: Path) -> None:
    allocator = JobCodeAllocator(tmp_path, start=1, width=4)
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(lambda _: allocator.allocate("192.0.2.251"), range(20)))
    assert sorted(values) == [f"{value:04d}" for value in range(1, 21)]


def test_parser_discovery_ignores_partial_job(tmp_path: Path) -> None:
    partial = tmp_path / "192.0.2.251" / "2026" / "08" / "12" / ".0001.synthetic.partial"
    partial.mkdir(parents=True)
    (partial / "file_1.000000000.raw.partial").write_bytes(b"partial")
    assert discover_ready_jobs(tmp_path) == []


def test_load_rejects_hash_mismatch(tmp_path: Path) -> None:
    config = make_config(tmp_path, unused_port(), unused_port())
    result = RawSpoolStorage(config).archive(_job(config), job_code="0044")
    manifest = json.loads((result.job_dir / "manifest.json").read_text(encoding="utf-8"))
    request = result.job_dir / manifest["files"]["request_raw"]
    request.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_spool_job(result.job_dir, max_bytes=1024)


def test_live_spool_is_incremental_hidden_and_atomically_published(tmp_path: Path) -> None:
    config = make_config(tmp_path, unused_port(), unused_port())
    storage = RawSpoolStorage(config)
    job = CapturedJob(
        session_id="live-session",
        connection_id="live-connection",
        client_ip="192.0.2.10",
        client_port=41000,
        proxy_ip=config.listen_ip,
        proxy_port=config.listen_port,
        printer_ip=config.printer_ip,
        printer_port=config.printer_port,
        max_payload_bytes=config.max_payload_bytes,
        started_at=datetime.fromtimestamp(1_700_000_000.123456789, tz=UTC),
        started_unix_ns=1_700_000_000_123_456_789,
    )
    live = storage.begin_live(job, job_code="0050")
    chunk_index = job.append(
        CLIENT_TO_RCH,
        b"first-live-block",
        sequence=1,
        session_offset=0,
        received_unix_ns=1_700_000_000_123_456_789,
        forwarded_unix_ns=1_700_000_000_123_456_999,
        retain_payload=False,
    )
    assert chunk_index == 0
    live.append(
        sequence=1,
        direction=CLIENT_TO_RCH,
        data=b"first-live-block",
        timeline_chunk=job.chunks[chunk_index],
    )

    partial_raw = live.partial_dir / "request.raw.partial"
    assert partial_raw.read_bytes() == b"first-live-block"
    assert job.request_bytes == b""
    assert discover_ready_jobs(config.output_dir) == []
    assert not (live.partial_dir / ".ready").exists()

    token = CaptureToken(job.job_id, chunk_index, CLIENT_TO_RCH, 16, 1)
    job.mark_local_write_drain(token, True, drain_unix_ns=1_700_000_000_123_457_111)
    live.mark_local_write_drain(
        sequence=1,
        completed=True,
        drain_unix_ns=1_700_000_000_123_457_111,
        error=None,
    )
    job.finish("synthetic_connection_close")
    result = live.finalize(job)

    assert discover_ready_jobs(config.output_dir) == [result.job_dir]
    loaded = load_spool_job(result.job_dir, max_bytes=1024)
    assert loaded.request == b"first-live-block"
    assert loaded.response == b""
    timeline = json.loads(loaded.timeline_path.read_text(encoding="utf-8"))
    assert timeline["byte_count"] == 16
    assert timeline["sha256"] == hashlib.sha256(b"first-live-block").hexdigest()
    assert timeline["local_write_drain_completed"] is True


def test_live_spool_crash_close_preserves_unpublished_partial(tmp_path: Path) -> None:
    config = make_config(tmp_path, unused_port(), unused_port())
    job = CapturedJob(
        session_id="crash-session",
        connection_id="crash-connection",
        client_ip="192.0.2.10",
        client_port=41000,
        proxy_ip=config.listen_ip,
        proxy_port=config.listen_port,
        printer_ip=config.printer_ip,
        printer_port=config.printer_port,
        max_payload_bytes=config.max_payload_bytes,
    )
    live = RawSpoolStorage(config).begin_live(job, job_code="0051")
    chunk_index = job.append(CLIENT_TO_RCH, b"survives-process-crash", sequence=1, retain_payload=False)
    assert chunk_index == 0
    live.append(
        sequence=1,
        direction=CLIENT_TO_RCH,
        data=b"survives-process-crash",
        timeline_chunk=job.chunks[chunk_index],
    )
    live.close_incomplete()

    assert live.partial_dir.is_dir()
    assert (live.partial_dir / "request.raw.partial").read_bytes() == b"survives-process-crash"
    assert not (live.partial_dir / ".ready").exists()
    assert discover_ready_jobs(config.output_dir) == []


def test_automatic_code_skips_existing_hidden_staging_code(tmp_path: Path) -> None:
    config = make_config(tmp_path, unused_port(), unused_port())
    storage = RawSpoolStorage(config)
    explicit = storage.begin_live(_job(config), job_code="0001")
    automatic = storage.begin_live(_job(config))
    try:
        assert explicit.code == "0001"
        assert automatic.code == "0002"
        assert explicit.partial_dir.is_dir()
        assert automatic.partial_dir.is_dir()
    finally:
        explicit.close_incomplete()
        automatic.close_incomplete()


def test_load_rejects_ready_marker_manifest_mismatch(tmp_path: Path) -> None:
    config = make_config(tmp_path, unused_port(), unused_port())
    result = RawSpoolStorage(config).archive(_job(config), job_code="0045")
    marker = json.loads((result.job_dir / ".ready").read_text(encoding="utf-8"))
    marker["manifest_sha256"] = "0" * 64
    (result.job_dir / ".ready").write_text(json.dumps(marker), encoding="utf-8")
    with pytest.raises(ValueError, match="does not authenticate"):
        load_spool_job(result.job_dir, max_bytes=1024)
