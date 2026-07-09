from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
SCRIPT = PROJECT_ROOT / "scripts/run_tech_bottleneck_latent_manual_review_standard_backfill.py"
COLLECTION_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_manual_review_standard_collection_v1"
SOURCES = COLLECTION_DIR / "latent_manual_review_standard_collection_sources.csv"
DOWNLOADS = COLLECTION_DIR / "latent_manual_review_standard_collection_download_manifest.csv"
COLLECTION_SUMMARY = COLLECTION_DIR / "latent_manual_review_standard_collection_summary.json"
INPUT_QUEUE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_manual_review_first_triage_v1/latent_manual_review_standard_collection_queue.csv"
)
HIGH_PRIORITY_QUEUE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_manual_review_first_triage_v1/latent_manual_review_high_priority_collection_queue.csv"
)
HUMAN_QUEUE = (
    PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_manual_review_first_triage_v1/latent_manual_review_human_confirm_first.csv"
)
QUALITY_POOL_V5 = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v5/quality_pool_layer_v5_manifest.csv"
V6_PROPOSAL = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_quality_pool_layer_v6_proposal_v1/tech_bottleneck_quality_pool_layer_v6_proposal.csv"
)
V6_MANUAL = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_quality_pool_layer_v6_manual_approval_v1/tech_bottleneck_quality_pool_layer_v6_manual_approval_packet.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_manual_review_standard_backfill_v1"
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


def test_latent_manual_review_standard_backfill_outputs_and_guardrails() -> None:
    input_hashes_before = {
        "sources": _sha(SOURCES),
        "downloads": _sha(DOWNLOADS),
        "collection_summary": _sha(COLLECTION_SUMMARY),
        "queue": _sha(INPUT_QUEUE),
        "high_priority": _sha(HIGH_PRIORITY_QUEUE),
        "human": _sha(HUMAN_QUEUE),
        "quality_pool_v5": _sha(QUALITY_POOL_V5),
        "v6_proposal": _sha(V6_PROPOSAL),
        "v6_manual": _sha(V6_MANUAL),
    }
    _run_generator()
    input_hashes_after = {
        "sources": _sha(SOURCES),
        "downloads": _sha(DOWNLOADS),
        "collection_summary": _sha(COLLECTION_SUMMARY),
        "queue": _sha(INPUT_QUEUE),
        "high_priority": _sha(HIGH_PRIORITY_QUEUE),
        "human": _sha(HUMAN_QUEUE),
        "quality_pool_v5": _sha(QUALITY_POOL_V5),
        "v6_proposal": _sha(V6_PROPOSAL),
        "v6_manual": _sha(V6_MANUAL),
    }

    expected = {
        "latent_manual_review_standard_backfill_summary.json",
        "latent_manual_review_standard_backfill_evidence.csv",
        "latent_manual_review_standard_backfill_stock_status.csv",
        "latent_manual_review_standard_backfill_page_citations.csv",
        "latent_manual_review_standard_backfill_parse_gaps.csv",
        "latent_manual_review_standard_backfill_guardrails.json",
        "tech_bottleneck_latent_manual_review_standard_backfill_v1_report.md",
    }
    assert OUTPUT_DIR.exists()
    assert expected.issubset({path.name for path in OUTPUT_DIR.iterdir()})
    assert input_hashes_before == input_hashes_after

    summary = json.loads((OUTPUT_DIR / "latent_manual_review_standard_backfill_summary.json").read_text(encoding="utf-8"))
    guardrails = json.loads((OUTPUT_DIR / "latent_manual_review_standard_backfill_guardrails.json").read_text(encoding="utf-8"))

    assert summary["research_only"] is True
    assert summary["source_standard_collection_stock_count"] == 52
    assert summary["source_standard_collection_pdf_count"] == 156
    assert summary["processed_stock_count"] == 52
    assert summary["processed_pdf_count"] == 156
    assert summary["evidence_backfill_performed"] is True
    assert summary["core_equivalence_performed"] is False
    assert summary["quality_pool_v5_processed"] is False
    assert summary["quality_pool_v6_proposal_processed"] is False
    assert summary["frozen_quality_pool_v6_generated"] is False
    assert summary["auto_added_to_quality_pool_count"] == 0
    assert summary["price_move_used_for_signal"] == 0
    assert summary["low_position_used_for_signal"] == 0
    assert summary["used_for_signal_count"] == 0
    assert summary["used_for_admission_count"] == 0
    assert summary["strategy_file_diff_clean"] is True
    assert summary["formal_strategy_files_modified"] is False
    assert summary["acceptance_decision"] in {
        "latent_manual_review_standard_backfill_ready",
        "conditionally_ready_with_parse_gaps",
        "conditionally_ready_with_partial_support",
    }

    assert guardrails["research_only"] is True
    assert guardrails["source_standard_collection_stock_count"] == 52
    assert guardrails["source_standard_collection_pdf_count"] == 156
    assert guardrails["processed_stock_count"] == 52
    assert guardrails["processed_pdf_count"] == 156
    assert guardrails["evidence_backfill_performed"] is True
    assert guardrails["core_equivalence_performed"] is False
    assert guardrails["quality_pool_v5_processed"] is False
    assert guardrails["quality_pool_v6_proposal_processed"] is False
    assert guardrails["frozen_quality_pool_v6_generated"] is False
    assert guardrails["auto_added_to_quality_pool_count"] == 0
    assert guardrails["price_move_used_for_signal"] == 0
    assert guardrails["low_position_used_for_signal"] == 0
    assert guardrails["used_for_signal_count"] == 0
    assert guardrails["used_for_admission_count"] == 0
    assert guardrails["strategy_file_diff_clean"] is True


