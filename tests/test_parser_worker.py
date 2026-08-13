from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pypdf import PdfReader

from commercialrchproxy.capture.jobs import CLIENT_TO_RCH, RCH_TO_CLIENT, CapturedJob
from commercialrchproxy.config import Config
from commercialrchproxy.parser import worker as worker_module
from commercialrchproxy.parser.watcher import SpoolWatcher
from commercialrchproxy.parser.worker import ParserJobError, _load_request_timeline, process_job, run_once
from commercialrchproxy.rch.framing import build_frame
from commercialrchproxy.storage.spool import RawSpoolStorage
from tests.support import make_config, unused_port

FIXTURES = Path(__file__).parent / "fixtures"


def _hex_fixture(name: str) -> bytes:
    return bytes.fromhex((FIXTURES / name).read_text(encoding="ascii"))


def _unix_ns(value: datetime) -> int:
    return int(value.timestamp()) * 1_000_000_000 + value.microsecond * 1000


def _archive(
    config: Config,
    *,
    code: str,
    fixture: str = "management",
    copies: int = 1,
    received_at: datetime = datetime(2042, 2, 3, 4, 5, 6, 789000, tzinfo=UTC),
) -> Path:
    job = CapturedJob(
        session_id=f"synthetic-{code}",
        client_ip="127.0.0.1",
        client_port=1234,
        proxy_ip=config.listen_ip,
        proxy_port=config.listen_port,
        printer_ip=config.printer_ip,
        printer_port=config.printer_port,
        max_payload_bytes=config.max_payload_bytes,
    )
    request = _hex_fixture(f"rch_synthetic_{fixture}.request.hex") * copies
    response = _hex_fixture(f"rch_synthetic_{fixture}.response.hex") * copies
    stamp = _unix_ns(received_at)
    job.append(CLIENT_TO_RCH, request, received_unix_ns=stamp, forwarded_unix_ns=stamp + 1000)
    job.append(RCH_TO_CLIENT, response, received_unix_ns=stamp + 2000, forwarded_unix_ns=stamp + 3000)
    job.finish()
    return RawSpoolStorage(config).archive(job, job_code=code).job_dir


def _config(tmp_path: Path, **overrides: object) -> Config:
    values: dict[str, object] = {
        "timezone": "Europe/Rome",
        "save_clean_txt": True,
        "save_pdf": True,
        "parser_workers": 1,
    }
    values.update(overrides)
    return make_config(
        tmp_path,
        printer_port=unused_port(),
        listen_port=unused_port(),
        **values,
    )


def test_timeline_reader_counts_both_directions_and_checks_manifest_count(tmp_path: Path) -> None:
    timeline = tmp_path / "timeline.jsonl"
    request_event = {
        "direction": "CLIENT -> RCH",
        "job_offset": 0,
        "byte_count": 3,
        "received_unix_ns": 2_275_318_706_789_000_000,
    }
    response_event = {
        "direction": "RCH -> CLIENT",
        "job_offset": 0,
        "byte_count": 1,
        "received_unix_ns": 2_275_318_706_790_000_000,
    }
    timeline.write_text(
        "\n".join(json.dumps(event) for event in (request_event, response_event)) + "\n",
        encoding="utf-8",
    )

    events = _load_request_timeline(timeline, max_events=2, expected_event_count=2)
    assert len(events) == 1

    with pytest.raises(ParserJobError, match="timeline event count mismatch: manifest=3, file=2"):
        _load_request_timeline(timeline, max_events=3, expected_event_count=3)


def test_timeline_reader_bounds_event_count_and_physical_line_size(tmp_path: Path) -> None:
    timeline = tmp_path / "timeline.jsonl"
    event = {
        "direction": "CLIENT -> RCH",
        "job_offset": 0,
        "byte_count": 1,
        "received_unix_ns": 2_275_318_706_789_000_000,
    }
    encoded = (json.dumps(event) + "\n").encode()
    timeline.write_bytes(encoded + encoded)

    with pytest.raises(ParserJobError, match="timeline event limit 1 exceeded"):
        _load_request_timeline(timeline, max_events=1, expected_event_count=1)

    timeline.write_bytes(b'{"direction":"' + (b"X" * (64 * 1024)))
    with pytest.raises(ParserJobError, match="timeline line 1 exceeds 65536 bytes"):
        _load_request_timeline(timeline, max_events=1, expected_event_count=1)


