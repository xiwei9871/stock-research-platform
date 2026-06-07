from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_trend_protection_scan import (
    build_mid_trend_trend_protection_scan_from_frames,
)


def _funnel_detail() -> pd.DataFrame:
    rows = []
    dates = ["2025-01-03", "2025-01-06", "2025-01-13", "2025-01-20"]
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
                    "industry_mainline_score_v1": 0.60 if asset_id != "H" else 0.35,
                    "mid_trend_layer": "stable_trend_watch",
                    "mid_trend_funnel_score": 100 - rank + day_index,
                    "score_rank": rank,
                    "trend_r2_20_score": 90 if asset_id in {"A", "B", "C"} else 70,
                    "ret_20_score": 85 if asset_id in {"A", "B", "C"} else 65,
                    "max_drawdown_20_score": 70,
                }
            )
    return pd.DataFrame(rows)


def _prices() -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2025-01-03", "2025-01-31", freq="B")
    for day_index, trade_date in enumerate(dates):
        for asset_index, asset_id in enumerate(["A", "B", "C", "D", "E", "F", "G", "H"], start=1):
            close = 10.0 + day_index * (0.08 + asset_index * 0.01)
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


def test_trend_protection_scan_builds_parameter_grid_and_baseline(tmp_path: Path):
    result = build_mid_trend_trend_protection_scan_from_frames(
        funnel_detail=_funnel_detail(),
        prices=_prices(),
        start_date="2025-01-03",
        end_date="2025-01-31",
        score_gap_values=[8.0, 10.0],
        mainline_gap_values=[0.05, 0.10],
        trend_r2_min_values=[80.0],
        ret20_min_values=[70.0],
        drawdown_min_values=[55.0],
        transaction_cost_bps=20.0,
        output_dir=tmp_path,
    )

    summary = result["summary"]
    assert len(summary) == 5
    assert "top5_weekly_max_2_replacements" in set(summary["variant_name"])
    grid = summary[summary["variant_name"].str.contains("selective_trend_protection")]
    assert set(grid["protection_score_gap"]) == {8.0, 10.0}
    assert set(grid["protection_mainline_gap"]) == {0.05, 0.10}
    assert summary["scan_rank"].tolist() == sorted(summary["scan_rank"].tolist())
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_trend_protection_scan(monkeypatch, capsys, tmp_path: Path):
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

    monkeypatch.setattr(cli, "run_mid_trend_trend_protection_scan", fake_run)

    cli.main_for_args(
        [
            "scan-mid-trend-protection",
            "--funnel-detail-path",
            "outputs/research/mid_trend_watch_funnel_detail.csv",
            "--start-date",
            "2025-01-03",
            "--end-date",
            "2025-01-31",
            "--score-gap-values",
            "8,10",
            "--mainline-gap-values",
            "0.05,0.10",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["score_gap_values"] == [8.0, 10.0]
    assert captured["mainline_gap_values"] == [0.05, 0.10]
    out = capsys.readouterr().out
    assert "mid_trend_trend_protection_scan|summary|" in out
