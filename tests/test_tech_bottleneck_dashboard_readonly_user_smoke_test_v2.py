from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_tech_bottleneck_dashboard_readonly_user_smoke_test_v2.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_dashboard_readonly_user_smoke_test_v2"


def _load_module():
    spec = importlib.util.spec_from_file_location("dashboard_readonly_user_smoke_test_v2", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_v2_output_files_and_summary_exist() -> None:
    expected_files = {
        "smoke_test_v2_summary.json",
        "smoke_test_v2_section_status.csv",
        "smoke_test_v2_validation_checks.csv",
        "smoke_test_v2_route_nav_checks.json",
        "smoke_test_v2_guardrail_checks.json",
        "smoke_test_v2_test_results.json",
        "tech_bottleneck_dashboard_readonly_user_smoke_test_v2_report.md",
    }
    assert expected_files.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    summary = json.loads((OUTPUT_DIR / "smoke_test_v2_summary.json").read_text(encoding="utf-8"))
    assert summary["acceptance_decision"] == "readonly_internal_review_ready"
    assert summary["core_sections_passed"] == 8
    assert summary["partial_sections"] == 0
    assert summary["failed_sections"] == 0
    assert summary["data_mismatch_count"] == 0


def test_v2_section_status_all_passed_and_enhanced_sections_passed() -> None:
    sections = pd.read_csv(OUTPUT_DIR / "smoke_test_v2_section_status.csv")
    enhanced = {
        "Watchlist Table",
        "Risk Review Queue",
        "Manual Review Template Status",
        "Consolidated Report Links",
    }
    assert len(sections) == 8
    assert set(sections["v2_status"]) == {"passed"}
    assert int(sections["v2_status"].eq("partial").sum()) == 0
    assert int(sections["v2_status"].eq("failed").sum()) == 0
    enhanced_rows = sections[sections["section"].isin(enhanced)]
    assert set(enhanced_rows["enhancement_applied"].astype(str).str.lower()) == {"true"}
    assert set(enhanced_rows["v2_status"]) == {"passed"}


def test_v2_guardrails_route_nav_and_report_are_clean() -> None:
    module = _load_module()
    route_nav = json.loads((OUTPUT_DIR / "smoke_test_v2_route_nav_checks.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "smoke_test_v2_guardrail_checks.json").read_text(encoding="utf-8"))
    checks = pd.read_csv(OUTPUT_DIR / "smoke_test_v2_validation_checks.csv")
    report = (OUTPUT_DIR / "tech_bottleneck_dashboard_readonly_user_smoke_test_v2_report.md").read_text(
        encoding="utf-8"
    )
    assert route_nav["route_available"] is True
    assert route_nav["nav_available"] is True
    assert route_nav["nav_label"] == "科技卡脖子观察池"
    assert route_nav["page_component_loadable"] is True
    assert guardrails["writeback_allowed_count"] == 0
    assert guardrails["forbidden_action_leakage_count"] == 0
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["formal_strategy_diff_status"] == "clean"
    assert set(checks["status"]) == {"passed"}
    assert not module.contains_actionable_trading_language(report)
