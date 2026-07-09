from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd

from stock_research import tech_bottleneck_review_universe_frontend_dataset as frontend_dataset


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_review_universe_frontend_dataset.py"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1"
V5_HYDRATED = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_v5_evidence_hydration_v1/tech_bottleneck_review_universe_v5_hydrated_frontend_ready.csv"
)
TARGETED = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_targeted_evidence_collection_v1/tech_bottleneck_review_universe_targeted_evidence_frontend_ready.csv"
)
V7_PROPOSAL = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v7_proposal_v1/tech_bottleneck_quality_pool_layer_v7_proposal.csv"
)
V7_LEDGER = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v7_manual_approval_ingest_v1/v7_manual_approval_ledger.csv"
)
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


def test_frontend_dataset_outputs_summary_and_guardrails() -> None:
    input_hashes_before = {
        "v5_hydrated": _sha(V5_HYDRATED),
        "targeted": _sha(TARGETED),
        "v7_proposal": _sha(V7_PROPOSAL),
        "v7_ledger": _sha(V7_LEDGER),
    }
    _run_generator()
    input_hashes_after = {
        "v5_hydrated": _sha(V5_HYDRATED),
        "targeted": _sha(TARGETED),
        "v7_proposal": _sha(V7_PROPOSAL),
        "v7_ledger": _sha(V7_LEDGER),
    }
    expected = {
        "tech_bottleneck_review_universe_frontend_dataset_summary.json",
        "tech_bottleneck_review_universe_frontend_dataset.csv",
        "tech_bottleneck_review_universe_frontend_evidence_index.csv",
        "tech_bottleneck_review_universe_frontend_source_index.csv",
        "tech_bottleneck_review_universe_frontend_filter_options.json",
        "tech_bottleneck_review_universe_frontend_guardrails.json",
        "tech_bottleneck_review_universe_frontend_dataset_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hashes_before == input_hashes_after

    summary = json.loads((OUTPUT_DIR / "tech_bottleneck_review_universe_frontend_dataset_summary.json").read_text())
    guardrails = json.loads((OUTPUT_DIR / "tech_bottleneck_review_universe_frontend_guardrails.json").read_text())
    assert summary["review_universe_total_count"] == 378
    assert summary["v5_hydrated_count"] == 271
    assert summary["v7_proposal_new_count"] == 78
    assert summary["v5_targeted_hydrated_count"] == 29
    assert summary["frontend_dataset_count"] == 378
    assert summary["duplicate_stock_count"] == 0
    assert summary["remaining_evidence_gap_count"] == 0
    assert summary["primary_source_collection_performed"] is False
    assert summary["new_pdf_download_count"] == 0
    assert summary["evidence_backfill_performed"] is False
    assert summary["core_equivalence_performed"] is False
    assert summary["frontend_write_performed"] is False
    assert summary["dashboard_code_modified"] is False
    assert summary["frozen_quality_pool_generated"] is False
    assert summary["auto_added_to_quality_pool_count"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["price_move_used_for_signal"] == 0
    assert summary["low_position_used_for_signal"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["acceptance_decision"] == "tech_bottleneck_review_universe_frontend_dataset_ready"
    assert guardrails["frontend_dataset_count"] == 378
    assert guardrails["dashboard_code_modified"] is False


def test_frontend_dataset_rows_fields_and_indexes() -> None:
    _run_generator()
    dataset = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_review_universe_frontend_dataset.csv",
        dtype={"stock_code": str},
    ).fillna("")
    evidence = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_review_universe_frontend_evidence_index.csv",
        dtype={"stock_code": str},
    ).fillna("")
    sources = pd.read_csv(
        OUTPUT_DIR / "tech_bottleneck_review_universe_frontend_source_index.csv",
        dtype={"stock_code": str},
    ).fillna("")
    filters = json.loads((OUTPUT_DIR / "tech_bottleneck_review_universe_frontend_filter_options.json").read_text())

    assert len(dataset) == 378
    assert dataset["stock_code"].nunique() == 378
    assert dataset["review_universe_source"].value_counts().to_dict() == {
        "v5_hydrated": 271,
        "v7_proposal_new": 78,
        "v5_targeted_hydrated": 29,
    }
    required_columns = {
        "stock_code",
        "stock_name",
        "review_universe_source",
        "current_layer_status",
        "manual_approval_status",
        "frontend_review_status",
        "evidence_count",
        "page_citation_count",
        "source_pdf_count",
        "primary_source_supported",
        "hard_tech_domain",
        "supply_chain_role_hint",
        "business_relevance_hint",
        "bottleneck_or_chokepoint_hint",
        "concept_pollution_risk",
        "route_around_or_substitution_risk",
        "value_capture_risk",
        "disconfirmation_trigger",
        "next_primary_source_to_check",
        "strongest_primary_source_claim",
        "weakest_or_riskiest_claim",
        "evidence_summary_for_review",
        "reviewer_decision",
        "reviewer_note",
        "used_for_signal",
        "used_for_admission",
        "auto_added_to_quality_pool",
        "industry",
        "concept_tags",
        "evidence_strength",
        "bottleneck_relevance",
        "source_group",
        "previous_tier",
        "bottleneck_confidence_score",
        "evidence_quality_score",
    }
    assert required_columns.issubset(dataset.columns)
    assert set(dataset["frontend_review_status"]) == {"pending_review"}
    assert set(dataset["reviewer_decision"]) == {""}
    assert dataset["used_for_signal"].eq(False).all()
    assert dataset["used_for_admission"].eq(False).all()
    assert dataset["auto_added_to_quality_pool"].eq(False).all()
    assert dataset["evidence_count"].astype(int).gt(0).all()
    assert dataset["page_citation_count"].astype(int).gt(0).all()
    assert dataset["source_pdf_count"].astype(int).gt(0).all()
    assert dataset["industry"].astype(str).str.len().gt(0).all()
    assert not dataset["industry"].isin(["未映射", ""]).any()
    assert dataset["concept_tags"].astype(str).str.len().gt(0).all()
    assert not dataset["concept_tags"].isin(["未映射", ""]).any()
    assert dataset["evidence_strength"].astype(str).str.len().gt(0).all()
    assert not dataset["evidence_strength"].isin(["missing", ""]).any()
    assert dataset["bottleneck_relevance"].astype(str).str.len().gt(0).all()
    assert not dataset["bottleneck_relevance"].isin(["missing", "unclear", ""]).any()
    assert dataset["source_group"].astype(str).str.len().gt(0).all()
    assert dataset["previous_tier"].astype(str).str.len().gt(0).all()
    assert dataset["bottleneck_confidence_score"].astype(str).ne("-").all()
    assert dataset["evidence_quality_score"].astype(str).ne("-").all()
    assert dataset["bottleneck_confidence_score"].astype(float).between(45, 95).all()
    assert dataset["evidence_quality_score"].astype(float).between(20, 90).all()
    assert set(evidence["stock_code"]) == set(dataset["stock_code"])
    assert set(sources["stock_code"]) == set(dataset["stock_code"])
    for key in [
        "review_universe_source",
        "current_layer_status",
        "manual_approval_status",
        "hard_tech_domain",
        "supply_chain_role_hint",
        "concept_pollution_risk",
        "primary_source_supported",
        "frontend_review_status",
        "reviewer_decision",
    ]:
        assert key in filters


def test_frontend_dataset_deterministic_and_strategy_diff_clean() -> None:
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


def test_frontend_dataset_prefers_database_stock_metadata(monkeypatch) -> None:
    v5_hydrated = pd.DataFrame(
        [
            {
                "stock_code": "000551",
                "stock_name": "创元科技",
                "current_layer_status": "false_negative_rescue_core_equivalent_quality_pool",
                "evidence_count": 42,
                "page_citation_count": 21,
                "source_pdf_count": 3,
                "primary_source_supported": True,
                "hard_tech_domain": "supported",
                "supply_chain_role_hint": "supported",
                "business_relevance_hint": "supported",
                "bottleneck_or_chokepoint_hint": "strong",
                "concept_pollution_risk": "not_detected_in_existing_artifacts",
            }
        ]
    )
    targeted = pd.DataFrame(columns=v5_hydrated.columns)
    v7 = pd.DataFrame(columns=["stock_code"])
    ledger = pd.DataFrame(columns=["stock_code"])
    universe = pd.DataFrame(
        [
            {
                "stock_code": "000551",
                "industry": "CSV旧行业",
                "tech_bottleneck_domain": "CSV旧概念",
                "tech_bottleneck_sub_domain": "CSV旧子概念",
                "supply_chain_role": "concept_only",
                "candidate_tier": "Excluded",
            }
        ]
    )
    report_status = pd.DataFrame(columns=["stock_code"])
    db_metadata = pd.DataFrame(
        [
            {
                "stock_code": "000551",
                "industry": "专用设备制造业",
                "concept_tags": "机器人概念 / 高端装备",
                "industry_source": "baostock",
                "concept_source": "akshare:concept_constituents",
            }
        ]
    )

    monkeypatch.setattr(frontend_dataset, "_load_database_stock_metadata", lambda stock_codes: db_metadata)

    dataset = frontend_dataset._build_dataset(v5_hydrated, targeted, v7, ledger, universe, report_status)
    row = dataset.iloc[0]

    assert row["industry"] == "专用设备制造业"
    assert row["concept_tags"] == "机器人概念 / 高端装备"
    assert row["source_group"] == "v5_hydrated"
