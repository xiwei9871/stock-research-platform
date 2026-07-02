import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


def _make_cron_harness(
    tmp_path: Path,
    python_body: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "stock_research"
    bin_dir = tmp_path / "bin"
    scripts_dir = root / "scripts"

    scripts_dir.mkdir(parents=True)
    bin_dir.mkdir()
    (scripts_dir / "stock_cron_guard.sh").write_text(
        "clear_stock_proxy_env() {\n"
        "  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY\n"
        "}\n"
    )
    _write_executable(
        bin_dir / "rtk",
        "#!/usr/bin/env bash\n"
        'echo "rtk|$*" >> "$STOCK_RESEARCH_ROOT/rtk.log"\n'
        'exec "$@"\n',
    )
    for lock_cmd in ("flock", "lockf"):
        _write_executable(
            bin_dir / lock_cmd,
            "#!/usr/bin/env bash\n"
            f'echo "{lock_cmd}|$*" >> "$STOCK_RESEARCH_ROOT/lock-command.log"\n'
            "exit 66\n",
        )
    python_stub = bin_dir / "python"
    _write_executable(
        python_stub,
        "#!/usr/bin/env bash\n"
        'echo "python|$*" >> "$STOCK_RESEARCH_ROOT/python.log"\n'
        f"{python_body or 'exit \"${STUB_PYTHON_RC:-0}\"'}\n",
    )

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "STOCK_RESEARCH_ROOT": str(root),
            "STOCK_RESEARCH_PYTHON": str(python_stub),
        }
    )
    if extra_env:
        env.update(extra_env)
    return root, env


def _run_cron(env: dict[str, str], trade_date: str = "2026-07-02") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(REPO_ROOT / "scripts/run_eod_auto_repair_cron.sh"), trade_date],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_eod_auto_repair_cron_uses_module_entrypoint_and_portable_lock():
    script = Path("scripts/run_eod_auto_repair_cron.sh").read_text()

    assert "python -m stock_research.eod_auto_repair" in script
    assert "flock" not in script
    assert "lockf" not in script
    assert "stock_cron_guard.sh" in script
    assert 'LOCK_FILE="$ROOT/.locks/eod_auto_repair.lock"' in script
    assert 'mkdir "$LOCK_FILE"' in script
    assert "eod_auto_repair|locked|$LOCK_FILE" in script
    assert "--mode repair" in script
    assert "logs/eod_auto_repair" in script
    assert "run_summary.json" in script
    assert "run_report.md" in script


def test_eod_auto_repair_cron_ignores_stale_lock_file_and_preserves_exit_code(tmp_path):
    root, env = _make_cron_harness(
        tmp_path,
        python_body=(
            "for name in HTTP_PROXY HTTPS_PROXY http_proxy https_proxy; do\n"
            '  eval "value=\\${$name-}"\n'
            '  if [[ -n "$value" ]]; then echo "$name=$value" >> "$STOCK_RESEARCH_ROOT/proxy.log"; fi\n'
            "done\n"
            'exit "${STUB_PYTHON_RC:-0}"'
        ),
        extra_env={
            "STUB_PYTHON_RC": "7",
            "HTTP_PROXY": "http://proxy.invalid:8080",
            "HTTPS_PROXY": "http://proxy.invalid:8443",
            "http_proxy": "http://proxy.invalid:8081",
            "https_proxy": "http://proxy.invalid:8444",
        },
    )
    lock_file = root / ".locks" / "eod_auto_repair.lock"
    trade_date = "2026-07-02"

    lock_file.parent.mkdir(parents=True)
    lock_file.write_text("999999\n")

    result = _run_cron(env, trade_date)

    assert result.returncode == 7
    assert not lock_file.exists()
    assert "-m stock_research.eod_auto_repair" in (root / "python.log").read_text()
    lock_command_log = root / "lock-command.log"
    assert not lock_command_log.exists()
    log = root / "logs" / "eod_auto_repair" / f"{trade_date}.log"
    log_text = log.read_text()
    assert "eod_auto_repair|locked" not in log_text
    assert f"eod_auto_repair|summary|{root}/outputs/research/eod_auto_repair/{trade_date}/run_summary.json" in log_text
    assert f"eod_auto_repair|report|{root}/outputs/research/eod_auto_repair/{trade_date}/run_report.md" in log_text
    proxy_log = root / "proxy.log"
    assert not proxy_log.exists() or proxy_log.read_text() == ""


