import pandas as pd
import pytest

import stock_research.vectorized_topn_backtest as vectorized_topn_backtest
from stock_research.vectorized_topn_backtest import (
    VectorizedTopNConfig,
    load_vectorized_topn_inputs,
    run_vectorized_topn_backtest,
)


def _scores(rows: list[tuple[str, str, int, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": trade_date,
                "asset_id": asset_id,
                "rank": rank,
                "score_total": score,
            }
            for trade_date, asset_id, rank, score in rows
        ]
    )


def _prices(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": trade_date, "asset_id": asset_id, "close": close}
            for trade_date, asset_id, close in rows
        ]
    )


def test_run_vectorized_topn_backtest_daily_rebalances_topn_with_costs():
    scores = _scores(
        [
            ("2026-01-01", "A", 1, 90.0),
            ("2026-01-01", "B", 2, 80.0),
            ("2026-01-01", "C", 3, 70.0),
            ("2026-01-02", "B", 1, 95.0),
            ("2026-01-02", "C", 2, 85.0),
            ("2026-01-02", "A", 3, 75.0),
        ]
    )
    prices = _prices(
        [
            ("2026-01-01", "A", 10.0),
            ("2026-01-01", "B", 20.0),
            ("2026-01-01", "C", 30.0),
            ("2026-01-02", "A", 11.0),
            ("2026-01-02", "B", 18.0),
            ("2026-01-02", "C", 30.0),
            ("2026-01-03", "A", 11.0),
            ("2026-01-03", "B", 19.8),
            ("2026-01-03", "C", 30.0),
        ]
    )
    config = VectorizedTopNConfig(
        start_date="2026-01-01",
        end_date="2026-01-03",
        top_n=2,
        rebalance_frequency="daily",
        transaction_cost_bps=10.0,
    )

    result = run_vectorized_topn_backtest(scores, prices, config)

    assert list(result.equity_curve["date"]) == ["2026-01-02", "2026-01-03"]
    assert list(result.equity_curve["turnover"]) == pytest.approx([1.0, 1.0])
    assert list(result.equity_curve["gross_return"]) == pytest.approx([0.0, 0.05])
    assert list(result.equity_curve["transaction_cost"]) == pytest.approx([0.001, 0.001])
    assert list(result.equity_curve["net_return"]) == pytest.approx([-0.001, 0.049])
    assert result.equity_curve.iloc[-1]["equity"] == pytest.approx(0.999 * 1.049)

    positions = result.positions.sort_values(["rebalance_date", "asset_id"])
    assert list(positions["rebalance_date"]) == [
        "2026-01-01",
        "2026-01-01",
        "2026-01-02",
        "2026-01-02",
    ]
    assert list(positions["asset_id"]) == ["A", "B", "B", "C"]
    assert list(positions["weight"]) == pytest.approx([0.5, 0.5, 0.5, 0.5])
    assert result.summary["total_return"] == pytest.approx(0.999 * 1.049 - 1.0)


def test_run_vectorized_topn_backtest_weekly_rebalances_first_available_week_date():
    scores = _scores(
        [
            ("2026-01-05", "A", 1, 90.0),
            ("2026-01-05", "B", 2, 80.0),
            ("2026-01-06", "C", 1, 95.0),
            ("2026-01-06", "B", 2, 85.0),
        ]
    )
    prices = _prices(
        [
            ("2026-01-05", "A", 10.0),
            ("2026-01-05", "B", 20.0),
            ("2026-01-05", "C", 30.0),
            ("2026-01-06", "A", 11.0),
            ("2026-01-06", "B", 20.0),
            ("2026-01-06", "C", 60.0),
            ("2026-01-07", "A", 12.1),
            ("2026-01-07", "B", 20.0),
            ("2026-01-07", "C", 120.0),
        ]
    )
    config = VectorizedTopNConfig(
        start_date="2026-01-05",
        end_date="2026-01-07",
        top_n=1,
        rebalance_frequency="weekly",
    )

    result = run_vectorized_topn_backtest(scores, prices, config)

    assert list(result.positions["rebalance_date"]) == ["2026-01-05"]
    assert list(result.positions["asset_id"]) == ["A"]
    assert list(result.equity_curve["date"]) == ["2026-01-06", "2026-01-07"]
    assert list(result.equity_curve["gross_return"]) == pytest.approx([0.10, 0.10])
    assert result.equity_curve.iloc[-1]["equity"] == pytest.approx(1.21)


def test_run_vectorized_topn_backtest_caps_holdings_with_max_positions():
    scores = _scores(
        [
            ("2026-01-01", "A", 1, 90.0),
            ("2026-01-01", "B", 2, 80.0),
            ("2026-01-01", "C", 3, 70.0),
        ]
    )
    prices = _prices(
        [
            ("2026-01-01", "A", 10.0),
            ("2026-01-01", "B", 20.0),
            ("2026-01-01", "C", 30.0),
            ("2026-01-02", "A", 11.0),
            ("2026-01-02", "B", 22.0),
            ("2026-01-02", "C", 33.0),
        ]
    )
    config = VectorizedTopNConfig(
        start_date="2026-01-01",
        end_date="2026-01-02",
        top_n=3,
        max_positions=2,
    )

    result = run_vectorized_topn_backtest(scores, prices, config)

    assert list(result.positions["asset_id"]) == ["A", "B"]
    assert list(result.positions["weight"]) == pytest.approx([0.5, 0.5])
    assert result.equity_curve.iloc[0]["holdings_count"] == 2


def test_load_vectorized_topn_inputs_queries_scores_and_prices(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        if "factor.stock_score_daily" in sql:
            return [
                {
                    "trade_date": "2026-01-01",
                    "asset_id": "A",
                    "rank": 1,
                    "score_total": 90.0,
                }
            ]
        return [{"trade_date": "2026-01-01", "asset_id": "A", "close": 10.0}]

    monkeypatch.setattr(
        vectorized_topn_backtest,
        "connect",
        lambda service: _context(object()),
    )
    monkeypatch.setattr(vectorized_topn_backtest, "fetch_all", fake_fetch_all)

    scores, prices = load_vectorized_topn_inputs(
        start_date="2026-01-01",
        end_date="2026-01-31",
        score_version="manual_v1",
        adjust_type="hfq",
    )

    assert scores.iloc[0]["score_total"] == 90.0
    assert prices.iloc[0]["close"] == 10.0
    assert "FROM factor.stock_score_daily" in calls[0][0]
    assert calls[0][1] == ["manual_v1", "2026-01-01", "2026-01-31"]
    assert "FROM market_daily_bar" in calls[1][0]
    assert calls[1][1] == ["hfq", "2026-01-01", "2026-01-31"]


class _context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False
