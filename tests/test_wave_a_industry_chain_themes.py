from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from stock_research.ai_power_source_pack import validate_theme_evidence_sources
from stock_research.industry_chain_theme_research import (
    classify_beneficiary,
    verify_deep_theme_coverage,
)
from stock_research.technology_industry_catalog import load_industry_catalog
from stock_research.theme_company_mapping import (
    load_theme_company_mapping_package,
)
from stock_research.theme_decomposition import CLAIM_FIELDS, load_theme_package
from stock_research.theme_research_priority import (
    load_theme_research_priority_package,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
THEME_ID = "ai_logic_compute_chips_value_chain_v1"
CHAIN_ID = "ai_logic_compute_chips"
THEME_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/ai_logic_compute_chips_value_chain_v1.json"
)
MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "ai_logic_compute_chips_company_mapping_v1.json"
)
SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "ai_logic_compute_chips_source_pack_v1.json"
)
MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "ai_logic_compute_chips_node_evidence_matrix_v1.json"
)
MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/batch_manifests"
    / "next_fifteen_industry_chain_themes_v1.json"
)
SCRIPT_PATH = REPOSITORY_ROOT / "scripts/verify_industry_chain_theme_batch.py"
SPEC = importlib.util.spec_from_file_location("wave_a_theme_verifier", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_ai_logic_compute_artifacts_load_through_canonical_packages():
    theme_package = load_theme_package()
    mapping_package = load_theme_company_mapping_package()
    priority_package = load_theme_research_priority_package()
    catalog = load_industry_catalog()

    assert THEME_ID in {row["theme_id"] for row in theme_package["themes"]}
    assert THEME_ID in {
        row["theme_id"] for row in mapping_package["company_mappings"]
    }
    assert THEME_ID in {
        row["theme_id"] for row in priority_package["node_priorities"]
    }
    assert next(
        row for row in catalog["theme_links"] if row["theme_id"] == THEME_ID
    )["node_links"] == []


def test_ai_logic_compute_batch_row_is_ready_before_wave_a_is_complete():
    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_a")
    row = next(row for row in report["theme_results"] if row["chain_id"] == CHAIN_ID)

    assert row["ready"] is True
    assert all(row["checks"].values())
    assert report["wave_results"]["wave_a"]["ready"] is False
    assert report["wave_results"]["wave_a"]["ready_theme_count"] == 1


def test_ai_logic_compute_research_meets_evidence_and_mapping_gates():
    theme = _read_json(THEME_PATH)
    mapping = _read_json(MAPPING_PATH)
    source_pack = _read_json(SOURCE_PACK_PATH)
    node_ids = {row["node_id"] for row in theme["nodes"]}
    accepted_sources = [
        row for row in source_pack["sources"] if row["review_status"] == "accepted"
    ]
    accepted_source_by_id = validate_theme_evidence_sources(
        source_pack["sources"], node_ids
    )
    accepted_source_ids = {
        source_id
        for source_id, row in accepted_source_by_id.items()
        if row["review_status"] == "accepted"
    }
    primary_sources = [
        row
        for row in accepted_sources
        if row["source_type"] in {"company_filing", "official_report", "official_article"}
    ]
    claims = theme["claims"]
    reviewed_mappings = [
        row for row in mapping["company_mappings"] if row["review_status"] == "reviewed"
    ]
    mapping_sources = {row["source_id"]: row for row in mapping["sources"]}
    mapping_evidence = {row["evidence_id"]: row for row in mapping["evidence_items"]}

    assert len(accepted_sources) >= 10
    assert len(primary_sources) >= 4
    assert len(claims) >= 10
    assert len(reviewed_mappings) >= 8
    assert len({row["source_id"] for row in source_pack["sources"]}) == len(
        source_pack["sources"]
    )
    assert len({row["claim_id"] for row in claims}) == len(claims)
    assert len({row["mapping_id"] for row in mapping["company_mappings"]}) == len(
        mapping["company_mappings"]
    )
    assert len({row["company_code"] for row in reviewed_mappings}) >= 8
    assert all(set(row) >= CLAIM_FIELDS for row in claims)
    assert all(
        row["source_id"] in accepted_source_ids
        or bool(set(row["supporting_source_ids"]) & accepted_source_ids)
        for row in claims
        if row["platform_use_status"] == "reviewed"
    )
    for row in reviewed_mappings:
        evidence = [
            {
                **mapping_evidence[evidence_id],
                "source": mapping_sources[mapping_evidence[evidence_id]["source_id"]],
            }
            for evidence_id in row["evidence_ids"]
        ]
        assert classify_beneficiary(row, evidence) != "concept_association"


def test_ai_logic_compute_matrix_covers_every_node_with_evidence_or_explicit_gap():
    theme = _read_json(THEME_PATH)
    source_pack = _read_json(SOURCE_PACK_PATH)
    matrix = _read_json(MATRIX_PATH)
    node_ids = {row["node_id"] for row in theme["nodes"]}
    accepted_source_ids = {
        row["source_id"]
        for row in source_pack["sources"]
        if row["review_status"] == "accepted"
    }
    claim_ids = {row["claim_id"] for row in theme["claims"]}

    assert {row["node_id"] for row in matrix["node_evidence_matrix"]} == node_ids
    assert len(matrix["node_evidence_matrix"]) == len(node_ids)
    for row in matrix["node_evidence_matrix"]:
        assert set(row["accepted_source_ids"]) <= accepted_source_ids
        assert set(row["supported_claim_ids"]) <= claim_ids
        assert row["accepted_source_ids"] or row["evidence_gap_status"] in {
            "evidence_gap",
            "technical_route_only",
        }


def test_ai_logic_compute_profile_claim_refs_and_skeleton_catalog_are_ready():
    theme = _read_json(THEME_PATH)
    profile = theme["research_profile"]
    claim_ids = {row["claim_id"] for row in theme["claims"]}
    node_ids = {row["node_id"] for row in theme["nodes"]}
    catalog = load_industry_catalog()
    link = next(row for row in catalog["theme_links"] if row["theme_id"] == THEME_ID)
    context = load_theme_research_priority_package()

    assert profile["catalyst_claim_ids"]
    assert profile["risk_claim_ids"]
    assert set(profile["catalyst_claim_ids"] + profile["risk_claim_ids"]) <= claim_ids
    assert link["node_links"] == []
    assert set(link["unmapped_theme_node_ids"]) == node_ids
    assert len(link["unmapped_theme_node_ids"]) == len(node_ids)

    result = verify_deep_theme_coverage(
        THEME_ID,
        catalog=catalog,
        theme_context=context,
    )
    assert result["ready"] is True
    assert all(result["checks"].values())