def test_eod_auto_repair_cron_allows_only_one_contender_while_locked(tmp_path):
    root, env = _make_cron_harness(
        tmp_path,
        python_body=(
            'echo "start|$$" >> "$STOCK_RESEARCH_ROOT/starts.log"\n'
            "sleep 1\n"
            'echo "end|$$" >> "$STOCK_RESEARCH_ROOT/starts.log"\n'
            "exit 0"
        ),
    )

    procs = [
        subprocess.Popen(
            [str(REPO_ROOT / "scripts/run_eod_auto_repair_cron.sh"), "2026-07-02"],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(6)
    ]
    results = [proc.communicate(timeout=10) for proc in procs]

    assert all(proc.returncode == 0 for proc in procs), results
    starts_log = root / "starts.log"
    starts = starts_log.read_text().splitlines() if starts_log.exists() else []
    assert len([line for line in starts if line.startswith("start|")]) == 1
    log_text = (root / "logs" / "eod_auto_repair" / "2026-07-02.log").read_text()
    assert "eod_auto_repair|locked" in log_text


def test_eod_auto_repair_cron_allows_only_one_contender_after_stale_lock(tmp_path):
    root, env = _make_cron_harness(
        tmp_path,
        python_body=(
            'echo "start|$$" >> "$STOCK_RESEARCH_ROOT/starts.log"\n'
            "sleep 1\n"
            'echo "end|$$" >> "$STOCK_RESEARCH_ROOT/starts.log"\n'
            "exit 0"
        ),
    )
    lock_file = root / ".locks" / "eod_auto_repair.lock"
    lock_file.parent.mkdir(parents=True)
    lock_file.write_text("999999\n")

    procs = [
        subprocess.Popen(
            [str(REPO_ROOT / "scripts/run_eod_auto_repair_cron.sh"), "2026-07-02"],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(12)
    ]
    results = [proc.communicate(timeout=10) for proc in procs]

    assert all(proc.returncode == 0 for proc in procs), results
    starts_log = root / "starts.log"
    starts = starts_log.read_text().splitlines() if starts_log.exists() else []
    assert len([line for line in starts if line.startswith("start|")]) == 1
    assert not lock_file.exists()
    log_text = (root / "logs" / "eod_auto_repair" / "2026-07-02.log").read_text()
    assert "eod_auto_repair|locked" in log_text


def test_eod_auto_repair_cron_treats_pidless_lock_directory_as_locked(tmp_path):
    root, env = _make_cron_harness(tmp_path)
    lock_file = root / ".locks" / "eod_auto_repair.lock"
    trade_date = "2026-07-02"

    lock_file.mkdir(parents=True)

    result = _run_cron(env, trade_date)

    assert result.returncode == 0
    assert not (root / "python.log").exists()
    assert lock_file.is_dir()
    log_text = (root / "logs" / "eod_auto_repair" / f"{trade_date}.log").read_text()
    assert "eod_auto_repair|locked" in log_text


def test_eod_auto_repair_cron_treats_empty_old_lock_file_as_locked(tmp_path):
    root, env = _make_cron_harness(tmp_path)
    lock_file = root / ".locks" / "eod_auto_repair.lock"
    trade_date = "2026-07-02"

    lock_file.parent.mkdir(parents=True)
    lock_file.write_text("")

    result = _run_cron(env, trade_date)

    assert result.returncode == 0
    assert not (root / "python.log").exists()
    assert lock_file.is_file()
    log_text = (root / "logs" / "eod_auto_repair" / f"{trade_date}.log").read_text()
    assert "eod_auto_repair|locked" in log_text
