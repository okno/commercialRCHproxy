from __future__ import annotations

import hashlib
import json
import re
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest

from commercialrchproxy.capture.jobs import CapturedJob
from commercialrchproxy.storage.spool import RawSpoolStorage, load_spool_job
from commercialrchproxy.tools import reparse as reparse_module
from commercialrchproxy.tools.reparse import reparse_ready_job
from commercialrchproxy.tools.replay import replay_raw_to_spool
from tests.support import make_config, unused_port

FIXTURES = Path(__file__).parent / "fixtures"


def _config(tmp_path: Path):
    return make_config(tmp_path, printer_port=unused_port(), listen_port=unused_port())


def _ready_job(tmp_path: Path, *, code: str = "0042"):
    config = _config(tmp_path)
    request = tmp_path / "synthetic-request.raw"
    response = tmp_path / "synthetic-response.raw"
    request.write_bytes(b"synthetic-request\x00bytes")
    response.write_bytes(b"synthetic-response\x06")
    result = replay_raw_to_spool(
        config,
        request,
        response,
        job_code=code,
        started_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        started_unix_ns=1_767_323_045_123_456_789,
    )
    return config, result


def _capture_hashes(job_dir: Path) -> dict[str, str]:
    manifest = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
    names = ["manifest.json", ".ready", *manifest["files"].values()]
    return {name: hashlib.sha256((job_dir / name).read_bytes()).hexdigest() for name in names}


def test_offline_replay_publishes_directional_ready_job_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path)
    request = tmp_path / "request.raw"
    response = tmp_path / "response.raw"
    request.write_bytes(b"request\x00payload")
    response.write_bytes(b"response\x06payload")

    def forbidden_socket(*_args: object, **_kwargs: object) -> socket.socket:
        raise AssertionError("offline replay attempted network access")

    monkeypatch.setattr(socket, "socket", forbidden_socket)
    result = replay_raw_to_spool(
        config,
        request,
        response,
        job_code="0040",
        started_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        started_unix_ns=1_767_323_045_123_456_789,
    )

    loaded = load_spool_job(result.job_dir, max_bytes=config.max_payload_bytes)
    assert loaded.request == b"request\x00payload"
    assert loaded.response == b"response\x06payload"
    assert result.job_dir.is_relative_to(config.output_dir)
    assert loaded.manifest["close_reason"] == "offline_replay_no_network_delivery"
    assert loaded.manifest["bytes_local_write_drain_to_printer"] == 0
    assert loaded.manifest["bytes_local_write_drain_to_client"] == 0
    assert loaded.manifest["job_boundary_source"] == "offline_supplied_directional_files"
    assert request.read_bytes() == b"request\x00payload"
    assert response.read_bytes() == b"response\x06payload"


def test_offline_replay_creates_empty_response_and_refuses_overwrite(tmp_path: Path) -> None:
    config = _config(tmp_path)
    request = tmp_path / "request.raw"
    request.write_bytes(b"request-only")
    first = replay_raw_to_spool(config, request, job_code="0041")
    loaded = load_spool_job(first.job_dir, max_bytes=config.max_payload_bytes)
    assert loaded.response == b""
    with pytest.raises(FileExistsError, match="already exists"):
        replay_raw_to_spool(config, request, job_code="0041")


def test_explicit_offline_0001_then_live_allocation_uses_0002(tmp_path: Path) -> None:
    config = _config(tmp_path)
    request = tmp_path / "request.raw"
    request.write_bytes(b"offline-0001")
    started_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    offline = replay_raw_to_spool(
        config,
        request,
        job_code="0001",
        started_at=started_at,
        started_unix_ns=1_767_323_045_123_456_789,
    )
    live_job = CapturedJob(
        session_id="live-after-offline",
        connection_id="live-after-offline",
        client_ip="192.0.2.10",
        client_port=41000,
        proxy_ip=config.listen_ip,
        proxy_port=config.listen_port,
        printer_ip=config.printer_ip,
        printer_port=config.printer_port,
        max_payload_bytes=config.max_payload_bytes,
        started_at=started_at,
        started_unix_ns=1_767_323_046_123_456_789,
    )
    live = RawSpoolStorage(config).begin_live(live_job)
    try:
        assert offline.code == "0001"
        assert live.code == "0002"
        assert live.partial_dir.name.startswith(".0002.")
    finally:
        live.close_incomplete(live_job, reason="synthetic test cleanup")


def test_offline_replay_refuses_symlink_input(tmp_path: Path) -> None:
    config = _config(tmp_path)
    source = tmp_path / "source.raw"
    source.write_bytes(b"request")
    link = tmp_path / "link.raw"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("symlinks are unavailable for this test account")
    with pytest.raises(ValueError, match="symlink"):
        replay_raw_to_spool(config, link, job_code="0043")


