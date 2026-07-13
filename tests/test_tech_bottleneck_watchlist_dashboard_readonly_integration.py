from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_tech_bottleneck_watchlist_dashboard_readonly_integration.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_dashboard_readonly_integration_v1"


def _load_module():
    spec = importlib.util.spec_from_file_location("dashboard_readonly_integration", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_data_contract_counts_and_mode() -> None:
    contract = json.loads((OUTPUT_DIR / "dashboard_readonly_data_contract_v2.json").read_text(encoding="utf-8"))
    assert contract["mode"] == "read_only_research_review"
    assert contract["watchlist_count"] == 102
    assert contract["quality_controls"]["v2_candidates_count"] == 102
    assert contract["quality_controls"]["dashboard_table_count"] == 102
    assert contract["quality_controls"]["manual_review_template_rows"] == 102
    assert contract["quality_controls"]["report_links_count"] == 102
    assert contract["quality_controls"]["used_for_signal"] is False


def test_allowed_actions_exclude_forbidden_and_no_writeback() -> None:
    contract = json.loads((OUTPUT_DIR / "dashboard_readonly_data_contract_v2.json").read_text(encoding="utf-8"))
    allowed = {item["action_name"] for item in contract["allowed_actions"]}
    forbidden = {item["action_name"] for item in contract["forbidden_actions"]}
    assert allowed
    assert forbidden
    assert allowed.isdisjoint(forbidden)

    route = pd.read_csv(OUTPUT_DIR / "dashboard_readonly_route_plan.csv")
    components = pd.read_csv(OUTPUT_DIR / "dashboard_readonly_component_plan.csv")
    assert set(route["writeback_allowed"].astype(str).str.lower()) == {"false"}
    assert set(route["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert set(components["writeback_allowed"].astype(str).str.lower()) == {"false"}
    assert set(components["used_for_signal"].astype(str).str.lower()) == {"false"}


def test_field_mapping_and_audit_are_clean() -> None:
    module = _load_module()
    mapping = pd.read_csv(OUTPUT_DIR / "dashboard_readonly_field_mapping.csv")
    audit = pd.read_csv(OUTPUT_DIR / "dashboard_readonly_integration_quality_audit.csv")
    metrics = dict(zip(audit["metric"], audit["value"]))
    assert {"v2_review_priority", "manual_review_status", "consolidated_report_path"}.issubset(set(mapping["dashboard_field"]))
    assert not mapping["dashboard_field"].str.contains("target|position|entry|exit", case=False).any()
    assert set(mapping["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert int(metrics["trading language hit count"]) == 0
    assert int(metrics["forbidden action leakage count"]) == 0
    assert int(metrics["baseline admission changed count"]) == 0
    assert int(metrics["lookahead violation rows"]) == 0
    assert int(metrics["writeback allowed count"]) == 0
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".md", ".txt"}:
            assert not module.contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")), path


def test_inventory_defers_frontend_change_and_strategy_files_clean() -> None:
    inventory = pd.read_csv(OUTPUT_DIR / "dashboard_readonly_integration_inventory.csv")
    audit = pd.read_csv(OUTPUT_DIR / "dashboard_readonly_integration_quality_audit.csv")
    metrics = dict(zip(audit["metric"], audit["value"]))
    assert int(metrics["frontend files modified"]) == 0
    assert "defer_frontend_change" in set(inventory["recommended_action"])
    strategy_status = str(metrics["formal strategy file status"])
    assert strategy_status == "clean" or "src/stock_research/tech_bottleneck_v1.py" in strategy_status
