from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_tech_bottleneck_manual_review_label_schema.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_manual_review_label_schema_v1"


def _load_module():
    spec = importlib.util.spec_from_file_location("manual_review_schema", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_label_dictionary_contains_required_groups_and_flags() -> None:
    labels = pd.read_csv(OUTPUT_DIR / "manual_review_label_dictionary.csv")
    groups = set(labels["label_group"])
    assert {
        "thesis_review",
        "announcement_review",
        "fundamental_review",
        "valuation_review",
        "risk_review",
        "data_quality_review",
        "review_conclusion",
    }.issubset(groups)
    assert set(labels["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert {"manual_review_conclusion", "research_status_after_manual", "thesis_clarity"}.issubset(set(labels["label_name"]))


def test_form_status_and_actions_are_research_only() -> None:
    module = _load_module()
    form = pd.read_csv(OUTPUT_DIR / "manual_review_form_schema.csv")
    status = pd.read_csv(OUTPUT_DIR / "manual_review_status_enum.csv")
    actions = pd.read_csv(OUTPUT_DIR / "manual_review_action_enum.csv")
    assert not form["field_name"].str.contains("target|position|entry|exit", case=False).any()
    assert not status["enum_value"].str.contains("target|position|entry|exit", case=False).any()
    allowed = actions[actions["allowed_in_dashboard"].astype(str).str.lower().eq("true")]
    forbidden = actions[actions["allowed_in_dashboard"].astype(str).str.lower().eq("false")]
    assert not allowed.empty
    assert not forbidden.empty
    assert {"open_consolidated_report", "save_review_labels", "request_more_news_source"}.issubset(set(allowed["action_name"]))
    assert {"buy", "sell", "set_target_price", "create_entry_signal", "create_exit_signal"}.issubset(set(forbidden["action_name"]))
    assert not module.contains_actionable_trading_language(allowed.to_csv(index=False))
    assert set(allowed["used_for_signal"].astype(str).str.lower()) == {"false"}


def test_data_products_and_dashboard_contract_are_research_only() -> None:
    products = pd.read_csv(OUTPUT_DIR / "manual_review_data_product_spec.csv")
    dashboard = pd.read_csv(OUTPUT_DIR / "manual_review_dashboard_contract_patch.csv")
    assert len(products) >= 5
    assert len(dashboard) >= 7
    assert products["file_name"].str.contains("manual_review").all()
    assert set(products["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert set(dashboard["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert dashboard["writeback_target"].astype(str).str.contains("formal|strategy|production", case=False).sum() == 0


def test_quality_audit_distinguishes_forbidden_list_from_violations() -> None:
    module = _load_module()
    audit = pd.read_csv(OUTPUT_DIR / "manual_review_quality_audit.csv")
    metrics = dict(zip(audit["metric"], audit["value"]))
    assert int(metrics["trading language hit count"]) == 0
    assert int(metrics["forbidden trading actions listed"]) >= 8
    assert int(metrics["baseline admission change count"]) == 0
    assert int(metrics["lookahead violation rows"]) == 0
    strategy_status = str(metrics["formal strategy file status"])
    assert strategy_status == "clean" or "src/stock_research/tech_bottleneck_v1.py" in strategy_status
    for path in OUTPUT_DIR.rglob("*"):
        if path.name == "manual_review_action_enum.csv":
            continue
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            assert not module.contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")), path
