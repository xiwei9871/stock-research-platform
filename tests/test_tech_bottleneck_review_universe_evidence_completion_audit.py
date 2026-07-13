from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_review_universe_evidence_completion_audit.py"
V5_MANIFEST = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v5/quality_pool_layer_v5_manifest.csv"
V7_PROPOSAL = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v7_proposal_v1/tech_bottleneck_quality_pool_layer_v7_proposal.csv"
)
V7_INGEST = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_quality_pool_layer_v7_manual_approval_ingest_v1/v7_manual_approval_ledger.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_review_universe_evidence_completion_audit_v1"
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


def test_review_universe_evidence_completion_audit_outputs_and_guardrails() -> None:
    input_hashes_before = {
        "v5": _sha(V5_MANIFEST),
        "v7_proposal": _sha(V7_PROPOSAL),
        "v7_ingest": _sha(V7_INGEST),
    }
    _run_generator()
    input_hashes_after = {
        "v5": _sha(V5_MANIFEST),
        "v7_proposal": _sha(V7_PROPOSAL),
        "v7_ingest": _sha(V7_INGEST),
    }

    expected = {
        "tech_bottleneck_review_universe_v1.csv",
        "tech_bottleneck_review_universe_evidence_completion_summary.json",
        "tech_bottleneck_review_universe_evidence_completion_audit.csv",
        "tech_bottleneck_review_universe_evidence_gap_queue.csv",
        "tech_bottleneck_review_universe_frontend_ready.csv",
        "tech_bottleneck_review_universe_evidence_completion_guardrails.json",
        "tech_bottleneck_review_universe_evidence_completion_audit_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hashes_before == input_hashes_after

    summary = json.loads(
        (OUTPUT_DIR / "tech_bottleneck_review_universe_evidence_completion_summary.json").read_text(encoding="utf-8")
    )
    guardrails = json.loads(
        (OUTPUT_DIR / "tech_bottleneck_review_universe_evidence_completion_guardrails.json").read_text(encoding="utf-8")
    )

    assert summary["quality_pool_v5_reference_count"] == 300
    assert summary["v7_proposal_new_candidate_count"] == 78
    assert summary["review_universe_total_count"] == 378
    assert summary["duplicate_stock_count"] == 0
    assert summary["primary_source_collection_performed"] is False
    assert summary["evidence_backfill_performed"] is False
    assert summary["core_equivalence_performed"] is False
    assert summary["frozen_quality_pool_generated"] is False
    assert summary["frontend_write_performed"] is False
    assert summary["auto_added_to_quality_pool_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["price_move_used_for_signal"] == 0
    assert summary["low_position_used_for_signal"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["acceptance_decision"] in {
        "tech_bottleneck_review_universe_evidence_completion_audit_ready",
        "conditionally_ready_with_evidence_gaps",
    }

    assert guardrails["quality_pool_v5_reference_count"] == 300
    assert guardrails["v7_proposal_new_candidate_count"] == 78
    assert guardrails["review_universe_total_count"] == 378
    assert guardrails["frozen_quality_pool_generated"] is False
    assert guardrails["frontend_write_performed"] is False
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0


def test_review_universe_evidence_completion_audit_universe_layers_and_fields() -> None:
    _run_generator()

    universe = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_review_universe_v1.csv", dtype={"stock_code": str}).fillna("")
    audit = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_review_universe_evidence_completion_audit.csv",
        dtype={"stock_code": str},
    ).fillna("")
    gap_queue = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_review_universe_evidence_gap_queue.csv",
        dtype={"stock_code": str},
    ).fillna("")
    frontend_ready = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_review_universe_frontend_ready.csv",
        dtype={"stock_code": str},
    ).fillna("")

    assert len(universe) == 378
    assert universe["stock_code"].nunique() == 378
    assert universe["review_universe_source"].value_counts().to_dict() == {
        "v5_existing": 300,
        "v7_pending_from_standard": 52,
        "v6_hold_from_high_priority": 26,
    }
    assert len(audit) == 378
    assert set(audit["stock_code"]) == set(universe["stock_code"])
    assert set(audit["evidence_completion_status"]).issubset(
        {
            "frontend_ready",
            "evidence_light_but_usable",
            "needs_evidence_backfill",
            "needs_role_confirmation",
            "needs_external_check",
            "insufficient_for_review",
        }
    )

    required_columns = {
        "stock_code",
        "stock_name",
        "review_universe_source",
        "current_layer_status",
        "manual_approval_status",
        "evidence_count",
        "page_citation_count",
        "source_pdf_count",
        "primary_source_supported",
        "hard_tech_domain",
        "supply_chain_role_hint",
        "business_relevance_hint",
        "bottleneck_or_chokepoint_hint",
        "concept_pollution_risk",
        "route_around_or_substitution_risk",
        "value_capture_risk",
        "disconfirmation_trigger",
        "next_primary_source_to_check",
        "evidence_completion_status",
        "frontend_ready",
        "recommended_next_action",
        "used_for_signal",
        "used_for_admission",
        "auto_added_to_quality_pool",
    }
    assert required_columns.issubset(audit.columns)
    assert audit["used_for_signal"].eq(False).all()
    assert audit["used_for_admission"].eq(False).all()
    assert audit["auto_added_to_quality_pool"].eq(False).all()
    assert len(gap_queue) + len(frontend_ready) == 378
    if not frontend_ready.empty:
        assert frontend_ready["frontend_ready"].eq(True).all()
    if not gap_queue.empty:
        assert gap_queue["frontend_ready"].eq(False).all()


def test_review_universe_evidence_completion_audit_deterministic_and_strategy_diff_clean() -> None:
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
