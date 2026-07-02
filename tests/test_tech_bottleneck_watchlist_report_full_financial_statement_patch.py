from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_watchlist_report_full_financial_statement_patch_v1"
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
]


def _has_forbidden_language(text: str) -> bool:
    return any(pattern.search(text) for pattern in FORBIDDEN_PATTERNS)


def test_patch_outputs_exist_and_summary_counts_are_expected() -> None:
    expected = {
        "watchlist_report_full_financial_statement_patch_summary.json",
        "watchlist_report_full_financial_statement_patch_manifest.csv",
        "watchlist_report_full_financial_statement_sections.json",
        "watchlist_report_full_financial_statement_sections.csv",
        "watchlist_report_full_financial_statement_missing.csv",
        "watchlist_report_full_financial_statement_pit_audit.csv",
        "watchlist_report_full_financial_statement_field_coverage.csv",
        "watchlist_report_full_financial_statement_guardrails.json",
        "tech_bottleneck_watchlist_report_full_financial_statement_patch_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads(
        (OUTPUT_DIR / "watchlist_report_full_financial_statement_patch_summary.json").read_text(encoding="utf-8")
    )
    assert summary["watchlist_count"] == 102
    assert summary["reports_total"] == 102
    assert summary["reports_patched"] == 63
    assert summary["reports_missing_financial_statement"] == 39
    assert summary["pit_strong_count"] == 63
    assert summary["pit_degraded_count"] == 0
    assert summary["missing_count"] == 39
    assert summary["lookahead_violation_rows"] == 0
    assert summary["writeback_allowed_count"] == 0
    assert summary["trading_language_hit_count"] == 0
    assert summary["baseline_admission_changed_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["acceptance_decision"] == "watchlist_report_full_financial_statement_patch_ready"


def test_patch_sections_manifest_and_missing_notes_are_research_only() -> None:
    manifest = pd.read_csv(OUTPUT_DIR / "watchlist_report_full_financial_statement_patch_manifest.csv")
    sections = pd.read_csv(OUTPUT_DIR / "watchlist_report_full_financial_statement_sections.csv")
    missing = pd.read_csv(OUTPUT_DIR / "watchlist_report_full_financial_statement_missing.csv")

    assert len(manifest) == 102
    assert len(sections) == 102
    assert len(missing) == 39
    assert manifest["patch_status"].eq("patched").sum() == 63
    assert manifest["patch_status"].eq("data_gap_section").sum() == 39
    assert set(sections["research_only"].astype(str).str.lower()) == {"true"}
    assert set(sections["used_for_signal"].astype(str).str.lower()) == {"false"}
    assert set(sections["used_for_admission"].astype(str).str.lower()) == {"false"}
    assert sections["section_markdown"].str.contains("Full Financial Statement Review Context", regex=False).all()
    assert missing["data_gap_note"].str.len().min() > 0
    assert missing["manual_review_impact"].str.len().min() > 0

    strong = sections[sections["pit_status"].eq("pit_strong")]
    assert (
        pd.to_datetime(strong["announce_date"], errors="coerce")
        <= pd.to_datetime(strong["first_admission_date"], errors="coerce")
    ).all()


def test_guardrails_report_scan_and_formal_strategy_diff_are_clean() -> None:
    guardrails = json.loads(
        (OUTPUT_DIR / "watchlist_report_full_financial_statement_guardrails.json").read_text(encoding="utf-8")
    )
    pit_audit = pd.read_csv(OUTPUT_DIR / "watchlist_report_full_financial_statement_pit_audit.csv")
    assert guardrails["writeback_allowed_count"] == 0
    assert guardrails["forbidden_action_leakage_count"] == 0
    assert guardrails["trading_language_hit_count"] == 0
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
