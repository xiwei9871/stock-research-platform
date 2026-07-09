from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_nginx_example_documents_dashboard_static_api_proxy_and_spa_fallback():
    config = _read("deploy/nginx/stock_research_dashboard.conf.example")

    assert "root /opt/stock_research/dashboard/dist;" in config
    assert "location /api/" in config
    assert "proxy_pass http://127.0.0.1:8765" in config
    assert "try_files $uri /index.html" in config
    assert "proxy_set_header X-Forwarded-For" in config
    assert "proxy_set_header X-Forwarded-Proto" in config
    assert "proxy_set_header Host" in config
    assert "client_max_body_size" in config
    assert "gzip on;" in config
    assert "PostgreSQL" in config and "never exposed" in config
    assert "DASHBOARD_WRITE_TOKEN" in config and "frontend bundle" in config
    assert "WebSocket is not required" in config


def test_staging_basic_auth_nginx_example_protects_dashboard_and_api():
    config = _read("deploy/nginx/stock_research_dashboard.staging_basic_auth.conf.example")

    assert 'auth_basic "Stock Research staging";' in config
    assert "auth_basic_user_file /etc/nginx/.htpasswd-stock-research-dashboard;" in config
    assert "allow 203.0.113.0/24;" in config
    assert "deny all;" in config
    assert "root /opt/stock_research/dashboard/dist;" in config
    assert "location /api/" in config
    assert "proxy_pass http://127.0.0.1:8765" in config
    assert "try_files $uri /index.html" in config
    assert "proxy_set_header Host" in config
    assert "proxy_set_header X-Real-IP" in config
    assert "proxy_set_header X-Forwarded-For" in config
    assert "proxy_set_header X-Forwarded-Proto" in config
    assert "client_max_body_size" in config
    assert "PostgreSQL" in config and "never exposed" in config
    assert "Basic Auth is a temporary external access gate" in config
    assert "WebSocket is not required" in config


def test_systemd_and_env_examples_keep_api_local_and_secrets_server_side():
    service = _read("deploy/systemd/stock-research-api.service.example")
    env = _read("deploy/env/.env.dashboard.example")

    assert "ExecStart=/opt/stock_research/.venv/bin/stock-research dashboard-api" in service
    assert "EnvironmentFile=/etc/stock-research/dashboard.env" in service
    assert "WorkingDirectory=/opt/stock_research" in service
    assert "DASHBOARD_API_BIND_HOST=127.0.0.1" in env
    assert "DASHBOARD_API_BIND_PORT=8765" in env
    assert "PGSERVICEFILE=" in env
    assert "DASHBOARD_WRITE_TOKEN=" in env
    assert "server-only" in env
    assert "frontend bundle" in env
    assert "Do not bind FastAPI to 0.0.0.0" in env
    assert "Database port must not be opened to the public internet" in env


def test_external_access_runbook_covers_proxy_auth_guardrails_and_operations():
    runbook = _read("docs/platform_external_access_runbook.md")

    for expected in [
        "Nginx",
        "FastAPI",
        "dashboard/dist",
        "SPA fallback",
        "/api/",
        "X-Dashboard-Write-Token",
        "X-Request-ID",
        "PostgreSQL",
        "systemd",
        "readiness",
    ]:
        assert expected in runbook


def test_external_access_docs_include_first_party_auth_settings():
    env = _read("deploy/env/.env.dashboard.example")
    runbook = _read("docs/platform_external_access_runbook.md")

    assert "STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED=true" in env
    assert "STOCK_RESEARCH_DASHBOARD_COOKIE_SECURE=true" in env
    assert "STOCK_RESEARCH_DASHBOARD_SESSION_TTL_SECONDS" in env
    assert "dashboard-auth-init" in runbook
    assert "dashboard-admin-create" in runbook
    assert "first-party auth" in runbook


def test_auth_proxy_smoke_runbook_covers_manual_checklist_and_boundaries():
    runbook = _read("docs/platform_external_access_auth_proxy_smoke_runbook.md")

    for expected in [
        "staging/internal access",
        "Basic Auth",
        "IP allowlist",
        "not application role authorization",
        "SPA fallback",
        "/api/platform/summary",
        "X-Request-ID",
        "X-Dashboard-Write-Token",
        "wrong token",
        "Nginx access log",
        "systemd",
        "database port",
        "smoke_platform_external_access.py",
        "--check-first-party-auth",
        "--auth-username",
        "--check-admin-users",
        "/api/auth/me",
        "/api/admin/users",
        "first-party login view",
    ]:
        assert expected in runbook


def test_internal_auth_smoke_runbook_covers_internal_first_party_auth_mode():
    runbook = _read("docs/platform_internal_auth_smoke_runbook.md")

    for expected in [
        "internal network only",
        "STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED=true",
        "STOCK_RESEARCH_DASHBOARD_COOKIE_SECURE=false",
        "dashboard-auth-init",
        "dashboard-admin-create",
        "--internal",
        "--check-first-party-auth",
        "--check-admin-users",
        "--check-regular-user-admin-denied",
        "--regular-auth-username",
        "--check-write-guard",
        "Basic Auth is not required",
        "X-Dashboard-Write-Token",
        "regular user",
        "用户管理",
    ]:
        assert expected in runbook
