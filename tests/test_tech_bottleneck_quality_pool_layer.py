from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_quality_pool_layer.py"
INTERNAL_88 = PROJECT_ROOT / "outputs/research/tech_bottleneck_90_manual_approval_consolidation_v1/manual_approval_candidates_88.csv"
EXPANSION_84 = PROJECT_ROOT / "outputs/research/tech_bottleneck_doubler_expansion_core_equivalence_gate_v1/core_equivalent_add_to_quality_pool.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v1"
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


def test_quality_pool_layer_outputs_and_guardrails() -> None:
    internal_hash_before = _sha(INTERNAL_88)
    expansion_hash_before = _sha(EXPANSION_84)
    _run_generator()
    internal_hash_after = _sha(INTERNAL_88)
    expansion_hash_after = _sha(EXPANSION_84)

    expected = {
        "quality_pool_layer_manifest.csv",
        "quality_pool_layer_summary.json",
        "quality_pool_layer_by_source.csv",
        "expansion_keep_separate_4.csv",
        "downgrade_or_reject_2.csv",
        "quality_pool_layer_guardrails.json",
        "tech_bottleneck_quality_pool_layer_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert internal_hash_before == internal_hash_after
    assert expansion_hash_before == expansion_hash_after

    summary = json.loads((OUTPUT_DIR / "quality_pool_layer_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "quality_pool_layer_guardrails.json").read_text(encoding="utf-8"))

    assert summary["quality_pool_count"] == 172
    assert summary["internal_quality_pool_count"] == 88
    assert summary["expansion_core_equivalent_count"] == 84
    assert summary["expansion_keep_separate_count"] == 4
    assert summary["downgrade_reject_count"] == 2
    assert summary["auto_applied_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["baseline_admission_changed_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["trading_language_hit_count"] == 0
    assert summary["execution_language_hit_count"] == 0
    assert summary["acceptance_decision"] == "quality_pool_layer_ready"

    assert guardrails["research_only"] is True
    assert guardrails["quality_pool_layer_generated"] is True
    assert guardrails["quality_pool_count"] == 172
    assert guardrails["internal_quality_pool_count"] == 88
    assert guardrails["expansion_core_equivalent_count"] == 84
    assert guardrails["expansion_keep_separate_count"] == 4
    assert guardrails["downgrade_reject_count"] == 2
    assert guardrails["auto_applied_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0


def test_quality_pool_layer_manifest_integrity() -> None:
    _run_generator()

    manifest = pd.read_csv(OUTPUT_DIR / "quality_pool_layer_manifest.csv", dtype={"stock_code": str})
    by_source = pd.read_csv(OUTPUT_DIR / "quality_pool_layer_by_source.csv")
    keep = pd.read_csv(OUTPUT_DIR / "expansion_keep_separate_4.csv", dtype={"stock_code": str})
    reject = pd.read_csv(OUTPUT_DIR / "downgrade_or_reject_2.csv", dtype={"stock_code": str})

    assert len(manifest) == 172
    assert manifest["stock_code"].nunique() == 172
    assert set(manifest["quality_layer"]) == {"internal_quality_pool", "expansion_core_equivalent_quality_pool"}
    assert manifest["research_only"].eq(True).all()
    assert manifest["used_for_signal"].eq(False).all()
    assert manifest["used_for_admission"].eq(False).all()
    assert manifest["manual_review_status"].eq("pending_manual_approval").all()
    assert manifest["manual_approval_question"].str.len().gt(0).all()
    assert manifest["recommended_next_action"].str.len().gt(0).all()

    counts = dict(zip(by_source["quality_layer"], by_source["candidate_count"], strict=False))
    assert counts["internal_quality_pool"] == 88
    assert counts["expansion_core_equivalent_quality_pool"] == 84
    assert len(keep) == 4
    assert len(reject) == 2
    assert keep["research_only"].eq(True).all()
    assert reject["research_only"].eq(True).all()


def test_quality_pool_layer_deterministic_and_strategy_diff_clean() -> None:
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
