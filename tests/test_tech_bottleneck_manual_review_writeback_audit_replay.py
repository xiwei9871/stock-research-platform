from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_manual_review_writeback_audit_replay_v1"
WRITEBACK_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_manual_review_writeback_research_only_v1"
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


def test_audit_replay_outputs_and_summary_are_valid() -> None:
    expected = {
        "manual_review_writeback_audit_replay_summary.json",
        "manual_review_writeback_audit_replay_events.csv",
        "manual_review_writeback_audit_replay_rejected_events.csv",
        "manual_review_writeback_audit_replay_expected_store.csv",
        "manual_review_writeback_audit_replay_reconstructed_store.csv",
        "manual_review_writeback_audit_replay_consistency_checks.csv",
        "manual_review_writeback_audit_replay_field_validation.csv",
        "manual_review_writeback_audit_replay_guardrails.json",
        "tech_bottleneck_manual_review_writeback_audit_replay_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "manual_review_writeback_audit_replay_summary.json").read_text(encoding="utf-8"))
    events = pd.read_csv(OUTPUT_DIR / "manual_review_writeback_audit_replay_events.csv")
    rejected = pd.read_csv(OUTPUT_DIR / "manual_review_writeback_audit_replay_rejected_events.csv")
    assert summary["acceptance_decision"] == "manual_review_writeback_audit_replay_ready"
    assert summary["synthetic_event_count"] > 0
    assert summary["allowed_event_count"] > 0
    assert summary["forbidden_attempt_count"] > 0
    assert summary["rejected_event_count"] == summary["forbidden_attempt_count"]
    assert len(events) == summary["allowed_event_count"]
    assert len(rejected) == summary["rejected_event_count"]
    assert events["research_only"].astype(str).str.lower().eq("true").all()
    assert events["synthetic_only"].astype(str).str.lower().eq("true").all()
    assert rejected["research_only"].astype(str).str.lower().eq("true").all()
    assert rejected["synthetic_only"].astype(str).str.lower().eq("true").all()


def test_replay_reconstructs_expected_store_and_rejects_forbidden_fields() -> None:
    expected_store = pd.read_csv(OUTPUT_DIR / "manual_review_writeback_audit_replay_expected_store.csv")
    reconstructed = pd.read_csv(OUTPUT_DIR / "manual_review_writeback_audit_replay_reconstructed_store.csv")
    consistency = pd.read_csv(OUTPUT_DIR / "manual_review_writeback_audit_replay_consistency_checks.csv")
    field_validation = pd.read_csv(OUTPUT_DIR / "manual_review_writeback_audit_replay_field_validation.csv")
    rejected = pd.read_csv(OUTPUT_DIR / "manual_review_writeback_audit_replay_rejected_events.csv")
    template = pd.read_csv(WRITEBACK_DIR / "manual_review_writeback_store_template.csv")

    pd.testing.assert_frame_equal(expected_store, reconstructed)
    assert set(consistency["status"]) == {"passed"}
    assert set(field_validation["status"]) == {"passed"}
    assert "trading_signal" in set(rejected["field_name"])
    assert "baseline_admission_change" in set(rejected["field_name"])
    assert "target_price" in set(rejected["field_name"])
    assert "position" in set(rejected["field_name"])
    forbidden_columns = set(rejected["field_name"])
    assert forbidden_columns.isdisjoint(set(reconstructed.columns))
    assert template["review_status"].eq("not_reviewed").all()
    assert template["manual_review_conclusion"].eq("not_reviewed").all()
    assert reconstructed["review_status"].iloc[0] == "in_review"
    assert reconstructed["manual_review_conclusion"].iloc[0] == "data_insufficient"


def test_audit_replay_guardrails_and_strategy_diff_are_clean() -> None:
    guardrails = json.loads((OUTPUT_DIR / "manual_review_writeback_audit_replay_guardrails.json").read_text(encoding="utf-8"))
    assert guardrails["synthetic_event_count"] > 0
    assert guardrails["allowed_event_count"] > 0
    assert guardrails["forbidden_attempt_count"] > 0
    assert guardrails["rejected_event_count"] == guardrails["forbidden_attempt_count"]
    assert guardrails["replay_consistency_mismatch_count"] == 0
    assert guardrails["audit_hash_missing_count"] == 0
    assert guardrails["manual_review_writeback_enabled"] is True
    assert guardrails["strategy_writeback_enabled_count"] == 0
    assert guardrails["baseline_admission_change_enabled_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["forbidden_action_leakage_count"] == 0
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["research_only"] is True
    assert guardrails["synthetic_only"] is True

    for path in OUTPUT_DIR.rglob("*"):
        if path.name in {
            "manual_review_writeback_audit_replay_rejected_events.csv",
            "manual_review_writeback_audit_replay_field_validation.csv",
        }:
            continue
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
