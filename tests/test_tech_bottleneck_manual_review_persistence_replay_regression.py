from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_manual_review_persistence_replay_regression_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def test_replay_regression_outputs_exist() -> None:
    expected = {
        "manual_review_persistence_replay_regression_summary.json",
        "manual_review_persistence_replay_regression_events.csv",
        "manual_review_persistence_replay_regression_rejected_writes.csv",
        "manual_review_persistence_replay_regression_expected_store.csv",
        "manual_review_persistence_replay_regression_reconstructed_store.csv",
        "manual_review_persistence_replay_regression_latest_state.csv",
        "manual_review_persistence_replay_regression_consistency_checks.csv",
        "manual_review_persistence_replay_regression_field_validation.csv",
        "manual_review_persistence_replay_regression_guardrails.json",
        "tech_bottleneck_manual_review_persistence_replay_regression_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})


def test_replay_regression_counts_and_consistency_are_clean() -> None:
    summary = json.loads((OUTPUT_DIR / "manual_review_persistence_replay_regression_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "manual_review_persistence_replay_regression_guardrails.json").read_text(encoding="utf-8"))
    expected_store = pd.read_csv(OUTPUT_DIR / "manual_review_persistence_replay_regression_expected_store.csv")
    reconstructed = pd.read_csv(OUTPUT_DIR / "manual_review_persistence_replay_regression_reconstructed_store.csv")
    latest_state = pd.read_csv(OUTPUT_DIR / "manual_review_persistence_replay_regression_latest_state.csv")
    checks = pd.read_csv(OUTPUT_DIR / "manual_review_persistence_replay_regression_consistency_checks.csv")

    assert summary["regression_generated"] is True
    assert summary["synthetic_event_count"] > 0
    assert summary["allowed_event_count"] > 0
    assert summary["forbidden_write_attempt_count"] > 0
    assert summary["invalid_attempt_count"] > 0
    assert summary["rejected_write_count"] == summary["forbidden_write_attempt_count"] + summary["invalid_attempt_count"]
    assert summary["replay_consistency_mismatch_count"] == 0
    assert summary["latest_state_mismatch_count"] == 0
    assert summary["audit_hash_missing_count"] == 0
    assert summary["event_ordering_error_count"] == 0
    assert summary["forbidden_field_persisted_count"] == 0
    assert expected_store.fillna("").astype(str).to_dict("records") == reconstructed.fillna("").astype(str).to_dict("records")
    assert len(latest_state) > 0
    assert set(checks["status"]) == {"passed"}
    assert guardrails["replay_consistency_mismatch_count"] == 0


def test_replay_regression_guardrails_events_and_strategy_diff_are_clean() -> None:
    guardrails = json.loads((OUTPUT_DIR / "manual_review_persistence_replay_regression_guardrails.json").read_text(encoding="utf-8"))
    events = pd.read_csv(OUTPUT_DIR / "manual_review_persistence_replay_regression_events.csv")
    rejected = pd.read_csv(OUTPUT_DIR / "manual_review_persistence_replay_regression_rejected_writes.csv")
    expected_store = pd.read_csv(OUTPUT_DIR / "manual_review_persistence_replay_regression_expected_store.csv")

    assert guardrails["strategy_writeback_enabled_count"] == 0
    assert guardrails["baseline_admission_change_enabled_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["forbidden_action_leakage_count"] == 0
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["research_only"] is True
    assert guardrails["synthetic_only"] is True
    assert events["synthetic_only"].astype(str).str.lower().eq("true").all()
    assert events["research_only"].astype(str).str.lower().eq("true").all()
    assert events["audit_hash"].fillna("").str.len().eq(64).all()
    assert rejected["status"].eq("rejected").all()
    forbidden_rejected = rejected[rejected["attempt_type"].eq("forbidden_write")]
    assert not set(forbidden_rejected["field_name"]).intersection(set(expected_store.columns))

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
