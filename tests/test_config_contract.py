from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts" / "config_contract.sh"
DUMPER_UNIT = ROOT / "systemd" / "commercialrchproxy-dumper.service"


def _bash() -> str:
    if os.name == "nt":
        pytest.skip("executable shell contract tests run on the Linux deployment test lane")
    executable = shutil.which("bash")
    if executable is None:
        pytest.skip("bash is unavailable")
    return executable


def _load(config: Path) -> subprocess.CompletedProcess[str]:
    command = (
        'source "$1"; crch_load_config_contract "$2" || exit $?; '
        "printf '%s\\n' \"$CRCH_SERVICE_USER\" \"$CRCH_SERVICE_GROUP\" "
        '"$CRCH_OUTPUT_DIR" "$CRCH_LOG_DIR"'
    )
    return subprocess.run(  # noqa: S603 - fixed interpreter and test-only helper
        [_bash(), "-c", command, "contract-test", str(CONTRACT), str(config)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_contract_loads_custom_identity_and_separate_normalized_paths(tmp_path: Path) -> None:
    config = tmp_path / "site.conf"
    config.write_text(
        "SERVICE_USER=rchcapture\n"
        "SERVICE_GROUP=rcharchive\n"
        "OUTPUT_DIR=/srv/rch-capture/jobs\n"
        "LOG_DIR=/var/log/rch-capture\n",
        encoding="utf-8",
    )

    result = _load(config)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "rchcapture",
        "rcharchive",
        "/srv/rch-capture/jobs",
        "/var/log/rch-capture",
    ]


@pytest.mark.parametrize(
    ("output_dir", "log_dir"),
    [
        ("/", "/var/log/rch-capture"),
        ("/etc/rch/jobs", "/var/log/rch-capture"),
        ("/opt/rch/jobs", "/var/log/rch-capture"),
        ("/var/lib", "/var/log/rch-capture"),
        ("/srv/rch/../jobs", "/var/log/rch-capture"),
        ("/srv/rch", "/srv/rch/logs"),
        ("/srv/rch/jobs", "/srv/rch"),
        ("/srv/rch", "/srv/rch"),
    ],
)
def test_contract_rejects_dangerous_or_overlapping_paths(
    tmp_path: Path,
    output_dir: str,
    log_dir: str,
) -> None:
    config = tmp_path / "site.conf"
    config.write_text(
        f"OUTPUT_DIR={output_dir}\nLOG_DIR={log_dir}\n",
        encoding="utf-8",
    )

    result = _load(config)

    assert result.returncode != 0


def test_contract_rejects_duplicate_keys_and_never_executes_values(tmp_path: Path) -> None:
    marker = tmp_path / "must-not-exist"
    duplicate = tmp_path / "duplicate.conf"
    duplicate.write_text(
        "OUTPUT_DIR=/srv/rch/jobs\n"
        "OUTPUT_DIR=/srv/rch/other\n"
        "LOG_DIR=/var/log/rch-capture\n",
        encoding="utf-8",
    )
    malicious = tmp_path / "malicious.conf"
    malicious.write_text(
        f"SERVICE_USER=$(touch {marker})\n"
        "OUTPUT_DIR=/srv/rch/jobs\n"
        "LOG_DIR=/var/log/rch-capture\n",
        encoding="utf-8",
    )

    assert _load(duplicate).returncode != 0
    assert _load(malicious).returncode != 0
    assert not marker.exists()


def test_unit_renderer_escapes_paths_and_applies_all_four_values(tmp_path: Path) -> None:
    rendered = tmp_path / "dumper.service"
    command = (
        'source "$1"; crch_render_service_unit "$2" "$3" '
        'rchcapture rcharchive "/srv/rch-jobs/raw" "/var/log/rch-capture" true'
    )
    result = subprocess.run(  # noqa: S603 - fixed interpreter and test-only helper
        [
            _bash(),
            "-c",
            command,
            "contract-test",
            str(CONTRACT),
            str(DUMPER_UNIT),
            str(rendered),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    text = rendered.read_text(encoding="utf-8")
    assert "User=rchcapture\n" in text
    assert "Group=rcharchive\n" in text
    assert 'WorkingDirectory="/srv/rch-jobs/raw"\n' in text
    assert 'ReadWritePaths="/srv/rch-jobs/raw" "/var/log/rch-capture"\n' in text
    assert text.count("User=") == 1
    assert text.count("Group=") == 1
    assert text.count("WorkingDirectory=") == 1
    assert text.count("ReadWritePaths=") == 1
