from __future__ import annotations

import importlib.util
import json
import re
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
    assert report["wave_results"]["wave_b"]["ready"] is True
    assert report["wave_results"]["wave_b"]["ready_theme_count"] == 5
    assert report["wave_results"]["wave_b"]["not_ready_theme_count"] == 0
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


SMART_GRID_THEME_ID = "new_power_system_smart_grid_value_chain_v1"
SMART_GRID_CHAIN_ID = "new_power_system_smart_grid"
SMART_GRID_THEME_PATH = (
    REPOSITORY_ROOT / f"artifacts/theme_decomposition/{SMART_GRID_THEME_ID}.json"
)
SMART_GRID_MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "new_power_system_smart_grid_company_mapping_v1.json"
)
SMART_GRID_SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "new_power_system_smart_grid_source_pack_v1.json"
)
SMART_GRID_MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "new_power_system_smart_grid_node_evidence_matrix_v1.json"
)


def _assert_smart_grid_bidirectional_source_and_matrix_links() -> None:
    theme = _read_json(SMART_GRID_THEME_PATH)
    source_pack = _read_json(SMART_GRID_SOURCE_PACK_PATH)
    matrix = _read_json(SMART_GRID_MATRIX_PATH)
    node_ids = {row["node_id"] for row in theme["nodes"]}
    accepted_source_ids = {
        row["source_id"]
        for row in source_pack["sources"]
        if row["review_status"] == "accepted"
    }
    source_by_id = {row["source_id"]: row for row in source_pack["sources"]}
    claim_by_id = {row["claim_id"]: row for row in theme["claims"]}

    assert {
        source["source_id"]: set(source["supported_claim_ids"])
        for source in source_pack["sources"]
    } == {
        source["source_id"]: {
            claim["claim_id"]
            for claim in theme["claims"]
            if source["source_id"]
            in {claim["source_id"], *claim["supporting_source_ids"]}
        }
        for source in source_pack["sources"]
    }
    assert {row["node_id"] for row in matrix["node_evidence_matrix"]} == node_ids
    assert len(matrix["node_evidence_matrix"]) == len(node_ids)
    for row in matrix["node_evidence_matrix"]:
        expected_claim_ids = {
            claim["claim_id"]
            for claim in theme["claims"]
            if row["node_id"] in claim["affected_theme_nodes"]
        }
        assert set(row["supported_claim_ids"]) == expected_claim_ids
        assert set(row["accepted_source_ids"]) <= accepted_source_ids
        assert row["accepted_source_ids"]
        for source_id in row["accepted_source_ids"]:
            source = source_by_id[source_id]
            assert row["node_id"] in source["supported_node_ids"]
            assert expected_claim_ids & set(source["supported_claim_ids"])
        for claim_id in expected_claim_ids:
            claim = claim_by_id[claim_id]
            assert set(row["accepted_source_ids"]) & {
                claim["source_id"],
                *claim["supporting_source_ids"],
            }


def test_smart_grid_artifacts_load_and_second_wave_b_row_is_ready():
    theme_package = load_theme_package()
    mapping_package = load_theme_company_mapping_package()
    priority_package = load_theme_research_priority_package()

    assert SMART_GRID_THEME_ID in {row["theme_id"] for row in theme_package["themes"]}
    assert SMART_GRID_THEME_ID in {
        row["theme_id"] for row in mapping_package["company_mappings"]
    }
    assert SMART_GRID_THEME_ID in {
        row["theme_id"] for row in priority_package["node_priorities"]
    }
    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_b")
    rows = {row["chain_id"]: row for row in report["theme_results"]}

    assert rows[SMART_GRID_CHAIN_ID]["ready"] is True
    assert all(rows[SMART_GRID_CHAIN_ID]["checks"].values())
    assert report["wave_results"]["wave_b"]["ready"] is True
    assert report["wave_results"]["wave_b"]["ready_theme_count"] == 5
    assert report["wave_results"]["wave_b"]["not_ready_theme_count"] == 0
    assert {chain_id for chain_id, row in rows.items() if row["ready"]} == (
        _implemented_wave_chain_ids("wave_b")
    )


def test_smart_grid_evidence_mapping_and_links_are_exact():
    _assert_smart_grid_bidirectional_source_and_matrix_links()
    theme = _read_json(SMART_GRID_THEME_PATH)
    mapping = _read_json(SMART_GRID_MAPPING_PATH)
    source_pack = _read_json(SMART_GRID_SOURCE_PACK_PATH)
    node_ids = {row["node_id"] for row in theme["nodes"]}
    accepted = validate_theme_evidence_sources(source_pack["sources"], node_ids)
    reviewed_mappings = [
        row for row in mapping["company_mappings"] if row["review_status"] == "reviewed"
    ]
    canonical_sources = {row["source_id"]: row for row in theme["sources"]}

    assert len([row for row in accepted.values() if row["review_status"] == "accepted"]) == 10
    assert all(
        row["source_type"] == "company_filing" and row["reliability_level"] == "S0"
        for row in source_pack["sources"]
    )
    assert len(theme["nodes"]) == 10
    assert len(theme["claims"]) == 15
    assert all(set(row) >= CLAIM_FIELDS for row in theme["claims"])
    assert len(reviewed_mappings) == 10
    assert len({row["company_code"] for row in reviewed_mappings}) == 10
    assert len({row["source_id"] for row in source_pack["sources"]}) == 10
    assert len({row["url"] for row in source_pack["sources"]}) == 10
    assert {
        row["source_id"]: row["url_or_ref"] for row in mapping["sources"]
    } == {
        source_id: row["url_or_ref"] for source_id, row in canonical_sources.items()
    }


