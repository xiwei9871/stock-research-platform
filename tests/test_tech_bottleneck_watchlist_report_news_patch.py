from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_report_news_patch_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

FORBIDDEN_PATTERNS = [
    re.compile(
        r"\b(?:buy|sell|add|reduce|hold|entry|exit|position|target price|increase position|"
        r"reduce position|target_price|position_size|entry_signal|exit_signal)\b",
        re.I,
    ),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|退出|止盈|止损|调仓|交易信号"),
    re.compile(r"保存|提交|写回"),
]


def _has_forbidden_language(text: str) -> bool:
    return any(pattern.search(text) for pattern in FORBIDDEN_PATTERNS)


def test_news_patch_outputs_exist_and_summary_counts_are_expected() -> None:
    expected = {
        "watchlist_report_news_patch_summary.json",
        "watchlist_report_news_patch_manifest.csv",
        "watchlist_report_news_sections.json",
        "watchlist_report_news_sections.csv",
        "watchlist_report_news_missing.csv",
        "watchlist_report_news_partial.csv",
        "watchlist_report_news_pit_audit.csv",
        "watchlist_report_news_event_type_coverage.csv",
        "watchlist_report_news_source_quality.csv",
        "watchlist_report_news_guardrails.json",
        "tech_bottleneck_watchlist_report_news_patch_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "watchlist_report_news_patch_summary.json").read_text(encoding="utf-8"))
    assert summary["watchlist_count"] == 102
    assert summary["reports_total"] == 102
    assert summary["reports_news_supported"] == 30
    assert summary["reports_news_partial"] == 1
    assert summary["reports_news_missing"] == 71
    assert summary["pit_available_event_count"] == 189
    assert summary["post_admission_event_count"] == 11
    assert summary["date_missing_event_count"] == 71
    assert summary["lookahead_violation_rows"] == 0
    assert summary["writeback_allowed_count"] == 0
    assert summary["manual_review_writeback_enabled_count"] == 0
    assert summary["trading_language_hit_count"] == 0
    assert summary["execution_language_hit_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["baseline_admission_changed_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["acceptance_decision"] == "watchlist_report_news_patch_ready_with_degraded_coverage"


def test_news_patch_sections_manifest_missing_and_partial_are_research_only() -> None:
    manifest = pd.read_csv(OUTPUT_DIR / "watchlist_report_news_patch_manifest.csv")
    sections = pd.read_csv(OUTPUT_DIR / "watchlist_report_news_sections.csv")
    missing = pd.read_csv(OUTPUT_DIR / "watchlist_report_news_missing.csv")
    partial = pd.read_csv(OUTPUT_DIR / "watchlist_report_news_partial.csv")

    assert len(manifest) == 102
    assert len(sections) == 102
    assert len(missing) == 71
    assert len(partial) == 1
    assert manifest["patch_status"].eq("news_supported_section").sum() == 30
    assert manifest["patch_status"].eq("news_partial_section").sum() == 1
    assert manifest["patch_status"].eq("news_data_gap_section").sum() == 71
    assert set(sections["research_only"].astype(str).str.lower()) == {"true"}
    assert set(sections["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert set(sections["used_for_admission"].astype(str).str.lower()) == {"false"}
    assert sections["section_markdown"].str.contains("News and Event Review Context", regex=False).all()
    assert missing["data_gap_note"].str.len().min() > 0
    assert missing["manual_review_impact"].str.len().min() > 0
    assert partial["partial_note"].str.len().min() > 0

    event_records = json.loads((OUTPUT_DIR / "watchlist_report_news_sections.json").read_text(encoding="utf-8"))
    all_events = [event for row in event_records for event in row["events"]]
    pit_events = [event for event in all_events if event["pit_status"] == "pit_available"]
    post_events = [event for event in all_events if event["pit_status"] == "post_admission_context"]
    date_missing = [event for event in all_events if event["pit_status"] == "date_missing"]
    assert len(pit_events) == 189
    assert len(post_events) == 11
    assert len(date_missing) == 71
    assert all(
        pd.to_datetime(event["publish_date"], errors="coerce")
        <= pd.to_datetime(event["first_admission_date"], errors="coerce")
        for event in pit_events
    )
    assert all(
        pd.to_datetime(event["publish_date"], errors="coerce")
        > pd.to_datetime(event["first_admission_date"], errors="coerce")
        for event in post_events
    )
    assert all(event["source_quality"] == "degraded" for event in date_missing)


def test_news_patch_guardrails_report_scan_and_strategy_diff_are_clean() -> None:
    guardrails = json.loads((OUTPUT_DIR / "watchlist_report_news_guardrails.json").read_text(encoding="utf-8"))
    pit_audit = pd.read_csv(OUTPUT_DIR / "watchlist_report_news_pit_audit.csv")
    assert guardrails["writeback_allowed_count"] == 0
    assert guardrails["manual_review_writeback_enabled_count"] == 0
    assert guardrails["forbidden_action_leakage_count"] == 0
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert int(pit_audit.loc[pit_audit["metric"].eq("lookahead_violation_rows"), "value"].iloc[0]) == 0

    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".md", ".txt"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert not _has_forbidden_language(text), path

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
