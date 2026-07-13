from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard.auth_models import CurrentUser


def test_dashboard_api_allows_reads_when_auth_not_required(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED", "false")
    monkeypatch.setattr(dashboard_app, "load_platform_summary", lambda **kwargs: {"latest_market_date": "2026-07-08"})
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/platform/summary")

    assert response.status_code == 200


def test_dashboard_api_rejects_reads_when_auth_required_and_missing_session(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED", "true")
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/platform/summary")

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"


def test_dashboard_api_allows_reads_when_auth_required_and_session_valid(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED", "true")
    monkeypatch.setattr(
        dashboard_app,
        "load_current_user_from_session",
        lambda token: CurrentUser("user:1", "admin", "Admin", "admin", True) if token == "session" else None,
    )
    monkeypatch.setattr(dashboard_app, "load_platform_summary", lambda **kwargs: {"latest_market_date": "2026-07-08"})
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/platform/summary", cookies={"stock_research_session": "session"})

    assert response.status_code == 200


def test_dashboard_api_allows_auth_routes_when_auth_required(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_AUTH_REQUIRED", "true")
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"
