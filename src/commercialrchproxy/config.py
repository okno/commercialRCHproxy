"""Strict configuration loading for commercialRCHproxy.

The protocol-facing port is intentionally configurable.  Nothing in this
module assigns protocol meaning to TCP port 23.
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, fields
from ipaddress import ip_address
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("/etc/commercialrchproxy/commercialrchproxy.conf")


class ConfigError(ValueError):
    """Raised for configuration that would be unsafe or ambiguous."""


def _parse_bool(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be true or false, got {value!r}")


def _parse_int(value: str, name: str, minimum: int, maximum: int) -> int:
    try:
        result = int(value, 10)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {value!r}") from exc
    if not minimum <= result <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}")
    return result


def _parse_float(value: str, name: str, minimum: float, maximum: float) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {value!r}") from exc
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}")
    return result


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse the deliberately small KEY=VALUE configuration format."""
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ConfigError(f"Cannot read configuration {path}: {exc}") from exc

    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"{path}:{line_number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not key.replace("_", "").isalnum() or key.upper() != key:
            raise ConfigError(f"{path}:{line_number}: invalid key {key!r}")
        if key in values:
            raise ConfigError(f"{path}:{line_number}: duplicate key {key}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


@dataclass(frozen=True, slots=True)
class Config:
    listen_ip: str = "192.0.2.231"
    listen_port: int = 23
    printer_ip: str = "192.0.2.251"
    printer_port: int = 23
    output_dir: Path = Path("/var/lib/commercialrchproxy/jobs")
    log_dir: Path = Path("/var/log/commercialrchproxy")
    connection_timeout_sec: float = 30.0
    response_timeout_sec: float = 10.0
    job_idle_timeout_ms: int = 1000
    save_raw: bool = True
    save_technical_txt: bool = True
    save_clean_txt: bool = True
    save_pdf: bool = True
    save_json: bool = True
    hash_algorithm: str = "sha256"
    debug: bool = False
    debug_hexdump: bool = False
    debug_pcap: bool = False
    retention_days: int = 0
    max_payload_bytes: int = 67_108_864
    renderer_paper_width_mm: float = 79.5
    renderer_characters_per_line: int = 48
    log_payload: bool = False
    log_level: str = "INFO"
    shutdown_grace_sec: float = 15.0

    @classmethod
    def load(
        cls,
        path: Path | str | None = None,
        environ: Mapping[str, str] | None = None,
        *,
        require_file: bool = True,
    ) -> Config:
        env = dict(os.environ if environ is None else environ)
        selected = Path(path or env.get("COMMERCIALRCHPROXY_CONFIG", DEFAULT_CONFIG_PATH))
        values: dict[str, str] = {}
        if selected.exists():
            values.update(parse_env_file(selected))
        elif require_file:
            raise ConfigError(f"Configuration file does not exist: {selected}")

        # Explicit process environment wins over the file, but only for known
        # application keys.  This is useful for containers and test fixtures.
        for key in _KEYS:
            if key in env:
                values[key] = env[key]
        return cls.from_mapping(values)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> Config:
        unknown = sorted(set(values) - _KEYS)
        if unknown:
            raise ConfigError(f"Unknown configuration key(s): {', '.join(unknown)}")

        def value(name: str, default: str) -> str:
            return str(values.get(name, default))

        listen_ip = value("LISTEN_IP", "192.0.2.231")
        printer_ip = value("PRINTER_IP", "192.0.2.251")
        for name, candidate in (("LISTEN_IP", listen_ip), ("PRINTER_IP", printer_ip)):
            try:
                parsed = ip_address(candidate)
            except ValueError as exc:
                raise ConfigError(f"{name} is not a valid IP address: {candidate!r}") from exc
            if parsed.version != 4:
                raise ConfigError(f"{name} must be an IPv4 address")
            if parsed.is_unspecified or parsed.is_multicast:
                raise ConfigError(f"{name} must be a specific unicast address")

        hash_algorithm = value("HASH_ALGORITHM", "sha256").lower()
        if hash_algorithm != "sha256":
            raise ConfigError("HASH_ALGORITHM must be sha256 in this release")
        log_level = value("LOG_LEVEL", "INFO").upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigError(f"Unsupported LOG_LEVEL: {log_level}")

        listen_port = _parse_int(value("LISTEN_PORT", "23"), "LISTEN_PORT", 1, 65535)
        printer_port = _parse_int(value("PRINTER_PORT", "23"), "PRINTER_PORT", 1, 65535)
        if listen_ip == printer_ip and listen_port == printer_port:
            raise ConfigError("Proxy and printer endpoints must not be identical")

        result = cls(
            listen_ip=listen_ip,
            listen_port=listen_port,
            printer_ip=printer_ip,
            printer_port=printer_port,
            output_dir=Path(value("OUTPUT_DIR", "/var/lib/commercialrchproxy/jobs")),
            log_dir=Path(value("LOG_DIR", "/var/log/commercialrchproxy")),
            connection_timeout_sec=_parse_float(
                value("CONNECTION_TIMEOUT_SEC", "30"), "CONNECTION_TIMEOUT_SEC", 0.05, 3600.0
            ),
            response_timeout_sec=_parse_float(
                value("RESPONSE_TIMEOUT_SEC", "10"), "RESPONSE_TIMEOUT_SEC", 0.05, 3600.0
            ),
            job_idle_timeout_ms=_parse_int(value("JOB_IDLE_TIMEOUT_MS", "1000"), "JOB_IDLE_TIMEOUT_MS", 50, 86_400_000),
            save_raw=_parse_bool(value("SAVE_RAW", "true"), "SAVE_RAW"),
            save_technical_txt=_parse_bool(value("SAVE_TECHNICAL_TXT", "true"), "SAVE_TECHNICAL_TXT"),
            save_clean_txt=_parse_bool(value("SAVE_CLEAN_TXT", "true"), "SAVE_CLEAN_TXT"),
            save_pdf=_parse_bool(value("SAVE_PDF", "true"), "SAVE_PDF"),
            save_json=_parse_bool(value("SAVE_JSON", "true"), "SAVE_JSON"),
            hash_algorithm=hash_algorithm,
            debug=_parse_bool(value("DEBUG", "false"), "DEBUG"),
            debug_hexdump=_parse_bool(value("DEBUG_HEXDUMP", "false"), "DEBUG_HEXDUMP"),
            debug_pcap=_parse_bool(value("DEBUG_PCAP", "false"), "DEBUG_PCAP"),
            retention_days=_parse_int(value("RETENTION_DAYS", "0"), "RETENTION_DAYS", 0, 36500),
            max_payload_bytes=_parse_int(
                value("MAX_PAYLOAD_BYTES", "67108864"), "MAX_PAYLOAD_BYTES", 1024, 2_147_483_647
            ),
            renderer_paper_width_mm=_parse_float(
                value("RENDERER_PAPER_WIDTH_MM", "79.5"),
                "RENDERER_PAPER_WIDTH_MM",
                40.0,
                120.0,
            ),
            renderer_characters_per_line=_parse_int(
                value("RENDERER_CHARACTERS_PER_LINE", "48"),
                "RENDERER_CHARACTERS_PER_LINE",
                16,
                96,
            ),
            log_payload=_parse_bool(value("LOG_PAYLOAD", "false"), "LOG_PAYLOAD"),
            log_level=log_level,
            shutdown_grace_sec=_parse_float(value("SHUTDOWN_GRACE_SEC", "15"), "SHUTDOWN_GRACE_SEC", 0.05, 3600.0),
        )
        for name, path_value in (("OUTPUT_DIR", result.output_dir), ("LOG_DIR", result.log_dir)):
            if not path_value.is_absolute():
                raise ConfigError(f"{name} must be an absolute path")
            if path_value == Path(path_value.anchor):
                raise ConfigError(f"{name} must not be a filesystem root")
        if not result.save_json:
            raise ConfigError("SAVE_JSON must remain true because the forensic manifest is mandatory")
        if not result.save_raw:
            raise ConfigError("SAVE_RAW must remain true because immutable directional evidence is mandatory")
        if not result.save_technical_txt:
            raise ConfigError("SAVE_TECHNICAL_TXT must remain true because the receive timeline is mandatory")
        return result

    def redacted_dict(self) -> dict[str, object]:
        return {field.name: getattr(self, field.name) for field in fields(self)}


_KEYS = {
    "LISTEN_IP",
    "LISTEN_PORT",
    "PRINTER_IP",
    "PRINTER_PORT",
    "OUTPUT_DIR",
    "LOG_DIR",
    "CONNECTION_TIMEOUT_SEC",
    "RESPONSE_TIMEOUT_SEC",
    "JOB_IDLE_TIMEOUT_MS",
    "SAVE_RAW",
    "SAVE_TECHNICAL_TXT",
    "SAVE_CLEAN_TXT",
    "SAVE_PDF",
    "SAVE_JSON",
    "HASH_ALGORITHM",
    "DEBUG",
    "DEBUG_HEXDUMP",
    "DEBUG_PCAP",
    "RETENTION_DAYS",
    "MAX_PAYLOAD_BYTES",
    "RENDERER_PAPER_WIDTH_MM",
    "RENDERER_CHARACTERS_PER_LINE",
    "LOG_PAYLOAD",
    "LOG_LEVEL",
    "SHUTDOWN_GRACE_SEC",
}
