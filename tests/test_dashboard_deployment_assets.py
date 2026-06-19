from pathlib import Path
import stat


REPO_ROOT = Path(__file__).resolve().parents[1]


def read_repo_file(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_dashboard_deployment_templates_define_api_and_spa_routes() -> None:
    nginx_conf = read_repo_file("deploy/nginx/stock-dashboard.conf")
    service = read_repo_file("deploy/systemd/stock-research-dashboard-api.service")

    assert "server_name stock.manqiaotechnology.com" in nginx_conf
    assert "location /api/" in nginx_conf
    assert "proxy_pass http://127.0.0.1:8765" in nginx_conf
    assert "try_files $uri $uri/ /index.html" in nginx_conf
    assert "proxy_read_timeout 180s" in nginx_conf

    assert "WorkingDirectory=/opt/stock_research" in service
    assert "Environment=PYTHONPATH=src" in service
    assert "stock_research.dashboard.app:app" in service
    assert "--host 127.0.0.1 --port 8765" in service


def test_dashboard_release_check_script_covers_live_endpoints() -> None:
    script = read_repo_file("deploy/check_dashboard_release.sh")

    assert "set -euo pipefail" in script
    assert "API_BASE" in script
    assert "FETCH_RETRIES" in script
    assert "FETCH_RETRY_SLEEP_SECONDS" in script
    assert "/api/platform/summary" in script
    assert "/api/backtests/strategies" in script
    assert "/api/backtests/jobs" in script
    assert "/api/assets/000001.SZ/profile" in script
    assert "Backtest Lab" in script
    assert "Market Monitor" in script
    assert "Data Explorer" in script
    assert "TOPN" in script


def test_fast_dashboard_sync_script_uses_mounted_source_restart_path() -> None:
    script = read_repo_file("deploy/sync_dashboard_fast.sh")

    assert "pnpm build" in script
    assert "dashboard/dist/" in script
    assert "STRATEGY_OUTPUT_ROOT" in script
    assert "LATEST_STRATEGY_DAILY_EOD" in script
    assert "find_latest_strategy_daily_eod" in script
    assert "outputs/research" in script
    assert "strategy_daily_eod" in script
    assert "strategy_daily_eod/2026-06-16" not in script
    assert "web_tech_bottleneck_v1_runs" in script
    assert "rsync -az -e \"ssh ${SSH_OPTS}\"" in script
    assert "docker compose restart api dashboard" in script
    assert "REBUILD=1" in script
    assert "docker compose build api dashboard" in script


def test_daily_dashboard_sync_wrapper_guards_and_verifies_release() -> None:
    script_path = REPO_ROOT / "deploy/sync_dashboard_daily.sh"
    script = read_repo_file("deploy/sync_dashboard_daily.sh")
    mode = script_path.stat().st_mode

    assert mode & stat.S_IXUSR
    assert "set -euo pipefail" in script
    assert "git diff-index --quiet HEAD --" in script
    assert "tmp/" in script
    assert "deploy/sync_dashboard_fast.sh" in script
    assert "deploy/check_dashboard_release.sh" in script
    assert "logs/dashboard_daily_sync.log" in script
    assert "mkdir \"$lock_dir\"" in script
    assert "trap 'rmdir \"$lock_dir\"' EXIT" in script
    assert "DASHBOARD_AUTH" in script
    assert "REMOTE_HOST" in script
    assert "192.168.3.185" in script
    assert "export REMOTE_USER REMOTE_HOST REMOTE_DIR SSH_OPTS REBUILD STRATEGY_OUTPUT_ROOT" in script
    assert "timestamp()" in script
    assert "date '+%Y-%m-%dT%H:%M:%S%z'" in script


def test_launchd_daily_dashboard_sync_runs_after_close() -> None:
    plist = read_repo_file("deploy/launchd/com.stockresearch.dashboard-daily-sync.plist")

    assert "com.stockresearch.dashboard-daily-sync" in plist
    assert "/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/deploy/sync_dashboard_daily.sh" in plist
    assert "<key>Hour</key>" in plist
    assert "<integer>18</integer>" in plist
    assert "<key>Minute</key>" in plist
    assert "<integer>30</integer>" in plist
    assert "dashboard_daily_sync.launchd.out.log" in plist
    assert "dashboard_daily_sync.launchd.err.log" in plist


def test_strategy_eod_publish_launchd_runs_at_display_cutoff() -> None:
    script_path = REPO_ROOT / "scripts/run_strategy_eod_publish_daily.sh"
    script = read_repo_file("scripts/run_strategy_eod_publish_daily.sh")
    plist = read_repo_file("deploy/launchd/com.stockresearch.strategy-eod-publish.plist")
    mode = script_path.stat().st_mode

    assert mode & stat.S_IXUSR
    assert "set -euo pipefail" in script
    assert "PYTHONPATH=src" in script
    assert "stock_research.strategy_eod_publish" in script
    assert "--trade-date" in script
    assert "logs/strategy_eod_publish_daily.log" in script

    assert "com.stockresearch.strategy-eod-publish" in plist
    assert "/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/scripts/run_strategy_eod_publish_daily.sh" in plist
    assert "<key>Hour</key>" in plist
    assert "<integer>20</integer>" in plist
    assert "<key>Minute</key>" in plist
    assert "<integer>30</integer>" in plist
    assert "strategy_eod_publish.launchd.out.log" in plist
    assert "strategy_eod_publish.launchd.err.log" in plist


def test_dashboard_deployment_runbook_documents_version_and_database_checks() -> None:
    runbook = read_repo_file("docs/deployment-dashboard.md")

    assert "origin/dashboard" in runbook
    assert "2d2f223" in runbook
    assert "stock_research" in runbook
    assert "stock_hfq" in runbook
    assert "stock_qfq" in runbook
    assert "Run Fresh Backtest" in runbook
    assert "Load Cached Replay" in runbook
    assert "Fast Docker Deploy On 192.168.3.185" in runbook
    assert "PYTHONPATH=/app/src" in runbook
    assert "/Users/xiwei/stock_research/outputs/research" in runbook
    assert "回滚" in runbook
