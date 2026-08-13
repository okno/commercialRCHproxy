from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _script(name: str) -> str:
    return (SCRIPTS / name).read_text(encoding="utf-8")


def test_installer_deploys_and_verifies_all_units_as_one_transaction() -> None:
    script = _script("install.sh")

    assert 'DUMPER_SERVICE="commercialrchproxy-dumper.service"' in script
    assert 'PARSER_SERVICE="commercialrchproxy-parser.service"' in script
    assert 'LEGACY_SERVICE="commercialrchproxy.service"' in script
    assert 'for service_name in "${ALL_SERVICES[@]}"' in script
    assert 'systemd-analyze verify "${unit_paths[@]}"' in script
    assert 'systemctl enable "${MANAGED_SERVICES[@]}"' in script
    assert 'systemctl disable "${LEGACY_SERVICE}"' in script
    assert 'commercialrchproxy-dumper commercialrchproxy-parser' in script


def test_installer_renders_configured_identity_and_paths_without_sourcing_config() -> None:
    script = _script("install.sh")
    contract = _script("config_contract.sh")

    assert 'source "${SCRIPT_DIR}/config_contract.sh"' in script
    assert 'crch_load_config_contract "${CONFIG_INPUT}"' in script
    assert 'SERVICE_USER="${CRCH_SERVICE_USER}"' in script
    assert 'SERVICE_GROUP="${CRCH_SERVICE_GROUP}"' in script
    assert 'OUTPUT_DIR="${CRCH_OUTPUT_DIR}"' in script
    assert 'LOG_DIR="${CRCH_LOG_DIR}"' in script
    assert 'render_service_unit "${service_name}"' in script
    assert '"${ROLLBACK_DIR}/rendered-units/${service_name}"' in script
    assert 'crch_render_service_unit "${source_path}" "${destination}"' in script
    assert 'WorkingDirectory=%s' in contract
    assert 'ReadWritePaths=%s %s' in contract
    assert 'source "${CONFIG_PATH}"' not in script
    assert "never sourced or evaluated" in contract
    assert "crch_validate_managed_path" in contract


def test_maintenance_scripts_use_the_same_configured_roots_and_identity() -> None:
    for name in ("backup.sh", "check_config.sh", "uninstall.sh"):
        script = _script(name)
        assert 'source "${SCRIPT_DIR}/config_contract.sh"' in script
        assert "crch_load_config_contract" in script
        assert 'source "${CONFIG_PATH}"' not in script

    backup = _script("backup.sh")
    assert '"${CONFIG_DIR}" "${OUTPUT_DIR}" "${LOG_DIR}"' in backup

    check_config = _script("check_config.sh")
    assert "verify_unit_contract commercialrchproxy-dumper.service" in check_config
    assert "verify_unit_contract commercialrchproxy-parser.service" in check_config
    assert "WorkingDirectory" in check_config
    assert "ReadWritePaths" in check_config

    uninstall = _script("uninstall.sh")
    assert 'rm -rf -- "${OUTPUT_DIR}"' in uninstall
    assert 'rm -rf -- "${LOG_DIR}"' in uninstall
    assert 'userdel "${SERVICE_USER}"' in uninstall


def test_lifecycle_and_health_scripts_address_both_real_services() -> None:
    for name in ("start.sh", "stop.sh", "restart.sh", "status.sh", "healthcheck.sh"):
        script = _script(name)
        assert "commercialrchproxy-dumper.service" in script
        assert "commercialrchproxy-parser.service" in script

    healthcheck = _script("healthcheck.sh")
    assert "commercialrchproxy-dumper" in healthcheck
    assert 'for service_name in "${DUMPER_SERVICE}" "${PARSER_SERVICE}"' in healthcheck
    assert "RCH protocol reachability: NOT PROBED" in healthcheck


def test_backup_preserves_active_state_per_service_and_archives_every_unit() -> None:
    script = _script("backup.sh")

    assert 'ACTIVE_BEFORE=()' in script
    assert 'systemctl stop "${ACTIVE_BEFORE[@]}"' in script
    assert 'systemctl start "${ACTIVE_BEFORE[@]}"' in script
    assert 'for service_name in "${SERVICES[@]}"' in script
    assert 'unit_path="${UNIT_DIR}/${service_name}"' in script


def test_uninstall_removes_all_app_units_but_keeps_default_data_policy() -> None:
    script = _script("uninstall.sh")

    assert 'systemctl disable --now "${SERVICES[@]}"' in script
    assert 'rm -f -- "${UNIT_DIR}/${service_name}"' in script
    assert "PRESERVED: captured jobs" in script
    assert 'if [[ "${PURGE}" -eq 1 ]]' in script


def test_secondary_ip_dependency_targets_only_dumper_and_migrates_legacy() -> None:
    script = _script("manage_secondary_ip.sh")

    assert 'APP_SERVICE="commercialrchproxy-dumper.service"' in script
    assert 'LEGACY_APP_SERVICE="commercialrchproxy.service"' in script
    assert "Before=${APP_SERVICE}" in script
    assert 'DROPIN_DIR="/etc/systemd/system/${APP_SERVICE}.d"' in script
    assert 'rm -f -- "${LEGACY_DROPIN_PATH}"' in script
    assert "commercialrchproxy-parser.service" not in script
