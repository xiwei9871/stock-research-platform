from pathlib import Path


RUN_SCRIPT = Path("scripts/run_founder_os_model_recovery_cron.sh")
INSTALL_SCRIPT = Path("scripts/install_founder_os_model_recovery.sh")


def test_recovery_cron_script_uses_lock_and_repo_python() -> None:
    text = RUN_SCRIPT.read_text(encoding="utf-8")

    assert "python_lockfile" in text
    assert "founder-os-model-recovery.log" in text
    assert '-m stock_research.founder_os_model_recovery_cli "$COMMAND"' in text
    assert '[[ "$COMMAND" == "run" || "$COMMAND" == "audit" ]]' in text


def test_recovery_cron_script_defaults_to_run() -> None:
    text = RUN_SCRIPT.read_text(encoding="utf-8")

    assert 'COMMAND="${1:-run}"' in text


def test_recovery_cron_script_forwards_additional_cli_arguments() -> None:
    text = RUN_SCRIPT.read_text(encoding="utf-8")

    assert 'shift' in text
    assert '"$COMMAND" "$@"' in text


def test_installer_supports_dry_run_apply_and_rollback() -> None:
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "--dry-run" in text
    assert "--apply" in text
    assert "--rollback" in text
    assert "ln -sfn" in text
    assert "founder_os_model_recovery_config" in text


def test_installer_dry_run_does_not_install_runtime_shim() -> None:
    text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert text.index("--dry-run)") < text.index("ln -sfn")
