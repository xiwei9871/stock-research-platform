from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_tech_bottleneck_manual_review_template.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_manual_review_template_v1"


def _load_module():
    spec = importlib.util.spec_from_file_location("manual_review_template", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_labels_template_rows_defaults_and_schema_coverage() -> None:
    labels = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_manual_review_labels_template.csv")
    assert len(labels) == 102
    assert labels["asset_id"].nunique() == 102
    required = {
        "thesis_clarity",
        "announcement_evidence_quality",
        "fundamental_recovery_validity",
        "valuation_context_reasonableness",
        "risk_level_manual",
        "source_coverage_quality",
        "manual_review_conclusion",
        "research_status_after_manual",
    }
    assert required.issubset(set(labels.columns))
    assert set(labels["review_status"]) == {"not_started"}
    assert set(labels["manual_review_conclusion"]) == {"not_reviewed"}
    assert set(labels["research_status_after_manual"]) == {"not_reviewed"}
    assert set(labels["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert set(labels["baseline_admission_changed"].astype(str).str.lower()) == {"false"}


def test_history_template_empty_and_dashboard_allowed_actions() -> None:
    history = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_manual_review_history_template.csv")
    dashboard = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_manual_review_dashboard_table_template.csv")
    assert history.empty
    assert {
        "review_id",
        "asset_id",
        "review_round",
        "review_timestamp",
        "used_for_signal",
        "baseline_admission_changed",
    }.issubset(set(history.columns))
    assert len(dashboard) == 102
    assert set(dashboard["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert set(dashboard["baseline_admission_changed"].astype(str).str.lower()) == {"false"}
    forbidden = "buy|sell|add_position|reduce_position|hold_position|set_target_price|set_position_size|create_entry_signal|create_exit_signal|override_strategy_score"
    assert not dashboard["allowed_actions"].astype(str).str.contains(forbidden, case=False, regex=True).any()


def test_field_guide_and_quality_audit_are_clean() -> None:
    module = _load_module()
    guide = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_manual_review_template_field_guide.csv")
    audit = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_manual_review_template_quality_audit.csv")
    metrics = dict(zip(audit["metric"], audit["value"]))
    assert len(guide) >= 48
    assert not module.contains_actionable_trading_language(guide.to_csv(index=False))
    assert int(metrics["template candidate rows"]) == 102
    assert int(metrics["dashboard template rows"]) == 102
    assert int(metrics["forbidden action leakage count"]) == 0
    assert int(metrics["trading language hit count"]) == 0
    assert int(metrics["lookahead violation rows"]) == 0
    assert int(metrics["baseline admission changed count"]) == 0


def test_outputs_are_clean_and_formal_strategy_unchanged() -> None:
    module = _load_module()
    audit = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_manual_review_template_quality_audit.csv")
    metrics = dict(zip(audit["metric"], audit["value"]))
    strategy_status = str(metrics["formal strategy file status"])
    assert strategy_status == "clean" or "src/stock_research/tech_bottleneck_v1.py" in strategy_status
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            assert not module.contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")), path
