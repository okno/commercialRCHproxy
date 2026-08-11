"""Small in-process counters exposed through structured logs and health checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock


@dataclass(slots=True)
class Metrics:
    sessions_total: int = 0
    jobs_total: int = 0
    jobs_completed: int = 0
    jobs_failed: int = 0
    bytes_to_rch: int = 0
    bytes_from_rch: int = 0
    printer_connect_errors: int = 0
    parser_errors: int = 0
    render_errors: int = 0
    _lock: Lock = field(default_factory=Lock, repr=False)

    def increment(self, name: str, amount: int = 1) -> None:
        if name.startswith("_") or not hasattr(self, name):
            raise KeyError(name)
        with self._lock:
            setattr(self, name, int(getattr(self, name)) + amount)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                name: int(getattr(self, name))
                for name in (
                    "sessions_total",
                    "jobs_total",
                    "jobs_completed",
                    "jobs_failed",
                    "bytes_to_rch",
                    "bytes_from_rch",
                    "printer_connect_errors",
                    "parser_errors",
                    "render_errors",
                )
            }