def test_smart_grid_company_beneficiary_tiers_follow_classifier_exactly():
    expected = {
        "600406.SH": ("elastic_beneficiary", "core_business", "undisclosed"),
        "000400.SZ": ("elastic_beneficiary", "meaningful_segment", "limited"),
        "600312.SH": ("core_beneficiary", "core_business", "material"),
        "601179.SH": ("core_beneficiary", "core_business", "material"),
        "601126.SH": ("elastic_beneficiary", "core_business", "undisclosed"),
        "000682.SZ": ("elastic_beneficiary", "core_business", "undisclosed"),
        "688100.SH": ("core_beneficiary", "core_business", "material"),
        "603556.SH": ("elastic_beneficiary", "core_business", "undisclosed"),
        "002028.SZ": ("elastic_beneficiary", "meaningful_segment", "undisclosed"),
        "600131.SH": ("indirect_beneficiary", "meaningful_segment", "undisclosed"),
    }
    read_model = list_theme_research_companies(SMART_GRID_THEME_ID)
    response = TestClient(dashboard_app.create_app()).get(
        f"/api/research/theme-decomposition/themes/{SMART_GRID_THEME_ID}/companies"
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


def test_smart_grid_profile_catalog_and_unmapped_nodes_are_ready():
    theme = _read_json(SMART_GRID_THEME_PATH)
    profile = theme["research_profile"]
    node_ids = {row["node_id"] for row in theme["nodes"]}
    claim_ids = {row["claim_id"] for row in theme["claims"]}
    catalog = load_industry_catalog()
    link = next(
        row for row in catalog["theme_links"] if row["theme_id"] == SMART_GRID_THEME_ID
    )

    assert profile["catalog_chain_id"] == SMART_GRID_CHAIN_ID
    assert profile["research_kind"] == "industry_chain_deep_research"
    assert set(profile["catalyst_claim_ids"] + profile["risk_claim_ids"]) <= claim_ids
    assert link["node_links"] == [
        {"theme_node_id": "uhv_hvdc_flexible_dc", "catalog_node_id": "grid_connection_transmission_protection"},
        {"theme_node_id": "primary_power_transformers", "catalog_node_id": "power_transformer"},
    ]
    assert "阶段级L3覆盖" in link["notes"]
    assert "不是柔直或换流阀产品等价映射" in link["notes"]
    assert "protection_substation_automation" in link["unmapped_theme_node_ids"]
    assert "storage_grid_connection_power_quality" in link["unmapped_theme_node_ids"]
    assert "relay_protection_system" not in {
        row["catalog_node_id"] for row in link["node_links"]
    }
    assert "power_quality_management_system" not in {
        row["catalog_node_id"] for row in link["node_links"]
    }
    assert set(link["unmapped_theme_node_ids"]) == node_ids - {
        row["theme_node_id"] for row in link["node_links"]
    }
    result = verify_deep_theme_coverage(
        SMART_GRID_THEME_ID,
        catalog=catalog,
        theme_context=load_theme_research_priority_package(),
    )
    assert result["ready"] is True
    assert all(result["checks"].values())


def test_smart_grid_revenue_and_scope_boundaries_block_over_attribution():
    theme = _read_json(SMART_GRID_THEME_PATH)
    mapping = _read_json(SMART_GRID_MAPPING_PATH)
    evidence = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    mapping_by_company = {
        row["company_code"]: row for row in mapping["company_mappings"]
    }
    claim_text = " ".join(row["claim_text"] for row in theme["claims"])

    assert "334.22亿元" in evidence["smartgrid_ev_600406_revenue"]["evidence_summary"]
    assert "不是单一调度或柔直收入" in evidence["smartgrid_ev_600406_revenue"]["evidence_summary"]
    assert "77.47亿元" in evidence["smartgrid_ev_600312_revenue"]["evidence_summary"]
    assert "不是特高压独立收入" in evidence["smartgrid_ev_600312_revenue"]["evidence_summary"]
    assert "39.72亿元" in evidence["smartgrid_ev_601179_revenue"]["evidence_summary"]
    assert "不能强映射为柔直收入" in evidence["smartgrid_ev_601179_revenue"]["evidence_summary"]
    assert "41.69亿元" in evidence["smartgrid_ev_603556_revenue"]["evidence_summary"]
    assert "不等于电表独立收入" in evidence["smartgrid_ev_603556_revenue"]["evidence_summary"]
    assert "15.25亿元" in evidence["smartgrid_ev_002028_revenue"]["evidence_summary"]
    assert "15.31亿元" in evidence["smartgrid_ev_002028_revenue"]["evidence_summary"]
    assert "不是柔直突破的独立收入" in evidence["smartgrid_ev_002028_revenue"]["evidence_summary"]
    assert "53.78亿元" in evidence["smartgrid_ev_600131_revenue"]["evidence_summary"]
    assert "25.01亿元" in evidence["smartgrid_ev_600131_revenue"]["evidence_summary"]
    assert "不等于AI或单一软件收入" in evidence["smartgrid_ev_600131_revenue"]["evidence_summary"]
    assert "直流输电系统收入同比下降" in claim_text
    assert "通信模块收入下降、通信网关收入增长" in claim_text
    assert "集中招标价格" in claim_text
    assert mapping_by_company["600131.SH"]["bottleneck_relevance"] == "adjacent"


CORE_MECHANICAL_THEME_ID = "core_mechanical_components_value_chain_v1"
CORE_MECHANICAL_CHAIN_ID = "core_mechanical_components"
CORE_MECHANICAL_THEME_PATH = (
    REPOSITORY_ROOT / f"artifacts/theme_decomposition/{CORE_MECHANICAL_THEME_ID}.json"
)
CORE_MECHANICAL_MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "core_mechanical_components_company_mapping_v1.json"
)
CORE_MECHANICAL_SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "core_mechanical_components_source_pack_v1.json"
)
CORE_MECHANICAL_MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "core_mechanical_components_node_evidence_matrix_v1.json"
)


def _assert_core_mechanical_bidirectional_source_and_matrix_links() -> None:
    theme = _read_json(CORE_MECHANICAL_THEME_PATH)
    source_pack = _read_json(CORE_MECHANICAL_SOURCE_PACK_PATH)
    matrix = _read_json(CORE_MECHANICAL_MATRIX_PATH)
    node_ids = {row["node_id"] for row in theme["nodes"]}
    accepted_source_ids = {
        row["source_id"]
        for row in source_pack["sources"]
        if row["review_status"] == "accepted"
    }
    source_by_id = {row["source_id"]: row for row in source_pack["sources"]}
    claim_by_id = {row["claim_id"]: row for row in theme["claims"]}
    matrix_by_node = {
        row["node_id"]: row for row in matrix["node_evidence_matrix"]
    }

    assert {
        source["source_id"]: set(source["supported_claim_ids"])
        for source in source_pack["sources"]
    } == {
        source["source_id"]: {
            claim["claim_id"]
            for claim in theme["claims"]
            if source["source_id"]
            in {claim["source_id"], *claim["supporting_source_ids"]}
        }
        for source in source_pack["sources"]
    }
    assert {row["node_id"] for row in matrix["node_evidence_matrix"]} == node_ids
    assert len(matrix["node_evidence_matrix"]) == len(node_ids)
    for row in matrix["node_evidence_matrix"]:
        expected_claim_ids = {
            claim["claim_id"]
            for claim in theme["claims"]
            if row["node_id"] in claim["affected_theme_nodes"]
        }
        assert set(row["supported_claim_ids"]) == expected_claim_ids
        assert set(row["accepted_source_ids"]) <= accepted_source_ids
        assert row["accepted_source_ids"] or row["evidence_gap_status"] == "evidence_gap"
        for source_id in row["accepted_source_ids"]:
            source = source_by_id[source_id]
            assert row["node_id"] in source["supported_node_ids"]
            assert expected_claim_ids & set(source["supported_claim_ids"])
        for claim_id in expected_claim_ids:
            claim = claim_by_id[claim_id]
            if row["accepted_source_ids"]:
                assert set(row["accepted_source_ids"]) & {
                    claim["source_id"],
                    *claim["supporting_source_ids"],
                }
            else:
                assert row["evidence_gap_status"] == "evidence_gap"
                assert claim["claim_type"] == "risk"
    for source in source_pack["sources"]:
        for node_id in source["supported_node_ids"]:
            assert set(source["supported_claim_ids"]) & set(
                matrix_by_node[node_id]["supported_claim_ids"]
            )


