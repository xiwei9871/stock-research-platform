from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_latent_standard_core_equivalence_gate.py"
INPUT_CANDIDATES = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_standard_backfill_queue_v1/latent_standard_manual_approval_candidates.csv"
)
INPUT_EVIDENCE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_standard_backfill_queue_v1/latent_standard_evidence_matrix.csv"
)
QUALITY_POOL_V4 = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v4/quality_pool_layer_v4_manifest.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_standard_core_equivalence_gate_v1"
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


def test_latent_standard_core_equivalence_gate_outputs_and_guardrails() -> None:
    input_hashes_before = {
        "candidates": _sha(INPUT_CANDIDATES),
        "evidence": _sha(INPUT_EVIDENCE),
        "quality_pool_v4": _sha(QUALITY_POOL_V4),
    }
    _run_generator()
    input_hashes_after = {
        "candidates": _sha(INPUT_CANDIDATES),
        "evidence": _sha(INPUT_EVIDENCE),
        "quality_pool_v4": _sha(QUALITY_POOL_V4),
    }

    expected = {
        "latent_standard_core_equivalence_gate.csv",
        "latent_standard_core_equivalence_summary.json",
        "latent_standard_core_equivalent_candidates.csv",
        "latent_standard_keep_separate_candidates.csv",
        "latent_standard_remain_watch.csv",
        "latent_standard_downgrade_or_reject.csv",
        "latent_standard_core_equivalence_guardrails.json",
        "tech_bottleneck_latent_standard_core_equivalence_gate_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hashes_before == input_hashes_after

    summary = json.loads((OUTPUT_DIR / "latent_standard_core_equivalence_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads(
        (OUTPUT_DIR / "latent_standard_core_equivalence_guardrails.json").read_text(encoding="utf-8")
    )

    assert summary["source_latent_standard_candidate_count"] == 24
    assert summary["processed_count"] == 24
    assert (
        summary["latent_standard_core_equivalent_count"]
        + summary["keep_as_latent_standard_candidate_count"]
        + summary["remain_latent_standard_watch_count"]
        + summary["downgrade_or_reject_count"]
        == 24
    )
    assert summary["quality_pool_v4_reference_count"] == 276
    assert summary["quality_pool_v4_processed"] is False
    assert summary["auto_added_to_quality_pool_count"] == 0
    assert summary["price_move_used_for_signal"] == 0
    assert summary["low_position_used_for_signal"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["acceptance_decision"] in {
        "latent_standard_core_equivalence_gate_ready",
        "conditionally_ready_with_equivalence_gaps",
    }

    assert guardrails["research_only"] is True
    assert guardrails["source_latent_standard_candidate_count"] == 24
    assert guardrails["processed_count"] == 24
    assert guardrails["auto_added_to_quality_pool_count"] == 0
    assert guardrails["price_move_used_for_signal"] == 0
    assert guardrails["low_position_used_for_signal"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True


def test_latent_standard_core_equivalence_gate_integrity() -> None:
    _run_generator()

    candidates = pd.read_csv(INPUT_CANDIDATES, dtype={"stock_code": str})
    quality_pool_v4 = pd.read_csv(QUALITY_POOL_V4, dtype={"stock_code": str})
    gate = pd.read_csv(OUTPUT_DIR / "latent_standard_core_equivalence_gate.csv", dtype={"stock_code": str})
    core = pd.read_csv(OUTPUT_DIR / "latent_standard_core_equivalent_candidates.csv", dtype={"stock_code": str})
    keep = pd.read_csv(OUTPUT_DIR / "latent_standard_keep_separate_candidates.csv", dtype={"stock_code": str})
    watch = pd.read_csv(OUTPUT_DIR / "latent_standard_remain_watch.csv", dtype={"stock_code": str})
    reject = pd.read_csv(OUTPUT_DIR / "latent_standard_downgrade_or_reject.csv", dtype={"stock_code": str})

    assert len(gate) == 24
    assert set(gate["stock_code"]) == set(candidates["stock_code"].astype(str).str.zfill(6))
    assert set(gate["stock_code"]).isdisjoint(set(quality_pool_v4["stock_code"].astype(str).str.zfill(6)))
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
            "latent_standard_core_equivalent_add_to_quality_pool",
            "keep_as_latent_standard_candidate",
            "remain_latent_standard_watch",
            "downgrade_or_reject",
        }
    )
    assert len(core) + len(keep) + len(watch) + len(reject) == 24


def test_latent_standard_core_equivalence_gate_deterministic_and_strategy_diff_clean() -> None:
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
