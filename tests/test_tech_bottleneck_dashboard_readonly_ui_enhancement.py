from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_tech_bottleneck_dashboard_readonly_ui_enhancement.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_dashboard_readonly_ui_enhancement_v1"


def _load_module():
    spec = importlib.util.spec_from_file_location("dashboard_readonly_ui_enhancement", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_before_after_and_section_audit_cover_partial_sections() -> None:
    before_after = pd.read_csv(OUTPUT_DIR / "dashboard_ui_enhancement_before_after.csv")
    section_audit = pd.read_csv(OUTPUT_DIR / "dashboard_ui_enhancement_section_audit.csv")
    partial_sections = {
        "Watchlist Table",
        "Risk Review Queue",
        "Manual Review Template Status",
        "Consolidated Report Links",
    }
    assert partial_sections.issubset(set(before_after["section_name"]))
    assert partial_sections.issubset(set(section_audit["section_name"]))
    assert set(before_after["smoke_test_status_before"]) == {"partial"}
    assert set(before_after["status_after"]) == {"passed"}
    assert set(before_after["writeback_allowed"].astype(str).str.lower()) == {"false"}
    assert set(before_after["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert set(section_audit["status"]) == {"passed"}
    assert int(section_audit["blocking"].astype(str).str.lower().eq("true").sum()) == 0


def test_enhanced_sections_have_required_readonly_evidence() -> None:
    section_audit = pd.read_csv(OUTPUT_DIR / "dashboard_ui_enhancement_section_audit.csv")
    fields = dict(zip(section_audit["section_name"], section_audit["fields_present"]))
    forbidden = dict(zip(section_audit["section_name"], section_audit["interactions_forbidden"]))
    assert "symbol" in fields["Watchlist Table"]
    assert "consolidated_report_path" in fields["Watchlist Table"]
    assert "auto_exclude=false" in fields["Risk Review Queue"]
    assert "not_reviewed" in fields["Manual Review Template Status"]
    assert "writeback disabled" in fields["Manual Review Template Status"]
    assert "report links count=102" in fields["Consolidated Report Links"]
    assert "writeback" in forbidden["Watchlist Table"]
    assert "manual review save" in forbidden["Manual Review Template Status"]


def test_quality_audit_and_forbidden_scan_are_clean() -> None:
    module = _load_module()
    files_changed = pd.read_csv(OUTPUT_DIR / "dashboard_ui_enhancement_files_changed.csv")
    boundary = pd.read_csv(OUTPUT_DIR / "dashboard_ui_enhancement_boundary_audit.csv")
    audit = pd.read_csv(OUTPUT_DIR / "dashboard_ui_enhancement_quality_audit.csv")
    metrics = dict(zip(audit["metric"], audit["value"]))
    assert {"read-only", "no writeback", "formal strategy untouched"}.issubset(set(boundary["boundary_name"]))
    assert str(metrics["route still available"]) == "1"
    assert str(metrics["nav still available"]) == "1"
    assert int(metrics["partial sections before"]) == 4
    assert int(metrics["partial sections after"]) == 0
    assert int(metrics["passed sections after"]) >= 8
    assert int(metrics["writeback allowed count"]) == 0
    assert int(metrics["forbidden action leakage count"]) == 0
    assert int(metrics["trading language hit count"]) == 0
    assert int(metrics["baseline admission changed count"]) == 0
    assert int(metrics["lookahead violation rows"]) == 0
    assert str(metrics["formal strategy file status"]) == "clean"
    assert set(files_changed["writeback_allowed"].astype(str).str.lower()) == {"false"}
    assert set(files_changed["used_for_signal"].astype(str).str.lower()) == {"false"}
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            assert not module.contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")), path
