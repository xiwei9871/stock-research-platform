from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_excluded_false_negative_review.py"
INPUT_FALSE_NEGATIVE = PROJECT_ROOT / "outputs/research/tech_bottleneck_2025_doubler_tech_expansion_queue_v1/excluded_false_negative_review.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_excluded_false_negative_review_v1"
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


def test_excluded_false_negative_review_outputs_and_guardrails() -> None:
    input_hash_before = _sha(INPUT_FALSE_NEGATIVE)
    _run_generator()
    input_hash_after = _sha(INPUT_FALSE_NEGATIVE)

    expected = {
        "excluded_false_negative_review_results.csv",
        "false_negative_rescue_queue.csv",
        "possible_false_negative_manual_review.csv",
        "remain_excluded.csv",
        "reject_as_concept_or_non_bottleneck.csv",
        "excluded_false_negative_review_summary.json",
        "excluded_false_negative_review_guardrails.json",
        "tech_bottleneck_excluded_false_negative_review_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hash_before == input_hash_after

    summary = json.loads((OUTPUT_DIR / "excluded_false_negative_review_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "excluded_false_negative_review_guardrails.json").read_text(encoding="utf-8"))

    assert summary["excluded_false_negative_review_count"] == 76
    assert summary["processed_count"] == 76
    assert (
        summary["likely_false_negative_count"]
        + summary["possible_false_negative_count"]
        + summary["remain_excluded_count"]
        + summary["reject_as_concept_or_non_bottleneck_count"]
        == 76
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
        "excluded_false_negative_review_ready",
        "conditionally_ready_with_manual_review_needed",
    }

    assert guardrails["research_only"] is True
    assert guardrails["excluded_false_negative_review_count"] == 76
    assert guardrails["only_false_negative_review_processed"] is True
    assert guardrails["primary_source_backfill_performed"] is False
    assert guardrails["auto_added_to_quality_pool_count"] == 0
    assert guardrails["price_move_used_for_signal"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0


def test_excluded_false_negative_review_processes_only_76_rows() -> None:
    _run_generator()

    source = pd.read_csv(INPUT_FALSE_NEGATIVE, dtype={"stock_code": str})
    results = pd.read_csv(OUTPUT_DIR / "excluded_false_negative_review_results.csv", dtype={"stock_code": str})
    rescue = pd.read_csv(OUTPUT_DIR / "false_negative_rescue_queue.csv", dtype={"stock_code": str})
    possible = pd.read_csv(OUTPUT_DIR / "possible_false_negative_manual_review.csv", dtype={"stock_code": str})
    remain = pd.read_csv(OUTPUT_DIR / "remain_excluded.csv", dtype={"stock_code": str})
    reject = pd.read_csv(OUTPUT_DIR / "reject_as_concept_or_non_bottleneck.csv", dtype={"stock_code": str})

    assert len(results) == 76
    assert results["stock_code"].nunique() == 76
    assert set(results["stock_code"]) == set(source["stock_code"].str.zfill(6))
    assert len(rescue) + len(possible) + len(remain) + len(reject) == 76
    assert results["research_only"].eq(True).all()
    assert results["used_for_signal"].eq(False).all()
    assert results["used_for_admission"].eq(False).all()
    assert results["price_move_used_for_signal"].eq(False).all()
    assert results["primary_source_backfill_performed"].eq(False).all()
    assert results["auto_added_to_quality_pool"].eq(False).all()

    allowed = {
        "likely_false_negative_needs_primary_source_backfill",
        "possible_false_negative_manual_review",
        "remain_excluded",
        "reject_as_concept_or_non_bottleneck",
    }
    assert set(results["review_decision"]).issubset(allowed)
    assert results["recommended_next_action"].str.len().gt(0).all()
    assert results["rescue_reason"].str.len().gt(0).all()
    assert set(rescue["review_decision"]) <= {"likely_false_negative_needs_primary_source_backfill"}


def test_excluded_false_negative_review_deterministic_and_strategy_diff_clean() -> None:
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