def test_worker_validates_and_publishes_human_named_document_pair(tmp_path: Path) -> None:
    config = _config(tmp_path)
    job_dir = _archive(config, code="7315")
    immutable = {
        path.name: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in job_dir.iterdir()
        if path.name in {"manifest.json", ".ready"} or path.suffix in {".raw", ".jsonl"}
    }

    result = process_job(config, job_dir)

    assert result.status == "parsed"
    assert result.document_count == 1
    pharsed = job_dir / "PHARSED"
    assert {path.name for path in pharsed.iterdir()} == {
        "7315_G_05.05.06.789.txt",
        "7315_G_05.05.06.789.pdf",
        "parsed.json",
    }
    expected = (FIXTURES / "rch_synthetic_management.expected.txt").read_text(encoding="utf-8")
    rendered = (pharsed / "7315_G_05.05.06.789.txt").read_text(encoding="utf-8")
    assert rendered.endswith(expected)
    assert "TIPO: G\nSOTTOTIPO: DOCUMENTO GESTIONALE GENERICO\n" in rendered
    assert "STATO: COMPLETO\n" in rendered
    assert "METADATI PARSER" in rendered
    assert "(NON PARTE DEL DOCUMENTO)" in rendered
    pdf = PdfReader(str(pharsed / "7315_G_05.05.06.789.pdf"))
    assert len(pdf.pages) == 1
    assert "TIPO: G" in (pdf.pages[0].extract_text() or "")
    metadata = json.loads((pharsed / "parsed.json").read_text(encoding="utf-8"))
    assert metadata["schema"] == "commercialrchproxy.pharsed.v1"
    assert metadata["documents"][0]["type"] == "G"
    assert metadata["documents"][0]["subtype"] == "DOCUMENTO GESTIONALE GENERICO"
    assert metadata["documents"][0]["subtype_evidence"] == "CONSERVATIVE_DEFAULT"
    assert metadata["documents"][0]["capture_time_local"] == "2042-02-03T05:05:06.789+0100"
    assert all(not name.startswith("178") for name in (path.name for path in pharsed.iterdir()))
    assert (job_dir / ".parsed").is_file()
    assert not (job_dir / ".processing").exists()
    assert immutable == {
        path.name: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in job_dir.iterdir()
        if path.name in immutable
    }


def test_worker_is_idempotent_and_multiple_documents_get_human_suffix(tmp_path: Path) -> None:
    config = _config(tmp_path)
    job_dir = _archive(config, code="7316", copies=2)

    first = process_job(config, job_dir)
    files_before = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in (job_dir / "PHARSED").iterdir()
    }
    second = process_job(config, job_dir)

    assert first.document_count == 2
    assert second.status == "already_parsed"
    assert files_before == {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in (job_dir / "PHARSED").iterdir()
    }
    assert (job_dir / "PHARSED" / "7316_G_05.05.06.789.txt").is_file()
    assert (job_dir / "PHARSED" / "7316_G_05.05.06.789_02.txt").is_file()
    metadata = json.loads((job_dir / "PHARSED" / "parsed.json").read_text(encoding="utf-8"))
    assert [document["ordinal"] for document in metadata["documents"]] == [1, 2]


def test_commercial_document_maps_to_c_without_inventing_receipt_fields(tmp_path: Path) -> None:
    config = _config(tmp_path)
    job_dir = _archive(config, code="7317", fixture="commercial")

    assert process_job(config, job_dir).status == "parsed"

    output = job_dir / "PHARSED" / "7317_C_05.05.06.789.txt"
    expected = (FIXTURES / "rch_synthetic_commercial.expected.txt").read_text(encoding="utf-8")
    rendered = output.read_text(encoding="utf-8")
    assert rendered.endswith(expected)
    metadata = json.loads((job_dir / "PHARSED" / "parsed.json").read_text(encoding="utf-8"))
    document = metadata["documents"][0]
    assert document["type"] == "C"
    assert document["subtype"] == "DOCUMENTO COMMERCIALE"
    assert "TIPO: C\nSOTTOTIPO: DOCUMENTO COMMERCIALE\n" in rendered
    assert document["semantic"]["parsed"]["metadata"]["parser_subtype"] == "DOCUMENTO COMMERCIALE"


def test_incomplete_document_is_explicit_in_non_document_metadata(tmp_path: Path) -> None:
    config = _config(tmp_path)
    job_dir = _archive(config, code="0412", fixture="partial_transaction")

    assert process_job(config, job_dir).status == "parsed"

    output = job_dir / "PHARSED" / "0412_C_05.05.06.789.txt"
    rendered = output.read_text(encoding="utf-8")
    metadata_header, document_body = rendered.split("=== DOCUMENTO RICOSTRUITO ===", 1)
    assert "STATO: INCOMPLETO" in metadata_header
    assert "STATO: INCOMPLETO" not in document_body
    pdf = PdfReader(str(output.with_suffix(".pdf")))
    assert "STATO: INCOMPLETO" in (pdf.pages[0].extract_text() or "")
    metadata = json.loads((job_dir / "PHARSED" / "parsed.json").read_text(encoding="utf-8"))
    document = metadata["documents"][0]
    assert document["complete"] is False
    assert document["semantic"]["parsed"]["metadata"]["parser_complete"] is False
    assert document["semantic"]["parsed"]["metadata"]["parser_completeness"] == "INCOMPLETO"


