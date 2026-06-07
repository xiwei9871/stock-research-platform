from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_drawdown_throttle_scan import (
    build_mid_trend_drawdown_throttle_scan_from_frames,
)


def _funnel_detail() -> pd.DataFrame:
    rows = []
    dates = ["2025-01-03", "2025-01-06", "2025-01-13", "2025-01-20", "2025-01-27"]
    for day_index, trade_date in enumerate(dates):
        ranking = ["A", "B", "C", "D", "E", "F", "G", "H"]
        if trade_date >= "2025-01-13":
            ranking = ["F", "G", "A", "B", "C", "D", "E", "H"]
        for rank, asset_id in enumerate(ranking, start=1):
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "ts_code": f"{rank:06d}.SZ",
                    "stock_name": f"Stock{asset_id}",
                    "industry_name": "计算机、通信和其他电子设备制造业",
                    "market_regime": "mainline",
                    "industry_mainline_score_v1": 0.60,
                    "mid_trend_layer": "stable_trend_watch",
                    "mid_trend_funnel_score": 100 - rank + day_index,
                    "score_rank": rank,
                    "trend_r2_20_score": 85,
                    "ret_20_score": 80,
                    "max_drawdown_20_score": 70,
                }
            )
    return pd.DataFrame(rows)


def _prices() -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2025-01-03", "2025-02-14", freq="B")
    for day_index, trade_date in enumerate(dates):
        for asset_index, asset_id in enumerate(["A", "B", "C", "D", "E", "F", "G", "H"], start=1):
            close = 10.0 + day_index * (0.05 + asset_index * 0.01)
            if 5 <= day_index <= 9:
                close *= 0.88
            rows.append(
                {
                    "trade_date": trade_date.date().isoformat(),
                    "asset_id": asset_id,
                    "open": close,
                    "close": close,
                    "amount": 1000000,
                    "trade_status": "1",
                }
            )
    return pd.DataFrame(rows)


def test_drawdown_throttle_scan_builds_grid_with_baseline_and_trigger_metrics(tmp_path: Path):
    result = build_mid_trend_drawdown_throttle_scan_from_frames(
        funnel_detail=_funnel_detail(),
        prices=_prices(),
        start_date="2025-01-03",
        end_date="2025-02-14",
        threshold_values=[0.05, 0.08],
        invested_weight_values=[0.8, 0.9],
        max_replacement_values=[1, 2],
        transaction_cost_bps=20.0,
        output_dir=tmp_path,
    )

    summary = result["summary"]
    assert len(summary) == 9
    assert "top5_weekly_max_2_replacements" in set(summary["variant_name"])
    grid = summary[summary["variant_name"].str.contains("drawdown_throttle")]
    assert set(grid["drawdown_throttle_threshold"]) == {-0.05, -0.08}
    assert set(grid["drawdown_throttle_invested_weight"]) == {0.8, 0.9}
    assert set(grid["drawdown_throttle_max_replacements"]) == {1, 2}
    assert "drawdown_throttle_trigger_count" in summary.columns
    assert "average_invested_weight" in summary.columns
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_drawdown_throttle_scan(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "summary": pd.DataFrame([{"variant_name": "top5_weekly_max_2_replacements"}]),
            "paths": {
                "summary": str(tmp_path / "summary.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_drawdown_throttle_scan", fake_run)

    cli.main_for_args(
        [
            "scan-mid-trend-drawdown-throttle",
            "--funnel-detail-path",
            "outputs/research/mid_trend_watch_funnel_detail.csv",
            "--start-date",
            "2025-01-03",
            "--end-date",
            "2025-02-14",
            "--threshold-values",
            "0.08,0.10",
            "--invested-weight-values",
            "0.8,0.9",
            "--max-replacement-values",
            "1,2",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["threshold_values"] == [0.08, 0.10]
    assert captured["invested_weight_values"] == [0.8, 0.9]
    assert captured["max_replacement_values"] == [1, 2]
    out = capsys.readouterr().out
    assert "mid_trend_drawdown_throttle_scan|summary|" in out
