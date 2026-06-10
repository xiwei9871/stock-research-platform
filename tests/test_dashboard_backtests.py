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
    assert set(by_id) >= {
        "manual_v1_topn_rotation",
        "lhb_shortline",
        "mid_trend",
        "tech_bottleneck",
        "position_control",
    }
    assert {
        by_id[key]["status"]
        for key in by_id
        if key
        in {
            "manual_v1_topn_rotation",
            "lhb_shortline",
            "mid_trend",
            "tech_bottleneck",
            "position_control",
        }
    } == {"runnable"}


def test_load_vectorized_topn_prices_queries_market_daily_bar_directly(monkeypatch):
    calls = []
    expected_rows = [
        {
            "trade_date": "2026-06-02",
            "asset_id": "A",
            "open": 10.0,
            "close": 10.5,
            "amount": 1000000.0,
            "trade_status": "1",
            "is_limit_up": False,
            "is_limit_down": False,
            "is_suspended": False,
        }
    ]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_fetch_all(conn, sql, params):
        calls.append({"conn": conn, "sql": sql, "params": params})
        return expected_rows

    monkeypatch.setattr(backtests, "connect", lambda service: FakeConnection(), raising=False)
    monkeypatch.setattr(backtests, "fetch_all", fake_fetch_all, raising=False)
    monkeypatch.setattr(
        backtests,
        "load_vectorized_topn_inputs",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("unexpected score query")),
        raising=False,
    )

    prices = backtests.load_vectorized_topn_prices(
        start_date="2026-06-01",
        end_date="2026-06-05",
        adjust_type="hfq",
    )

    assert prices.to_dict("records") == expected_rows
    assert len(calls) == 1
    assert "FROM market_daily_bar" in calls[0]["sql"]
    assert "stock_score_daily" not in calls[0]["sql"]
    assert "false AS is_limit_up" in calls[0]["sql"]
    assert "false AS is_limit_down" in calls[0]["sql"]
    assert "trade_status <> '1' AS is_suspended" in calls[0]["sql"]
    assert "ORDER BY trade_date, asset_id" in calls[0]["sql"]
    assert calls[0]["params"] == ["hfq", "2026-06-01", "2026-06-05"]


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

    def fake_load_prices(**kwargs):
        calls["prices"] = kwargs
        return pd.DataFrame([{"trade_date": "2026-06-02", "asset_id": "A", "close": 10.5}])

    def fake_run_backtest(scores, prices, config):
        calls["scores"] = scores
        calls["price_frame"] = prices
        calls["config"] = config
        return result

    class FakeAdapter:
        strategy_id = "manual_v1_topn_rotation"

        def load_scores(self, params):
            calls["params"] = params
            return pd.DataFrame(
                [
                    {
                        "trade_date": "2026-06-01",
                        "asset_id": "A",
                        "rank": 1,
                        "score_total": 90.0,
                    }
                ]
            )

    monkeypatch.setitem(
        backtests.STRATEGY_BACKTEST_REGISTRY,
        "manual_v1_topn_rotation",
        FakeAdapter(),
    )
    monkeypatch.setattr(backtests, "load_vectorized_topn_prices", fake_load_prices)
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

    assert calls["prices"] == {
        "start_date": "2026-06-01",
        "end_date": "2026-06-05",
        "adjust_type": "hfq",
    }
    assert calls["params"].start_date == "2026-06-01"
    assert calls["params"].end_date == "2026-06-05"
    assert calls["params"].score_version == "manual_v1"
    assert calls["params"].adjust_type == "hfq"
    assert calls["scores"].to_dict("records") == [
        {
            "trade_date": "2026-06-01",
            "asset_id": "A",
            "rank": 1,
            "score_total": 90.0,
        }
    ]
    assert calls["price_frame"].to_dict("records") == [
        {"trade_date": "2026-06-02", "asset_id": "A", "close": 10.5}
    ]
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


def test_run_backtest_rejects_unknown_strategy():
    try:
        backtests.run_backtest(
            {
                "strategy_id": "unknown_strategy",
                "start_date": "2026-06-01",
                "end_date": "2026-06-05",
            }
        )
    except ValueError as exc:
        assert "unsupported strategy" in str(exc)
    else:
        raise AssertionError("expected unknown strategy to raise ValueError")


def test_run_backtest_routes_lhb_strategy_through_adapter(monkeypatch):
    calls = {}
    result = VectorizedTopNResult(
        config=VectorizedTopNConfig(start_date="2026-06-01", end_date="2026-06-05", top_n=2),
        equity_curve=pd.DataFrame([{"date": "2026-06-02", "equity": 1.01, "drawdown": 0.0}]),
        positions=pd.DataFrame(
            [
                {
                    "rebalance_date": "2026-06-01",
                    "asset_id": "A",
                    "rank": 1,
                    "score_total": 90.0,
                    "weight": 0.5,
                }
            ]
        ),
        trades=pd.DataFrame([{"execution_date": "2026-06-02", "asset_id": "A", "side": "buy"}]),
        summary={"total_return": 0.01, "max_drawdown": 0.0},
    )

    class FakeAdapter:
        strategy_id = "lhb_shortline"

        def load_scores(self, params):
            calls["params"] = params
            return pd.DataFrame(
                [
                    {
                        "trade_date": "2026-06-01",
                        "asset_id": "A",
                        "rank": 1,
                        "score_total": 90.0,
                    }
                ]
            )

    monkeypatch.setitem(backtests.STRATEGY_BACKTEST_REGISTRY, "lhb_shortline", FakeAdapter())
    monkeypatch.setattr(backtests, "load_vectorized_topn_prices", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr(backtests, "run_vectorized_topn_backtest", lambda scores, prices, config: result)

    payload = backtests.run_backtest(
        {
            "strategy_id": "lhb_shortline",
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

    assert calls["params"].start_date == "2026-06-01"
    assert payload["strategy_id"] == "lhb_shortline"
    assert payload["strategy_name"] == "LHB Shortline"


def test_json_safe_conversion_handles_common_pandas_and_scalar_values():
    assert backtests.to_json_safe(pd.Timestamp("2026-06-02 13:45:00")) == "2026-06-02T13:45:00"
    assert backtests.to_json_safe(float("nan")) is None
    assert backtests.to_json_safe(pd.NA) is None
    assert backtests.to_json_safe({"value": math.inf}) == {"value": None}
    assert backtests.to_json_safe(pd.Series([1, pd.NA])) == [1, None]


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


def test_backtest_run_route_rejects_missing_required_fields():
    client = TestClient(dashboard_app.create_app())

    response = client.post(
        "/api/backtests/run",
        json={"strategy_id": "manual_v1_topn_rotation"},
    )

    assert response.status_code == 400


def test_run_backtest_validates_config_before_loading_inputs(monkeypatch):
    calls = []

    monkeypatch.setattr(
        backtests,
        "load_vectorized_topn_prices",
        lambda **kwargs: calls.append(kwargs) or pd.DataFrame(),
    )

    try:
        backtests.run_backtest(
            {
                "strategy_id": "manual_v1_topn_rotation",
                "start_date": "2026-06-01",
                "end_date": "2026-06-05",
                "top_n": 0,
                "rebalance_frequency": "daily",
                "transaction_cost_bps": "inf",
                "max_positions": 0,
            }
        )
    except ValueError as exc:
        assert "top_n" in str(exc)
    else:
        raise AssertionError("expected invalid config to raise ValueError")

    assert calls == []
