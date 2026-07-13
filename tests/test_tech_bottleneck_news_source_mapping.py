from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_news_source_mapping_v1"
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


def test_news_source_mapping_outputs_and_guardrails_exist() -> None:
    expected = {
        "news_source_mapping_summary.json",
        "news_source_mapping_events.csv",
        "news_source_mapping_events.json",
        "news_source_mapping_company_summary.csv",
        "news_source_mapping_source_quality.csv",
        "news_source_mapping_pit_audit.csv",
        "news_source_mapping_missing.csv",
        "news_source_mapping_keywords.csv",
        "news_source_mapping_guardrails.json",
        "tech_bottleneck_news_source_mapping_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    summary = json.loads((OUTPUT_DIR / "news_source_mapping_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "news_source_mapping_guardrails.json").read_text(encoding="utf-8"))
    assert summary["watchlist_count"] == 102
    assert summary["news_supported_count"] >= 0
    assert summary["news_missing_count"] >= 0
    assert summary["lookahead_violation_rows"] == 0
    assert summary["acceptance_decision"] in {
        "news_source_mapping_ready",
        "conditionally_ready_with_degraded_news_coverage",
        "blocked_due_to_source_unavailable",
    }
    assert guardrails["watchlist_count"] == 102
    assert guardrails["lookahead_violation_rows"] == 0
    assert guardrails["writeback_allowed_count"] == 0
    assert guardrails["manual_review_writeback_enabled_count"] == 0
    assert guardrails["forbidden_action_leakage_count"] == 0
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["research_only"] is True
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0


def test_news_events_company_summary_and_pit_rules_are_valid() -> None:
    events = pd.read_csv(OUTPUT_DIR / "news_source_mapping_events.csv")
    company = pd.read_csv(OUTPUT_DIR / "news_source_mapping_company_summary.csv")
    pit = pd.read_csv(OUTPUT_DIR / "news_source_mapping_pit_audit.csv")
    missing = pd.read_csv(OUTPUT_DIR / "news_source_mapping_missing.csv")
    assert len(company) == 102
    assert {"pit_available", "post_admission_context", "date_missing"}.intersection(set(events["pit_status"]))
    assert set(events["research_only"].astype(str).str.lower()) == {"true"}
    assert set(events["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert set(events["used_for_admission"].astype(str).str.lower()) == {"false"}
    assert set(company["research_only"].astype(str).str.lower()) == {"true"}
    assert set(company["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert set(company["used_for_admission"].astype(str).str.lower()) == {"false"}
    assert len(missing) == int(company["news_support"].eq("missing").sum())
    assert missing["missing_reason"].str.len().min() > 0
    assert missing["manual_review_impact"].str.len().min() > 0

    pit_available = events[events["pit_status"].eq("pit_available")]
    assert (
        pd.to_datetime(pit_available["publish_date"], errors="coerce")
        <= pd.to_datetime(pit_available["first_admission_date"], errors="coerce")
    ).all()
    post = events[events["pit_status"].eq("post_admission_context")]
    if not post.empty:
        assert (
            pd.to_datetime(post["publish_date"], errors="coerce")
            > pd.to_datetime(post["first_admission_date"], errors="coerce")
        ).all()
    date_missing = events[events["pit_status"].eq("date_missing")]
    if not date_missing.empty:
        assert not date_missing["source_quality"].isin(["high", "medium"]).any()
        assert not date_missing["pit_status"].eq("pit_available").any()
    assert int(pit.loc[pit["metric"].eq("lookahead_violation_rows"), "value"].iloc[0]) == 0


def test_news_mapping_outputs_have_no_execution_language_and_strategy_diff_is_clean() -> None:
    for path in OUTPUT_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".md", ".txt"}:
            assert not _has_forbidden_language(path.read_text(encoding="utf-8", errors="ignore")), path

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