def test_core_mechanical_artifacts_load_and_third_wave_b_row_is_ready():
    theme_package = load_theme_package()
    mapping_package = load_theme_company_mapping_package()
    priority_package = load_theme_research_priority_package()

    assert CORE_MECHANICAL_THEME_ID in {
        row["theme_id"] for row in theme_package["themes"]
    }
    assert CORE_MECHANICAL_THEME_ID in {
        row["theme_id"] for row in mapping_package["company_mappings"]
    }
    assert CORE_MECHANICAL_THEME_ID in {
        row["theme_id"] for row in priority_package["node_priorities"]
    }
    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_b")
    rows = {row["chain_id"]: row for row in report["theme_results"]}

    assert rows[CORE_MECHANICAL_CHAIN_ID]["ready"] is True
    assert all(rows[CORE_MECHANICAL_CHAIN_ID]["checks"].values())
    assert report["wave_results"]["wave_b"]["ready"] is True
    assert report["wave_results"]["wave_b"]["ready_theme_count"] == 5
    assert report["wave_results"]["wave_b"]["not_ready_theme_count"] == 0
    assert {chain_id for chain_id, row in rows.items() if row["ready"]} == (
        _implemented_wave_chain_ids("wave_b")
    )


def test_core_mechanical_evidence_mapping_and_duplicate_company_are_exact():
    _assert_core_mechanical_bidirectional_source_and_matrix_links()
    theme = _read_json(CORE_MECHANICAL_THEME_PATH)
    mapping = _read_json(CORE_MECHANICAL_MAPPING_PATH)
    source_pack = _read_json(CORE_MECHANICAL_SOURCE_PACK_PATH)
    node_ids = {row["node_id"] for row in theme["nodes"]}
    accepted = validate_theme_evidence_sources(source_pack["sources"], node_ids)
    reviewed_mappings = [
        row for row in mapping["company_mappings"] if row["review_status"] == "reviewed"
    ]
    canonical_sources = {row["source_id"]: row for row in theme["sources"]}
    mapping_sources = {row["source_id"]: row for row in mapping["sources"]}
    pack_sources = {row["source_id"]: row for row in source_pack["sources"]}

    assert len(
        [row for row in accepted.values() if row["review_status"] == "accepted"]
    ) == 14
    assert all(
        row["source_type"] == "company_filing" and row["reliability_level"] == "S0"
        for row in source_pack["sources"]
    )
    assert len(theme["nodes"]) == 11
    assert len(theme["claims"]) == 16
    assert all(set(row) >= CLAIM_FIELDS for row in theme["claims"])
    assert len(reviewed_mappings) == 15
    assert len({row["company_code"] for row in reviewed_mappings}) == 14
    assert [row["company_code"] for row in reviewed_mappings].count("000837.SZ") == 2
    assert {
        row["mapped_node_id"]
        for row in reviewed_mappings
        if row["company_code"] == "000837.SZ"
    } == {"ball_roller_screws_linear_guides", "precision_reducers"}
    assert len({row["source_id"] for row in source_pack["sources"]}) == 14
    assert len({row["url"] for row in source_pack["sources"]}) == 14
    assert {
        row["source_id"]: row["url_or_ref"] for row in mapping["sources"]
    } == {
        source_id: row["url_or_ref"] for source_id, row in canonical_sources.items()
    }
    for source_id, canonical_source in canonical_sources.items():
        assert {
            field: mapping_sources[source_id][field]
            for field in ("title", "publisher", "publish_date", "url_or_ref")
        } == {
            field: canonical_source[field]
            for field in ("title", "publisher", "publish_date", "url_or_ref")
        }
        assert {
            "title": pack_sources[source_id]["title"],
            "publisher": pack_sources[source_id]["publisher"],
            "publish_date": pack_sources[source_id]["publish_date"],
            "url_or_ref": pack_sources[source_id]["url"],
        } == {
            field: canonical_source[field]
            for field in ("title", "publisher", "publish_date", "url_or_ref")
        }


