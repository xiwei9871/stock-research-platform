from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard.strategy_catalog import list_strategy_catalog


def test_strategy_catalog_marks_backtest_lab_strategies_as_runnable():
    rows = list_strategy_catalog()

    by_id = {row["strategy_id"]: row for row in rows}
    strategy_ids = {
        "manual_v1_topn_rotation",
        "lhb_shortline",
        "mid_trend",
        "tech_bottleneck",
        "position_control",
    }
    assert {by_id[strategy_id]["status"] for strategy_id in strategy_ids} == {"runnable"}
    assert {
        by_id[strategy_id]["primary_action"] for strategy_id in strategy_ids
    } == {"Run backtest"}
    assert "momentum" in by_id["manual_v1_topn_rotation"]["factor_groups"]


def test_strategy_catalog_route_returns_items():
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/strategies/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) >= 5
    assert payload["items"][0]["strategy_id"] == "manual_v1_topn_rotation"
