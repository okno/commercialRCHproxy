from __future__ import annotations

import asyncio
import json
import logging
import socket
from contextlib import closing
from pathlib import Path

from commercialrchproxy.config import Config


def unused_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def make_config(tmp_path: Path, printer_port: int, listen_port: int, **overrides: object) -> Config:
    values: dict[str, object] = {
        "listen_ip": "127.0.0.1",
        "listen_port": listen_port,
        "printer_ip": "127.0.0.1",
        "printer_port": printer_port,
        "output_dir": tmp_path / "jobs",
        "log_dir": tmp_path / "logs",
        "connection_timeout_sec": 1.0,
        "response_timeout_sec": 0.5,
        "job_idle_timeout_ms": 50,
        "save_pdf": False,
        "shutdown_grace_sec": 1.0,
    }
    values.update(overrides)
    return Config(**values)  # type: ignore[arg-type]


def null_logger() -> logging.Logger:
    logger = logging.getLogger(f"commercialrchproxy.tests.{id(object())}")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    return logger


async def wait_for_manifests(root: Path, count: int, timeout: float = 3.0) -> list[Path]:
    def ready_manifests() -> list[Path]:
        if not root.exists():
            return []
        return sorted(
            path
            for path in root.rglob("manifest.json")
            if path.parent.name.isdecimal() and (path.parent / ".ready").is_file()
        )

    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        found = ready_manifests()
        if len(found) >= count:
            return found
        await asyncio.sleep(0.02)
    return ready_manifests()


def load_manifest(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