def test_core_mechanical_company_beneficiary_tiers_follow_classifier_exactly():
    expected = {
        ("603667.SH", "precision_rolling_bearings"): (
            "core_beneficiary",
            "core_business",
            "material",
        ),
        ("300718.SZ", "plain_self_lubricating_bearings"): (
            "core_beneficiary",
            "core_business",
            "material",
        ),
        ("000837.SZ", "ball_roller_screws_linear_guides"): (
            "elastic_beneficiary",
            "emerging_segment",
            "undisclosed",
        ),
        ("300580.SZ", "ball_roller_screws_linear_guides"): (
            "elastic_beneficiary",
            "emerging_segment",
            "undisclosed",
        ),
        ("688017.SH", "precision_reducers"): (
            "core_beneficiary",
            "core_business",
            "material",
        ),
        ("000837.SZ", "precision_reducers"): (
            "elastic_beneficiary",
            "emerging_segment",
            "undisclosed",
        ),
        ("603915.SH", "precision_gears_industrial_transmission"): (
            "core_beneficiary",
            "core_business",
            "material",
        ),
        ("002472.SZ", "precision_gears_industrial_transmission"): (
            "core_beneficiary",
            "core_business",
            "material",
        ),
        ("300503.SZ", "precision_spindles_rotary_tables"): (
            "core_beneficiary",
            "core_business",
            "material",
        ),
        ("601100.SH", "hydraulic_components"): (
            "core_beneficiary",
            "core_business",
            "material",
        ),
        ("300470.SZ", "industrial_seals"): (
            "core_beneficiary",
            "core_business",
            "material",
        ),
        ("301161.SZ", "industrial_seals"): (
            "core_beneficiary",
            "core_business",
            "material",
        ),
        ("601002.SH", "springs_fasteners"): (
            "core_beneficiary",
            "core_business",
            "material",
        ),
        ("001380.SZ", "springs_fasteners"): (
            "elastic_beneficiary",
            "emerging_segment",
            "undisclosed",
        ),
        ("688355.SH", "precision_casting_forging_surface_treatment"): (
            "core_beneficiary",
            "meaningful_segment",
            "meaningful",
        ),
    }
    read_model = list_theme_research_companies(CORE_MECHANICAL_THEME_ID)
    response = TestClient(dashboard_app.create_app()).get(
        f"/api/research/theme-decomposition/themes/{CORE_MECHANICAL_THEME_ID}/companies"
    )

    assert response.status_code == 200
    for payload in (read_model, response.json()):
        assert payload["total"] == len(expected)
        assert {
            (row["company_code"], row["mapped_node_id"]): (
                row["beneficiary_tier"],
                row["business_materiality"],
                row["revenue_relevance"],
            )
            for row in payload["items"]
        } == expected


def test_core_mechanical_profile_catalog_and_pneumatic_gap_are_ready():
    theme = _read_json(CORE_MECHANICAL_THEME_PATH)
    mapping = _read_json(CORE_MECHANICAL_MAPPING_PATH)
    matrix = _read_json(CORE_MECHANICAL_MATRIX_PATH)
    profile = theme["research_profile"]
    node_ids = {row["node_id"] for row in theme["nodes"]}
    claim_ids = {row["claim_id"] for row in theme["claims"]}
    catalog = load_industry_catalog()
    link = next(
        row for row in catalog["theme_links"] if row["theme_id"] == CORE_MECHANICAL_THEME_ID
    )
    pneumatic_node = next(
        row for row in theme["nodes"] if row["node_id"] == "pneumatic_components"
    )
    pneumatic_matrix = next(
        row
        for row in matrix["node_evidence_matrix"]
        if row["node_id"] == "pneumatic_components"
    )

    assert profile["catalog_chain_id"] == CORE_MECHANICAL_CHAIN_ID
    assert profile["research_kind"] == "industry_chain_deep_research"
    assert set(profile["catalyst_claim_ids"] + profile["risk_claim_ids"]) <= claim_ids
    assert link["node_links"] == []
    assert set(link["unmapped_theme_node_ids"]) == node_ids
    assert "catalog仍为L2 skeleton" in link["notes"]
    assert "不映射整机、机器人关节" in link["notes"]
    assert pneumatic_node["node_review_status"] == "draft"
    assert pneumatic_node["evidence_strength"] <= 2
    assert pneumatic_matrix["node_review_status"] == "draft"
    assert pneumatic_matrix["evidence_gap_status"] == "evidence_gap"
    assert pneumatic_matrix["accepted_source_ids"] == ["coremech_301161_ar2025"]
    assert pneumatic_matrix["supported_claim_ids"] == [
        "coremech_claim_11_hydraulic_pneumatic_seals_boundary"
    ]
    pneumatic_boundary_claim = next(
        row
        for row in theme["claims"]
        if row["claim_id"] == "coremech_claim_11_hydraulic_pneumatic_seals_boundary"
    )
    assert pneumatic_boundary_claim["claim_type"] == "risk"
    assert "pneumatic_components" in pneumatic_boundary_claim["affected_theme_nodes"]
    assert "仅用于排除误映射" in pneumatic_matrix["rationale"]
    assert "气动执行与控制元件" in pneumatic_matrix["next_evidence_needed"]
    assert "pneumatic_components" not in {
        row["mapped_node_id"] for row in mapping["company_mappings"]
    }
    result = verify_deep_theme_coverage(
        CORE_MECHANICAL_THEME_ID,
        catalog=catalog,
        theme_context=load_theme_research_priority_package(),
    )
    assert result["ready"] is True
    assert all(result["checks"].values())


def test_core_mechanical_scope_boundaries_block_over_attribution():
    theme = _read_json(CORE_MECHANICAL_THEME_PATH)
    mapping = _read_json(CORE_MECHANICAL_MAPPING_PATH)
    evidence = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    claim_text = " ".join(row["claim_text"] for row in theme["claims"])

    assert "少量" in evidence["coremech_ev_603667_revenue"]["evidence_summary"]
    assert "配件与铸件" in evidence["coremech_ev_601100_revenue"]["evidence_summary"]
    assert "丝杠不可拆" in evidence["coremech_ev_601100_revenue"]["evidence_summary"]
    assert "14.72亿元" in evidence["coremech_ev_000837_revenue"]["evidence_summary"]
    assert "宽口径" in evidence["coremech_ev_000837_revenue"]["evidence_summary"]
    assert "其他零部件不可拆" in evidence["coremech_ev_300580_revenue"]["evidence_summary"]
    assert "金属件" in evidence["coremech_ev_688017_revenue"]["evidence_summary"]
    assert "谐波未拆" in evidence["coremech_ev_603915_revenue"]["evidence_summary"]
    assert "转台组合" in evidence["coremech_ev_300503_revenue"]["evidence_summary"]
    assert "稳定杆" in evidence["coremech_ev_001380_revenue"]["evidence_summary"]
    assert "仅铸件" in evidence["coremech_ev_688355_product"]["evidence_summary"]
    assert "非锻造或热处理" in evidence["coremech_ev_688355_product"]["evidence_summary"]
    assert "仅为密封件" in evidence["coremech_ev_301161_product"]["evidence_summary"]
    assert "不是气缸或气阀" in evidence["coremech_ev_301161_product"]["evidence_summary"]
    assert "不能用气动密封替代气动执行与控制元件证据" in claim_text


