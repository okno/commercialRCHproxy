"""Persistent, per-printer CODICE_DOC allocation."""

from __future__ import annotations

import re
from pathlib import Path

from commercialrchproxy.storage.atomic import atomic_write_bytes, ensure_directory
from commercialrchproxy.storage.locking import FileLock

_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9_.-]")
_CODE = re.compile(r"[0-9]{4,32}")


def printer_component(printer_ip: str) -> str:
    value = _SAFE_COMPONENT.sub("_", printer_ip)
    if not value or value in {".", ".."}:
        raise ValueError("printer identifier cannot form a safe path component")
    return value


def validate_job_code(value: str, width: int = 4) -> str:
    if not _CODE.fullmatch(value) or len(value) < width:
        raise ValueError(f"CODICE_DOC must contain at least {width} decimal digits")
    return value


class JobCodeAllocator:
    def __init__(
        self,
        root: Path,
        *,
        start: int = 1,
        width: int = 4,
        file_mode: int = 0o640,
        directory_mode: int = 0o750,
    ) -> None:
        self.root = root
        self.start = start
        self.width = width
        self.file_mode = file_mode
        self.directory_mode = directory_mode

    def allocate(self, printer_ip: str) -> str:
        state = self.root / ".state" / printer_component(printer_ip)
        ensure_directory(state, self.directory_mode)
        counter_path = state / "next-code"
        lock_path = state / "next-code.lock"
        with FileLock(lock_path):
            if counter_path.exists():
                if counter_path.is_symlink() or not counter_path.is_file():
                    raise RuntimeError(f"Unsafe CODICE_DOC counter: {counter_path}")
                raw = counter_path.read_text(encoding="ascii").strip()
                if not raw.isdecimal():
                    raise RuntimeError(f"Corrupt CODICE_DOC counter: {counter_path}")
                current = int(raw, 10)
            else:
                current = self.start
            if current < 0:
                raise RuntimeError("CODICE_DOC counter cannot be negative")
            code = f"{current:0{self.width}d}"
            validate_job_code(code, self.width)
            atomic_write_bytes(
                counter_path,
                f"{current + 1}\n".encode("ascii"),
                mode=self.file_mode,
                directory_mode=self.directory_mode,
            )
            return code
