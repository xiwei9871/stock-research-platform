from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd

from stock_research.tech_bottleneck_quality_pool_layer_v7_manual_approval_ingest import run


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_quality_pool_layer_v7_manual_approval_ingest.py"
PACKET_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v7_manual_review_packet_v1"
TEMPLATE = PACKET_DIR / "v7_manual_approval_template.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v7_manual_approval_ingest_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _run_cli(*args: str) -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT), *args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_v7_manual_approval_ingest_default_template_keeps_all_pending_or_hold() -> None:
    _run_cli()

    expected = {
        "v7_manual_approval_ledger.json",
        "v7_manual_approval_ledger.csv",
        "v7_manual_approval_ingest_summary.json",
        "v7_manual_approval_ingest_summary.md",
        "v7_manual_approval_validation_errors.json",
        "v7_manual_approval_validation_warnings.json",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "v7_manual_approval_ingest_summary.json").read_text(encoding="utf-8"))
    ledger = pd.read_csv(OUTPUT_DIR / "v7_manual_approval_ledger.csv", dtype={"stock_code": str}).fillna("")

    assert summary["packet_candidate_count"] == 378
    assert summary["total_rows"] == 78
    assert summary["approved_count"] == 0
    assert summary["valid_approved_count"] == 0
    assert summary["invalid_approved_count"] == 0
    assert summary["hold_count"] == 26
    assert summary["pending_count"] == 52
    assert summary["v6_hold_approved_count"] == 0
    assert summary["standard_candidate_approved_count"] == 0
    assert summary["can_freeze_v7"] is False
    assert summary["frozen_v7_generated"] is False
    assert summary["auto_approved_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["freeze_precheck"]["status"] == "no_approved_candidates"
    assert summary["freeze_precheck"]["expected_frozen_v7_count_if_next_step"] == 300
    assert summary["acceptance_decision"] == "quality_pool_layer_v7_manual_approval_ingest_no_approved_candidates"
    assert ledger["can_enter_freeze_candidate"].eq(False).all()


def test_v7_manual_approval_ingest_accepts_explicit_standard_and_v6_hold_approvals(tmp_path: Path) -> None:
    template = pd.read_csv(TEMPLATE, dtype={"stock_code": str}).fillna("")
    approval = template.copy()
    standard_index = approval[approval["candidate_source"].eq("standard_core_equivalent_v7_candidates")].index[0]
    v6_index = approval[approval["candidate_source"].eq("v6_hold_for_review_unresolved")].index[0]
    approval.loc[standard_index, "manual_decision"] = "approve"
    approval.loc[standard_index, "manual_reviewer"] = "reviewer_a"
    approval.loc[standard_index, "manual_comment"] = "checked standard primary-source evidence"
    approval.loc[v6_index, "manual_decision"] = "approve"
    approval.loc[v6_index, "manual_reviewer"] = "reviewer_b"
    approval.loc[v6_index, "manual_comment"] = "explicitly approved unresolved v6 hold"
    approval_file = tmp_path / "approval.csv"
    output_dir = tmp_path / "out"
    approval.to_csv(approval_file, index=False)

    summary = run(approval_file=approval_file, packet_dir=PACKET_DIR, output_dir=output_dir)
    ledger = pd.read_csv(output_dir / "v7_manual_approval_ledger.csv", dtype={"stock_code": str}).fillna("")

    assert summary["approved_count"] == 2
    assert summary["valid_approved_count"] == 2
    assert summary["invalid_approved_count"] == 0
    assert summary["v6_hold_approved_count"] == 1
    assert summary["standard_candidate_approved_count"] == 1
    assert summary["validation_error_count"] == 0
    assert summary["can_freeze_v7"] is False
    assert summary["frozen_v7_generated"] is False
    assert summary["freeze_precheck"]["status"] == "ready_for_freeze_proposal"
    assert summary["freeze_precheck"]["expected_frozen_v7_count_if_next_step"] == 302
    assert summary["acceptance_decision"] == "quality_pool_layer_v7_manual_approval_ingest_ready_for_freeze_proposal"
    approved_rows = ledger[ledger["normalized_decision"].eq("approve")]
    assert len(approved_rows) == 2
    assert approved_rows["can_enter_freeze_candidate"].eq(True).all()


def test_v7_manual_approval_ingest_blocks_invalid_approvals_unknown_and_conflicts(tmp_path: Path) -> None:
    template = pd.read_csv(TEMPLATE, dtype={"stock_code": str}).fillna("")

    missing = template.head(1).copy()
    missing.loc[missing.index[0], "manual_decision"] = "approve"
    missing.loc[missing.index[0], "manual_reviewer"] = ""
    missing.loc[missing.index[0], "manual_comment"] = ""
    missing_path = tmp_path / "missing.csv"
    missing.to_csv(missing_path, index=False)
    missing_summary = run(approval_file=missing_path, packet_dir=PACKET_DIR, output_dir=tmp_path / "missing_out")
    assert missing_summary["approved_count"] == 1
    assert missing_summary["valid_approved_count"] == 0
    assert missing_summary["invalid_approved_count"] == 1
    assert missing_summary["validation_error_count"] > 0
    assert missing_summary["acceptance_decision"] == "quality_pool_layer_v7_manual_approval_ingest_blocked"

    unknown = template.head(1).copy()
    unknown.loc[unknown.index[0], "stock_code"] = "999999"
    unknown.loc[unknown.index[0], "manual_decision"] = "hold"
    unknown_path = tmp_path / "unknown.csv"
    unknown.to_csv(unknown_path, index=False)
    unknown_summary = run(approval_file=unknown_path, packet_dir=PACKET_DIR, output_dir=tmp_path / "unknown_out")
    assert unknown_summary["unknown_stock_count"] == 1
    assert unknown_summary["validation_error_count"] > 0
    assert unknown_summary["acceptance_decision"] == "quality_pool_layer_v7_manual_approval_ingest_blocked"

    duplicate = pd.concat([template.head(1), template.head(1)], ignore_index=True)
    duplicate.loc[0, "manual_decision"] = "approve"
    duplicate.loc[0, "manual_reviewer"] = "reviewer"
    duplicate.loc[0, "manual_comment"] = "checked"
    duplicate.loc[1, "manual_decision"] = "reject"
    duplicate.loc[1, "manual_comment"] = "conflicting reject"
    duplicate_path = tmp_path / "duplicate.csv"
    duplicate.to_csv(duplicate_path, index=False)
    duplicate_summary = run(approval_file=duplicate_path, packet_dir=PACKET_DIR, output_dir=tmp_path / "duplicate_out")
    assert duplicate_summary["duplicate_conflict_count"] == 1
    assert duplicate_summary["validation_error_count"] > 0
    assert duplicate_summary["acceptance_decision"] == "quality_pool_layer_v7_manual_approval_ingest_blocked"


def test_v7_manual_approval_ingest_reject_hold_pending_do_not_enter_freeze(tmp_path: Path) -> None:
    template = pd.read_csv(TEMPLATE, dtype={"stock_code": str}).fillna("")
    approval = template.head(3).copy()
    approval.loc[approval.index[0], "manual_decision"] = "reject"
    approval.loc[approval.index[0], "manual_comment"] = "not enough support"
    approval.loc[approval.index[1], "manual_decision"] = "hold"
    approval.loc[approval.index[2], "manual_decision"] = "pending"
    approval_path = tmp_path / "non_approve.csv"
    output_dir = tmp_path / "non_approve_out"
    approval.to_csv(approval_path, index=False)

    summary = run(approval_file=approval_path, packet_dir=PACKET_DIR, output_dir=output_dir)
    ledger = pd.read_csv(output_dir / "v7_manual_approval_ledger.csv", dtype={"stock_code": str}).fillna("")

    assert summary["rejected_count"] == 1
    assert summary["hold_count"] == 1
    assert summary["pending_count"] == 1
    assert summary["valid_approved_count"] == 0
    assert ledger["can_enter_freeze_candidate"].eq(False).all()
    assert summary["freeze_precheck"]["expected_frozen_v7_count_if_next_step"] == 300
    assert summary["frozen_v7_generated"] is False


def test_v7_manual_approval_ingest_strategy_diff_clean() -> None:
    _run_cli()
    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