MACHINE_VISION_THEME_ID = (
    "industrial_inspection_metrology_machine_vision_value_chain_v1"
)
MACHINE_VISION_CHAIN_ID = "industrial_inspection_metrology_machine_vision"
MACHINE_VISION_THEME_PATH = (
    REPOSITORY_ROOT / f"artifacts/theme_decomposition/{MACHINE_VISION_THEME_ID}.json"
)
MACHINE_VISION_MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "industrial_inspection_metrology_machine_vision_company_mapping_v1.json"
)
MACHINE_VISION_SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "industrial_inspection_metrology_machine_vision_source_pack_v1.json"
)
MACHINE_VISION_MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "industrial_inspection_metrology_machine_vision_node_evidence_matrix_v1.json"
)
CLOUD_THEME_ID = "cloud_data_center_infrastructure_value_chain_v1"
CLOUD_CHAIN_ID = "cloud_data_center_infrastructure"
CLOUD_THEME_PATH = REPOSITORY_ROOT / f"artifacts/theme_decomposition/{CLOUD_THEME_ID}.json"
CLOUD_MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "cloud_data_center_infrastructure_company_mapping_v1.json"
)
CLOUD_SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "cloud_data_center_infrastructure_source_pack_v1.json"
)
CLOUD_MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "cloud_data_center_infrastructure_node_evidence_matrix_v1.json"
)
CLOUD_NODE_IDS = {
    "facility_systems_modular_deployment",
    "power_availability_electrical_architecture_dependency",
    "backup_power_storage_resilience_dependency",
    "thermal_liquid_cooling_systems",
    "heat_rejection_chillers_pumps_recovery",
    "water_refrigerant_environmental_constraints",
    "dcim_monitoring_energy_management",
    "design_integration_epc_commissioning",
    "facility_operations_lifecycle_services",
    "customer_deployment_utilization_validation",
}
CLOUD_UNMAPPED_NODE_IDS = {
    "power_availability_electrical_architecture_dependency",
    "backup_power_storage_resilience_dependency",
    "water_refrigerant_environmental_constraints",
    "customer_deployment_utilization_validation",
}
CLOUD_LINK_PAIRS = {
    ("facility_systems_modular_deployment", "data_center_facility_systems_services"),
    ("facility_systems_modular_deployment", "modular_data_center_system"),
    ("thermal_liquid_cooling_systems", "data_center_cold_plate"),
    ("thermal_liquid_cooling_systems", "immersion_cooling_system"),
    ("thermal_liquid_cooling_systems", "spray_cooling_system"),
    ("thermal_liquid_cooling_systems", "coolant_distribution_unit"),
    ("thermal_liquid_cooling_systems", "liquid_cooling_quick_connector"),
    ("thermal_liquid_cooling_systems", "liquid_cooling_pipe_system"),
    ("thermal_liquid_cooling_systems", "data_center_coolant"),
    ("thermal_liquid_cooling_systems", "liquid_cooling_leak_detection_system"),
    ("heat_rejection_chillers_pumps_recovery", "data_center_chiller"),
    ("heat_rejection_chillers_pumps_recovery", "liquid_cooling_pump"),
    ("heat_rejection_chillers_pumps_recovery", "data_center_heat_exchanger"),
    ("heat_rejection_chillers_pumps_recovery", "data_center_waste_heat_recovery_system"),
    ("dcim_monitoring_energy_management", "data_center_infrastructure_management_platform"),
    ("design_integration_epc_commissioning", "data_center_electrical_design_service"),
    ("design_integration_epc_commissioning", "liquid_cooling_integration_service"),
    ("design_integration_epc_commissioning", "data_center_epc_service"),
    ("design_integration_epc_commissioning", "data_center_commissioning_certification_service"),
    ("facility_operations_lifecycle_services", "data_center_facility_operations_service"),
}


def _assert_machine_vision_bidirectional_source_and_matrix_links() -> None:
    theme = _read_json(MACHINE_VISION_THEME_PATH)
    source_pack = _read_json(MACHINE_VISION_SOURCE_PACK_PATH)
    matrix = _read_json(MACHINE_VISION_MATRIX_PATH)
    node_ids = {row["node_id"] for row in theme["nodes"]}
    accepted_source_ids = {
        row["source_id"]
        for row in source_pack["sources"]
        if row["review_status"] == "accepted"
    }
    source_by_id = {row["source_id"]: row for row in source_pack["sources"]}
    claim_by_id = {row["claim_id"]: row for row in theme["claims"]}
    matrix_by_node = {
        row["node_id"]: row for row in matrix["node_evidence_matrix"]
    }

    assert {
        source["source_id"]: set(source["supported_claim_ids"])
        for source in source_pack["sources"]
    } == {
        source["source_id"]: {
            claim["claim_id"]
            for claim in theme["claims"]
            if source["source_id"]
            in {claim["source_id"], *claim["supporting_source_ids"]}
        }
        for source in source_pack["sources"]
    }
    assert {row["node_id"] for row in matrix["node_evidence_matrix"]} == node_ids
    assert len(matrix["node_evidence_matrix"]) == len(node_ids)
    for row in matrix["node_evidence_matrix"]:
        expected_claim_ids = {
            claim["claim_id"]
            for claim in theme["claims"]
            if row["node_id"] in claim["affected_theme_nodes"]
        }
        assert set(row["supported_claim_ids"]) == expected_claim_ids
        assert set(row["accepted_source_ids"]) <= accepted_source_ids
        assert row["accepted_source_ids"] or row["evidence_gap_status"] == "evidence_gap"
        for source_id in row["accepted_source_ids"]:
            source = source_by_id[source_id]
            assert row["node_id"] in source["supported_node_ids"]
            assert expected_claim_ids & set(source["supported_claim_ids"])
        for claim_id in expected_claim_ids:
            claim = claim_by_id[claim_id]
            assert set(row["accepted_source_ids"]) & {
                claim["source_id"],
                *claim["supporting_source_ids"],
            }
    for source in source_pack["sources"]:
        for node_id in source["supported_node_ids"]:
            assert set(source["supported_claim_ids"]) & set(
                matrix_by_node[node_id]["supported_claim_ids"]
            )


