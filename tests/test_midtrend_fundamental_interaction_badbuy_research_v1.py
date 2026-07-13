from pathlib import Path

import pandas as pd


def _events() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "asset_id": "A",
                "trade_date": "2025-01-03",
                "canonical_fundamental_quality_bucket": "quality_weak",
                "canonical_fundamental_momentum_bucket": "deteriorating",
                "high_elasticity_watch": True,
                "mainline_confirmed": False,
                "score_rank": 28,
                "stock_excess_ret_20_score": 55,
                "max_drawdown_20_score": 45,
                "is_bad_buy": True,
                "is_winner": False,
                "trade_return": -0.3,
                "contribution": -0.03,
                "weighted_bad_buy_loss": -0.03,
            },
            {
                "asset_id": "B",
                "trade_date": "2025-01-03",
                "canonical_fundamental_quality_bucket": "quality_weak",
                "canonical_fundamental_momentum_bucket": "stable",
                "high_elasticity_watch": False,
                "mainline_confirmed": True,
                "score_rank": 8,
                "stock_excess_ret_20_score": 90,
                "max_drawdown_20_score": 85,
                "is_bad_buy": False,
                "is_winner": True,
                "trade_return": 0.5,
                "contribution": 0.05,
                "weighted_bad_buy_loss": 0.0,
            },
            {
                "asset_id": "C",
                "trade_date": "2025-01-03",
                "canonical_fundamental_quality_bucket": "quality_strong",
                "canonical_fundamental_momentum_bucket": "deteriorating",
                "high_elasticity_watch": True,
                "mainline_confirmed": True,
                "score_rank": 18,
                "stock_excess_ret_20_score": 75,
                "max_drawdown_20_score": 70,
                "is_bad_buy": True,
                "is_winner": False,
                "trade_return": -0.1,
                "contribution": -0.01,
                "weighted_bad_buy_loss": -0.01,
            },
        ]
    )


def test_build_interaction_denominator_marks_expected_buckets() -> None:
    from stock_research.midtrend_fundamental_interaction_badbuy_research_v1 import (
        build_bad_buy_interaction_denominator,
    )

    result = build_bad_buy_interaction_denominator(_events())
    names = set(result["interaction_name"])

    assert "high_elasticity_quality_weak" in names
    assert "high_elasticity_deteriorating" in names
    assert "mainline_weak_quality_weak" in names
    assert "mainline_weak_deteriorating" in names
    assert "quality_weak_rank_edge" in names
    assert "quality_weak_weak_stock_excess" in names
    assert "quality_weak_weak_drawdown_quality" in names


def test_interaction_net_contribution_uses_denominator_not_count_only() -> None:
    from stock_research.midtrend_fundamental_interaction_badbuy_research_v1 import (
        build_bad_buy_interaction_denominator,
        build_bad_buy_interaction_net_contribution,
    )

    denominator = build_bad_buy_interaction_denominator(_events())
    summary = build_bad_buy_interaction_net_contribution(denominator)
    row = summary[summary["interaction_name"].eq("high_elasticity_quality_weak")].iloc[0]

    assert row["sample_count"] == 1
    assert row["bad_buy_rate"] == 1.0
    assert row["net_bucket_contribution"] == -0.03
    assert row["winner_contribution"] == 0.0
    assert row["worst_loss"] == -0.3
    assert row["rule_readiness"] == "CANDIDATE_FOR_SMALL_EXPERIMENT"


def test_runner_writes_required_research_outputs(tmp_path: Path) -> None:
    from stock_research.midtrend_fundamental_interaction_badbuy_research_v1 import (
        run_midtrend_fundamental_interaction_badbuy_research_from_frames,
    )

    result = run_midtrend_fundamental_interaction_badbuy_research_from_frames(
        denominator_events=_events(),
        output_dir=tmp_path,
    )

    assert result["paths"]["output_dir"] == str(tmp_path)
    for filename in [
        "bad_buy_interaction_denominator.csv",
        "bad_buy_interaction_net_contribution.csv",
        "high_elasticity_quality_weak_analysis.csv",
        "mainline_weak_quality_weak_analysis.csv",
        "deteriorating_quality_interaction_analysis.csv",
        "fundamental_interaction_rule_candidates_research_only.md",
        "final_interpretation.md",
    ]:
        assert (tmp_path / filename).exists(), filename
    text = (tmp_path / "fundamental_interaction_rule_candidates_research_only.md").read_text(encoding="utf-8")
    assert "RESEARCH_ONLY" in text
