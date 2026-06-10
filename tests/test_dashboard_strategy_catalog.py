from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard.strategy_catalog import list_strategy_catalog


def test_strategy_catalog_marks_validated_combos_as_backtest_runnable():
    rows = list_strategy_catalog()

    by_id = {row["strategy_id"]: row for row in rows}
    strategy_ids = {
        "lhb_shortline",
        "mid_trend",
        "tech_bottleneck",
    }
    assert {by_id[strategy_id]["status"] for strategy_id in strategy_ids} == {"runnable"}
    assert {
        by_id[strategy_id]["primary_action"] for strategy_id in strategy_ids
    } == {"Run backtest"}
    assert by_id["manual_v1_topn_rotation"]["status"] == "diagnostic"
    assert by_id["manual_v1_topn_rotation"]["primary_action"] == "Internal baseline"
    assert by_id["position_control"]["status"] == "diagnostic"
    assert by_id["position_control"]["primary_action"] == "Internal overlay"


def test_strategy_catalog_describes_default_combos_in_user_language():
    rows = list_strategy_catalog()
    by_id = {row["strategy_id"]: row for row in rows}

    assert by_id["lhb_shortline"]["strategy_name"] == "LHB Shortline Combo"
    assert "龙虎榜资金行为" in by_id["lhb_shortline"]["description"]
    assert "龙虎榜净买占比" in by_id["lhb_shortline"]["signal_inputs"]
    assert "涨停失败风险" in by_id["lhb_shortline"]["signal_inputs"]
    assert "2026区间净值 1.6341" in by_id["lhb_shortline"]["latest_evidence"]

    assert by_id["mid_trend"]["strategy_name"] == "Mid Trend Combo"
    assert "中期趋势股票池" in by_id["mid_trend"]["description"]
    assert "20日趋势强度" in by_id["mid_trend"]["signal_inputs"]
    assert "每周最多替换2只" in by_id["mid_trend"]["signal_inputs"]
    assert "2026区间净值 1.5599" in by_id["mid_trend"]["latest_evidence"]

    assert by_id["tech_bottleneck"]["strategy_name"] == "Tech Bottleneck Combo"
    assert "技术形态" in by_id["tech_bottleneck"]["description"]
    assert "技术瓶颈形态" in by_id["tech_bottleneck"]["signal_inputs"]
    assert "假突破过滤" in by_id["tech_bottleneck"]["signal_inputs"]
    assert "2026区间净值 1.2351" in by_id["tech_bottleneck"]["latest_evidence"]

    public_text = " ".join(
        str(value)
        for strategy_id in ["lhb_shortline", "mid_trend", "tech_bottleneck"]
        for value in by_id[strategy_id].values()
    )
    for internal_token in [
        "Phase14C",
        "Phase15",
        "Phase16C",
        "report_mild_bonus",
        "C2",
        "tech_hard_filter",
        "top5_adaptive_daily_check_max2_v1",
    ]:
        assert internal_token not in public_text


def test_strategy_catalog_route_returns_items():
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/strategies/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) >= 5
    assert payload["items"][0]["strategy_id"] == "manual_v1_topn_rotation"
