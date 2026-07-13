from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_research_selection_layer_v2_design"


def _load_module():
    path = PROJECT_ROOT / "scripts/run_tech_bottleneck_research_selection_layer_v2_design.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_research_selection_layer_v2_design", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_feature_dictionary_covers_required_groups_and_keeps_forward_return_out() -> None:
    features = pd.read_csv(OUTPUT_DIR / "research_selection_v2_feature_dictionary.csv")

    groups = set(features["feature_group"])
    assert {"announcement", "fundamental", "valuation", "cross_source_validation", "data_quality"}.issubset(groups)
    assert "announcement_fulltext_support" in set(features["feature_name"])
    assert "fundamental_quality_level" in set(features["feature_name"])
    assert "valuation_context_level" in set(features["feature_name"])
    assert "baidu_validation_status" in set(features["feature_name"])
    assert not features["feature_name"].str.contains("forward_return", na=False).any()
    assert features["must_not_use_for_signal"].astype(bool).all()


def test_pit_feasibility_marks_snapshot_and_dashboard_as_ex_post_only() -> None:
    matrix = pd.read_csv(OUTPUT_DIR / "research_selection_v2_pit_feasibility_matrix.csv")
    ex_post_layers = matrix[~matrix["pit_feasible_now"].astype(bool)]["source_layer"].tolist()

    assert "consolidated snapshot" in ex_post_layers
    assert "dashboard readonly" in ex_post_layers
    assert "forward return" in ex_post_layers
    assert matrix["pit_gap"].str.contains("ex-post|not selection", case=False, na=False).any()


def test_rule_candidates_are_research_only_and_include_required_candidates() -> None:
    rules = pd.read_csv(OUTPUT_DIR / "research_selection_v2_rule_candidates.csv")
    names = set(rules["rule_candidate_name"])

    assert "v2_baseline_plus_fundamental_quality" in names
    assert "v2_announcement_risk_review_queue" in names
    assert "v2_high_quality_review_candidates" in names
    assert not rules["used_for_signal"].astype(bool).any()
    assert rules["recommended_status"].isin(
        ["use_as_review_priority", "use_as_dashboard_filter", "requires_pit_replay", "do_not_use", "manual_review_only"]
    ).all()


def test_review_priority_warning_and_dashboard_rules_are_non_execution() -> None:
    module = _load_module()
    priority = pd.read_csv(OUTPUT_DIR / "research_selection_v2_review_priority_rules.csv")
    warnings = pd.read_csv(OUTPUT_DIR / "research_selection_v2_exclusion_and_warning_rules.csv")
    filters = pd.read_csv(OUTPUT_DIR / "research_selection_v2_dashboard_filter_plan.csv")

    assert not priority["used_for_signal"].astype(bool).any()
    assert not warnings["used_for_signal"].astype(bool).any()
    assert not filters["used_for_signal"].astype(bool).any()
    assert not warnings["auto_exclude"].astype(bool).any()
    assert "fundamental_recovery_signal" in set(filters["source_field"])
    assert "valuation_context_level" in set(filters["source_field"])
    assert not module.contains_actionable_trading_language(priority.to_csv(index=False))
    assert not module.contains_actionable_trading_language(filters.to_csv(index=False))


def test_replay_plan_and_quality_audit_are_clean() -> None:
    replay = pd.read_csv(OUTPUT_DIR / "research_selection_v2_replay_plan.csv")
    audit = pd.read_csv(OUTPUT_DIR / "research_selection_v2_quality_audit.csv")
    lookup = dict(zip(audit["metric"], audit["value"]))

    assert "tech_bottleneck_research_selection_layer_v2_pit_replay_v1" in set(replay["replay_task_name"])
    assert int(lookup["lookahead violation rows"]) == 0
    assert int(lookup["trading language hit count"]) == 0
    assert int(lookup["rule candidates generated"]) >= 6


def test_outputs_have_no_trading_language_and_report_mentions_untracked_status() -> None:
    module = _load_module()
    report = (OUTPUT_DIR / "research_selection_layer_v2_design.md").read_text(encoding="utf-8")

    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            assert not module.contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")), path
    assert "无法仅靠 `git diff` 完整证明" in report
