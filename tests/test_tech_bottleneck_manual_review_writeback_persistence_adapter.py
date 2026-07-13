from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_manual_review_writeback_persistence_adapter_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def test_persistence_adapter_outputs_and_contract_exist() -> None:
    expected = {
        "manual_review_persistence_adapter_summary.json",
        "manual_review_persistence_adapter_contract.json",
        "manual_review_persistence_store.csv",
        "manual_review_persistence_store.json",
        "manual_review_persistence_audit_log.csv",
        "manual_review_persistence_rejected_writes.csv",
        "manual_review_persistence_replay_reconstructed_store.csv",
        "manual_review_persistence_consistency_checks.csv",
        "manual_review_persistence_field_validation.csv",
        "manual_review_persistence_guardrails.json",
        "tech_bottleneck_manual_review_writeback_persistence_adapter_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    contract = json.loads((OUTPUT_DIR / "manual_review_persistence_adapter_contract.json").read_text(encoding="utf-8"))
    summary = json.loads((OUTPUT_DIR / "manual_review_persistence_adapter_summary.json").read_text(encoding="utf-8"))
    assert contract["storage_scope"] == "manual_review_only"
    assert contract["storage_mode"] == "file_based_append_only_audit"
    assert contract["research_only"] is True
    assert contract["manual_review_writeback_enabled"] is True
    assert contract["strategy_writeback_enabled"] is False
    assert contract["baseline_admission_change_enabled"] is False
    assert contract["used_for_signal"] is False
    assert contract["used_for_admission"] is False
    assert contract["audit_log_mode"] == "append_only"
    assert contract["audit_replay_supported"] is True
    assert summary["acceptance_decision"] == "manual_review_writeback_persistence_adapter_ready"


def test_persistence_store_audit_replay_and_rejections_are_valid() -> None:
    store = pd.read_csv(OUTPUT_DIR / "manual_review_persistence_store.csv")
    reconstructed = pd.read_csv(OUTPUT_DIR / "manual_review_persistence_replay_reconstructed_store.csv")
    audit_log = pd.read_csv(OUTPUT_DIR / "manual_review_persistence_audit_log.csv")
    rejected = pd.read_csv(OUTPUT_DIR / "manual_review_persistence_rejected_writes.csv")
    checks = pd.read_csv(OUTPUT_DIR / "manual_review_persistence_consistency_checks.csv")

    assert len(store) > 0
    assert len(audit_log) > 0
    assert len(rejected) > 0
    assert set(checks["status"]) == {"passed"}
    assert store.fillna("").astype(str).to_dict("records") == reconstructed.fillna("").astype(str).to_dict("records")
    assert audit_log["audit_hash"].fillna("").str.len().eq(64).all()
    assert store["research_only"].astype(str).str.lower().eq("true").all()
    assert store["used_for_signal"].astype(str).str.lower().eq("false").all()
    assert store["used_for_admission"].astype(str).str.lower().eq("false").all()
    assert store["strategy_writeback_allowed"].astype(str).str.lower().eq("false").all()
    assert store["baseline_admission_change_allowed"].astype(str).str.lower().eq("false").all()
    assert rejected["status"].eq("rejected").all()
    assert not set(rejected["field_name"]).intersection(set(store.columns))


def test_persistence_guardrails_and_formal_strategy_diff_are_clean() -> None:
    guardrails = json.loads((OUTPUT_DIR / "manual_review_persistence_guardrails.json").read_text(encoding="utf-8"))
    assert guardrails["persistence_adapter_generated"] is True
    assert guardrails["manual_review_writeback_enabled"] is True
    assert guardrails["storage_scope"] == "manual_review_only"
    assert guardrails["allowed_write_count"] > 0
    assert guardrails["forbidden_write_attempt_count"] > 0
    assert guardrails["rejected_write_count"] == guardrails["forbidden_write_attempt_count"]
    assert guardrails["replay_consistency_mismatch_count"] == 0
    assert guardrails["audit_hash_missing_count"] == 0
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

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
