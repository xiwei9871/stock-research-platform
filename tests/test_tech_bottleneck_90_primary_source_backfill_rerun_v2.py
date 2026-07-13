from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_90_primary_source_backfill_rerun_v2.py"
INPUT_QUEUE = PROJECT_ROOT / "outputs/research/tech_bottleneck_confirmed_core_pool_proposal_v1/primary_source_backfill_queue.csv"
TEXT_FIRST_SUMMARY = PROJECT_ROOT / "outputs/research/data_to_brief_backfill_primary_source_text_first_parse_v1/text_first_parse_summary.json"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_90_primary_source_backfill_rerun_v2"
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
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(OUTPUT_DIR.iterdir())
        if path.is_file()
    }


def test_primary_source_backfill_rerun_v2_outputs_and_guardrails() -> None:
    queue_hash_before = _sha(INPUT_QUEUE)
    _run_generator()
    queue_hash_after = _sha(INPUT_QUEUE)

    expected = {
        "tech_bottleneck_90_primary_source_backfill_rerun_v2_summary.json",
        "primary_source_backfill_rerun_v2_results.csv",
        "primary_source_backfill_rerun_v2_evidence_matrix.csv",
        "primary_source_backfill_rerun_v2_gap_matrix.csv",
        "backfill_rerun_v2_upgrade_candidates.csv",
        "backfill_rerun_v2_remain_pending_candidates.csv",
        "backfill_rerun_v2_adjacent_or_downgrade_candidates.csv",
        "tech_bottleneck_90_primary_source_backfill_rerun_v2_guardrails.json",
        "tech_bottleneck_90_primary_source_backfill_rerun_v2_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert queue_hash_before == queue_hash_after

    summary = json.loads((OUTPUT_DIR / "tech_bottleneck_90_primary_source_backfill_rerun_v2_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "tech_bottleneck_90_primary_source_backfill_rerun_v2_guardrails.json").read_text(encoding="utf-8"))
    text_summary = json.loads(TEXT_FIRST_SUMMARY.read_text(encoding="utf-8"))

    assert summary["source_backfill_queue_count"] == 23
    assert summary["backfill_processed_count"] == 23
    assert summary["text_first_evidence_chunk_count"] == text_summary["evidence_chunk_count"]
    assert summary["primary_source_supported_after_count"] == 23
    assert summary["brokerage_only_after_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["baseline_admission_changed_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["trading_language_hit_count"] == 0
    assert summary["execution_language_hit_count"] == 0
    assert summary["acceptance_decision"] in {
        "primary_source_backfill_rerun_v2_ready",
        "conditionally_ready_with_remaining_evidence_gaps",
    }

    assert guardrails["research_only"] is True
    assert guardrails["source_backfill_queue_count"] == 23
    assert guardrails["only_backfill_queue_processed"] is True
    assert guardrails["text_first_artifacts_used"] is True
    assert guardrails["auto_applied_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0


def test_primary_source_backfill_rerun_v2_processes_only_23_queue_rows() -> None:
    _run_generator()

    queue = pd.read_csv(INPUT_QUEUE, dtype={"stock_code": str})
    results = pd.read_csv(OUTPUT_DIR / "primary_source_backfill_rerun_v2_results.csv", dtype={"stock_code": str})
    evidence = pd.read_csv(OUTPUT_DIR / "primary_source_backfill_rerun_v2_evidence_matrix.csv", dtype={"stock_code": str})
    gaps = pd.read_csv(OUTPUT_DIR / "primary_source_backfill_rerun_v2_gap_matrix.csv", dtype={"stock_code": str})

    assert len(results) == 23
    assert set(results["stock_code"]) == set(queue["stock_code"].str.zfill(6))
    assert set(evidence["stock_code"]) == set(results["stock_code"])
    assert set(gaps["stock_code"]) == set(results["stock_code"])
    assert results["primary_source_supported"].eq(True).all()
    assert results["brokerage_only_after_backfill"].eq(False).all()
    assert results["recommended_backfill_decision"].notna().all()
    assert results["recommended_manual_review_entry_class"].notna().all()
    assert results["research_only"].eq(True).all()
    assert results["used_for_signal"].eq(False).all()
    assert results["used_for_admission"].eq(False).all()
    assert evidence["is_primary_source"].eq(True).all()
    assert evidence["provenance_status"].eq("page_level").all()


def test_primary_source_backfill_rerun_v2_deterministic_and_strategy_diff_clean() -> None:
    _run_generator()

    upgrades = pd.read_csv(OUTPUT_DIR / "backfill_rerun_v2_upgrade_candidates.csv", dtype={"stock_code": str})
    pending = pd.read_csv(OUTPUT_DIR / "backfill_rerun_v2_remain_pending_candidates.csv", dtype={"stock_code": str})
    adjacent_or_downgrade = pd.read_csv(OUTPUT_DIR / "backfill_rerun_v2_adjacent_or_downgrade_candidates.csv", dtype={"stock_code": str})

    assert len(upgrades) + len(pending) + len(adjacent_or_downgrade) == 23
    if not upgrades.empty:
        assert upgrades["primary_source_supported"].eq(True).all()
        assert upgrades["brokerage_only_after_backfill"].eq(False).all()

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
