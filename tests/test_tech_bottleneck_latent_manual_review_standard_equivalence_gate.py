from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_latent_manual_review_standard_equivalence_gate.py"
BACKFILL_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_manual_review_standard_backfill_v1"
BACKFILL_SUMMARY = BACKFILL_DIR / "latent_manual_review_standard_backfill_summary.json"
BACKFILL_EVIDENCE = BACKFILL_DIR / "latent_manual_review_standard_backfill_evidence.csv"
BACKFILL_STATUS = BACKFILL_DIR / "latent_manual_review_standard_backfill_stock_status.csv"
BACKFILL_CITATIONS = BACKFILL_DIR / "latent_manual_review_standard_backfill_page_citations.csv"
INPUT_QUEUE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_manual_review_first_triage_v1/latent_manual_review_standard_collection_queue.csv"
)
HIGH_PRIORITY_QUEUE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_manual_review_first_triage_v1/latent_manual_review_high_priority_collection_queue.csv"
)
HUMAN_QUEUE = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_manual_review_first_triage_v1/latent_manual_review_human_confirm_first.csv"
)
QUALITY_POOL_V5 = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v5/quality_pool_layer_v5_manifest.csv"
V6_PROPOSAL = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_quality_pool_layer_v6_proposal_v1/tech_bottleneck_quality_pool_layer_v6_proposal.csv"
)
V6_MANUAL = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_quality_pool_layer_v6_manual_approval_v1/tech_bottleneck_quality_pool_layer_v6_manual_approval_packet.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_manual_review_standard_equivalence_gate_v1"
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


