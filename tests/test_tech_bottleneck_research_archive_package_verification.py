from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_research_archive_package_verification_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def test_package_verification_outputs_exist() -> None:
    expected = {
        "research_archive_package_verification_summary.json",
        "research_archive_package_verification_checks.csv",
        "research_archive_package_latest_artifact_coverage.csv",
        "research_archive_package_delta_manifest.csv",
        "research_archive_package_missing_latest_artifacts.csv",
        "research_archive_package_checksum_verification.csv",
        "research_archive_package_verification_guardrails.json",
        "tech_bottleneck_research_archive_package_verification_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})


def test_package_verification_readiness_and_latest_chain_are_clean() -> None:
    summary = json.loads((OUTPUT_DIR / "research_archive_package_verification_summary.json").read_text(encoding="utf-8"))
    checks = pd.read_csv(OUTPUT_DIR / "research_archive_package_verification_checks.csv")
    coverage = pd.read_csv(OUTPUT_DIR / "research_archive_package_latest_artifact_coverage.csv")
    delta = pd.read_csv(OUTPUT_DIR / "research_archive_package_delta_manifest.csv")

    assert summary["package_verification_generated"] is True
    assert summary["package_generated"] is True
    assert summary["package_manifest_generated"] is True
    assert summary["package_checksums_generated"] is True
    assert summary["release_notes_ready"] is True
    assert summary["archive_integrity_ready"] is True
    assert summary["ops_handoff_ready"] is True
    assert summary["persistence_adapter_ready"] is True
    assert summary["smoke_v6_ready"] is True
    assert summary["persistence_replay_regression_ready"] is True
    assert summary["blocking_issue_count"] == 0
    assert summary["acceptance_decision"] in {
        "research_archive_package_verified_current",
        "package_refresh_required_for_latest_persistence_chain",
    }
    assert set(checks["severity"]).issubset({"info", "warning", "blocking"})
    assert not checks[(checks["severity"].eq("blocking")) & (~checks["status"].eq("passed"))].any().any()
    assert len(coverage) > 0
    if summary["package_refresh_required"] is True:
        assert summary["latest_artifact_coverage_status"] == "incomplete"
        assert len(delta) > 0


def test_package_verification_guardrails_checksums_and_strategy_diff_are_clean() -> None:
    guardrails = json.loads((OUTPUT_DIR / "research_archive_package_verification_guardrails.json").read_text(encoding="utf-8"))
    checksums = pd.read_csv(OUTPUT_DIR / "research_archive_package_checksum_verification.csv")
    missing = pd.read_csv(OUTPUT_DIR / "research_archive_package_missing_latest_artifacts.csv")

    assert guardrails["strategy_writeback_enabled_count"] == 0
    assert guardrails["baseline_admission_change_enabled_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0
    assert guardrails["replay_consistency_mismatch_count"] == 0
    assert guardrails["latest_state_mismatch_count"] == 0
    assert guardrails["forbidden_field_persisted_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["research_only"] is True
    assert guardrails["acceptance_decision"] != "blocked_due_to_package_verification_guardrail_failure"
    assert checksums["checksum_present"].astype(str).str.lower().eq("true").all()
    assert checksums["status"].eq("passed").all()
    assert "artifact_name" in missing.columns

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
