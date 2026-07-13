from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_tech_bottleneck_dashboard_readonly_frontend.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_dashboard_readonly_frontend_v1"
FRONTEND_DIR = PROJECT_ROOT / "dashboard/src/features/techBottleneckWatchlistReview"


def _load_module():
    spec = importlib.util.spec_from_file_location("dashboard_readonly_frontend", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_readonly_frontend_outputs_and_flags() -> None:
    audit = pd.read_csv(OUTPUT_DIR / "dashboard_readonly_frontend_quality_audit.csv")
    files = pd.read_csv(OUTPUT_DIR / "dashboard_readonly_frontend_files_changed.csv")
    metrics = dict(zip(audit["metric"], audit["value"]))

    assert int(metrics["read_only page added"]) == 1
    assert int(metrics["route added"]) == 0
    assert int(metrics["data loader added"]) == 1
    assert int(metrics["writeback allowed count"]) == 0
    assert int(metrics["baseline admission changed count"]) == 0
    assert int(metrics["lookahead violation rows"]) == 0
    assert set(files["read_only"].astype(str).str.lower()) == {"true"}
    assert set(files["writeback_allowed"].astype(str).str.lower()) == {"false"}
    assert set(files["used_for_signal"].astype(str).str.lower()) == {"false"}


def test_frontend_module_exists_and_is_readonly() -> None:
    module = _load_module()
    page = FRONTEND_DIR / "TechBottleneckWatchlistReviewPage.tsx"
    data = FRONTEND_DIR / "techBottleneckReadonlyData.ts"
    types = FRONTEND_DIR / "types.ts"

    assert page.exists()
    assert data.exists()
    assert types.exists()
    for path in [page, data, types]:
        text = path.read_text(encoding="utf-8")
        assert "writebackAllowed: false" in text or path.name == "types.ts"
        assert "usedForSignal: false" in text or path.name == "types.ts"
        assert not module.contains_actionable_trading_language(text), path


def test_output_reports_are_clean_and_record_preexisting_dirty_state() -> None:
    module = _load_module()
    audit = pd.read_csv(OUTPUT_DIR / "dashboard_readonly_frontend_quality_audit.csv")
    inventory = pd.read_csv(OUTPUT_DIR / "dashboard_readonly_frontend_inventory.csv")
    metrics = dict(zip(audit["metric"], audit["value"]))

    assert int(metrics["pre_existing_dirty_dashboard_files"]) >= 1
    assert int(metrics["forbidden action leakage count"]) == 0
    assert int(metrics["trading language hit count"]) == 0
    assert "yes" in set(inventory["pre_existing_dirty"].astype(str).str.lower())
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            assert not module.contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")), path


def test_formal_strategy_files_unchanged() -> None:
    audit = pd.read_csv(OUTPUT_DIR / "dashboard_readonly_frontend_quality_audit.csv")
    metrics = dict(zip(audit["metric"], audit["value"]))
    assert str(metrics["formal strategy file status"]) == "clean"
