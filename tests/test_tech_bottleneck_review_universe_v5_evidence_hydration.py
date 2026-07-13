from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_review_universe_v5_evidence_hydration.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_review_universe_v5_evidence_hydration_v1"
AUDIT_UNIVERSE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_evidence_completion_audit_v1/tech_bottleneck_review_universe_v1.csv"
)
AUDIT_GAP_QUEUE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_evidence_completion_audit_v1/tech_bottleneck_review_universe_evidence_gap_queue.csv"
)
V5_MANIFEST = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v5/quality_pool_layer_v5_manifest.csv"
V7_PROPOSAL = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v7_proposal_v1/tech_bottleneck_quality_pool_layer_v7_proposal.csv"
)
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


def test_v5_evidence_hydration_outputs_summary_and_guardrails() -> None:
    input_hashes_before = {
        "audit_universe": _sha(AUDIT_UNIVERSE),
        "audit_gap_queue": _sha(AUDIT_GAP_QUEUE),
        "v5_manifest": _sha(V5_MANIFEST),
        "v7_proposal": _sha(V7_PROPOSAL),
    }
    _run_generator()
    input_hashes_after = {
        "audit_universe": _sha(AUDIT_UNIVERSE),
        "audit_gap_queue": _sha(AUDIT_GAP_QUEUE),
        "v5_manifest": _sha(V5_MANIFEST),
        "v7_proposal": _sha(V7_PROPOSAL),
    }

    expected = {
        "tech_bottleneck_review_universe_v5_evidence_hydration_summary.json",
        "tech_bottleneck_review_universe_v5_evidence_hydrated.csv",
        "tech_bottleneck_review_universe_v5_evidence_index.csv",
        "tech_bottleneck_review_universe_v5_hydrated_frontend_ready.csv",
        "tech_bottleneck_review_universe_v5_remaining_gap_queue.csv",
        "tech_bottleneck_review_universe_v5_missing_source_directories.json",
        "tech_bottleneck_review_universe_v5_evidence_hydration_guardrails.json",
        "tech_bottleneck_review_universe_v5_evidence_hydration_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hashes_before == input_hashes_after

    summary = json.loads(
        (OUTPUT_DIR / "tech_bottleneck_review_universe_v5_evidence_hydration_summary.json").read_text(encoding="utf-8")
    )
    guardrails = json.loads(
        (OUTPUT_DIR / "tech_bottleneck_review_universe_v5_evidence_hydration_guardrails.json").read_text(encoding="utf-8")
    )

    assert summary["review_universe_total_count"] == 378
    assert summary["source_evidence_gap_queue_count"] == 300
    assert summary["processed_v5_gap_count"] == 300
    assert summary["v7_frontend_ready_reference_count"] == 78
    assert summary["duplicate_stock_count"] == 0
    assert summary["primary_source_collection_performed"] is False
    assert summary["new_pdf_download_count"] == 0
    assert summary["evidence_hydration_performed"] is True
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
        "tech_bottleneck_review_universe_v5_evidence_hydration_ready",
        "conditionally_ready_with_remaining_gaps",
    }
    assert guardrails["processed_v5_gap_count"] == 300
    assert guardrails["evidence_hydration_performed"] is True
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0


def test_v5_evidence_hydration_processes_only_v5_and_normalizes_fields() -> None:
    _run_generator()

    hydrated = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_review_universe_v5_evidence_hydrated.csv",
        dtype={"stock_code": str},
    ).fillna("")
    index = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_review_universe_v5_evidence_index.csv",
        dtype={"stock_code": str},
    ).fillna("")
    frontend_ready = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_review_universe_v5_hydrated_frontend_ready.csv",
        dtype={"stock_code": str},
    ).fillna("")
    remaining = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_review_universe_v5_remaining_gap_queue.csv",
        dtype={"stock_code": str},
    ).fillna("")

    assert len(hydrated) == 300
    assert hydrated["stock_code"].nunique() == 300
    assert set(hydrated["review_universe_source"]) == {"v5_existing"}
    assert len(frontend_ready) + len(remaining) == 300
    assert set(index["stock_code"]).issubset(set(hydrated["stock_code"]))
    assert len(index) > 0

    expected_columns = {
        "stock_code",
        "stock_name",
        "review_universe_source",
        "hydration_status",
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
        "strongest_primary_source_claim",
        "weakest_or_riskiest_claim",
        "used_for_signal",
        "used_for_admission",
        "auto_added_to_quality_pool",
    }
    assert expected_columns.issubset(hydrated.columns)
    assert set(hydrated["hydration_status"]).issubset(
        {
            "hydrated_frontend_ready",
            "hydrated_evidence_light_but_usable",
            "remaining_needs_targeted_collection",
            "remaining_needs_manual_source_mapping",
            "insufficient_existing_artifacts",
        }
    )
    assert hydrated["used_for_signal"].eq(False).all()
    assert hydrated["used_for_admission"].eq(False).all()
    assert hydrated["auto_added_to_quality_pool"].eq(False).all()
    assert hydrated["evidence_count"].astype(int).ge(0).all()
    assert hydrated["page_citation_count"].astype(int).ge(0).all()
    assert hydrated["source_pdf_count"].astype(int).ge(0).all()


def test_v5_evidence_hydration_missing_directories_and_determinism() -> None:
    _run_generator()
    first = _output_hashes()
    _run_generator()
    second = _output_hashes()
    assert first == second

    missing = json.loads(
        (OUTPUT_DIR / "tech_bottleneck_review_universe_v5_missing_source_directories.json").read_text(encoding="utf-8")
    )
    assert "missing_source_directories" in missing
    assert isinstance(missing["missing_source_directories"], list)

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
