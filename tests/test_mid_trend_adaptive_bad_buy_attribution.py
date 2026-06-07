from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_adaptive_bad_buy_attribution import (
    build_mid_trend_adaptive_bad_buy_attribution_from_frames,
)


def _attribution_detail() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "variant_name": "top5_adaptive_daily_check_max2_v1",
                "trade_date": "2025-01-08",
                "sold_asset_id": "OLD",
                "bought_asset_id": "BAD",
                "bad_rebalance_flag": True,
                "bad_rebalance_reasons": "bad_buy;negative_replacement_alpha_10d",
                "replacement_alpha_10d": -0.12,
                "bought_next_10d_return": -0.08,
                "sold_next_10d_return": 0.04,
            },
            {
                "variant_name": "top5_adaptive_daily_check_max2_v1",
                "trade_date": "2025-01-09",
                "sold_asset_id": "OLD2",
                "bought_asset_id": "GOOD",
                "bad_rebalance_flag": False,
                "bad_rebalance_reasons": "",
                "replacement_alpha_10d": 0.10,
                "bought_next_10d_return": 0.15,
                "sold_next_10d_return": 0.05,
            },
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "trade_date": "2025-01-08",
                "sold_asset_id": "OLD3",
                "bought_asset_id": "BAD",
                "bad_rebalance_flag": True,
                "bad_rebalance_reasons": "bad_buy",
                "replacement_alpha_10d": -0.20,
                "bought_next_10d_return": -0.10,
                "sold_next_10d_return": 0.10,
            },
        ]
    )


def _funnel_detail() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-08",
                "asset_id": "BAD",
                "mid_trend_funnel_score": 98,
                "score_rank": 1,
                "trend_r2_20_score": 54,
                "ret_20_score": 95,
                "volatility_20_score": 93,
                "max_drawdown_20_score": 30,
                "industry_mainline_score_v1": 0.25,
                "mid_trend_layer": "high_elasticity_watch",
                "industry_name": "机械",
                "market_regime": "rotation",
                "mainline_status": "amount_spike_not_sustained",
                "mainline_context": "rotation",
            },
            {
                "trade_date": "2025-01-09",
                "asset_id": "GOOD",
                "mid_trend_funnel_score": 94,
                "score_rank": 3,
                "trend_r2_20_score": 86,
                "ret_20_score": 78,
                "volatility_20_score": 45,
                "max_drawdown_20_score": 72,
                "industry_mainline_score_v1": 0.62,
                "mid_trend_layer": "stable_trend_watch",
                "industry_name": "电子",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "mainline_context": "mainline",
            },
        ]
    )


def test_adaptive_bad_buy_attribution_outputs_detail_contrast_and_report(tmp_path: Path):
    result = build_mid_trend_adaptive_bad_buy_attribution_from_frames(
        attribution_detail=_attribution_detail(),
        funnel_detail=_funnel_detail(),
        output_dir=tmp_path,
    )

    detail = result["bad_buy_detail"]
    assert len(detail) == 1
    row = detail.iloc[0]
    assert row["bought_asset_id"] == "BAD"
    assert row["bought_weak_mainline"] is True
    assert row["bought_high_volatility"] is True
    assert row["bought_poor_drawdown_quality"] is True

    contrast = result["feature_contrast"].set_index("group")
    assert {"adaptive_bad_buy", "adaptive_other_buys"}.issubset(set(contrast.index))
    assert contrast.loc["adaptive_bad_buy", "sample_count"] == 1
    assert contrast.loc["adaptive_other_buys", "sample_count"] == 1
    assert Path(result["paths"]["bad_buy_detail"]).exists()
    assert Path(result["paths"]["feature_contrast"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_adaptive_bad_buy_attribution(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "bad_buy_detail": pd.DataFrame([{"trade_date": "2025-01-08"}]),
            "paths": {
                "bad_buy_detail": str(tmp_path / "detail.csv"),
                "feature_contrast": str(tmp_path / "contrast.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_adaptive_bad_buy_attribution", fake_run)

    cli.main_for_args(
        [
            "review-mid-trend-adaptive-bad-buy-attribution",
            "--attribution-detail-path",
            "outputs/research/mid_trend_adaptive_candidate_review_v1/mid_trend_adaptive_candidate_rebalance_attribution_detail.csv",
            "--funnel-detail-path",
            "outputs/research/mid_trend_watch_funnel_detail.csv",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["funnel_detail_path"] == "outputs/research/mid_trend_watch_funnel_detail.csv"
    out = capsys.readouterr().out
    assert "mid_trend_adaptive_bad_buy_attribution|bad_buy_detail|" in out
