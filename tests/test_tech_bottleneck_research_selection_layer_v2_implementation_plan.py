from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_tech_bottleneck_research_selection_layer_v2_implementation_plan.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_research_selection_layer_v2_implementation_plan"


def _load_module():
    spec = importlib.util.spec_from_file_location("v2_implementation_plan", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_final_rule_set_contains_required_research_rules() -> None:
    rules = pd.read_csv(OUTPUT_DIR / "research_selection_v2_final_rule_set.csv")
    names = set(rules["rule_name"])
    assert {
        "v2_fundamental_quality_review_priority",
        "v2_fundamental_recovery_review_priority",
        "v2_high_quality_review_queue",
        "v2_specific_validation_thesis_review",
        "v2_announcement_risk_review_queue",
        "v2_valuation_context_dashboard_filter",
        "v2_baidu_validation_warning",
    }.issubset(names)
    assert set(rules["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert set(rules["must_not_change_baseline_admission"].astype(str).str.lower()) == {"true"}
    assert set(rules["implementation_scope"]).issubset({"research_outputs", "dashboard_readonly", "manual_review"})


def test_review_priority_dashboard_and_data_products_are_non_execution() -> None:
    module = _load_module()
    priority = pd.read_csv(OUTPUT_DIR / "research_selection_v2_review_priority_contract.csv")
    dashboard = pd.read_csv(OUTPUT_DIR / "research_selection_v2_dashboard_contract_patch.csv")
    products = pd.read_csv(OUTPUT_DIR / "research_selection_v2_data_product_spec.csv")
    assert len(priority) >= 5
    assert len(dashboard) >= 10
    assert len(products) >= 6
    assert set(priority["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert set(dashboard["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert set(products["used_for_signal"].astype(str).str.lower()) == {"false"}
    for df in [priority, dashboard, products]:
        assert not module.contains_actionable_trading_language(df.to_csv(index=False))
    assert not dashboard["dashboard_field"].str.contains("target|position|entry|exit", case=False).any()


def test_acceptance_criteria_and_risks_cover_required_boundaries() -> None:
    criteria = pd.read_csv(OUTPUT_DIR / "research_selection_v2_acceptance_criteria.csv")
    risks = pd.read_csv(OUTPUT_DIR / "research_selection_v2_risk_and_limitations.csv")
    criteria_text = "\n".join(criteria["criteria"].astype(str).tolist()).lower()
    risk_text = "\n".join(risks[["risk_name", "description"]].astype(str).agg(" ".join, axis=1).tolist()).lower()
    assert "baseline admission unchanged" in criteria_text
    assert "used_for_signal = false" in criteria_text
    assert "lookahead violation rows = 0" in criteria_text
    assert "announcement coverage" in risk_text
    assert "fundamental coverage" in risk_text
    assert "formal strategy files currently untracked" in risk_text


def test_implementation_steps_quality_audit_and_outputs_are_clean() -> None:
    module = _load_module()
    steps = pd.read_csv(OUTPUT_DIR / "research_selection_v2_implementation_steps.csv")
    audit = pd.read_csv(OUTPUT_DIR / "research_selection_v2_quality_audit.csv")
    metrics = dict(zip(audit["metric"], audit["value"]))
    assert len(steps) >= 10
    assert int(metrics["final rules generated"]) >= 7
    assert int(metrics["baseline admission change count"]) == 0
    assert int(metrics["lookahead violation rows"]) == 0
    assert int(metrics["trading language hit count"]) == 0
    assert "?? src/stock_research/tech_bottleneck_v1.py" in str(metrics["formal strategy file status"])
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            assert not module.contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")), path
