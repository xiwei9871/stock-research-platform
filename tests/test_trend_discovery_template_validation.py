from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.watchlist.trend_template_validation import (
    build_trend_discovery_template_validation,
)


def _detail() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "watchlist_review_layer": "mid_term_trend_watch",
                "watch_group": "opportunity_watch",
                "event_structure": "trend_continuation_candidate",
                "mainline_context": "mainline",
                "sector_strength_bucket": "top_10",
                "fundamental_quality_bucket": "expectation_growth",
                "score_rank": 5,
                "score_components": {
                    "ret_20_score": 85,
                    "ret_60_score": 80,
                    "ma20_slope_score": 82,
                    "ma60_slope_score": 70,
                    "trend_r2_20_score": 75,
                    "momentum_20_5_score": 70,
                    "stock_excess_ret_20_score": 90,
                    "max_drawdown_20_score": 80,
                },
                "amount_vs_20d": 1.8,
                "volatility_5d": 0.03,
                "high_to_close_drawdown": 0.02,
                "future_10d_return": 0.10,
                "future_20d_return": 0.20,
                "future_30d_return": 0.30,
                "future_40d_return": 0.35,
                "future_60d_return": 0.60,
                "future_20d_max_drawdown": -0.05,
                "future_60d_max_drawdown": -0.10,
                "max_return_within_60d": 0.90,
                "hit_double_within_60d": False,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "watchlist_review_layer": "mid_term_trend_watch",
                "watch_group": "candidate",
                "event_structure": "",
                "mainline_context": "mainline",
                "sector_strength_bucket": "top_30",
                "fundamental_quality_bucket": "cyclical_or_turnaround",
                "score_rank": 40,
                "score_components": {
                    "ret_20_score": 75,
                    "ret_60_score": 70,
                    "ma20_slope_score": 70,
                    "ma60_slope_score": 55,
                    "trend_r2_20_score": 65,
                    "momentum_20_5_score": 60,
                    "stock_excess_ret_20_score": 80,
                    "max_drawdown_20_score": 65,
                },
                "amount_vs_20d": 1.1,
                "volatility_5d": 0.025,
                "high_to_close_drawdown": 0.03,
                "future_10d_return": 0.03,
                "future_20d_return": 0.08,
                "future_30d_return": 0.12,
                "future_40d_return": 0.18,
                "future_60d_return": 0.22,
                "future_20d_max_drawdown": -0.08,
                "future_60d_max_drawdown": -0.16,
                "max_return_within_60d": 0.35,
                "hit_double_within_60d": False,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "C",
                "watchlist_review_layer": "short_speculation_watch",
                "watch_group": "risk_watch",
                "event_structure": "a_kill_failure",
                "mainline_context": "mainline",
                "sector_strength_bucket": "top_10",
                "fundamental_quality_bucket": "loss_worsening",
                "score_rank": 10,
                "amount_vs_20d": 6.0,
                "volatility_5d": 0.08,
                "high_to_close_drawdown": 0.12,
                "future_10d_return": -0.20,
                "future_20d_return": -0.30,
                "future_60d_return": -0.40,
                "future_20d_max_drawdown": -0.35,
                "future_60d_max_drawdown": -0.50,
                "max_return_within_60d": 0.10,
                "hit_double_within_60d": False,
            },
        ]
    )


def _strong_winners() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "winner_id": "W1",
                "asset_id": "A",
                "capture_status": "captured_pre_double",
                "best_pre_double_score_rank": 5,
            },
            {
                "winner_id": "W2",
                "asset_id": "Z",
                "capture_status": "missed",
                "best_pre_double_score_rank": pd.NA,
            },
        ]
    )


def test_trend_template_validation_generates_template_hits_and_summary(tmp_path: Path):
    result = build_trend_discovery_template_validation(
        detail=_detail(),
        strong_winners=_strong_winners(),
        output_dir=tmp_path,
    )

    detail = result["detail"]
    assert detail["template_hit_count"].max() > 0
    assert bool(detail.loc[detail["asset_id"].eq("A"), "dual_momentum_template"].iloc[0]) is True
    summary = result["summary"]
    assert "dual_momentum_template" in set(summary["template_name"])
    assert "future_60d_return_mean" in summary.columns
    capture = result["strong_winner_capture"]
    assert "captured_strong_winner_count" in capture.columns
    assert Path(result["paths"]["detail"]).exists()
    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["recommendations"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_trend_template_validation_does_not_use_future_returns_for_template_flags():
    result = build_trend_discovery_template_validation(detail=_detail())
    row_a = result["detail"][result["detail"]["asset_id"].eq("A")].iloc[0]
    row_b = result["detail"][result["detail"]["asset_id"].eq("B")].iloc[0]

    assert bool(row_a["dual_momentum_template"]) is True
    assert bool(row_b["dual_momentum_template"]) is True


def test_cli_dispatches_trend_template_validation(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "paths": {
                "detail": str(tmp_path / "detail.csv"),
                "summary": str(tmp_path / "summary.csv"),
                "strong_winner_capture": str(tmp_path / "capture.csv"),
                "recommendations": str(tmp_path / "recommendations.csv"),
                "report": str(tmp_path / "report.md"),
            },
            "warnings": [],
        }

    monkeypatch.setattr(cli, "run_trend_discovery_template_validation", fake_run)
    cli.main_for_args(
        [
            "validate-trend-discovery-templates",
            "--detail-path",
            "outputs/research/watchlist_context_cross_detail.csv",
            "--strong-winner-path",
            "outputs/research/strong_winner_miss_analysis_2025_to_now.csv",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["detail_path"] == "outputs/research/watchlist_context_cross_detail.csv"
    out = capsys.readouterr().out
    assert "trend_template_validation|summary|" in out
    assert "trend_template_validation|recommendations|" in out