def test_hash_mismatch_retries_then_quarantines_without_rewriting_capture(tmp_path: Path) -> None:
    config = _config(tmp_path, parser_retry_count=1)
    job_dir = _archive(config, code="7318")
    manifest = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
    raw_path = job_dir / manifest["files"]["request_raw"]
    raw_path.write_bytes(raw_path.read_bytes() + b"corruption")
    corrupted = raw_path.read_bytes()

    first = process_job(config, job_dir)
    second = process_job(config, job_dir)
    third = process_job(config, job_dir)

    assert first.status == "retry_pending"
    assert second.status == "parse_failed"
    assert third.status == "parse_failed"
    failure = json.loads((job_dir / ".parse_failed").read_text(encoding="utf-8"))
    assert failure["attempts"] == 2
    assert "SHA-256 mismatch" in failure["last_error"]
    assert raw_path.read_bytes() == corrupted
    assert not (job_dir / ".parsed").exists()
    assert not (job_dir / ".processing").exists()


def test_management_subtype_requires_and_preserves_literal_marker(tmp_path: Path) -> None:
    config = _config(tmp_path)
    received_at = datetime(2042, 2, 3, 4, 8, 9, 12000, tzinfo=UTC)
    request = (
        build_frame("=o", sequence="0")
        + build_frame('="/(PRECONTO)', sequence="1")
        + build_frame('="/(VOCE SINTETICA 0,00 X)', sequence="2")
        + build_frame("=o", sequence="3")
    )
    stamp = _unix_ns(received_at)
    job = CapturedJob(
        session_id="synthetic-preconto",
        client_ip="127.0.0.1",
        client_port=1234,
        proxy_ip=config.listen_ip,
        proxy_port=config.listen_port,
        printer_ip=config.printer_ip,
        printer_port=config.printer_port,
        max_payload_bytes=config.max_payload_bytes,
    )
    job.append(CLIENT_TO_RCH, request, received_unix_ns=stamp, forwarded_unix_ns=stamp + 1000)
    job.finish()
    job_dir = RawSpoolStorage(config).archive(job, job_code="7319").job_dir

    assert process_job(config, job_dir).status == "parsed"

    output = job_dir / "PHARSED" / "7319_G_05.08.09.012.txt"
    assert "SOTTOTIPO: PRECONTO" in output.read_text(encoding="utf-8")
    metadata = json.loads((job_dir / "PHARSED" / "parsed.json").read_text(encoding="utf-8"))
    document = metadata["documents"][0]
    assert document["subtype"] == "PRECONTO"
    assert document["subtype_evidence"] == "OBSERVED_LITERAL_MARKER"
    assert document["semantic"]["parsed"]["metadata"]["parser_subtype"] == "PRECONTO"


def test_stale_processing_marker_is_recovered_and_scan_order_is_deterministic(tmp_path: Path) -> None:
    config = _config(tmp_path, parser_stale_lock_sec=1.0, parser_workers=2)
    later = _archive(config, code="7321")
    earlier = _archive(config, code="7320")
    marker = earlier / ".processing"
    marker.write_text("{}", encoding="utf-8")
    stale_time = time.time() - 60
    os.utime(marker, (stale_time, stale_time))

    results = run_once(config)

    assert [result.job_dir.name for result in results] == ["7320", "7321"]
    assert all(result.status == "parsed" for result in results)
    assert (earlier / ".processing.stale").is_file()
    assert not (earlier / ".processing").exists()
    assert (later / ".parsed").is_file()


def test_stale_takeover_removes_crashed_parser_staging_without_touching_raw_partial(tmp_path: Path) -> None:
    config = _config(tmp_path, parser_stale_lock_sec=1.0)
    job_dir = _archive(config, code="0412")
    crashed_token = "a" * 32
    orphan = job_dir / f".PHARSED.{crashed_token}.partial"
    orphan.mkdir()
    (orphan / "interrupted-output.tmp").write_bytes(b"uncommitted parser output")
    marker = job_dir / ".processing"
    marker.write_text(
        json.dumps({"schema": worker_module.PROCESSING_SCHEMA, "token": crashed_token}),
        encoding="utf-8",
    )
    stale_time = time.time() - 60
    os.utime(marker, (stale_time, stale_time))

    # The similarly suffixed sibling has a Dumper capture name, not a
    # tokenized Parser staging name, and must therefore remain untouched.
    raw_partial = job_dir.parent / ".0412.synthetic.partial"
    raw_partial.mkdir()
    (raw_partial / "request.raw.partial").write_bytes(b"forensic partial")

    result = process_job(config, job_dir)

    assert result.status == "parsed"
    assert not orphan.exists()
    assert raw_partial.is_dir()
    assert (raw_partial / "request.raw.partial").read_bytes() == b"forensic partial"
    assert not list(job_dir.glob(".PHARSED.*.partial"))


