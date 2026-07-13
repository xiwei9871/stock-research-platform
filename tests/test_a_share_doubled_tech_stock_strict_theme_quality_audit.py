from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_a_share_doubled_tech_stock_strict_theme_quality_audit.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/a_share_doubled_tech_stock_strict_theme_quality_audit_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
SPECIAL_CASES = {
    "胜宏科技",
    "中际旭创",
    "新易盛",
    "天孚通信",
    "寒武纪",
    "源杰科技",
    "北方华创",
    "中微公司",
    "华海清科",
    "安集科技",
    "长川科技",
    "中科飞测",
}
STRICT_CATEGORIES = {
    "confirmed_hard_tech_doubler",
    "likely_hard_tech_doubler",
    "broad_tech_application_doubler",
    "theme_or_sentiment_driven_doubler",
    "concept_only_or_weak_tech_doubler",
    "non_tech_false_positive",
}


def _run_generator() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_strict_theme_quality_audit_generates_required_outputs() -> None:
    _run_generator()

    expected = {
        "strict_theme_quality_audit_summary.json",
        "strict_theme_quality_master.csv",
        "confirmed_hard_tech_doublers.csv",
        "likely_hard_tech_doublers.csv",
        "broad_tech_application_doublers.csv",
        "theme_or_sentiment_driven_doublers.csv",
        "concept_only_or_weak_tech_doublers.csv",
        "non_tech_false_positives.csv",
        "confirmed_hard_tech_theme_summary.csv",
        "broad_tech_application_theme_summary.csv",
        "sentiment_driven_theme_summary.csv",
        "strict_pattern_statistics_by_category.csv",
        "special_case_strict_audit.csv",
        "strict_theme_quality_audit_report.md",
    }
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "strict_theme_quality_audit_summary.json").read_text(encoding="utf-8"))
    master = pd.read_csv(OUTPUT_DIR / "strict_theme_quality_master.csv", dtype={"stock_code": str})
    confirmed = pd.read_csv(OUTPUT_DIR / "confirmed_hard_tech_doublers.csv", dtype={"stock_code": str})
    broad = pd.read_csv(OUTPUT_DIR / "broad_tech_application_doublers.csv", dtype={"stock_code": str})
    special = pd.read_csv(OUTPUT_DIR / "special_case_strict_audit.csv", dtype={"stock_code": str})

    assert summary["task_name"] == "a_share_doubled_tech_stock_strict_theme_quality_audit_v1"
    assert summary["input_count"] == 596
    assert summary["master_rows"] == 596
    assert summary["allowed_for_signal_count"] == 0
    assert summary["allowed_for_admission_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert len(master) == 596
    assert master["strict_quality_category"].notna().all()
    assert set(master["strict_quality_category"]).issubset(STRICT_CATEGORIES)
    assert master["rationale"].fillna("").str.len().gt(0).all()
    assert confirmed["return_since_20250101"].ge(1.0).all()
    assert not confirmed["strict_quality_category"].eq("broad_tech_application_doubler").any()
    assert broad["strict_quality_category"].eq("broad_tech_application_doubler").all()
    assert set(SPECIAL_CASES).issubset(set(special["stock_name"]))


def test_strict_theme_quality_audit_is_research_only_and_no_strategy_diff() -> None:
    _run_generator()

    report = (OUTPUT_DIR / "strict_theme_quality_audit_report.md").read_text(encoding="utf-8")
    master = pd.read_csv(OUTPUT_DIR / "strict_theme_quality_master.csv", dtype={"stock_code": str})
    stats = pd.read_csv(OUTPUT_DIR / "strict_pattern_statistics_by_category.csv")

    assert not stats.empty
    assert {"strict_quality_category", "stock_count", "median_return", "top_strict_themes"}.issubset(stats.columns)
    assert master["used_for_signal"].eq(False).all()
    assert master["used_for_admission"].eq(False).all()
    assert "How many of the 596 are confirmed/likely hard-tech doublers" in report
    assert "Which strict hard-tech themes produced the strongest doublers" in report
    assert "No production signal/admission change was made" in report
    for forbidden in ["买入", "卖出", "目标价", "target price", "buy recommendation", "sell recommendation"]:
        assert forbidden.lower() not in report.lower()

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
