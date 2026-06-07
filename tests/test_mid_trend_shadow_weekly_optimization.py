from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_shadow_weekly_optimization import (
    build_mid_trend_shadow_weekly_optimization_from_frames,
)


def _funnel_detail() -> pd.DataFrame:
    rows = []
    industries = [
        "计算机、通信和其他电子设备制造业",
        "电气机械和器材制造业",
        "有色金属冶炼和压延加工业",
        "专用设备制造业",
    ]
    dates = ["2025-01-03", "2025-01-06", "2025-01-07", "2025-01-13", "2025-01-14"]
    for day_index, trade_date in enumerate(dates):
        for asset_index in range(1, 7):
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": f"A{asset_index}",
                    "ts_code": f"00000{asset_index}.SZ",
                    "stock_name": f"Stock{asset_index}",
                    "industry_name": industries[(asset_index - 1) % len(industries)],
                    "market_regime": "mainline" if day_index % 2 == 0 else "rotation",
                    "mainline_status": "sustained_mainline",
                    "mainline_context": "mainline",
                    "industry_mainline_score_v1": 0.7,
                    "mid_trend_layer": "stable_trend_watch" if asset_index <= 4 else "high_elasticity_watch",
                    "mid_trend_funnel_score": 100 - asset_index + day_index,
                    "score_rank": asset_index,
                    "volatility_20_score": 35 + asset_index,
                    "trend_r2_20_score": 90 - asset_index,
                    "ret_20_score": 90,
                    "max_drawdown_20_score": 70,
                }
            )
    return pd.DataFrame(rows)


def _prices() -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2025-01-03", "2025-01-20", freq="B")
    for day_index, trade_date in enumerate(dates):
        for asset_index in range(1, 7):
            rows.append(
                {
                    "trade_date": trade_date.date().isoformat(),
                    "asset_id": f"A{asset_index}",
                    "close": 10.0 + day_index * (0.2 + asset_index * 0.03),
                    "open": 10.0 + day_index * (0.2 + asset_index * 0.03),
                    "amount": 1000000,
                    "trade_status": "1",
                }
            )
    return pd.DataFrame(rows)


def test_weekly_optimization_builds_topn_cost_grid_and_best_outputs(tmp_path: Path):
    result = build_mid_trend_shadow_weekly_optimization_from_frames(
        funnel_detail=_funnel_detail(),
        prices=_prices(),
        start_date="2025-01-03",
        end_date="2025-01-20",
        top_n_values=[3, 5],
        transaction_cost_bps_values=[10.0, 20.0],
        output_dir=tmp_path,
    )

    summary = result["summary"]
    assert set(summary["top_n"]) == {3, 5}
    assert set(summary["transaction_cost_bps"]) == {10.0, 20.0}
    assert summary["rebalance_frequency"].eq("weekly").all()
    assert summary["optimization_rank"].tolist() == sorted(summary["optimization_rank"].tolist())
    assert not result["best_equity_curve"].empty
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["best_equity_curve"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_weekly_optimization_handles_empty_inputs(tmp_path: Path):
    result = build_mid_trend_shadow_weekly_optimization_from_frames(
        funnel_detail=pd.DataFrame(),
        prices=pd.DataFrame(),
        start_date="2025-01-03",
        end_date="2025-01-20",
        output_dir=tmp_path,
    )

    assert result["summary"].empty
    assert result["best_equity_curve"].empty
    assert "No optimization rows" in result["report"]


def test_cli_dispatches_weekly_optimization(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "summary": pd.DataFrame([{"top_n": 10, "total_return": 0.3}]),
            "paths": {
                "summary": str(tmp_path / "summary.csv"),
                "best_equity_curve": str(tmp_path / "best_equity.csv"),
                "best_positions": str(tmp_path / "best_positions.csv"),
                "best_trades": str(tmp_path / "best_trades.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_shadow_weekly_optimization", fake_run)

    cli.main_for_args(
        [
            "optimize-mid-trend-shadow-weekly",
            "--funnel-detail-path",
            "outputs/research/mid_trend_watch_funnel_detail.csv",
            "--start-date",
            "2025-01-03",
            "--end-date",
            "2025-01-20",
            "--top-n-values",
            "5,10",
            "--transaction-cost-bps-values",
            "10,20",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["top_n_values"] == [5, 10]
    assert captured["transaction_cost_bps_values"] == [10.0, 20.0]
    out = capsys.readouterr().out
    assert "mid_trend_shadow_weekly_optimization|summary|" in out
