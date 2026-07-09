from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_quality_pool_layer_v7_proposal.py"
V5_MANIFEST = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v5/quality_pool_layer_v5_manifest.csv"
V6_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v6_proposal_v1"
V6_PROPOSAL = V6_DIR / "tech_bottleneck_quality_pool_layer_v6_proposal.csv"
V6_SUMMARY = V6_DIR / "tech_bottleneck_quality_pool_layer_v6_proposal_summary.json"
V6_MANUAL_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v6_manual_approval_v1"
V6_MANUAL_DECISIONS = V6_MANUAL_DIR / "tech_bottleneck_quality_pool_layer_v6_manual_approval_decisions.csv"
V6_MANUAL_PACKET = V6_MANUAL_DIR / "tech_bottleneck_quality_pool_layer_v6_manual_approval_packet.csv"
GATE_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_manual_review_standard_equivalence_gate_v1"
GATE_SUMMARY = GATE_DIR / "latent_manual_review_standard_equivalence_gate_summary.json"
GATE_DECISIONS = GATE_DIR / "latent_manual_review_standard_equivalence_gate_decisions.csv"
GATE_CORE = GATE_DIR / "latent_manual_review_standard_equivalence_gate_core_equivalent_proposals.csv"
BACKFILL_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_manual_review_standard_backfill_v1"
BACKFILL_EVIDENCE = BACKFILL_DIR / "latent_manual_review_standard_backfill_evidence.csv"
BACKFILL_CITATIONS = BACKFILL_DIR / "latent_manual_review_standard_backfill_page_citations.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v7_proposal_v1"
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


