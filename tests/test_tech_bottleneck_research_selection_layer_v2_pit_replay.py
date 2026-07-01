from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_tech_bottleneck_research_selection_layer_v2_pit_replay.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_research_selection_layer_v2_pit_replay_v1"


def _load_module():
    spec = importlib.util.spec_from_file_location("pit_replay", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_variant_definitions_include_baseline_and_v2_candidates_without_outcome_conditions() -> None:
    variants = pd.read_csv(OUTPUT_DIR / "v2_pit_replay_variant_definitions.csv")
    names = set(variants["variant_name"])
    assert {
        "baseline_standard_watchlist",
        "v2_baseline_plus_fundamental_quality",
        "v2_high_quality_review_candidates",
        "v2_announcement_risk_review_queue",
        "v2_specific_validation_review_priority",
        "v2_fundamental_recovery_positive",
        "v2_valuation_context_event_recomputed",
    }.issubset(names)
    assert set(variants["validation_mode"]) == {"pit_feasible_replay"}
    assert set(variants["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert not variants["required_conditions"].astype(str).str.contains("forward_return", case=False).any()


def test_candidate_events_are_pit_feasible_and_do_not_use_snapshot_sources() -> None:
    events = pd.read_csv(OUTPUT_DIR / "v2_pit_replay_candidate_events.csv")
    assert not events.empty
    assert set(events["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert events["pit_feasible"].astype(bool).all()
    assert events["required_features_available"].astype(bool).all()
    assert not events["source_dates_used"].astype(str).str.contains("consolidated_snapshot|dashboard_readonly", case=False).any()

    feature_matrix = pd.read_csv(OUTPUT_DIR / "v2_pit_replay_event_feature_matrix.csv")
    assert {"snapshot_only", "outcome_only"}.isdisjoint(set(feature_matrix.get("pit_status", pd.Series(dtype=str))))
    assert not feature_matrix["source_layer"].isin({"consolidated_snapshot", "dashboard_readonly", "forward_return"}).any()
    assert set(feature_matrix["used_for_signal"].astype(str).str.lower()) == {"false"}


def test_valuation_context_and_baidu_validation_are_recomputed_by_event_date() -> None:
    valuation = pd.read_csv(OUTPUT_DIR / "v2_pit_replay_recomputed_valuation_context.csv")
    baidu = pd.read_csv(OUTPUT_DIR / "v2_pit_replay_recomputed_baidu_validation.csv")
    assert len(valuation) == 102
    assert len(baidu) == 102
    assert pd.to_datetime(valuation["baostock_date_used"]).le(pd.to_datetime(valuation["first_admission_date"])).all()
    assert pd.to_datetime(baidu["baostock_date_used"]).le(pd.to_datetime(baidu["first_admission_date"])).all()
    for col in ["baidu_trade_date_pe_ttm_used", "baidu_trade_date_pb_used", "baidu_trade_date_market_cap_used"]:
        dated = pd.to_datetime(baidu[col], errors="coerce")
        assert dated.dropna().le(pd.to_datetime(baidu.loc[dated.notna(), "first_admission_date"])).all()
    assert not valuation["valuation_context_level_event"].isna().all()
    assert set(baidu["baidu_ps_ttm_available"].astype(str).str.lower()) == {"false"}
    assert int(valuation["lookahead_violation"].sum()) == 0
    assert int(baidu["lookahead_violation"].sum()) == 0


def test_forward_return_outputs_are_outcome_only_and_use_required_horizons() -> None:
    forward = pd.read_csv(OUTPUT_DIR / "v2_pit_replay_forward_return_30_60_90_120.csv")
    assert set(forward["horizon"]) == {"30d", "60d", "90d", "120d"}
    assert set(forward["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert not forward.columns.str.contains("entry|exit|target|position", case=False).any()

    summary = pd.read_csv(OUTPUT_DIR / "v2_pit_replay_variant_summary.csv")
    assert "baseline_standard_watchlist" in set(summary["variant_name"])
    assert summary["sample_quality_warning"].isin({"ok", "sample_too_small", "not_enough_to_conclude"}).all()


def test_quality_audit_and_outputs_are_clean() -> None:
    module = _load_module()
    audit = pd.read_csv(OUTPUT_DIR / "v2_pit_replay_quality_audit.csv")
    metrics = dict(zip(audit["metric"], audit["value"]))
    assert int(metrics["lookahead violation rows"]) == 0
    assert int(metrics["snapshot label usage count"]) == 0
    assert int(metrics["forward return used as feature count"]) == 0
    assert int(metrics["trading language hit count"]) == 0
    assert "?? src/stock_research/tech_bottleneck_v1.py" in str(metrics["formal strategy file status"])

    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            assert not module.contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")), path