def test_reparse_dry_run_is_read_only_and_does_not_load_parser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, archived = _ready_job(tmp_path)
    pharsed = archived.job_dir / "PHARSED"
    pharsed.mkdir()
    (pharsed / "old.txt").write_text("old output", encoding="utf-8")
    before = _capture_hashes(archived.job_dir)

    def forbidden_loader():
        raise AssertionError("dry-run loaded parser worker")

    monkeypatch.setattr(reparse_module, "_load_process_job", forbidden_loader)
    result = reparse_ready_job(
        config,
        archived.job_dir,
        dry_run=True,
        backup_existing=True,
        code_filter="0042",
        now=datetime(2026, 1, 2, 3, 4, 5, 678000, tzinfo=UTC),
    )

    assert result.dry_run is True
    assert pharsed.is_dir()
    assert (pharsed / "old.txt").read_text(encoding="utf-8") == "old output"
    assert result.backup_path is not None
    assert not result.backup_path.exists()
    assert result.backup_path.name == "PHARSED.backup-2026-01-02_04.04.05.678"
    assert _capture_hashes(archived.job_dir) == before


def test_reparse_refuses_existing_output_without_backup(tmp_path: Path) -> None:
    config, archived = _ready_job(tmp_path)
    (archived.job_dir / "PHARSED").mkdir()
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        reparse_ready_job(config, archived.job_dir)


def test_reparse_backs_up_human_named_output_invokes_force_and_preserves_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, archived = _ready_job(tmp_path)
    old = archived.job_dir / "PHARSED"
    old.mkdir()
    (old / "old.txt").write_text("old output", encoding="utf-8")
    before = _capture_hashes(archived.job_dir)
    calls: list[tuple[object, Path, bool]] = []

    def fake_process_job(received_config, job_dir: Path, *, force: bool = False):
        calls.append((received_config, job_dir, force))
        output = job_dir / "PHARSED"
        output.mkdir()
        (output / "new.txt").write_text("new output", encoding="utf-8")
        return {"status": "synthetic-ok"}

    monkeypatch.setattr(reparse_module, "_load_process_job", lambda: fake_process_job)
    result = reparse_ready_job(
        config,
        archived.job_dir,
        backup_existing=True,
        now=datetime(2026, 1, 2, 3, 4, 5, 678000, tzinfo=UTC),
    )

    assert calls == [(config, archived.job_dir.resolve(), True)]
    assert result.parser_result == {"status": "synthetic-ok"}
    assert result.backup_path is not None
    assert re.fullmatch(
        r"PHARSED\.backup-\d{4}-\d{2}-\d{2}_\d{2}\.\d{2}\.\d{2}\.\d{3}",
        result.backup_path.name,
    )
    assert (result.backup_path / "old.txt").read_text(encoding="utf-8") == "old output"
    assert (archived.job_dir / "PHARSED" / "new.txt").read_text(encoding="utf-8") == "new output"
    assert _capture_hashes(archived.job_dir) == before


def test_reparse_integrates_with_worker_api_and_preserves_capture(tmp_path: Path) -> None:
    config = _config(tmp_path)
    request = tmp_path / "synthetic-management.request.raw"
    response = tmp_path / "synthetic-management.response.raw"
    request.write_bytes(bytes.fromhex((FIXTURES / "rch_synthetic_management.request.hex").read_text("ascii")))
    response.write_bytes(bytes.fromhex((FIXTURES / "rch_synthetic_management.response.hex").read_text("ascii")))
    archived = replay_raw_to_spool(
        config,
        request,
        response,
        job_code="0044",
        started_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        started_unix_ns=1_767_323_045_123_456_789,
    )
    before = _capture_hashes(archived.job_dir)

    result = reparse_ready_job(config, archived.job_dir, code_filter="0044")

    assert result.parser_result is not None
    assert result.parser_result.status == "parsed"
    assert result.parser_result.document_count == 1
    assert (archived.job_dir / ".parsed").is_file()
    assert (archived.job_dir / "PHARSED" / "parsed.json").is_file()
    assert _capture_hashes(archived.job_dir) == before


def test_reparse_filter_and_containment_fail_closed(tmp_path: Path) -> None:
    config, archived = _ready_job(tmp_path)
    with pytest.raises(ValueError, match="does not match"):
        reparse_ready_job(config, archived.job_dir, dry_run=True, code_filter="9999")

    outside = tmp_path / "outside" / "0042"
    outside.mkdir(parents=True)
    (outside / ".ready").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="outside configured spool root"):
        reparse_ready_job(config, outside, dry_run=True)