def test_quality_pool_layer_v7_proposal_outputs_and_guardrails() -> None:
    input_hashes_before = {
        "v5": _sha(V5_MANIFEST),
        "v6_summary": _sha(V6_SUMMARY),
        "v6_proposal": _sha(V6_PROPOSAL),
        "v6_manual_decisions": _sha(V6_MANUAL_DECISIONS),
        "v6_manual_packet": _sha(V6_MANUAL_PACKET),
        "gate_summary": _sha(GATE_SUMMARY),
        "gate_decisions": _sha(GATE_DECISIONS),
        "gate_core": _sha(GATE_CORE),
        "backfill_evidence": _sha(BACKFILL_EVIDENCE),
        "backfill_citations": _sha(BACKFILL_CITATIONS),
    }
    _run_generator()
    input_hashes_after = {
        "v5": _sha(V5_MANIFEST),
        "v6_summary": _sha(V6_SUMMARY),
        "v6_proposal": _sha(V6_PROPOSAL),
        "v6_manual_decisions": _sha(V6_MANUAL_DECISIONS),
        "v6_manual_packet": _sha(V6_MANUAL_PACKET),
        "gate_summary": _sha(GATE_SUMMARY),
        "gate_decisions": _sha(GATE_DECISIONS),
        "gate_core": _sha(GATE_CORE),
        "backfill_evidence": _sha(BACKFILL_EVIDENCE),
        "backfill_citations": _sha(BACKFILL_CITATIONS),
    }

    expected = {
        "tech_bottleneck_quality_pool_layer_v7_proposal_summary.json",
        "tech_bottleneck_quality_pool_layer_v7_proposal.csv",
        "tech_bottleneck_quality_pool_layer_v7_added_from_standard.csv",
        "tech_bottleneck_quality_pool_layer_v7_duplicate_check.csv",
        "tech_bottleneck_quality_pool_layer_v7_evidence_index.csv",
        "tech_bottleneck_quality_pool_layer_v7_guardrails.json",
        "tech_bottleneck_quality_pool_layer_v7_proposal_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hashes_before == input_hashes_after

    summary = json.loads(
        (OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v7_proposal_summary.json").read_text(encoding="utf-8")
    )
    guardrails = json.loads(
        (OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v7_guardrails.json").read_text(encoding="utf-8")
    )

    assert summary["research_only"] is True
    assert summary["quality_pool_v5_reference_count"] == 300
    assert summary["quality_pool_v6_proposal_reference_count"] == 326
    assert summary["v6_manual_approved_count"] == 0
    assert summary["v6_hold_for_review_count"] == 26
    assert summary["source_standard_core_equivalent_proposal_count"] == 52
    assert summary["processed_standard_core_equivalent_proposal_count"] == 52
    assert summary["duplicate_stock_count"] == 0
    assert summary["proposed_addition_count"] == 52
    assert summary["proposed_quality_pool_v7_count"] == 378
    assert summary["primary_source_collection_performed"] is False
    assert summary["evidence_backfill_performed"] is False
    assert summary["core_equivalence_performed"] is False
    assert summary["quality_pool_v7_is_proposal_only"] is True
    assert summary["frozen_quality_pool_v6_generated"] is False
    assert summary["frozen_quality_pool_v7_generated"] is False
    assert summary["auto_added_to_quality_pool_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["price_move_used_for_signal"] == 0
    assert summary["low_position_used_for_signal"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["acceptance_decision"] == "quality_pool_layer_v7_proposal_ready"

    assert guardrails["quality_pool_v5_reference_count"] == 300
    assert guardrails["quality_pool_v6_proposal_reference_count"] == 326
    assert guardrails["v6_manual_approved_count"] == 0
    assert guardrails["v6_hold_for_review_count"] == 26
    assert guardrails["source_standard_core_equivalent_proposal_count"] == 52
    assert guardrails["proposed_quality_pool_v7_count"] == 378
    assert guardrails["quality_pool_v7_is_proposal_only"] is True
    assert guardrails["frozen_quality_pool_v6_generated"] is False
    assert guardrails["frozen_quality_pool_v7_generated"] is False
    assert guardrails["auto_added_to_quality_pool_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True


def test_quality_pool_layer_v7_proposal_manifest_added_rows_and_hold_state() -> None:
    _run_generator()

    v5 = pd.read_csv(V5_MANIFEST, dtype={"stock_code": str})
    v6 = pd.read_csv(V6_PROPOSAL, dtype={"stock_code": str})
    v6_manual = pd.read_csv(V6_MANUAL_DECISIONS, dtype={"stock_code": str})
    gate_core = pd.read_csv(GATE_CORE, dtype={"stock_code": str})
    proposal = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v7_proposal.csv", dtype={"stock_code": str})
    added = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v7_added_from_standard.csv", dtype={"stock_code": str})
    duplicate = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v7_duplicate_check.csv", dtype={"stock_code": str})
    evidence_index = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_quality_pool_layer_v7_evidence_index.csv",
        dtype={"stock_code": str},
    )

    assert len(v5) == 300
    assert len(v6) == 326
    assert len(v6_manual) == 26
    assert v6_manual["manual_decision"].eq("hold_for_review").all()
    assert len(gate_core) == 52
    assert len(proposal) == 378
    assert proposal["stock_code"].nunique() == 378
    assert set(v6["stock_code"].astype(str).str.zfill(6)).issubset(set(proposal["stock_code"].astype(str).str.zfill(6)))
    assert set(gate_core["stock_code"].astype(str).str.zfill(6)).issubset(
        set(proposal["stock_code"].astype(str).str.zfill(6))
    )
    assert len(added) == 52
    assert set(added["stock_code"].astype(str).str.zfill(6)) == set(gate_core["stock_code"].astype(str).str.zfill(6))
    assert duplicate.empty
    assert not evidence_index.empty
    assert set(evidence_index["stock_code"].astype(str).str.zfill(6)).issubset(
        set(added["stock_code"].astype(str).str.zfill(6))
    )

    required_added_columns = {
        "stock_code",
        "stock_name",
        "source_layer",
        "v7_proposal_status",
        "added_from",
        "evidence_count",
        "page_citation_count",
        "source_pdf_count",
        "primary_source_supported",
        "equivalence_decision",
        "hard_tech_domain",
        "supply_chain_role_hint",
        "business_relevance_hint",
        "bottleneck_or_chokepoint_hint",
        "concept_pollution_risk",
        "next_action_hint",
        "used_for_signal",
        "used_for_admission",
        "auto_added_to_quality_pool",
    }
    assert required_added_columns.issubset(added.columns)
    assert added["source_layer"].eq("latent_manual_review_standard_core_equivalent_proposal").all()
    assert added["v7_proposal_status"].eq("proposed_standard_addition_only").all()
    assert added["added_from"].eq("latent_manual_review_standard_equivalence_gate_v1").all()
    assert added["equivalence_decision"].eq("core_equivalent_proposal").all()
    assert added["primary_source_supported"].eq(True).all()
    assert added["used_for_signal"].eq(False).all()
    assert added["used_for_admission"].eq(False).all()
    assert added["auto_added_to_quality_pool"].eq(False).all()
    assert added["evidence_count"].ge(1).all()
    assert added["page_citation_count"].ge(1).all()
    assert added["source_pdf_count"].ge(1).all()
    assert proposal["research_only"].eq(True).all()
    assert proposal["used_for_signal"].eq(False).all()
    assert proposal["used_for_admission"].eq(False).all()
    assert proposal["auto_added_to_quality_pool"].eq(False).all()
    assert proposal["quality_pool_v7_is_proposal_only"].eq(True).all()


def test_quality_pool_layer_v7_proposal_deterministic_and_strategy_diff_clean() -> None:
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
