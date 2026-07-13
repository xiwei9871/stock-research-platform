from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_tech_bottleneck_research_selection_layer_v2_generator.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_research_selection_layer_v2_generator_v1"


def _load_module():
    spec = importlib.util.spec_from_file_location("v2_generator", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_candidates_preserve_baseline_and_research_flags() -> None:
    candidates = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_research_selection_v2_candidates.csv")
    assert len(candidates) == 102
    assert candidates["asset_id"].nunique() == 102
    assert set(candidates["baseline_admission_changed"].astype(str).str.lower()) == {"false"}
    assert set(candidates["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert set(candidates["baseline_admission_status"]) == {"baseline_standard_watchlist"}
    assert not candidates.columns.str.contains("target|position|entry|exit", case=False).any()


def test_review_priority_and_risk_queue_are_review_only() -> None:
    module = _load_module()
    priority = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_research_selection_v2_review_priority.csv")
    risk = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_research_selection_v2_risk_queue.csv")
    assert not priority.empty
    assert not risk.empty
    assert {"priority_high_fundamental_review", "priority_risk_review", "priority_data_gap_review"}.intersection(
        set(priority["priority_level"])
    )
    assert {
        "announcement_specific_risk_event",
        "missing_announcement_support",
        "missing_fundamental_support",
        "missing_full_financial_statement",
        "missing_news_source",
    }.issubset(set(risk["risk_type"]))
    assert set(priority["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert set(risk["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert set(risk["auto_exclude"].astype(str).str.lower()) == {"false"}
    assert not module.contains_actionable_trading_language(priority.to_csv(index=False))
    assert not module.contains_actionable_trading_language(risk.to_csv(index=False))


def test_dashboard_table_and_quality_audit() -> None:
    dashboard = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_research_selection_v2_dashboard_table.csv")
    audit = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_research_selection_v2_quality_audit.csv")
    metrics = dict(zip(audit["metric"], audit["value"]))
    assert len(dashboard) == 102
    assert dashboard["asset_id"].nunique() == 102
    assert set(dashboard["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert not dashboard.columns.str.contains("target|position|entry|exit", case=False).any()
    assert int(metrics["baseline admission changed count"]) == 0
    assert int(metrics["auto exclude count"]) == 0
    assert int(metrics["trading language hit count"]) == 0
    assert int(metrics["lookahead violation rows"]) == 0


def test_outputs_are_clean_and_formal_strategy_unchanged() -> None:
    module = _load_module()
    audit = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_research_selection_v2_quality_audit.csv")
    metrics = dict(zip(audit["metric"], audit["value"]))
    strategy_status = str(metrics["formal strategy file status"])
    assert strategy_status == "clean" or "src/stock_research/tech_bottleneck_v1.py" in strategy_status
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            assert not module.contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")), path
