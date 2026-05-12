import pandas as pd
import pytest

from stock_research.performance_metrics import calc_performance_metrics


def test_calc_performance_metrics_reports_empyrical_style_metrics():
    equity_curve = pd.DataFrame(
        [
            {
                "date": "2026-01-02",
                "net_return": 0.10,
                "equity": 1.10,
                "drawdown": 0.0,
                "turnover": 1.0,
            },
            {
                "date": "2026-01-03",
                "net_return": -0.05,
                "equity": 1.045,
                "drawdown": -0.05,
                "turnover": 0.5,
            },
            {
                "date": "2026-01-04",
                "net_return": 0.02,
                "equity": 1.0659,
                "drawdown": -0.031,
                "turnover": 0.0,
            },
            {
                "date": "2026-01-05",
                "net_return": -0.01,
                "equity": 1.055241,
                "drawdown": -0.04069,
                "turnover": 0.25,
            },
        ]
    )
    positions = pd.DataFrame(
        [
            {"rebalance_date": "2026-01-01", "asset_id": "A", "weight": 0.5},
            {"rebalance_date": "2026-01-01", "asset_id": "B", "weight": 0.5},
            {"rebalance_date": "2026-01-03", "asset_id": "B", "weight": 0.5},
            {"rebalance_date": "2026-01-03", "asset_id": "C", "weight": 0.5},
        ]
    )

    metrics = calc_performance_metrics(equity_curve, positions, annualization=252)

    returns = pd.Series([0.10, -0.05, 0.02, -0.01], dtype=float)
    expected_annual_return = (1.055241 ** (252 / 4)) - 1.0
    expected_volatility = returns.std(ddof=1) * (252**0.5)
    expected_sharpe = returns.mean() / returns.std(ddof=1) * (252**0.5)
    downside = returns[returns < 0]
    expected_sortino = returns.mean() / downside.std(ddof=0) * (252**0.5)

    assert metrics["cumulative_return"] == pytest.approx(0.055241)
    assert metrics["annual_return"] == pytest.approx(expected_annual_return)
    assert metrics["annual_volatility"] == pytest.approx(expected_volatility)
    assert metrics["max_drawdown"] == pytest.approx(-0.05)
    assert metrics["sharpe_ratio"] == pytest.approx(expected_sharpe)
    assert metrics["sortino_ratio"] == pytest.approx(expected_sortino)
    assert metrics["calmar_ratio"] == pytest.approx(expected_annual_return / 0.05)
    assert metrics["win_rate"] == pytest.approx(0.5)
    assert metrics["average_holding_days"] == pytest.approx(2.0)
    assert metrics["annual_turnover"] == pytest.approx(0.4375 * 252)
    assert metrics["periods"] == 4


def test_calc_performance_metrics_handles_empty_equity_curve():
    metrics = calc_performance_metrics(pd.DataFrame(), pd.DataFrame())

    assert metrics["cumulative_return"] == 0.0
    assert metrics["periods"] == 0
    assert metrics["sharpe_ratio"] is None
    assert metrics["average_holding_days"] is None
