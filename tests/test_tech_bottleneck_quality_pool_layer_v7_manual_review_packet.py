from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd

from stock_research.tech_bottleneck_quality_pool_layer_v7_manual_review_packet import (
    validate_v7_manual_approval_file,
)


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_quality_pool_layer_v7_manual_review_packet.py"
V7_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v7_proposal_v1"
V7_SUMMARY = V7_DIR / "tech_bottleneck_quality_pool_layer_v7_proposal_summary.json"
V7_PROPOSAL = V7_DIR / "tech_bottleneck_quality_pool_layer_v7_proposal.csv"
V7_ADDED = V7_DIR / "tech_bottleneck_quality_pool_layer_v7_added_from_standard.csv"
V7_EVIDENCE = V7_DIR / "tech_bottleneck_quality_pool_layer_v7_evidence_index.csv"
V6_MANUAL_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v6_manual_approval_v1"
V6_MANUAL_DECISIONS = V6_MANUAL_DIR / "tech_bottleneck_quality_pool_layer_v6_manual_approval_decisions.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v7_manual_review_packet_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_generator() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _output_hashes() -> dict[str, str]:
    return {path.name: _sha(path) for path in sorted(OUTPUT_DIR.iterdir()) if path.is_file()}


def test_quality_pool_layer_v7_manual_review_packet_outputs_and_summary() -> None:
    input_hashes_before = {
        "v7_summary": _sha(V7_SUMMARY),
        "v7_proposal": _sha(V7_PROPOSAL),
        "v7_added": _sha(V7_ADDED),
        "v7_evidence": _sha(V7_EVIDENCE),
        "v6_manual": _sha(V6_MANUAL_DECISIONS),
    }
    _run_generator()
    input_hashes_after = {
        "v7_summary": _sha(V7_SUMMARY),
        "v7_proposal": _sha(V7_PROPOSAL),
        "v7_added": _sha(V7_ADDED),
        "v7_evidence": _sha(V7_EVIDENCE),
        "v6_manual": _sha(V6_MANUAL_DECISIONS),
    }

    expected = {
        "v7_manual_review_packet.json",
        "v7_manual_review_packet.md",
        "v7_manual_review_candidates.csv",
        "v7_manual_approval_template.csv",
        "v7_manual_review_packet_summary.json",
        "v7_manual_review_packet_summary.md",
        "v7_manual_review_packet_guardrails.json",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hashes_before == input_hashes_after

    summary = json.loads((OUTPUT_DIR / "v7_manual_review_packet_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "v7_manual_review_packet_guardrails.json").read_text(encoding="utf-8"))

    assert summary["quality_pool_v5_reference_count"] == 300
    assert summary["quality_pool_v6_proposal_reference_count"] == 326
    assert summary["v6_manual_approved_count"] == 0
    assert summary["v6_hold_for_review_count"] == 26
    assert summary["standard_core_equivalent_candidate_count"] == 52
    assert summary["proposed_additions_count"] == 52
    assert summary["evidence_index_rows"] == 1096
    assert summary["candidates_requiring_manual_review"] == 78
    assert summary["unresolved_hold_count"] == 26
    assert summary["auto_approved_count"] == 0
    assert summary["frozen_v7_generated"] is False
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["acceptance_decision"] == "quality_pool_layer_v7_manual_review_packet_ready"

    assert guardrails["research_only"] is True
    assert guardrails["auto_approved_count"] == 0
    assert guardrails["frozen_v7_generated"] is False
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True


def test_quality_pool_layer_v7_manual_review_packet_candidate_layers_and_template_defaults() -> None:
    _run_generator()

    candidates = pd.read_csv(OUTPUT_DIR / "v7_manual_review_candidates.csv", dtype={"stock_code": str})
    template = pd.read_csv(OUTPUT_DIR / "v7_manual_approval_template.csv", dtype={"stock_code": str}).fillna("")

    assert len(candidates) == 378
    assert (candidates["candidate_layer"].eq("v5_baseline_kept")).sum() == 300
    assert (candidates["candidate_layer"].eq("v6_hold_for_review_unresolved")).sum() == 26
    assert (candidates["candidate_layer"].eq("standard_core_equivalent_v7_candidates")).sum() == 52
    assert candidates[candidates["candidate_layer"].eq("v6_hold_for_review_unresolved")]["review_status"].eq(
        "hold_for_review"
    ).all()
    standard = candidates[candidates["candidate_layer"].eq("standard_core_equivalent_v7_candidates")]
    assert standard["review_status"].eq("manual_review_required").all()
    assert standard["approval_default"].eq("pending").all()
    assert standard["proposal_reason"].eq("standard_core_equivalent_primary_source_supported").all()
    assert standard["evidence_row_count"].ge(1).all()
    assert standard["page_citation_count"].ge(1).all()

    assert len(template) == 78
    assert set(template["candidate_source"]) == {
        "v6_hold_for_review_unresolved",
        "standard_core_equivalent_v7_candidates",
    }
    assert not template["manual_decision"].str.lower().eq("approve").any()
    assert set(template["manual_decision"].unique()).issubset({"", "pending", "hold"})
    assert template[template["candidate_source"].eq("v6_hold_for_review_unresolved")]["manual_decision"].eq("hold").all()
    assert template[template["candidate_source"].eq("standard_core_equivalent_v7_candidates")][
        "recommended_action"
    ].eq("review_for_approval").all()


def test_quality_pool_layer_v7_manual_review_packet_validator_rejects_invalid_files(tmp_path: Path) -> None:
    _run_generator()
    template = pd.read_csv(OUTPUT_DIR / "v7_manual_approval_template.csv", dtype={"stock_code": str}).fillna("")

    unknown = template.head(1).copy()
    unknown.loc[unknown.index[0], "stock_code"] = "999999"
    unknown_path = tmp_path / "unknown.csv"
    unknown.to_csv(unknown_path, index=False)
    unknown_result = validate_v7_manual_approval_file(unknown_path)
    assert unknown_result["valid"] is False
    assert unknown_result["frozen_v7_generated"] is False
    assert unknown_result["unknown_stock_code_count"] == 1

    duplicate = pd.concat([template.head(1), template.head(1)], ignore_index=True)
    duplicate.loc[0, "manual_decision"] = "approve"
    duplicate.loc[0, "manual_reviewer"] = "reviewer"
    duplicate.loc[0, "manual_comment"] = "checked"
    duplicate.loc[1, "manual_decision"] = "reject"
    duplicate_path = tmp_path / "duplicate.csv"
    duplicate.to_csv(duplicate_path, index=False)
    duplicate_result = validate_v7_manual_approval_file(duplicate_path)
    assert duplicate_result["valid"] is False
    assert duplicate_result["duplicate_conflict_count"] == 1
    assert duplicate_result["frozen_v7_generated"] is False

    missing_reviewer = template.head(1).copy()
    missing_reviewer.loc[missing_reviewer.index[0], "manual_decision"] = "approve"
    missing_reviewer.loc[missing_reviewer.index[0], "manual_reviewer"] = ""
    missing_reviewer.loc[missing_reviewer.index[0], "manual_comment"] = ""
    missing_reviewer_path = tmp_path / "missing_reviewer.csv"
    missing_reviewer.to_csv(missing_reviewer_path, index=False)
    missing_result = validate_v7_manual_approval_file(missing_reviewer_path)
    assert missing_result["valid"] is False
    assert missing_result["approve_missing_reviewer_count"] == 1
    assert missing_result["approve_missing_comment_count"] == 1
    assert missing_result["frozen_v7_generated"] is False

    invalid_decision = template.head(1).copy()
    invalid_decision.loc[invalid_decision.index[0], "manual_decision"] = "auto_approve"
    invalid_decision_path = tmp_path / "invalid_decision.csv"
    invalid_decision.to_csv(invalid_decision_path, index=False)
    invalid_result = validate_v7_manual_approval_file(invalid_decision_path)
    assert invalid_result["valid"] is False
    assert invalid_result["invalid_manual_decision_count"] == 1


def test_quality_pool_layer_v7_manual_review_packet_deterministic_and_strategy_diff_clean() -> None:
    _run_generator()
    first = _output_hashes()
    _run_generator()
    second = _output_hashes()
    assert first == second

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
