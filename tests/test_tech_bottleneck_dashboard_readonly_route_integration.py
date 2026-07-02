from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_tech_bottleneck_dashboard_readonly_route_integration.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_dashboard_readonly_route_integration_v1"


def _load_module():
    spec = importlib.util.spec_from_file_location("dashboard_readonly_route_integration", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_route_and_nav_audits_are_readonly() -> None:
    route = pd.read_csv(OUTPUT_DIR / "dashboard_route_integration_route_audit.csv")
    nav = pd.read_csv(OUTPUT_DIR / "dashboard_route_integration_nav_audit.csv")
    assert set(route["route_path"]) == {"/tech-bottleneck/watchlist-review"}
    assert set(route["page_component"]) == {"TechBottleneckWatchlistReviewPage"}
    assert set(route["route_added"].astype(str).str.lower()) == {"true"}
    assert set(nav["nav_added"].astype(str).str.lower()) == {"true"}
    assert set(route["read_only"].astype(str).str.lower()) == {"true"}
    assert set(nav["read_only"].astype(str).str.lower()) == {"true"}
    assert set(route["writeback_allowed"].astype(str).str.lower()) == {"false"}
    assert set(nav["writeback_allowed"].astype(str).str.lower()) == {"false"}
    assert set(route["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert set(nav["used_for_signal"].astype(str).str.lower()) == {"false"}


def test_files_changed_and_quality_audit_are_clean() -> None:
    module = _load_module()
    files = pd.read_csv(OUTPUT_DIR / "dashboard_route_integration_files_changed.csv")
    audit = pd.read_csv(OUTPUT_DIR / "dashboard_route_integration_quality_audit.csv")
    metrics = dict(zip(audit["metric"], audit["value"]))
    assert "dashboard/src/components/AppShell.tsx" in set(files["file_path"])
    assert int(metrics["route added"]) == 1
    assert int(metrics["nav added"]) == 1
    assert int(metrics["writeback allowed count"]) == 0
    assert int(metrics["forbidden action leakage count"]) == 0
    assert int(metrics["trading language hit count"]) == 0
    assert int(metrics["baseline admission changed count"]) == 0
    assert int(metrics["lookahead violation rows"]) == 0
    assert str(metrics["formal strategy file status"]) == "clean"
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            assert not module.contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")), path


def test_inventory_records_preexisting_dashboard_dirty_paths() -> None:
    inventory = pd.read_csv(OUTPUT_DIR / "dashboard_route_integration_inventory.csv")
    audit = pd.read_csv(OUTPUT_DIR / "dashboard_route_integration_quality_audit.csv")
    metrics = dict(zip(audit["metric"], audit["value"]))
    assert int(metrics["pre_existing_dirty_dashboard_files"]) >= 1
    assert "dashboard/src/components/AppShell.tsx" in set(inventory["path"])
    app_shell = inventory[inventory["path"].eq("dashboard/src/components/AppShell.tsx")].iloc[0]
    assert str(app_shell["modified_by_this_task"]).lower() == "true"
    assert str(app_shell["pre_existing_dirty"]).lower() == "no"
