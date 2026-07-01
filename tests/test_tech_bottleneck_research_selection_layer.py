from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_tech_bottleneck_research_selection_layer.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_research_selection_layer", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_review_card_actions_are_review_only_and_not_trading_language():
    module = _load_module()
    cards = pd.DataFrame(
        {
            "recommended_action_for_reviewer": [
                "review_thesis",
                "monitor_setup",
                "review_data_quality",
                "risk_review_required",
                "ignore_until_reconfirmed",
                "watch_only",
            ]
        }
    )

    assert module.validate_review_actions(cards)


def test_review_card_rejects_trading_language():
    module = _load_module()
    cards = pd.DataFrame({"recommended_action_for_reviewer": ["buy", "review_thesis"]})

    assert not module.validate_review_actions(cards)


def test_missing_evidence_is_neutral_not_0p6_penalty():
    module = _load_module()
    row = pd.Series(
        {
            "source_backed_field_count": 0,
            "low_position_score": 0.5,
            "commercial_validation_score": 0.5,
            "freshness_score": 0.5,
            "fundamental_risk_score": 0.0,
        }
    )

    score = module.compute_research_candidate_score(row)

    assert score > 0.0
    assert score != 0.6
    assert module.evidence_quality_score(0) == 0.5


def test_evidence_is_active_only_on_or_after_source_date():
    module = _load_module()
    evidence = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "source_date": "2026-01-10",
                "field": "revenue_exposure_bucket",
                "source_type": "broker_report",
            }
        ]
    )

    assert module.active_evidence_count(evidence, asset_id="A", trade_date="2026-01-09") == 0
    assert module.active_evidence_count(evidence, asset_id="A", trade_date="2026-01-10") == 1


def test_research_candidates_do_not_emit_trade_signal_columns():
    module = _load_module()
    candidates = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-10",
                "asset_id": "A",
                "stock_name": "A",
                "bottleneck_score": 0.5,
                "source_backed_field_count": 0,
                "low_position_score": 0.5,
                "commercial_validation_score": 0.5,
                "freshness_score": 0.5,
                "fundamental_risk_score": 0.0,
            }
        ]
    )

    result = module.build_research_candidates(candidates)

    forbidden = {"buy_signal", "sell_signal", "entry_allowed", "target_weight", "trade_signal"}
    assert forbidden.isdisjoint(result.columns)


def test_source_coverage_flags_lookahead_violations():
    module = _load_module()
    candidates = pd.DataFrame(
        [
            {"trade_date": "2026-01-09", "asset_id": "A"},
            {"trade_date": "2026-01-10", "asset_id": "A"},
        ]
    )
    evidence = pd.DataFrame(
        [
            {"asset_id": "A", "source_date": "2026-01-10", "source_type": "broker_report", "field": "revenue"}
        ]
    )

    coverage = module.build_source_coverage(candidates, evidence)

    assert int(coverage["lookahead_violation_rows"].sum()) == 0
    assert coverage.loc[coverage["trade_date"].eq("2026-01-09"), "pit_evidence_count"].iloc[0] == 0
    assert coverage.loc[coverage["trade_date"].eq("2026-01-10"), "pit_evidence_count"].iloc[0] == 1
