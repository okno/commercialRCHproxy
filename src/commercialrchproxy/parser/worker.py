"""Consume atomically published RAW jobs without participating in the relay.

The dumper and this module share no memory and no inline network path.  A job
is eligible only after the dumper has published ``.ready``; ``load_spool_job``
then verifies every immutable input against the capture manifest before any
derived output is produced.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import re
import shutil
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from commercialrchproxy import __version__
from commercialrchproxy.config import MAX_CAPTURE_EVENTS_UPPER_BOUND, Config
from commercialrchproxy.rch.protocol import analyze_copies
from commercialrchproxy.render.clean_text import render_clean_text
from commercialrchproxy.render.document_model import DocumentLine, DocumentModel
from commercialrchproxy.render.pdf import render_pdf
from commercialrchproxy.storage.atomic import (
    atomic_generate,
    atomic_write_bytes,
    ensure_directory,
    fsync_directory,
)
from commercialrchproxy.storage.locking import FileLock
from commercialrchproxy.storage.spool import discover_ready_jobs, load_spool_job

PARSED_SCHEMA = "commercialrchproxy.pharsed.v1"
PROCESSING_SCHEMA = "commercialrchproxy.parser-processing.v1"
FAILURE_SCHEMA = "commercialrchproxy.parser-failure.v1"
_REQUEST_DIRECTION = "CLIENT -> RCH"
_MAX_TIMELINE_LINE_BYTES = 64 * 1024
_PARSER_OUTPUT_RE = re.compile(
    r"^[0-9]{4,32}_[CG]_[0-2][0-9]\.[0-5][0-9]\.[0-5][0-9]\.[0-9]{3}(?:_[0-9]{2,})?\.(?:txt|pdf)$"
)
_PARSER_STAGING_RE = re.compile(r"^\.PHARSED\.([0-9a-f]{32})\.partial$")
_LOGGER = logging.getLogger("commercialrchproxy.parser.worker")


class ParserJobError(RuntimeError):
    """A ready job could not safely produce semantic documents."""


class _ParserClaimLost(ParserJobError):
    """The processing lease is no longer owned by this worker."""


@dataclass(frozen=True, slots=True)
class ProcessResult:
    job_dir: Path
    status: str
    document_count: int = 0
    error: str | None = None


@dataclass(frozen=True, slots=True)
class _TimelineEvent:
    start_offset: int
    end_offset: int
    received_at: datetime
    received_unix_ns: int | None


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_capture_commit(job_dir: Path) -> None:
    ready = _read_small_json(job_dir / ".ready")
    expected = ready.get("manifest_sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ParserJobError("ready marker has no valid capture-manifest hash")
    if ready.get("codice_doc") != job_dir.name:
        raise ParserJobError("ready marker CODICE_DOC does not match its directory")
    manifest = job_dir / "manifest.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise ParserJobError("unsafe capture manifest")
    if _sha256(manifest) != expected:
        raise ParserJobError("capture manifest does not match the ready marker")


def _revalidate_loaded_inputs(loaded: Any) -> None:
    files = loaded.manifest.get("files")
    hashes = loaded.manifest.get("sha256")
    if not isinstance(files, dict) or not isinstance(hashes, dict):
        raise ParserJobError("capture manifest file maps changed during parsing")
    for key in ("request_raw", "response_raw", "timeline"):
        name = files.get(key)
        expected = hashes.get(key)
        if not isinstance(name, str) or Path(name).name != name or not isinstance(expected, str):
            raise ParserJobError(f"invalid capture artifact metadata for {key}")
        path = loaded.job_dir / name
        if path.is_symlink() or not path.is_file() or _sha256(path) != expected:
            raise ParserJobError(f"capture artifact changed during parsing: {key}")


def _unlink_parser_state(path: Path) -> None:
    if path.is_symlink():
        raise ParserJobError(f"refusing symlink parser state: {path}")
    try:
        path.unlink()
    except FileNotFoundError:
        return
    fsync_directory(path.parent)


def _read_small_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ParserJobError(f"unsafe parser state file: {path}")
    if path.stat().st_size > 64 * 1024:
        raise ParserJobError(f"parser state file is too large: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ParserJobError(f"parser state file is malformed: {path}")
    return value


def _require_current_claim(job_dir: Path, token: str) -> None:
    """Fail closed unless ``token`` still owns the processing marker.

    Callers that use this as a publication fence must already hold
    ``.parser.lock``.  Treat every unsafe or malformed marker as a lost lease:
    a worker that cannot prove ownership must not publish shared state.
    """

    path = job_dir / ".processing"
    if path.is_symlink() or not path.is_file():
        raise _ParserClaimLost("processing claim is missing or unsafe")
    try:
        state = _read_small_json(path)
    except Exception as exc:
        raise _ParserClaimLost("processing claim cannot be verified") from exc
    if state.get("schema") != PROCESSING_SCHEMA or state.get("token") != token:
        raise _ParserClaimLost("processing claim was replaced")


def _read_parser_metadata(path: Path, *, max_bytes: int) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ParserJobError(f"unsafe parser metadata: {path}")
    size = path.stat().st_size
    if size <= 0 or size > max_bytes:
        raise ParserJobError(f"parser metadata has an unsafe size: {path}")
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ParserJobError(f"parser metadata is malformed: {path}") from exc
    if not isinstance(value, dict):
        raise ParserJobError(f"parser metadata is not an object: {path}")
    return value


def _validate_parser_outputs(
    job_dir: Path,
    config: Config,
    *,
    output_dir: Path | None = None,
    expected_metadata_hash: str | None = None,
    expected_document_count: int | None = None,
) -> tuple[int, str]:
    """Authenticate ``parsed.json`` and every human output it references."""

    output_dir = output_dir or job_dir / config.pharsed_dirname
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise ParserJobError(f"parser output directory is missing or unsafe: {output_dir}")
    metadata_path = output_dir / "parsed.json"
    if metadata_path.is_symlink() or not metadata_path.is_file():
        raise ParserJobError(f"unsafe parser metadata: {metadata_path}")
    metadata_hash = _sha256(metadata_path)
    if expected_metadata_hash is not None and metadata_hash != expected_metadata_hash:
        raise ParserJobError("parser metadata hash does not match the completion state")
    metadata = _read_parser_metadata(metadata_path, max_bytes=config.max_payload_bytes)
    if metadata.get("schema") != PARSED_SCHEMA or metadata.get("codice_doc") != job_dir.name:
        raise ParserJobError("parser metadata does not identify this job")
    capture_hash = metadata.get("capture_manifest_sha256")
    if (
        metadata.get("capture_manifest") != "../manifest.json"
        or not isinstance(capture_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", capture_hash)
        or _sha256(job_dir / "manifest.json") != capture_hash
    ):
        raise ParserJobError("parser metadata is not bound to the current capture manifest")
    documents = metadata.get("documents")
    document_count = metadata.get("document_count")
    if (
        not isinstance(documents, list)
        or not isinstance(document_count, int)
        or isinstance(document_count, bool)
        or document_count != len(documents)
    ):
        raise ParserJobError("parser metadata has an invalid document count")
    if expected_document_count is not None and document_count != expected_document_count:
        raise ParserJobError("parser output document count changed before commit")

    referenced: set[str] = set()
    for document in documents:
        if not isinstance(document, dict):
            raise ParserJobError("parser metadata contains a malformed document")
        document_type = document.get("type")
        outputs = document.get("outputs")
        if document_type not in {"C", "G"} or not isinstance(outputs, dict):
            raise ParserJobError("parser metadata contains invalid document outputs")
        for output_kind, suffix in (("txt", ".txt"), ("pdf", ".pdf")):
            output = outputs.get(output_kind)
            if output is None:
                continue
            if not isinstance(output, dict):
                raise ParserJobError("parser metadata contains a malformed output reference")
            name = output.get("name")
            expected_hash = output.get("sha256")
            if (
                not isinstance(name, str)
                or Path(name).name != name
                or not _PARSER_OUTPUT_RE.fullmatch(name)
                or not name.startswith(f"{job_dir.name}_{document_type}_")
                or not name.endswith(suffix)
                or not isinstance(expected_hash, str)
                or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
                or name in referenced
            ):
                raise ParserJobError("parser metadata contains an unsafe output reference")
            path = output_dir / name
            if path.is_symlink() or not path.is_file() or _sha256(path) != expected_hash:
                raise ParserJobError(f"parser output is missing or has changed: {name}")
            referenced.add(name)

    children = list(output_dir.iterdir())
    if any(path.is_symlink() for path in children):
        raise ParserJobError("PHARSED contains a symlink")
    actual = {
        path.name for path in children if path.is_file() and _PARSER_OUTPUT_RE.fullmatch(path.name)
    }
    if actual != referenced:
        raise ParserJobError("PHARSED contains uncommitted or unreferenced parser outputs")
    return document_count, metadata_hash


def _validate_parsed_marker(job_dir: Path, config: Config) -> None:
    marker = _read_small_json(job_dir / ".parsed")
    expected_hash = marker.get("metadata_sha256")
    if (
        marker.get("schema") != PARSED_SCHEMA
        or marker.get("status") != "parsed"
        or marker.get("codice_doc") != job_dir.name
        or marker.get("metadata") != f"{config.pharsed_dirname}/parsed.json"
        or not isinstance(expected_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
    ):
        raise ParserJobError("invalid parser completion marker")
    count, _metadata_hash = _validate_parser_outputs(
        job_dir,
        config,
        expected_metadata_hash=expected_hash,
    )
    if marker.get("document_count") != count:
        raise ParserJobError("completion marker document count does not match parser metadata")


def _create_processing_marker(path: Path, token: str, config: Config) -> None:
    payload = _json_bytes(
        {
            "schema": PROCESSING_SCHEMA,
            "token": token,
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "started_at": datetime.now(UTC).isoformat(),
            "parser_version": __version__,
        }
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=True) as stream:
            fd = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, config.file_mode)
        fsync_directory(path.parent)
    finally:
        if fd >= 0:
            os.close(fd)


def _clear_parser_outputs(job_dir: Path, config: Config) -> None:
    """Invalidate parser state; output replacement is deferred until commit."""

    output_dir = job_dir / config.pharsed_dirname
    if output_dir.is_symlink():
        raise ParserJobError(f"refusing symlink PHARSED directory: {output_dir}")
    if output_dir.exists():
        if not output_dir.is_dir():
            raise ParserJobError(f"PHARSED path is not a directory: {output_dir}")
        if any(path.is_symlink() for path in output_dir.rglob("*")):
            raise ParserJobError(f"refusing symlink in PHARSED: {output_dir}")
    for name in (".parsed", ".parse_failed", ".parse_attempts.json"):
        _unlink_parser_state(job_dir / name)


def _cleanup_orphan_parser_staging(job_dir: Path, *, current_token: str | None) -> None:
    """Remove tokenized Parser staging that no current claim can publish.

    Callers must hold ``.parser.lock`` and must first prove which processing
    token, if any, is current.  The exact tokenized name deliberately excludes
    Dumper-owned ``.<CODICE_DOC>.<job-id>.partial`` directories.  Keeping the
    current token also prevents a commit fence from deleting its own staged
    output.
    """

    removed = False
    for path in job_dir.iterdir():
        match = _PARSER_STAGING_RE.fullmatch(path.name)
        if match is None or match.group(1) == current_token:
            continue
        if path.is_symlink() or not path.is_dir():
            raise ParserJobError(f"unsafe orphan parser staging artifact: {path}")
        shutil.rmtree(path)
        removed = True
    if removed:
        fsync_directory(job_dir)


def _claim_job(job_dir: Path, config: Config, *, force: bool) -> tuple[str | None, str]:
    """Create the exclusive marker, serializing stale recovery with an advisory lock."""

    root = config.output_dir
    if root.is_symlink() or not root.is_dir():
        raise ParserJobError(f"unsafe spool root: {root}")
    try:
        relative = job_dir.absolute().relative_to(root.absolute())
    except ValueError as exc:
        raise ParserJobError(f"job is outside the configured spool root: {job_dir}") from exc
    current = root.absolute()
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ParserJobError(f"refusing symlink spool path: {current}")
    if job_dir.is_symlink() or not job_dir.is_dir() or not re.fullmatch(r"[0-9]{4,32}", job_dir.name):
        raise ParserJobError(f"unsafe job directory: {job_dir}")
    ready = job_dir / ".ready"
    if ready.is_symlink() or not ready.is_file():
        raise ParserJobError(f"job is not atomically ready: {job_dir}")
    for path in job_dir.iterdir():
        if not path.name.endswith(".partial"):
            continue
        if _PARSER_STAGING_RE.fullmatch(path.name):
            if path.is_symlink() or not path.is_dir():
                raise ParserJobError(f"unsafe parser staging artifact: {path}")
            continue
        raise ParserJobError(f"ready job contains a partial artifact: {job_dir}")
    processing = job_dir / ".processing"
    with FileLock(job_dir / ".parser.lock", timeout=5.0):
        if processing.exists() or processing.is_symlink():
            if processing.is_symlink() or not processing.is_file():
                raise ParserJobError(f"unsafe processing marker: {processing}")
            age = max(0.0, time.time() - processing.stat().st_mtime)
            if age < config.parser_stale_lock_sec:
                return None, "busy"
            stale = job_dir / ".processing.stale"
            if stale.is_symlink():
                raise ParserJobError(f"unsafe stale marker: {stale}")
            os.replace(processing, stale)
            fsync_directory(job_dir)

        # No active claim remains at this point.  A crashed worker can leave a
        # tokenized staging directory behind; it is not a committed output and
        # cannot be published after its processing token has been displaced.
        _cleanup_orphan_parser_staging(job_dir, current_token=None)

        parsed = job_dir / ".parsed"
        failed = job_dir / ".parse_failed"
        if parsed.is_symlink() or failed.is_symlink():
            raise ParserJobError("refusing symlink parser completion state")
        if force:
            _clear_parser_outputs(job_dir, config)
        elif parsed.is_file():
            _validate_capture_commit(job_dir)
            _validate_parsed_marker(job_dir, config)
            return None, "already_parsed"
        elif failed.is_file():
            return None, "parse_failed"

        token = uuid.uuid4().hex
        _create_processing_marker(processing, token, config)
        return token, "claimed"


def _refresh_claim(job_dir: Path, token: str) -> None:
    path = job_dir / ".processing"
    with FileLock(job_dir / ".parser.lock", timeout=5.0):
        _require_current_claim(job_dir, token)
        # Stale takeover uses the same lock, so the verified pathname cannot
        # be replaced between this check and the heartbeat update.
        os.utime(path, None)


def _release_claim(job_dir: Path, token: str) -> None:
    path = job_dir / ".processing"
    with FileLock(job_dir / ".parser.lock", timeout=5.0):
        if not path.exists():
            return
        try:
            _require_current_claim(job_dir, token)
        except _ParserClaimLost:
            return
        _unlink_parser_state(path)


def _timeline_datetime(value: dict[str, Any]) -> tuple[datetime, int | None]:
    unix_ns = value.get("received_unix_ns")
    if isinstance(unix_ns, int) and not isinstance(unix_ns, bool) and unix_ns >= 0:
        seconds, nanoseconds = divmod(unix_ns, 1_000_000_000)
        return datetime.fromtimestamp(seconds, UTC) + timedelta(microseconds=nanoseconds // 1000), unix_ns
    received_at = value.get("received_at")
    if not isinstance(received_at, str):
        raise ParserJobError("request timeline event has no capture timestamp")
    try:
        parsed = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ParserJobError("request timeline event has an invalid capture timestamp") from exc
    if parsed.tzinfo is None:
        raise ParserJobError("request timeline timestamp has no timezone")
    return parsed, None


def _load_request_timeline(
    path: Path,
    *,
    max_events: int,
    expected_event_count: int,
) -> list[_TimelineEvent]:
    if (
        not isinstance(max_events, int)
        or isinstance(max_events, bool)
        or not 1 <= max_events <= MAX_CAPTURE_EVENTS_UPPER_BOUND
    ):
        raise ParserJobError(
            f"invalid configured timeline event limit {max_events}; "
            f"expected 1-{MAX_CAPTURE_EVENTS_UPPER_BOUND}"
        )
    if (
        not isinstance(expected_event_count, int)
        or isinstance(expected_event_count, bool)
        or expected_event_count < 0
    ):
        raise ParserJobError("capture manifest has an invalid timeline_event_count")
    if expected_event_count > max_events:
        raise ParserJobError(
            f"capture manifest declares {expected_event_count} timeline events, "
            f"exceeding configured limit {max_events}"
        )

    events: list[_TimelineEvent] = []
    event_count = 0
    with path.open("rb") as stream:
        while True:
            # Never let a corrupt JSONL record make ``readline`` allocate an
            # unbounded byte string before its size can be checked.
            raw_line = stream.readline(_MAX_TIMELINE_LINE_BYTES + 1)
            if not raw_line:
                break
            event_count += 1
            line_number = event_count
            if event_count > max_events:
                raise ParserJobError(f"timeline event limit {max_events} exceeded")
            if len(raw_line) > _MAX_TIMELINE_LINE_BYTES:
                raise ParserJobError(
                    f"timeline line {line_number} exceeds {_MAX_TIMELINE_LINE_BYTES} bytes"
                )
            try:
                value = json.loads(raw_line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ParserJobError(f"malformed timeline JSON at line {line_number}") from exc
            if not isinstance(value, dict):
                raise ParserJobError(f"timeline line {line_number} is not a JSON object")
            if value.get("direction") != _REQUEST_DIRECTION:
                continue
            offset = value.get("job_offset", value.get("session_offset"))
            length = value.get("byte_count")
            if (
                not isinstance(offset, int)
                or isinstance(offset, bool)
                or not isinstance(length, int)
                or isinstance(length, bool)
                or offset < 0
                or length <= 0
            ):
                raise ParserJobError(f"invalid request offset in timeline line {line_number}")
            received_at, unix_ns = _timeline_datetime(value)
            events.append(_TimelineEvent(offset, offset + length, received_at, unix_ns))
    if event_count != expected_event_count:
        raise ParserJobError(
            f"timeline event count mismatch: manifest={expected_event_count}, file={event_count}"
        )
    if not events:
        raise ParserJobError("timeline contains no timestamped request event")
    events.sort(key=lambda event: (event.start_offset, event.end_offset))
    return events


def _event_for_offset(events: list[_TimelineEvent], offset: int) -> _TimelineEvent:
    for event in events:
        if event.start_offset <= offset < event.end_offset:
            return event
    # A document opener can begin exactly at a receive boundary; select the
    # first later request event rather than fabricating a wall-clock value.
    for event in events:
        if event.start_offset >= offset:
            return event
    raise ParserJobError(f"no request timeline event covers document offset {offset}")


def _document_subtype(model: Any, document_type: str) -> tuple[str, str]:
    if document_type == "C":
        return "DOCUMENTO COMMERCIALE", "INFERRED_FROM_OBSERVED_RCH_COMMAND_SEQUENCE"
    visible = "\n".join(line.text for line in [*model.header, *model.lines, *model.footer]).upper()
    for marker in ("COPIA CONFORME", "PRECONTO", "COMANDA"):
        if marker in visible:
            return marker, "OBSERVED_LITERAL_MARKER"
    semantic_subtype = model.metadata.get("subtype")
    semantic_evidence = model.metadata.get("subtype_evidence")
    if (
        isinstance(semantic_subtype, str)
        and semantic_subtype in {"COMANDA", "PRECONTO", "COPIA CONFORME"}
    ):
        evidence = semantic_evidence if isinstance(semantic_evidence, str) else "INFERRED"
        return semantic_subtype, evidence
    return "DOCUMENTO GESTIONALE GENERICO", "CONSERVATIVE_DEFAULT"


def _annotate_parser_classification(
    model: DocumentModel,
    document_type: str,
    *,
    complete: bool,
) -> None:
    """Store the one authoritative parser classification on the model."""

    subtype, evidence = _document_subtype(model, document_type)
    model.metadata["parser_type"] = document_type
    model.metadata["parser_subtype"] = subtype
    model.metadata["parser_subtype_evidence"] = evidence
    model.metadata["parser_complete"] = complete
    model.metadata["parser_completeness"] = "COMPLETO" if complete else "INCOMPLETO"


def _render_model_with_metadata(model: DocumentModel) -> DocumentModel:
    """Prepend an explicitly non-receipt parser header to a copy of the model."""

    document_type = model.metadata.get("parser_type")
    subtype = model.metadata.get("parser_subtype")
    evidence = model.metadata.get("parser_subtype_evidence")
    completeness = model.metadata.get("parser_completeness")
    if not all(
        isinstance(value, str) and value
        for value in (document_type, subtype, evidence, completeness)
    ):
        raise ParserJobError("document model has no parser classification metadata")
    rendered = copy.deepcopy(model)
    rendered.header = [
        DocumentLine("=== METADATI PARSER ===", bold=True),
        DocumentLine("(NON PARTE DEL DOCUMENTO)"),
        DocumentLine(f"TIPO: {document_type}"),
        DocumentLine(f"SOTTOTIPO: {subtype}"),
        DocumentLine(f"STATO: {completeness}"),
        DocumentLine(f"EVIDENZA: {evidence}"),
        DocumentLine("=== DOCUMENTO RICOSTRUITO ===", bold=True),
        DocumentLine("(DA DATI CATTURATI)"),
        DocumentLine(""),
        *rendered.header,
    ]
    return rendered


def _human_capture_time(value: datetime, timezone: ZoneInfo) -> tuple[str, str]:
    local = value.astimezone(timezone)
    milliseconds = local.microsecond // 1000
    name = f"{local:%H.%M.%S}.{milliseconds:03d}"
    display = f"{local:%Y-%m-%dT%H:%M:%S}.{milliseconds:03d}{local:%z}"
    return name, display


def _unique_stem(code: str, kind: str, clock: str, seen: dict[str, int]) -> str:
    base = f"{code}_{kind}_{clock}"
    occurrence = seen.get(base, 0) + 1
    seen[base] = occurrence
    return base if occurrence == 1 else f"{base}_{occurrence:02d}"


def _remove_unreferenced_outputs(output_dir: Path, expected: set[str]) -> None:
    for path in output_dir.iterdir():
        if path.is_symlink():
            raise ParserJobError(f"refusing symlink in PHARSED: {path}")
        if path.is_file() and _PARSER_OUTPUT_RE.fullmatch(path.name) and path.name not in expected:
            path.unlink()
    fsync_directory(output_dir)


def _write_documents(
    config: Config,
    loaded: Any,
    token: str,
    output_dir: Path,
) -> tuple[int, str]:
    analysis = analyze_copies(loaded.request, loaded.response)
    if not analysis.protocol or not analysis.protocol.documents:
        raise ParserJobError(f"no semantic document reconstructed ({analysis.parser_status})")
    timeline = _load_request_timeline(
        loaded.timeline_path,
        max_events=config.max_capture_events,
        expected_event_count=loaded.manifest.get("timeline_event_count"),
    )
    timezone = ZoneInfo(config.timezone)
    if config.pharsed_dirname != "PHARSED":
        raise ParserJobError("PHARSED_DIRNAME must remain the literal PHARSED")
    expected_staging = loaded.job_dir / f".{config.pharsed_dirname}.{token}.partial"
    if output_dir != expected_staging:
        raise ParserJobError("unsafe parser staging directory")
    ensure_directory(output_dir, config.directory_mode)
    code = str(loaded.manifest["codice_doc"])
    seen: dict[str, int] = {}
    expected_files: set[str] = set()
    documents: list[dict[str, Any]] = []

    for index, parsed in enumerate(analysis.protocol.documents):
        _refresh_claim(loaded.job_dir, token)
        model = parsed.model
        canonical = model.document_type
        if canonical == "commerciale":
            kind = "C"
        elif canonical == "gestionale":
            kind = "G"
        else:
            raise ParserJobError(f"unsupported semantic document type: {canonical!r}")
        _annotate_parser_classification(model, kind, complete=parsed.complete)
        event = _event_for_offset(timeline, parsed.start_offset)
        clock, local_capture_time = _human_capture_time(event.received_at, timezone)
        stem = _unique_stem(code, kind, clock, seen)
        rendered_model = _render_model_with_metadata(model)
        text = render_clean_text(rendered_model)
        if not text:
            raise ParserJobError(f"semantic document {index + 1} has no human-readable captured fields")
        subtype = str(model.metadata["parser_subtype"])
        subtype_evidence = str(model.metadata["parser_subtype_evidence"])
        txt_name = f"{stem}.txt"
        pdf_name = f"{stem}.pdf"
        txt_path = output_dir / txt_name
        pdf_path = output_dir / pdf_name
        written: dict[str, dict[str, str] | None] = {"txt": None, "pdf": None}
        if config.save_clean_txt:
            atomic_write_bytes(
                txt_path,
                text.encode("utf-8"),
                mode=config.file_mode,
                directory_mode=config.directory_mode,
            )
            expected_files.add(txt_name)
            written["txt"] = {"name": txt_name, "sha256": _sha256(txt_path)}
        if config.save_pdf:
            atomic_generate(
                pdf_path,
                lambda temp, document=rendered_model: render_pdf(
                    document,
                    temp,
                    paper_width_mm=config.renderer_paper_width_mm,
                    characters_per_line=config.renderer_characters_per_line,
                ),
                mode=config.file_mode,
                directory_mode=config.directory_mode,
            )
            expected_files.add(pdf_name)
            written["pdf"] = {"name": pdf_name, "sha256": _sha256(pdf_path)}
        documents.append(
            {
                "ordinal": index + 1,
                "document_id": parsed.document_id,
                "type": kind,
                "canonical_type": canonical,
                "subtype": subtype,
                "subtype_evidence": subtype_evidence,
                "complete": parsed.complete,
                "classification_evidence": parsed.evidence,
                "capture_time_local": local_capture_time,
                "timezone": config.timezone,
                "source": {
                    "start_offset": parsed.start_offset,
                    "end_offset": parsed.end_offset,
                    "frame_ids": list(parsed.frame_ids),
                    "timeline_request_offset": event.start_offset,
                    "timeline_received_unix_ns": event.received_unix_ns,
                },
                "outputs": written,
                "semantic": parsed.to_dict(),
            }
        )

    _remove_unreferenced_outputs(output_dir, expected_files)
    metadata = {
        "schema": PARSED_SCHEMA,
        "project": "commercialRCHproxy",
        "parser_version": __version__,
        "codice_doc": code,
        "capture_manifest": "../manifest.json",
        "capture_manifest_sha256": _sha256(loaded.job_dir / "manifest.json"),
        "parser_status": analysis.parser_status,
        "document_count": len(documents),
        "documents": documents,
        "protocol_issues": [issue.to_dict() for issue in analysis.protocol.issues],
        "correlations": [item.to_dict() for item in analysis.protocol.correlations],
        "evidence_policy": analysis.protocol.to_dict()["evidence_policy"],
    }
    metadata_path = output_dir / "parsed.json"
    atomic_write_bytes(
        metadata_path,
        _json_bytes(metadata),
        mode=config.file_mode,
        directory_mode=config.directory_mode,
    )
    return len(documents), _sha256(metadata_path)


def _failure_count(job_dir: Path) -> int:
    path = job_dir / ".parse_attempts.json"
    if path.is_symlink():
        raise ParserJobError(f"refusing symlink parser attempt state: {path}")
    if not path.exists():
        return 0
    value = _read_small_json(path)
    count = value.get("attempts")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ParserJobError("invalid parser attempt counter")
    return count


def _record_failure(job_dir: Path, config: Config, error: Exception) -> tuple[int, bool]:
    attempts = _failure_count(job_dir) + 1
    message = f"{type(error).__name__}: {error}"[:2000]
    state = {
        "schema": FAILURE_SCHEMA,
        "attempts": attempts,
        "retry_count": config.parser_retry_count,
        "last_error": message,
        "last_failed_at": datetime.now(UTC).isoformat(),
    }
    atomic_write_bytes(
        job_dir / ".parse_attempts.json",
        _json_bytes(state),
        mode=config.file_mode,
        directory_mode=config.directory_mode,
    )
    exhausted = attempts > config.parser_retry_count
    if exhausted:
        atomic_write_bytes(
            job_dir / ".parse_failed",
            _json_bytes({**state, "status": "parse_failed_retries_exhausted"}),
            mode=config.file_mode,
            directory_mode=config.directory_mode,
        )
    return attempts, exhausted


def _record_failure_if_owned(
    job_dir: Path,
    config: Config,
    token: str,
    error: Exception,
) -> tuple[int, bool]:
    """Publish retry state only while the original lease is still current."""

    with FileLock(job_dir / ".parser.lock", timeout=5.0):
        _require_current_claim(job_dir, token)
        return _record_failure(job_dir, config, error)


def _commit_success(
    job_dir: Path,
    config: Config,
    token: str,
    loaded: Any,
    count: int,
    metadata_hash: str,
    staging_dir: Path,
) -> None:
    """Fence successful publication with the processing lease."""

    with FileLock(job_dir / ".parser.lock", timeout=5.0):
        _require_current_claim(job_dir, token)
        # A previously lost worker may have left or recreated its private
        # staging after this worker claimed the job.  Clean every other token
        # under the same publication fence, while preserving our own staging.
        _cleanup_orphan_parser_staging(job_dir, current_token=token)
        _validate_capture_commit(job_dir)
        _revalidate_loaded_inputs(loaded)
        _validate_parser_outputs(
            job_dir,
            config,
            output_dir=staging_dir,
            expected_metadata_hash=metadata_hash,
            expected_document_count=count,
        )
        output_dir = job_dir / config.pharsed_dirname
        superseded = job_dir / f".{config.pharsed_dirname}.{token}.superseded"
        if superseded.exists() or superseded.is_symlink():
            raise ParserJobError(f"parser superseded-output path already exists: {superseded}")
        if output_dir.is_symlink():
            raise ParserJobError(f"refusing symlink parser output: {output_dir}")
        if output_dir.exists():
            if not output_dir.is_dir() or any(path.is_symlink() for path in output_dir.rglob("*")):
                raise ParserJobError(f"unsafe existing parser output: {output_dir}")
            os.rename(output_dir, superseded)
            fsync_directory(job_dir)
        try:
            os.rename(staging_dir, output_dir)
            fsync_directory(job_dir)
        except Exception:
            if superseded.is_dir() and not output_dir.exists():
                os.rename(superseded, output_dir)
                fsync_directory(job_dir)
            raise
        _validate_parser_outputs(
            job_dir,
            config,
            expected_metadata_hash=metadata_hash,
            expected_document_count=count,
        )
        for name in (".parse_attempts.json", ".parse_failed"):
            _unlink_parser_state(job_dir / name)
        atomic_write_bytes(
            job_dir / ".parsed",
            _json_bytes(
                {
                    "schema": PARSED_SCHEMA,
                    "status": "parsed",
                    "codice_doc": loaded.manifest["codice_doc"],
                    "document_count": count,
                    "metadata": f"{config.pharsed_dirname}/parsed.json",
                    "metadata_sha256": metadata_hash,
                    "completed_at": datetime.now(UTC).isoformat(),
                    "parser_version": __version__,
                }
            ),
            mode=config.file_mode,
            directory_mode=config.directory_mode,
        )
        if superseded.is_dir() and not superseded.is_symlink():
            try:
                shutil.rmtree(superseded)
                fsync_directory(job_dir)
            except OSError as exc:
                _LOGGER.warning(
                    "parser_superseded_output_cleanup_failed job=%s error_type=%s",
                    job_dir,
                    type(exc).__name__,
                )


def process_job(config: Config, job_dir: Path, *, force: bool = False) -> ProcessResult:
    """Process one ready job; repeat calls are a no-op after ``.parsed``.

    ``force`` clears parser-owned markers and PHARSED outputs only.  It never
    changes request RAW, response RAW, timeline, ``.ready`` or manifest.
    """

    job_dir = Path(job_dir)
    try:
        token, state = _claim_job(job_dir, config, force=force)
    except Exception as exc:
        return ProcessResult(job_dir, "claim_error", error=f"{type(exc).__name__}: {exc}")
    if token is None:
        return ProcessResult(job_dir, state)
    staging_dir = job_dir / f".{config.pharsed_dirname}.{token}.partial"
    heartbeat_stop = threading.Event()

    def heartbeat() -> None:
        interval = max(0.1, min(30.0, config.parser_stale_lock_sec / 3.0))
        while not heartbeat_stop.wait(interval):
            try:
                _refresh_claim(job_dir, token)
            except Exception:
                return

    heartbeat_thread = threading.Thread(
        target=heartbeat,
        name=f"rch-parser-heartbeat-{job_dir.name}",
        daemon=True,
    )
    heartbeat_thread.start()
    try:
        _validate_capture_commit(job_dir)
        loaded = load_spool_job(job_dir, max_bytes=config.max_payload_bytes)
        _refresh_claim(job_dir, token)
        if staging_dir.exists() or staging_dir.is_symlink():
            raise ParserJobError(f"parser staging path already exists: {staging_dir}")
        staging_dir.mkdir(mode=config.directory_mode)
        fsync_directory(job_dir)
        count, metadata_hash = _write_documents(config, loaded, token, staging_dir)
        # Derived files become committed only after the immutable inputs and
        # their ready/manifest binding have been checked again under the same
        # lock used for stale takeover.  Losing the lease before this fence
        # makes the attempt uncommitted.
        _commit_success(job_dir, config, token, loaded, count, metadata_hash, staging_dir)
        return ProcessResult(job_dir, "parsed", count)
    except Exception as exc:
        try:
            _attempts, exhausted = _record_failure_if_owned(job_dir, config, token, exc)
        except _ParserClaimLost as claim_error:
            return ProcessResult(
                job_dir,
                "claim_lost",
                error=f"{type(exc).__name__}: {exc}; lease: {claim_error}",
            )
        except Exception as state_exc:
            return ProcessResult(
                job_dir,
                "failure_state_error",
                error=f"{type(exc).__name__}: {exc}; state: {type(state_exc).__name__}: {state_exc}",
            )
        return ProcessResult(
            job_dir,
            "parse_failed" if exhausted else "retry_pending",
            error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=1.0)
        if staging_dir.is_dir() and not staging_dir.is_symlink():
            try:
                shutil.rmtree(staging_dir)
                fsync_directory(job_dir)
            except OSError as staging_error:
                _LOGGER.error(
                    "parser_staging_cleanup_failed job=%s error_type=%s",
                    job_dir,
                    type(staging_error).__name__,
                )
        try:
            _release_claim(job_dir, token)
        except Exception as release_error:
            # A stale marker is recoverable on a later pass.  Never turn a
            # successfully published .parsed marker into a false parse error.
            _LOGGER.error(
                "parser_claim_release_failed job=%s error_type=%s",
                job_dir,
                type(release_error).__name__,
            )


def run_once(config: Config) -> list[ProcessResult]:
    """Process the deterministic lexicographic ready-job snapshot once."""

    jobs = discover_ready_jobs(config.output_dir)
    if config.parser_workers <= 1 or len(jobs) <= 1:
        return [process_job(config, job) for job in jobs]
    with ThreadPoolExecutor(max_workers=config.parser_workers, thread_name_prefix="rch-parser") as executor:
        return list(executor.map(lambda job: process_job(config, job), jobs))
