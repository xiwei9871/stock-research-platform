from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_dashboard_readonly_financial_statement_patch_v1"
FRONTEND_DIR = PROJECT_ROOT / "dashboard/src/features/techBottleneckWatchlistReview"
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


def test_dashboard_financial_statement_outputs_and_contract_are_valid() -> None:
    expected = {
        "dashboard_financial_statement_patch_summary.json",
        "dashboard_financial_statement_rows.csv",
        "dashboard_financial_statement_cards.json",
        "dashboard_financial_statement_missing_rows.csv",
        "dashboard_financial_statement_field_coverage.csv",
        "dashboard_financial_statement_filters.json",
        "dashboard_financial_statement_guardrails.json",
        "dashboard_financial_statement_frontend_contract.json",
        "tech_bottleneck_dashboard_readonly_financial_statement_patch_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "dashboard_financial_statement_patch_summary.json").read_text(encoding="utf-8"))
    contract = json.loads((OUTPUT_DIR / "dashboard_financial_statement_frontend_contract.json").read_text(encoding="utf-8"))
    assert summary["watchlist_count"] == 102
    assert summary["supported_count"] == 63
    assert summary["missing_count"] == 39
    assert summary["pit_strong_count"] == 63
    assert summary["pit_degraded_count"] == 0
    assert summary["lookahead_violation_rows"] == 0
    assert summary["section_status"] == "passed"
    assert summary["acceptance_decision"] == "dashboard_readonly_financial_statement_patch_ready"
    assert contract["section_status"] == "passed"
    assert contract["watchlist_count"] == 102
    assert contract["supported_count"] == 63
    assert contract["missing_count"] == 39
    assert contract["writeback_enabled"] is False
    assert contract["manual_review_writeback_enabled"] is False
    assert contract["used_for_signal"] is False
    assert contract["used_for_admission"] is False
    assert contract["research_only"] is True


def test_dashboard_rows_missing_rows_and_guardrails_are_readonly() -> None:
    rows = pd.read_csv(OUTPUT_DIR / "dashboard_financial_statement_rows.csv")
    missing = pd.read_csv(OUTPUT_DIR / "dashboard_financial_statement_missing_rows.csv")
    guardrails = json.loads((OUTPUT_DIR / "dashboard_financial_statement_guardrails.json").read_text(encoding="utf-8"))
    assert len(rows) == 102
    assert len(missing) == 39
    assert rows["financial_statement_support"].eq("supported").sum() == 63
    assert rows["financial_statement_support"].eq("missing").sum() == 39
    assert set(rows["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert set(rows["used_for_admission"].astype(str).str.lower()) == {"false"}
    assert set(rows["research_only"].astype(str).str.lower()) == {"true"}
    assert missing["data_gap_note"].str.len().min() > 0
    assert guardrails["writeback_allowed_count"] == 0
    assert guardrails["manual_review_writeback_enabled_count"] == 0
    assert guardrails["forbidden_action_leakage_count"] == 0
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["readonly_ui_only"] is True


def test_frontend_patch_is_readonly_and_formal_strategy_diff_is_clean() -> None:
    page = (FRONTEND_DIR / "TechBottleneckWatchlistReviewPage.tsx").read_text(encoding="utf-8")
    data = (FRONTEND_DIR / "techBottleneckReadonlyData.ts").read_text(encoding="utf-8")
    types = (FRONTEND_DIR / "types.ts").read_text(encoding="utf-8")
    assert "Full Financial Statement Review Context" in page
    assert "Financial Statement Support" in page
    assert "Financial statement data unavailable before first admission date" in data
    assert "techBottleneckFinancialStatementSummary" in data
    assert "TechBottleneckFinancialStatementRow" in types
    assert "writebackEnabled: false" in data
    assert "manualReviewWritebackEnabled: false" in data
    assert not _has_forbidden_language(page)
    assert not _has_forbidden_language(data)
    assert not _has_forbidden_language(types)

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
