from pathlib import Path

import pandas as pd
import pytest

from stock_research import trend_candidate_backtest


def _candidate_scores() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "candidate_score": 90.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "candidate_score": 80.0},
            {"trade_date": "2026-01-02", "asset_id": "C", "candidate_score": 95.0},
            {"trade_date": "2026-01-02", "asset_id": "B", "candidate_score": 85.0},
            {"trade_date": "2026-01-05", "asset_id": "C", "candidate_score": 96.0},
            {"trade_date": "2026-01-05", "asset_id": "A", "candidate_score": 70.0},
        ]
    )


def _prices() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "close": 10.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "close": 20.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "close": 30.0},
            {"trade_date": "2026-01-02", "asset_id": "A", "close": 11.0},
            {"trade_date": "2026-01-02", "asset_id": "B", "close": 18.0},
            {"trade_date": "2026-01-02", "asset_id": "C", "close": 30.0},
            {"trade_date": "2026-01-05", "asset_id": "A", "close": 11.0},
            {"trade_date": "2026-01-05", "asset_id": "B", "close": 19.8},
            {"trade_date": "2026-01-05", "asset_id": "C", "close": 33.0},
            {"trade_date": "2026-01-06", "asset_id": "A", "close": 11.0},
            {"trade_date": "2026-01-06", "asset_id": "B", "close": 19.8},
            {"trade_date": "2026-01-06", "asset_id": "C", "close": 36.3},
        ]
    )


def test_run_fixed_holding_backtest_rebalances_only_after_holding_days_with_costs():
    config = trend_candidate_backtest.TrendCandidateBacktestConfig(
        start_date="2026-01-01",
        end_date="2026-01-06",
        top_n=1,
        holding_days=2,
        transaction_cost_bps=20.0,
    )

    result = trend_candidate_backtest.run_fixed_holding_backtest(
        _candidate_scores(),
        _prices(),
        config,
    )

    assert list(result.positions["rebalance_date"]) == ["2026-01-01", "2026-01-05"]
    assert list(result.positions["asset_id"]) == ["A", "C"]
    assert list(result.equity_curve["turnover"]) == pytest.approx([1.0, 0.0, 2.0])
    assert list(result.equity_curve["transaction_cost"]) == pytest.approx([0.002, 0.0, 0.004])
    assert list(result.equity_curve["gross_return"]) == pytest.approx([0.10, 0.0, 0.10])
    assert result.summary["rebalance_count"] == 2
    assert result.summary["average_holding_days"] == pytest.approx(2.0)


def test_run_trend_candidate_backtest_report_writes_grid_outputs(tmp_path: Path, monkeypatch):
    scores_path = tmp_path / "candidate_scores.csv"
    _candidate_scores().to_csv(scores_path, index=False)
    calls = []

    def fake_load_prices(**kwargs):
        calls.append(kwargs)
        return _prices()

    monkeypatch.setattr(trend_candidate_backtest, "load_candidate_backtest_prices", fake_load_prices)

    result = trend_candidate_backtest.run_trend_candidate_backtest_report(
        start_date="2026-01-01",
        end_date="2026-01-06",
        candidate_scores_path=scores_path,
        top_ns=(1, 2),
        holding_days=(2,),
        transaction_cost_bps=20.0,
        reports_dir=tmp_path,
    )

    assert calls[0]["start_date"] == "2026-01-01"
    assert calls[0]["end_date"] == "2026-01-06"
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["equity_curve"]).exists()
    assert Path(result["paths"]["positions"]).exists()
    assert Path(result["paths"]["trades"]).exists()
    assert "Trend Candidate Paper Backtest" in Path(result["paths"]["markdown_report"]).read_text(encoding="utf-8")
    assert len(result["summary"]) == 2
    assert set(result["summary"]["top_n"]) == {1, 2}
