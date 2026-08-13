from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEMD = ROOT / "systemd"
CONFIG_PATH = "/etc/commercialrchproxy/commercialrchproxy.conf"
JOBS_PATH = "/var/lib/commercialrchproxy/jobs"
LOG_PATH = "/var/log/commercialrchproxy"


def _unit(name: str) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    section: str | None = None
    path = SYSTEMD / name
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            sections.setdefault(section, {})
            continue
        assert section is not None, f"directive outside a section in {path}: {line}"
        key, separator, value = line.partition("=")
        assert separator, f"invalid directive in {path}: {line}"
        if key in sections[section]:
            sections[section][key] += f"\n{value}"
        else:
            sections[section][key] = value
    return sections


def _tokens(value: str) -> set[str]:
    return set(value.split())


def test_real_services_are_independent_and_use_the_shared_config() -> None:
    dumper = _unit("commercialrchproxy-dumper.service")
    parser = _unit("commercialrchproxy-parser.service")

    dumper_unit_text = " ".join(dumper["Unit"].values())
    parser_unit_text = " ".join(parser["Unit"].values())
    assert "commercialrchproxy-parser" not in dumper_unit_text
    assert "commercialrchproxy-dumper" not in parser_unit_text

    dumper_start = dumper["Service"]["ExecStart"]
    parser_start = parser["Service"]["ExecStart"]
    assert "/commercialrchproxy-dumper " in dumper_start
    assert "/commercialrchproxy-parser " in parser_start
    assert f"--config {CONFIG_PATH}" in dumper_start
    assert f"--config {CONFIG_PATH}" in parser_start
    assert f"COMMERCIALRCHPROXY_CONFIG={CONFIG_PATH}" in dumper["Service"]["Environment"].splitlines()
    assert f"COMMERCIALRCHPROXY_CONFIG={CONFIG_PATH}" in parser["Service"]["Environment"].splitlines()


def test_dumper_has_only_bind_capability_and_network_address_families() -> None:
    service = _unit("commercialrchproxy-dumper.service")["Service"]

    assert _tokens(service["CapabilityBoundingSet"]) == {"CAP_NET_BIND_SERVICE"}
    assert _tokens(service["AmbientCapabilities"]) == {"CAP_NET_BIND_SERVICE"}
    families = _tokens(service["RestrictAddressFamilies"])
    assert {"AF_INET", "AF_INET6"} <= families
    assert service["SyslogIdentifier"] == "commercialrchproxy-dumper"


def test_parser_has_no_capability_or_ip_network_access() -> None:
    service = _unit("commercialrchproxy-parser.service")["Service"]

    assert service["CapabilityBoundingSet"] == ""
    assert service["AmbientCapabilities"] == ""
    assert service["PrivateNetwork"] == "true"
    assert service["IPAddressDeny"] == "any"
    families = _tokens(service["RestrictAddressFamilies"])
    assert "AF_INET" not in families
    assert "AF_INET6" not in families
    assert service["SyslogIdentifier"] == "commercialrchproxy-parser"


def test_parser_persistent_writes_are_limited_to_jobs_and_logs() -> None:
    service = _unit("commercialrchproxy-parser.service")["Service"]

    assert service["ProtectSystem"] == "strict"
    assert _tokens(service["ReadWritePaths"]) == {JOBS_PATH, LOG_PATH}
    assert _tokens(service["ReadOnlyPaths"]) == {
        "/etc/commercialrchproxy",
        "/opt/commercialrchproxy",
    }


def test_parser_task_limit_covers_maximum_configured_workers_and_heartbeats() -> None:
    service = _unit("commercialrchproxy-parser.service")["Service"]

    # Config accepts at most 64 workers. Each active job can consume both an
    # executor thread and a lease-heartbeat thread, in addition to the main,
    # watcher and logging tasks.
    assert int(service["TasksMax"]) >= (2 * 64) + 4


def test_default_unit_templates_follow_the_config_contract() -> None:
    for name in ("commercialrchproxy-dumper.service", "commercialrchproxy-parser.service"):
        service = _unit(name)["Service"]
        assert service["WorkingDirectory"] == JOBS_PATH
        assert _tokens(service["ReadWritePaths"]) == {JOBS_PATH, LOG_PATH}
        # Custom LOG_DIR cannot be represented by systemd LogsDirectory=;
        # install.sh creates it and renders the writable sandbox paths instead.
        assert "LogsDirectory" not in service


def test_both_real_services_run_unprivileged_with_common_hardening() -> None:
    for name in ("commercialrchproxy-dumper.service", "commercialrchproxy-parser.service"):
        service = _unit(name)["Service"]
        assert service["User"] == "commercialrchproxy"
        assert service["Group"] == "commercialrchproxy"
        assert service["UMask"] == "0027"
        assert service["NoNewPrivileges"] == "true"
        assert service["ProtectHome"] == "true"
        assert service["PrivateDevices"] == "true"
        assert service["ProtectKernelTunables"] == "true"
        assert service["ProtectControlGroups"] == "true"
        assert service["MemoryDenyWriteExecute"] == "true"
        assert service["StandardOutput"] == "journal"
        assert service["StandardError"] == "journal"


def test_legacy_service_is_a_noop_compatibility_launcher() -> None:
    unit = _unit("commercialrchproxy.service")
    required = _tokens(unit["Unit"]["Requires"])
    propagated = _tokens(unit["Unit"]["PropagatesStopTo"])
    expected = {
        "commercialrchproxy-dumper.service",
        "commercialrchproxy-parser.service",
    }

    assert required == expected
    assert propagated == expected
    assert _tokens(unit["Unit"]["Before"]) == expected
    assert unit["Service"]["Type"] == "oneshot"
    assert unit["Service"]["ExecStart"] == "/usr/bin/true"
    assert unit["Service"]["RemainAfterExit"] == "yes"
    assert unit["Service"]["CapabilityBoundingSet"] == ""
    assert unit["Service"]["AmbientCapabilities"] == ""
