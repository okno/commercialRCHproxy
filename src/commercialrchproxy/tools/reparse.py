"""Safely request parsing of an already-published spool job."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from commercialrchproxy import __version__
from commercialrchproxy.capture.hashing import sha256_file
from commercialrchproxy.config import Config, ConfigError
from commercialrchproxy.storage.atomic import fsync_directory
from commercialrchproxy.storage.counter import validate_job_code
from commercialrchproxy.storage.locking import FileLock
from commercialrchproxy.storage.spool import CAPTURE_SCHEMA, LoadedSpoolJob, load_spool_job

_BACKUP_NAME = re.compile(r"PHARSED\.backup-[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{2}\.[0-9]{2}\.[0-9]{2}\.[0-9]{3}")
_PARSER_STAGING_NAME = re.compile(r"^\.PHARSED\.[0-9a-f]{32}\.partial$")


@dataclass(frozen=True, slots=True)
class ReparseResult:
    job_dir: Path
    code: str
    dry_run: bool
    backup_path: Path | None
    parser_result: object | None


def _contained_ready_job(config: Config, candidate: Path) -> Path:
    root = config.output_dir.absolute()
    target = candidate.absolute()
    if root.is_symlink():
        raise ValueError(f"Refusing symlink spool root: {root}")
    if not root.is_dir():
        raise ValueError(f"Spool root does not exist or is not a directory: {root}")
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Job is outside configured spool root: {candidate}") from exc
    current = root
    for component in relative.parts:
        current /= component
        if current.is_symlink():
            raise ValueError(f"Refusing symlink in job path: {current}")
    try:
        resolved_root = root.resolve(strict=True)
        resolved_target = target.resolve(strict=True)
        resolved_target.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Job path is missing or escapes the configured spool root: {candidate}") from exc
    if not resolved_target.is_dir():
        raise ValueError(f"Job path is not a directory: {candidate}")
    marker = resolved_target / ".ready"
    if marker.is_symlink() or not marker.is_file():
        raise ValueError(f"Job is not atomically ready: {resolved_target}")
    if marker.stat().st_size > 64 * 1024:
        raise ValueError(f"Ready marker is too large: {marker}")
    try:
        ready = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Ready marker is malformed: {marker}") from exc
    if (
        not isinstance(ready, dict)
        or ready.get("schema") != CAPTURE_SCHEMA
        or ready.get("codice_doc") != resolved_target.name
    ):
        raise ValueError(f"Ready marker does not identify this capture job: {marker}")
    manifest = resolved_target / "manifest.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError(f"Capture manifest is missing or unsafe: {manifest}")
    expected_manifest_hash = ready.get("manifest_sha256")
    if not isinstance(expected_manifest_hash, str) or sha256_file(manifest) != expected_manifest_hash:
        raise ValueError(f"Ready marker manifest hash does not match: {marker}")
    for child in resolved_target.iterdir():
        if not child.name.endswith(".partial"):
            continue
        if _PARSER_STAGING_NAME.fullmatch(child.name):
            if child.is_symlink() or not child.is_dir():
                raise ValueError(f"Unsafe parser staging artifact: {child}")
            continue
        raise ValueError(f"Ready job still contains a partial artifact: {child}")
    return resolved_target


def _capture_snapshot(loaded: LoadedSpoolJob) -> dict[str, str]:
    files = loaded.manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("capture manifest files map is malformed")
    names: list[str] = ["manifest.json", ".ready"]
    for key in ("request_raw", "response_raw", "timeline"):
        name = files.get(key)
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError(f"capture manifest has an unsafe {key} name")
        names.append(name)
    snapshot: dict[str, str] = {}
    job_root = loaded.job_dir.resolve(strict=True)
    for name in names:
        path = loaded.job_dir / name
        if path.is_symlink() or not path.is_file() or path.resolve(strict=True).parent != job_root:
            raise ValueError(f"Missing or unsafe immutable capture artifact: {path}")
        snapshot[name] = sha256_file(path)
    return snapshot


def _backup_destination(job_dir: Path, *, now: datetime, timezone: str) -> Path:
    if now.tzinfo is None:
        raise ValueError("backup timestamp must be timezone-aware")
    local = now.astimezone(ZoneInfo(timezone))
    milliseconds = local.microsecond // 1000
    name = f"PHARSED.backup-{local:%Y-%m-%d_%H.%M.%S}.{milliseconds:03d}"
    if not _BACKUP_NAME.fullmatch(name):
        raise RuntimeError("internal backup naming error")
    return job_dir / name


def _validate_parser_paths(job_dir: Path, parsed_dir: Path, *, stale_lock_sec: float) -> None:
    processing = job_dir / ".processing"
    if processing.is_symlink():
        raise ValueError(f"Refusing symlink parser state: {processing}")
    if processing.exists():
        if not processing.is_file():
            raise ValueError(f"Parser state is not a regular file: {processing}")
        age = max(0.0, time.time() - processing.stat().st_mtime)
        if age < stale_lock_sec:
            raise RuntimeError(f"Job is currently marked as processing: {processing}")
    if parsed_dir.is_symlink():
        raise ValueError(f"Refusing symlink parser output: {parsed_dir}")
    if parsed_dir.exists() and not parsed_dir.is_dir():
        raise ValueError(f"Parser output is not a directory: {parsed_dir}")
    if parsed_dir.exists():
        for path in parsed_dir.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"Refusing symlink in parser output: {path}")
    parsed_marker = job_dir / ".parsed"
    if parsed_marker.is_symlink():
        raise ValueError(f"Refusing symlink parser state: {parsed_marker}")
    if parsed_marker.exists() and not parsed_marker.is_file():
        raise ValueError(f"Parser state is not a regular file: {parsed_marker}")


def _invalidate_parsed_commit(job_dir: Path) -> None:
    """Remove the acceptance marker before moving its referenced outputs."""

    marker = job_dir / ".parsed"
    if marker.is_symlink():
        raise ValueError(f"Refusing symlink parser state: {marker}")
    try:
        marker.unlink()
    except FileNotFoundError:
        return
    fsync_directory(job_dir)


def _load_process_job() -> Callable[..., object]:
    """Resolve the parser lazily so dry-run remains dependency-free."""
    try:
        from commercialrchproxy.parser.worker import process_job
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError("parser worker API is unavailable in this installation") from exc
    if not callable(process_job):
        raise RuntimeError("parser worker process_job API is not callable")
    return process_job


def reparse_ready_job(
    config: Config,
    job_dir: Path,
    *,
    dry_run: bool = False,
    backup_existing: bool = False,
    code_filter: str | None = None,
    now: datetime | None = None,
) -> ReparseResult:
    """Validate and reprocess one ready job without touching capture evidence.

    The parser API contract is ``process_job(config, job_dir, force=True)``.
    ``force`` may replace parser state and ``PHARSED`` only; request/response
    RAW, timeline, manifest, and ``.ready`` remain immutable.
    """
    selected = _contained_ready_job(config, Path(job_dir))
    if code_filter is not None:
        expected = validate_job_code(code_filter, config.job_code_width)
        if selected.name != expected:
            raise ValueError(f"CODICE_DOC filter {expected} does not match target {selected.name}")
    else:
        validate_job_code(selected.name, config.job_code_width)

    loaded = load_spool_job(selected, max_bytes=config.max_payload_bytes)
    immutable_before = _capture_snapshot(loaded)
    parsed_dir = selected / config.pharsed_dirname
    _validate_parser_paths(selected, parsed_dir, stale_lock_sec=config.parser_stale_lock_sec)
    if parsed_dir.exists() and not backup_existing:
        raise FileExistsError(f"Refusing to overwrite existing {config.pharsed_dirname}; use --backup-existing")

    backup_path: Path | None = None
    if parsed_dir.exists():
        backup_path = _backup_destination(
            selected,
            now=now or datetime.now(ZoneInfo(config.timezone)),
            timezone=config.timezone,
        )
        if backup_path.exists() or backup_path.is_symlink():
            raise FileExistsError(f"Refusing to overwrite parser backup: {backup_path}")

    if dry_run:
        return ReparseResult(selected, selected.name, True, backup_path, None)

    # Resolve the callable before moving the existing output.  An incomplete
    # installation therefore fails without changing the job directory.
    process_job = _load_process_job()
    if backup_path is not None:
        # Coordinate check-and-rename with the worker's own claim lock.  The
        # lock is released before process_job because that API acquires it
        # internally while creating its processing marker.
        with FileLock(selected / ".parser.lock", timeout=5.0):
            _validate_parser_paths(selected, parsed_dir, stale_lock_sec=config.parser_stale_lock_sec)
            if backup_path.exists() or backup_path.is_symlink():
                raise FileExistsError(f"Refusing to overwrite parser backup: {backup_path}")
            # A crash after this point must never leave an accepted .parsed
            # marker pointing at the PHARSED directory that is about to move.
            _invalidate_parsed_commit(selected)
            os.rename(parsed_dir, backup_path)
            fsync_directory(selected)
    try:
        parser_result = process_job(config, selected, force=True)
    finally:
        reloaded = load_spool_job(selected, max_bytes=config.max_payload_bytes)
        immutable_after = _capture_snapshot(reloaded)
        if immutable_after != immutable_before:
            raise RuntimeError("parser modified immutable capture evidence")
    return ReparseResult(selected, selected.name, False, backup_path, parser_result)


def _jsonable(value: object) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _parser_result_status(value: object | None) -> str | None:
    if isinstance(value, dict):
        status = value.get("status")
    else:
        status = getattr(value, "status", None)
    return status if isinstance(status, str) else None


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reparse one immutable, ready RAW spool job")
    parser.add_argument("job_dir", type=Path, help="ready CODICE_DOC job directory")
    parser.add_argument("--config", type=Path, help="shared commercialRCHproxy configuration")
    parser.add_argument("--code", help="optional CODICE_DOC safety filter")
    parser.add_argument("--dry-run", action="store_true", help="validate and report without changing files")
    parser.add_argument(
        "--backup-existing",
        action="store_true",
        help="rename an existing PHARSED directory to a human-timestamped backup",
    )
    parser.add_argument("--json", action="store_true", help="print a machine-readable result")
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def cli(argv: list[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    try:
        config = Config.load(args.config)
        result = reparse_ready_job(
            config,
            args.job_dir,
            dry_run=args.dry_run,
            backup_existing=args.backup_existing,
            code_filter=args.code,
        )
    except (ConfigError, OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    payload = _jsonable(result)
    parser_status = _parser_result_status(result.parser_result)
    if not result.dry_run and parser_status != "parsed":
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        print(f"ERROR: parser did not commit the reparse (status={parser_status!r})", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        action = "validated (dry-run)" if result.dry_run else "reparsed"
        print(f"Job {result.code} {action}: {result.job_dir}")
        if result.backup_path is not None:
            verb = "would back up to" if result.dry_run else "backed up to"
            print(f"Existing {config.pharsed_dirname} {verb}: {result.backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
