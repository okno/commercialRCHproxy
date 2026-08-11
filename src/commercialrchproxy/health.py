"""Non-invasive configuration and health reporting."""

from __future__ import annotations

import errno
import json
import shutil
import socket
from pathlib import Path
from typing import Any

from commercialrchproxy import __version__
from commercialrchproxy.config import Config


def local_ip_assigned(ip: str) -> tuple[bool, str | None]:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((ip, 0))
        return True, None
    except OSError as exc:
        if exc.errno in {errno.EADDRNOTAVAIL, 10049}:
            return False, f"The IP address {ip} is not assigned to this host"
        return False, f"Cannot validate local IP {ip}: {exc}"
    finally:
        probe.close()


def _linux_listener(ip: str, port: int) -> bool | None:
    tcp = Path("/proc/net/tcp")
    if not tcp.exists():
        return None
    packed = socket.inet_aton(ip)
    address_hex = packed[::-1].hex().upper()
    endpoint = f"{address_hex}:{port:04X}"
    try:
        lines = tcp.read_text(encoding="ascii").splitlines()[1:]
    except OSError:
        return None
    for line in lines:
        columns = line.split()
        if len(columns) > 3 and columns[1].upper() == endpoint and columns[3] == "0A":
            return True
    return False


def _latest_manifest(root: Path) -> dict[str, Any] | None:
    if not root.exists() or root.is_symlink():
        return None
    candidates = [path for path in root.rglob("*.json") if path.is_file() and not path.is_symlink()]
    if not candidates:
        return None
    latest = max(candidates, key=lambda path: path.stat().st_mtime_ns)
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "unreadable", "path": str(latest)}
    return {
        "id": data.get("job_id"),
        "status": data.get("status"),
        "timestamp": data.get("timestamp_end"),
        "path": str(latest),
    }


def health_report(config: Config) -> dict[str, Any]:
    assigned, ip_error = local_ip_assigned(config.listen_ip)
    listener = _linux_listener(config.listen_ip, config.listen_port)
    output_ok = config.output_dir.exists() and config.output_dir.is_dir() and not config.output_dir.is_symlink()
    try:
        free = shutil.disk_usage(config.output_dir if output_ok else config.output_dir.parent).free
    except OSError:
        free = None

    printer = {
        "status": "not_probed",
        "probe": None,
        "safety": "UNCONFIRMED",
        "reason": "An empty RCH port-23 session is not documented or observed as inert",
    }

    return {
        "project": "commercialRCHproxy",
        "version": __version__,
        "proxy": {
            "endpoint": f"{config.listen_ip}:{config.listen_port}",
            "ip_assigned": assigned,
            "ip_error": ip_error,
            "listener": "ok" if listener is True else "not_listening" if listener is False else "unknown",
        },
        "printer": {"endpoint": f"{config.printer_ip}:{config.printer_port}", **printer},
        "jobs_directory": {"path": str(config.output_dir), "ok": output_ok, "disk_free_bytes": free},
        "last_job": _latest_manifest(config.output_dir),
    }


def format_health(report: dict[str, Any]) -> str:
    proxy = report["proxy"]
    printer = report["printer"]
    jobs = report["jobs_directory"]
    last = report["last_job"] or {}
    return "\n".join(
        (
            "commercialRCHproxy",
            "",
            f"Proxy: {proxy['endpoint']}",
            f"  IP assigned: {'YES' if proxy['ip_assigned'] else 'NO'}",
            f"  Listener: {str(proxy['listener']).upper()}",
            "",
            f"RCH Print! F: {printer['endpoint']}",
            f"  Protocol reachability: {str(printer['status']).upper()}",
            f"  Probe safety: {printer['safety']}",
            "",
            f"Jobs directory: {'OK' if jobs['ok'] else 'ERROR'} ({jobs['path']})",
            f"Disk free: {jobs['disk_free_bytes'] if jobs['disk_free_bytes'] is not None else 'UNKNOWN'} bytes",
            "",
            f"Last job ID: {last.get('id', 'NONE')}",
            f"Last job status: {last.get('status', 'NONE')}",
            f"Version: {report['version']}",
        )
    )
