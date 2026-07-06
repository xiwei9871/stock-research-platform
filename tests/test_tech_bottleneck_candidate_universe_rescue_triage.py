from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_rescue_triage_v1"
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_candidate_universe_rescue_triage.py"
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


def _hash_outputs() -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(OUTPUT_DIR.iterdir())
        if path.is_file()
    }


def test_rescue_triage_outputs_and_guardrails() -> None:
    _run_generator()
    expected = {
        "rescue_triage_summary.json",
        "rescue_triage_queue.csv",
        "seed_tier_b_rescue_queue.csv",
        "possible_false_negative_rescue_queue.csv",
        "tier_b_threshold_sensitivity.csv",
        "data_gap_severity_breakdown.csv",
        "non_seed_tier_a_manual_review_queue.csv",
        "tech_bottleneck_candidate_universe_rescue_triage_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    summary = json.loads((OUTPUT_DIR / "rescue_triage_summary.json").read_text(encoding="utf-8"))
    assert summary["research_only"] is True
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["baseline_admission_changed_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["rescue_review_required_count"] == 1002
    assert summary["seed_tier_b_count"] == 16
    assert summary["seed_tier_b_p0_count"] == 16
    assert summary["possible_false_negative_count"] == 90
    assert summary["non_seed_tier_a_manual_review_count"] == 40
    assert summary["threshold_58_high_quality_count"] == 0


def test_rescue_priority_rules_and_threshold_sensitivity() -> None:
    _run_generator()
    queue = pd.read_csv(OUTPUT_DIR / "rescue_triage_queue.csv")
    seed = pd.read_csv(OUTPUT_DIR / "seed_tier_b_rescue_queue.csv")
    possible = pd.read_csv(OUTPUT_DIR / "possible_false_negative_rescue_queue.csv")
    sensitivity = pd.read_csv(OUTPUT_DIR / "tier_b_threshold_sensitivity.csv")
    gaps = pd.read_csv(OUTPUT_DIR / "data_gap_severity_breakdown.csv")
    non_seed_tier_a = pd.read_csv(OUTPUT_DIR / "non_seed_tier_a_manual_review_queue.csv")

    assert len(queue) == 1002
    assert len(seed) == 16
    assert seed["rescue_priority"].eq("P0").all()
    assert queue.loc[queue["is_tier_b_seed"].astype(bool), "rescue_priority"].eq("P0").all()
    assert len(possible) == 90
    assert set(possible["rescue_priority"]).issubset({"P0", "P1"})
    assert not queue["data_gap_severity"].isna().any()
    assert set(queue["data_gap_severity"]).issubset({"minor", "moderate", "severe", "blocking"})
    assert set(sensitivity["score_threshold"].round(2)) == {58.0, 57.5, 57.0, 56.0, 55.0}
    assert sensitivity.loc[sensitivity["score_threshold"].eq(57.0), "would_be_high_quality_count"].iloc[0] == 74
    assert sensitivity["blocking_data_gap_count"].ge(0).all()
    assert {
        "name/code mapping gap",
        "industry mapping gap",
        "evidence text gap",
        "financial data gap",
        "trading status gap",
        "keyword/category gap",
        "other",
    }.issubset(set(gaps["data_gap_type"]))
    assert len(non_seed_tier_a) == 40
    assert non_seed_tier_a["recommended_action"].eq("manual_rescue_review").all()


def test_rescue_outputs_are_deterministic_and_strategy_diff_clean() -> None:
    _run_generator()
    first = _hash_outputs()
    _run_generator()
    second = _hash_outputs()
    assert first == second
    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
