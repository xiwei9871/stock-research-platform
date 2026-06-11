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
    assert "lhb_shortline" in script
    assert "mid_trend" in script
    assert "tech_bottleneck" in script
    assert "lhb_shortline_combo_v1" not in script
    assert "Research Cockpit" in script
    assert "TOPN" in script


def test_dashboard_deployment_runbook_documents_version_and_database_checks() -> None:
    runbook = read_repo_file("docs/deployment-dashboard.md")

    assert "origin/dashboard" in runbook
    assert "2d2f223" in runbook
    assert "stock_research" in runbook
    assert "stock_hfq" in runbook
    assert "stock_qfq" in runbook
    assert "Run Fresh Backtest" in runbook
    assert "Load Cached Replay" in runbook
    assert "回滚" in runbook
