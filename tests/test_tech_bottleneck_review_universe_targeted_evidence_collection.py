from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_review_universe_targeted_evidence_collection.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_review_universe_targeted_evidence_collection_v1"
REMAINING_GAP = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_v5_evidence_hydration_v1/tech_bottleneck_review_universe_v5_remaining_gap_queue.csv"
)
HYDRATED = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_v5_evidence_hydration_v1/tech_bottleneck_review_universe_v5_evidence_hydrated.csv"
)
AUDIT_UNIVERSE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_evidence_completion_audit_v1/tech_bottleneck_review_universe_v1.csv"
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


def test_targeted_evidence_collection_outputs_and_guardrails() -> None:
    input_hashes_before = {
        "remaining_gap": _sha(REMAINING_GAP),
        "hydrated": _sha(HYDRATED),
        "audit_universe": _sha(AUDIT_UNIVERSE),
        "v5_manifest": _sha(V5_MANIFEST),
        "v7_proposal": _sha(V7_PROPOSAL),
    }
    _run_generator()
    input_hashes_after = {
        "remaining_gap": _sha(REMAINING_GAP),
        "hydrated": _sha(HYDRATED),
        "audit_universe": _sha(AUDIT_UNIVERSE),
        "v5_manifest": _sha(V5_MANIFEST),
        "v7_proposal": _sha(V7_PROPOSAL),
    }

    expected = {
        "tech_bottleneck_review_universe_targeted_evidence_collection_summary.json",
        "tech_bottleneck_review_universe_targeted_evidence_sources.csv",
        "tech_bottleneck_review_universe_targeted_evidence_download_manifest.csv",
        "tech_bottleneck_review_universe_targeted_evidence_index.csv",
        "tech_bottleneck_review_universe_targeted_evidence_frontend_ready.csv",
        "tech_bottleneck_review_universe_targeted_evidence_remaining_gaps.csv",
        "tech_bottleneck_review_universe_targeted_evidence_guardrails.json",
        "tech_bottleneck_review_universe_targeted_evidence_collection_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hashes_before == input_hashes_after

    summary = json.loads(
        (OUTPUT_DIR / "tech_bottleneck_review_universe_targeted_evidence_collection_summary.json").read_text(
            encoding="utf-8"
        )
    )
    guardrails = json.loads(
        (OUTPUT_DIR / "tech_bottleneck_review_universe_targeted_evidence_guardrails.json").read_text(encoding="utf-8")
    )
    assert summary["review_universe_total_count"] == 378
    assert summary["source_remaining_gap_count"] == 29
    assert summary["processed_remaining_gap_count"] == 29
    assert summary["existing_hydrated_frontend_ready_count"] == 271
    assert summary["v7_frontend_ready_reference_count"] == 78
    assert summary["targeted_frontend_ready_count"] == 29
    assert summary["remaining_gap_count"] == 0
    assert summary["core_equivalence_performed"] is False
    assert summary["frozen_quality_pool_generated"] is False
    assert summary["frontend_write_performed"] is False
    assert summary["auto_added_to_quality_pool_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["price_move_used_for_signal"] == 0
    assert summary["low_position_used_for_signal"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["acceptance_decision"] == "tech_bottleneck_review_universe_targeted_evidence_collection_ready"
    assert guardrails["processed_remaining_gap_count"] == 29
    assert guardrails["frontend_write_performed"] is False
    assert guardrails["used_for_signal_count"] == 0


def test_targeted_evidence_collection_processes_only_remaining_gap_and_maps_sources() -> None:
    _run_generator()
    sources = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_review_universe_targeted_evidence_sources.csv",
        dtype={"stock_code": str},
    ).fillna("")
    manifest = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_review_universe_targeted_evidence_download_manifest.csv",
        dtype={"stock_code": str},
    ).fillna("")
    index = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_review_universe_targeted_evidence_index.csv",
        dtype={"stock_code": str},
    ).fillna("")
    frontend_ready = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_review_universe_targeted_evidence_frontend_ready.csv",
        dtype={"stock_code": str},
    ).fillna("")
    remaining = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_review_universe_targeted_evidence_remaining_gaps.csv",
        dtype={"stock_code": str},
    ).fillna("")

    assert sources["stock_code"].nunique() == 29
    assert manifest["stock_code"].nunique() == 29
    assert index["stock_code"].nunique() == 29
    assert len(frontend_ready) == 29
    assert remaining.empty
    assert set(frontend_ready["targeted_evidence_status"]) == {"targeted_frontend_ready"}
    assert frontend_ready["source_pdf_count"].astype(int).gt(0).all()
    assert frontend_ready["page_citation_count"].astype(int).gt(0).all()
    assert frontend_ready["used_for_signal"].eq(False).all()
    assert frontend_ready["used_for_admission"].eq(False).all()
    assert set(manifest["download_status"]) == {"existing_artifact_reused"}
    assert set(manifest["new_pdf_downloaded"]) == {False}


def test_targeted_evidence_collection_deterministic_and_strategy_diff_clean() -> None:
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
