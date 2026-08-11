"""Wazuh-friendly structured logging without payloads by default."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return _CONTROL.sub("?", value.replace("\r", "\\r").replace("\n", "\\n"))[:4096]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _clean(str(value))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", "log"),
            "message": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(_clean(payload), ensure_ascii=False, separators=(",", ":"))


def configure_logging(log_dir: Path, level: str = "INFO") -> logging.Logger:
    if log_dir.exists() and log_dir.is_symlink():
        raise RuntimeError(f"Refusing symlink log directory: {log_dir}")
    log_dir.mkdir(mode=0o750, parents=True, exist_ok=True)
    if log_dir.is_symlink() or not log_dir.is_dir():
        raise RuntimeError(f"Unsafe log directory: {log_dir}")
    try:
        log_dir.chmod(0o750)
    except OSError:
        pass
    log_file = log_dir / "commercialrchproxy.jsonl"
    if not log_file.exists():
        fd = os.open(log_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        os.close(fd)
    elif log_file.is_symlink():
        raise RuntimeError(f"Refusing symlink log file: {log_file}")

    formatter = JsonFormatter()
    handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=7, encoding="utf-8")
    handler.setFormatter(formatter)
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)

    logger = logging.getLogger("commercialrchproxy")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(getattr(logging, level))
    logger.addHandler(handler)
    logger.addHandler(stream)
    return logger


def event(logger: logging.Logger, name: str, message: str, **fields: Any) -> None:
    logger.info(message, extra={"event": name, "fields": fields})
