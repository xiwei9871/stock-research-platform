from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app


def test_dashboard_api_adds_request_id_header(monkeypatch):
    monkeypatch.setattr(dashboard_app, "load_platform_summary", lambda **kwargs: {"latest_market_date": "2026-07-06"})
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/platform/summary")

    assert response.status_code == 200
    assert response.headers["x-request-id"]


def test_dashboard_api_echoes_agent_run_id_header(monkeypatch):
    monkeypatch.setattr(dashboard_app, "load_platform_summary", lambda **kwargs: {"latest_market_date": "2026-07-06"})
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/platform/summary", headers={"X-Agent-Run-ID": "agent_run:test"})

    assert response.status_code == 200
    assert response.headers["x-agent-run-id"] == "agent_run:test"
