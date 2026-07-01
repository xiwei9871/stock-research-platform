from pathlib import Path

import pandas as pd


def _pit() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": "A",
                "pit_valid_flag": True,
                "lookahead_violation_flag": False,
                "fundamental_quality_bucket": "quality_strong",
                "fundamental_momentum_bucket": "improving",
                "fundamental_risk_flag": False,
            },
            {
                "trade_date": "2025-01-03",
                "asset_id": "B",
                "pit_valid_flag": True,
                "lookahead_violation_flag": False,
                "fundamental_quality_bucket": "quality_weak",
                "fundamental_momentum_bucket": "deteriorating",
                "fundamental_risk_flag": True,
            },
            {
                "trade_date": "2025-01-03",
                "asset_id": "C",
                "pit_valid_flag": True,
                "lookahead_violation_flag": False,
                "fundamental_quality_bucket": "quality_neutral",
                "fundamental_momentum_bucket": "stable",
                "fundamental_risk_flag": False,
            },
            {
                "trade_date": "2025-01-03",
                "asset_id": "D",
                "pit_valid_flag": True,
                "lookahead_violation_flag": False,
                "fundamental_quality_bucket": "quality_strong",
                "fundamental_momentum_bucket": "stable",
                "fundamental_risk_flag": False,
            },
        ]
    )


def _trade_changes() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "source_strategy": "top10",
                "trade_date": "2025-01-03",
                "asset_id": "A",
                "stock_name": "Alpha",
                "industry_name": "Tech",
                "action": "buy",
                "target_weight": 0.1,
                "audit_label": "bad_buy",
                "forward_return": -0.10,
                "weighted_bad_buy_loss": -0.01,
                "mid_trend_layer": "high_elasticity_watch",
                "technical_confirmed": True,
                "mainline_confirmed": True,
            },
            {
                "source_strategy": "top10",
                "trade_date": "2025-01-03",
                "asset_id": "B",
                "stock_name": "Beta",
                "industry_name": "Auto",
                "action": "buy",
                "target_weight": 0.1,
                "audit_label": "bad_buy",
                "forward_return": -0.30,
                "weighted_bad_buy_loss": -0.03,
                "mid_trend_layer": "high_elasticity_watch",
                "technical_confirmed": True,
                "mainline_confirmed": False,
            },
            {
                "source_strategy": "top10",
                "trade_date": "2025-01-03",
                "asset_id": "C",
                "stock_name": "Core",
                "industry_name": "Tech",
                "action": "buy",
                "target_weight": 0.1,
                "audit_label": "",
                "forward_return": 0.25,
                "weighted_bad_buy_loss": 0.0,
                "mid_trend_layer": "stable_trend_watch",
                "technical_confirmed": True,
                "mainline_confirmed": True,
            },
            {
                "source_strategy": "top10",
                "trade_date": "2025-01-03",
                "asset_id": "D",
                "stock_name": "Delta",
                "industry_name": "Health",
                "action": "buy",
                "target_weight": 0.1,
                "audit_label": "bad_buy",
                "forward_return": -0.05,
                "forward_return_30d": 0.18,
                "weighted_bad_buy_loss": -0.005,
                "mid_trend_layer": "mainline_momentum_watch",
                "technical_confirmed": True,
                "mainline_confirmed": True,
            },
            {
                "source_strategy": "top10",
                "trade_date": "2025-01-04",
                "asset_id": "A",
                "action": "sell",
                "target_weight": 0.0,
                "audit_label": "",
                "forward_return": 0.0,
            },
        ]
    )


def test_validate_daily_review_lite_artifact_counts_and_blocks_trading_words(tmp_path: Path) -> None:
    from stock_research.midtrend_daily_review_lite_and_badbuy_denominator_v1 import (
        validate_daily_review_lite_artifact,
    )

    artifact = tmp_path / "lite.json"
    artifact.write_text(
        """
        {
          "sections": {
            "HIGH_FUNDAMENTAL": {"items": [{"asset_id": "A", "suggested_review_action": "review_strong_improving_post_exit_name"}]},
            "HIGH_TECH_MAINLINE": {"items": []},
            "MEDIUM_FUNDAMENTAL_WATCH": {"items": []},
            "RISK_DOWNGRADE": {"items": [{"asset_id": "B", "suggested_review_action": "downgrade_fundamental_weak_or_deteriorating"}]},
            "LOW_OR_EXPIRED": {"items": []}
          }
        }
        """,
        encoding="utf-8",
    )

    validation = validate_daily_review_lite_artifact(artifact)
    row = validation.iloc[0]
    assert row["artifact_exists"] is True
    assert row["total_items"] == 2
    assert row["section_count_HIGH_FUNDAMENTAL"] == 1
    assert row["section_count_RISK_DOWNGRADE"] == 1
    assert row["invalid_action_word_count"] == 0
    assert row["schema_valid_flag"] is True