def test_reparse_rejects_ready_marker_that_no_longer_authenticates_manifest(tmp_path: Path) -> None:
    config, archived = _ready_job(tmp_path)
    marker = archived.job_dir / ".ready"
    value = json.loads(marker.read_text(encoding="utf-8"))
    value["manifest_sha256"] = "0" * 64
    marker.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest hash does not match"):
        reparse_ready_job(config, archived.job_dir, dry_run=True)


def test_reparse_refuses_symlink_pharsed_and_backup_collision(
    tmp_path: Path,
) -> None:
    config, archived = _ready_job(tmp_path)
    external = tmp_path / "external-output"
    external.mkdir()
    pharsed = archived.job_dir / "PHARSED"
    try:
        pharsed.symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are unavailable for this test account")
    with pytest.raises(ValueError, match="symlink parser output"):
        reparse_ready_job(config, archived.job_dir, dry_run=True, backup_existing=True)


def test_reparse_refuses_processing_marker_and_existing_backup(tmp_path: Path) -> None:
    config, archived = _ready_job(tmp_path)
    processing = archived.job_dir / ".processing"
    processing.write_text("synthetic active marker", encoding="utf-8")
    with pytest.raises(RuntimeError, match="processing"):
        reparse_ready_job(config, archived.job_dir, dry_run=True)
    processing.unlink()

    pharsed = archived.job_dir / "PHARSED"
    pharsed.mkdir()
    fixed = datetime(2026, 1, 2, 3, 4, 5, 678000, tzinfo=UTC)
    collision = archived.job_dir / "PHARSED.backup-2026-01-02_04.04.05.678"
    collision.mkdir()
    with pytest.raises(FileExistsError, match="Refusing to overwrite parser backup"):
        reparse_ready_job(
            config,
            archived.job_dir,
            dry_run=True,
            backup_existing=True,
            now=fixed,
        )


def test_reparse_backup_invalidates_old_commit_before_crash_gap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, archived = _ready_job(tmp_path)
    pharsed = archived.job_dir / "PHARSED"
    pharsed.mkdir()
    (pharsed / "old.txt").write_text("old output", encoding="utf-8")
    (archived.job_dir / ".parsed").write_text('{"status":"parsed"}\n', encoding="utf-8")

    def crash_after_backup(_config, _job_dir: Path, *, force: bool = False):
        assert force is True
        assert not pharsed.exists()
        assert not (archived.job_dir / ".parsed").exists()
        (archived.job_dir / f".PHARSED.{'a' * 32}.partial").mkdir()
        raise RuntimeError("synthetic crash after backup")

    monkeypatch.setattr(reparse_module, "_load_process_job", lambda: crash_after_backup)
    with pytest.raises(RuntimeError, match="synthetic crash"):
        reparse_ready_job(
            config,
            archived.job_dir,
            backup_existing=True,
            now=datetime(2026, 1, 2, 3, 4, 5, 678000, tzinfo=UTC),
        )

    backup = archived.job_dir / "PHARSED.backup-2026-01-02_04.04.05.678"
    assert (backup / "old.txt").read_text(encoding="utf-8") == "old output"
    assert not (archived.job_dir / ".parsed").exists()
    assert not pharsed.exists()

    def recovery_parser(_config, job_dir: Path, *, force: bool = False):
        assert force is True
        output = job_dir / "PHARSED"
        output.mkdir()
        (output / "recovered.txt").write_text("recovered", encoding="utf-8")
        return {"status": "parsed"}

    monkeypatch.setattr(reparse_module, "_load_process_job", lambda: recovery_parser)
    recovered = reparse_ready_job(config, archived.job_dir)
    assert recovered.parser_result == {"status": "parsed"}
    assert (pharsed / "recovered.txt").is_file()
    assert (backup / "old.txt").is_file()


def test_reparse_cli_returns_nonzero_when_worker_does_not_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config, archived = _ready_job(tmp_path)
    config_file = tmp_path / "site.conf"
    config_file.write_text(
        "\n".join(
            (
                f"LISTEN_IP={config.listen_ip}",
                f"LISTEN_PORT={config.listen_port}",
                f"PRINTER_IP={config.printer_ip}",
                f"PRINTER_PORT={config.printer_port}",
                f"OUTPUT_DIR={config.output_dir}",
                f"LOG_DIR={config.log_dir}",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        reparse_module,
        "reparse_ready_job",
        lambda *_args, **_kwargs: reparse_module.ReparseResult(
            archived.job_dir,
            archived.job_dir.name,
            False,
            None,
            {"status": "retry_pending"},
        ),
    )

    exit_code = reparse_module.cli(
        [str(archived.job_dir), "--config", str(config_file), "--json"]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert '"status": "retry_pending"' in captured.out
    assert "did not commit" in captured.err
