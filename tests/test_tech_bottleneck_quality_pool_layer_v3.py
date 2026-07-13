from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_quality_pool_layer_v3.py"
V2_MANIFEST = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v2/quality_pool_layer_v2_manifest.csv"
DATA_GAP_24 = PROJECT_ROOT / "outputs/research/tech_bottleneck_data_gap_core_equivalence_gate_v1/data_gap_core_equivalent_candidates.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v3"
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


def test_quality_pool_layer_v3_outputs_and_guardrails() -> None:
    v2_hash_before = _sha(V2_MANIFEST)
    data_gap_hash_before = _sha(DATA_GAP_24)
    _run_generator()
    v2_hash_after = _sha(V2_MANIFEST)
    data_gap_hash_after = _sha(DATA_GAP_24)

    expected = {
        "quality_pool_layer_v3_manifest.csv",
        "quality_pool_layer_v3_summary.json",
        "quality_pool_layer_v3_by_source.csv",
        "expansion_keep_separate_4.csv",
        "rescue_keep_separate_1.csv",
        "data_gap_keep_separate_3.csv",
        "downgrade_or_reject_2.csv",
        "possible_false_negative_manual_review_9.csv",
        "remain_excluded_22.csv",
        "reject_concept_or_non_bottleneck_6.csv",
        "data_gap_manual_review_31.csv",
        "remain_data_gap_watch_6.csv",
        "reject_weak_or_concept_3.csv",
        "quality_pool_layer_v3_guardrails.json",
        "tech_bottleneck_quality_pool_layer_v3_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert v2_hash_before == v2_hash_after
    assert data_gap_hash_before == data_gap_hash_after

    summary = json.loads((OUTPUT_DIR / "quality_pool_layer_v3_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "quality_pool_layer_v3_guardrails.json").read_text(encoding="utf-8"))

    assert summary["quality_pool_v2_count"] == 210
    assert summary["quality_pool_v3_count"] == 234
    assert summary["internal_quality_pool_count"] == 88
    assert summary["expansion_core_equivalent_count"] == 84
    assert summary["rescue_core_equivalent_count"] == 38
    assert summary["data_gap_core_equivalent_count"] == 24
    assert summary["expansion_keep_separate_count"] == 4
    assert summary["rescue_keep_separate_count"] == 1
    assert summary["data_gap_keep_separate_count"] == 3
    assert summary["downgrade_reject_count"] == 2
    assert summary["possible_false_negative_manual_review_count"] == 9
    assert summary["remain_excluded_count"] == 22
    assert summary["reject_concept_or_non_bottleneck_count"] == 6
    assert summary["data_gap_manual_review_count"] == 31
    assert summary["remain_data_gap_watch_count"] == 6
    assert summary["reject_weak_or_concept_count"] == 3
    assert summary["auto_applied_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["baseline_admission_changed_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["trading_language_hit_count"] == 0
    assert summary["execution_language_hit_count"] == 0
    assert summary["acceptance_decision"] == "quality_pool_layer_v3_ready"

    assert guardrails["research_only"] is True
    assert guardrails["quality_pool_layer_v3_generated"] is True
    assert guardrails["quality_pool_v3_count"] == 234
    assert guardrails["auto_applied_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["lookahead_violation_rows"] == 0


def test_quality_pool_layer_v3_manifest_integrity_and_sidecars() -> None:
    _run_generator()

    manifest = pd.read_csv(OUTPUT_DIR / "quality_pool_layer_v3_manifest.csv", dtype={"stock_code": str})
    by_source = pd.read_csv(OUTPUT_DIR / "quality_pool_layer_v3_by_source.csv")
    data_gap_keep = pd.read_csv(OUTPUT_DIR / "data_gap_keep_separate_3.csv", dtype={"stock_code": str})
    manual_31 = pd.read_csv(OUTPUT_DIR / "data_gap_manual_review_31.csv", dtype={"stock_code": str})
    watch_6 = pd.read_csv(OUTPUT_DIR / "remain_data_gap_watch_6.csv", dtype={"stock_code": str})
    weak_3 = pd.read_csv(OUTPUT_DIR / "reject_weak_or_concept_3.csv", dtype={"stock_code": str})

    assert len(manifest) == 234
    assert manifest["stock_code"].nunique() == 234
    assert set(manifest["quality_layer"]) == {
        "internal_quality_pool",
        "expansion_core_equivalent_quality_pool",
        "false_negative_rescue_core_equivalent_quality_pool",
        "data_gap_core_equivalent_quality_pool",
    }
    assert manifest["research_only"].eq(True).all()
    assert manifest["used_for_signal"].eq(False).all()
    assert manifest["used_for_admission"].eq(False).all()
    assert manifest["manual_review_status"].eq("pending_manual_approval").all()
    assert manifest["manual_approval_question"].str.len().gt(0).all()
    assert manifest["recommended_next_action"].str.len().gt(0).all()

    counts = dict(zip(by_source["quality_layer"], by_source["candidate_count"], strict=False))
    assert counts["internal_quality_pool"] == 88
    assert counts["expansion_core_equivalent_quality_pool"] == 84
    assert counts["false_negative_rescue_core_equivalent_quality_pool"] == 38
    assert counts["data_gap_core_equivalent_quality_pool"] == 24

    assert len(data_gap_keep) == 3
    assert {"600184", "688001", "688820"} == set(data_gap_keep["stock_code"])
    assert "600184" not in set(manifest["stock_code"])
    assert "688001" not in set(manifest["stock_code"])
    assert "688820" not in set(manifest["stock_code"])
    assert len(manual_31) == 31
    assert len(watch_6) == 6
    assert len(weak_3) == 3
    for sidecar in [data_gap_keep, manual_31, watch_6, weak_3]:
        assert sidecar["research_only"].eq(True).all()
        assert sidecar["used_for_signal"].eq(False).all()
        assert sidecar["used_for_admission"].eq(False).all()


def test_quality_pool_layer_v3_deterministic_and_strategy_diff_clean() -> None:
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
