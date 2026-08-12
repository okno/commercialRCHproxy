from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from commercialrchproxy.tools import inspect_stream
from commercialrchproxy.tools.inspect_stream import cli, load_archive_directory

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> bytes:
    return bytes.fromhex((FIXTURES / name).read_text(encoding="ascii"))


def test_cli_json_inspects_direct_streams(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    request_path = tmp_path / "request.bin"
    response_path = tmp_path / "reply.bin"
    request_path.write_bytes(_fixture("rch_synthetic_commercial.request.hex"))
    response_path.write_bytes(_fixture("rch_synthetic_commercial.response.hex"))

    assert cli([str(request_path), "--response", str(response_path), "--json"]) == 0
    captured = capsys.readouterr()
    value = json.loads(captured.out)
    documents = value["sessions"][0]["protocol"]["documents"]
    assert documents[0]["document_type"] == "commerciale"
    assert documents[0]["complete"] is True
    assert value["sessions"][0]["summary"]["response"]["acks"] == 12


def test_cli_writes_per_document_forensic_chain(tmp_path: Path) -> None:
    request = _fixture("rch_synthetic_management.request.hex")
    response = _fixture("rch_synthetic_management.response.hex")
    request_path = tmp_path / "management.bin"
    response_path = tmp_path / "management-response.bin"
    output = tmp_path / "reconstructed"
    request_path.write_bytes(request)
    response_path.write_bytes(response)

    assert cli(
        [
            str(request_path),
            "--response",
            str(response_path),
            "--output-dir",
            str(output),
        ]
    ) == 0

    directories = [path for path in output.iterdir() if path.is_dir()]
    assert len(directories) == 1
    document_dir = directories[0]
    assert (document_dir / "raw_client_to_printer.bin").read_bytes() == request
    assert (document_dir / "raw.bin").read_bytes() == request
    assert (document_dir / "raw_printer_to_client.bin").read_bytes() == response
    expected = (FIXTURES / "rch_synthetic_management.expected.txt").read_text(encoding="utf-8")
    assert (document_dir / "receipt.txt").read_text(encoding="utf-8") == expected
    parsed = json.loads((document_dir / "parsed.json").read_text(encoding="utf-8"))
    metadata = json.loads((document_dir / "metadata.json").read_text(encoding="utf-8"))
    assert parsed["document"]["document_type"] == "gestionale"
    assert metadata["request_sha256"] == hashlib.sha256(request).hexdigest()
    assert metadata["connection_id"].startswith("offline-")
    assert metadata["raw_bin_scope"] == "client_to_printer_compatibility_alias"
    assert metadata["application_success"] is None
    assert (document_dir / "raw_event_log.txt").exists()


def test_archive_directory_reassembles_same_session_segments_in_order(tmp_path: Path) -> None:
    request = _fixture("rch_synthetic_commercial.request.hex")
    response = _fixture("rch_synthetic_commercial.response.hex")
    request_cut = 168
    response_cut = 158
    assert [request_cut, len(request) - request_cut] == [168, 106]
    assert [response_cut, len(response) - response_cut] == [158, 106]
    session_id = "synthetic-session"

    for index, (request_part, response_part) in enumerate(
        (
            (request[:request_cut], response[:response_cut]),
            (request[request_cut:], response[response_cut:]),
        ),
        1,
    ):
        base = f"segment-{index}"
        raw_name = f"{base}.raw"
        response_name = f"{base}.response.raw"
        (tmp_path / raw_name).write_bytes(request_part)
        (tmp_path / response_name).write_bytes(response_part)
        manifest = {
            "project": "commercialRCHproxy",
            "job_id": base,
            "session_id": session_id,
            "timestamp_start": f"2026-01-01T00:00:0{index}+00:00",
            "timestamp_end": f"2026-01-01T00:00:0{index}.1+00:00",
            "client_ip": "192.0.2.10",
            "client_port": 41000,
            "proxy_ip": "192.0.2.20",
            "proxy_port": 23,
            "printer_ip": "192.0.2.30",
            "printer_port": 23,
            "raw_sha256": hashlib.sha256(request_part).hexdigest(),
            "response_raw_sha256": hashlib.sha256(response_part).hexdigest(),
            "files": {"raw": raw_name, "response_raw": response_name, "technical_txt": None},
        }
        (tmp_path / f"{base}.json").write_text(json.dumps(manifest), encoding="utf-8")

    sessions = load_archive_directory(tmp_path)
    assert len(sessions) == 1
    assert sessions[0].session_id == session_id
    assert sessions[0].request == request
    assert sessions[0].response == response
    assert [source["job_id"] for source in sessions[0].source_artifacts] == ["segment-1", "segment-2"]
    assert sessions[0].client_ip == "192.0.2.10"
    assert sessions[0].printer_ip == "192.0.2.30"
    assert sessions[0].timestamp_start == "2026-01-01T00:00:01+00:00"
    assert sessions[0].timestamp_end == "2026-01-01T00:00:02.1+00:00"


@pytest.mark.parametrize("reference_kind", ["parent", "absolute"])
def test_archive_manifest_cannot_escape_its_directory(tmp_path: Path, reference_kind: str) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"MUST-NOT-BE-READ")
    manifest = {
        "project": "commercialRCHproxy",
        "job_id": "escape",
        "session_id": "escape-session",
        "timestamp_start": "2026-01-01T00:00:00+00:00",
        "files": {
            "raw": "../outside.bin" if reference_kind == "parent" else str(outside.resolve()),
            "response_raw": None,
        },
    }
    (archive / "escape.json").write_text(json.dumps(manifest), encoding="utf-8")

    sessions = load_archive_directory(archive)

    assert sessions[0].request == b""
    assert any("escapes" in warning for warning in sessions[0].warnings)


