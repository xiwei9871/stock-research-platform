import os
import subprocess
from pathlib import Path


def test_platform_build_script_runs_required_platform_steps(tmp_path: Path) -> None:
    fake_root = tmp_path / "root"
    fake_root.mkdir()
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
            "PLATFORM_READY_ROOT": str(fake_root),
            "PLATFORM_READY_PYTHON": str(fake_python),
            "PLATFORM_READY_TRADE_DATE": "2026-06-18",
            "PLATFORM_READY_OUTPUT_DIR": str(tmp_path / "outputs"),
            "PLATFORM_READY_REPORTS_DIR": str(tmp_path / "reports"),
            "PLATFORM_READY_LOG_DIR": str(tmp_path / "logs"),
            "PLATFORM_READY_LHB_CASE_PATH": str(tmp_path / "case.csv"),
            "PLATFORM_READY_LHB_FEATURES_PATH": str(tmp_path / "features.csv"),
            "PLATFORM_READY_LHB_ALIGNMENT_PATH": str(tmp_path / "alignment.csv"),
        }
    )

    result = subprocess.run(
        ["scripts/run_platform_ready_build_cron.sh"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    calls = calls_file.read_text(encoding="utf-8")
    assert "-m stock_research.cli free-enrichment-backfill" in calls
    assert "-m stock_research.cli run-daily-factor-pipeline" in calls
    assert "-m stock_research.cli build-technical-features-daily" in calls
    assert "-m stock_research.cli run-lhb-shortline-daily-v1" in calls
    assert "-m stock_research.cli watchlist-build" in calls
    assert "-m stock_research.platform_ready --trade-date 2026-06-18" in calls


def test_platform_ready_check_script_exits_with_check_status(tmp_path: Path) -> None:
    fake_root = tmp_path / "root"
    fake_root.mkdir()
    fake_python = tmp_path / "python.sh"
    calls_file = tmp_path / "calls.txt"

    fake_python.write_text(
        f"""#!/usr/bin/env bash
printf '%s\\n' "$*" > "{calls_file}"
exit 3
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PLATFORM_READY_ROOT": str(fake_root),
            "PLATFORM_READY_PYTHON": str(fake_python),
            "PLATFORM_READY_TRADE_DATE": "2026-06-18",
            "PLATFORM_READY_LOG_DIR": str(tmp_path / "logs"),
        }
    )

    result = subprocess.run(
        ["scripts/run_platform_ready_check_cron.sh"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 3
    assert "-m stock_research.platform_ready --trade-date 2026-06-18" in calls_file.read_text(encoding="utf-8")
