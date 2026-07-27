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
    flock_body: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "stock_research"
    bin_dir = tmp_path / "bin"
    scripts_dir = root / "scripts"
    deploy_dir = root / "deploy"

    scripts_dir.mkdir(parents=True)
    deploy_dir.mkdir()
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
    _write_executable(
        bin_dir / "curl",
        "#!/usr/bin/env bash\n"
        'echo "curl|$*" >> "$STOCK_RESEARCH_ROOT/curl.log"\n'
        'exit "${STUB_CURL_RC:-0}"\n',
    )
    _write_executable(
        deploy_dir / "sync_dashboard_release.sh",
        "#!/usr/bin/env bash\n"
        'echo "sync|date=$EXPECTED_TRADE_DATE|root=$STOCK_RESEARCH_RELEASE_ROOT" >> "$STOCK_RESEARCH_ROOT/sync.log"\n'
        'exit "${STUB_SYNC_RC:-0}"\n',
    )
    (deploy_dir / "validate_strategy_release.py").write_text("# test stub\n")
    if flock_body is not None:
        _write_executable(
            bin_dir / "flock",
            "#!/usr/bin/env bash\n"
            'echo "flock|$*" >> "$STOCK_RESEARCH_ROOT/lock-command.log"\n'
            f"{flock_body}\n",
        )
    python_stub = bin_dir / "python"
    _write_executable(
        python_stub,
        "#!/usr/bin/env bash\n"
        'echo "python|$*" >> "$STOCK_RESEARCH_ROOT/python.log"\n'
        'if [[ "$*" == *"stock_research.platform_ready"* ]]; then\n'
        '  for ((i=1; i<=$#; i++)); do\n'
        '    if [[ "${!i}" == "--json-output" ]]; then j=$((i+1)); printf \'{"status":"%s"}\\n\' "${STUB_READY_STATUS:-ready}" > "${!j}"; fi\n'
        '  done\n'
        '  [[ "${STUB_READY_STATUS:-ready}" == "ready" ]] && exit 0 || exit 1\n'
        'fi\n'
        'if [[ "$*" == *"validate_strategy_release.py"* ]]; then exit "${STUB_CONTRACT_RC:-0}"; fi\n'
        f"{python_body or 'exit \"${STUB_PYTHON_RC:-0}\"'}\n",
    )

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "STOCK_RESEARCH_ROOT": str(root),
            "STOCK_RESEARCH_PYTHON": str(python_stub),
            "EOD_AUTO_REPAIR_DISABLE_FLOCK": "0" if flock_body is not None else "1",
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
    assert "command -v flock" in script
    assert "LOCK_MODE=" in script
    assert "python_lockfile" in script
    assert "stock_cron_guard.sh" in script
    assert 'LOCK_FILE="$ROOT/.locks/eod_auto_repair.lock"' in script
    assert 'mkdir "$LOCK_FILE"' in script
    assert "eod_auto_repair|locked|lock_mode|" in script
    assert "--mode loop" in script
    assert "--action-timeout-seconds" in script
    assert 'ACTION_TIMEOUT_SECONDS="${EOD_AUTO_REPAIR_ACTION_TIMEOUT_SECONDS:-43200}"' in script
    assert "logs/eod_auto_repair" in script
    assert "run_summary.json" in script
    assert "run_report.md" in script
    assert "lock_mode|$LOCK_MODE" in script


def test_eod_auto_repair_cron_uses_flock_when_available(tmp_path):
    root, env = _make_cron_harness(
        tmp_path,
        flock_body="exit 0",
    )

    result = _run_cron(env, "2026-07-02")

    assert result.returncode == 0
    assert "flock|" in (root / "lock-command.log").read_text()
    log_text = (root / "logs" / "eod_auto_repair" / "2026-07-02.log").read_text()
    assert "eod_auto_repair|lock_mode|flock" in log_text
    assert "--mode loop" in (root / "python.log").read_text()
    assert "--action-timeout-seconds" in (root / "python.log").read_text()
    assert "-X POST http://127.0.0.1:8765/api/dashboard/cache/clear" in (root / "curl.log").read_text()
    assert "eod_auto_repair|dashboard_cache_clear|success" in log_text
    assert (root / "sync.log").read_text().strip() == (
        f"sync|date=2026-07-02|root={root}"
    )
    calls = (root / "python.log").read_text()
    assert calls.index("stock_research.eod_auto_repair") < calls.index("stock_research.platform_ready")
    assert calls.index("stock_research.platform_ready") < calls.index("validate_strategy_release.py")
    assert "EOD自动修复完成" in result.stdout
    assert "交易日: 2026-07-02" in result.stdout
    assert "详细日志:" in result.stdout
    assert "eod_auto_repair|" not in result.stdout


