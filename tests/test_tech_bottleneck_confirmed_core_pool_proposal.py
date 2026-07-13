from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_confirmed_core_pool_proposal.py"
QUALITY_GATE_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_90_docling_report_quality_gate_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_confirmed_core_pool_proposal_v1"
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


def test_confirmed_core_pool_proposal_outputs_and_counts() -> None:
    quality_gate_hash_before = _sha(QUALITY_GATE_DIR / "tech_bottleneck_90_report_quality_gate.csv")
    _run_generator()
    quality_gate_hash_after = _sha(QUALITY_GATE_DIR / "tech_bottleneck_90_report_quality_gate.csv")

    expected = {
        "confirmed_core_pool_proposal.csv",
        "confirmed_core_pool_proposal_summary.json",
        "likely_core_pending_evidence_queue.csv",
        "primary_source_backfill_queue.csv",
        "downgrade_or_reject_proposal.csv",
        "confirmed_core_pool_proposal_guardrails.json",
        "tech_bottleneck_confirmed_core_pool_proposal_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert quality_gate_hash_before == quality_gate_hash_after

    summary = json.loads((OUTPUT_DIR / "confirmed_core_pool_proposal_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "confirmed_core_pool_proposal_guardrails.json").read_text(encoding="utf-8"))

    assert summary["source_pool_total"] == 90
    assert summary["confirmed_core_pool_proposal_count"] == 29
    assert summary["likely_core_pending_evidence_count"] == 36
    assert summary["primary_source_backfill_queue_count"] == 23
    assert summary["downgrade_or_reject_proposal_count"] == 2
    assert summary["auto_applied_count"] == 0
    assert summary["acceptance_decision"] == "confirmed_core_pool_proposal_ready"

    assert guardrails["research_only"] is True
    assert guardrails["proposal_generated"] is True
    assert guardrails["source_pool_total"] == 90
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0


def test_confirmed_core_pool_proposal_uses_only_confirmed_core_ready_rows() -> None:
    _run_generator()

    proposal = pd.read_csv(OUTPUT_DIR / "confirmed_core_pool_proposal.csv", dtype={"stock_code": str})
    likely = pd.read_csv(OUTPUT_DIR / "likely_core_pending_evidence_queue.csv", dtype={"stock_code": str})
    backfill = pd.read_csv(OUTPUT_DIR / "primary_source_backfill_queue.csv", dtype={"stock_code": str})
    downgrade = pd.read_csv(OUTPUT_DIR / "downgrade_or_reject_proposal.csv", dtype={"stock_code": str})

    assert len(proposal) == 29
    assert len(likely) == 36
    assert len(backfill) == 23
    assert len(downgrade) == 2

    assert set(proposal["manual_review_entry_class"]) == {"confirmed_core_ready_for_manual_review"}
    assert set(likely["manual_review_entry_class"]) == {"likely_core_pending_evidence"}
    assert set(backfill["manual_review_entry_class"]) == {"evidence_backfill_required"}
    assert set(downgrade["manual_review_entry_class"]) == {"downgrade_or_reject"}

    assert not proposal["stock_code"].isin(likely["stock_code"]).any()
    assert not proposal["stock_code"].isin(backfill["stock_code"]).any()
    assert not proposal["stock_code"].isin(downgrade["stock_code"]).any()
    assert proposal["research_only"].eq(True).all()
    assert proposal["used_for_signal"].eq(False).all()
    assert proposal["used_for_admission"].eq(False).all()
    assert proposal["manual_approval_required"].eq(True).all()
    assert proposal["auto_apply_to_strategy"].eq(False).all()


def test_confirmed_core_pool_proposal_is_deterministic_and_strategy_diff_clean() -> None:
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
