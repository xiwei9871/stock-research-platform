from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_shadow_backtest import (
    build_mid_trend_shadow_backtest_from_frames,
)


def _shadow_top10() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "shadow_top10_rank": 1, "mid_trend_funnel_score": 90},
            {"trade_date": "2025-01-01", "asset_id": "B", "shadow_top10_rank": 2, "mid_trend_funnel_score": 80},
            {"trade_date": "2025-01-02", "asset_id": "B", "shadow_top10_rank": 1, "mid_trend_funnel_score": 90},
            {"trade_date": "2025-01-02", "asset_id": "C", "shadow_top10_rank": 2, "mid_trend_funnel_score": 80},
        ]
    )


def _prices() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "close": 10.0},
            {"trade_date": "2025-01-01", "asset_id": "B", "close": 20.0},
            {"trade_date": "2025-01-01", "asset_id": "C", "close": 30.0},
            {"trade_date": "2025-01-02", "asset_id": "A", "close": 11.0},
            {"trade_date": "2025-01-02", "asset_id": "B", "close": 18.0},
            {"trade_date": "2025-01-02", "asset_id": "C", "close": 30.0},
            {"trade_date": "2025-01-03", "asset_id": "A", "close": 11.0},
            {"trade_date": "2025-01-03", "asset_id": "B", "close": 19.8},
            {"trade_date": "2025-01-03", "asset_id": "C", "close": 33.0},
        ]
    )


def test_mid_trend_shadow_backtest_outputs_equity_and_metrics():
    result = build_mid_trend_shadow_backtest_from_frames(
        shadow_top10=_shadow_top10(),
        prices=_prices(),
        start_date="2025-01-01",
        end_date="2025-01-03",
        transaction_cost_bps=10.0,
    )

    summary = result["summary"].set_index("metric")["value"].to_dict()
    assert result["equity_curve"].iloc[-1]["date"] == "2025-01-03"
    assert float(summary["total_return"]) > 0
    assert "sharpe_ratio" in summary
    assert "max_drawdown" in summary
    assert len(result["positions"]) == 4


def test_mid_trend_shadow_backtest_writes_outputs(tmp_path: Path):
    result = build_mid_trend_shadow_backtest_from_frames(
        shadow_top10=_shadow_top10(),
        prices=_prices(),
        start_date="2025-01-01",
        end_date="2025-01-03",
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["equity_curve"]).exists()
    assert Path(result["paths"]["positions"]).exists()
    assert Path(result["paths"]["trades"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_mid_trend_shadow_backtest(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "summary": pd.DataFrame([{"metric": "total_return", "value": 0.1}]),
            "paths": {
                "equity_curve": str(tmp_path / "equity.csv"),
                "positions": str(tmp_path / "positions.csv"),
                "trades": str(tmp_path / "trades.csv"),
                "summary": str(tmp_path / "summary.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_shadow_backtest", fake_run)

    cli.main_for_args(
        [
            "backtest-mid-trend-shadow-top10",
            "--shadow-top10-path",
            "outputs/research/mid_trend_shadow_top10.csv",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2025-01-03",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["start_date"] == "2025-01-01"
    out = capsys.readouterr().out
    assert "mid_trend_shadow_backtest|summary|" in out
