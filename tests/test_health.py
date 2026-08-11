from __future__ import annotations

from pathlib import Path

from commercialrchproxy.health import health_report
from tests.support import make_config, unused_port


def test_default_healthcheck_never_connects_to_fiscal_device(tmp_path: Path, monkeypatch) -> None:
    config = make_config(tmp_path, unused_port(), unused_port())
    config.output_dir.mkdir(parents=True)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("network connect was attempted")

    monkeypatch.setattr("commercialrchproxy.health.socket.create_connection", forbidden)
    report = health_report(config)
    assert report["printer"]["status"] == "not_probed"
    assert report["printer"]["safety"] == "UNCONFIRMED"
