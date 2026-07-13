from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_candidate_universe_true_rescue_primary_source_verification_v1"
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_candidate_universe_true_rescue_primary_source_verification.py"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
EXPECTED_NAMES = {"道恩股份", "京泉华", "浙江力诺"}


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


def test_primary_source_verification_outputs_and_guardrails() -> None:
    _run_generator()
    expected_files = {
        "true_rescue_primary_source_verification_summary.json",
        "true_rescue_primary_source_evidence_matrix.csv",
        "verified_rescue_candidates.csv",
        "evidence_insufficient_rescue_candidates.csv",
        "downgrade_to_adjacent_watchlist.csv",
        "rejected_seed_pollution_candidates.csv",
        "tech_bottleneck_candidate_universe_true_rescue_primary_source_verification_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected_files.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    summary = json.loads((OUTPUT_DIR / "true_rescue_primary_source_verification_summary.json").read_text(encoding="utf-8"))
    assert summary["research_only"] is True
    assert summary["candidate_count"] == 3
    assert summary["expected_candidates_accounted_for"] is True
    assert summary["auto_promote_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False


def test_each_candidate_has_primary_source_decision_fields() -> None:
    _run_generator()
    matrix = pd.read_csv(OUTPUT_DIR / "true_rescue_primary_source_evidence_matrix.csv")
    assert len(matrix) == 3
    assert set(matrix["stock_name"]) == EXPECTED_NAMES
    assert matrix["verification_decision"].notna().all()
    assert matrix["evidence_strength"].notna().all()
    assert matrix["primary_source_type"].isin(
        {
            "annual report",
            "semiannual/quarterly report",
            "IPO/refinancing prospectus",
            "exchange announcement",
            "official company website",
            "official investor relations disclosure",
            "exchange investor Q&A",
            "missing",
        }
    ).all()
    assert matrix["evidence_category"].isin(
        {
            "key_material",
            "key_component",
            "industrial_equipment",
            "industrial_software",
            "process_technology",
            "import_substitution",
            "supply_chain_security",
            "other",
        }
    ).all()
    assert matrix["bottleneck_relevance"].isin({"core", "adjacent", "unclear", "not_relevant"}).all()
    assert matrix["verification_decision"].isin(
        {
            "verified_rescue_candidate",
            "evidence_insufficient",
            "downgrade_to_adjacent_watchlist",
            "reject_seed_pollution",
        }
    ).all()
    assert not matrix["auto_promote"].astype(bool).any()
    assert not matrix["used_for_signal"].astype(bool).any()
    assert not matrix["used_for_admission"].astype(bool).any()


def test_primary_source_verification_is_deterministic_and_strategy_diff_clean() -> None:
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
