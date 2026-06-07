from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_trend_protection_stability import (
    build_mid_trend_trend_protection_stability_review_from_frames,
)


def _funnel_detail() -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2025-01-03", "2025-03-31", freq="B")
    assets = ["A", "B", "C", "D", "E", "F", "G", "H"]
    for day_index, trade_date in enumerate(dates):
        ranking = assets.copy()
        if day_index >= 20:
            ranking = ["F", "G", "A", "B", "C", "D", "E", "H"]
        for rank, asset_id in enumerate(ranking, start=1):
            rows.append(
                {
                    "trade_date": trade_date.date().isoformat(),
                    "asset_id": asset_id,
                    "ts_code": f"{rank:06d}.SZ",
                    "stock_name": f"Stock{asset_id}",
                    "industry_name": "计算机、通信和其他电子设备制造业",
                    "market_regime": "mainline",
                    "mainline_status": "sustained_mainline",
                    "mainline_context": "mainline",
                    "industry_mainline_score_v1": 0.6,
                    "mid_trend_layer": "stable_trend_watch",
                    "mid_trend_funnel_score": 100 - rank,
                    "score_rank": rank,
                    "volatility_20_score": 40,
                    "trend_r2_20_score": 90 if asset_id in {"A", "B", "C"} else 75,
                    "ret_20_score": 85 if asset_id in {"A", "B", "C"} else 65,
                    "max_drawdown_20_score": 70,
                }
            )
    return pd.DataFrame(rows)


def _prices() -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2025-01-03", "2025-03-31", freq="B")
    for day_index, trade_date in enumerate(dates):
        for asset_index, asset_id in enumerate(["A", "B", "C", "D", "E", "F", "G", "H"], start=1):
            close = 10.0 + day_index * (0.05 + asset_index * 0.01)
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


def test_trend_protection_stability_outputs_period_and_attribution_tables(tmp_path: Path):
    result = build_mid_trend_trend_protection_stability_review_from_frames(
        funnel_detail=_funnel_detail(),
        prices=_prices(),
        start_date="2025-01-03",
        end_date="2025-03-31",
        output_dir=tmp_path,
        protection_score_gap=6.0,
        protection_mainline_gap=0.05,
    )

    assert set(result["monthly"]["period_type"]) == {"month"}
    assert set(result["quarterly"]["period_type"]) == {"quarter"}
    assert {"top5_weekly_max_2_replacements", "selective_trend_protection_score_gap_6"}.issubset(
        set(result["monthly"]["variant_name"])
    )
    assert {"bad_rebalance_pair_count", "sell_fly_count", "drawdown_amplified_count"}.issubset(
        set(result["attribution_summary"]["metric"])
    )
    assert Path(result["paths"]["monthly"]).exists()
    assert Path(result["paths"]["quarterly"]).exists()
    assert Path(result["paths"]["attribution_summary"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_trend_protection_stability(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "monthly": pd.DataFrame([{"variant_name": "baseline"}]),
            "paths": {
                "monthly": str(tmp_path / "monthly.csv"),
                "quarterly": str(tmp_path / "quarterly.csv"),
                "attribution_summary": str(tmp_path / "attr.csv"),
                "attribution_detail": str(tmp_path / "detail.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_trend_protection_stability_review", fake_run)

    cli.main_for_args(
        [
            "review-mid-trend-protection-stability",
            "--funnel-detail-path",
            "outputs/research/mid_trend_watch_funnel_detail.csv",
            "--start-date",
            "2025-01-03",
            "--end-date",
            "2025-03-31",
            "--protection-score-gap",
            "6",
            "--protection-mainline-gap",
            "0.05",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["protection_score_gap"] == 6.0
    assert captured["protection_mainline_gap"] == 0.05
    out = capsys.readouterr().out
    assert "mid_trend_trend_protection_stability|monthly|" in out