def test_archive_manifest_symlink_artifact_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"MUST-NOT-BE-READ")
    link = archive / "linked.bin"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    manifest = {
        "project": "commercialRCHproxy",
        "job_id": "symlink",
        "session_id": "symlink-session",
        "timestamp_start": "2026-01-01T00:00:00+00:00",
        "files": {"raw": link.name, "response_raw": None},
    }
    (archive / "symlink.json").write_text(json.dumps(manifest), encoding="utf-8")

    sessions = load_archive_directory(archive)

    assert sessions[0].request == b""
    assert any("escapes" in warning or "non-symlink" in warning for warning in sessions[0].warnings)


def test_archive_manifest_file_symlink_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text(
        json.dumps(
            {
                "project": "commercialRCHproxy",
                "job_id": "outside",
                "session_id": "outside-session",
                "timestamp_start": "2026-01-01T00:00:00+00:00",
                "files": {},
            }
        ),
        encoding="utf-8",
    )
    link = archive / "linked.json"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(ValueError, match="escapes|non-symlink"):
        load_archive_directory(archive)


def test_archive_reader_handles_invalid_files_shape_and_incomplete_capture(tmp_path: Path) -> None:
    (tmp_path / "array.json").write_text("[]", encoding="utf-8")
    manifest = {
        "project": "commercialRCHproxy",
        "job_id": "partial",
        "session_id": "partial-session",
        "timestamp_start": "2026-01-01T00:00:00+00:00",
        "files": None,
        "raw_complete": False,
        "capture_error": "synthetic truncation",
    }
    (tmp_path / "partial.json").write_text(json.dumps(manifest), encoding="utf-8")

    sessions = load_archive_directory(tmp_path)

    assert len(sessions) == 1
    assert any("valid files object" in warning for warning in sessions[0].warnings)
    assert any("synthetic truncation" in warning for warning in sessions[0].warnings)


@pytest.mark.parametrize(
    ("timeline_complete", "timeline_error", "expected_warning"),
    [
        (False, None, "incomplete timeline"),
        (False, "synthetic timeline truncation", "synthetic timeline truncation"),
        (True, "synthetic writer failure", "timeline error reported"),
    ],
)
def test_archive_reader_warns_about_incomplete_or_failed_timeline(
    tmp_path: Path,
    timeline_complete: bool,
    timeline_error: str | None,
    expected_warning: str,
) -> None:
    manifest = {
        "project": "commercialRCHproxy",
        "job_id": "timeline-state",
        "session_id": "timeline-session",
        "timestamp_start": "2026-01-01T00:00:00+00:00",
        "files": {},
        "timeline_complete": timeline_complete,
        "timeline_error": timeline_error,
    }
    (tmp_path / "timeline-state.json").write_text(json.dumps(manifest), encoding="utf-8")

    sessions = load_archive_directory(tmp_path)

    assert any(expected_warning in warning for warning in sessions[0].warnings)