def test_build_bad_buy_denominator_events_uses_canonical_pit_bucket() -> None:
    from stock_research.midtrend_daily_review_lite_and_badbuy_denominator_v1 import (
        build_bad_buy_denominator_events,
    )

    events = build_bad_buy_denominator_events(_trade_changes(), _pit())

    assert events["action"].tolist() == ["buy", "buy", "buy", "buy"]
    row_a = events[events["asset_id"].eq("A")].iloc[0]
    assert row_a["canonical_fundamental_quality_bucket"] == "quality_strong"
    assert row_a["canonical_fundamental_momentum_bucket"] == "improving"
    assert row_a["fundamental_bucket_source"] == "pit"
    assert row_a["is_bad_buy"] is True
    assert row_a["is_winner"] is False


def test_bad_buy_rate_and_net_contribution_by_bucket() -> None:
    from stock_research.midtrend_daily_review_lite_and_badbuy_denominator_v1 import (
        build_bad_buy_denominator_events,
        build_bad_buy_denominator_rate_by_bucket,
    )

    events = build_bad_buy_denominator_events(_trade_changes(), _pit())
    summary = build_bad_buy_denominator_rate_by_bucket(events)
    quality_rows = summary[summary["group_type"].eq("canonical_fundamental_quality_bucket")]
    weak = quality_rows[quality_rows["group_value"].eq("quality_weak")].iloc[0]
    neutral = quality_rows[quality_rows["group_value"].eq("quality_neutral")].iloc[0]
    strong = quality_rows[quality_rows["group_value"].eq("quality_strong")].iloc[0]

    assert weak["total_entry_count"] == 1
    assert weak["bad_buy_rate"] == 1.0
    assert weak["net_bucket_contribution"] < 0
    assert neutral["winner_rate"] == 1.0
    assert strong["bad_buy_count"] == 2
    assert strong["bad_buy_rate"] == 1.0


def test_quality_strong_recovery_and_quality_weak_left_tail_outputs() -> None:
    from stock_research.midtrend_daily_review_lite_and_badbuy_denominator_v1 import (
        build_bad_buy_denominator_events,
        build_quality_strong_recovery_analysis,
        build_quality_weak_left_tail_analysis,
    )

    events = build_bad_buy_denominator_events(_trade_changes(), _pit())
    strong = build_quality_strong_recovery_analysis(events)
    weak = build_quality_weak_left_tail_analysis(events)

    assert strong.iloc[0]["count"] == 2
    assert strong.iloc[0]["recovery_rate_30d"] == 0.5
    assert weak.iloc[0]["count"] == 1
    assert weak.iloc[0]["worst_10_loss"] == -0.3
    assert weak.iloc[0]["weighted_bad_buy_loss"] == -0.03


def test_runner_writes_required_research_only_outputs(tmp_path: Path) -> None:
    from stock_research.midtrend_daily_review_lite_and_badbuy_denominator_v1 import (
        run_midtrend_daily_review_lite_and_badbuy_denominator_from_frames,
    )

    artifact = tmp_path / "lite.json"
    artifact.write_text('{"sections":{"HIGH_FUNDAMENTAL":{"items":[]},"HIGH_TECH_MAINLINE":{"items":[]},"MEDIUM_FUNDAMENTAL_WATCH":{"items":[]},"RISK_DOWNGRADE":{"items":[]},"LOW_OR_EXPIRED":{"items":[]}}}', encoding="utf-8")
    out = tmp_path / "out"

    result = run_midtrend_daily_review_lite_and_badbuy_denominator_from_frames(
        lite_artifact_path=artifact,
        trade_changes=_trade_changes(),
        pit_features=_pit(),
        output_dir=out,
        frontend_integration_files=[],
    )

    assert result["paths"]["output_dir"] == str(out)
    for filename in [
        "daily_review_lite_artifact_validation.csv",
        "daily_review_lite_frontend_integration_report.md",
        "bad_buy_denominator_events_canonical.csv",
        "bad_buy_denominator_rate_by_bucket.csv",
        "bad_buy_quality_strong_recovery_analysis.csv",
        "bad_buy_quality_weak_left_tail_analysis.csv",
        "fundamental_entry_gate_readiness_research_only.md",
        "final_interpretation.md",
    ]:
        assert (out / filename).exists(), filename
    readiness = (out / "fundamental_entry_gate_readiness_research_only.md").read_text(encoding="utf-8")
    assert "RESEARCH_ONLY" in readiness
    assert "NOT_READY" in readiness
