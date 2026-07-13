from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_quality_pool_layer_v6_manual_approval.py"
PROPOSAL_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v6_proposal_v1"
PROPOSAL_SUMMARY = PROPOSAL_DIR / "tech_bottleneck_quality_pool_layer_v6_proposal_summary.json"
PROPOSAL_MANIFEST = PROPOSAL_DIR / "tech_bottleneck_quality_pool_layer_v6_proposal.csv"
PROPOSAL_ADDED = PROPOSAL_DIR / "tech_bottleneck_quality_pool_layer_v6_added_from_batch1.csv"
PROPOSAL_EVIDENCE = PROPOSAL_DIR / "tech_bottleneck_quality_pool_layer_v6_evidence_index.csv"
GATE_DECISIONS = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_manual_review_equivalence_gate_batch1_v1/latent_manual_review_equivalence_gate_batch1_decisions.csv"
)
BACKFILL_EVIDENCE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_manual_review_backfill_batch1_v1/latent_manual_review_backfill_batch1_evidence.csv"
)
V5_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v5"
V5_MANIFEST = V5_DIR / "quality_pool_layer_v5_manifest.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v6_manual_approval_v1"
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


def test_quality_pool_layer_v6_manual_approval_outputs_and_guardrails() -> None:
    input_hashes_before = {
        "proposal_summary": _sha(PROPOSAL_SUMMARY),
        "proposal_manifest": _sha(PROPOSAL_MANIFEST),
        "proposal_added": _sha(PROPOSAL_ADDED),
        "proposal_evidence": _sha(PROPOSAL_EVIDENCE),
        "gate_decisions": _sha(GATE_DECISIONS),
        "backfill_evidence": _sha(BACKFILL_EVIDENCE),
        "v5": _sha(V5_MANIFEST),
    }
    _run_generator()
    input_hashes_after = {
        "proposal_summary": _sha(PROPOSAL_SUMMARY),
        "proposal_manifest": _sha(PROPOSAL_MANIFEST),
        "proposal_added": _sha(PROPOSAL_ADDED),
        "proposal_evidence": _sha(PROPOSAL_EVIDENCE),
        "gate_decisions": _sha(GATE_DECISIONS),
        "backfill_evidence": _sha(BACKFILL_EVIDENCE),
        "v5": _sha(V5_MANIFEST),
    }

    expected = {
        "tech_bottleneck_quality_pool_layer_v6_manual_approval_summary.json",
        "tech_bottleneck_quality_pool_layer_v6_manual_approval_packet.csv",
        "tech_bottleneck_quality_pool_layer_v6_manual_approval_decisions.csv",
        "tech_bottleneck_quality_pool_layer_v6_manual_approved.csv",
        "tech_bottleneck_quality_pool_layer_v6_manual_rejected_or_downgraded.csv",
        "tech_bottleneck_quality_pool_layer_v6_manual_hold_for_review.csv",
        "tech_bottleneck_quality_pool_layer_v6_manual_approval_guardrails.json",
        "tech_bottleneck_quality_pool_layer_v6_manual_approval_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hashes_before == input_hashes_after

    summary = json.loads(
        (OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_manual_approval_summary.json").read_text(encoding="utf-8")
    )
    guardrails = json.loads(
        (OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_manual_approval_guardrails.json").read_text(encoding="utf-8")
    )

    assert summary["research_only"] is True
    assert summary["quality_pool_v5_reference_count"] == 300
    assert summary["source_v6_proposed_addition_count"] == 26
    assert summary["processed_proposed_addition_count"] == 26
    assert summary["manual_approved_count"] == 0
    assert summary["hold_for_review_count"] == 26
    assert summary["rejected_or_downgraded_count"] == 0
    assert summary["primary_source_collection_performed"] is False
    assert summary["evidence_backfill_performed"] is False
    assert summary["core_equivalence_performed"] is False
    assert summary["frozen_quality_pool_v6_generated"] is False
    assert summary["auto_added_to_quality_pool_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["price_move_used_for_signal"] == 0
    assert summary["low_position_used_for_signal"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["acceptance_decision"] == "conditionally_ready_with_hold_for_review"

    assert guardrails["research_only"] is True
    assert guardrails["source_v6_proposed_addition_count"] == 26
    assert guardrails["processed_proposed_addition_count"] == 26
    assert guardrails["frozen_quality_pool_v6_generated"] is False
    assert guardrails["auto_added_to_quality_pool_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True


def test_quality_pool_layer_v6_manual_approval_default_hold_packet() -> None:
    _run_generator()

    added = pd.read_csv(PROPOSAL_ADDED, dtype={"stock_code": str})
    packet = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_manual_approval_packet.csv",
        dtype={"stock_code": str},
        keep_default_na=False,
    )
    decisions = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_manual_approval_decisions.csv",
        dtype={"stock_code": str},
        keep_default_na=False,
    )
    approved = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_manual_approved.csv",
        dtype={"stock_code": str},
    )
    hold = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_manual_hold_for_review.csv",
        dtype={"stock_code": str},
    )
    rejected = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v6_manual_rejected_or_downgraded.csv",
        dtype={"stock_code": str},
    )

    assert len(packet) == 26
    assert len(decisions) == 26
    assert len(hold) == 26
    assert approved.empty
    assert rejected.empty
    assert set(packet["stock_code"].astype(str).str.zfill(6)) == set(added["stock_code"].astype(str).str.zfill(6))
    assert packet["manual_decision"].eq("hold_for_review").all()
    assert decisions["manual_decision"].eq("hold_for_review").all()
    assert packet["manual_reviewer"].eq("").all()
    assert packet["manual_review_note"].eq("").all()
    assert packet["used_for_signal"].eq(False).all()
    assert packet["used_for_admission"].eq(False).all()
    assert packet["auto_added_to_quality_pool"].eq(False).all()

    required_columns = {
        "stock_code",
        "stock_name",
        "proposed_from_layer",
        "evidence_count",
        "page_citation_count",
        "source_pdf_count",
        "hard_tech_domain",
        "supply_chain_role_hint",
        "business_relevance_hint",
        "bottleneck_or_chokepoint_hint",
        "concept_pollution_risk",
        "route_around_or_substitution_risk",
        "value_capture_risk",
        "disconfirmation_trigger",
        "strongest_primary_source_claim",
        "weakest_or_riskiest_claim",
        "approval_recommendation",
        "approval_reason",
        "manual_decision",
        "manual_reviewer",
        "manual_review_note",
        "used_for_signal",
        "used_for_admission",
        "auto_added_to_quality_pool",
    }
    assert required_columns.issubset(packet.columns)
    assert packet["strongest_primary_source_claim"].astype(str).str.len().gt(0).all()
    assert packet["approval_recommendation"].eq("hold_for_review").all()
    assert packet["approval_reason"].astype(str).str.len().gt(0).all()


def test_quality_pool_layer_v6_manual_approval_deterministic_and_strategy_diff_clean() -> None:
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