def test_machine_vision_artifacts_load_and_fourth_wave_b_row_is_ready():
    theme_package = load_theme_package()
    mapping_package = load_theme_company_mapping_package()
    priority_package = load_theme_research_priority_package()

    assert MACHINE_VISION_THEME_ID in {
        row["theme_id"] for row in theme_package["themes"]
    }
    assert MACHINE_VISION_THEME_ID in {
        row["theme_id"] for row in mapping_package["company_mappings"]
    }
    assert MACHINE_VISION_THEME_ID in {
        row["theme_id"] for row in priority_package["node_priorities"]
    }
    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_b")
    rows = {row["chain_id"]: row for row in report["theme_results"]}

    assert rows[MACHINE_VISION_CHAIN_ID]["ready"] is True
    assert all(rows[MACHINE_VISION_CHAIN_ID]["checks"].values())
    assert report["wave_results"]["wave_b"]["ready"] is True
    assert report["wave_results"]["wave_b"]["ready_theme_count"] == 5
    assert report["wave_results"]["wave_b"]["not_ready_theme_count"] == 0
    assert {chain_id for chain_id, row in rows.items() if row["ready"]} == (
        _implemented_wave_chain_ids("wave_b")
    )


def test_machine_vision_evidence_mapping_and_source_identity_are_exact():
    _assert_machine_vision_bidirectional_source_and_matrix_links()
    theme = _read_json(MACHINE_VISION_THEME_PATH)
    mapping = _read_json(MACHINE_VISION_MAPPING_PATH)
    source_pack = _read_json(MACHINE_VISION_SOURCE_PACK_PATH)
    node_ids = {row["node_id"] for row in theme["nodes"]}
    accepted = validate_theme_evidence_sources(source_pack["sources"], node_ids)
    reviewed_mappings = [
        row for row in mapping["company_mappings"] if row["review_status"] == "reviewed"
    ]
    canonical_sources = {row["source_id"]: row for row in theme["sources"]}
    mapping_sources = {row["source_id"]: row for row in mapping["sources"]}
    pack_sources = {row["source_id"]: row for row in source_pack["sources"]}

    assert len(
        [row for row in accepted.values() if row["review_status"] == "accepted"]
    ) == 12
    assert all(
        row["source_type"] == "company_filing" and row["reliability_level"] == "S0"
        for row in source_pack["sources"]
    )
    assert len(theme["nodes"]) == 11
    assert len(theme["claims"]) == 14
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
    for source_id, canonical_source in canonical_sources.items():
        assert {
            field: mapping_sources[source_id][field]
            for field in ("title", "publisher", "publish_date", "url_or_ref")
        } == {
            field: canonical_source[field]
            for field in ("title", "publisher", "publish_date", "url_or_ref")
        }
        assert {
            "title": pack_sources[source_id]["title"],
            "publisher": pack_sources[source_id]["publisher"],
            "publish_date": pack_sources[source_id]["publish_date"],
            "url_or_ref": pack_sources[source_id]["url"],
        } == {
            field: canonical_source[field]
            for field in ("title", "publisher", "publish_date", "url_or_ref")
        }


