from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from commercialrchproxy.capture.jobs import CLIENT_TO_RCH, RCH_TO_CLIENT, CapturedJob, CaptureToken
from commercialrchproxy.config import Config
from commercialrchproxy.storage import files as storage_module
from commercialrchproxy.storage.files import JobStorage
from tests.support import make_config, unused_port

FIXTURES = Path(__file__).parent / "fixtures"


def _hex_fixture(name: str) -> bytes:
    return bytes.fromhex((FIXTURES / name).read_text(encoding="ascii"))


def _job(config: Config, *, session_id: str = "session-1") -> CapturedJob:
    return CapturedJob(
        session_id=session_id,
        client_ip="127.0.0.1",
        client_port=1234,
        proxy_ip=config.listen_ip,
        proxy_port=config.listen_port,
        printer_ip=config.printer_ip,
        printer_port=config.printer_port,
        max_payload_bytes=config.max_payload_bytes,
    )


def test_all_required_artifacts_are_atomic_and_hashed(tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        printer_port=unused_port(),
        listen_port=unused_port(),
        save_pdf=True,
    )
    job = CapturedJob(
        session_id="session-1",
        client_ip="127.0.0.1",
        client_port=1234,
        proxy_ip=config.listen_ip,
        proxy_port=config.listen_port,
        printer_ip=config.printer_ip,
        printer_port=config.printer_port,
        max_payload_bytes=config.max_payload_bytes,
    )
    # Synthetic visible text must not become a human-rendered document without
    # an authoritative protocol mapping.
    request = b"DOCUMENTO GESTIONALE\r\nProdotto 0,00\r\nTavolo: 00-X\r\n"
    response = b"\x02opaque-response\x03"
    job.append(CLIENT_TO_RCH, request)
    job.append(RCH_TO_CLIENT, response)
    job.finish()

    result = JobStorage(config).archive(job)
    assert any(path.name.endswith(".raw") and not path.name.endswith(".response.raw") for path in result.files.values())
    assert any(path.name.endswith(".response.raw") for path in result.files.values())
    assert any(path.name.endswith(".PULITO.txt") for path in result.files.values())
    assert any(path.name.endswith(".timeline.jsonl") for path in result.files.values())
    assert any(path.name.endswith(".pdf") for path in result.files.values())
    assert result.manifest_path.exists()
    assert not list(config.output_dir.rglob("*.tmp"))

    raw_path = result.files["raw"]
    response_path = result.files["response_raw"]
    clean_path = result.files["clean_txt"]
    timeline_path = result.files["timeline_jsonl"]
    assert raw_path.read_bytes() == request
    assert response_path.read_bytes() == response
    assert clean_path.read_bytes() == b""
    timeline = [json.loads(line) for line in timeline_path.read_text(encoding="utf-8").splitlines()]
    assert [event["sequence"] for event in timeline] == [1, 2]
    assert [event["direction"] for event in timeline] == [CLIENT_TO_RCH, RCH_TO_CLIENT]
    assert timeline[0]["session_offset"] == 0
    assert timeline[0]["byte_count"] == len(request)
    assert timeline[0]["sha256"] == hashlib.sha256(request).hexdigest()
    assert timeline[0]["remote_arrival"] is None
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["raw_sha256"] == hashlib.sha256(request).hexdigest()
    assert manifest["response_raw_sha256"] == hashlib.sha256(response).hexdigest()
    assert manifest["protocol_status"] is None
    assert manifest["application_success"] is None
    assert manifest["framing_confirmed"] is False
    assert manifest["human_render_status"] == "unavailable_unconfirmed_field_mapping"
    assert manifest["document_type"] is None
    assert manifest["observed_variant"] is None
    assert manifest["classification_evidence"] == "UNCONFIRMED"
    assert manifest["candidate_printed_class"] == "documento_gestionale"
    assert manifest["candidate_observed_variant"] is None
    assert manifest["candidate_classification_evidence"] == "INFERRED"
    assert manifest["bytes_arrived_at_printer"] is None
    assert manifest["bytes_arrived_at_client"] is None
    assert manifest["delivery_evidence"] == "UNCONFIRMED_WITHOUT_PCAP"
    assert manifest["pdf_kind"] == "PDF_PROXY_RENDERED"
    assert manifest["pdf_rch_original"] is None
    assert len(PdfReader(str(result.files["pdf"])).pages) == 1


def test_capture_limit_is_explicit_and_never_claimed_complete(tmp_path: Path) -> None:
    config = make_config(tmp_path, unused_port(), unused_port(), max_payload_bytes=8, save_pdf=False)
    job = CapturedJob(
        session_id="limited",
        client_ip="127.0.0.1",
        client_port=None,
        proxy_ip=config.listen_ip,
        proxy_port=config.listen_port,
        printer_ip=config.printer_ip,
        printer_port=config.printer_port,
        max_payload_bytes=8,
    )
    job.append(CLIENT_TO_RCH, b"0123456789")
    job.finish()
    result = JobStorage(config).archive(job)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["raw_complete"] is False
    assert manifest["status"] == "capture_incomplete"
    assert result.files["raw"].read_bytes() == b"01234567"


