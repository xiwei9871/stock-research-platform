import math

import pandas as pd
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import backtests
from stock_research.vectorized_topn_backtest import (
    VectorizedTopNConfig,
    VectorizedTopNResult,
)


def test_list_backtest_strategies_returns_strategy_catalog_rows():
    rows = backtests.list_backtest_strategies()

    by_id = {row["strategy_id"]: row for row in rows}
    assert by_id["manual_v1_topn_rotation"]["status"] == "runnable"
    assert by_id["manual_v1_topn_rotation"]["primary_action"] == "Run backtest"
    assert by_id["lhb_shortline"]["status"] == "replay_only"


def test_run_topn_backtest_loads_inputs_and_returns_json_safe_payload(monkeypatch):
    calls = {}
    result = VectorizedTopNResult(
        config=VectorizedTopNConfig(
            start_date="2026-06-01",
            end_date="2026-06-05",
            top_n=2,
            rebalance_frequency="daily",
            transaction_cost_bps=10.0,
            max_positions=2,
        ),
        equity_curve=pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2026-06-02"),
                    "equity": 1.02,
                    "drawdown": pd.NA,
                    "turnover": float("nan"),
                    "net_return": 0.02,
                }
            ]
        ),
        positions=pd.DataFrame(
            [
                {
                    "rebalance_date": pd.Timestamp("2026-06-01"),
                    "asset_id": "A",
                    "rank": 1,
                    "score_total": 90,
                    "weight": 0.5,
                }
            ]
        ),
        trades=pd.DataFrame(
            [
                {
                    "execution_date": pd.Timestamp("2026-06-02"),
                    "asset_id": "A",
                    "side": "buy",
                    "executed_weight": 0.5,
                }
            ]
        ),
        summary={
            "total_return": 0.02,
            "max_drawdown": float("nan"),
            "average_turnover": pd.NA,
            "periods": 1,
        },
    )

    def fake_load_inputs(**kwargs):
        calls["inputs"] = kwargs
        return pd.DataFrame(), pd.DataFrame()

    def fake_run_backtest(scores, prices, config):
        calls["config"] = config
        return result

    monkeypatch.setattr(backtests, "load_vectorized_topn_inputs", fake_load_inputs)
    monkeypatch.setattr(backtests, "run_vectorized_topn_backtest", fake_run_backtest)

    payload = backtests.run_backtest(
        {
            "strategy_id": "manual_v1_topn_rotation",
            "start_date": "2026-06-01",
            "end_date": "2026-06-05",
            "top_n": 2,
            "rebalance_frequency": "daily",
            "transaction_cost_bps": 10,
            "max_positions": 2,
            "score_version": "manual_v1",
            "adjust_type": "hfq",
        }
    )

    assert calls["inputs"] == {
        "start_date": "2026-06-01",
        "end_date": "2026-06-05",
        "score_version": "manual_v1",
        "adjust_type": "hfq",
    }
    assert calls["config"] == VectorizedTopNConfig(
        start_date="2026-06-01",
        end_date="2026-06-05",
        top_n=2,
        rebalance_frequency="daily",
        transaction_cost_bps=10.0,
        max_positions=2,
    )
    assert payload["strategy_id"] == "manual_v1_topn_rotation"
    assert payload["strategy_name"] == "Manual V1 TopN Rotation"
    assert payload["read_only"] is True
    assert payload["config"]["adjust_type"] == "hfq"
    assert payload["summary"]["total_return"] == 0.02
    assert payload["summary"]["max_drawdown"] is None
    assert payload["summary"]["average_turnover"] is None
    assert payload["equity_curve"][0]["date"] == "2026-06-02"
    assert payload["equity_curve"][0]["turnover"] is None
    assert payload["positions"][0]["rebalance_date"] == "2026-06-01"
    assert payload["trades"][0]["execution_date"] == "2026-06-02"


def test_run_backtest_rejects_unsupported_strategy():
    try:
        backtests.run_backtest({"strategy_id": "lhb_shortline"})
    except ValueError as exc:
        assert "manual_v1_topn_rotation" in str(exc)
    else:
        raise AssertionError("expected unsupported strategy to raise ValueError")


def test_json_safe_conversion_handles_common_pandas_and_scalar_values():
    assert backtests.to_json_safe(pd.Timestamp("2026-06-02 13:45:00")) == "2026-06-02T13:45:00"
    assert backtests.to_json_safe(float("nan")) is None
    assert backtests.to_json_safe(pd.NA) is None
    assert backtests.to_json_safe({"value": math.inf}) == {"value": None}


def test_backtest_routes(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "list_backtest_strategies",
        lambda: [{"strategy_id": "manual_v1_topn_rotation"}],
    )
    monkeypatch.setattr(
        dashboard_app,
        "run_backtest",
        lambda payload: {"strategy_id": payload["strategy_id"], "read_only": True},
    )
    client = TestClient(dashboard_app.create_app())

    strategies = client.get("/api/backtests/strategies")
    result = client.post(
        "/api/backtests/run",
        json={
            "strategy_id": "manual_v1_topn_rotation",
            "start_date": "2026-06-01",
            "end_date": "2026-06-05",
            "top_n": 2,
            "rebalance_frequency": "daily",
            "transaction_cost_bps": 10,
            "max_positions": 2,
            "score_version": "manual_v1",
            "adjust_type": "hfq",
        },
    )

    assert strategies.status_code == 200
    assert strategies.json()["items"][0]["strategy_id"] == "manual_v1_topn_rotation"
    assert result.status_code == 200
    assert result.json()["read_only"] is True


def test_backtest_run_route_maps_value_error_to_400(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "run_backtest",
        lambda payload: (_ for _ in ()).throw(ValueError("unsupported strategy")),
    )
    client = TestClient(dashboard_app.create_app())

    response = client.post("/api/backtests/run", json={"strategy_id": "lhb_shortline"})

    assert response.status_code == 400
    assert response.json()["detail"] == "unsupported strategy"
