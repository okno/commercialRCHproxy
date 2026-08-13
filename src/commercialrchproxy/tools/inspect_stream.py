"""Inspect captured RCH directional streams and reconstruct readable copies."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from commercialrchproxy import __version__
from commercialrchproxy.rch.receipt_parser import ParsedReceipt, ProtocolCopiesResult, parse_protocol_copies
from commercialrchproxy.storage.files import atomic_write_bytes

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")
_DEFAULT_MAX_INPUT_BYTES = 64 * 1024 * 1024
_DEFAULT_MAX_TOTAL_INPUT_BYTES = 256 * 1024 * 1024
_MAX_MANIFEST_BYTES = 1024 * 1024
_MAX_TOTAL_MANIFEST_BYTES = 64 * 1024 * 1024
_MAX_JSON_CANDIDATE_COUNT = 10000
_MAX_MANIFEST_COUNT = 10000
_MAX_SESSION_COUNT = 1024


@dataclass(slots=True)
class InspectionInput:
    session_id: str
    request: bytes = b""
    response: bytes = b""
    source_artifacts: list[dict[str, object]] = field(default_factory=list)
    timeline_text: str = ""
    timeline_bytes: int = 0
    warnings: list[str] = field(default_factory=list)
    client_ip: str | None = None
    client_port: int | None = None
    proxy_ip: str | None = None
    proxy_port: int | None = None
    printer_ip: str | None = None
    printer_port: int | None = None
    timestamp_start: str | None = None
    timestamp_end: str | None = None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest_files(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    found: list[tuple[Path, dict[str, Any]]] = []
    candidate_count = 0
    manifest_bytes = 0
    archive_root = root.resolve(strict=True)
    for path in root.rglob("*.json"):
        candidate_count += 1
        if candidate_count > _MAX_JSON_CANDIDATE_COUNT:
            raise ValueError(
                f"archive contains more than {_MAX_JSON_CANDIDATE_COUNT} JSON candidates"
            )
        if path.name.endswith(".parsed.json"):
            continue
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(archive_root)
        except (OSError, ValueError) as exc:
            raise ValueError(f"candidate manifest escapes or is unreadable: {path}") from exc
        if path.is_symlink() or not resolved.is_file():
            raise ValueError(f"candidate manifest is not a regular non-symlink file: {path}")
        size = resolved.stat().st_size
        if size > _MAX_MANIFEST_BYTES:
            raise ValueError(f"candidate manifest {path} is {size} bytes; limit is {_MAX_MANIFEST_BYTES}")
        try:
            raw_manifest = _read_bounded(resolved, _MAX_MANIFEST_BYTES)
        except OSError as exc:
            raise ValueError(f"candidate manifest is unreadable: {path}") from exc
        if manifest_bytes + len(raw_manifest) > _MAX_TOTAL_MANIFEST_BYTES:
            raise ValueError(
                f"candidate manifests exceed the {_MAX_TOTAL_MANIFEST_BYTES}-byte aggregate limit"
            )
        manifest_bytes += len(raw_manifest)
        try:
            value = json.loads(raw_manifest.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(value, dict):
            continue
        if value.get("project") == "commercialRCHproxy" and value.get("session_id"):
            found.append((path, value))
            if len(found) > _MAX_MANIFEST_COUNT:
                raise ValueError(f"archive contains more than {_MAX_MANIFEST_COUNT} candidate manifests")
    return sorted(
        found,
        key=lambda item: (
            (
                item[1].get("timestamp_start", item[1].get("opened_at"))
                if isinstance(item[1].get("timestamp_start", item[1].get("opened_at")), str)
                else ""
            ),
            str(item[0]),
        ),
    )


def _contained_artifact_path(manifest_path: Path, name: object, warnings: list[str]) -> Path | None:
    if not isinstance(name, str) or not name or "\x00" in name:
        warnings.append(f"invalid artifact name in {manifest_path}")
        return None
    base = manifest_path.parent.resolve()
    candidate = manifest_path.parent / name
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(base)
    except (OSError, ValueError):
        warnings.append(f"artifact path escapes or is missing from manifest directory: {name!r}")
        return None
    if candidate.is_symlink() or not resolved.is_file():
        warnings.append(f"artifact is not a regular non-symlink file: {name!r}")
        return None
    return resolved


def _read_bounded(path: Path, max_bytes: int) -> bytes:
    size = path.stat().st_size
    if size > max_bytes:
        raise ValueError(f"input {path} is {size} bytes; limit is {max_bytes}")
    data = path.read_bytes()
    if len(data) > max_bytes:
        raise ValueError(f"input {path} grew beyond the {max_bytes}-byte limit while reading")
    return data


def _read_manifest_artifact(
    manifest_path: Path,
    manifest: dict[str, Any],
    key: str,
    expected_hash: object,
    warnings: list[str],
    max_bytes: int,
) -> bytes:
    files = manifest.get("files")
    if not isinstance(files, dict):
        warnings.append(f"manifest {manifest_path} has no valid files object")
        return b""
    name = files.get(key)
    if not name:
        return b""
    path = _contained_artifact_path(manifest_path, name, warnings)
    if path is None:
        return b""
    try:
        data = _read_bounded(path, max_bytes)
    except OSError as exc:
        warnings.append(f"cannot read {path}: {exc}")
        return b""
    if expected_hash and _sha256(data) != expected_hash:
        warnings.append(f"SHA-256 mismatch for {path}")
    return data


def _capture_artifact_spec(manifest: dict[str, Any], direction: str) -> tuple[str, object]:
    """Return the file-map key and expected digest for legacy or spool-v1 manifests."""

    if manifest.get("schema") == "commercialrchproxy.capture.v1":
        key = "request_raw" if direction == "request" else "response_raw"
        hashes = manifest.get("sha256")
        expected = hashes.get(key) if isinstance(hashes, dict) else None
        return key, expected
    if direction == "request":
        return "raw", manifest.get("raw_sha256")
    return "response_raw", manifest.get("response_raw_sha256")


def load_archive_directory(
    root: Path,
    *,
    max_input_bytes: int = _DEFAULT_MAX_INPUT_BYTES,
    max_total_input_bytes: int = _DEFAULT_MAX_TOTAL_INPUT_BYTES,
) -> list[InspectionInput]:
    """Group legacy fallback segments by connection ``session_id``."""
    if max_input_bytes < 1 or max_total_input_bytes < 1:
        raise ValueError("archive input limits must be positive")
    groups: dict[str, InspectionInput] = {}
    request_parts: dict[str, list[bytes]] = {}
    response_parts: dict[str, list[bytes]] = {}
    timeline_parts: dict[str, list[str]] = {}
    request_bytes: dict[str, int] = {}
    response_bytes: dict[str, int] = {}
    seen_start_times: dict[str, set[str]] = {}
    timeline_omitted: set[str] = set()
    total_input_bytes = 0
    for manifest_path, manifest in _manifest_files(root):
        session_id = str(manifest["session_id"])
        current = groups.get(session_id)
        if current is None:
            if len(groups) >= _MAX_SESSION_COUNT:
                raise ValueError(f"archive contains more than {_MAX_SESSION_COUNT} sessions")
            current = InspectionInput(session_id=session_id)
            groups[session_id] = current
            request_parts[session_id] = []
            response_parts[session_id] = []
            timeline_parts[session_id] = []
            request_bytes[session_id] = 0
            response_bytes[session_id] = 0
            seen_start_times[session_id] = set()
        endpoint_fields = (
            "client_ip",
            "client_port",
            "proxy_ip",
            "proxy_port",
            "printer_ip",
            "printer_port",
        )
        for field_name in endpoint_fields:
            manifest_name = {
                "proxy_ip": "listen_ip",
                "proxy_port": "listen_port",
            }.get(field_name, field_name)
            observed = manifest.get(field_name, manifest.get(manifest_name))
            existing = getattr(current, field_name)
            if existing is None:
                setattr(current, field_name, observed)
            elif observed is not None and existing != observed:
                current.warnings.append(
                    f"inconsistent {field_name} across session manifests: {existing!r} != {observed!r}"
                )
        started = manifest.get("timestamp_start", manifest.get("opened_at"))
        ended = manifest.get("timestamp_end", manifest.get("closed_at"))
        if not isinstance(started, str) or not started:
            current.warnings.append(
                f"manifest {manifest_path} has no valid timestamp_start; segment order may be ambiguous"
            )
        else:
            if started in seen_start_times[session_id]:
                current.warnings.append(
                    f"duplicate timestamp_start {started!r} in session; path order used as a tie-breaker"
                )
            seen_start_times[session_id].add(started)
            if current.timestamp_start is None or started < current.timestamp_start:
                current.timestamp_start = started
        if isinstance(ended, str) and (current.timestamp_end is None or ended > current.timestamp_end):
            current.timestamp_end = ended
        request_key, request_hash = _capture_artifact_spec(manifest, "request")
        response_key, response_hash = _capture_artifact_spec(manifest, "response")
        request = _read_manifest_artifact(
            manifest_path,
            manifest,
            request_key,
            request_hash,
            current.warnings,
            max_input_bytes,
        )
        response = _read_manifest_artifact(
            manifest_path,
            manifest,
            response_key,
            response_hash,
            current.warnings,
            max_input_bytes,
        )
        if request_bytes[session_id] + len(request) > max_input_bytes:
            raise ValueError(f"grouped request session {session_id!r} exceeds {max_input_bytes} bytes")
        if response_bytes[session_id] + len(response) > max_input_bytes:
            raise ValueError(f"grouped response session {session_id!r} exceeds {max_input_bytes} bytes")
        directional_bytes = len(request) + len(response)
        if total_input_bytes + directional_bytes > max_total_input_bytes:
            raise ValueError(
                f"archive input exceeds the {max_total_input_bytes}-byte global aggregate limit"
            )
        total_input_bytes += directional_bytes
        request_parts[session_id].append(request)
        response_parts[session_id].append(response)
        request_bytes[session_id] += len(request)
        response_bytes[session_id] += len(response)
        files = manifest.get("files")
        timeline_name = (
            files.get("timeline") or files.get("timeline_jsonl")
            if isinstance(files, dict)
            else None
        )
        technical_name = files.get("technical_txt") if isinstance(files, dict) else None
        event_log_name = timeline_name or technical_name
        if event_log_name:
            event_log_path = _contained_artifact_path(manifest_path, event_log_name, current.warnings)
        else:
            event_log_path = None
        if event_log_path is not None and session_id not in timeline_omitted:
            try:
                event_log = _read_bounded(event_log_path, max_input_bytes).decode("utf-8")
            except (OSError, UnicodeError, ValueError) as exc:
                current.warnings.append(f"cannot read {event_log_path}: {exc}")
            else:
                section = f"[SOURCE {event_log_path.name}]\n{event_log.rstrip()}\n\n"
                section_bytes = len(section.encode("utf-8"))
                if current.timeline_bytes + section_bytes > max_input_bytes:
                    current.warnings.append(
                        f"event-log aggregation exceeded {max_input_bytes} bytes; later timeline sections omitted"
                    )
                    timeline_omitted.add(session_id)
                else:
                    if total_input_bytes + section_bytes > max_total_input_bytes:
                        raise ValueError(
                            f"archive input exceeds the {max_total_input_bytes}-byte global aggregate limit"
                        )
                    total_input_bytes += section_bytes
                    timeline_parts[session_id].append(section)
                    current.timeline_bytes += section_bytes
        if manifest.get("raw_complete") is False:
            detail = manifest.get("capture_error") or "capture manifest reports an incomplete RAW copy"
            current.warnings.append(f"incomplete RAW segment {manifest_path}: {detail}")
        if manifest.get("timeline_complete") is False:
            detail = manifest.get("timeline_error") or "capture manifest reports an incomplete timeline"
            current.warnings.append(f"incomplete timeline segment {manifest_path}: {detail}")
        elif manifest.get("timeline_error"):
            current.warnings.append(
                f"timeline error reported by {manifest_path}: {manifest['timeline_error']}"
            )
        current.source_artifacts.append(
            {
                "manifest": str(manifest_path),
                "job_id": manifest.get("job_id"),
                "timestamp_start": started,
                "timestamp_end": ended,
                "request_bytes": len(request),
                "response_bytes": len(response),
                "client_ip": manifest.get("client_ip"),
                "client_port": manifest.get("client_port"),
                "proxy_ip": manifest.get("proxy_ip", manifest.get("listen_ip")),
                "proxy_port": manifest.get("proxy_port", manifest.get("listen_port")),
                "printer_ip": manifest.get("printer_ip"),
                "printer_port": manifest.get("printer_port"),
            }
        )
    for session_id, current in groups.items():
        current.request = b"".join(request_parts[session_id])
        current.response = b"".join(response_parts[session_id])
        current.timeline_text = "".join(timeline_parts[session_id])
    return list(groups.values())


def _auto_response_path(request_path: Path) -> Path | None:
    if request_path.name.endswith(".raw") and not request_path.name.endswith(".response.raw"):
        candidate = request_path.with_name(f"{request_path.name[:-4]}.response.raw")
        return candidate if candidate.is_file() else None
    if request_path.suffix == ".bin":
        candidate = request_path.with_name(f"{request_path.stem}.response.bin")
        return candidate if candidate.is_file() else None
    return None


def load_direct_files(
    request_paths: list[Path],
    response_paths: list[Path],
    *,
    max_input_bytes: int = _DEFAULT_MAX_INPUT_BYTES,
    max_total_input_bytes: int = _DEFAULT_MAX_TOTAL_INPUT_BYTES,
) -> InspectionInput:
    if max_input_bytes < 1 or max_total_input_bytes < 1:
        raise ValueError("direct input limits must be positive")
    result = InspectionInput(session_id="offline-input")
    request_parts: list[bytes] = []
    response_parts: list[bytes] = []
    request_bytes = 0
    response_bytes = 0
    for path in request_paths:
        data = _read_bounded(path, max_input_bytes)
        if request_bytes + len(data) > max_input_bytes:
            raise ValueError(f"combined request input exceeds {max_input_bytes} bytes")
        if request_bytes + response_bytes + len(data) > max_total_input_bytes:
            raise ValueError(f"direct input exceeds the {max_total_input_bytes}-byte global aggregate limit")
        request_parts.append(data)
        request_bytes += len(data)
        result.source_artifacts.append(
            {"direction": "request", "path": str(path), "byte_count": len(data), "sha256": _sha256(data)}
        )
    selected_responses = response_paths
    if not selected_responses:
        selected_responses = [candidate for path in request_paths if (candidate := _auto_response_path(path))]
    for path in selected_responses:
        data = _read_bounded(path, max_input_bytes)
        if response_bytes + len(data) > max_input_bytes:
            raise ValueError(f"combined response input exceeds {max_input_bytes} bytes")
        if request_bytes + response_bytes + len(data) > max_total_input_bytes:
            raise ValueError(f"direct input exceeds the {max_total_input_bytes}-byte global aggregate limit")
        response_parts.append(data)
        response_bytes += len(data)
        result.source_artifacts.append(
            {"direction": "response", "path": str(path), "byte_count": len(data), "sha256": _sha256(data)}
        )
    if request_bytes + response_bytes > max_total_input_bytes:
        raise ValueError(f"direct input exceeds the {max_total_input_bytes}-byte global aggregate limit")
    result.request = b"".join(request_parts)
    result.response = b"".join(response_parts)
    identity_hash = hashlib.sha256()
    identity_hash.update(result.request)
    identity_hash.update(b"\x00RCH-DIRECTION\x00")
    identity_hash.update(result.response)
    identity = identity_hash.hexdigest()[:32]
    result.session_id = f"offline-{identity}"
    return result


def _encoding_summary(data: bytes) -> str:
    if not data:
        return "empty"
    if all(byte < 128 for byte in data):
        return "7-bit ASCII plus control bytes (observed)"
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return "binary/non-UTF-8; Latin-1 is available only as a lossless byte view"
    return "valid UTF-8 bytes; protocol semantics remain unconfirmed"


def _hexdump(data: bytes, limit: int) -> str:
    lines: list[str] = []
    shown = data[:limit]
    for offset in range(0, len(shown), 16):
        block = shown[offset : offset + 16]
        hex_part = " ".join(f"{byte:02x}" for byte in block)
        ascii_part = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in block)
        lines.append(f"{offset:08x}  {hex_part:<47}  |{ascii_part}|")
    if len(data) > limit:
        lines.append(f"...[{len(data) - limit} bytes not shown]")
    return "\n".join(lines)


def _session_summary(source: InspectionInput, parsed: ProtocolCopiesResult) -> dict[str, object]:
    return {
        "session_id": source.session_id,
        "request": {
            "size": len(source.request),
            "sha256": _sha256(source.request),
            "encoding": _encoding_summary(source.request),
            "frames": len(parsed.request_framing.frames),
        },
        "response": {
            "size": len(source.response),
            "sha256": _sha256(source.response) if source.response else None,
            "encoding": _encoding_summary(source.response),
            "frames": len(parsed.response_framing.frames),
            "acks": len(parsed.response_framing.acks),
        },
        "documents": [
            {
                "document_id": document.document_id,
                "document_type": document.document_type,
                "printed_class": document.printed_class,
                "complete": document.complete,
                "evidence": document.evidence,
            }
            for document in parsed.documents
        ],
        "message_count": len(parsed.messages),
        "correlation_count": len(parsed.correlations),
        "issue_count": len(parsed.issues),
        "warnings": [*source.warnings, *(f"{issue.code}: {issue.detail}" for issue in parsed.issues)],
        "source_artifacts": source.source_artifacts,
    }


def _safe_component(value: str) -> str:
    return _SAFE_NAME.sub("_", value).strip("._") or "unknown"


def _document_output(
    root: Path,
    source: InspectionInput,
    parsed: ProtocolCopiesResult,
    document: ParsedReceipt,
) -> Path:
    source_identity_hash = hashlib.sha256()
    source_identity_hash.update(source.session_id.encode("utf-8", errors="replace"))
    source_identity_hash.update(b"\x00")
    source_identity_hash.update(source.request)
    source_identity_hash.update(b"\x00")
    source_identity_hash.update(source.response)
    source_identity = source_identity_hash.hexdigest()[:16]
    session_component = _safe_component(source.session_id)[:48]
    directory = root / f"{session_component}-{source_identity}_{_safe_component(document.document_id)}"
    root.mkdir(mode=0o750, parents=True, exist_ok=True)
    directory.mkdir(mode=0o750, exist_ok=False)
    event_log = source.timeline_text or (
        f"request bytes={len(source.request)} sha256={_sha256(source.request)}\n"
        f"response bytes={len(source.response)} sha256={_sha256(source.response) if source.response else 'none'}\n"
    )
    receipt_bytes = document.receipt_text.encode("utf-8")
    metadata = {
        "schema": "commercialrchproxy.reconstruction-metadata.v1",
        "parser_version": __version__,
        "session_id": source.session_id,
        "connection_id": source.session_id,
        "document_id": document.document_id,
        "document_type": document.document_type,
        "document_type_evidence": document.evidence,
        "complete": document.complete,
        "raw_scope": "full_directional_session_copy",
        "raw_bin_scope": "client_to_printer_compatibility_alias",
        "request_sha256": _sha256(source.request),
        "response_sha256": _sha256(source.response) if source.response else None,
        "receipt_sha256": _sha256(receipt_bytes),
        "raw_event_log_sha256": _sha256(event_log.encode("utf-8")),
        "byte_count_client": len(source.request),
        "byte_count_printer": len(source.response),
        "timestamp_start": source.timestamp_start,
        "timestamp_end": source.timestamp_end,
        "source_ip": source.client_ip,
        "source_port": source.client_port,
        "proxy_ip": source.proxy_ip,
        "proxy_port": source.proxy_port,
        "destination_ip": source.printer_ip,
        "destination_port": source.printer_port,
        "source_artifacts": source.source_artifacts,
        "source_frame_ids": list(document.frame_ids),
        "source_start_offset": document.start_offset,
        "source_end_offset": document.end_offset,
        "warnings": source.warnings,
        "application_success": None,
    }
    parsed_document = {
        "schema": "commercialrchproxy.parsed-document.v1",
        "parser_version": __version__,
        "document": document.to_dict(),
        "correlations": [correlation.to_dict() for correlation in parsed.correlations],
        "protocol_issues": [issue.to_dict() for issue in parsed.issues],
    }
    parsed_bytes = (json.dumps(parsed_document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    metadata["parsed_sha256"] = _sha256(parsed_bytes)
    atomic_write_bytes(directory / "raw_client_to_printer.bin", source.request)
    atomic_write_bytes(directory / "raw.bin", source.request)
    atomic_write_bytes(directory / "raw_printer_to_client.bin", source.response)
    atomic_write_bytes(directory / "receipt.txt", receipt_bytes)
    atomic_write_bytes(directory / "parsed.json", parsed_bytes)
    atomic_write_bytes(directory / "raw_event_log.txt", event_log.encode("utf-8"))
    atomic_write_bytes(
        directory / "metadata.json",
        (json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return directory


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and reconstruct captured RCH directional streams")
    parser.add_argument("paths", nargs="+", type=Path, help="request RAW file(s), or one archive directory")
    parser.add_argument("--response", action="append", default=[], type=Path, help="response stream file; repeatable")
    parser.add_argument("--hex", action="store_true", help="show a bounded request/response hexdump")
    parser.add_argument("--ascii", action="store_true", help="show the lossless Latin-1 data view for parsed frames")
    parser.add_argument("--xml", action="store_true", help="report whether an XML declaration is present")
    parser.add_argument("--timeline", action="store_true", help="list source segment chronology")
    parser.add_argument("--json", action="store_true", help="write full machine-readable analysis to stdout")
    parser.add_argument("--receipt", action="store_true", help="write reconstructed receipt text to stdout")
    parser.add_argument("--output-dir", type=Path, help="write one forensic reconstruction directory per document")
    parser.add_argument("--max-display-bytes", type=int, default=4096, help="hexdump display cap (default: 4096)")
    parser.add_argument(
        "--max-input-bytes",
        type=int,
        default=_DEFAULT_MAX_INPUT_BYTES,
        help=f"per-direction analysis cap (default: {_DEFAULT_MAX_INPUT_BYTES})",
    )
    parser.add_argument(
        "--max-total-input-bytes",
        type=int,
        default=_DEFAULT_MAX_TOTAL_INPUT_BYTES,
        help=f"global aggregate analysis cap (default: {_DEFAULT_MAX_TOTAL_INPUT_BYTES})",
    )
    return parser


def _load_inputs(
    paths: list[Path],
    responses: list[Path],
    *,
    max_input_bytes: int,
    max_total_input_bytes: int,
) -> list[InspectionInput]:
    if len(paths) == 1 and paths[0].is_dir():
        if responses:
            raise ValueError("--response cannot be combined with an archive directory")
        return load_archive_directory(
            paths[0],
            max_input_bytes=max_input_bytes,
            max_total_input_bytes=max_total_input_bytes,
        )
    if any(path.is_dir() for path in paths):
        raise ValueError("a directory must be the only positional path")
    return [
        load_direct_files(
            paths,
            responses,
            max_input_bytes=max_input_bytes,
            max_total_input_bytes=max_total_input_bytes,
        )
    ]


def cli(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.max_display_bytes < 1:
        print("ERROR: --max-display-bytes must be positive", file=sys.stderr)
        return 2
    if args.max_input_bytes < 1:
        print("ERROR: --max-input-bytes must be positive", file=sys.stderr)
        return 2
    if args.max_total_input_bytes < 1:
        print("ERROR: --max-total-input-bytes must be positive", file=sys.stderr)
        return 2
    try:
        sources = _load_inputs(
            args.paths,
            args.response,
            max_input_bytes=args.max_input_bytes,
            max_total_input_bytes=args.max_total_input_bytes,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if not sources:
        print("ERROR: no commercialRCHproxy manifests or input streams found", file=sys.stderr)
        return 2

    analyses: list[tuple[InspectionInput, ProtocolCopiesResult]] = []
    output_paths: list[str] = []
    try:
        for source in sources:
            parsed = parse_protocol_copies(source.request, source.response)
            analyses.append((source, parsed))
            if args.output_dir:
                for document in parsed.documents:
                    output_paths.append(str(_document_output(args.output_dir, source, parsed, document)))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        payload = {
            "tool": "commercialrchproxy.tools.inspect_stream",
            "version": __version__,
            "sessions": [
                {"summary": _session_summary(source, parsed), "protocol": parsed.to_dict()}
                for source, parsed in analyses
            ],
            "output_paths": output_paths,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    for source, parsed in analyses:
        summary = _session_summary(source, parsed)
        print(f"Session: {source.session_id}")
        print(f"Request: {len(source.request)} bytes, SHA256 {_sha256(source.request)}")
        response_hash = _sha256(source.response) if source.response else "none"
        print(f"Response: {len(source.response)} bytes, SHA256 {response_hash}")
        framing_observed = bool(parsed.request_framing.frames) and all(
            frame.bcc_valid and frame.address == "00" and frame.frame_class == "z"
            for frame in parsed.request_framing.frames
        )
        protocol_label = "observed RCH framing" if framing_observed else "unrecognized/unknown"
        print(
            f"Protocol: {protocol_label}; "
            f"{len(parsed.request_framing.frames)} request frames, "
            f"{len(parsed.response_framing.frames)} response frames, "
            f"{len(parsed.response_framing.acks)} ACK"
        )
        print(f"Documents: {len(parsed.documents)}; issues: {len(parsed.issues)}")
        for document in parsed.documents:
            print(
                f"  {document.document_id}: {document.document_type}, "
                f"complete={str(document.complete).lower()}, evidence={document.evidence}"
            )
        if args.xml:
            print(f"XML declaration present: {str(b'<?xml' in source.request).lower()}")
        if args.timeline:
            for artifact in source.source_artifacts:
                print(f"  source: {artifact}")
        if args.ascii:
            for frame in parsed.request_framing.frames:
                print(f"  request frame {frame.frame_id} @{frame.stream_offset}: {frame.data_text!r}")
        if args.hex:
            print("[REQUEST HEX]")
            print(_hexdump(source.request, args.max_display_bytes))
            print("[RESPONSE HEX]")
            print(_hexdump(source.response, args.max_display_bytes))
        if args.receipt:
            for document in parsed.documents:
                print(document.receipt_text, end="" if document.receipt_text.endswith("\n") else "\n")
        for warning in summary["warnings"]:
            print(f"WARNING: {warning}")
        print()
    for path in output_paths:
        print(f"Output: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
