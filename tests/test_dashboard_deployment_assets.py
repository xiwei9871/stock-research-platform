from pathlib import Path


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
    assert "/api/platform/summary" in script
    assert "/api/backtests/strategies" in script
    assert "/api/assets/000001.SZ/profile" in script
    assert "Research Cockpit" in script
    assert "TOPN" in script


def test_fast_dashboard_sync_script_uses_mounted_source_restart_path() -> None:
    script = read_repo_file("deploy/sync_dashboard_fast.sh")

    assert "pnpm build" in script
    assert "dashboard/dist/" in script
    assert "STRATEGY_OUTPUT_ROOT" in script
    assert "outputs/research" in script
    assert "strategy_daily_eod" in script
    assert "docker compose restart api dashboard" in script
    assert "REBUILD=1" in script
    assert "docker compose build api dashboard" in script


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
