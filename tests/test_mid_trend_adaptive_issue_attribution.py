from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.mid_trend_adaptive_issue_attribution import (
    build_mid_trend_adaptive_issue_attribution_from_frames,
)


def _monthly() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "period": "2025-01",
                "variant_name": "top5_weekly_max_2_replacements",
                "period_return": -0.02,
                "period_max_drawdown": -0.10,
                "trade_rows": 10,
            },
            {
                "period": "2025-01",
                "variant_name": "top5_adaptive_daily_check_max2_v1",
                "period_return": -0.05,
                "period_max_drawdown": -0.12,
                "trade_rows": 10,
            },
            {
                "period": "2025-02",
                "variant_name": "top5_weekly_max_2_replacements",
                "period_return": 0.03,
                "period_max_drawdown": -0.08,
                "trade_rows": 8,
            },
            {
                "period": "2025-02",
                "variant_name": "top5_adaptive_daily_check_max2_v1",
                "period_return": 0.05,
                "period_max_drawdown": -0.07,
                "trade_rows": 8,
            },
        ]
    )


def _attribution_detail() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "variant_name": "top5_adaptive_daily_check_max2_v1",
                "trade_date": "2025-01-10",
                "sold_asset_id": "OLD",
                "bought_asset_id": "NEW",
                "replacement_alpha_10d": -0.09,
                "replacement_alpha_20d": -0.11,
                "sold_next_10d_return": 0.12,
                "bought_next_10d_return": -0.02,
                "bad_rebalance_flag": True,
                "bad_rebalance_reasons": "sell_fly;negative_replacement_alpha_10d",
            },
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "trade_date": "2025-01-10",
                "sold_asset_id": "OLD2",
                "bought_asset_id": "NEW2",
                "replacement_alpha_10d": -0.03,
                "replacement_alpha_20d": 0.02,
                "sold_next_10d_return": 0.03,
                "bought_next_10d_return": 0.00,
                "bad_rebalance_flag": False,
                "bad_rebalance_reasons": "",
            },
        ]
    )


def _funnel() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-10",
                "asset_id": "OLD",
                "mid_trend_funnel_score": 90,
                "score_rank": 9,
                "trend_r2_20_score": 92,
                "ret_20_score": 84,
                "volatility_20_score": 45,
                "max_drawdown_20_score": 70,
                "industry_mainline_score_v1": 0.60,
                "mid_trend_layer": "stable_trend_watch",
                "industry_name": "电子",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "mainline_context": "mainline",
            },
            {
                "trade_date": "2025-01-10",
                "asset_id": "NEW",
                "mid_trend_funnel_score": 96,
                "score_rank": 2,
                "trend_r2_20_score": 86,
                "ret_20_score": 96,
                "volatility_20_score": 88,
                "max_drawdown_20_score": 35,
                "industry_mainline_score_v1": 0.40,
                "mid_trend_layer": "high_elasticity_watch",
                "industry_name": "机械",
                "market_regime": "mainline",
                "mainline_status": "rotating",
                "mainline_context": "rotation",
            },
        ]
    )


def test_adaptive_issue_attribution_generates_q1_and_sell_fly_outputs(tmp_path: Path):
    result = build_mid_trend_adaptive_issue_attribution_from_frames(
        monthly=_monthly(),
        attribution_detail=_attribution_detail(),
        funnel_detail=_funnel(),
        output_dir=tmp_path,
    )

    assert not result["period_gap"].empty
    assert result["period_gap"].iloc[0]["return_delta"] < 0
    assert not result["sell_fly_detail"].empty
    assert result["sell_fly_detail"].iloc[0]["sold_still_strong"] is True
    assert not result["feature_summary"].empty
    assert Path(result["paths"]["period_gap"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_cli_dispatches_adaptive_issue_attribution(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "period_gap": pd.DataFrame([{"period": "2025-01"}]),
            "paths": {
                "period_gap": str(tmp_path / "gap.csv"),
                "sell_fly_detail": str(tmp_path / "sell.csv"),
                "feature_summary": str(tmp_path / "feature.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_adaptive_issue_attribution", fake_run)

    cli.main_for_args(
        [
            "review-mid-trend-adaptive-issue-attribution",
            "--monthly-path",
            "outputs/research/mid_trend_adaptive_candidate_review_v1/mid_trend_adaptive_candidate_monthly_stability.csv",
            "--attribution-detail-path",
            "outputs/research/mid_trend_adaptive_candidate_review_v1/mid_trend_adaptive_candidate_rebalance_attribution_detail.csv",
            "--funnel-detail-path",
            "outputs/research/mid_trend_watch_funnel_detail.csv",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["monthly_path"].endswith("monthly_stability.csv")
    out = capsys.readouterr().out
    assert "mid_trend_adaptive_issue_attribution|period_gap|" in out
