from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_tech_bottleneck_dashboard_readonly_user_acceptance.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_dashboard_readonly_user_acceptance_v1"


def _load_module():
    spec = importlib.util.spec_from_file_location("dashboard_readonly_user_acceptance", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_acceptance_checklist_generated_and_clean() -> None:
    checklist = pd.read_csv(OUTPUT_DIR / "dashboard_user_acceptance_checklist.csv")
    groups = set(checklist["check_group"])
    assert {
        "read_only_boundary",
        "data_coverage",
        "review_priority_display",
        "risk_queue_display",
        "manual_review_template_display",
        "report_links",
        "warnings",
        "forbidden_actions",
        "route_readiness",
        "build_and_tests",
    }.issubset(groups)
    assert len(checklist) >= 14
    assert set(checklist["status"]) <= {"passed", "warning", "failed"}
    assert not checklist[checklist["blocking_for_readonly_use"].astype(str).str.lower().eq("true")].shape[0]


def test_data_consistency_counts_match() -> None:
    consistency = pd.read_csv(OUTPUT_DIR / "dashboard_user_acceptance_data_consistency.csv")
    required_metrics = {
        "watchlist count",
        "v2 candidates count",
        "dashboard table count",
        "review priority rows",
        "risk queue rows",
        "manual review template rows",
        "report links count",
        "writeback allowed count",
        "forbidden action leakage count",
        "trading language hit count",
        "baseline admission changed count",
        "lookahead violation rows",
    }
    assert required_metrics.issubset(set(consistency["metric"]))
    assert set(consistency["match"].astype(str).str.lower()) == {"true"}


def test_ui_review_risk_and_route_readiness() -> None:
    ui = pd.read_csv(OUTPUT_DIR / "dashboard_user_acceptance_ui_review.csv")
    risk = pd.read_csv(OUTPUT_DIR / "dashboard_user_acceptance_risk_review.csv")
    route = pd.read_csv(OUTPUT_DIR / "dashboard_user_acceptance_route_readiness.csv")
    assert {
        "Snapshot Summary",
        "Global Warning Banner",
        "V2 Review Priority Summary",
        "Watchlist Table",
        "Risk Review Queue",
        "Manual Review Template Status",
        "Consolidated Report Links",
        "Methodology Panel",
    }.issubset(set(ui["ui_section"]))
    assert {"route_not_integrated", "static_data_freshness", "no_writeback_yet"}.issubset(set(risk["risk_id"]))
    assert set(route["route_added"].astype(str).str.lower()) == {"false"}
    assert set(route["writeback_allowed"].astype(str).str.lower()) == {"false"}
    assert set(route["read_only"].astype(str).str.lower()) == {"true"}
    assert set(route["route_readiness_status"]) == {"deferred_due_to_pre_existing_dirty_dashboard"}


def test_quality_audit_and_reports_are_clean() -> None:
    module = _load_module()
    audit = pd.read_csv(OUTPUT_DIR / "dashboard_user_acceptance_quality_audit.csv")
    metrics = dict(zip(audit["metric"], audit["value"]))
    assert int(metrics["writeback allowed count"]) == 0
    assert int(metrics["forbidden action leakage count"]) == 0
    assert int(metrics["trading language hit count"]) == 0
    assert int(metrics["baseline admission changed count"]) == 0
    assert int(metrics["lookahead violation rows"]) == 0
    assert int(metrics["frontend files modified in this task"]) == 0
    assert str(metrics["formal strategy file status"]) == "clean"
    assert str(metrics["acceptance decision"]) == "conditionally_ready_requires_route"
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            assert not module.contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")), path
