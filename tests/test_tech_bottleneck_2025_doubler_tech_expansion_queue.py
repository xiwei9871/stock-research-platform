from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_2025_doubler_tech_expansion_queue.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_2025_doubler_tech_expansion_queue_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def _run_generator() -> None:
    result = subprocess.run(
        [str(PROJECT_ROOT / ".venv/bin/python"), str(SCRIPT)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_doubler_expansion_queue_outputs_and_guardrails() -> None:
    _run_generator()

    expected = {
        "tech_bottleneck_2025_doubler_tech_expansion_queue_summary.json",
        "tech_bottleneck_2025_doubler_tech_expansion_queue_master.csv",
        "already_in_90_pool.csv",
        "eligible_expansion_evidence_queue.csv",
        "excluded_false_negative_review.csv",
        "weak_or_concept_only_no_backfill.csv",
        "data_gap_watch.csv",
        "doubler_candidate_universe_overlap_audit.csv",
        "tech_bottleneck_2025_doubler_tech_expansion_queue_guardrails.json",
        "tech_bottleneck_2025_doubler_tech_expansion_queue_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "tech_bottleneck_2025_doubler_tech_expansion_queue_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "tech_bottleneck_2025_doubler_tech_expansion_queue_guardrails.json").read_text(encoding="utf-8"))

    assert summary["input_doubled_tech_count"] == 596
    assert summary["classified_count"] == 596
    assert summary["already_in_90_pool_count"] >= 0
    assert summary["eligible_expansion_evidence_queue_count"] >= 0
    assert summary["price_move_used_for_signal_count"] == 0
    assert summary["auto_applied_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["baseline_admission_changed_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["trading_language_hit_count"] == 0
    assert summary["execution_language_hit_count"] == 0

    assert guardrails["research_only"] is True
    assert guardrails["input_doubled_tech_count"] == 596
    assert guardrails["classified_count"] == 596
    assert guardrails["no_direct_admission_from_price_move"] is True
    assert guardrails["auto_applied_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0


def test_doubler_expansion_queue_classification_integrity() -> None:
    _run_generator()

    master = pd.read_csv(OUTPUT_DIR / "tech_bottleneck_2025_doubler_tech_expansion_queue_master.csv", dtype={"stock_code": str})
    already = pd.read_csv(OUTPUT_DIR / "already_in_90_pool.csv", dtype={"stock_code": str})
    eligible = pd.read_csv(OUTPUT_DIR / "eligible_expansion_evidence_queue.csv", dtype={"stock_code": str})
    excluded = pd.read_csv(OUTPUT_DIR / "excluded_false_negative_review.csv", dtype={"stock_code": str})
    weak = pd.read_csv(OUTPUT_DIR / "weak_or_concept_only_no_backfill.csv", dtype={"stock_code": str})
    data_gap = pd.read_csv(OUTPUT_DIR / "data_gap_watch.csv", dtype={"stock_code": str})

    assert len(master) == 596
    assert master["stock_code"].nunique() == 596
    assert master["expansion_queue_class"].notna().all()
    assert master["research_only"].eq(True).all()
    assert master["used_for_signal"].eq(False).all()
    assert master["used_for_admission"].eq(False).all()
    assert master["price_move_used_for_signal"].eq(False).all()
    assert master["price_move_used_for_discovery"].eq(True).all()

    assert len(already) + len(eligible) + len(excluded) + len(weak) + len(data_gap) == 596
    assert not eligible["stock_code"].isin(already["stock_code"]).any()
    if not eligible.empty:
        assert eligible["in_90_pool"].eq(False).all()
        assert eligible["expansion_queue_class"].eq("eligible_expansion_evidence_queue").all()
        assert eligible["recommended_next_action"].str.contains("primary-source", case=False, regex=False).all()
    if not weak.empty:
        assert weak["expansion_queue_class"].eq("weak_or_concept_only_no_backfill").all()


def test_doubler_expansion_queue_strategy_diff_clean() -> None:
    _run_generator()

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
