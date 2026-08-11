"""Secure atomic artifact storage."""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from commercialrchproxy.capture.hashing import sha256_bytes, sha256_file
from commercialrchproxy.capture.jobs import CapturedJob
from commercialrchproxy.config import Config
from commercialrchproxy.rch.protocol import analyze_copies
from commercialrchproxy.render.clean_text import render_clean_text
from commercialrchproxy.render.pdf import render_pdf
from commercialrchproxy.render.technical_text import render_technical_text
from commercialrchproxy.storage.manifest import build_manifest

_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9_.-]")


@dataclass(frozen=True, slots=True)
class ArchiveResult:
    manifest_path: Path
    status: str
    files: dict[str, Path]


def _ensure_directory(path: Path) -> None:
    if path.exists() and path.is_symlink():
        raise RuntimeError(f"Refusing symlink directory: {path}")
    path.mkdir(mode=0o750, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError(f"Unsafe output directory: {path}")
    try:
        path.chmod(0o750)
    except OSError:
        pass


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, data: bytes, mode: int = 0o640) -> None:
    _ensure_directory(path.parent)
    temp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd: int | None = os.open(temp, flags, 0o600)
    try:
        # close before os.replace: POSIX permits replacing an open file but
        # Windows correctly rejects it.  Publication semantics stay identical.
        stream = os.fdopen(fd, "wb", closefd=True)
        fd = None
        with stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
        _fsync_directory(path.parent)
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def atomic_generate(path: Path, generator: Callable[[Path], None], mode: int = 0o640) -> None:
    _ensure_directory(path.parent)
    temp = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(temp, flags, 0o600)
    os.close(fd)
    try:
        generator(temp)
        # Windows requires a writable descriptor for FlushFileBuffers/fsync.
        with temp.open("r+b") as stream:
            os.fsync(stream.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


class JobStorage:
    def __init__(self, config: Config) -> None:
        self.config = config
        _ensure_directory(config.output_dir)

    def _directory_for(self, job: CapturedJob) -> Path:
        device = _SAFE_COMPONENT.sub("_", job.printer_ip)
        stamp = job.started_at
        directory = self.config.output_dir / device / f"{stamp:%Y}" / f"{stamp:%m}" / f"{stamp:%d}"
        # Validate every application-controlled level; never accept a symlink.
        current = self.config.output_dir
        _ensure_directory(current)
        for component in directory.relative_to(self.config.output_dir).parts:
            current = current / component
            _ensure_directory(current)
        return directory

    def archive(self, job: CapturedJob) -> ArchiveResult:
        analysis = analyze_copies(job.request_bytes, job.response_bytes)
        directory = self._directory_for(job)
        timestamp = job.started_at.strftime("%Y%m%dT%H%M%S.%fZ")
        base = f"{timestamp}_{job.job_id}"
        paths = {
            "raw": directory / f"{base}.raw",
            "response_raw": directory / f"{base}.response.raw",
            "technical_txt": directory / f"{base}.txt",
            "clean_txt": directory / f"{base}.PULITO.txt",
            "pdf": directory / f"{base}.pdf",
            "json": directory / f"{base}.json",
        }
        written: dict[str, Path] = {}
        hashes: dict[str, str | None] = {
            "raw": sha256_bytes(job.request_bytes),
            "response_raw": sha256_bytes(job.response_bytes) if job.response else None,
            "clean_txt": None,
            "pdf": None,
        }
        render_errors: list[str] = []

        if self.config.save_raw:
            atomic_write_bytes(paths["raw"], job.request_bytes)
            written["raw"] = paths["raw"]
            if job.response:
                atomic_write_bytes(paths["response_raw"], job.response_bytes)
                written["response_raw"] = paths["response_raw"]

        if self.config.save_technical_txt:
            try:
                technical = render_technical_text(job.chunks, analysis).encode("utf-8")
                atomic_write_bytes(paths["technical_txt"], technical)
                written["technical_txt"] = paths["technical_txt"]
            except Exception as exc:
                render_errors.append(f"technical_txt: {type(exc).__name__}: {exc}")

        clean = render_clean_text(analysis.document)
        if self.config.save_clean_txt:
            try:
                atomic_write_bytes(paths["clean_txt"], clean.encode("utf-8"))
                written["clean_txt"] = paths["clean_txt"]
                hashes["clean_txt"] = sha256_file(paths["clean_txt"])
            except Exception as exc:
                render_errors.append(f"clean_txt: {type(exc).__name__}: {exc}")

        if self.config.save_pdf:
            try:
                atomic_generate(
                    paths["pdf"],
                    lambda temp: render_pdf(
                        analysis.document,
                        temp,
                        paper_width_mm=self.config.renderer_paper_width_mm,
                        characters_per_line=self.config.renderer_characters_per_line,
                    ),
                )
                written["pdf"] = paths["pdf"]
                hashes["pdf"] = sha256_file(paths["pdf"])
            except Exception as exc:
                render_errors.append(f"pdf: {type(exc).__name__}: {exc}")

        if not job.capture_complete:
            status = "capture_incomplete"
        elif render_errors:
            status = "archived_render_partial_application_status_unknown"
        else:
            status = "archived_application_status_unknown"

        file_manifest = {key: (path.name if key in written else None) for key, path in paths.items() if key != "json"}
        if self.config.save_json:
            file_manifest["json"] = paths["json"].name
        manifest = build_manifest(
            job,
            analysis,
            self.config,
            status=status,
            hashes=hashes,
            files=file_manifest,
            render_errors=render_errors,
        )
        if self.config.save_json:
            atomic_write_bytes(
                paths["json"],
                (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            )
            written["json"] = paths["json"]
        return ArchiveResult(paths["json"], status, written)
