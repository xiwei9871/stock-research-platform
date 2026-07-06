from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_dashboard_readonly_release_notes_v1"
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


def test_release_notes_outputs_and_readiness_flags_exist() -> None:
    expected = {
        "dashboard_readonly_release_notes_summary.json",
        "dashboard_readonly_release_notes_checklist.csv",
        "dashboard_readonly_release_notes_guardrails.json",
        "dashboard_readonly_release_notes_known_limitations.csv",
        "dashboard_readonly_release_notes_usage_boundary.csv",
        "tech_bottleneck_dashboard_readonly_release_notes_v1.md",
        "tech_bottleneck_dashboard_readonly_release_notes_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "dashboard_readonly_release_notes_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "dashboard_readonly_release_notes_guardrails.json").read_text(encoding="utf-8"))
    assert summary["release_name"] == "Tech Bottleneck Watchlist Review Dashboard v1"
    assert summary["release_notes_generated"] is True
    assert summary["smoke_v5_ready"] is True
    assert summary["manual_review_writeback_ready"] is True
    assert summary["audit_replay_ready"] is True
    assert summary["archive_integrity_ready"] is True
    assert summary["acceptance_decision"] == "dashboard_readonly_release_notes_ready"
    assert guardrails["release_notes_generated"] is True
    assert guardrails["acceptance_decision"] == "dashboard_readonly_release_notes_ready"


def test_release_checklist_and_guardrails_are_clean() -> None:
    checklist = pd.read_csv(OUTPUT_DIR / "dashboard_readonly_release_notes_checklist.csv")
    guardrails = json.loads((OUTPUT_DIR / "dashboard_readonly_release_notes_guardrails.json").read_text(encoding="utf-8"))
    assert checklist["status"].eq("passed").all()
    assert guardrails["strategy_writeback_enabled_count"] == 0
    assert guardrails["baseline_admission_change_enabled_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["research_only"] is True


def test_release_notes_content_and_formal_strategy_diff_are_clean() -> None:
    notes = (OUTPUT_DIR / "tech_bottleneck_dashboard_readonly_release_notes_v1.md").read_text(encoding="utf-8")
    report = (OUTPUT_DIR / "tech_bottleneck_dashboard_readonly_release_notes_v1_report.md").read_text(encoding="utf-8")
    limitations = pd.read_csv(OUTPUT_DIR / "dashboard_readonly_release_notes_known_limitations.csv")
    usage = pd.read_csv(OUTPUT_DIR / "dashboard_readonly_release_notes_usage_boundary.csv")
    assert "research-only" in notes
    assert "Forbidden Usage" in notes
    assert "Manual Review Research-Only Writeback" in notes
    assert "Full Financial Statement Review Context" in notes
    assert "News and Event Review Context" in notes
    assert len(limitations) >= 6
    assert {"recommended", "forbidden"}.issubset(set(usage["usage_type"]))
    for text in [notes, report]:
        assert not _has_forbidden_language(text)

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