def test_commit_fence_removes_parser_staging_that_reappears_after_claim(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = _config(tmp_path)
    job_dir = _archive(config, code="0415")
    original_write = worker_module._write_documents
    late_orphan = job_dir / f".PHARSED.{'b' * 32}.partial"

    def write_with_late_orphan(received_config, loaded, token, output_dir):
        result = original_write(received_config, loaded, token, output_dir)
        late_orphan.mkdir()
        (late_orphan / "interrupted-output.tmp").write_bytes(b"lost worker")
        return result

    monkeypatch.setattr(worker_module, "_write_documents", write_with_late_orphan)

    result = process_job(config, job_dir)

    assert result.status == "parsed"
    assert (job_dir / ".parsed").is_file()
    assert not late_orphan.exists()
    assert not list(job_dir.glob(".PHARSED.*.partial"))


def test_lost_lease_cannot_publish_or_overwrite_takeover_outputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = _config(tmp_path, parser_stale_lock_sec=0.15)
    job_dir = _archive(config, code="0413")
    paused = threading.Event()
    resume = threading.Event()
    first_token: list[str] = []
    original_refresh = worker_module._refresh_claim
    original_commit = worker_module._commit_success

    def controlled_refresh(received_job: Path, token: str) -> None:
        is_first_heartbeat = (
            first_token
            and token == first_token[0]
            and threading.current_thread().name.startswith("rch-parser-heartbeat-")
        )
        if not is_first_heartbeat:
            original_refresh(received_job, token)

    def controlled_commit(
        received_job,
        received_config,
        token,
        loaded,
        count,
        metadata_hash,
        staging_dir,
    ):
        if not first_token:
            first_token.append(token)
            paused.set()
            assert resume.wait(5.0)
        return original_commit(
            received_job,
            received_config,
            token,
            loaded,
            count,
            metadata_hash,
            staging_dir,
        )

    monkeypatch.setattr(worker_module, "_refresh_claim", controlled_refresh)
    monkeypatch.setattr(worker_module, "_commit_success", controlled_commit)
    first_result: list[object] = []
    first = threading.Thread(target=lambda: first_result.append(process_job(config, job_dir)))
    first.start()
    assert paused.wait(5.0)
    time.sleep(config.parser_stale_lock_sec + 0.1)

    takeover = process_job(config, job_dir)
    assert (takeover.status, takeover.error) == ("parsed", None), repr(takeover)
    committed_before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [job_dir / ".parsed", *(job_dir / "PHARSED").iterdir()]
    }
    resume.set()
    first.join(timeout=5.0)

    assert not first.is_alive()
    assert len(first_result) == 1
    assert first_result[0].status == "claim_lost"
    assert committed_before == {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [job_dir / ".parsed", *(job_dir / "PHARSED").iterdir()]
    }
    assert not (job_dir / ".parse_attempts.json").exists()
    assert not (job_dir / ".parse_failed").exists()
    assert not list(job_dir.glob(".PHARSED.*.partial"))


def test_already_parsed_requires_authenticated_metadata_and_outputs(tmp_path: Path) -> None:
    config = _config(tmp_path)
    job_dir = _archive(config, code="0414")
    assert process_job(config, job_dir).status == "parsed"
    pdf = next((job_dir / "PHARSED").glob("*.pdf"))
    pdf.unlink()

    repeated = process_job(config, job_dir)

    assert repeated.status == "claim_error"
    assert repeated.error is not None
    assert "missing or has changed" in repeated.error
    assert not (job_dir / ".processing").exists()


def test_watcher_always_has_polling_fallback_and_optional_wakeup(tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    root.mkdir()
    stop = threading.Event()
    with SpoolWatcher(root, enabled=False) as polling:
        assert polling.mode == "polling"
        stop.set()
        assert polling.wait(0.1, stop) is False

    stop.clear()
    with SpoolWatcher(root, enabled=True) as watcher:
        assert watcher.mode in {"polling", "inotify+polling"}
        if watcher.inotify_available:
            (root / "new-date-directory").mkdir()
            assert watcher.wait(2.0, stop) is True