def test_eod_auto_repair_cron_cache_clear_can_use_dashboard_auth(tmp_path):
    root, env = _make_cron_harness(
        tmp_path,
        extra_env={
            "DASHBOARD_AUTH_USERNAME": "admin",
            "DASHBOARD_AUTH_PASSWORD": "1234",
            "DASHBOARD_WRITE_TOKEN": "secret-token",
        },
    )

    result = _run_cron(env, "2026-07-02")

    assert result.returncode == 0
    curl_log = (root / "curl.log").read_text()
    assert "/api/auth/login" in curl_log
    assert '{"username":"admin","password":"1234"}' in curl_log
    assert "-b " in curl_log
    assert "X-Dashboard-Write-Token: secret-token" in curl_log
    assert "-X POST http://127.0.0.1:8765/api/dashboard/cache/clear" in curl_log


def test_eod_auto_repair_cron_loads_dashboard_password_from_keychain(tmp_path):
    root, env = _make_cron_harness(
        tmp_path,
        extra_env={
            "DASHBOARD_AUTH_USERNAME": "eod_repair",
            "DASHBOARD_AUTH_KEYCHAIN_SERVICE": "stock-research-dashboard-eod-repair",
        },
    )
    _write_executable(
        tmp_path / "bin" / "security",
        "#!/usr/bin/env bash\n"
        'echo "security|$*" >> "$STOCK_RESEARCH_ROOT/security.log"\n'
        'printf "%s\\n" "keychain-secret"\n',
    )

    result = _run_cron(env, "2026-07-02")

    assert result.returncode == 0
    assert "find-generic-password -s stock-research-dashboard-eod-repair -a eod_repair -w" in (
        root / "security.log"
    ).read_text()
    curl_log = (root / "curl.log").read_text()
    assert "/api/auth/login" in curl_log
    assert '{"username":"eod_repair","password":"keychain-secret"}' in curl_log


def test_eod_auto_repair_cron_does_not_clear_cache_or_sync_when_readiness_is_not_ready(tmp_path):
    root, env = _make_cron_harness(
        tmp_path,
        extra_env={"STUB_READY_STATUS": "degraded_ready"},
    )

    result = _run_cron(env, "2026-07-02")

    assert result.returncode != 0
    curl_log = root / "curl.log"
    assert not curl_log.exists() or "/api/dashboard/cache/clear" not in curl_log.read_text()
    assert not (root / "sync.log").exists()


def test_eod_auto_repair_cron_does_not_clear_cache_or_sync_when_contract_is_invalid(tmp_path):
    root, env = _make_cron_harness(
        tmp_path,
        extra_env={"STUB_CONTRACT_RC": "2"},
    )

    result = _run_cron(env, "2026-07-02")

    assert result.returncode == 2
    curl_log = root / "curl.log"
    assert not curl_log.exists() or "/api/dashboard/cache/clear" not in curl_log.read_text()
    assert not (root / "sync.log").exists()


def test_eod_auto_repair_cron_does_not_sync_when_cache_clear_fails(tmp_path):
    root, env = _make_cron_harness(
        tmp_path,
        extra_env={"STUB_CURL_RC": "22"},
    )

    result = _run_cron(env, "2026-07-02")

    assert result.returncode != 0
    assert "/api/dashboard/cache/clear" in (root / "curl.log").read_text()
    assert not (root / "sync.log").exists()


def test_eod_auto_repair_cron_logs_flock_lock_mode_when_already_locked(tmp_path):
    root, env = _make_cron_harness(
        tmp_path,
        flock_body="exit 1",
    )

    result = _run_cron(env, "2026-07-02")

    assert result.returncode == 0
    log_text = (root / "logs" / "eod_auto_repair" / "2026-07-02.log").read_text()
    assert "eod_auto_repair|locked|lock_mode|flock" in log_text
    assert not (root / "python.log").exists()


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
    assert "EOD自动修复失败" in result.stdout
    assert "交易日: 2026-07-02" in result.stdout
    assert "退出码: 7" in result.stdout
    assert "详细日志:" in result.stdout
    assert not lock_file.exists()
    assert "-m stock_research.eod_auto_repair" in (root / "python.log").read_text()
    assert "--mode loop" in (root / "python.log").read_text()
    assert "--action-timeout-seconds" in (root / "python.log").read_text()
    log = root / "logs" / "eod_auto_repair" / f"{trade_date}.log"
    log_text = log.read_text()
    assert "eod_auto_repair|lock_mode|python_lockfile" in log_text
    assert "eod_auto_repair|locked" not in log_text
    assert f"eod_auto_repair|summary|{root}/outputs/research/eod_auto_repair/{trade_date}/run_summary.json" in log_text
    assert f"eod_auto_repair|report|{root}/outputs/research/eod_auto_repair/{trade_date}/run_report.md" in log_text
    proxy_log = root / "proxy.log"
    assert not proxy_log.exists() or proxy_log.read_text() == ""
    curl_log = root / "curl.log"
    assert not curl_log.exists() or "/api/dashboard/cache/clear" not in curl_log.read_text()
    assert not (root / "sync.log").exists()


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
    assert "eod_auto_repair|locked|lock_mode|python_lockfile" in log_text


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
