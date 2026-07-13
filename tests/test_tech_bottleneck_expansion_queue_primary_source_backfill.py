from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_expansion_queue_primary_source_backfill.py"
INPUT_QUEUE = PROJECT_ROOT / "outputs/research/tech_bottleneck_2025_doubler_tech_expansion_queue_v1/eligible_expansion_evidence_queue.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_expansion_queue_primary_source_backfill_v1"
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
    return {
        path.name: _sha(path)
        for path in sorted(OUTPUT_DIR.iterdir())
        if path.is_file()
    }


def test_expansion_queue_primary_source_backfill_outputs_and_guardrails() -> None:
    queue_hash_before = _sha(INPUT_QUEUE)
    _run_generator()
    queue_hash_after = _sha(INPUT_QUEUE)

    expected = {
        "expansion_queue_primary_source_backfill_summary.json",
        "expansion_queue_backfill_results.csv",
        "expansion_queue_primary_source_evidence_matrix.csv",
        "expansion_queue_gap_matrix.csv",
        "expansion_queue_manual_approval_candidates.csv",
        "expansion_queue_remain_pending_candidates.csv",
        "expansion_queue_adjacent_or_downgrade_candidates.csv",
        "expansion_queue_primary_source_backfill_guardrails.json",
        "tech_bottleneck_expansion_queue_primary_source_backfill_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert queue_hash_before == queue_hash_after

    summary = json.loads((OUTPUT_DIR / "expansion_queue_primary_source_backfill_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "expansion_queue_primary_source_backfill_guardrails.json").read_text(encoding="utf-8"))

    assert summary["source_expansion_queue_count"] == 88
    assert summary["processed_count"] == 88
    assert summary["upgrade_count"] + summary["remain_pending_count"] + summary["adjacent_count"] + summary["downgrade_or_reject_count"] == 88
    assert summary["price_move_used_for_signal"] == 0
    assert summary["auto_applied_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["baseline_admission_changed_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["trading_language_hit_count"] == 0
    assert summary["execution_language_hit_count"] == 0
    assert summary["acceptance_decision"] in {
        "expansion_queue_primary_source_backfill_ready",
        "conditionally_ready_with_remaining_evidence_gaps",
    }

    assert guardrails["research_only"] is True
    assert guardrails["source_expansion_queue_count"] == 88
    assert guardrails["only_expansion_queue_processed"] is True
    assert guardrails["price_move_used_for_signal"] == 0
    assert guardrails["auto_applied_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0


def test_expansion_queue_primary_source_backfill_processes_only_88_queue_rows() -> None:
    _run_generator()

    queue = pd.read_csv(INPUT_QUEUE, dtype={"stock_code": str})
    results = pd.read_csv(OUTPUT_DIR / "expansion_queue_backfill_results.csv", dtype={"stock_code": str})
    evidence = pd.read_csv(OUTPUT_DIR / "expansion_queue_primary_source_evidence_matrix.csv", dtype={"stock_code": str})
    gaps = pd.read_csv(OUTPUT_DIR / "expansion_queue_gap_matrix.csv", dtype={"stock_code": str})

    assert len(results) == 88
    assert set(results["stock_code"]) == set(queue["stock_code"].str.zfill(6))
    assert set(evidence["stock_code"]).issubset(set(results["stock_code"]))
    assert set(gaps["stock_code"]) == set(results["stock_code"])
    assert results["expansion_queue_source"].eq("eligible_expansion_evidence_queue").all()
    assert results["recommended_backfill_decision"].notna().all()
    assert results["recommended_manual_review_entry_class"].notna().all()
    assert results["research_only"].eq(True).all()
    assert results["used_for_signal"].eq(False).all()
    assert results["used_for_admission"].eq(False).all()
    assert "price_move_used_for_signal" not in results.columns or results["price_move_used_for_signal"].eq(False).all()

    allowed_decisions = {
        "upgrade_to_expansion_manual_approval_candidate",
        "remain_expansion_pending_evidence",
        "move_to_adjacent_watchlist",
        "downgrade_or_reject",
    }
    allowed_classes = {
        "expansion_manual_approval_candidate",
        "expansion_pending_evidence",
        "adjacent_watchlist",
        "downgrade_or_reject",
    }
    assert set(results["recommended_backfill_decision"]).issubset(allowed_decisions)
    assert set(results["recommended_manual_review_entry_class"]).issubset(allowed_classes)
    if not evidence.empty:
        assert evidence["provenance_status"].isin(["page_level", "source_level"]).all()


def test_expansion_queue_primary_source_backfill_deterministic_and_strategy_diff_clean() -> None:
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
