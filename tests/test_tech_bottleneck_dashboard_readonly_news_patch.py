from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_dashboard_readonly_news_patch_v1"
FRONTEND_DIR = PROJECT_ROOT / "dashboard/src/features/techBottleneckWatchlistReview"
ROUTE_TEST = PROJECT_ROOT / "dashboard/tests/tech-bottleneck-route.test.tsx"
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


def test_dashboard_news_patch_outputs_and_contract_are_expected() -> None:
    expected = {
        "dashboard_news_patch_summary.json",
        "dashboard_news_rows.csv",
        "dashboard_news_event_cards.json",
        "dashboard_news_missing_rows.csv",
        "dashboard_news_partial_rows.csv",
        "dashboard_news_date_missing_rows.csv",
        "dashboard_news_post_admission_rows.csv",
        "dashboard_news_event_type_coverage.csv",
        "dashboard_news_filters.json",
        "dashboard_news_guardrails.json",
        "dashboard_news_frontend_contract.json",
        "tech_bottleneck_dashboard_readonly_news_patch_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "dashboard_news_patch_summary.json").read_text(encoding="utf-8"))
    contract = json.loads((OUTPUT_DIR / "dashboard_news_frontend_contract.json").read_text(encoding="utf-8"))
    assert summary["watchlist_count"] == 102
    assert summary["news_supported_count"] == 30
    assert summary["news_partial_count"] == 1
    assert summary["news_missing_count"] == 71
    assert summary["pit_available_event_count"] == 189
    assert summary["post_admission_event_count"] == 11
    assert summary["date_missing_event_count"] == 71
    assert summary["lookahead_violation_rows"] == 0
    assert summary["section_status"] == "passed"
    assert contract["section_status"] == "passed"
    assert contract["used_for_signal"] is False
    assert contract["used_for_admission"] is False
    assert contract["research_only"] is True
    assert contract["writeback_enabled"] is False
    assert contract["manual_review_writeback_enabled"] is False


def test_dashboard_news_rows_event_cards_and_degraded_context_are_valid() -> None:
    rows = pd.read_csv(OUTPUT_DIR / "dashboard_news_rows.csv")
    missing = pd.read_csv(OUTPUT_DIR / "dashboard_news_missing_rows.csv")
    partial = pd.read_csv(OUTPUT_DIR / "dashboard_news_partial_rows.csv")
    date_missing = pd.read_csv(OUTPUT_DIR / "dashboard_news_date_missing_rows.csv")
    post = pd.read_csv(OUTPUT_DIR / "dashboard_news_post_admission_rows.csv")
    cards = json.loads((OUTPUT_DIR / "dashboard_news_event_cards.json").read_text(encoding="utf-8"))

    assert len(rows) == 102
    assert len(missing) == 71
    assert len(partial) == 1
    assert len(date_missing) == 71
    assert len(post) == 11
    assert len(cards) == 271
    assert rows["news_support"].eq("supported").sum() == 30
    assert rows["news_support"].eq("partial").sum() == 1
    assert rows["news_support"].eq("missing").sum() == 71
    assert missing["data_gap_note"].str.len().min() > 0
    assert partial["partial_coverage_note"].str.len().min() > 0
    assert date_missing["source_quality"].eq("degraded").all()
    assert post["pit_status"].eq("post_admission_context").all()
    assert set(rows["research_only"].astype(str).str.lower()) == {"true"}
    assert set(rows["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert set(rows["used_for_admission"].astype(str).str.lower()) == {"false"}


def test_dashboard_news_guardrails_frontend_patch_and_strategy_diff_are_clean() -> None:
    guardrails = json.loads((OUTPUT_DIR / "dashboard_news_guardrails.json").read_text(encoding="utf-8"))
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
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["readonly_ui_only"] is True

    page = (FRONTEND_DIR / "TechBottleneckWatchlistReviewPage.tsx").read_text(encoding="utf-8")
    data = (FRONTEND_DIR / "techBottleneckReadonlyData.ts").read_text(encoding="utf-8")
    types = (FRONTEND_DIR / "types.ts").read_text(encoding="utf-8")
    route_test = ROUTE_TEST.read_text(encoding="utf-8")
    assert "News and Event Review Context" in page
    assert "techBottleneckNewsSummary" in data
    assert "TechBottleneckNewsSummary" in types
    assert "News Support: 30 / 102" in route_test
    assert "Partial News Coverage: 1" in route_test
    assert "Missing News: 71" in route_test
    for text in [page, data, types, route_test]:
        assert not _has_forbidden_language(text)

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
