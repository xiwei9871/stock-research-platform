from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_seed_tier_b_reconciliation_v1"
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_candidate_universe_seed_tier_b_reconciliation.py"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
EXPECTED_NAMES = {
    "深圳能源",
    "德赛电池",
    "穗恒运Ａ",
    "顺发恒能",
    "万里扬",
    "圣阳股份",
    "道恩股份",
    "京泉华",
    "欣旺达",
    "易事特",
    "浙江力诺",
    "奕帆传动",
    "贵航股份",
    "德宏股份",
    "新中港",
    "神农集团",
}


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


def test_seed_tier_b_reconciliation_outputs_and_guardrails() -> None:
    _run_generator()
    expected_files = {
        "seed_tier_b_reconciliation_summary.json",
        "seed_tier_b_reconciliation.csv",
        "seed_tier_b_true_rescue_candidates.csv",
        "seed_tier_b_watchlist_only_adjacent.csv",
        "seed_tier_b_seed_pollution_candidates.csv",
        "seed_tier_b_evidence_backfill_required.csv",
        "tech_bottleneck_candidate_universe_seed_tier_b_reconciliation_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected_files.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "seed_tier_b_reconciliation_summary.json").read_text(encoding="utf-8"))
    assert summary["research_only"] is True
    assert summary["candidate_count"] == 16
    assert summary["expected_seed_names_accounted_for"] is True
    assert summary["auto_promote_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["acceptance_decision"] == "seed_tier_b_reconciliation_ready"


def test_all_seed_tier_b_candidates_have_reconciliation_fields() -> None:
    _run_generator()
    df = pd.read_csv(OUTPUT_DIR / "seed_tier_b_reconciliation.csv")
    assert len(df) == 16
    assert set(df["stock_name"]) == EXPECTED_NAMES
    assert df["reconciliation_decision"].notna().all()
    assert df["business_relevance_category"].notna().all()
    assert df["recommended_next_action"].notna().all()
    assert df["rationale"].notna().all()
    assert df["evidence_status"].isin({"sufficient", "insufficient", "missing", "contradictory"}).all()
    assert df["business_relevance_category"].isin(
        {
            "core_tech_bottleneck",
            "key_component",
            "key_material",
            "industrial_software_or_equipment",
            "energy_infrastructure_adjacent",
            "generic_new_energy",
            "traditional_business",
            "unrelated_or_polluted",
        }
    ).all()
    assert df["reconciliation_decision"].isin(
        {
            "true_rescue_to_tier_a_candidate",
            "watchlist_only_adjacent",
            "evidence_backfill_required",
            "data_backfill_required",
            "seed_pollution_remove_from_tech_bottleneck",
            "unclear_manual_review_required",
        }
    ).all()
    assert not df["auto_promote"].astype(bool).any()
    assert not df["used_for_signal"].astype(bool).any()
    assert not df["used_for_admission"].astype(bool).any()


def test_reconciliation_subsets_and_determinism() -> None:
    _run_generator()
    first = _hash_outputs()
    _run_generator()
    second = _hash_outputs()
    assert first == second

    full = pd.read_csv(OUTPUT_DIR / "seed_tier_b_reconciliation.csv")
    true_rescue = pd.read_csv(OUTPUT_DIR / "seed_tier_b_true_rescue_candidates.csv")
    adjacent = pd.read_csv(OUTPUT_DIR / "seed_tier_b_watchlist_only_adjacent.csv")
    pollution = pd.read_csv(OUTPUT_DIR / "seed_tier_b_seed_pollution_candidates.csv")
    backfill = pd.read_csv(OUTPUT_DIR / "seed_tier_b_evidence_backfill_required.csv")
    assert len(true_rescue) > 0
    assert len(adjacent) > 0
    assert len(pollution) > 0
    assert len(backfill) > 0
    assert len(true_rescue) + len(adjacent) + len(pollution) + len(backfill) <= len(full)

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
