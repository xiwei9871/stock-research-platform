from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_latent_candidate_discovery.py"
DOUBLER_596 = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_doubler_market_discovered_closure_v1/doubler_market_discovered_closure_master.csv"
)
QUALITY_V3 = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v3/quality_pool_layer_v3_manifest.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_candidate_discovery_v1"
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


def _codes(path: Path) -> set[str]:
    frame = pd.read_csv(path, dtype={"stock_code": str})
    return set(frame["stock_code"].astype(str).str.zfill(6))


def test_latent_candidate_discovery_outputs_and_guardrails() -> None:
    doubler_hash_before = _sha(DOUBLER_596)
    quality_hash_before = _sha(QUALITY_V3)
    _run_generator()
    doubler_hash_after = _sha(DOUBLER_596)
    quality_hash_after = _sha(QUALITY_V3)

    expected = {
        "latent_candidate_discovery_summary.json",
        "latent_candidate_discovery_universe.csv",
        "latent_evidence_completion_queue.csv",
        "latent_manual_review_queue.csv",
        "latent_data_gap_watch.csv",
        "latent_reject_or_exclude.csv",
        "latent_candidate_discovery_guardrails.json",
        "tech_bottleneck_latent_candidate_discovery_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert doubler_hash_before == doubler_hash_after
    assert quality_hash_before == quality_hash_after

    summary = json.loads((OUTPUT_DIR / "latent_candidate_discovery_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "latent_candidate_discovery_guardrails.json").read_text(encoding="utf-8"))

    assert summary["research_only"] is True
    assert summary["source_candidate_universe_count"] == 3252
    assert summary["doubled_tech_596_count"] == 596
    assert summary["quality_pool_v3_count"] == 234
    assert summary["doubled_tech_596_excluded"] is True
    assert summary["quality_pool_v3_excluded"] is True
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
        "latent_candidate_discovery_ready",
        "conditionally_ready_with_data_gaps",
    }
    assert (
        summary["latent_evidence_completion_queue_count"]
        + summary["latent_manual_review_count"]
        + summary["latent_data_gap_watch_count"]
        + summary["latent_reject_or_exclude_count"]
        == summary["latent_universe_count"]
    )

    assert guardrails["research_only"] is True
    assert guardrails["doubled_tech_596_excluded"] is True
    assert guardrails["quality_pool_v3_excluded"] is True
    assert guardrails["primary_source_backfill_performed"] is False
    assert guardrails["auto_added_to_quality_pool_count"] == 0
    assert guardrails["price_move_used_for_signal"] == 0
    assert guardrails["low_position_used_for_signal"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["lookahead_violation_rows"] == 0


def test_latent_candidate_discovery_universe_integrity() -> None:
    _run_generator()

    universe = pd.read_csv(OUTPUT_DIR / "latent_candidate_discovery_universe.csv", dtype={"stock_code": str})
    evidence = pd.read_csv(OUTPUT_DIR / "latent_evidence_completion_queue.csv", dtype={"stock_code": str})
    manual = pd.read_csv(OUTPUT_DIR / "latent_manual_review_queue.csv", dtype={"stock_code": str})
    watch = pd.read_csv(OUTPUT_DIR / "latent_data_gap_watch.csv", dtype={"stock_code": str})
    reject = pd.read_csv(OUTPUT_DIR / "latent_reject_or_exclude.csv", dtype={"stock_code": str})

    required_columns = {
        "stock_code",
        "stock_name",
        "industry",
        "tech_bottleneck_domain",
        "supply_chain_role",
        "candidate_tier",
        "not_in_doubler_596",
        "not_in_quality_pool_v3",
        "price_move_bucket",
        "low_position_research_tag",
        "hard_tech_domain_signal",
        "bottleneck_or_chokepoint_possibility",
        "business_relevance_signal",
        "concept_pollution_risk",
        "beneficiary_only_risk",
        "primary_source_feasibility",
        "next_primary_source_to_check",
        "latent_discovery_decision",
        "latent_discovery_reason",
        "recommended_next_action",
        "research_only",
        "used_for_signal",
        "used_for_admission",
        "notes",
    }
    assert required_columns.issubset(universe.columns)
    assert universe["stock_code"].nunique() == len(universe)
    assert universe["latent_discovery_decision"].notna().all()
    assert universe["recommended_next_action"].astype(str).str.len().gt(0).all()
    assert universe["not_in_doubler_596"].eq(True).all()
    assert universe["not_in_quality_pool_v3"].eq(True).all()
    assert universe["research_only"].eq(True).all()
    assert universe["used_for_signal"].eq(False).all()
    assert universe["used_for_admission"].eq(False).all()
    assert set(universe["latent_discovery_decision"]) <= {
        "latent_evidence_completion_queue",
        "latent_manual_review",
        "latent_data_gap_watch",
        "latent_reject_or_exclude",
    }
    assert set(universe["stock_code"]).isdisjoint(_codes(DOUBLER_596))
    assert set(universe["stock_code"]).isdisjoint(_codes(QUALITY_V3))
    assert len(evidence) + len(manual) + len(watch) + len(reject) == len(universe)
    assert set(evidence["latent_discovery_decision"]) <= {"latent_evidence_completion_queue"}
    assert set(manual["latent_discovery_decision"]) <= {"latent_manual_review"}
    assert set(watch["latent_discovery_decision"]) <= {"latent_data_gap_watch"}
    assert set(reject["latent_discovery_decision"]) <= {"latent_reject_or_exclude"}


def test_latent_candidate_discovery_deterministic_and_strategy_diff_clean() -> None:
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
