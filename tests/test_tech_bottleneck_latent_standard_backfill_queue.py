from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_latent_standard_backfill_queue.py"
INPUT_QUEUE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_candidate_discovery_quality_audit_v1/latent_standard_backfill_queue.csv"
)
HIGH_PRIORITY = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_candidate_discovery_quality_audit_v1/latent_high_priority_backfill_queue.csv"
)
MANUAL_REVIEW_FIRST = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_candidate_discovery_quality_audit_v1/latent_manual_review_first.csv"
)
DEFER_REJECT = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_candidate_discovery_quality_audit_v1/latent_defer_or_reject.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_standard_backfill_queue_v1"
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


def test_latent_standard_backfill_queue_outputs_and_guardrails() -> None:
    input_hashes_before = {
        "standard": _sha(INPUT_QUEUE),
        "high_priority": _sha(HIGH_PRIORITY),
        "manual_review_first": _sha(MANUAL_REVIEW_FIRST),
        "defer_reject": _sha(DEFER_REJECT),
    }
    _run_generator()
    input_hashes_after = {
        "standard": _sha(INPUT_QUEUE),
        "high_priority": _sha(HIGH_PRIORITY),
        "manual_review_first": _sha(MANUAL_REVIEW_FIRST),
        "defer_reject": _sha(DEFER_REJECT),
    }

    expected = {
        "latent_standard_backfill_summary.json",
        "latent_standard_backfill_results.csv",
        "latent_standard_evidence_matrix.csv",
        "latent_standard_gap_matrix.csv",
        "latent_standard_manual_approval_candidates.csv",
        "latent_standard_remain_pending.csv",
        "latent_standard_adjacent_or_reject.csv",
        "latent_standard_backfill_guardrails.json",
        "tech_bottleneck_latent_standard_backfill_queue_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hashes_before == input_hashes_after

    summary = json.loads((OUTPUT_DIR / "latent_standard_backfill_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "latent_standard_backfill_guardrails.json").read_text(encoding="utf-8"))

    assert summary["source_latent_standard_backfill_count"] == 24
    assert summary["processed_count"] == 24
    assert (
        summary["upgrade_count"]
        + summary["remain_pending_count"]
        + summary["adjacent_count"]
        + summary["downgrade_or_reject_count"]
        == 24
    )
    assert summary["high_priority_processed"] is False
    assert summary["manual_review_first_processed"] is False
    assert summary["defer_reject_processed"] is False
    assert summary["core_equivalence_performed"] is False
    assert summary["auto_added_to_quality_pool_count"] == 0
    assert summary["price_move_used_for_signal"] == 0
    assert summary["low_position_used_for_signal"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["acceptance_decision"] in {
        "latent_standard_backfill_queue_ready",
        "conditionally_ready_with_remaining_gaps",
    }

    assert guardrails["research_only"] is True
    assert guardrails["source_latent_standard_backfill_count"] == 24
    assert guardrails["processed_count"] == 24
    assert guardrails["high_priority_processed"] is False
    assert guardrails["manual_review_first_processed"] is False
    assert guardrails["defer_reject_processed"] is False
    assert guardrails["core_equivalence_performed"] is False
    assert guardrails["auto_added_to_quality_pool_count"] == 0
    assert guardrails["price_move_used_for_signal"] == 0
    assert guardrails["low_position_used_for_signal"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True


def test_latent_standard_backfill_queue_processes_only_standard_24() -> None:
    _run_generator()

    queue = pd.read_csv(INPUT_QUEUE, dtype={"stock_code": str})
    high_priority = pd.read_csv(HIGH_PRIORITY, dtype={"stock_code": str})
    manual_first = pd.read_csv(MANUAL_REVIEW_FIRST, dtype={"stock_code": str})
    defer_reject = pd.read_csv(DEFER_REJECT, dtype={"stock_code": str})
    results = pd.read_csv(OUTPUT_DIR / "latent_standard_backfill_results.csv", dtype={"stock_code": str})
    evidence = pd.read_csv(OUTPUT_DIR / "latent_standard_evidence_matrix.csv", dtype={"stock_code": str})
    gaps = pd.read_csv(OUTPUT_DIR / "latent_standard_gap_matrix.csv", dtype={"stock_code": str})
    manual = pd.read_csv(OUTPUT_DIR / "latent_standard_manual_approval_candidates.csv", dtype={"stock_code": str})
    pending = pd.read_csv(OUTPUT_DIR / "latent_standard_remain_pending.csv", dtype={"stock_code": str})
    adjacent = pd.read_csv(OUTPUT_DIR / "latent_standard_adjacent_or_reject.csv", dtype={"stock_code": str})

    expected_codes = set(queue["stock_code"].astype(str).str.zfill(6))
    assert len(results) == 24
    assert set(results["stock_code"]) == expected_codes
    assert set(results["stock_code"]).isdisjoint(set(high_priority["stock_code"].astype(str).str.zfill(6)))
    assert set(results["stock_code"]).isdisjoint(set(manual_first["stock_code"].astype(str).str.zfill(6)))
    assert set(results["stock_code"]).isdisjoint(set(defer_reject["stock_code"].astype(str).str.zfill(6)))
    assert set(gaps["stock_code"]) == expected_codes
    if not evidence.empty:
        assert set(evidence["stock_code"]).issubset(expected_codes)
        assert evidence["is_primary_source"].eq(True).all()
        assert evidence["provenance_status"].isin(["page_level", "source_level"]).all()
    assert len(manual) + len(pending) + len(adjacent) == 24
    assert results["recommended_backfill_decision"].notna().all()
    assert results["recommended_manual_review_entry_class"].notna().all()
    assert results["research_only"].eq(True).all()
    assert results["used_for_signal"].eq(False).all()
    assert results["used_for_admission"].eq(False).all()
    assert results["price_move_used_for_signal"].eq(False).all()
    assert results["low_position_used_for_signal"].eq(False).all()
    assert results["core_equivalence_performed"].eq(False).all()
    assert set(results["recommended_backfill_decision"]).issubset(
        {
            "upgrade_to_latent_standard_manual_approval_candidate",
            "remain_latent_standard_pending_evidence",
            "move_to_adjacent_watchlist",
            "downgrade_or_reject",
        }
    )
    assert set(results["recommended_manual_review_entry_class"]).issubset(
        {
            "latent_standard_manual_approval_candidate",
            "latent_standard_pending_evidence",
            "adjacent_watchlist",
            "downgrade_or_reject",
        }
    )


def test_latent_standard_backfill_queue_deterministic_and_strategy_diff_clean() -> None:
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
