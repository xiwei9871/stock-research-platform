from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_adaptive_candidate_review import (
    build_mid_trend_adaptive_candidate_review_from_frames,
)


def _funnel_detail() -> pd.DataFrame:
    rows = []
    dates = ["2025-01-03", "2025-01-06", "2025-01-07", "2025-01-13"]
    for day_index, trade_date in enumerate(dates):
        ranking = ["A", "B", "C", "D", "E", "F", "G"]
        if trade_date == "2025-01-07":
            ranking = ["F", "A", "B", "C", "D", "E", "G"]
        if trade_date == "2025-01-13":
            ranking = ["F", "G", "A", "B", "C", "D", "E"]
        for rank, asset_id in enumerate(ranking, start=1):
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "ts_code": f"{rank:06d}.SZ",
                    "stock_name": f"Stock{asset_id}",
                    "industry_name": "计算机、通信和其他电子设备制造业",
                    "market_regime": "mainline",
                    "mainline_status": "sustained_mainline",
                    "mainline_context": "mainline",
                    "industry_mainline_score_v1": 0.60,
                    "mid_trend_layer": "stable_trend_watch",
                    "structure_slot": "preferred_core",
                    "mid_trend_funnel_score": 110 - rank + day_index,
                    "score_rank": rank,
                    "volatility_20_score": 40,
                    "trend_r2_20_score": 85,
                    "ret_20_score": 80,
                    "max_drawdown_20_score": 70,
                }
            )
    return pd.DataFrame(rows)


def _prices() -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2025-01-03", "2025-01-31", freq="B")
    for day_index, trade_date in enumerate(dates):
        for asset_index, asset_id in enumerate(["A", "B", "C", "D", "E", "F", "G"], start=1):
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


def test_adaptive_candidate_review_outputs_stability_attribution_cost_and_weak_periods(tmp_path: Path):
    result = build_mid_trend_adaptive_candidate_review_from_frames(
        funnel_detail=_funnel_detail(),
        prices=_prices(),
        start_date="2025-01-03",
        end_date="2025-01-31",
        output_dir=tmp_path,
        transaction_cost_bps=20.0,
        cost_bps_values=[10.0, 20.0],
    )

    assert {"top5_weekly_max_2_replacements", "top5_adaptive_daily_check_max2_v1"}.issubset(
        set(result["monthly"]["variant_name"])
    )
    assert not result["quarterly"].empty
    assert not result["attribution_summary"].empty
    assert set(result["cost_scan"]["transaction_cost_bps"]) == {10.0, 20.0}
    assert "2025Q1" in set(result["weak_periods"]["period"])
    assert Path(result["paths"]["monthly"]).exists()
    assert Path(result["paths"]["cost_scan"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_adaptive_candidate_review(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "monthly": pd.DataFrame([{"variant_name": "x"}]),
            "paths": {
                "monthly": str(tmp_path / "monthly.csv"),
                "quarterly": str(tmp_path / "quarterly.csv"),
                "attribution_summary": str(tmp_path / "attr.csv"),
                "attribution_detail": str(tmp_path / "detail.csv"),
                "cost_scan": str(tmp_path / "cost.csv"),
                "weak_periods": str(tmp_path / "weak.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_adaptive_candidate_review", fake_run)

    cli.main_for_args(
        [
            "review-mid-trend-adaptive-candidate",
            "--funnel-detail-path",
            "outputs/research/mid_trend_watch_funnel_detail.csv",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-05-19",
            "--cost-bps-values",
            "10,20",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["cost_bps_values"] == [10.0, 20.0]
    out = capsys.readouterr().out
    assert "mid_trend_adaptive_candidate|monthly|" in out
