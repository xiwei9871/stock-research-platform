from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.watchlist.dual_strategy_review import build_dual_strategy_effectiveness_review


def _detail() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "watchlist_review_layer": "short_speculation_watch",
                "watch_group": "high_odds_burst_watch",
                "event_structure": "trend_continuation_candidate",
                "mainline_context": "mainline",
                "sector_strength_bucket": "top_10",
                "fundamental_quality_bucket": "loss_worsening",
                "future_1d_return": 0.03,
                "future_3d_return": 0.06,
                "future_5d_return": 0.08,
                "future_10d_return": 0.02,
                "future_5d_max_drawdown": -0.03,
                "future_10d_max_drawdown": -0.08,
                "future_20d_return": -0.10,
                "future_60d_return": -0.20,
                "future_60d_max_drawdown": -0.30,
                "hit_double_within_60d": False,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "watchlist_review_layer": "mid_term_trend_watch",
                "watch_group": "opportunity_watch",
                "event_structure": "trend_continuation_candidate",
                "mainline_context": "mainline",
                "sector_strength_bucket": "top_10",
                "fundamental_quality_bucket": "expectation_growth",
                "future_1d_return": -0.01,
                "future_3d_return": 0.01,
                "future_5d_return": 0.04,
                "future_10d_return": 0.10,
                "future_20d_return": 0.20,
                "future_30d_return": 0.30,
                "future_40d_return": 0.40,
                "future_60d_return": 0.80,
                "future_20d_max_drawdown": -0.05,
                "future_60d_max_drawdown": -0.12,
                "max_return_within_60d": 0.95,
                "hit_double_within_60d": False,
            },
        ]
    )


def test_dual_strategy_review_generates_separate_short_and_trend_outputs(tmp_path: Path):
    result = build_dual_strategy_effectiveness_review(detail=_detail(), output_dir=tmp_path)

    short = result["short_event_summary"]
    trend = result["trend_discovery_summary"]
    assert short.iloc[0]["strategy_line"] == "short_event_lhb"
    assert trend.iloc[0]["strategy_line"] == "trend_discovery"
    assert "future_1d_return_mean" in short.columns
    assert "future_60d_return_mean" not in short.columns
    assert "future_60d_return_mean" in trend.columns
    assert "future_1d_return_mean" not in trend.columns
    assert Path(result["paths"]["short_event_summary"]).exists()
    assert Path(result["paths"]["trend_discovery_summary"]).exists()
    assert Path(result["paths"]["comparison"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_dual_strategy_review_uses_60d_as_longest_trend_horizon_without_90d_warning():
    result = build_dual_strategy_effectiveness_review(detail=_detail())

    assert "missing_trend_90d_metrics" not in result["warnings"]
    assert "future_90d_return_mean" not in result["trend_discovery_summary"].columns
    assert "future_60d_return_mean" in result["trend_discovery_summary"].columns


def test_cli_dispatches_dual_strategy_review(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "warnings": [],
            "paths": {
                "short_event_summary": str(tmp_path / "short.csv"),
                "trend_discovery_summary": str(tmp_path / "trend.csv"),
                "comparison": str(tmp_path / "comparison.csv"),
                "report": str(tmp_path / "report.md"),
            },
        }

    monkeypatch.setattr(cli, "run_dual_strategy_effectiveness_review", fake_run)
    cli.main_for_args(
        [
            "review-dual-strategy-effectiveness",
            "--detail-path",
            "outputs/research/watchlist_context_cross_detail.csv",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["detail_path"] == "outputs/research/watchlist_context_cross_detail.csv"
    out = capsys.readouterr().out
    assert "dual_strategy_review|short_event_summary|" in out
    assert "dual_strategy_review|trend_discovery_summary|" in out
    assert "dual_strategy_review|warning|missing_trend_90d_metrics" not in out
