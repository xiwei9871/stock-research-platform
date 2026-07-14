from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from fastapi.testclient import TestClient

from stock_research.ai_power_source_pack import validate_theme_evidence_sources
from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard.theme_research import list_theme_research_companies
from stock_research.industry_chain_theme_research import verify_deep_theme_coverage
from stock_research.technology_industry_catalog import load_industry_catalog
from stock_research.theme_company_mapping import load_theme_company_mapping_package
from stock_research.theme_decomposition import CLAIM_FIELDS, load_theme_package
from stock_research.theme_research_priority import load_theme_research_priority_package


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
THEME_ID = "semiconductor_packaging_test_advanced_packaging_value_chain_v1"
CHAIN_ID = "semiconductor_packaging_test_advanced_packaging"
THEME_PATH = REPOSITORY_ROOT / f"artifacts/theme_decomposition/{THEME_ID}.json"
MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "semiconductor_packaging_test_advanced_packaging_company_mapping_v1.json"
)
SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "semiconductor_packaging_test_advanced_packaging_source_pack_v1.json"
)
MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "semiconductor_packaging_test_advanced_packaging_node_evidence_matrix_v1.json"
)
MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/batch_manifests"
    / "next_fifteen_industry_chain_themes_v1.json"
)
SCRIPT_PATH = REPOSITORY_ROOT / "scripts/verify_industry_chain_theme_batch.py"
SPEC = importlib.util.spec_from_file_location("wave_b_theme_verifier", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _implemented_wave_chain_ids(wave: str) -> set[str]:
    manifest = _read_json(MANIFEST_PATH)
    return {
        chain_id
        for chain_id in manifest["waves"][wave]
        if all(
            (REPOSITORY_ROOT / artifact_path).is_file()
            for artifact_path in manifest["themes"][chain_id]["artifacts"].values()
        )
    }


def _assert_bidirectional_source_and_matrix_links() -> None:
    theme = _read_json(THEME_PATH)
    source_pack = _read_json(SOURCE_PACK_PATH)
    matrix = _read_json(MATRIX_PATH)
    node_ids = {row["node_id"] for row in theme["nodes"]}
    accepted_source_ids = {
        row["source_id"]
        for row in source_pack["sources"]
        if row["review_status"] == "accepted"
    }
    source_by_id = {row["source_id"]: row for row in source_pack["sources"]}
    claim_by_id = {row["claim_id"]: row for row in theme["claims"]}
    expected_claim_ids_by_source = {
        source["source_id"]: {
            claim["claim_id"]
            for claim in theme["claims"]
            if source["source_id"]
            in {claim["source_id"], *claim["supporting_source_ids"]}
        }
        for source in source_pack["sources"]
    }
    expected_claim_ids_by_node = {
        node_id: {
            claim["claim_id"]
            for claim in theme["claims"]
            if node_id in claim["affected_theme_nodes"]
        }
        for node_id in node_ids
    }

    assert {
        source["source_id"]: set(source["supported_claim_ids"])
        for source in source_pack["sources"]
    } == expected_claim_ids_by_source
    assert {row["node_id"] for row in matrix["node_evidence_matrix"]} == node_ids
    assert len(matrix["node_evidence_matrix"]) == len(node_ids)
    for row in matrix["node_evidence_matrix"]:
        row_claim_ids = set(row["supported_claim_ids"])
        assert row_claim_ids == expected_claim_ids_by_node[row["node_id"]]
        assert set(row["accepted_source_ids"]) <= accepted_source_ids
        assert row["accepted_source_ids"] or row["evidence_gap_status"] == "evidence_gap"
        for source_id in row["accepted_source_ids"]:
            source = source_by_id[source_id]
            assert row["node_id"] in source["supported_node_ids"]
            assert row_claim_ids & set(source["supported_claim_ids"])
        for claim_id in row_claim_ids:
            claim = claim_by_id[claim_id]
            assert set(row["accepted_source_ids"]) & {
                claim["source_id"],
                *claim["supporting_source_ids"],
            }


def test_advanced_packaging_artifacts_load_and_first_wave_b_row_is_ready():
    theme_package = load_theme_package()
    mapping_package = load_theme_company_mapping_package()
    priority_package = load_theme_research_priority_package()

    assert THEME_ID in {row["theme_id"] for row in theme_package["themes"]}
    assert THEME_ID in {
        row["theme_id"] for row in mapping_package["company_mappings"]
    }
    assert THEME_ID in {
        row["theme_id"] for row in priority_package["node_priorities"]
    }
    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_b")
    rows = {row["chain_id"]: row for row in report["theme_results"]}

    assert rows[CHAIN_ID]["ready"] is True
    assert all(rows[CHAIN_ID]["checks"].values())
    assert report["wave_results"]["wave_b"]["ready"] is False
    assert report["wave_results"]["wave_b"]["ready_theme_count"] == 1
    assert report["wave_results"]["wave_b"]["not_ready_theme_count"] == 4
    assert {chain_id for chain_id, row in rows.items() if row["ready"]} == (
        _implemented_wave_chain_ids("wave_b")
    )


def test_advanced_packaging_evidence_mapping_and_links_are_exact():
    _assert_bidirectional_source_and_matrix_links()
    theme = _read_json(THEME_PATH)
    mapping = _read_json(MAPPING_PATH)
    source_pack = _read_json(SOURCE_PACK_PATH)
    node_ids = {row["node_id"] for row in theme["nodes"]}
    accepted = validate_theme_evidence_sources(source_pack["sources"], node_ids)
    reviewed_mappings = [
        row for row in mapping["company_mappings"] if row["review_status"] == "reviewed"
    ]
    canonical_sources = {row["source_id"]: row for row in theme["sources"]}

    assert len([row for row in accepted.values() if row["review_status"] == "accepted"]) == 12
    assert all(
        row["source_type"] == "company_filing" and row["reliability_level"] == "S0"
        for row in source_pack["sources"]
    )
    assert len(theme["nodes"]) == 12
    assert len(theme["claims"]) == 16
    assert all(set(row) >= CLAIM_FIELDS for row in theme["claims"])
    assert len(reviewed_mappings) == 12
    assert len({row["company_code"] for row in reviewed_mappings}) == 12
    assert len({row["source_id"] for row in source_pack["sources"]}) == 12
    assert len({row["url"] for row in source_pack["sources"]}) == 12
    assert {
        row["source_id"]: row["url_or_ref"] for row in mapping["sources"]
    } == {
        source_id: row["url_or_ref"] for source_id, row in canonical_sources.items()
    }


def test_advanced_packaging_company_beneficiary_tiers_are_exact():
    expected = {
        "600584.SH": ("elastic_beneficiary", "core_business", "undisclosed"),
        "002156.SZ": ("elastic_beneficiary", "core_business", "undisclosed"),
        "002185.SZ": ("elastic_beneficiary", "core_business", "undisclosed"),
        "688362.SH": ("core_beneficiary", "core_business", "material"),
        "603005.SH": ("core_beneficiary", "core_business", "material"),
        "002916.SZ": ("core_beneficiary", "meaningful_segment", "material"),
        "002436.SZ": ("core_beneficiary", "meaningful_segment", "material"),
        "300480.SZ": ("core_beneficiary", "core_business", "material"),
        "300604.SZ": ("core_beneficiary", "core_business", "material"),
        "688200.SH": ("core_beneficiary", "core_business", "material"),
        "688630.SH": ("elastic_beneficiary", "meaningful_segment", "undisclosed"),
        "688300.SH": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
    }
    read_model = list_theme_research_companies(THEME_ID)
    response = TestClient(dashboard_app.create_app()).get(
        f"/api/research/theme-decomposition/themes/{THEME_ID}/companies"
    )

    assert response.status_code == 200
    for payload in (read_model, response.json()):
        assert payload["total"] == len(expected)
        assert {
            row["company_code"]: (
                row["beneficiary_tier"],
                row["business_materiality"],
                row["revenue_relevance"],
            )
            for row in payload["items"]
        } == expected


def test_advanced_packaging_profile_catalog_and_bonding_gap_are_ready():
    theme = _read_json(THEME_PATH)
    matrix = _read_json(MATRIX_PATH)
    profile = theme["research_profile"]
    node_ids = {row["node_id"] for row in theme["nodes"]}
    claim_ids = {row["claim_id"] for row in theme["claims"]}
    catalog = load_industry_catalog()
    link = next(row for row in catalog["theme_links"] if row["theme_id"] == THEME_ID)
    bonding = next(
        row
        for row in matrix["node_evidence_matrix"]
        if row["node_id"] == "bonding_attach_equipment_process"
    )

    assert profile["catalog_chain_id"] == CHAIN_ID
    assert profile["research_kind"] == "industry_chain_deep_research"
    assert set(profile["catalyst_claim_ids"] + profile["risk_claim_ids"]) <= claim_ids
    assert link["node_links"] == []
    assert set(link["unmapped_theme_node_ids"]) == node_ids
    # Canonical matrix schema represents "reviewed with a remaining gap" as a
    # reviewed node carrying the explicit evidence_gap status.
    assert bonding["node_review_status"] == "reviewed"
    assert bonding["evidence_gap_status"] == "evidence_gap"
    assert bonding["accepted_source_ids"]
    assert bonding["supported_claim_ids"]
    assert "bonding_attach_equipment_process" not in {
        row["mapped_node_id"] for row in _read_json(MAPPING_PATH)["company_mappings"]
    }
    result = verify_deep_theme_coverage(
        THEME_ID,
        catalog=catalog,
        theme_context=load_theme_research_priority_package(),
    )
    assert result["ready"] is True
    assert all(result["checks"].values())


def test_advanced_packaging_revenue_evidence_blocks_over_attribution():
    mapping = _read_json(MAPPING_PATH)
    evidence = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    mapping_by_company = {
        row["company_code"]: row for row in mapping["company_mappings"]
    }

    assert "387.14亿元" in evidence["advpkg_ev_600584_revenue"]["evidence_summary"]
    assert "不是先进封装独立收入" in evidence["advpkg_ev_600584_revenue"]["evidence_summary"]
    assert "272.48亿元" in evidence["advpkg_ev_002156_revenue"]["evidence_summary"]
    assert "172.11亿元" in evidence["advpkg_ev_002185_revenue"]["evidence_summary"]
    assert "16.70亿元" in evidence["advpkg_ev_002436_revenue"]["evidence_summary"]
    assert "主要为CSP" in evidence["advpkg_ev_002436_revenue"]["evidence_summary"]
    assert "FCBGA尚未大批量" in evidence["advpkg_ev_002436_revenue"]["evidence_summary"]
    assert "2.33亿元" in evidence["advpkg_ev_688630_revenue"]["evidence_summary"]
    assert "多用途" in evidence["advpkg_ev_688630_revenue"]["evidence_summary"]
    assert "6.52亿元" in evidence["advpkg_ev_688300_revenue"]["evidence_summary"]
    assert "多用途" in evidence["advpkg_ev_688300_revenue"]["evidence_summary"]
    assert "非先进封装专属" in evidence["advpkg_ev_300604_revenue"]["evidence_summary"]
    assert "非先进封装专属" in evidence["advpkg_ev_688200_revenue"]["evidence_summary"]
    assert "不可外推AI/HPC" in mapping_by_company["603005.SH"]["notes"]
    assert all(row["business_stage"] == "primary_business" for row in mapping_by_company.values())