def test_archive_scan_limits_all_json_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(inspect_stream, "_MAX_JSON_CANDIDATE_COUNT", 1)
    (tmp_path / "one.parsed.json").write_text("{}", encoding="utf-8")
    (tmp_path / "two.parsed.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON candidates"):
        load_archive_directory(tmp_path)


def test_archive_scan_limits_total_candidate_manifest_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(inspect_stream, "_MAX_TOTAL_MANIFEST_BYTES", 3)
    (tmp_path / "one.json").write_text("{}", encoding="utf-8")
    (tmp_path / "two.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="aggregate limit"):
        load_archive_directory(tmp_path)


def test_archive_scan_limits_distinct_sessions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(inspect_stream, "_MAX_SESSION_COUNT", 1)
    for index in range(2):
        manifest = {
            "project": "commercialRCHproxy",
            "job_id": f"job-{index}",
            "session_id": f"session-{index}",
            "timestamp_start": f"2026-01-01T00:00:0{index}+00:00",
            "files": {},
        }
        (tmp_path / f"job-{index}.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="more than 1 sessions"):
        load_archive_directory(tmp_path)


def test_archive_reassembly_warns_when_segment_order_is_ambiguous(tmp_path: Path) -> None:
    for job_id in ("a", "b", "c"):
        manifest = {
            "project": "commercialRCHproxy",
            "job_id": job_id,
            "session_id": "same-session",
            "timestamp_start": None if job_id == "b" else "2026-01-01T00:00:00+00:00",
            "files": {},
        }
        (tmp_path / f"{job_id}.json").write_text(json.dumps(manifest), encoding="utf-8")

    sessions = load_archive_directory(tmp_path)

    assert any("segment order may be ambiguous" in warning for warning in sessions[0].warnings)
    assert any("path order used as a tie-breaker" in warning for warning in sessions[0].warnings)


def test_archive_scan_limits_global_aggregate_stream_bytes(tmp_path: Path) -> None:
    for index in range(2):
        raw_name = f"job-{index}.raw"
        (tmp_path / raw_name).write_bytes(b"1234")
        manifest = {
            "project": "commercialRCHproxy",
            "job_id": f"job-{index}",
            "session_id": f"session-{index}",
            "timestamp_start": f"2026-01-01T00:00:0{index}+00:00",
            "files": {"raw": raw_name},
        }
        (tmp_path / f"job-{index}.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="global aggregate limit"):
        load_archive_directory(tmp_path, max_input_bytes=4, max_total_input_bytes=7)


def test_cli_refuses_to_overwrite_existing_reconstruction(tmp_path: Path) -> None:
    request_path = tmp_path / "request.bin"
    response_path = tmp_path / "response.bin"
    output = tmp_path / "out"
    request_path.write_bytes(_fixture("rch_synthetic_commercial.request.hex"))
    response_path.write_bytes(_fixture("rch_synthetic_commercial.response.hex"))
    args = [str(request_path), "--response", str(response_path), "--output-dir", str(output)]

    assert cli(args) == 0
    first_directory = next(path for path in output.iterdir() if path.is_dir())
    raw_hash = hashlib.sha256((first_directory / "raw.bin").read_bytes()).hexdigest()
    assert cli(args) == 2
    assert hashlib.sha256((first_directory / "raw.bin").read_bytes()).hexdigest() == raw_hash


def test_cli_labels_unframed_input_as_unknown(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    opaque = tmp_path / "opaque.bin"
    opaque.write_bytes(b"not an RCH frame")

    assert cli([str(opaque)]) == 0

    assert "Protocol: unrecognized/unknown" in capsys.readouterr().out


def test_cli_enforces_input_size_limit(tmp_path: Path) -> None:
    opaque = tmp_path / "opaque.bin"
    opaque.write_bytes(b"0123456789")

    assert cli([str(opaque), "--max-input-bytes", "5"]) == 2


def test_cli_enforces_global_direct_input_size_limit(tmp_path: Path) -> None:
    request = tmp_path / "request.bin"
    response = tmp_path / "response.bin"
    request.write_bytes(b"1234")
    response.write_bytes(b"5678")

    assert (
        cli(
            [
                str(request),
                "--response",
                str(response),
                "--max-input-bytes",
                "4",
                "--max-total-input-bytes",
                "7",
            ]
        )
        == 2
    )
