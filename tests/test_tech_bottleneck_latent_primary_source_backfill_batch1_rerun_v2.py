from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_latent_primary_source_backfill_batch1_rerun_v2.py"
INPUT_QUEUE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_primary_source_backfill_batch1_v1/latent_backfill_batch1_remain_pending.csv"
)
COLLECTION_MANIFEST = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_pending_primary_source_collection_v1/latent_pending_primary_source_collection_manifest.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_primary_source_backfill_batch1_rerun_v2"
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


def test_latent_primary_source_backfill_batch1_rerun_v2_outputs_and_guardrails() -> None:
    queue_hash_before = _sha(INPUT_QUEUE)
    manifest_hash_before = _sha(COLLECTION_MANIFEST)
    _run_generator()
    queue_hash_after = _sha(INPUT_QUEUE)
    manifest_hash_after = _sha(COLLECTION_MANIFEST)

    expected = {
        "latent_backfill_batch1_rerun_v2_summary.json",
        "latent_backfill_batch1_rerun_v2_results.csv",
        "latent_backfill_batch1_rerun_v2_evidence_matrix.csv",
        "latent_backfill_batch1_rerun_v2_gap_matrix.csv",
        "latent_backfill_batch1_rerun_v2_manual_approval_candidates.csv",
        "latent_backfill_batch1_rerun_v2_remain_pending.csv",
        "latent_backfill_batch1_rerun_v2_adjacent_or_reject.csv",
        "latent_backfill_batch1_rerun_v2_guardrails.json",
        "tech_bottleneck_latent_primary_source_backfill_batch1_rerun_v2_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert queue_hash_before == queue_hash_after
    assert manifest_hash_before == manifest_hash_after

    summary = json.loads((OUTPUT_DIR / "latent_backfill_batch1_rerun_v2_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "latent_backfill_batch1_rerun_v2_guardrails.json").read_text(encoding="utf-8"))

    assert summary["source_latent_pending_count"] == 45
    assert summary["processed_count"] == 45
    assert summary["collection_pdf_count"] == 135
    assert (
        summary["upgrade_count"]
        + summary["remain_pending_count"]
        + summary["adjacent_count"]
        + summary["downgrade_or_reject_count"]
        == 45
    )
    assert summary["core_equivalence_performed"] is False
    assert summary["auto_added_to_quality_pool_count"] == 0
    assert summary["price_move_used_for_signal"] == 0
    assert summary["low_position_used_for_signal"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["acceptance_decision"] in {
        "latent_primary_source_backfill_batch1_rerun_v2_ready",
        "conditionally_ready_with_remaining_gaps",
    }

    assert guardrails["research_only"] is True
    assert guardrails["source_latent_pending_count"] == 45
    assert guardrails["processed_count"] == 45
    assert guardrails["collection_pdf_count"] == 135
    assert guardrails["core_equivalence_performed"] is False
    assert guardrails["auto_added_to_quality_pool_count"] == 0
    assert guardrails["price_move_used_for_signal"] == 0
    assert guardrails["low_position_used_for_signal"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True


def test_latent_primary_source_backfill_batch1_rerun_v2_processes_only_45_rows() -> None:
    _run_generator()

    queue = pd.read_csv(INPUT_QUEUE, dtype={"stock_code": str})
    results = pd.read_csv(OUTPUT_DIR / "latent_backfill_batch1_rerun_v2_results.csv", dtype={"stock_code": str})
    evidence = pd.read_csv(OUTPUT_DIR / "latent_backfill_batch1_rerun_v2_evidence_matrix.csv", dtype={"stock_code": str})
    gaps = pd.read_csv(OUTPUT_DIR / "latent_backfill_batch1_rerun_v2_gap_matrix.csv", dtype={"stock_code": str})
    manual = pd.read_csv(OUTPUT_DIR / "latent_backfill_batch1_rerun_v2_manual_approval_candidates.csv", dtype={"stock_code": str})
    pending = pd.read_csv(OUTPUT_DIR / "latent_backfill_batch1_rerun_v2_remain_pending.csv", dtype={"stock_code": str})
    adjacent = pd.read_csv(OUTPUT_DIR / "latent_backfill_batch1_rerun_v2_adjacent_or_reject.csv", dtype={"stock_code": str})

    assert len(results) == 45
    assert set(results["stock_code"]) == set(queue["stock_code"].astype(str).str.zfill(6))
    assert set(evidence["stock_code"]) == set(results["stock_code"])
    assert set(gaps["stock_code"]) == set(results["stock_code"])
    assert len(manual) + len(pending) + len(adjacent) == 45
    assert results["recommended_backfill_decision"].notna().all()
    assert results["recommended_manual_review_entry_class"].notna().all()
    assert results["research_only"].eq(True).all()
    assert results["used_for_signal"].eq(False).all()
    assert results["used_for_admission"].eq(False).all()
    assert set(results["recommended_backfill_decision"]).issubset(
        {
            "upgrade_to_latent_manual_approval_candidate",
            "remain_latent_pending_evidence",
            "move_to_adjacent_watchlist",
            "downgrade_or_reject",
        }
    )
    assert set(results["recommended_manual_review_entry_class"]).issubset(
        {
            "latent_manual_approval_candidate",
            "latent_pending_evidence",
            "adjacent_watchlist",
            "downgrade_or_reject",
        }
    )
    assert evidence["is_primary_source"].eq(True).all()
    assert evidence["provenance_status"].isin(["page_level", "source_level"]).all()


def test_latent_primary_source_backfill_batch1_rerun_v2_deterministic_and_strategy_diff_clean() -> None:
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
