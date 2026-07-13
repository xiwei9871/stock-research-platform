from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_quality_pool_layer_v4.py"
V3_MANIFEST = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v3/quality_pool_layer_v3_manifest.csv"
LATENT_CORE_42 = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_core_equivalence_gate_batch1_rerun_v2/latent_core_equivalent_batch1_rerun_v2_candidates.csv"
)
LATENT_KEEP_3 = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_core_equivalence_gate_batch1_rerun_v2/latent_keep_separate_batch1_rerun_v2_candidates.csv"
)
LATENT_INITIAL_KEEP_4 = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_core_equivalence_gate_batch1_v1/latent_keep_separate_batch1_candidates.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v4"
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


def test_quality_pool_layer_v4_outputs_and_guardrails() -> None:
    input_hashes_before = {
        "v3": _sha(V3_MANIFEST),
        "latent_core_42": _sha(LATENT_CORE_42),
        "latent_keep_3": _sha(LATENT_KEEP_3),
        "latent_initial_keep_4": _sha(LATENT_INITIAL_KEEP_4),
    }
    _run_generator()
    input_hashes_after = {
        "v3": _sha(V3_MANIFEST),
        "latent_core_42": _sha(LATENT_CORE_42),
        "latent_keep_3": _sha(LATENT_KEEP_3),
        "latent_initial_keep_4": _sha(LATENT_INITIAL_KEEP_4),
    }

    expected = {
        "quality_pool_layer_v4_manifest.csv",
        "quality_pool_layer_v4_summary.json",
        "quality_pool_layer_v4_by_source.csv",
        "latent_keep_separate_v4.csv",
        "quality_pool_layer_v4_guardrails.json",
        "tech_bottleneck_quality_pool_layer_v4_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hashes_before == input_hashes_after

    summary = json.loads((OUTPUT_DIR / "quality_pool_layer_v4_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "quality_pool_layer_v4_guardrails.json").read_text(encoding="utf-8"))

    assert summary["quality_pool_v3_count"] == 234
    assert summary["latent_core_equivalent_added"] == 42
    assert summary["quality_pool_v4_count"] == 276
    assert summary["latent_keep_separate_rerun_v2_count"] == 3
    assert summary["latent_keep_separate_initial_count"] == 4
    assert summary["latent_keep_separate_count"] == 7
    assert summary["duplicate_stock_count"] == 0
    assert summary["auto_applied_count"] == 0
    assert summary["price_move_used_for_signal"] == 0
    assert summary["low_position_used_for_signal"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["baseline_admission_changed_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["trading_language_hit_count"] == 0
    assert summary["execution_language_hit_count"] == 0
    assert summary["acceptance_decision"] == "quality_pool_layer_v4_ready"

    assert guardrails["research_only"] is True
    assert guardrails["quality_pool_layer_v4_generated"] is True
    assert guardrails["quality_pool_v3_count"] == 234
    assert guardrails["latent_core_equivalent_added"] == 42
    assert guardrails["quality_pool_v4_count"] == 276
    assert guardrails["latent_keep_separate_count"] == 7
    assert guardrails["duplicate_stock_count"] == 0
    assert guardrails["auto_applied_count"] == 0
    assert guardrails["price_move_used_for_signal"] == 0
    assert guardrails["low_position_used_for_signal"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["lookahead_violation_rows"] == 0


def test_quality_pool_layer_v4_manifest_and_keep_separate_integrity() -> None:
    _run_generator()

    manifest = pd.read_csv(OUTPUT_DIR / "quality_pool_layer_v4_manifest.csv", dtype={"stock_code": str})
    by_source = pd.read_csv(OUTPUT_DIR / "quality_pool_layer_v4_by_source.csv")
    keep = pd.read_csv(OUTPUT_DIR / "latent_keep_separate_v4.csv", dtype={"stock_code": str})
    v3 = pd.read_csv(V3_MANIFEST, dtype={"stock_code": str})
    latent_core = pd.read_csv(LATENT_CORE_42, dtype={"stock_code": str})

    assert len(manifest) == 276
    assert manifest["stock_code"].nunique() == 276
    assert set(v3["stock_code"].astype(str).str.zfill(6)).issubset(set(manifest["stock_code"]))
    assert set(latent_core["stock_code"].astype(str).str.zfill(6)).issubset(set(manifest["stock_code"]))
    assert "latent_core_equivalent_quality_pool" in set(manifest["quality_layer"])
    assert manifest["research_only"].eq(True).all()
    assert manifest["used_for_signal"].eq(False).all()
    assert manifest["used_for_admission"].eq(False).all()
    assert manifest["manual_review_status"].eq("pending_manual_approval").all()
    assert manifest["manual_approval_question"].astype(str).str.len().gt(0).all()
    assert manifest["recommended_next_action"].astype(str).str.len().gt(0).all()

    counts = dict(zip(by_source["quality_layer"], by_source["candidate_count"], strict=False))
    assert counts["internal_quality_pool"] == 88
    assert counts["expansion_core_equivalent_quality_pool"] == 84
    assert counts["false_negative_rescue_core_equivalent_quality_pool"] == 38
    assert counts["data_gap_core_equivalent_quality_pool"] == 24
    assert counts["latent_core_equivalent_quality_pool"] == 42

    assert len(keep) == 7
    assert keep["stock_code"].nunique() == 7
    assert set(keep["latent_keep_separate_source"]) == {
        "latent_core_equivalence_gate_batch1_v1",
        "latent_core_equivalence_gate_batch1_rerun_v2",
    }
    assert keep["stock_code"].isna().sum() == 0
    assert set(keep["stock_code"]).isdisjoint(set(manifest["stock_code"]))
    assert keep["research_only"].eq(True).all()
    assert keep["used_for_signal"].eq(False).all()
    assert keep["used_for_admission"].eq(False).all()
    assert keep["auto_added_to_quality_pool"].eq(False).all()


def test_quality_pool_layer_v4_deterministic_and_strategy_diff_clean() -> None:
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
