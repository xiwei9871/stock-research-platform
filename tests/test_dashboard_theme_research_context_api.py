from __future__ import annotations

from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app


def test_asset_theme_research_context_endpoint_uses_read_model(monkeypatch) -> None:
    expected = {
        "asset_id": "CN:SZ:002837",
        "company_code": "002837.SZ",
        "status": "reviewed_context_available",
        "themes": [{"theme_id": "ai_power_value_capture_v1"}],
        "mappings": [],
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
    }
    monkeypatch.setattr(
        dashboard_app,
        "load_asset_theme_context",
        lambda asset_id: {**expected, "asset_id": asset_id},
    )

    response = TestClient(dashboard_app.create_app()).get(
        "/api/assets/CN:SZ:002837/theme-research-context"
    )

    assert response.status_code == 200
    assert response.json() == expected


def test_theme_research_updates_endpoint_validates_query(monkeypatch) -> None:
    monkeypatch.setattr(
        dashboard_app,
        "list_theme_research_updates",
        lambda since=None, limit=100: {
            "total": 1,
            "items": [{"update_id": "review-1", "created_at": since}],
            "limit": limit,
            "research_only": True,
            "used_for_signal": False,
            "used_for_admission": False,
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/research/theme-decomposition/updates?since=2026-07-10&limit=20"
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["created_at"] == "2026-07-10"
    assert response.json()["limit"] == 20


def test_theme_research_updates_endpoint_returns_400_for_non_numeric_limit() -> None:
    response = TestClient(dashboard_app.create_app()).get(
        "/api/research/theme-decomposition/updates?limit=abc"
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "theme_research_limit_invalid"


def test_theme_research_read_endpoints_return_structured_service_errors(monkeypatch) -> None:
    def unavailable(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(dashboard_app, "load_asset_theme_context", unavailable)
    monkeypatch.setattr(dashboard_app, "list_theme_research_updates", unavailable)
    client = TestClient(dashboard_app.create_app(), raise_server_exceptions=False)

    asset_response = client.get("/api/assets/CN:SZ:002837/theme-research-context")
    updates_response = client.get("/api/research/theme-decomposition/updates")

    for response in (asset_response, updates_response):
        assert response.status_code == 503
        assert response.json()["detail"] == {
            "status": "error",
            "error_code": "theme_research_service_unavailable",
            "message": "Theme Research read service is unavailable",
        }
