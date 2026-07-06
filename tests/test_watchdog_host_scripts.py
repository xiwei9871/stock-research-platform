import os
import subprocess
from pathlib import Path


def test_factor_gate_watchdog_host_smoke_mode_does_not_run_backfill(tmp_path: Path) -> None:
    fake_python = tmp_path / "python.sh"
    calls_file = tmp_path / "calls.txt"
    fake_python.write_text(
        f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "{calls_file}"
exit 0
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "FACTOR_GATE_WATCHDOG_ROOT": str(Path.cwd()),
            "FACTOR_GATE_WATCHDOG_PYTHON": str(fake_python),
            "FACTOR_GATE_WATCHDOG_LOG_DIR": str(tmp_path / "logs"),
            "FACTOR_GATE_WATCHDOG_SMOKE_ONLY": "1",
        }
    )

    result = subprocess.run(
        ["scripts/run_wave5_factor_gate_watchdog_host.sh"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    log = (tmp_path / "logs" / "wave5-factor-gate-watchdog.host.log").read_text(encoding="utf-8")
    assert "factor_gate_watchdog|smoke|would_run|adapter=factor-gate" in log
    calls = calls_file.read_text(encoding="utf-8") if calls_file.exists() else ""
    assert "-m stock_research.cli backfill-watchdog" not in calls
