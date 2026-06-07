from pathlib import Path

import pandas as pd

from stock_research import cli
from stock_research.watchlist.trend_discovery_v2_2_stability import (
    build_trend_discovery_v2_2_stability_review,
)


def _detail() -> pd.DataFrame:
    rows = []
    base = {
        "future_1d_return": 0.01,
        "future_3d_return": 0.02,
        "future_5d_return": 0.03,
        "future_10d_return": 0.04,
        "future_20d_return": 0.08,
        "future_30d_return": 0.10,
        "future_40d_return": 0.12,
        "future_60d_return": 0.16,
        "future_10d_max_drawdown": -0.04,
        "future_20d_max_drawdown": -0.06,
        "future_30d_max_drawdown": -0.08,
        "future_40d_max_drawdown": -0.09,
        "future_60d_max_drawdown": -0.10,
        "max_return_within_60d": 0.35,
        "hit_double_within_60d": False,
        "v2_final_baseline": True,
        "v2_1_quality_no_highvol_extremeamount": True,
        "v2_2_growth_trend_core": False,
        "v2_2_cyclical_trend_core": False,
        "v2_2_trend_continuation_boost": False,
        "v2_2_high_elasticity_shadow": False,
        "existing_trend_continuation_candidate": False,
    }
    for idx in range(120):
        rows.append(
            {
                **base,
                "trade_date": "2025-01-15",
                "asset_id": f"A{idx}",
                "industry_name": "科技",
                "market_regime": "mainline",
                "mainline_context": "mainline",
                "sector_strength_bucket": "top_10",
                "v2_2_growth_trend_core": True,
                "future_60d_return": 0.30,
            }
        )
    rows.append(
        {
            **base,
            "trade_date": "2025-04-15",
            "asset_id": "B",
            "industry_name": "周期",
            "market_regime": "rotation",
            "mainline_context": "rotation",
            "sector_strength_bucket": "top_30",
            "v2_2_cyclical_trend_core": True,
            "future_60d_return": 0.08,
        }
    )
    rows.append(
        {
            **base,
            "trade_date": "2026-02-15",
            "asset_id": "C",
            "industry_name": "科技",
            "market_regime": "mainline",
            "mainline_context": "mainline",
            "sector_strength_bucket": "top_10",
            "event_structure": "trend_continuation_candidate",
            "v2_2_trend_continuation_boost": True,
            "existing_trend_continuation_candidate": True,
            "future_60d_return": 0.22,
            "hit_double_within_60d": True,
        }
    )
    rows.append(
        {
            **base,
            "trade_date": "2026-03-15",
            "asset_id": "D",
            "industry_name": "题材",
            "market_regime": "retreat",
            "mainline_context": "retreat",
            "sector_strength_bucket": "top_10",
            "v2_1_quality_no_highvol_extremeamount": False,
            "v2_2_high_elasticity_shadow": True,
            "future_1d_return": 0.06,
            "future_3d_return": 0.08,
            "future_5d_return": 0.10,
            "future_10d_return": 0.12,
            "future_60d_return": -0.05,
            "future_60d_max_drawdown": -0.25,
            "max_return_within_60d": 0.55,
        }
    )
    return pd.DataFrame(rows)


def _strong_winners() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"winner_id": "W1", "asset_id": "C"},
            {"winner_id": "W2", "asset_id": "Z"},
        ]
    )


def test_stability_review_generates_period_regime_industry_and_decisions(tmp_path: Path):
    result = build_trend_discovery_v2_2_stability_review(
        detail=_detail(),
        strong_winners=_strong_winners(),
        output_dir=tmp_path,
    )

    assert {"2025Q1", "2025Q2", "2026YTD"} <= set(result["by_period"]["period"])
    assert {"mainline", "rotation", "retreat"} <= set(result["by_regime"]["regime_value"])
    assert {"科技", "周期"} <= set(result["by_industry"]["industry_name"])
    assert "short_horizon_edge" in result["high_elasticity_short_horizon"].columns
    assert set(result["decision"]["decision"]) >= {"promote_candidate", "short_horizon_only", "keep_shadow"}
    assert Path(result["paths"]["by_period"]).exists()
    assert Path(result["paths"]["decision"]).exists()
    assert Path(result["paths"]["report"]).exists()


def test_stability_review_marks_high_elasticity_short_horizon_only():
    result = build_trend_discovery_v2_2_stability_review(detail=_detail(), strong_winners=_strong_winners())

    decision = result["decision"]
    row = decision[decision["candidate_set"].eq("v2_2_high_elasticity_shadow")].iloc[0]
    assert row["decision"] == "short_horizon_only"


def test_cli_dispatches_v2_2_stability_review(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "paths": {
                "by_period": str(tmp_path / "period.csv"),
                "by_regime": str(tmp_path / "regime.csv"),
                "by_industry": str(tmp_path / "industry.csv"),
                "high_elasticity_short_horizon": str(tmp_path / "elastic.csv"),
                "strong_winner_capture": str(tmp_path / "capture.csv"),
                "decision": str(tmp_path / "decision.csv"),
                "report": str(tmp_path / "report.md"),
            },
            "warnings": [],
        }

    monkeypatch.setattr(cli, "run_trend_discovery_v2_2_stability_review", fake_run)
    cli.main_for_args(
        [
            "review-trend-discovery-v2-2-stability",
            "--detail-path",
            "outputs/research/trend_discovery_v2_2_replay_detail.csv",
            "--strong-winner-path",
            "outputs/research/strong_winner_miss_analysis_2025_to_now.csv",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert captured["detail_path"] == "outputs/research/trend_discovery_v2_2_replay_detail.csv"
    out = capsys.readouterr().out
    assert "trend_discovery_v2_2_stability|by_period|" in out
    assert "trend_discovery_v2_2_stability|decision|" in out
