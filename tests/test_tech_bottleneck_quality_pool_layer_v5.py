from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_quality_pool_layer_v5.py"
V4_MANIFEST = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v4/quality_pool_layer_v4_manifest.csv"
V4_KEEP = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v4/latent_keep_separate_v4.csv"
LATENT_STANDARD_24 = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_standard_core_equivalence_gate_v1/latent_standard_core_equivalent_candidates.csv"
)
STANDARD_KEEP = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_standard_core_equivalence_gate_v1/latent_standard_keep_separate_candidates.csv"
)
STANDARD_WATCH = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_standard_core_equivalence_gate_v1/latent_standard_remain_watch.csv"
)
STANDARD_REJECT = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_standard_core_equivalence_gate_v1/latent_standard_downgrade_or_reject.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v5"
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


def test_quality_pool_layer_v5_outputs_and_guardrails() -> None:
    input_hashes_before = {
        "v4": _sha(V4_MANIFEST),
        "v4_keep": _sha(V4_KEEP),
        "latent_standard_24": _sha(LATENT_STANDARD_24),
        "standard_keep": _sha(STANDARD_KEEP),
        "standard_watch": _sha(STANDARD_WATCH),
        "standard_reject": _sha(STANDARD_REJECT),
    }
    _run_generator()
    input_hashes_after = {
        "v4": _sha(V4_MANIFEST),
        "v4_keep": _sha(V4_KEEP),
        "latent_standard_24": _sha(LATENT_STANDARD_24),
        "standard_keep": _sha(STANDARD_KEEP),
        "standard_watch": _sha(STANDARD_WATCH),
        "standard_reject": _sha(STANDARD_REJECT),
    }

    expected = {
        "quality_pool_layer_v5_manifest.csv",
        "quality_pool_layer_v5_summary.json",
        "quality_pool_layer_v5_by_source.csv",
        "quality_pool_layer_v5_separate_buckets.csv",
        "quality_pool_layer_v5_guardrails.json",
        "tech_bottleneck_quality_pool_layer_v5_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hashes_before == input_hashes_after

    summary = json.loads((OUTPUT_DIR / "quality_pool_layer_v5_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "quality_pool_layer_v5_guardrails.json").read_text(encoding="utf-8"))

    assert summary["quality_pool_v4_count"] == 276
    assert summary["latent_standard_core_equivalent_added"] == 24
    assert summary["quality_pool_v5_count"] == 300
    assert summary["latent_keep_separate_count"] == 7
    assert summary["latent_standard_keep_separate_count"] == 0
    assert summary["latent_standard_remain_watch_count"] == 0
    assert summary["latent_standard_downgrade_or_reject_count"] == 0
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
    assert summary["acceptance_decision"] == "quality_pool_layer_v5_ready"

    assert guardrails["research_only"] is True
    assert guardrails["quality_pool_layer_v5_generated"] is True
    assert guardrails["quality_pool_v4_count"] == 276
    assert guardrails["latent_standard_core_equivalent_added"] == 24
    assert guardrails["quality_pool_v5_count"] == 300
    assert guardrails["duplicate_stock_count"] == 0
    assert guardrails["auto_applied_count"] == 0
    assert guardrails["price_move_used_for_signal"] == 0
    assert guardrails["low_position_used_for_signal"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["lookahead_violation_rows"] == 0


def test_quality_pool_layer_v5_manifest_and_sidecar_integrity() -> None:
    _run_generator()

    manifest = pd.read_csv(OUTPUT_DIR / "quality_pool_layer_v5_manifest.csv", dtype={"stock_code": str})
    by_source = pd.read_csv(OUTPUT_DIR / "quality_pool_layer_v5_by_source.csv")
    buckets = pd.read_csv(OUTPUT_DIR / "quality_pool_layer_v5_separate_buckets.csv")
    v4 = pd.read_csv(V4_MANIFEST, dtype={"stock_code": str})
    latent_standard = pd.read_csv(LATENT_STANDARD_24, dtype={"stock_code": str})

    assert len(manifest) == 300
    assert manifest["stock_code"].nunique() == 300
    assert set(v4["stock_code"].astype(str).str.zfill(6)).issubset(set(manifest["stock_code"]))
    assert set(latent_standard["stock_code"].astype(str).str.zfill(6)).issubset(set(manifest["stock_code"]))
    assert "latent_standard_core_equivalent_quality_pool" in set(manifest["quality_layer"])
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
    assert counts["latent_standard_core_equivalent_quality_pool"] == 24

    bucket_counts = dict(zip(buckets["bucket_name"], buckets["candidate_count"], strict=False))
    assert bucket_counts["latent_keep_separate_v4"] == 7
    assert bucket_counts["latent_standard_keep_separate"] == 0
    assert bucket_counts["latent_standard_remain_watch"] == 0
    assert bucket_counts["latent_standard_downgrade_or_reject"] == 0
    assert buckets["auto_applied"].eq(False).all()
    assert buckets["used_for_signal"].eq(False).all()
    assert buckets["used_for_admission"].eq(False).all()


def test_quality_pool_layer_v5_deterministic_and_strategy_diff_clean() -> None:
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