def test_machine_vision_company_beneficiary_tiers_follow_classifier_exactly():
    expected = {
        "688400.SH": ("core_beneficiary", "core_business", "material"),
        "688686.SH": ("core_beneficiary", "core_business", "material"),
        "688610.SH": ("core_beneficiary", "core_business", "material"),
        "688003.SH": ("core_beneficiary", "core_business", "material"),
        "300567.SZ": ("core_beneficiary", "meaningful_segment", "material"),
        "603203.SH": ("core_beneficiary", "meaningful_segment", "meaningful"),
        "300400.SZ": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
        "688001.SH": ("elastic_beneficiary", "meaningful_segment", "undisclosed"),
        "603297.SH": ("elastic_beneficiary", "meaningful_segment", "undisclosed"),
        "300416.SZ": ("indirect_beneficiary", "meaningful_segment", "material"),
        "688097.SH": ("indirect_beneficiary", "core_business", "undisclosed"),
        "603283.SH": ("indirect_beneficiary", "core_business", "undisclosed"),
    }
    read_model = list_theme_research_companies(MACHINE_VISION_THEME_ID)
    response = TestClient(dashboard_app.create_app()).get(
        f"/api/research/theme-decomposition/themes/{MACHINE_VISION_THEME_ID}/companies"
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


def test_machine_vision_profile_catalog_and_service_gap_are_ready():
    theme = _read_json(MACHINE_VISION_THEME_PATH)
    mapping = _read_json(MACHINE_VISION_MAPPING_PATH)
    matrix = _read_json(MACHINE_VISION_MATRIX_PATH)
    profile = theme["research_profile"]
    node_ids = {row["node_id"] for row in theme["nodes"]}
    claim_ids = {row["claim_id"] for row in theme["claims"]}
    catalog = load_industry_catalog()
    link = next(
        row for row in catalog["theme_links"] if row["theme_id"] == MACHINE_VISION_THEME_ID
    )
    service_matrix = next(
        row
        for row in matrix["node_evidence_matrix"]
        if row["node_id"] == "imv_calibration_testing_services"
    )
    service_node = next(
        row
        for row in theme["nodes"]
        if row["node_id"] == "imv_calibration_testing_services"
    )

    assert profile["catalog_chain_id"] == MACHINE_VISION_CHAIN_ID
    assert profile["research_kind"] == "industry_chain_deep_research"
    assert set(profile["catalyst_claim_ids"] + profile["risk_claim_ids"]) <= claim_ids
    assert link["node_links"] == []
    assert set(link["unmapped_theme_node_ids"]) == node_ids
    assert "catalog仍为L2 skeleton" in link["notes"]
    assert "宽节点不得映到窄节点" in link["notes"]
    assert service_node["node_review_status"] == "draft"
    assert service_node["evidence_strength"] == 2
    assert service_matrix["node_review_status"] == "draft"
    assert service_matrix["evidence_strength_after"] == service_node["evidence_strength"]
    assert service_matrix["evidence_gap_status"] == "evidence_gap"
    assert service_matrix["accepted_source_ids"] == ["imv_300416_2025_ar"]
    assert "邻近检测服务" in service_matrix["rationale"]
    assert "校准" in service_matrix["next_evidence_needed"]
    service_mapping = next(
        row for row in mapping["company_mappings"] if row["company_code"] == "300416.SZ"
    )
    assert service_mapping["mapped_node_id"] == "imv_calibration_testing_services"
    assert service_mapping["bottleneck_relevance"] == "adjacent"
    assert "邻近" in service_mapping["notes"]
    result = verify_deep_theme_coverage(
        MACHINE_VISION_THEME_ID,
        catalog=catalog,
        theme_context=load_theme_research_priority_package(),
    )
    assert result["ready"] is True
    assert all(result["checks"].values())


def test_machine_vision_scope_boundaries_block_over_attribution():
    theme = _read_json(MACHINE_VISION_THEME_PATH)
    mapping = _read_json(MACHINE_VISION_MAPPING_PATH)
    evidence = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    claim_text = " ".join(row["claim_text"] for row in theme["claims"])
    mapped_codes = {row["company_code"] for row in mapping["company_mappings"]}

    assert "半导体前道排除" in evidence["imv_ev_300567_revenue"]["evidence_summary"]
    assert "TCB/固晶排除" in evidence["imv_ev_603203_revenue"]["evidence_summary"]
    assert "晶圆检测排除" in evidence["imv_ev_603283_revenue"]["evidence_summary"]
    assert "集成电路测试排除" in evidence["imv_ev_688001_revenue"]["evidence_summary"]
    assert "自动化总收入" in evidence["imv_ev_688097_revenue"]["evidence_summary"]
    assert "自动化总收入" in evidence["imv_ev_603283_revenue"]["evidence_summary"]
    assert "电子装联" in evidence["imv_ev_300400_revenue"]["evidence_summary"]
    assert "检测设备" in evidence["imv_ev_688001_revenue"]["evidence_summary"]
    assert "光学元件" in evidence["imv_ev_603297_revenue"]["evidence_summary"]
    assert "非机器视觉单节点收入" in claim_text
    assert "标准部件毛利" in claim_text
    assert "不跨公司估值" in claim_text
    assert mapped_codes.isdisjoint({"688112.SH", "002065.SZ", "688115.SH"})


def _assert_cloud_bidirectional_direct_claim_links() -> None:
    theme = _read_json(CLOUD_THEME_PATH)
    source_pack = _read_json(CLOUD_SOURCE_PACK_PATH)
    matrix = _read_json(CLOUD_MATRIX_PATH)
    source_by_id = {row["source_id"]: row for row in source_pack["sources"]}
    claim_by_id = {row["claim_id"]: row for row in theme["claims"]}
    matrix_by_node = {row["node_id"]: row for row in matrix["node_evidence_matrix"]}

    assert set(matrix_by_node) == CLOUD_NODE_IDS
    for source in source_pack["sources"]:
        expected_claim_ids = {
            claim["claim_id"]
            for claim in theme["claims"]
            if source["source_id"]
            in {claim["source_id"], *claim["supporting_source_ids"]}
        }
        assert set(source["supported_claim_ids"]) == expected_claim_ids
        supported_node_ids = set(source["supported_node_ids"])
        for claim_id in expected_claim_ids:
            assert set(claim_by_id[claim_id]["affected_theme_nodes"]) <= (
                supported_node_ids
            ), (source["source_id"], claim_id)
        for node_id in source["supported_node_ids"]:
            direct_claim_ids = {
                claim_id
                for claim_id in expected_claim_ids
                if claim_by_id[claim_id]["affected_theme_nodes"] == [node_id]
            }
            assert direct_claim_ids
            assert direct_claim_ids & set(matrix_by_node[node_id]["supported_claim_ids"])

    for node_id, row in matrix_by_node.items():
        expected_claim_ids = {
            claim["claim_id"]
            for claim in theme["claims"]
            if node_id in claim["affected_theme_nodes"]
        }
        assert set(row["supported_claim_ids"]) == expected_claim_ids
        assert row["accepted_source_ids"]
        for source_id in row["accepted_source_ids"]:
            source = source_by_id[source_id]
            assert node_id in source["supported_node_ids"]
            assert {
                claim_id
                for claim_id in source["supported_claim_ids"]
                if claim_by_id[claim_id]["affected_theme_nodes"] == [node_id]
            }
        for claim_id in expected_claim_ids:
            claim = claim_by_id[claim_id]
            assert set(row["accepted_source_ids"]) & {
                claim["source_id"],
                *claim["supporting_source_ids"],
            }


def test_cloud_data_center_artifacts_complete_wave_b():
    theme_package = load_theme_package()
    mapping_package = load_theme_company_mapping_package()
    priority_package = load_theme_research_priority_package()

    assert CLOUD_THEME_ID in {row["theme_id"] for row in theme_package["themes"]}
    assert CLOUD_THEME_ID in {
        row["theme_id"] for row in mapping_package["company_mappings"]
    }
    assert CLOUD_THEME_ID in {
        row["theme_id"] for row in priority_package["node_priorities"]
    }
    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_b")
    rows = {row["chain_id"]: row for row in report["theme_results"]}

    assert rows[CLOUD_CHAIN_ID]["ready"] is True
    assert all(rows[CLOUD_CHAIN_ID]["checks"].values())
    wave_result = report["wave_results"]["wave_b"]
    assert wave_result["ready"] is True
    assert wave_result["theme_count"] == 5
    assert wave_result["ready_theme_count"] == 5
    assert wave_result["not_ready_theme_count"] == 0
    assert {chain_id for chain_id, row in rows.items() if row["ready"]} == (
        _implemented_wave_chain_ids("wave_b")
    )


def test_cloud_data_center_evidence_counts_identity_and_mapping_evidence_are_exact():
    _assert_cloud_bidirectional_direct_claim_links()
    theme = _read_json(CLOUD_THEME_PATH)
    mapping = _read_json(CLOUD_MAPPING_PATH)
    source_pack = _read_json(CLOUD_SOURCE_PACK_PATH)
    node_ids = {row["node_id"] for row in theme["nodes"]}
    accepted = validate_theme_evidence_sources(source_pack["sources"], node_ids)
    reviewed_mappings = [
        row for row in mapping["company_mappings"] if row["review_status"] == "reviewed"
    ]
    evidence_by_id = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    canonical_sources = {row["source_id"]: row for row in theme["sources"]}
    mapping_sources = {row["source_id"]: row for row in mapping["sources"]}
    pack_sources = {row["source_id"]: row for row in source_pack["sources"]}

    assert node_ids == CLOUD_NODE_IDS
    assert len(theme["claims"]) == 13
    assert all(set(row) >= CLAIM_FIELDS for row in theme["claims"])
    assert len([row for row in accepted.values() if row["review_status"] == "accepted"]) == 11
    assert all(
        row["source_type"] == "company_filing"
        and row["reliability_level"] == "S0"
        and row["document_status"] == "full_text_reviewed"
        for row in source_pack["sources"]
    )
    assert len(reviewed_mappings) == 11
    assert len({row["company_code"] for row in reviewed_mappings}) == 11
    assert len({row["source_id"] for row in source_pack["sources"]}) == 11
    assert len({row["url"] for row in source_pack["sources"]}) == 11
    assert set(canonical_sources) == set(mapping_sources) == set(pack_sources)
    for source_id, canonical_source in canonical_sources.items():
        assert {
            field: mapping_sources[source_id][field]
            for field in ("title", "publisher", "publish_date", "url_or_ref")
        } == {
            field: canonical_source[field]
            for field in ("title", "publisher", "publish_date", "url_or_ref")
        }
        assert {
            "title": pack_sources[source_id]["title"],
            "publisher": pack_sources[source_id]["publisher"],
            "publish_date": pack_sources[source_id]["publish_date"],
            "url_or_ref": pack_sources[source_id]["url"],
        } == {
            field: canonical_source[field]
            for field in ("title", "publisher", "publish_date", "url_or_ref")
        }
    for row in reviewed_mappings:
        evidence_types = {evidence_by_id[item_id]["evidence_type"] for item_id in row["evidence_ids"]}
        assert evidence_types & {"product_relationship", "service_relationship"}
        assert "revenue_materiality" in evidence_types
        assert "business_stage" in evidence_types
        stage_evidence = [
            evidence_by_id[item_id]
            for item_id in row["evidence_ids"]
            if evidence_by_id[item_id]["evidence_type"] == "business_stage"
        ]
        assert all("风险边界" in item["evidence_summary"] for item in stage_evidence)
    assert {
        evidence_by_id[evidence_id]["source_id"]
        for row in reviewed_mappings
        for evidence_id in row["evidence_ids"]
    } == set(pack_sources)


def test_cloud_data_center_mapping_locators_are_precise_and_role_specific():
    mapping = _read_json(CLOUD_MAPPING_PATH)
    evidence_by_id = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    fuzzy_locator_phrases = {
        "风险章节",
        "收入与风险章节",
        "经营与金融风险章节",
        "发展与风险章节",
        "收入分析及研发项目页",
        "主营业务与战略章节",
        "客户、项目和竞争风险章节",
    }

    for row in mapping["company_mappings"]:
        evidence = [evidence_by_id[evidence_id] for evidence_id in row["evidence_ids"]]
        locators = [item["excerpt_locator"] for item in evidence]
        assert len(evidence) == 3
        assert len(set(locators)) == 3, row["company_code"]
        assert {
            item["evidence_type"] for item in evidence
        } >= {"revenue_materiality", "business_stage"}
        assert {
            item["evidence_type"] for item in evidence
        } & {"product_relationship", "service_relationship"}
        for locator in locators:
            assert re.search(r"第[\d、,\-]+页", locator), locator
            assert not any(phrase in locator for phrase in fuzzy_locator_phrases), locator

    assert "第18页" in evidence_by_id["cloud_dc_ev_300442_stage"]["excerpt_locator"]
    assert "客户集中" in evidence_by_id["cloud_dc_ev_300442_stage"]["excerpt_locator"]
    assert "第36页" in evidence_by_id["cloud_dc_ev_300442_stage"]["excerpt_locator"]
    assert "上架率" in evidence_by_id["cloud_dc_ev_300442_stage"]["excerpt_locator"]


def test_cloud_data_center_beneficiary_tiers_and_company_api_are_exact():
    expected = {
        "002837.SZ": ("elastic_beneficiary", "meaningful_segment", "undisclosed"),
        "300499.SZ": ("elastic_beneficiary", "meaningful_segment", "undisclosed"),
        "301018.SZ": ("elastic_beneficiary", "meaningful_segment", "undisclosed"),
        "000811.SZ": ("elastic_beneficiary", "meaningful_segment", "undisclosed"),
        "002335.SZ": ("indirect_beneficiary", "meaningful_segment", "material"),
        "300442.SZ": ("core_beneficiary", "core_business", "material"),
        "002364.SZ": ("indirect_beneficiary", "meaningful_segment", "material"),
        "603912.SH": ("elastic_beneficiary", "meaningful_segment", "undisclosed"),
        "300249.SZ": ("elastic_beneficiary", "meaningful_segment", "undisclosed"),
        "002929.SZ": ("elastic_beneficiary", "meaningful_segment", "undisclosed"),
        "603881.SH": ("core_beneficiary", "core_business", "material"),
    }
    read_model = list_theme_research_companies(CLOUD_THEME_ID)
    response = TestClient(dashboard_app.create_app()).get(
        f"/api/research/theme-decomposition/themes/{CLOUD_THEME_ID}/companies"
    )

    assert response.status_code == 200
    for payload in (read_model, response.json()):
        assert payload["total"] == 11
        assert {
            row["company_code"]: (
                row["beneficiary_tier"],
                row["business_materiality"],
                row["revenue_relevance"],
            )
            for row in payload["items"]
        } == expected


def test_cloud_data_center_readable_sections_links_and_cross_chain_boundaries_are_exact():
    theme = _read_json(CLOUD_THEME_PATH)
    profile = theme["research_profile"]
    claim_ids = {row["claim_id"] for row in theme["claims"]}
    catalog = load_industry_catalog()
    link = next(row for row in catalog["theme_links"] if row["theme_id"] == CLOUD_THEME_ID)

    assert set(profile["readable_section_claim_ids"]) == {
        "conclusion",
        "value_chain",
        "profit_pool_barriers",
        "catalysts_validation_risks",
        "beneficiary_companies",
        "source_evidence",
        "evidence_gaps",
    }
    assert all(profile["readable_section_claim_ids"].values())
    assert all(
        set(section_claim_ids) <= claim_ids
        for section_claim_ids in profile["readable_section_claim_ids"].values()
    )
    assert set(profile["catalyst_claim_ids"] + profile["risk_claim_ids"]) <= claim_ids
    assert {
        (row["theme_node_id"], row["catalog_node_id"])
        for row in link["node_links"]
    } == CLOUD_LINK_PAIRS
    assert len(link["node_links"]) == 20
    assert set(link["unmapped_theme_node_ids"]) == CLOUD_UNMAPPED_NODE_IDS
    assert "family/stage完整等价" in link["notes"]
    assert "power_electronics_power_supply_equipment" in link["notes"]
    assert "new_energy_storage" in link["notes"]
    assert "new_power_system_smart_grid" in link["notes"]
    assert "industrial_software" in link["notes"]
    result = verify_deep_theme_coverage(
        CLOUD_THEME_ID,
        catalog=catalog,
        theme_context=load_theme_research_priority_package(),
    )
    assert result["ready"] is True
    assert all(result["checks"].values())
