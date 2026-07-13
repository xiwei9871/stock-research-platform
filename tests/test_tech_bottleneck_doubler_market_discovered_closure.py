from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_doubler_market_discovered_closure.py"
MASTER_596 = PROJECT_ROOT / "outputs/research/tech_bottleneck_2025_doubler_tech_expansion_queue_v1/tech_bottleneck_2025_doubler_tech_expansion_queue_master.csv"
QUALITY_V3 = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v3/quality_pool_layer_v3_manifest.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_doubler_market_discovered_closure_v1"
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


def test_doubler_market_discovered_closure_outputs_and_guardrails() -> None:
    master_hash_before = _sha(MASTER_596)
    quality_hash_before = _sha(QUALITY_V3)
    _run_generator()
    master_hash_after = _sha(MASTER_596)
    quality_hash_after = _sha(QUALITY_V3)

    expected = {
        "doubler_market_discovered_closure_summary.json",
        "doubler_market_discovered_closure_master.csv",
        "doubler_market_discovered_bucket_summary.csv",
        "quality_pool_v3_source_summary.csv",
        "residual_review_queue.csv",
        "keep_separate_queue.csv",
        "excluded_reject_queue.csv",
        "ipo_cohort_risk_audit.csv",
        "doubler_market_discovered_closure_guardrails.json",
        "tech_bottleneck_doubler_market_discovered_closure_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert master_hash_before == master_hash_after
    assert quality_hash_before == quality_hash_after

    summary = json.loads((OUTPUT_DIR / "doubler_market_discovered_closure_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "doubler_market_discovered_closure_guardrails.json").read_text(encoding="utf-8"))

    assert summary["input_doubled_tech_count"] == 596
    assert summary["closed_count"] == 596
    assert summary["quality_pool_v3_count"] == 234
    assert summary["internal_quality_pool_count"] == 88
    assert summary["expansion_core_equivalent_count"] == 84
    assert summary["false_negative_rescue_core_equivalent_count"] == 38
    assert summary["data_gap_core_equivalent_count"] == 24
    assert summary["keep_separate_count"] == 8
    assert summary["residual_manual_review_count"] == 40
    assert summary["remain_watch_count"] == 6
    assert summary["remain_excluded_count"] == 22
    assert summary["reject_count"] == 11
    assert summary["weak_or_concept_only_no_backfill_count"] == 310
    assert summary["price_move_used_for_signal"] == 0
    assert summary["auto_applied_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["baseline_admission_changed_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["trading_language_hit_count"] == 0
    assert summary["execution_language_hit_count"] == 0
    assert summary["acceptance_decision"] == "doubler_market_discovered_closure_ready"

    assert guardrails["research_only"] is True
    assert guardrails["all_596_accounted_for"] is True
    assert guardrails["quality_pool_v3_auto_applied"] is False
    assert guardrails["price_move_used_for_signal"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["lookahead_violation_rows"] == 0


def test_doubler_market_discovered_closure_master_integrity() -> None:
    _run_generator()

    master = pd.read_csv(OUTPUT_DIR / "doubler_market_discovered_closure_master.csv", dtype={"stock_code": str})
    bucket_summary = pd.read_csv(OUTPUT_DIR / "doubler_market_discovered_bucket_summary.csv")
    quality = pd.read_csv(OUTPUT_DIR / "quality_pool_v3_source_summary.csv")
    residual = pd.read_csv(OUTPUT_DIR / "residual_review_queue.csv", dtype={"stock_code": str})
    keep = pd.read_csv(OUTPUT_DIR / "keep_separate_queue.csv", dtype={"stock_code": str})
    excluded = pd.read_csv(OUTPUT_DIR / "excluded_reject_queue.csv", dtype={"stock_code": str})

    assert len(master) == 596
    assert master["stock_code"].nunique() == 596
    assert master["final_market_discovered_bucket"].notna().all()
    assert master["research_only"].eq(True).all()
    assert master["used_for_signal"].eq(False).all()
    assert master["used_for_admission"].eq(False).all()
    assert master["price_move_used_for_signal"].eq(False).all()
    assert int(bucket_summary["candidate_count"].sum()) == 596
    assert int(quality["candidate_count"].sum()) == 234
    assert len(residual) == 40
    assert len(keep) == 8
    assert len(excluded) == 33
    assert set(master[master["final_market_discovered_bucket"].eq("quality_pool_v3")]["quality_layer"]).issubset(
        {
            "internal_quality_pool",
            "expansion_core_equivalent_quality_pool",
            "false_negative_rescue_core_equivalent_quality_pool",
            "data_gap_core_equivalent_quality_pool",
        }
    )


def test_doubler_market_discovered_closure_deterministic_and_strategy_diff_clean() -> None:
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