def test_latent_manual_review_standard_backfill_scope_and_outputs() -> None:
    _run_generator()

    queue = pd.read_csv(INPUT_QUEUE, dtype={"stock_code": str})
    high_priority = pd.read_csv(HIGH_PRIORITY_QUEUE, dtype={"stock_code": str})
    human = pd.read_csv(HUMAN_QUEUE, dtype={"stock_code": str})
    quality_pool_v5 = pd.read_csv(QUALITY_POOL_V5, dtype={"stock_code": str})
    v6_proposal = pd.read_csv(V6_PROPOSAL, dtype={"stock_code": str})
    v6_manual = pd.read_csv(V6_MANUAL, dtype={"stock_code": str})
    evidence = pd.read_csv(OUTPUT_DIR / "latent_manual_review_standard_backfill_evidence.csv", dtype={"stock_code": str})
    stock_status = pd.read_csv(
        OUTPUT_DIR / "latent_manual_review_standard_backfill_stock_status.csv",
        dtype={"stock_code": str},
    )
    citations = pd.read_csv(
        OUTPUT_DIR / "latent_manual_review_standard_backfill_page_citations.csv",
        dtype={"stock_code": str},
    )
    parse_gaps = pd.read_csv(OUTPUT_DIR / "latent_manual_review_standard_backfill_parse_gaps.csv", dtype={"stock_code": str})

    expected_codes = set(queue["stock_code"].astype(str).str.zfill(6))
    assert len(queue) == 52
    assert len(stock_status) == 52
    assert set(stock_status["stock_code"].astype(str).str.zfill(6)) == expected_codes
    assert expected_codes.isdisjoint(set(high_priority["stock_code"].astype(str).str.zfill(6)))
    assert expected_codes.isdisjoint(set(human["stock_code"].astype(str).str.zfill(6)))
    assert expected_codes.isdisjoint(set(quality_pool_v5["stock_code"].astype(str).str.zfill(6)))
    assert expected_codes.isdisjoint(set(v6_proposal["stock_code"].astype(str).str.zfill(6)))
    assert expected_codes.isdisjoint(set(v6_manual["stock_code"].astype(str).str.zfill(6)))

    assert set(stock_status["backfill_status"]).issubset(
        {
            "primary_source_supported",
            "partially_supported",
            "insufficient_primary_source_evidence",
            "parse_failed_or_unusable",
        }
    )
    assert stock_status["research_only"].eq(True).all()
    assert stock_status["used_for_signal"].eq(False).all()
    assert stock_status["used_for_admission"].eq(False).all()
    assert stock_status["core_equivalence_performed"].eq(False).all()
    assert stock_status["quality_pool_v5_processed"].eq(False).all()
    assert stock_status["quality_pool_v6_proposal_processed"].eq(False).all()
    assert stock_status["frozen_quality_pool_v6_generated"].eq(False).all()

    required_evidence_columns = {
        "stock_code",
        "stock_name",
        "source_file",
        "source_type",
        "source_title",
        "source_date",
        "page",
        "evidence_text",
        "evidence_claim_type",
        "hard_tech_domain",
        "supply_chain_role_hint",
        "business_relevance_hint",
        "bottleneck_or_chokepoint_hint",
        "concept_pollution_risk",
        "citation_quality",
        "backfill_status",
        "next_action_hint",
    }
    assert required_evidence_columns.issubset(evidence.columns)
    if not evidence.empty:
        assert set(evidence["stock_code"].astype(str).str.zfill(6)).issubset(expected_codes)
        assert evidence["citation_quality"].isin(["page_level"]).all()
        assert evidence["page"].astype(str).str.len().gt(0).all()
        assert evidence["evidence_text"].astype(str).str.len().gt(0).all()

    if not citations.empty:
        assert set(citations["stock_code"].astype(str).str.zfill(6)).issubset(expected_codes)
        assert citations["citation_quality"].eq("page_level").all()
        assert citations["page"].astype(str).str.len().gt(0).all()
        assert citations["evidence_text"].astype(str).str.len().gt(0).all()

    if not parse_gaps.empty:
        assert set(parse_gaps["stock_code"].astype(str).str.zfill(6)).issubset(expected_codes)


def test_latent_manual_review_standard_backfill_deterministic_and_strategy_diff_clean() -> None:
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
