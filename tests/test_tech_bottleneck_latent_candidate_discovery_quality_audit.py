from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_latent_candidate_discovery_quality_audit.py"
SOURCE_QUEUE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_candidate_discovery_v1/latent_evidence_completion_queue.csv"
)
LATENT_UNIVERSE = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_candidate_discovery_v1/latent_candidate_discovery_universe.csv"
)
QUALITY_V3 = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v3/quality_pool_layer_v3_manifest.csv"
DOUBLER_596 = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_doubler_market_discovered_closure_v1/doubler_market_discovered_closure_master.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_candidate_discovery_quality_audit_v1"
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


def test_latent_candidate_discovery_quality_audit_outputs_and_guardrails() -> None:
    source_hash_before = _sha(SOURCE_QUEUE)
    universe_hash_before = _sha(LATENT_UNIVERSE)
    quality_hash_before = _sha(QUALITY_V3)
    doubler_hash_before = _sha(DOUBLER_596)
    _run_generator()
    assert source_hash_before == _sha(SOURCE_QUEUE)
    assert universe_hash_before == _sha(LATENT_UNIVERSE)
    assert quality_hash_before == _sha(QUALITY_V3)
    assert doubler_hash_before == _sha(DOUBLER_596)

    expected = {
        "latent_candidate_discovery_quality_audit_summary.json",
        "latent_candidate_quality_audit.csv",
        "latent_high_priority_backfill_queue.csv",
        "latent_standard_backfill_queue.csv",
        "latent_manual_review_first.csv",
        "latent_defer_or_reject.csv",
        "latent_candidate_discovery_quality_audit_guardrails.json",
        "tech_bottleneck_latent_candidate_discovery_quality_audit_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads(
        (OUTPUT_DIR / "latent_candidate_discovery_quality_audit_summary.json").read_text(encoding="utf-8")
    )
    guardrails = json.loads(
        (OUTPUT_DIR / "latent_candidate_discovery_quality_audit_guardrails.json").read_text(encoding="utf-8")
    )

    assert summary["research_only"] is True
    assert summary["source_latent_evidence_queue_count"] == 210
    assert summary["processed_count"] == 210
    assert summary["only_latent_evidence_queue_processed"] is True
    assert summary["doubled_tech_596_processed"] is False
    assert summary["quality_pool_v3_processed"] is False
    assert summary["latent_data_gap_watch_processed"] is False
    assert summary["primary_source_backfill_performed"] is False
    assert summary["auto_added_to_quality_pool_count"] == 0
    assert summary["price_move_used_for_signal"] == 0
    assert summary["low_position_used_for_signal"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["baseline_admission_changed_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["trading_language_hit_count"] == 0
    assert summary["execution_language_hit_count"] == 0
    assert summary["acceptance_decision"] in {
        "latent_candidate_discovery_quality_audit_ready",
        "conditionally_ready_with_manual_review_needed",
    }
    assert (
        summary["latent_high_priority_backfill_count"]
        + summary["latent_standard_backfill_count"]
        + summary["latent_manual_review_first_count"]
        + summary["latent_defer_or_reject_count"]
        == 210
    )

    assert guardrails["research_only"] is True
    assert guardrails["source_latent_evidence_queue_count"] == 210
    assert guardrails["only_latent_evidence_queue_processed"] is True
    assert guardrails["doubled_tech_596_processed"] is False
    assert guardrails["quality_pool_v3_processed"] is False
    assert guardrails["latent_data_gap_watch_processed"] is False
    assert guardrails["primary_source_backfill_performed"] is False
    assert guardrails["auto_added_to_quality_pool_count"] == 0
    assert guardrails["price_move_used_for_signal"] == 0
    assert guardrails["low_position_used_for_signal"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False


def test_latent_candidate_quality_audit_integrity() -> None:
    _run_generator()

    audit = pd.read_csv(OUTPUT_DIR / "latent_candidate_quality_audit.csv", dtype={"stock_code": str})
    high = pd.read_csv(OUTPUT_DIR / "latent_high_priority_backfill_queue.csv", dtype={"stock_code": str})
    standard = pd.read_csv(OUTPUT_DIR / "latent_standard_backfill_queue.csv", dtype={"stock_code": str})
    manual = pd.read_csv(OUTPUT_DIR / "latent_manual_review_first.csv", dtype={"stock_code": str})
    defer = pd.read_csv(OUTPUT_DIR / "latent_defer_or_reject.csv", dtype={"stock_code": str})
    source = pd.read_csv(SOURCE_QUEUE, dtype={"stock_code": str})

    required_columns = {
        "stock_code",
        "stock_name",
        "tech_bottleneck_domain",
        "supply_chain_role",
        "candidate_tier",
        "hard_tech_domain_signal",
        "bottleneck_or_chokepoint_possibility",
        "business_relevance_signal",
        "concept_pollution_risk",
        "beneficiary_only_risk",
        "primary_source_feasibility",
        "next_primary_source_to_check",
        "price_move_bucket",
        "low_position_research_tag",
        "quality_audit_decision",
        "quality_audit_reason",
        "recommended_next_action",
        "research_only",
        "used_for_signal",
        "used_for_admission",
        "notes",
    }
    assert required_columns.issubset(audit.columns)
    assert len(audit) == 210
    assert audit["stock_code"].nunique() == 210
    assert set(audit["stock_code"]) == set(source["stock_code"].astype(str).str.zfill(6))
    assert audit["quality_audit_decision"].notna().all()
    assert audit["recommended_next_action"].astype(str).str.len().gt(0).all()
    assert audit["research_only"].eq(True).all()
    assert audit["used_for_signal"].eq(False).all()
    assert audit["used_for_admission"].eq(False).all()
    assert set(audit["quality_audit_decision"]) <= {
        "latent_high_priority_backfill",
        "latent_standard_backfill",
        "latent_manual_review_first",
        "latent_defer_or_reject",
    }
    assert len(high) + len(standard) + len(manual) + len(defer) == 210
    assert set(high["quality_audit_decision"]) <= {"latent_high_priority_backfill"}
    assert set(standard["quality_audit_decision"]) <= {"latent_standard_backfill"}
    assert set(manual["quality_audit_decision"]) <= {"latent_manual_review_first"}
    assert set(defer["quality_audit_decision"]) <= {"latent_defer_or_reject"}


def test_latent_candidate_discovery_quality_audit_deterministic_and_strategy_diff_clean() -> None:
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
