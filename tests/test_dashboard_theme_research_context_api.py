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

