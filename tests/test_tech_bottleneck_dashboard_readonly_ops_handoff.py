from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_dashboard_readonly_ops_handoff_v1"
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


def test_ops_handoff_outputs_and_ready_flags_exist() -> None:
    expected = {
        "ops_handoff_summary.json",
        "ops_handoff_checklist.csv",
        "ops_handoff_guardrails.json",
        "ops_handoff_route_nav_frontend_checks.json",
        "ops_handoff_known_limitations.csv",
        "ops_handoff_troubleshooting.md",
        "ops_handoff_rollback_plan.md",
        "ops_handoff_user_guide.md",
        "ops_handoff_README.md",
        "tech_bottleneck_dashboard_readonly_ops_handoff_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "ops_handoff_summary.json").read_text(encoding="utf-8"))
    assert summary["ops_handoff_generated"] is True
    assert summary["route_available"] is True
    assert summary["nav_available"] is True
    assert summary["smoke_v5_ready"] is True
    assert summary["release_notes_ready"] is True
    assert summary["archive_packaging_ready"] is True
    assert summary["archive_integrity_ready"] is True
    assert summary["manual_review_writeback_ready"] is True
    assert summary["audit_replay_ready"] is True
    assert summary["acceptance_decision"] == "dashboard_readonly_ops_handoff_ready"


def test_ops_checklist_route_nav_and_guardrails_are_clean() -> None:
    checklist = pd.read_csv(OUTPUT_DIR / "ops_handoff_checklist.csv")
    guardrails = json.loads((OUTPUT_DIR / "ops_handoff_guardrails.json").read_text(encoding="utf-8"))
    route_nav = json.loads((OUTPUT_DIR / "ops_handoff_route_nav_frontend_checks.json").read_text(encoding="utf-8"))

    assert set(checklist["status"]) == {"passed"}
    assert route_nav["route_path"] == "/tech-bottleneck/watchlist-review"
    assert route_nav["route_available"] is True
    assert route_nav["nav_label"] == "科技卡脖子观察池"
    assert route_nav["nav_available"] is True
    assert route_nav["page_component_loadable"] is True
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


def test_ops_docs_are_research_only_and_formal_strategy_diff_is_empty() -> None:
    readme = (OUTPUT_DIR / "ops_handoff_README.md").read_text(encoding="utf-8")
    user_guide = (OUTPUT_DIR / "ops_handoff_user_guide.md").read_text(encoding="utf-8")
    rollback = (OUTPUT_DIR / "ops_handoff_rollback_plan.md").read_text(encoding="utf-8")
    troubleshooting = (OUTPUT_DIR / "ops_handoff_troubleshooting.md").read_text(encoding="utf-8")
    report = (OUTPUT_DIR / "tech_bottleneck_dashboard_readonly_ops_handoff_v1_report.md").read_text(encoding="utf-8")

    assert "research-only" in readme
    assert "Forbidden Usage" in readme
    assert "formal strategy files are out of rollback scope" in rollback
    for required in ["route unavailable", "nav hidden", "build failure", "manual review panel hidden", "audit replay mismatch"]:
        assert required in troubleshooting
    for text in [readme, user_guide, rollback, troubleshooting, report]:
        assert not _has_forbidden_language(text)

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
