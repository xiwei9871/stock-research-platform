from pathlib import Path


RUN_SCRIPT = Path("scripts/run_founder_os_model_recovery_cron.sh")


def test_recovery_cron_script_uses_lock_and_repo_python() -> None:
    text = RUN_SCRIPT.read_text(encoding="utf-8")

    assert "python_lockfile" in text
    assert "founder-os-model-recovery.log" in text
    assert '-m stock_research.founder_os_model_recovery_cli "$COMMAND"' in text
    assert '[[ "$COMMAND" == "run" || "$COMMAND" == "audit" ]]' in text


def test_recovery_cron_script_defaults_to_run() -> None:
    text = RUN_SCRIPT.read_text(encoding="utf-8")

    assert 'COMMAND="${1:-run}"' in text
