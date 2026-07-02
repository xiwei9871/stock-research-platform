from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_tech_bottleneck_dashboard_readonly_user_smoke_test.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_dashboard_readonly_user_smoke_test_v1"


def _load_module():
    spec = importlib.util.spec_from_file_location("dashboard_readonly_user_smoke_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_smoke_checklist_route_and_nav() -> None:
    checklist = pd.read_csv(OUTPUT_DIR / "dashboard_user_smoke_test_checklist.csv")
    route_nav = pd.read_csv(OUTPUT_DIR / "dashboard_user_smoke_test_route_nav.csv")
    assert len(checklist) >= 13
    assert {"route_access", "navigation_entry", "page_render", "read_only_boundary", "build_and_tests"}.issubset(
        set(checklist["check_group"])
    )
    assert int(checklist["blocking_for_internal_use"].astype(str).str.lower().eq("true").sum()) == 0
    assert set(route_nav["route_path"]) == {"/tech-bottleneck/watchlist-review"}
    assert set(route_nav["nav_present"].astype(str).str.lower()) == {"true"}
    assert set(route_nav["component_importable"].astype(str).str.lower()) == {"true"}
    assert set(route_nav["read_only"].astype(str).str.lower()) == {"true"}
    assert set(route_nav["writeback_allowed"].astype(str).str.lower()) == {"false"}
    assert set(route_nav["used_for_signal"].astype(str).str.lower()) == {"false"}


def test_page_sections_and_data_counts() -> None:
    sections = pd.read_csv(OUTPUT_DIR / "dashboard_user_smoke_test_page_sections.csv")
    counts = pd.read_csv(OUTPUT_DIR / "dashboard_user_smoke_test_data_counts.csv")
    assert {
        "Snapshot Summary",
        "Global Warning Banner",
        "V2 Review Priority Summary",
        "Watchlist Table",
        "Risk Review Queue",
        "Manual Review Template Status",
        "Consolidated Report Links",
        "Methodology / Non-trading Disclaimer",
    }.issubset(set(sections["section_name"]))
    assert set(sections["status"]) <= {"passed", "partial", "failed"}
    assert int(sections["blocking"].astype(str).str.lower().eq("true").sum()) == 0
    assert set(counts["match"].astype(str).str.lower()) == {"true"}
    assert {"v2 candidates count", "review priority rows", "risk queue rows", "report links count"}.issubset(
        set(counts["metric"])
    )


def test_boundary_and_quality_audits_are_clean() -> None:
    module = _load_module()
    boundary = pd.read_csv(OUTPUT_DIR / "dashboard_user_smoke_test_boundary_audit.csv")
    audit = pd.read_csv(OUTPUT_DIR / "dashboard_user_smoke_test_quality_audit.csv")
    metrics = dict(zip(audit["metric"], audit["value"]))
    assert {"read-only boundary", "no writeback", "formal strategy untouched"}.issubset(set(boundary["boundary_name"]))
    assert int(metrics["writeback allowed count"]) == 0
    assert int(metrics["forbidden action leakage count"]) == 0
    assert int(metrics["trading language hit count"]) == 0
    assert int(metrics["baseline admission changed count"]) == 0
    assert int(metrics["lookahead violation rows"]) == 0
    assert str(metrics["formal strategy file status"]) == "clean"
    assert str(metrics["acceptance decision"]) in {
        "conditionally_ready_with_minor_ui_gaps",
        "ready_for_internal_readonly_review",
    }
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            assert not module.contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")), path
