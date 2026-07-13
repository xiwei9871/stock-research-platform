from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_latent_core_equivalence_gate_batch1_rerun_v2.py"
INPUT_CANDIDATES = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_primary_source_backfill_batch1_rerun_v2/latent_backfill_batch1_rerun_v2_manual_approval_candidates.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_core_equivalence_gate_batch1_rerun_v2"
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


def test_latent_core_equivalence_gate_batch1_rerun_v2_outputs_and_guardrails() -> None:
    input_hash_before = _sha(INPUT_CANDIDATES)
    _run_generator()
    input_hash_after = _sha(INPUT_CANDIDATES)

    expected = {
        "latent_core_equivalence_gate_batch1_rerun_v2.csv",
        "latent_core_equivalence_batch1_rerun_v2_summary.json",
        "latent_core_equivalent_batch1_rerun_v2_candidates.csv",
        "latent_keep_separate_batch1_rerun_v2_candidates.csv",
        "latent_remain_watch_batch1_rerun_v2.csv",
        "latent_downgrade_or_reject_batch1_rerun_v2.csv",
        "latent_core_equivalence_batch1_rerun_v2_guardrails.json",
        "tech_bottleneck_latent_core_equivalence_gate_batch1_rerun_v2_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hash_before == input_hash_after

    summary = json.loads((OUTPUT_DIR / "latent_core_equivalence_batch1_rerun_v2_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads(
        (OUTPUT_DIR / "latent_core_equivalence_batch1_rerun_v2_guardrails.json").read_text(encoding="utf-8")
    )

    assert summary["source_latent_manual_approval_candidate_count"] == 45
    assert summary["processed_count"] == 45
    assert (
        summary["latent_core_equivalent_count"]
        + summary["keep_as_latent_candidate_count"]
        + summary["remain_latent_watch_count"]
        + summary["downgrade_or_reject_count"]
        == 45
    )
    assert summary["auto_added_to_quality_pool_count"] == 0
    assert summary["price_move_used_for_signal"] == 0
    assert summary["low_position_used_for_signal"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["acceptance_decision"] in {
        "latent_core_equivalence_gate_batch1_rerun_v2_ready",
        "conditionally_ready_with_equivalence_gaps",
    }

    assert guardrails["research_only"] is True
    assert guardrails["source_latent_manual_approval_candidate_count"] == 45
    assert guardrails["only_latent_manual_approval_candidates_processed"] is True
    assert guardrails["auto_added_to_quality_pool_count"] == 0
    assert guardrails["price_move_used_for_signal"] == 0
    assert guardrails["low_position_used_for_signal"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True


def test_latent_core_equivalence_gate_batch1_rerun_v2_integrity() -> None:
    _run_generator()

    candidates = pd.read_csv(INPUT_CANDIDATES, dtype={"stock_code": str})
    gate = pd.read_csv(OUTPUT_DIR / "latent_core_equivalence_gate_batch1_rerun_v2.csv", dtype={"stock_code": str})
    core = pd.read_csv(OUTPUT_DIR / "latent_core_equivalent_batch1_rerun_v2_candidates.csv", dtype={"stock_code": str})
    keep = pd.read_csv(OUTPUT_DIR / "latent_keep_separate_batch1_rerun_v2_candidates.csv", dtype={"stock_code": str})
    watch = pd.read_csv(OUTPUT_DIR / "latent_remain_watch_batch1_rerun_v2.csv", dtype={"stock_code": str})
    reject = pd.read_csv(OUTPUT_DIR / "latent_downgrade_or_reject_batch1_rerun_v2.csv", dtype={"stock_code": str})

    assert len(gate) == 45
    assert set(gate["stock_code"]) == set(candidates["stock_code"].astype(str).str.zfill(6))
    assert gate["research_only"].eq(True).all()
    assert gate["used_for_signal"].eq(False).all()
    assert gate["used_for_admission"].eq(False).all()
    assert gate["auto_added_to_quality_pool"].eq(False).all()
    assert gate["price_move_used_for_signal"].eq(False).all()
    assert gate["low_position_used_for_signal"].eq(False).all()
    assert gate["core_equivalence_decision"].notna().all()
    assert gate["core_equivalence_reason"].astype(str).str.len().gt(0).all()
    assert set(gate["core_equivalence_decision"]).issubset(
        {
            "latent_core_equivalent_add_to_quality_pool",
            "keep_as_latent_candidate",
            "remain_latent_watch",
            "downgrade_or_reject",
        }
    )
    assert len(core) + len(keep) + len(watch) + len(reject) == 45


def test_latent_core_equivalence_gate_batch1_rerun_v2_deterministic_and_strategy_diff_clean() -> None:
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
