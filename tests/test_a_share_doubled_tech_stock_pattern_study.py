from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_a_share_doubled_tech_stock_pattern_study.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/a_share_doubled_tech_stock_pattern_study_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
REQUIRED_CASES = {
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


def _run_generator() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_pattern_study_generates_required_outputs_for_596_doubled_tech_stocks() -> None:
    _run_generator()
    expected = {
        "pattern_study_summary.json",
        "doubled_tech_stock_pattern_master.csv",
        "doubled_tech_theme_summary.csv",
        "doubling_path_features.csv",
        "pre_breakout_technical_features.csv",
        "fundamental_features.csv",
        "catalyst_event_timeline.csv",
        "sentiment_and_theme_features.csv",
        "pattern_archetype_classification.csv",
        "representative_case_studies.md",
        "representative_case_studies.pdf",
        "pattern_methodology_notes.md",
        "early_signal_candidate_features.csv",
        "false_positive_and_risk_patterns.csv",
        "a_share_doubled_tech_stock_pattern_study_v1_report.md",
    }
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "pattern_study_summary.json").read_text(encoding="utf-8"))
    master = pd.read_csv(OUTPUT_DIR / "doubled_tech_stock_pattern_master.csv", dtype={"stock_code": str})
    path_features = pd.read_csv(OUTPUT_DIR / "doubling_path_features.csv", dtype={"stock_code": str})
    technical = pd.read_csv(OUTPUT_DIR / "pre_breakout_technical_features.csv", dtype={"stock_code": str})
    archetypes = pd.read_csv(OUTPUT_DIR / "pattern_archetype_classification.csv", dtype={"stock_code": str})

    assert summary["task_name"] == "a_share_doubled_tech_stock_pattern_study_v1"
    assert summary["input_doubled_tech_count"] == 596
    assert summary["allowed_for_signal_count"] == 0
    assert summary["allowed_for_admission_count"] == 0
    assert len(master) == 596
    assert len(path_features) == 596
    assert len(technical) == 596
    assert len(archetypes) == 596
    assert master["strict_theme"].notna().all()
    assert master["pattern_archetype"].notna().all()
    assert path_features["date_return_100pct"].notna().all()
    assert path_features["trading_days_to_100pct"].notna().all()
    assert path_features["return_since_20250101"].ge(1.0).all()
    assert set(REQUIRED_CASES).issubset(set(master["stock_name"]))


def test_pattern_study_reports_are_research_only_and_cover_cases() -> None:
    _run_generator()
    case_text = (OUTPUT_DIR / "representative_case_studies.md").read_text(encoding="utf-8")
    report = (OUTPUT_DIR / "a_share_doubled_tech_stock_pattern_study_v1_report.md").read_text(encoding="utf-8")
    theme_summary = pd.read_csv(OUTPUT_DIR / "doubled_tech_theme_summary.csv")
    catalyst = pd.read_csv(OUTPUT_DIR / "catalyst_event_timeline.csv", dtype={"stock_code": str})
    sentiment = pd.read_csv(OUTPUT_DIR / "sentiment_and_theme_features.csv", dtype={"stock_code": str})

    assert not theme_summary.empty
    assert {"strict_theme", "stock_count", "median_return", "representative_stocks"}.issubset(theme_summary.columns)
    assert {"stock_code", "stock_name", "event_date", "event_type", "source_title", "source_reference"}.issubset(catalyst.columns)
    assert {"stock_code", "stock_name", "sentiment_event_type", "news_count_30d_before_breakout", "research_report_count_60d_before_breakout"}.issubset(
        sentiment.columns
    )
    for stock_name in REQUIRED_CASES:
        assert stock_name in case_text
    for text in [case_text, report]:
        assert "买入" not in text
        assert "卖出" not in text
        assert "目标价" not in text
        assert "recommended stocks to buy" not in text.lower()
    assert "Which hard-tech themes produced the most doublers" in report
    assert "What early signals could have identified some winners" in report

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
