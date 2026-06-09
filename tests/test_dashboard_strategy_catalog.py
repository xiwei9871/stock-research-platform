from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard.strategy_catalog import list_strategy_catalog


def test_strategy_catalog_marks_only_manual_v1_topn_as_runnable():
    rows = list_strategy_catalog()

    by_id = {row["strategy_id"]: row for row in rows}
    assert by_id["manual_v1_topn_rotation"]["status"] == "runnable"
    assert by_id["manual_v1_topn_rotation"]["primary_action"] == "Run backtest"
    assert by_id["lhb_shortline"]["status"] == "replay_only"
    assert by_id["mid_trend"]["status"] == "replay_only"
    assert by_id["tech_bottleneck"]["status"] == "replay_only"
    assert by_id["position_control"]["status"] == "replay_only"
    assert "momentum" in by_id["manual_v1_topn_rotation"]["factor_groups"]


def test_strategy_catalog_route_returns_items():
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/strategies/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) >= 5
    assert payload["items"][0]["strategy_id"] == "manual_v1_topn_rotation"
