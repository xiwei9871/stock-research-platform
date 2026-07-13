from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_a_share_candidate_universe_v1"
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_a_share_candidate_universe.py"
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


def test_candidate_universe_outputs_and_guardrails() -> None:
    _run_generator()
    expected = {
        "a_share_universe_base.csv",
        "a_share_candidate_universe_summary.json",
        "a_share_candidate_universe.csv",
        "a_share_candidate_universe.json",
        "a_share_candidate_universe_by_domain.csv",
        "a_share_candidate_universe_by_tier.csv",
        "a_share_candidate_industry_channel.csv",
        "a_share_candidate_keyword_hits.csv",
        "a_share_candidate_evidence_links.csv",
        "a_share_candidate_seed_watchlist_overlap.csv",
        "a_share_candidate_seed_expansion.csv",
        "a_share_candidate_excluded_or_low_relevance.csv",
        "a_share_candidate_data_gaps.csv",
        "a_share_candidate_quality_audit.csv",
        "a_share_tech_bottleneck_supply_chain_nodes.csv",
        "a_share_tech_bottleneck_supply_chain_edges.csv",
        "a_share_candidate_guardrails.json",
        "tech_bottleneck_a_share_candidate_universe_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})

    summary = json.loads((OUTPUT_DIR / "a_share_candidate_universe_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "a_share_candidate_guardrails.json").read_text(encoding="utf-8"))

    assert summary["research_only"] is True
    assert guardrails["research_only"] is True
    assert guardrails["seed_watchlist_count"] == 102
    assert guardrails["candidate_total_count"] > 102
    tier_sum = (
        guardrails["tier_a_count"]
        + guardrails["tier_b_count"]
        + guardrails["tier_c_count"]
        + guardrails["watch_only_count"]
        + guardrails["risk_review_count"]
        + guardrails["excluded_count"]
    )
    assert tier_sum == guardrails["candidate_total_count"]
    assert guardrails["tier_a_beneficiary_count"] == 0
    assert guardrails["tier_a_concept_only_count"] == 0
    assert guardrails["tier_a_missing_disconfirmation_count"] == 0
    assert guardrails["tier_a_missing_next_primary_source_count"] == 0
    assert guardrails["tier_a_missing_validated_or_confirmed_evidence_count"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["baseline_admission_changed_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True
    assert guardrails["formal_strategy_files_modified"] is False
    assert guardrails["trading_language_hit_count"] == 0
    assert guardrails["execution_language_hit_count"] == 0
    assert guardrails["lookahead_violation_rows"] == 0
    assert guardrails["acceptance_decision"] in {
        "a_share_candidate_universe_ready_for_manual_review",
        "conditionally_ready_with_data_gaps",
    }


def test_candidate_universe_main_table_uses_hardened_fields() -> None:
    _run_generator()
    candidates = pd.read_csv(OUTPUT_DIR / "a_share_candidate_universe.csv")
    required_columns = {
        "stock_code",
        "ts_code",
        "stock_name",
        "trend_domain",
        "tech_bottleneck_domain",
        "supply_chain_role",
        "architecture_shift",
        "architecture_shift_score",
        "route_around_risk",
        "substitution_difficulty_score",
        "value_capture_score",
        "evidence_gate_level",
        "concept_pollution_risk",
        "bottleneck_exposure_score",
        "research_priority_score",
        "candidate_tier",
        "review_queue_type",
        "disconfirmation_trigger",
        "next_primary_source_check",
        "next_research_action",
        "candidate_reason",
        "data_gap_flags",
        "research_only",
        "used_for_signal",
        "used_for_admission",
    }
    assert required_columns.issubset(candidates.columns)
    assert len(candidates) > 102
    assert (
        candidates["candidate_reason"].fillna("").astype(str).str.strip().ne("")
        | candidates["data_gap_flags"].fillna("").astype(str).str.strip().ne("")
    ).all()
    assert candidates["research_only"].astype(bool).all()
    assert not candidates["used_for_signal"].astype(bool).any()
    assert not candidates["used_for_admission"].astype(bool).any()
    assert candidates["bottleneck_exposure_score"].between(0, 100).all()

    tier_a = candidates[candidates["candidate_tier"].eq("Tier A")]
    assert not tier_a.empty
    assert set(tier_a["supply_chain_role"]) <= {"bottleneck", "chokepoint"}
    assert not tier_a["supply_chain_role"].isin({"beneficiary", "concept_only"}).any()
    assert tier_a["disconfirmation_trigger"].fillna("").astype(str).str.strip().ne("").all()
    assert tier_a["next_primary_source_check"].fillna("").astype(str).str.strip().ne("").all()
    assert tier_a["next_research_action"].fillna("").astype(str).str.strip().ne("").all()
    assert tier_a["evidence_gate_level"].isin({"validated", "confirmed"}).all()


def test_seed_overlap_graph_and_formal_strategy_diff_are_clean() -> None:
    _run_generator()
    overlap = pd.read_csv(OUTPUT_DIR / "a_share_candidate_seed_watchlist_overlap.csv")
    nodes = pd.read_csv(OUTPUT_DIR / "a_share_tech_bottleneck_supply_chain_nodes.csv")
    edges = pd.read_csv(OUTPUT_DIR / "a_share_tech_bottleneck_supply_chain_edges.csv")
    guardrails = json.loads((OUTPUT_DIR / "a_share_candidate_guardrails.json").read_text(encoding="utf-8"))

    assert len(overlap) == 102
    assert overlap["in_seed_watchlist"].astype(bool).all()
    assert int(overlap["in_candidate_universe"].astype(bool).sum()) == guardrails["seed_overlap_count"]
    assert {"Tier A", "Tier B", "Tier C", "Watch Only", "Risk Review", "Excluded"}.issuperset(
        set(overlap["candidate_tier"].fillna(""))
    )
    assert {"trend", "system", "module", "component", "material", "equipment", "process", "certification", "capacity", "listed_company"}.issubset(
        set(nodes["node_type"])
    )
    assert {"depends_on", "supplies_to", "substitutable_by", "requires_certification_from", "capacity_constrained_by", "architecture_depends_on", "value_captured_by", "risk_from"}.issubset(
        set(edges["edge_type"])
    )
    assert len(nodes) == guardrails["supply_chain_nodes_count"]
    assert len(edges) == guardrails["supply_chain_edges_count"]

    diff = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert diff.stdout == ""
