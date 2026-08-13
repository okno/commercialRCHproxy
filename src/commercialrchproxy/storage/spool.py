"""Atomic RAW spool shared only through the filesystem.

The dumper publishes capture jobs here.  It deliberately imports no RCH
decoder or renderer.  The parser consumes only directories whose last
publication step created ``.ready``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO
from zoneinfo import ZoneInfo

from commercialrchproxy import __version__
from commercialrchproxy.capture.hashing import sha256_file
from commercialrchproxy.capture.jobs import CLIENT_TO_RCH, RCH_TO_CLIENT, CapturedChunk, CapturedJob
from commercialrchproxy.config import Config
from commercialrchproxy.render.timeline import render_timeline_event, render_timeline_jsonl
from commercialrchproxy.storage.atomic import atomic_write_bytes, ensure_directory, fsync_directory
from commercialrchproxy.storage.counter import JobCodeAllocator, printer_component, validate_job_code
from commercialrchproxy.storage.locking import FileLock

CAPTURE_SCHEMA = "commercialrchproxy.capture.v1"
_EPOCH_NAME = re.compile(r"[0-9]+\.[0-9]{9}")
_PARTIAL_DIRECTORY = re.compile(r"\.([0-9]{4,32})\..+\.partial")


def epoch_stamp(unix_ns: int) -> str:
    if unix_ns < 0:
        raise ValueError("Unix timestamp cannot be negative")
    seconds, nanoseconds = divmod(unix_ns, 1_000_000_000)
    return f"{seconds}.{nanoseconds:09d}"


@dataclass(frozen=True, slots=True)
class SpoolArchiveResult:
    job_dir: Path
    manifest_path: Path
    code: str
    status: str
    files: dict[str, Path]


@dataclass(frozen=True, slots=True)
class LoadedSpoolJob:
    job_dir: Path
    manifest: dict[str, Any]
    request: bytes
    response: bytes
    timeline_path: Path


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_all(stream: BinaryIO, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = stream.write(view)
        if written is None or written <= 0:
            raise OSError("short write while appending capture evidence")
        view = view[written:]


def _safe_artifact(job_dir: Path, name: object) -> Path:
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise ValueError(f"Unsafe spool artifact name: {name!r}")
    path = job_dir / name
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Missing or unsafe spool artifact: {path}")
    if path.resolve().parent != job_dir.resolve():
        raise ValueError(f"Spool artifact escapes job directory: {path}")
    return path


class LiveSpoolCapture:
    """Incrementally write one active transport capture into hidden staging.

    The object is deliberately synchronous and single-consumer.  The async
    recorder owns the bounded queue and invokes these methods serially in a
    worker thread.  A process crash can therefore leave only a hidden partial
    directory; publication is impossible until :meth:`finalize` completes all
    fsync, hash, manifest and rename steps.
    """

    _PARTIAL_NAMES = {
        "request_raw": "request.raw.partial",
        "response_raw": "response.raw.partial",
        "timeline": "timeline.jsonl.partial",
    }

    def __init__(
        self,
        storage: RawSpoolStorage,
        job: CapturedJob,
        *,
        code: str,
        parent: Path,
        partial_dir: Path,
        final_dir: Path,
    ) -> None:
        self.storage = storage
        self.config = storage.config
        self.code = code
        self.parent = parent
        self.partial_dir = partial_dir
        self.final_dir = final_dir
        self.session_id = job.session_id
        self.connection_id = job.connection_id
        self._closed = False
        self._files: dict[str, BinaryIO] = {}
        self._hashers = {key: hashlib.sha256() for key in self._PARTIAL_NAMES}
        self._sizes = {"request_raw": 0, "response_raw": 0, "timeline": 0}
        self._pending: dict[int, CapturedChunk] = {}
        self._skipped: set[int] = set()
        self._next_timeline_sequence = 1
        self._maximum_sequence = 0
        self._timeline_events = 0

        initial_names = self._final_names(job)
        capture_meta = storage._capture_manifest(
            job,
            code,
            initial_names,
            status="live_capture_in_progress",
            hashes={},
            request_size=0,
            response_size=0,
            timeline_event_count=0,
        )
        capture_meta["partial_files"] = dict(self._PARTIAL_NAMES)
        atomic_write_bytes(
            partial_dir / "capture-meta.json.partial",
            _json_bytes(capture_meta),
            mode=self.config.file_mode,
            directory_mode=self.config.directory_mode,
        )
        try:
            for key, name in self._PARTIAL_NAMES.items():
                path = partial_dir / name
                stream = path.open("xb", buffering=0)
                os.chmod(path, self.config.file_mode)
                self._files[key] = stream
        except Exception:
            self.close_incomplete()
            raise

    @staticmethod
    def _final_names(job: CapturedJob) -> dict[str, str]:
        return {
            "request_raw": f"file_{epoch_stamp(job.request_started_unix_ns)}.raw",
            "response_raw": f"response_{epoch_stamp(job.response_started_unix_ns)}.raw",
            "timeline": f"timeline_{epoch_stamp(job.request_started_unix_ns)}.jsonl",
        }

    def append(
        self,
        *,
        sequence: int,
        direction: str,
        data: bytes,
        timeline_chunk: CapturedChunk | None,
    ) -> None:
        if self._closed:
            raise RuntimeError("live capture is already closed")
        expected_sequence = self._maximum_sequence + 1
        if sequence != expected_sequence:
            raise ValueError(
                f"capture sequence must be contiguous: expected {expected_sequence}, got {sequence}"
            )
        key = "request_raw" if direction == CLIENT_TO_RCH else "response_raw"
        if direction not in {CLIENT_TO_RCH, RCH_TO_CLIENT}:
            raise ValueError(f"unsupported capture direction: {direction!r}")
        if data:
            _write_all(self._files[key], data)
            self._hashers[key].update(data)
            self._sizes[key] += len(data)
        self._maximum_sequence = max(self._maximum_sequence, sequence)
        if timeline_chunk is None:
            self._skipped.add(sequence)
        else:
            if timeline_chunk.sequence != sequence:
                raise ValueError("timeline sequence does not match queued capture sequence")
            if timeline_chunk.byte_count != len(data):
                raise ValueError("timeline byte count does not match queued RAW bytes")
            self._pending[sequence] = replace(timeline_chunk, data=b"")
        self._flush_ready_timeline()

    def mark_local_write_drain(
        self,
        *,
        sequence: int,
        completed: bool,
        drain_unix_ns: int,
        error: str | None,
    ) -> None:
        if self._closed:
            raise RuntimeError("live capture is already closed")
        chunk = self._pending.get(sequence)
        if chunk is None:
            # The event can be absent because MAX_CAPTURE_EVENTS deliberately
            # bounded timeline metadata.  Directional RAW remains authoritative.
            return
        chunk.local_write_drain_completed = completed
        chunk.drain_unix_ns = drain_unix_ns
        chunk.forward_error = error
        self._flush_ready_timeline()

    def _write_timeline_chunk(self, chunk: CapturedChunk) -> None:
        encoded = render_timeline_event(
            chunk,
            session_id=self.session_id,
            connection_id=self.connection_id,
        ).encode("utf-8")
        _write_all(self._files["timeline"], encoded)
        self._hashers["timeline"].update(encoded)
        self._sizes["timeline"] += len(encoded)
        self._timeline_events += 1

    def _flush_ready_timeline(self, *, force: bool = False) -> None:
        while self._next_timeline_sequence <= self._maximum_sequence:
            sequence = self._next_timeline_sequence
            if sequence in self._skipped:
                self._skipped.remove(sequence)
                self._next_timeline_sequence += 1
                continue
            chunk = self._pending.get(sequence)
            if chunk is None:
                break
            if not force and chunk.local_write_drain_completed is None:
                break
            self._pending.pop(sequence)
            self._write_timeline_chunk(chunk)
            self._next_timeline_sequence += 1

    def _sync_and_close(self) -> None:
        if self._closed:
            return
        self._flush_ready_timeline(force=True)
        for stream in self._files.values():
            stream.flush()
            os.fsync(stream.fileno())
        for stream in self._files.values():
            stream.close()
        self._closed = True
        fsync_directory(self.partial_dir)

    def finalize(self, job: CapturedJob) -> SpoolArchiveResult:
        self._sync_and_close()
        if self.final_dir.exists() or self.final_dir.is_symlink():
            raise FileExistsError(f"CODICE_DOC destination already exists: {self.final_dir}")
        names = self._final_names(job)
        final_paths: dict[str, Path] = {}
        for key, partial_name in self._PARTIAL_NAMES.items():
            source = self.partial_dir / partial_name
            destination = self.partial_dir / names[key]
            os.replace(source, destination)
            final_paths[key] = destination

        hashes = {key: self._hashers[key].hexdigest() for key in self._PARTIAL_NAMES}
        status = "ready" if job.capture_complete and job.timeline_complete else "ready_capture_incomplete"
        manifest = self.storage._capture_manifest(
            job,
            self.code,
            names,
            status=status,
            hashes=hashes,
            request_size=self._sizes["request_raw"],
            response_size=self._sizes["response_raw"],
            timeline_event_count=self._timeline_events,
        )
        atomic_write_bytes(
            self.partial_dir / "manifest.json",
            _json_bytes(manifest),
            mode=self.config.file_mode,
            directory_mode=self.config.directory_mode,
        )
        (self.partial_dir / "capture-meta.json.partial").unlink()
        atomic_write_bytes(
            self.partial_dir / ".ready",
            _json_bytes(
                {
                    "schema": CAPTURE_SCHEMA,
                    "codice_doc": self.code,
                    "manifest_sha256": sha256_file(self.partial_dir / "manifest.json"),
                    "published_at": datetime.now(UTC).isoformat(),
                }
            ),
            mode=self.config.file_mode,
            directory_mode=self.config.directory_mode,
        )
        fsync_directory(self.partial_dir)
        os.replace(self.partial_dir, self.final_dir)
        fsync_directory(self.parent)
        files = {key: self.final_dir / path.name for key, path in final_paths.items()}
        files["manifest"] = self.final_dir / "manifest.json"
        files["ready"] = self.final_dir / ".ready"
        return SpoolArchiveResult(self.final_dir, self.final_dir / "manifest.json", self.code, status, files)

    def close_incomplete(
        self,
        job: CapturedJob | None = None,
        *,
        reason: str | None = None,
    ) -> None:
        """Best-effort close that intentionally never publishes a ready job.

        When the recorder can still supply the job snapshot, refresh the
        partial metadata with the byte counts and hashes that actually reached
        disk.  This is recovery evidence only: no manifest or ``.ready`` marker
        is created and the parser must continue to ignore the directory.
        """
        if self._closed:
            return
        for stream in self._files.values():
            try:
                stream.flush()
                os.fsync(stream.fileno())
            except OSError:
                pass
            try:
                stream.close()
            except OSError:
                pass
        self._closed = True
        if job is not None:
            try:
                names = self._final_names(job)
                partial_sizes: dict[str, int] = {}
                partial_hashes: dict[str, str] = {}
                for key, name in self._PARTIAL_NAMES.items():
                    path = self.partial_dir / name
                    if path.is_file() and not path.is_symlink():
                        partial_sizes[key] = path.stat().st_size
                        partial_hashes[key] = sha256_file(path)
                capture_meta = self.storage._capture_manifest(
                    job,
                    self.code,
                    names,
                    status="live_capture_incomplete",
                    hashes={},
                    request_size=partial_sizes.get("request_raw", 0),
                    response_size=partial_sizes.get("response_raw", 0),
                    timeline_event_count=self._timeline_events,
                )
                capture_meta["partial_files"] = dict(self._PARTIAL_NAMES)
                capture_meta["partial_sizes"] = partial_sizes
                capture_meta["partial_sha256"] = partial_hashes
                capture_meta["incomplete_reason"] = reason or job.capture_error
                atomic_write_bytes(
                    self.partial_dir / "capture-meta.json.partial",
                    _json_bytes(capture_meta),
                    mode=self.config.file_mode,
                    directory_mode=self.config.directory_mode,
                )
            except (OSError, RuntimeError, ValueError):
                # The storage path is already failing.  Preserve whatever RAW
                # bytes were flushed instead of turning cleanup into another
                # publication attempt.
                pass
        try:
            fsync_directory(self.partial_dir)
        except OSError:
            pass


class RawSpoolStorage:
    """Publish immutable request/response/timeline jobs without parsing them."""

    def __init__(self, config: Config) -> None:
        self.config = config
        ensure_directory(config.output_dir, config.directory_mode)
        self.allocator = JobCodeAllocator(
            config.output_dir,
            start=config.job_code_start,
            width=config.job_code_width,
            file_mode=config.file_mode,
            directory_mode=config.directory_mode,
        )

    def _date_parent(self, job: CapturedJob) -> Path:
        device = printer_component(job.printer_ip)
        local = job.started_at.astimezone(ZoneInfo(self.config.timezone))
        parent = self.config.output_dir / device / f"{local:%Y}" / f"{local:%m}" / f"{local:%d}"
        current = self.config.output_dir
        for component in parent.relative_to(self.config.output_dir).parts:
            current /= component
            ensure_directory(current, self.config.directory_mode)
        return parent

    def _prepare_capture(
        self,
        job: CapturedJob,
        *,
        job_code: str | None,
    ) -> tuple[str, Path, Path, Path]:
        parent = self._date_parent(job)
        device = printer_component(job.printer_ip)
        state = self.config.output_dir / ".state" / device
        ensure_directory(state, self.config.directory_mode)

        # Explicit offline imports and automatic live captures share this
        # lock.  Together with the persistent counter it makes selection and
        # creation one cross-process critical section.  Automatic allocation
        # also scans immutable jobs and abandoned staging directories so a
        # pre-existing explicit replay cannot poison the next live capture.
        with FileLock(state / "capture-allocation.lock"):
            if job_code is not None:
                code = validate_job_code(job_code, self.config.job_code_width)
                if self._code_in_use(job.printer_ip, code):
                    raise FileExistsError(f"CODICE_DOC destination or staging already exists: {code}")
            else:
                code = self.allocator.allocate(job.printer_ip)
                if self._code_in_use(job.printer_ip, code):
                    # A missing/stale counter can collide with many imported
                    # jobs.  Scan once after the first collision rather than
                    # traversing the full archive for every normal capture.
                    used_codes = self._existing_codes(job.printer_ip)
                    while code in used_codes:
                        code = self.allocator.allocate(job.printer_ip)

            final_dir = parent / code
            partial_dir = parent / f".{code}.{job.job_id}.partial"
            if final_dir.exists() or final_dir.is_symlink():
                raise FileExistsError(f"CODICE_DOC destination already exists: {final_dir}")
            if partial_dir.exists() or partial_dir.is_symlink():
                raise FileExistsError(f"Capture staging directory already exists: {partial_dir}")
            partial_dir.mkdir(mode=self.config.directory_mode, exist_ok=False)
            try:
                partial_dir.chmod(self.config.directory_mode)
            except OSError:
                pass
            fsync_directory(parent)
            return code, parent, partial_dir, final_dir

    def _spool_days(self, printer_ip: str) -> Iterator[Path]:
        """Yield safe date directories without following historical links."""
        device_root = self.config.output_dir / printer_component(printer_ip)
        if not device_root.exists():
            return
        if device_root.is_symlink() or not device_root.is_dir():
            raise RuntimeError(f"Unsafe printer spool directory: {device_root}")

        for year in device_root.iterdir():
            if year.is_symlink() or not year.is_dir() or not re.fullmatch(r"[0-9]{4}", year.name):
                continue
            for month in year.iterdir():
                if month.is_symlink() or not month.is_dir() or not re.fullmatch(r"[0-9]{2}", month.name):
                    continue
                for day in month.iterdir():
                    if day.is_symlink() or not day.is_dir() or not re.fullmatch(r"[0-9]{2}", day.name):
                        continue
                    yield day

    def _code_in_use(self, printer_ip: str, code: str) -> bool:
        for day in self._spool_days(printer_ip):
            final = day / code
            if final.exists() or final.is_symlink():
                return True
            if next(day.glob(f".{code}.*.partial"), None) is not None:
                return True
        return False

    def _existing_codes(self, printer_ip: str) -> set[str]:
        """Return final or staging CODICE_DOC values without following links."""
        used: set[str] = set()
        for day in self._spool_days(printer_ip):
            for entry in day.iterdir():
                if re.fullmatch(r"[0-9]{4,32}", entry.name):
                    used.add(entry.name)
                    continue
                partial = _PARTIAL_DIRECTORY.fullmatch(entry.name)
                if partial is not None:
                    used.add(partial.group(1))
        return used

    def begin_live(self, job: CapturedJob, *, job_code: str | None = None) -> LiveSpoolCapture:
        """Open a hidden incremental capture; no parser-visible marker exists."""
        code, parent, partial_dir, final_dir = self._prepare_capture(job, job_code=job_code)
        return LiveSpoolCapture(
            self,
            job,
            code=code,
            parent=parent,
            partial_dir=partial_dir,
            final_dir=final_dir,
        )

    def archive(self, job: CapturedJob, *, job_code: str | None = None) -> SpoolArchiveResult:
        code, parent, partial_dir, final_dir = self._prepare_capture(job, job_code=job_code)

        request_name = f"file_{epoch_stamp(job.request_started_unix_ns)}.raw"
        response_name = f"response_{epoch_stamp(job.response_started_unix_ns)}.raw"
        timeline_name = f"timeline_{epoch_stamp(job.request_started_unix_ns)}.jsonl"
        names = {"request_raw": request_name, "response_raw": response_name, "timeline": timeline_name}
        capture_meta = self._capture_manifest(job, code, names, status="publication_in_progress", hashes={})
        atomic_write_bytes(
            partial_dir / "capture-meta.json.partial",
            _json_bytes(capture_meta),
            mode=self.config.file_mode,
            directory_mode=self.config.directory_mode,
        )

        partial_paths = {
            key: partial_dir / f"{name}.partial" for key, name in names.items()
        }
        atomic_write_bytes(
            partial_paths["request_raw"],
            job.request_bytes,
            mode=self.config.file_mode,
            directory_mode=self.config.directory_mode,
        )
        # The response file is intentionally present even when empty.
        atomic_write_bytes(
            partial_paths["response_raw"],
            job.response_bytes,
            mode=self.config.file_mode,
            directory_mode=self.config.directory_mode,
        )
        timeline = render_timeline_jsonl(
            job.chunks,
            session_id=job.session_id,
            connection_id=job.connection_id,
        ).encode("utf-8")
        atomic_write_bytes(
            partial_paths["timeline"],
            timeline,
            mode=self.config.file_mode,
            directory_mode=self.config.directory_mode,
        )
        final_paths: dict[str, Path] = {}
        for key, partial in partial_paths.items():
            destination = partial_dir / names[key]
            os.replace(partial, destination)
            final_paths[key] = destination

        hashes = {key: sha256_file(path) for key, path in final_paths.items()}
        status = "ready" if job.capture_complete and job.timeline_complete else "ready_capture_incomplete"
        manifest = self._capture_manifest(job, code, names, status=status, hashes=hashes)
        atomic_write_bytes(
            partial_dir / "manifest.json",
            _json_bytes(manifest),
            mode=self.config.file_mode,
            directory_mode=self.config.directory_mode,
        )
        (partial_dir / "capture-meta.json.partial").unlink()
        atomic_write_bytes(
            partial_dir / ".ready",
            _json_bytes(
                {
                    "schema": CAPTURE_SCHEMA,
                    "codice_doc": code,
                    "manifest_sha256": sha256_file(partial_dir / "manifest.json"),
                    "published_at": datetime.now(UTC).isoformat(),
                }
            ),
            mode=self.config.file_mode,
            directory_mode=self.config.directory_mode,
        )
        fsync_directory(partial_dir)
        os.replace(partial_dir, final_dir)
        fsync_directory(parent)
        files = {key: final_dir / path.name for key, path in final_paths.items()}
        files["manifest"] = final_dir / "manifest.json"
        files["ready"] = final_dir / ".ready"
        return SpoolArchiveResult(final_dir, final_dir / "manifest.json", code, status, files)

    def _capture_manifest(
        self,
        job: CapturedJob,
        code: str,
        names: dict[str, str],
        *,
        status: str,
        hashes: dict[str, str],
        request_size: int | None = None,
        response_size: int | None = None,
        timeline_event_count: int | None = None,
    ) -> dict[str, Any]:
        ended = job.ended_at or job.started_at
        return {
            "schema": CAPTURE_SCHEMA,
            "project": "commercialRCHproxy",
            "codice_doc": code,
            "job_id": job.job_id,
            "session_id": job.session_id,
            "connection_id": job.connection_id,
            "printer_ip": job.printer_ip,
            "printer_port": job.printer_port,
            "listen_ip": job.proxy_ip,
            "listen_port": job.proxy_port,
            "client_ip": job.client_ip,
            "client_port": job.client_port,
            "opened_at": job.started_at.isoformat(),
            "closed_at": ended.isoformat(),
            "opened_unix_ns": job.started_unix_ns,
            "request_first_unix_ns": job.request_started_unix_ns,
            "response_first_unix_ns": job.response_started_unix_ns,
            "timestamp_representation": "integer_unix_nanoseconds",
            "timestamp_resolution": "platform_runtime_clock_resolution_unverified",
            "close_reason": job.transport_status,
            "request_size": len(job.request) if request_size is None else request_size,
            "response_size": len(job.response) if response_size is None else response_size,
            "bytes_read_from_client": job.bytes_captured_from_client,
            "bytes_read_from_printer": job.bytes_captured_from_printer,
            "bytes_local_write_drain_to_printer": job.bytes_local_write_drain_to_printer,
            "bytes_local_write_drain_to_client": job.bytes_local_write_drain_to_client,
            "bytes_arrived_at_printer": None,
            "bytes_arrived_at_client": None,
            "remote_delivery": None,
            "delivery_evidence": "UNCONFIRMED_WITHOUT_PCAP",
            "files": names,
            "sha256": hashes,
            "raw_complete": job.capture_complete,
            "capture_error": job.capture_error,
            "timeline_complete": job.timeline_complete,
            "timeline_error": job.timeline_error,
            "timeline_event_count": (
                len(job.chunks) if timeline_event_count is None else timeline_event_count
            ),
            "timeline_event_count_observed": job.capture_event_count_observed,
            "job_boundary_source": job.boundary_source,
            "job_boundary_confidence": job.boundary_confidence,
            "status": status,
            "dumper_version": __version__,
            "config_version": self.config.config_version,
            "timezone": self.config.timezone,
        }

    def recover_partials(self, *, minimum_age_sec: float = 10.0, maximum: int = 1000) -> list[Path]:
        """Fail closed on abandoned publication directories.

        A partial contains no completion evidence, so it is never promoted to
        ``.ready`` automatically.  It is preserved for an operator/offline
        recovery tool and returned for CRITICAL logging by the dumper.
        """
        now = time.time()
        found: list[Path] = []
        for path in self.config.output_dir.rglob(".*.partial"):
            if len(found) >= maximum:
                break
            try:
                if path.is_dir() and not path.is_symlink() and now - path.stat().st_mtime >= minimum_age_sec:
                    found.append(path)
            except OSError:
                continue
        return sorted(found)


def discover_ready_jobs(root: Path, *, maximum: int = 10_000) -> list[Path]:
    jobs: list[Path] = []
    if not root.exists() or root.is_symlink():
        return jobs
    for marker in root.rglob(".ready"):
        if len(jobs) >= maximum:
            raise RuntimeError(f"ready job discovery limit exceeded ({maximum})")
        job_dir = marker.parent
        if job_dir.is_symlink() or not job_dir.is_dir():
            continue
        if not re.fullmatch(r"[0-9]{4,32}", job_dir.name):
            continue
        jobs.append(job_dir)
    return sorted(jobs)


def load_spool_job(job_dir: Path, *, max_bytes: int) -> LoadedSpoolJob:
    ready_path = job_dir / ".ready"
    if job_dir.is_symlink() or not job_dir.is_dir() or ready_path.is_symlink() or not ready_path.is_file():
        raise ValueError(f"Job is not atomically ready: {job_dir}")
    if ready_path.stat().st_size > 65_536:
        raise ValueError("ready marker exceeds 64 KiB")
    manifest_path = _safe_artifact(job_dir, "manifest.json")
    if manifest_path.stat().st_size > 1_048_576:
        raise ValueError("capture manifest exceeds 1 MiB")
    try:
        ready = json.loads(ready_path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("ready marker is malformed") from exc
    if (
        not isinstance(ready, dict)
        or ready.get("schema") != CAPTURE_SCHEMA
        or ready.get("codice_doc") != job_dir.name
        or ready.get("manifest_sha256") != sha256_file(manifest_path)
    ):
        raise ValueError("ready marker does not authenticate this capture manifest")
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != CAPTURE_SCHEMA:
        raise ValueError("unsupported or malformed capture manifest")
    if value.get("codice_doc") != job_dir.name:
        raise ValueError("CODICE_DOC does not match its directory")
    files = value.get("files")
    hashes = value.get("sha256")
    if not isinstance(files, dict) or not isinstance(hashes, dict):
        raise ValueError("capture manifest files/hash maps are malformed")
    request_path = _safe_artifact(job_dir, files.get("request_raw"))
    response_path = _safe_artifact(job_dir, files.get("response_raw"))
    timeline_path = _safe_artifact(job_dir, files.get("timeline"))
    if request_path.stat().st_size + response_path.stat().st_size > max_bytes:
        raise ValueError(f"capture exceeds parser input limit ({max_bytes} bytes)")
    request = request_path.read_bytes()
    response = response_path.read_bytes()
    for key, path in (("request_raw", request_path), ("response_raw", response_path), ("timeline", timeline_path)):
        expected = hashes.get(key)
        if not isinstance(expected, str) or sha256_file(path) != expected:
            raise ValueError(f"SHA-256 mismatch for {key}")
    return LoadedSpoolJob(job_dir, value, request, response, timeline_path)
