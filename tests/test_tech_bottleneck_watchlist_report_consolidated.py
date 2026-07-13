from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_report_consolidated_v1"


def _load_module():
    path = PROJECT_ROOT / "scripts/run_tech_bottleneck_watchlist_report_consolidated.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_watchlist_report_consolidated", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_generates_102_consolidated_reports_with_existing_paths() -> None:
    module = _load_module()
    index = pd.read_csv(OUTPUT_DIR / "watchlist_report_consolidated_index.csv")

    assert len(index) == 102
    assert index["consolidated_report_path"].notna().all()
    assert all(Path(path).exists() for path in index["consolidated_report_path"])
    assert not index["contains_trading_language"].astype(bool).any()
    assert not module.contains_actionable_trading_language(index.to_csv(index=False))


def test_consolidated_reports_include_required_research_sections() -> None:
    module = _load_module()
    index = pd.read_csv(OUTPUT_DIR / "watchlist_report_consolidated_index.csv")
    sample_text = Path(index["consolidated_report_path"].iloc[0]).read_text(encoding="utf-8")

    required_sections = [
        "## 4. Announcement Fulltext Evidence",
        "## 5. Fundamental Context",
        "## 6. Valuation Context",
        "## 7. Valuation Cross-source Validation",
        "## 8. Historical Watchlist Forward Return Context",
        "## 12. Non-trading Disclaimer",
    ]
    for section in required_sections:
        assert section in sample_text
    assert "仅用于事后复盘" in sample_text
    assert "不构成自动执行提示" in sample_text
    assert "BaoStock 是 primary valuation source" in sample_text
    assert "Baidu 不验证 PS/PS-TTM" in sample_text
    assert not module.contains_actionable_trading_language(sample_text)


def test_pe_negative_or_not_meaningful_is_not_interpreted_as_low() -> None:
    index = pd.read_csv(OUTPUT_DIR / "watchlist_report_consolidated_index.csv")
    summary = pd.read_csv(OUTPUT_DIR / "watchlist_report_consolidated_summary_by_asset.csv")
    subset = index[index["pe_meaningfulness"].isin(["pe_negative_or_loss_making", "pe_missing", "pe_not_meaningful"])]

    assert len(subset) == 9
    assert not subset["valuation_context_level"].eq("valuation_low_context").any()
    for path in subset["consolidated_report_path"].head(3):
        text = Path(path).read_text(encoding="utf-8")
        assert "负 PE 不能解释为低估" in text
    assert len(summary[summary["pe_meaningfulness"].ne("pe_meaningful")]) == 9


def test_baidu_material_discrepancy_does_not_override_baostock() -> None:
    summary = pd.read_csv(OUTPUT_DIR / "watchlist_report_consolidated_summary_by_asset.csv")
    material = summary[summary["baidu_validation_status"].eq("material_difference")]

    assert len(material) == 1
    assert material["recommended_review_action"].isin(["review_valuation_discrepancy", "manual_review_required"]).all()
    assert material["cross_source_discrepancy_flag"].str.contains("no_auto_override", na=False).all()


def test_dashboard_preview_has_no_execution_fields() -> None:
    module = _load_module()
    preview = pd.read_csv(OUTPUT_DIR / "watchlist_report_consolidated_dashboard_preview.csv")
    forbidden_columns = {
        "target_price",
        "position_size",
        "entry_signal",
        "exit_signal",
        "buy",
        "sell",
        "hold",
    }

    assert len(preview) == 102
    assert forbidden_columns.isdisjoint(set(preview.columns))
    assert not module.contains_actionable_trading_language(preview.to_csv(index=False))


def test_quality_audit_and_formal_strategy_status() -> None:
    audit = pd.read_csv(OUTPUT_DIR / "watchlist_report_consolidated_quality_audit.csv")
    lookup = dict(zip(audit["metric"], audit["value"]))
    report = (OUTPUT_DIR / "watchlist_report_consolidated_v1.md").read_text(encoding="utf-8")

    assert int(lookup["reports with trading language"]) == 0
    assert int(lookup["lookahead violation rows"]) == 0
    assert int(lookup["patch failures"]) == 0
    assert "forward return 只用于事后复盘" in report
    assert "无法仅靠 `git diff` 完整证明" in report
