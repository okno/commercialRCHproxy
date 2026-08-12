"""Secure atomic artifact storage."""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from commercialrchproxy import __version__
from commercialrchproxy.capture.hashing import sha256_bytes, sha256_file
from commercialrchproxy.capture.jobs import CapturedJob
from commercialrchproxy.config import Config
from commercialrchproxy.rch.protocol import analyze_copies, unavailable_analysis
from commercialrchproxy.render.clean_text import render_clean_text
from commercialrchproxy.render.pdf import render_pdf
from commercialrchproxy.render.technical_text import render_technical_text
from commercialrchproxy.render.timeline import render_timeline_jsonl
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
        directory = self._directory_for(job)
        timestamp = job.started_at.strftime("%Y%m%dT%H%M%S.%fZ")
        base = f"{timestamp}_{job.job_id}"
        paths = {
            "raw": directory / f"{base}.raw",
            "response_raw": directory / f"{base}.response.raw",
            "technical_txt": directory / f"{base}.txt",
            "timeline_jsonl": directory / f"{base}.timeline.jsonl",
            "clean_txt": directory / f"{base}.PULITO.txt",
            "receipt_txt": directory / f"{base}.receipt.txt",
            "parsed_json": directory / f"{base}.parsed.json",
            "pdf": directory / f"{base}.pdf",
            "json": directory / f"{base}.json",
        }
        written: dict[str, Path] = {}
        hashes: dict[str, str | None] = {
            "raw": sha256_bytes(job.request_bytes),
            "response_raw": sha256_bytes(job.response_bytes) if job.response else None,
            "clean_txt": None,
            "receipt_txt": None,
            "parsed_json": None,
            "pdf": None,
        }
        render_errors: list[str] = []

        if self.config.save_raw:
            atomic_write_bytes(paths["raw"], job.request_bytes)
            written["raw"] = paths["raw"]
            if job.response:
                atomic_write_bytes(paths["response_raw"], job.response_bytes)
                written["response_raw"] = paths["response_raw"]

        # Publish the immutable directional copies and their receive timeline
        # before invoking any protocol decoder.  A future parser regression
        # must never be able to prevent preservation of the original evidence.
        if self.config.save_technical_txt:
            try:
                timeline = render_timeline_jsonl(job.chunks).encode("utf-8")
                atomic_write_bytes(paths["timeline_jsonl"], timeline)
                written["timeline_jsonl"] = paths["timeline_jsonl"]
            except Exception as exc:
                render_errors.append(f"timeline_jsonl: {type(exc).__name__}: {exc}")

        try:
            analysis = analyze_copies(job.request_bytes, job.response_bytes)
        except Exception as exc:
            # Parsing is a sidecar operation.  The relay already forwarded the
            # original bytes and the RAW copies above remain authoritative.
            render_errors.append(f"parser: {type(exc).__name__}: {exc}")
            analysis = unavailable_analysis(job.request_bytes, job.response_bytes, exc)

        if self.config.save_technical_txt:
            try:
                technical = render_technical_text(job.chunks, analysis).encode("utf-8")
                atomic_write_bytes(paths["technical_txt"], technical)
                written["technical_txt"] = paths["technical_txt"]
            except Exception as exc:
                render_errors.append(f"technical_txt: {type(exc).__name__}: {exc}")

        clean = ""
        try:
            receipt_texts = [render_clean_text(model) for model in analysis.documents]
            nonempty_receipts = [text for text in receipt_texts if text]
            if len(nonempty_receipts) == 1:
                clean = nonempty_receipts[0]
            elif nonempty_receipts:
                clean = "\n\f\n".join(text.rstrip("\n") for text in nonempty_receipts) + "\n"
            elif not analysis.documents:
                clean = render_clean_text(analysis.document)
        except Exception as exc:
            render_errors.append(f"receipt_render: {type(exc).__name__}: {exc}")
        if self.config.save_clean_txt:
            try:
                atomic_write_bytes(paths["clean_txt"], clean.encode("utf-8"))
                written["clean_txt"] = paths["clean_txt"]
                hashes["clean_txt"] = sha256_file(paths["clean_txt"])
                atomic_write_bytes(paths["receipt_txt"], clean.encode("utf-8"))
                written["receipt_txt"] = paths["receipt_txt"]
                hashes["receipt_txt"] = sha256_file(paths["receipt_txt"])
            except Exception as exc:
                render_errors.append(f"receipt_txt: {type(exc).__name__}: {exc}")

        if self.config.save_json:
            try:
                reconstruction = {
                    "schema": "commercialrchproxy.parsed.v1",
                    "parser_version": __version__,
                    "job_id": job.job_id,
                    "session_id": job.session_id,
                    "timestamp_start": job.started_at.isoformat(),
                    "timestamp_end": (job.ended_at or job.started_at).isoformat(),
                    "request_sha256": hashes["raw"],
                    "response_sha256": hashes["response_raw"],
                    "protocol": analysis.protocol.to_dict() if analysis.protocol is not None else None,
                    "parser_status": analysis.parser_status,
                    "parser_error": analysis.parser_error,
                }
                atomic_write_bytes(
                    paths["parsed_json"],
                    (json.dumps(reconstruction, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
                )
                written["parsed_json"] = paths["parsed_json"]
                hashes["parsed_json"] = sha256_file(paths["parsed_json"])
            except Exception as exc:
                render_errors.append(f"parsed_json: {type(exc).__name__}: {exc}")

        if self.config.save_pdf:
            try:
                pdf_models = analysis.documents or (analysis.document,)
                if len(pdf_models) > 1:
                    # Preserve the historical base PDF path for integrations;
                    # it represents the first reconstructed document.  The
                    # complete set is also emitted with explicit per-document
                    # names below.
                    atomic_generate(
                        paths["pdf"],
                        lambda temp: render_pdf(
                            pdf_models[0],
                            temp,
                            paper_width_mm=self.config.renderer_paper_width_mm,
                            characters_per_line=self.config.renderer_characters_per_line,
                        ),
                    )
                    written["pdf"] = paths["pdf"]
                    hashes["pdf"] = sha256_file(paths["pdf"])
                for index, model in enumerate(pdf_models, 1):
                    key = "pdf" if len(pdf_models) == 1 else f"document_{index:03d}_pdf"
                    path = paths["pdf"] if key == "pdf" else directory / f"{base}.document-{index:03d}.pdf"
                    atomic_generate(
                        path,
                        lambda temp, selected=model: render_pdf(
                            selected,
                            temp,
                            paper_width_mm=self.config.renderer_paper_width_mm,
                            characters_per_line=self.config.renderer_characters_per_line,
                        ),
                    )
                    written[key] = path
                    hashes[key] = sha256_file(path)
            except Exception as exc:
                render_errors.append(f"pdf: {type(exc).__name__}: {exc}")

        if not job.capture_complete:
            status = "capture_incomplete"
        elif not job.timeline_complete:
            status = "archived_timeline_partial_application_status_unknown"
        elif render_errors:
            status = "archived_render_partial_application_status_unknown"
        else:
            status = "archived_application_status_unknown"

        file_manifest = {
            key: (path.name if key in written else None)
            for key, path in paths.items()
            if key != "json"
        }
        for key, path in written.items():
            file_manifest.setdefault(key, path.name)
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
