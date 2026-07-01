from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_report_baostock_valuation_patch_v1"


def _load_module():
    path = PROJECT_ROOT / "scripts/run_tech_bottleneck_watchlist_report_baostock_valuation_patch.py"
    spec = importlib.util.spec_from_file_location("run_tech_bottleneck_watchlist_report_baostock_valuation_patch", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_generates_102_baostock_valuation_patched_reports() -> None:
    module = _load_module()
    index_path = OUTPUT_DIR / "watchlist_report_baostock_valuation_patch_index.csv"
    index = pd.read_csv(index_path)

    assert len(index) == 102
    assert set(index["patch_status"]) == {"patched_with_baostock_valuation"}
    assert index["baostock_support"].astype(bool).all()
    assert not index["contains_trading_language"].astype(bool).any()
    assert all(Path(path).exists() for path in index["baostock_valuation_patched_report_path"])
    assert not module.contains_actionable_trading_language(index.to_csv(index=False))


def test_reports_state_pe_pb_ps_are_research_context_only() -> None:
    module = _load_module()
    index = pd.read_csv(OUTPUT_DIR / "watchlist_report_baostock_valuation_patch_index.csv")
    sample_paths = list(index["baostock_valuation_patched_report_path"].head(5))

    for path in sample_paths:
        text = Path(path).read_text(encoding="utf-8")
        assert "BaoStock PE/PB/PS Valuation Patch" in text
        assert "PE/PB/PS 分位只作为估值上下文" in text
        assert "不构成自动执行提示" in text
        assert not module.contains_actionable_trading_language(text)


def test_pe_not_meaningful_is_explicit_and_not_low_context() -> None:
    index = pd.read_csv(OUTPUT_DIR / "watchlist_report_baostock_valuation_patch_index.csv")
    summary = pd.read_csv(OUTPUT_DIR / "watchlist_baostock_valuation_patch_summary_by_asset.csv")
    not_meaningful = index[index["pe_meaningfulness"].isin(["pe_negative_or_loss_making", "pe_missing", "pe_not_meaningful"])]

    assert len(not_meaningful) == 9
    assert not not_meaningful["valuation_context_level"].eq("valuation_low_context").any()
    for path in not_meaningful["baostock_valuation_patched_report_path"].head(3):
        text = Path(path).read_text(encoding="utf-8")
        assert "不能将负 PE 或缺失 PE 解释为低估" in text
    assert len(summary[summary["pe_meaningfulness"].ne("pe_meaningful")]) == 9


def test_valuation_context_levels_are_not_execution_conclusions() -> None:
    module = _load_module()
    index = pd.read_csv(OUTPUT_DIR / "watchlist_report_baostock_valuation_patch_index.csv")
    low_or_high = index[index["valuation_context_level"].isin(["valuation_low_context", "valuation_high_context"])]

    assert not low_or_high.empty
    for path in low_or_high["baostock_valuation_patched_report_path"].head(10):
        text = Path(path).read_text(encoding="utf-8")
        assert "valuation_low_context 不是自动执行依据" in text
        assert "valuation_high_context 不是自动执行依据" in text
        assert not module.contains_actionable_trading_language(text)


def test_quality_audit_and_formal_strategy_status() -> None:
    audit = pd.read_csv(OUTPUT_DIR / "watchlist_baostock_valuation_patch_quality_audit.csv")
    lookup = dict(zip(audit["metric"], audit["value"]))
    report = (OUTPUT_DIR / "watchlist_report_baostock_valuation_patch_v1.md").read_text(encoding="utf-8")

    assert int(lookup["reports with trading language"]) == 0
    assert int(lookup["lookahead violation rows"]) == 0
    assert int(lookup["patch failures"]) == 0
    assert "无法仅靠 `git diff` 完整证明" in report
