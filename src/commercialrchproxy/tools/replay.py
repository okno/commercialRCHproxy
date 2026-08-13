"""Import directional RAW files into the persistent spool without networking.

This command deliberately does not replay bytes to a printer.  It creates a
synthetic :class:`~commercialrchproxy.capture.jobs.CapturedJob` and publishes
it through the same ``RawSpoolStorage`` path used by the dumper.  The normal
parser service can consequently process the ready job later.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from commercialrchproxy import __version__
from commercialrchproxy.capture.jobs import CLIENT_TO_RCH, RCH_TO_CLIENT, CapturedJob
from commercialrchproxy.config import Config, ConfigError
from commercialrchproxy.storage.spool import RawSpoolStorage, SpoolArchiveResult


def _read_regular_file(path: Path, *, maximum: int) -> bytes:
    """Read one bounded regular file without following a final symlink."""
    if maximum < 0:
        raise ValueError("input byte limit cannot be negative")
    if path.is_symlink():
        raise ValueError(f"Refusing symlink input: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"Cannot open RAW input {path}: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"RAW input is not a regular file: {path}")
        if before.st_size > maximum:
            raise ValueError(f"RAW input {path} exceeds the remaining {maximum}-byte limit")
        chunks: list[bytes] = []
        total = 0
        while True:
            block = os.read(descriptor, min(1024 * 1024, maximum - total + 1))
            if not block:
                break
            total += len(block)
            if total > maximum:
                raise ValueError(f"RAW input {path} grew beyond the {maximum}-byte limit")
            chunks.append(block)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino) or before.st_size != after.st_size:
            raise ValueError(f"RAW input changed while it was being read: {path}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def replay_raw_to_spool(
    config: Config,
    request_path: Path,
    response_path: Path | None = None,
    *,
    job_code: str | None = None,
    started_at: datetime | None = None,
    started_unix_ns: int | None = None,
) -> SpoolArchiveResult:
    """Publish supplied RAW streams as one offline job.

    No socket or relay component is imported or called.  The capture manifest
    explicitly records that no delivery was attempted.
    """
    request_path = Path(request_path)
    response_path = Path(response_path) if response_path is not None else None
    if response_path is not None:
        try:
            if request_path.resolve(strict=True) == response_path.resolve(strict=True):
                raise ValueError("request and response RAW inputs must be different files")
        except OSError as exc:
            raise ValueError(f"Cannot resolve RAW input: {exc}") from exc

    request = _read_regular_file(request_path, maximum=config.max_payload_bytes)
    if not request:
        raise ValueError("request RAW input must not be empty")
    remaining = config.max_payload_bytes - len(request)
    response = b"" if response_path is None else _read_regular_file(response_path, maximum=remaining)

    captured_at = started_at or datetime.now(UTC)
    if captured_at.tzinfo is None:
        raise ValueError("started_at must be timezone-aware")
    captured_at = captured_at.astimezone(UTC)
    capture_ns = time.time_ns() if started_unix_ns is None else started_unix_ns
    if capture_ns < 0:
        raise ValueError("started_unix_ns cannot be negative")
    identity = hashlib.sha256(request + b"\x00RCH-OFFLINE-DIRECTION\x00" + response).hexdigest()[:32]
    job = CapturedJob(
        session_id=f"offline-{identity}",
        connection_id=f"offline-{identity}",
        client_ip="127.0.0.1",
        client_port=None,
        proxy_ip=config.listen_ip,
        proxy_port=config.listen_port,
        printer_ip=config.printer_ip,
        printer_port=config.printer_port,
        max_payload_bytes=config.max_payload_bytes,
        started_at=captured_at,
        started_unix_ns=capture_ns,
        boundary_source="offline_supplied_directional_files",
        boundary_confidence=1.0,
        transport_status="offline_replay_no_network_delivery",
    )
    job.append(
        CLIENT_TO_RCH,
        request,
        timestamp=captured_at.isoformat(),
        received_unix_ns=capture_ns,
        forwarded_unix_ns=None,
    )
    if response:
        job.append(
            RCH_TO_CLIENT,
            response,
            timestamp=captured_at.isoformat(),
            received_unix_ns=capture_ns + 1,
            forwarded_unix_ns=None,
        )
    job.finish("offline_replay_no_network_delivery")
    return RawSpoolStorage(config).archive(job, job_code=job_code)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import RAW streams into the parser spool; never connect to a printer")
    parser.add_argument("request", type=Path, help="client-to-printer RAW file")
    parser.add_argument("--response", type=Path, help="optional printer-to-client RAW file")
    parser.add_argument("--config", type=Path, help="shared commercialRCHproxy configuration")
    parser.add_argument("--code", help="optional explicit CODICE_DOC (four or more decimal digits)")
    parser.add_argument("--json", action="store_true", help="print a machine-readable result")
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def cli(argv: list[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    try:
        config = Config.load(args.config)
        result = replay_raw_to_spool(
            config,
            args.request,
            args.response,
            job_code=args.code,
        )
    except (ConfigError, OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    payload = {
        "code": result.code,
        "job_dir": str(result.job_dir),
        "network_activity": False,
        "status": result.status,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Offline job {result.code} published: {result.job_dir}")
        print("Network activity: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