def test_local_writer_drain_is_not_claimed_as_remote_arrival(tmp_path: Path) -> None:
    config = make_config(tmp_path, unused_port(), unused_port(), save_pdf=False)
    job = CapturedJob(
        session_id="local-drain-only",
        client_ip="127.0.0.1",
        client_port=1234,
        proxy_ip=config.listen_ip,
        proxy_port=config.listen_port,
        printer_ip=config.printer_ip,
        printer_port=config.printer_port,
        max_payload_bytes=config.max_payload_bytes,
    )
    payload = b"opaque-bytes"
    chunk_index = job.append(CLIENT_TO_RCH, payload)
    job.mark_local_write_drain(
        CaptureToken(job.job_id, chunk_index, CLIENT_TO_RCH, len(payload)),
        completed=True,
    )
    job.finish()

    result = JobStorage(config).archive(job)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["bytes_local_write_drain_to_printer"] == len(payload)
    assert manifest["bytes_arrived_at_printer"] is None
    assert manifest["delivery_evidence"] == "UNCONFIRMED_WITHOUT_PCAP"
    assert "delivery_and_application_status_unknown" in manifest["transport_status"]


def test_observed_framing_generates_parsed_and_human_sidecars(tmp_path: Path) -> None:
    config = make_config(tmp_path, unused_port(), unused_port(), save_pdf=False)
    request = _hex_fixture("rch_synthetic_management.request.hex")
    response = _hex_fixture("rch_synthetic_management.response.hex")
    job = _job(config, session_id="synthetic-management")
    job.append(CLIENT_TO_RCH, request)
    job.append(RCH_TO_CLIENT, response)
    job.finish()

    result = JobStorage(config).archive(job)
    receipt = result.files["receipt_txt"].read_text(encoding="utf-8")
    expected = (FIXTURES / "rch_synthetic_management.expected.txt").read_text(encoding="utf-8")
    assert receipt == expected
    assert result.files["clean_txt"].read_text(encoding="utf-8") == expected

    parsed = json.loads(result.files["parsed_json"].read_text(encoding="utf-8"))
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert parsed["protocol"]["documents"][0]["document_type"] == "gestionale"
    assert manifest["framing_confirmed"] is True
    assert manifest["request_frames"] == 19
    assert manifest["response_frames"] == 18
    assert manifest["response_ack_count"] == 19
    assert manifest["document_type"] == "gestionale"
    assert manifest["classification_evidence"] == "INFERRED"
    assert manifest["document_count"] == 1
    assert manifest["human_render_status"].startswith("available_partial")
    assert manifest["receipt_txt_sha256"] == hashlib.sha256(expected.encode()).hexdigest()


def test_parser_exception_never_prevents_raw_or_manifest_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = make_config(tmp_path, unused_port(), unused_port(), save_pdf=False)
    request = b"opaque request that must survive"
    response = b"opaque response that must survive"
    job = _job(config, session_id="parser-failure")
    job.append(CLIENT_TO_RCH, request)
    job.append(RCH_TO_CLIENT, response)
    job.finish()

    def fail_parser(_request: bytes, _response: bytes) -> object:
        raise RuntimeError("synthetic parser fault")

    monkeypatch.setattr(storage_module, "analyze_copies", fail_parser)
    result = JobStorage(config).archive(job)

    assert result.files["raw"].read_bytes() == request
    assert result.files["response_raw"].read_bytes() == response
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["parser_status"] == "parser_error_raw_preserved"
    assert manifest["parser_error"] == "RuntimeError: synthetic parser fault"
    assert any("parser: RuntimeError" in error for error in manifest["render_errors"])
    parsed = json.loads(result.files["parsed_json"].read_text(encoding="utf-8"))
    assert parsed["protocol"] is None


def test_multiple_documents_receive_distinct_proxy_pdfs(tmp_path: Path) -> None:
    config = make_config(tmp_path, unused_port(), unused_port(), save_pdf=True)
    one_document = _hex_fixture("rch_synthetic_management.request.hex")
    job = _job(config, session_id="two-documents")
    job.append(CLIENT_TO_RCH, one_document + one_document)
    job.finish()

    result = JobStorage(config).archive(job)
    assert set(result.files) >= {"pdf", "document_001_pdf", "document_002_pdf"}
    for key in ("pdf", "document_001_pdf", "document_002_pdf"):
        assert len(PdfReader(str(result.files[key])).pages) == 1
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["document_count"] == 2
    assert manifest["pdf_kind"] == "PDF_PROXY_RENDERED"
    assert set(manifest["rendered_pdf_files"]) == {"pdf", "document_001_pdf", "document_002_pdf"}
    assert "\f" in result.files["receipt_txt"].read_text(encoding="utf-8")


def test_capture_event_timeline_limit_does_not_truncate_directional_raw(tmp_path: Path) -> None:
    config = make_config(tmp_path, unused_port(), unused_port(), save_pdf=False)
    job = _job(config, session_id="timeline-limit")
    job.max_capture_events = 2

    job.append(CLIENT_TO_RCH, b"A")
    job.append(CLIENT_TO_RCH, b"B")
    job.append(CLIENT_TO_RCH, b"C")
    job.finish()
    result = JobStorage(config).archive(job)

    assert result.files["raw"].read_bytes() == b"ABC"
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["raw_complete"] is True
    assert manifest["timeline_complete"] is False
    assert manifest["raw_event_count"] == 2
    assert manifest["raw_event_count_observed"] == 3
    assert manifest["status"] == "archived_timeline_partial_application_status_unknown"
