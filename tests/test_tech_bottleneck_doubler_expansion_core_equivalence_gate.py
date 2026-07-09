from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_doubler_expansion_core_equivalence_gate.py"
INPUT_PACKAGE = PROJECT_ROOT / "outputs/research/tech_bottleneck_expansion_manual_approval_consolidation_v1/expansion_manual_approval_package.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_doubler_expansion_core_equivalence_gate_v1"
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


def test_doubler_expansion_core_equivalence_gate_outputs_and_guardrails() -> None:
    input_hash_before = _sha(INPUT_PACKAGE)
    _run_generator()
    input_hash_after = _sha(INPUT_PACKAGE)

    expected = {
        "doubler_expansion_core_equivalence_summary.json",
        "doubler_expansion_core_equivalence_gate.csv",
        "core_equivalent_add_to_quality_pool.csv",
        "keep_as_expansion_candidate.csv",
        "adjacent_or_theme_watch.csv",
        "downgrade_or_reject.csv",
        "ipo_cohort_risk_audit.csv",
        "doubler_expansion_core_equivalence_guardrails.json",
        "tech_bottleneck_doubler_expansion_core_equivalence_gate_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hash_before == input_hash_after

    summary = json.loads((OUTPUT_DIR / "doubler_expansion_core_equivalence_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "doubler_expansion_core_equivalence_guardrails.json").read_text(encoding="utf-8"))

    assert summary["source_expansion_candidate_count"] == 88
    assert summary["processed_count"] == 88
    assert (
        summary["core_equivalent_count"]
        + summary["keep_as_expansion_candidate_count"]
        + summary["adjacent_or_theme_watch_count"]
        + summary["downgrade_or_reject_count"]
        == 88
    )
    assert summary["price_move_used_for_signal"] == 0
    assert summary["auto_applied_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["baseline_admission_changed_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["trading_language_hit_count"] == 0
    assert summary["execution_language_hit_count"] == 0
    assert summary["acceptance_decision"] in {
        "doubler_expansion_core_equivalence_gate_ready",
        "conditionally_ready_with_equivalence_gaps",
    }

    assert guardrails["research_only"] is True
    assert guardrails["only_expansion_88_processed"] is True
    assert guardrails["source_expansion_candidate_count"] == 88
    assert guardrails["price_move_used_for_signal"] == 0
    assert guardrails["auto_applied_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0


def test_doubler_expansion_core_equivalence_gate_integrity_and_ipo_flags() -> None:
    _run_generator()

    package = pd.read_csv(INPUT_PACKAGE, dtype={"stock_code": str})
    gate = pd.read_csv(OUTPUT_DIR / "doubler_expansion_core_equivalence_gate.csv", dtype={"stock_code": str})
    core = pd.read_csv(OUTPUT_DIR / "core_equivalent_add_to_quality_pool.csv", dtype={"stock_code": str})
    keep = pd.read_csv(OUTPUT_DIR / "keep_as_expansion_candidate.csv", dtype={"stock_code": str})
    adjacent = pd.read_csv(OUTPUT_DIR / "adjacent_or_theme_watch.csv", dtype={"stock_code": str})
    reject = pd.read_csv(OUTPUT_DIR / "downgrade_or_reject.csv", dtype={"stock_code": str})
    ipo = pd.read_csv(OUTPUT_DIR / "ipo_cohort_risk_audit.csv", dtype={"stock_code": str})

    assert len(gate) == 88
    assert gate["stock_code"].nunique() == 88
    assert set(gate["stock_code"]) == set(package["stock_code"].str.zfill(6))
    assert gate["source_group"].eq("expansion_2025_doubler_discovered").all()
    assert gate["research_only"].eq(True).all()
    assert gate["used_for_signal"].eq(False).all()
    assert gate["used_for_admission"].eq(False).all()
    assert gate["price_move_used_for_signal"].eq(False).all()

    allowed_decisions = {
        "core_equivalent_add_to_quality_pool",
        "keep_as_expansion_candidate",
        "adjacent_or_theme_watch",
        "downgrade_or_reject",
    }
    assert set(gate["equivalence_gate_decision"]).issubset(allowed_decisions)
    assert gate["equivalence_gate_reason"].str.len().gt(0).all()
    assert gate["recommended_next_action"].str.len().gt(0).all()
    assert len(core) + len(keep) + len(adjacent) + len(reject) == 88

    assert set(ipo["stock_code"]).issubset(set(gate["stock_code"]))
    if not ipo.empty:
        assert ipo["ipo_cohort_risk"].eq(True).all()
        assert ipo["limited_public_history"].eq(True).all()
        ipo_gate = gate[gate["stock_code"].isin(set(ipo["stock_code"]))]
        assert ipo_gate["ipo_cohort_risk"].eq(True).all()
        assert not ipo_gate["equivalence_gate_decision"].eq("core_equivalent_add_to_quality_pool").any()


def test_doubler_expansion_core_equivalence_gate_deterministic_and_strategy_diff_clean() -> None:
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
