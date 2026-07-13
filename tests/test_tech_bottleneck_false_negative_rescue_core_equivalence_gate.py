from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_false_negative_rescue_core_equivalence_gate.py"
INPUT_CANDIDATES = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_false_negative_rescue_primary_source_backfill_v1/false_negative_rescue_manual_approval_candidates.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_false_negative_rescue_core_equivalence_gate_v1"
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


def test_false_negative_rescue_core_equivalence_gate_outputs_and_guardrails() -> None:
    input_hash_before = _sha(INPUT_CANDIDATES)
    _run_generator()
    input_hash_after = _sha(INPUT_CANDIDATES)

    expected = {
        "false_negative_rescue_core_equivalence_summary.json",
        "false_negative_rescue_core_equivalence_gate.csv",
        "rescue_core_equivalent_add_to_quality_pool.csv",
        "keep_as_rescue_candidate.csv",
        "remain_excluded_after_backfill.csv",
        "downgrade_or_reject.csv",
        "false_negative_rescue_exclusion_reversal_audit.csv",
        "false_negative_rescue_core_equivalence_guardrails.json",
        "tech_bottleneck_false_negative_rescue_core_equivalence_gate_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hash_before == input_hash_after

    summary = json.loads(
        (OUTPUT_DIR / "false_negative_rescue_core_equivalence_summary.json").read_text(encoding="utf-8")
    )
    guardrails = json.loads(
        (OUTPUT_DIR / "false_negative_rescue_core_equivalence_guardrails.json").read_text(encoding="utf-8")
    )

    assert summary["source_rescue_candidate_count"] == 39
    assert summary["processed_count"] == 39
    assert (
        summary["rescue_core_equivalent_count"]
        + summary["keep_as_rescue_candidate_count"]
        + summary["remain_excluded_after_backfill_count"]
        + summary["downgrade_or_reject_count"]
        == 39
    )
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
        "false_negative_rescue_core_equivalence_gate_ready",
        "conditionally_ready_with_rescue_equivalence_gaps",
    }

    assert guardrails["research_only"] is True
    assert guardrails["only_rescue_39_processed"] is True
    assert guardrails["quality_pool_172_processed"] is False
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


def test_false_negative_rescue_core_equivalence_gate_integrity() -> None:
    _run_generator()

    candidates = pd.read_csv(INPUT_CANDIDATES, dtype={"stock_code": str})
    gate = pd.read_csv(OUTPUT_DIR / "false_negative_rescue_core_equivalence_gate.csv", dtype={"stock_code": str})
    core = pd.read_csv(OUTPUT_DIR / "rescue_core_equivalent_add_to_quality_pool.csv", dtype={"stock_code": str})
    keep = pd.read_csv(OUTPUT_DIR / "keep_as_rescue_candidate.csv", dtype={"stock_code": str})
    remain = pd.read_csv(OUTPUT_DIR / "remain_excluded_after_backfill.csv", dtype={"stock_code": str})
    reject = pd.read_csv(OUTPUT_DIR / "downgrade_or_reject.csv", dtype={"stock_code": str})
    reversal = pd.read_csv(
        OUTPUT_DIR / "false_negative_rescue_exclusion_reversal_audit.csv", dtype={"stock_code": str}
    )

    assert len(gate) == 39
    assert gate["stock_code"].nunique() == 39
    assert set(gate["stock_code"]) == set(candidates["stock_code"].str.zfill(6))
    assert gate["source_group"].eq("false_negative_rescue_backfilled").all()
    assert gate["research_only"].eq(True).all()
    assert gate["used_for_signal"].eq(False).all()
    assert gate["used_for_admission"].eq(False).all()
    assert gate["auto_added_to_quality_pool"].eq(False).all()
    assert gate["price_move_used_for_signal"].eq(False).all()

    allowed = {
        "rescue_core_equivalent_add_to_quality_pool",
        "keep_as_rescue_candidate",
        "remain_excluded_after_backfill",
        "downgrade_or_reject",
    }
    assert set(gate["equivalence_gate_decision"]).issubset(allowed)
    assert gate["excluded_reason_reversal_status"].str.len().gt(0).all()
    assert gate["concept_pollution_residual_risk"].str.len().gt(0).all()
    assert gate["equivalence_gate_reason"].str.len().gt(0).all()
    assert gate["recommended_next_action"].str.len().gt(0).all()
    assert len(core) + len(keep) + len(remain) + len(reject) == 39
    assert set(reversal["stock_code"]) == set(gate["stock_code"])


def test_false_negative_rescue_core_equivalence_gate_deterministic_and_strategy_diff_clean() -> None:
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
