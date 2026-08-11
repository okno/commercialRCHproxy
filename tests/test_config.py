from __future__ import annotations

from pathlib import Path

import pytest

from commercialrchproxy.config import Config, ConfigError, parse_env_file


def test_defaults_use_documentation_addresses_but_ports_remain_configurable(tmp_path: Path) -> None:
    config = Config.from_mapping(
        {
            "LISTEN_PORT": "12345",
            "PRINTER_PORT": "23456",
            "OUTPUT_DIR": str((tmp_path / "jobs").resolve()),
            "LOG_DIR": str((tmp_path / "logs").resolve()),
        }
    )
    assert config.listen_ip == "192.0.2.231"
    assert config.printer_ip == "192.0.2.251"
    assert config.listen_port == 12345
    assert config.printer_port == 23456


@pytest.mark.parametrize("key,value", [("LISTEN_PORT", "0"), ("PRINTER_PORT", "65536"), ("LISTEN_IP", "not-an-ip")])
def test_invalid_network_values_rejected(tmp_path: Path, key: str, value: str) -> None:
    mapping = {
        "OUTPUT_DIR": str((tmp_path / "jobs").resolve()),
        "LOG_DIR": str((tmp_path / "logs").resolve()),
        key: value,
    }
    with pytest.raises(ConfigError):
        Config.from_mapping(mapping)


def test_unknown_keys_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Unknown"):
        Config.from_mapping({"OUTPUT_DIR": str(tmp_path.resolve()), "POS80BL_MODE": "true"})


def test_forensic_manifest_cannot_be_disabled(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="SAVE_JSON must remain true"):
        Config.from_mapping(
            {
                "OUTPUT_DIR": str((tmp_path / "jobs").resolve()),
                "LOG_DIR": str((tmp_path / "logs").resolve()),
                "SAVE_JSON": "false",
            }
        )


def test_duplicate_file_key_rejected(tmp_path: Path) -> None:
    path = tmp_path / "proxy.conf"
    path.write_text("LISTEN_PORT=23\nLISTEN_PORT=24\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="duplicate"):
        parse_env_file(path)


def test_escpos_specific_keys_are_not_accepted(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        Config.from_mapping({"OUTPUT_DIR": str(tmp_path.resolve()), "SPLIT_ON_ESCPOS_CUT": "true"})


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("RENDERER_PAPER_WIDTH_MM", "nan"),
        ("RENDERER_PAPER_WIDTH_MM", "39.9"),
        ("RENDERER_CHARACTERS_PER_LINE", "15"),
        ("RENDERER_CHARACTERS_PER_LINE", "97"),
    ],
)
def test_provisional_renderer_parameters_are_bounded(tmp_path: Path, key: str, value: str) -> None:
    with pytest.raises(ConfigError):
        Config.from_mapping(
            {
                "OUTPUT_DIR": str((tmp_path / "jobs").resolve()),
                "LOG_DIR": str((tmp_path / "logs").resolve()),
                key: value,
            }
        )
