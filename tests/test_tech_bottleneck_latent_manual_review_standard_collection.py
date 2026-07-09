from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_latent_manual_review_standard_collection.py"
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
TRIAGE_SUMMARY = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_manual_review_first_triage_v1/latent_manual_review_first_triage_summary.json"
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
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_manual_review_standard_collection_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_generator() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT), "--sleep-seconds", "0"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _output_hashes() -> dict[str, str]:
    return {path.name: _sha(path) for path in sorted(OUTPUT_DIR.iterdir()) if path.is_file()}


def test_latent_manual_review_standard_collection_outputs_and_guardrails() -> None:
    input_hashes_before = {
        "standard": _sha(INPUT_QUEUE),
        "high_priority": _sha(HIGH_PRIORITY_QUEUE),
        "human": _sha(HUMAN_QUEUE),
        "triage_summary": _sha(TRIAGE_SUMMARY),
        "v5": _sha(QUALITY_POOL_V5),
        "v6_proposal": _sha(V6_PROPOSAL),
        "v6_manual": _sha(V6_MANUAL),
    }
    _run_generator()
    input_hashes_after = {
        "standard": _sha(INPUT_QUEUE),
        "high_priority": _sha(HIGH_PRIORITY_QUEUE),
        "human": _sha(HUMAN_QUEUE),
        "triage_summary": _sha(TRIAGE_SUMMARY),
        "v5": _sha(QUALITY_POOL_V5),
        "v6_proposal": _sha(V6_PROPOSAL),
        "v6_manual": _sha(V6_MANUAL),
    }

    expected = {
        "latent_manual_review_standard_collection_summary.json",
        "latent_manual_review_standard_collection_sources.csv",
        "latent_manual_review_standard_collection_download_manifest.csv",
        "latent_manual_review_standard_collection_collection_gaps.csv",
        "latent_manual_review_standard_collection_guardrails.json",
        "tech_bottleneck_latent_manual_review_standard_collection_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hashes_before == input_hashes_after

    summary = json.loads((OUTPUT_DIR / "latent_manual_review_standard_collection_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "latent_manual_review_standard_collection_guardrails.json").read_text(encoding="utf-8"))

    assert summary["research_only"] is True
    assert summary["source_standard_collection_queue_count"] == 52
    assert summary["processed_count"] == 52
    assert summary["primary_source_collection_performed"] is True
    assert summary["evidence_backfill_performed"] is False
    assert summary["core_equivalence_performed"] is False
    assert summary["quality_pool_v5_processed"] is False
    assert summary["quality_pool_v6_proposal_processed"] is False
    assert summary["frozen_quality_pool_v6_generated"] is False
    assert summary["auto_added_to_quality_pool_count"] == 0
    assert summary["price_move_used_for_signal"] == 0
    assert summary["low_position_used_for_signal"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["acceptance_decision"] in {
        "latent_manual_review_standard_collection_ready",
        "conditionally_ready_with_collection_gaps",
    }

    assert guardrails["research_only"] is True
    assert guardrails["source_standard_collection_queue_count"] == 52
    assert guardrails["processed_count"] == 52
    assert guardrails["primary_source_collection_performed"] is True
    assert guardrails["evidence_backfill_performed"] is False
    assert guardrails["core_equivalence_performed"] is False
    assert guardrails["quality_pool_v5_processed"] is False
    assert guardrails["quality_pool_v6_proposal_processed"] is False
    assert guardrails["frozen_quality_pool_v6_generated"] is False
    assert guardrails["auto_added_to_quality_pool_count"] == 0
    assert guardrails["price_move_used_for_signal"] == 0
    assert guardrails["low_position_used_for_signal"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True


def test_latent_manual_review_standard_collection_processes_only_standard_52() -> None:
    _run_generator()

    queue = pd.read_csv(INPUT_QUEUE, dtype={"stock_code": str})
    high_priority = pd.read_csv(HIGH_PRIORITY_QUEUE, dtype={"stock_code": str})
    human = pd.read_csv(HUMAN_QUEUE, dtype={"stock_code": str})
    quality_pool_v5 = pd.read_csv(QUALITY_POOL_V5, dtype={"stock_code": str})
    v6_proposal = pd.read_csv(V6_PROPOSAL, dtype={"stock_code": str})
    sources = pd.read_csv(OUTPUT_DIR / "latent_manual_review_standard_collection_sources.csv", dtype={"stock_code": str})
    downloads = pd.read_csv(
        OUTPUT_DIR / "latent_manual_review_standard_collection_download_manifest.csv",
        dtype={"stock_code": str},
    )
    gaps = pd.read_csv(
        OUTPUT_DIR / "latent_manual_review_standard_collection_collection_gaps.csv",
        dtype={"stock_code": str},
    )

    expected_codes = set(queue["stock_code"].astype(str).str.zfill(6))
    assert len(queue) == 52
    if not sources.empty:
        assert set(sources["stock_code"].astype(str).str.zfill(6)).issubset(expected_codes)
        assert sources["is_primary_source"].eq(True).all()
        assert sources["used_for_signal"].eq(False).all()
        assert sources["used_for_admission"].eq(False).all()
        assert sources["local_pdf_path"].astype(str).str.endswith(".pdf").all()
    if not downloads.empty:
        assert set(downloads["stock_code"].astype(str).str.zfill(6)).issubset(expected_codes)
    if not gaps.empty:
        assert set(gaps["stock_code"].astype(str).str.zfill(6)).issubset(expected_codes)
    assert expected_codes.isdisjoint(set(high_priority["stock_code"].astype(str).str.zfill(6)))
    assert expected_codes.isdisjoint(set(human["stock_code"].astype(str).str.zfill(6)))
    assert expected_codes.isdisjoint(set(quality_pool_v5["stock_code"].astype(str).str.zfill(6)))
    assert expected_codes.isdisjoint(set(v6_proposal["stock_code"].astype(str).str.zfill(6)))


def test_latent_manual_review_standard_collection_deterministic_and_strategy_diff_clean() -> None:
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