def test_latent_manual_review_standard_equivalence_gate_outputs_and_guardrails() -> None:
    input_hashes_before = {
        "summary": _sha(BACKFILL_SUMMARY),
        "evidence": _sha(BACKFILL_EVIDENCE),
        "status": _sha(BACKFILL_STATUS),
        "citations": _sha(BACKFILL_CITATIONS),
        "queue": _sha(INPUT_QUEUE),
        "quality_pool_v5": _sha(QUALITY_POOL_V5),
        "v6_proposal": _sha(V6_PROPOSAL),
        "v6_manual": _sha(V6_MANUAL),
    }
    _run_generator()
    input_hashes_after = {
        "summary": _sha(BACKFILL_SUMMARY),
        "evidence": _sha(BACKFILL_EVIDENCE),
        "status": _sha(BACKFILL_STATUS),
        "citations": _sha(BACKFILL_CITATIONS),
        "queue": _sha(INPUT_QUEUE),
        "quality_pool_v5": _sha(QUALITY_POOL_V5),
        "v6_proposal": _sha(V6_PROPOSAL),
        "v6_manual": _sha(V6_MANUAL),
    }

    expected = {
        "latent_manual_review_standard_equivalence_gate_summary.json",
        "latent_manual_review_standard_equivalence_gate_decisions.csv",
        "latent_manual_review_standard_equivalence_gate_core_equivalent_proposals.csv",
        "latent_manual_review_standard_equivalence_gate_keep_separate.csv",
        "latent_manual_review_standard_equivalence_gate_human_confirm_required.csv",
        "latent_manual_review_standard_equivalence_gate_downgrade_or_reject.csv",
        "latent_manual_review_standard_equivalence_gate_guardrails.json",
        "tech_bottleneck_latent_manual_review_standard_equivalence_gate_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hashes_before == input_hashes_after

    summary = json.loads(
        (OUTPUT_DIR / "latent_manual_review_standard_equivalence_gate_summary.json").read_text(encoding="utf-8")
    )
    guardrails = json.loads(
        (OUTPUT_DIR / "latent_manual_review_standard_equivalence_gate_guardrails.json").read_text(encoding="utf-8")
    )

    assert summary["research_only"] is True
    assert summary["source_standard_backfill_stock_count"] == 52
    assert summary["processed_stock_count"] == 52
    assert summary["source_primary_source_supported_count"] == 52
    assert summary["source_evidence_rows"] == 1096
    assert summary["source_page_level_citations"] == 1096
    assert (
        summary["core_equivalent_proposal_count"]
        + summary["keep_separate_latent_candidate_count"]
        + summary["human_confirm_required_count"]
        + summary["downgrade_or_reject_count"]
        == 52
    )
    assert summary["core_equivalence_performed"] is True
    assert summary["primary_source_collection_performed"] is False
    assert summary["evidence_backfill_performed"] is False
    assert summary["new_pdf_download_count"] == 0
    assert summary["quality_pool_v5_processed"] is False
    assert summary["quality_pool_v6_proposal_processed"] is False
    assert summary["frozen_quality_pool_v6_generated"] is False
    assert summary["new_quality_pool_layer_generated"] is False
    assert summary["auto_added_to_quality_pool_count"] == 0
    assert summary["price_move_used_for_signal"] == 0
    assert summary["low_position_used_for_signal"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["acceptance_decision"] in {
        "latent_manual_review_standard_equivalence_gate_ready",
        "conditionally_ready_with_human_confirm_needed",
    }

    assert guardrails["research_only"] is True
    assert guardrails["source_standard_backfill_stock_count"] == 52
    assert guardrails["processed_stock_count"] == 52
    assert guardrails["source_primary_source_supported_count"] == 52
    assert guardrails["source_evidence_rows"] == 1096
    assert guardrails["source_page_level_citations"] == 1096
    assert guardrails["core_equivalence_performed"] is True
    assert guardrails["primary_source_collection_performed"] is False
    assert guardrails["evidence_backfill_performed"] is False
    assert guardrails["new_pdf_download_count"] == 0
    assert guardrails["quality_pool_v5_processed"] is False
    assert guardrails["quality_pool_v6_proposal_processed"] is False
    assert guardrails["frozen_quality_pool_v6_generated"] is False
    assert guardrails["new_quality_pool_layer_generated"] is False
    assert guardrails["auto_added_to_quality_pool_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True


def test_latent_manual_review_standard_equivalence_gate_scope_and_integrity() -> None:
    _run_generator()

    queue = pd.read_csv(INPUT_QUEUE, dtype={"stock_code": str})
    high_priority = pd.read_csv(HIGH_PRIORITY_QUEUE, dtype={"stock_code": str})
    human = pd.read_csv(HUMAN_QUEUE, dtype={"stock_code": str})
    quality_pool_v5 = pd.read_csv(QUALITY_POOL_V5, dtype={"stock_code": str})
    v6_proposal = pd.read_csv(V6_PROPOSAL, dtype={"stock_code": str})
    v6_manual = pd.read_csv(V6_MANUAL, dtype={"stock_code": str})
    decisions = pd.read_csv(
        OUTPUT_DIR / "latent_manual_review_standard_equivalence_gate_decisions.csv",
        dtype={"stock_code": str},
    )
    core = pd.read_csv(
        OUTPUT_DIR / "latent_manual_review_standard_equivalence_gate_core_equivalent_proposals.csv",
        dtype={"stock_code": str},
    )
    keep = pd.read_csv(
        OUTPUT_DIR / "latent_manual_review_standard_equivalence_gate_keep_separate.csv",
        dtype={"stock_code": str},
    )
    confirm = pd.read_csv(
        OUTPUT_DIR / "latent_manual_review_standard_equivalence_gate_human_confirm_required.csv",
        dtype={"stock_code": str},
    )
    reject = pd.read_csv(
        OUTPUT_DIR / "latent_manual_review_standard_equivalence_gate_downgrade_or_reject.csv",
        dtype={"stock_code": str},
    )

    expected_codes = set(queue["stock_code"].astype(str).str.zfill(6))
    assert len(decisions) == 52
    assert set(decisions["stock_code"].astype(str).str.zfill(6)) == expected_codes
    assert expected_codes.isdisjoint(set(high_priority["stock_code"].astype(str).str.zfill(6)))
    assert expected_codes.isdisjoint(set(human["stock_code"].astype(str).str.zfill(6)))
    assert expected_codes.isdisjoint(set(quality_pool_v5["stock_code"].astype(str).str.zfill(6)))
    assert expected_codes.isdisjoint(set(v6_proposal["stock_code"].astype(str).str.zfill(6)))
    assert expected_codes.isdisjoint(set(v6_manual["stock_code"].astype(str).str.zfill(6)))
    assert len(core) + len(keep) + len(confirm) + len(reject) == 52
    assert decisions["research_only"].eq(True).all()
    assert decisions["used_for_signal"].eq(False).all()
    assert decisions["used_for_admission"].eq(False).all()
    assert decisions["auto_added_to_quality_pool"].eq(False).all()
    assert decisions["quality_pool_v5_processed"].eq(False).all()
    assert decisions["quality_pool_v6_proposal_processed"].eq(False).all()
    assert decisions["frozen_quality_pool_v6_generated"].eq(False).all()
    assert decisions["new_quality_pool_layer_generated"].eq(False).all()
    assert decisions["price_move_used_for_signal"].eq(False).all()
    assert decisions["low_position_used_for_signal"].eq(False).all()
    assert decisions["equivalence_decision"].notna().all()
    assert decisions["equivalence_reason"].astype(str).str.len().gt(0).all()
    assert set(decisions["equivalence_decision"]).issubset(
        {
            "core_equivalent_proposal",
            "keep_separate_latent_candidate",
            "human_confirm_required",
            "downgrade_or_reject",
        }
    )


def test_latent_manual_review_standard_equivalence_gate_deterministic_and_strategy_diff_clean() -> None:
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
