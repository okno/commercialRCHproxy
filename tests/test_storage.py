from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pypdf import PdfReader

from commercialrchproxy.capture.jobs import CLIENT_TO_RCH, RCH_TO_CLIENT, CapturedJob, CaptureToken
from commercialrchproxy.storage.files import JobStorage
from tests.support import make_config, unused_port


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
    assert any(path.name.endswith(".pdf") for path in result.files.values())
    assert result.manifest_path.exists()
    assert not list(config.output_dir.rglob("*.tmp"))

    raw_path = result.files["raw"]
    response_path = result.files["response_raw"]
    clean_path = result.files["clean_txt"]
    assert raw_path.read_bytes() == request
    assert response_path.read_bytes() == response
    assert clean_path.read_bytes() == b""
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
