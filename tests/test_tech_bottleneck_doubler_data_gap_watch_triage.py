from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_doubler_data_gap_watch_triage.py"
INPUT_DATA_GAP = PROJECT_ROOT / "outputs/research/tech_bottleneck_2025_doubler_tech_expansion_queue_v1/data_gap_watch.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_doubler_data_gap_watch_triage_v1"
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


def test_doubler_data_gap_watch_triage_outputs_and_guardrails() -> None:
    input_hash_before = _sha(INPUT_DATA_GAP)
    _run_generator()
    input_hash_after = _sha(INPUT_DATA_GAP)

    expected = {
        "doubler_data_gap_watch_triage_summary.json",
        "doubler_data_gap_watch_triage_results.csv",
        "data_gap_backfill_queue.csv",
        "data_gap_manual_review.csv",
        "remain_data_gap_watch.csv",
        "reject_as_weak_or_concept.csv",
        "doubler_data_gap_watch_triage_guardrails.json",
        "tech_bottleneck_doubler_data_gap_watch_triage_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hash_before == input_hash_after

    summary = json.loads((OUTPUT_DIR / "doubler_data_gap_watch_triage_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "doubler_data_gap_watch_triage_guardrails.json").read_text(encoding="utf-8"))

    assert summary["source_data_gap_watch_count"] == 67
    assert summary["processed_count"] == 67
    assert (
        summary["data_gap_backfill_queue_count"]
        + summary["data_gap_manual_review_count"]
        + summary["remain_data_gap_watch_count"]
        + summary["reject_as_weak_or_concept_count"]
        == 67
    )
    assert summary["primary_source_backfill_performed"] is False
    assert summary["auto_added_to_quality_pool_count"] == 0
    assert summary["price_move_used_for_signal"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["baseline_admission_changed_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["trading_language_hit_count"] == 0
    assert summary["execution_language_hit_count"] == 0
    assert summary["acceptance_decision"] in {
        "doubler_data_gap_watch_triage_ready",
        "conditionally_ready_with_data_gap_review_needed",
    }

    assert guardrails["research_only"] is True
    assert guardrails["only_data_gap_watch_processed"] is True
    assert guardrails["quality_pool_v2_processed"] is False
    assert guardrails["primary_source_backfill_performed"] is False
    assert guardrails["auto_added_to_quality_pool_count"] == 0
    assert guardrails["price_move_used_for_signal"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["lookahead_violation_rows"] == 0


def test_doubler_data_gap_watch_triage_integrity() -> None:
    _run_generator()

    source = pd.read_csv(INPUT_DATA_GAP, dtype={"stock_code": str})
    results = pd.read_csv(OUTPUT_DIR / "doubler_data_gap_watch_triage_results.csv", dtype={"stock_code": str})
    backfill = pd.read_csv(OUTPUT_DIR / "data_gap_backfill_queue.csv", dtype={"stock_code": str})
    manual = pd.read_csv(OUTPUT_DIR / "data_gap_manual_review.csv", dtype={"stock_code": str})
    watch = pd.read_csv(OUTPUT_DIR / "remain_data_gap_watch.csv", dtype={"stock_code": str})
    reject = pd.read_csv(OUTPUT_DIR / "reject_as_weak_or_concept.csv", dtype={"stock_code": str})

    assert len(results) == 67
    assert results["stock_code"].nunique() == 67
    assert set(results["stock_code"]) == set(source["stock_code"].str.zfill(6))
    assert results["source_group"].eq("doubler_data_gap_watch").all()
    assert results["research_only"].eq(True).all()
    assert results["used_for_signal"].eq(False).all()
    assert results["used_for_admission"].eq(False).all()
    assert results["primary_source_backfill_performed"].eq(False).all()
    assert results["auto_added_to_quality_pool"].eq(False).all()
    assert results["price_move_used_for_signal"].eq(False).all()

    allowed = {
        "data_gap_backfill_queue",
        "data_gap_manual_review",
        "remain_data_gap_watch",
        "reject_as_weak_or_concept",
    }
    assert set(results["triage_decision"]).issubset(allowed)
    assert results["data_gap_feasibility"].str.len().gt(0).all()
    assert results["recommended_next_action"].str.len().gt(0).all()
    assert len(backfill) + len(manual) + len(watch) + len(reject) == 67
    if not backfill.empty:
        assert backfill["triage_decision"].eq("data_gap_backfill_queue").all()
        assert backfill["recommended_next_action"].str.contains("primary-source", case=False, regex=False).all()


def test_doubler_data_gap_watch_triage_deterministic_and_strategy_diff_clean() -> None:
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
