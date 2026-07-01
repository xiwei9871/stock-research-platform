from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_tech_bottleneck_research_selection_layer_v2_pit_input_reconstruction.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_research_selection_layer_v2_pit_input_reconstruction_v1"


def _load_module():
    spec = importlib.util.spec_from_file_location("pit_input_reconstruction", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_source_date_inventory_marks_non_pit_layers_and_outcome_layer() -> None:
    inventory = pd.read_csv(OUTPUT_DIR / "pit_source_date_inventory.csv")
    layers = set(inventory["source_layer"])
    assert {
        "announcement_fulltext",
        "fundamental_derived_pit",
        "baostock_valuation",
        "baidu_validation",
        "consolidated_snapshot",
        "dashboard_readonly",
        "forward_return",
    }.issubset(layers)

    consolidated = inventory[inventory["source_layer"].eq("consolidated_snapshot")].iloc[0]
    dashboard = inventory[inventory["source_layer"].eq("dashboard_readonly")].iloc[0]
    forward = inventory[inventory["source_layer"].eq("forward_return")].iloc[0]
    assert consolidated["pit_ready"] is False or str(consolidated["pit_ready"]).lower() == "false"
    assert dashboard["pit_ready"] is False or str(dashboard["pit_ready"]).lower() == "false"
    assert "not PIT source" in consolidated["pit_gap"]
    assert "not PIT source" in dashboard["pit_gap"]
    assert "outcome" in forward["pit_gap"]


def test_feature_availability_contains_usable_date_and_research_flags() -> None:
    features = pd.read_csv(OUTPUT_DIR / "pit_feature_availability_by_asset.csv")
    assert "usable_date" in features.columns
    assert "used_for_signal" in features.columns
    assert set(features["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert {"snapshot_only", "outcome_only"}.issubset(set(features["pit_status"]))
    available = features[features["pit_status"].eq("pit_available")]
    if not available.empty:
        assert pd.to_datetime(available["usable_date"]).le(pd.to_datetime(available["first_admission_date"])).all()


def test_event_readiness_has_102_standard_events_and_no_forced_full_readiness() -> None:
    events = pd.read_csv(OUTPUT_DIR / "pit_feature_availability_by_event.csv")
    assert len(events) == 102
    assert set(events["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert events["event_pit_readiness"].isin({"ready_for_v2_replay", "partial_ready", "not_ready", "only_baseline_ready"}).all()
    assert not events["all_v2_core_features_pit_available"].astype(bool).all()
    assert events["pit_blocking_features"].astype(str).str.len().gt(0).any()


def test_rule_candidate_readiness_does_not_force_ex_post_rules_ready() -> None:
    readiness = pd.read_csv(OUTPUT_DIR / "pit_rule_candidate_readiness.csv")
    assert len(readiness) >= 6
    assert set(readiness["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert readiness["pit_replay_status"].isin(
        {"ready_for_replay", "partial_replay_possible", "blocked_by_source_dates", "ex_post_only", "do_not_replay"}
    ).all()
    assert not readiness["pit_replay_status"].eq("ready_for_replay").all()
    valuation = readiness[readiness["rule_candidate_name"].eq("v2_valuation_context_filter")]
    assert not valuation.empty
    assert valuation["pit_replay_status"].iloc[0] != "ready_for_replay"


def test_replay_ready_events_are_strictly_pit_ready() -> None:
    ready = pd.read_csv(OUTPUT_DIR / "pit_replay_ready_candidate_events.csv")
    expected = {
        "rule_candidate_name",
        "asset_id",
        "first_admission_date",
        "required_features_available",
        "pit_replay_ready",
        "used_for_signal",
    }
    assert expected.issubset(set(ready.columns))
    if not ready.empty:
        assert ready["pit_replay_ready"].astype(bool).all()
        assert ready["required_features_available"].astype(bool).all()
        assert set(ready["used_for_signal"].astype(str).str.lower()) == {"false"}


def test_blockers_audit_and_outputs_are_clean() -> None:
    module = _load_module()
    blockers = pd.read_csv(OUTPUT_DIR / "pit_replay_blocker_report.csv")
    assert {
        "missing_source_date",
        "source_after_admission",
        "snapshot_only_feature",
        "outcome_feature",
        "insufficient_ready_events",
    }.intersection(set(blockers["blocker_type"]))
    assert {"announcement_fulltext", "fundamental_derived_pit", "baostock_valuation", "baidu_validation"}.issubset(
        set(blockers["source_layer"])
    )

    audit = pd.read_csv(OUTPUT_DIR / "pit_input_reconstruction_quality_audit.csv")
    metrics = dict(zip(audit["metric"], audit["value"]))
    assert int(metrics["lookahead violation rows"]) == 0
    assert int(metrics["trading language hit count"]) == 0
    assert int(metrics["source layers evaluated"]) >= 7
    assert "?? src/stock_research/tech_bottleneck_v1.py" in str(metrics["formal strategy file status"])

    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            assert not module.contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")), path
