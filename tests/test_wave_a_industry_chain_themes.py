from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from fastapi.testclient import TestClient

from stock_research.ai_power_source_pack import validate_theme_evidence_sources
from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard.theme_research import list_theme_research_companies
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
OPTICAL_THEME_ID = (
    "optical_communications_data_center_interconnect_value_chain_v1"
)
OPTICAL_CHAIN_ID = "optical_communications_data_center_interconnect"
OPTICAL_THEME_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition"
    / "optical_communications_data_center_interconnect_value_chain_v1.json"
)
OPTICAL_MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "optical_communications_data_center_interconnect_company_mapping_v1.json"
)
OPTICAL_SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "optical_communications_data_center_interconnect_source_pack_v1.json"
)
OPTICAL_MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "optical_communications_data_center_interconnect_node_evidence_matrix_v1.json"
)
SEMICONDUCTOR_MATERIALS_THEME_ID = (
    "semiconductor_materials_electronic_chemicals_value_chain_v1"
)
SEMICONDUCTOR_MATERIALS_CHAIN_ID = "semiconductor_materials_electronic_chemicals"
SEMICONDUCTOR_MATERIALS_THEME_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition"
    / "semiconductor_materials_electronic_chemicals_value_chain_v1.json"
)
SEMICONDUCTOR_MATERIALS_MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "semiconductor_materials_electronic_chemicals_company_mapping_v1.json"
)
SEMICONDUCTOR_MATERIALS_SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "semiconductor_materials_electronic_chemicals_source_pack_v1.json"
)
SEMICONDUCTOR_MATERIALS_MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "semiconductor_materials_electronic_chemicals_node_evidence_matrix_v1.json"
)
INDUSTRIAL_AUTOMATION_THEME_ID = "industrial_automation_control_value_chain_v1"
INDUSTRIAL_AUTOMATION_CHAIN_ID = "industrial_automation_control"
INDUSTRIAL_AUTOMATION_THEME_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/industrial_automation_control_value_chain_v1.json"
)
INDUSTRIAL_AUTOMATION_MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "industrial_automation_control_company_mapping_v1.json"
)
INDUSTRIAL_AUTOMATION_SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "industrial_automation_control_source_pack_v1.json"
)
INDUSTRIAL_AUTOMATION_MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "industrial_automation_control_node_evidence_matrix_v1.json"
)
POWER_SEMICONDUCTORS_THEME_ID = "power_semiconductors_value_chain_v1"
POWER_SEMICONDUCTORS_CHAIN_ID = "power_semiconductors"
POWER_SEMICONDUCTORS_THEME_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/power_semiconductors_value_chain_v1.json"
)
POWER_SEMICONDUCTORS_MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "power_semiconductors_company_mapping_v1.json"
)
POWER_SEMICONDUCTORS_SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "power_semiconductors_source_pack_v1.json"
)
POWER_SEMICONDUCTORS_MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "power_semiconductors_node_evidence_matrix_v1.json"
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


def _assert_bidirectional_source_and_matrix_links(
    theme_path: Path,
    source_pack_path: Path,
    matrix_path: Path,
    *,
    exact_node_claim_coverage: bool,
) -> None:
    theme = _read_json(theme_path)
    source_pack = _read_json(source_pack_path)
    matrix = _read_json(matrix_path)
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
        if exact_node_claim_coverage:
            assert row_claim_ids == expected_claim_ids_by_node[row["node_id"]]
        else:
            assert row_claim_ids <= expected_claim_ids_by_node[row["node_id"]]
        assert set(row["accepted_source_ids"]) <= accepted_source_ids
        assert row["accepted_source_ids"] or row["evidence_gap_status"] in {
            "evidence_gap",
            "technical_route_only",
        }
        for source_id in row["accepted_source_ids"]:
            source = source_by_id[source_id]
            assert row["node_id"] in source["supported_node_ids"]
            assert row_claim_ids & set(source["supported_claim_ids"])
        for claim_id in row_claim_ids:
            claim = claim_by_id[claim_id]
            assert row["node_id"] in claim["affected_theme_nodes"]
            assert set(row["accepted_source_ids"]) & {
                claim["source_id"],
                *claim["supporting_source_ids"],
            }


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


def test_ai_logic_compute_batch_row_stays_ready_when_wave_a_is_complete():
    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_a")
    row = next(row for row in report["theme_results"] if row["chain_id"] == CHAIN_ID)

    assert row["ready"] is True
    assert all(row["checks"].values())
    assert report["wave_results"]["wave_a"]["ready"] is True
    implemented_chain_ids = _implemented_wave_chain_ids("wave_a")
    assert {
        result["chain_id"] for result in report["theme_results"] if result["ready"]
    } == implemented_chain_ids
    assert report["wave_results"]["wave_a"]["ready_theme_count"] == len(
        implemented_chain_ids
    )
    assert report["completion_status"] == "ready"


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


def test_ai_logic_compute_company_beneficiary_tiers_are_evidence_conservative():
    expected = {
        "688256.SH": ("core_beneficiary", "core_business", "material"),
        "688041.SH": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
        "688047.SH": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
        "688521.SH": ("core_beneficiary", "meaningful_segment", "meaningful"),
        "603893.SH": ("core_beneficiary", "core_business", "material"),
        "688008.SH": ("core_beneficiary", "meaningful_segment", "material"),
        "688262.SH": ("indirect_beneficiary", "meaningful_segment", "meaningful"),
        "688049.SH": ("core_beneficiary", "core_business", "material"),
    }
    read_model = list_theme_research_companies(THEME_ID)
    response = TestClient(dashboard_app.create_app()).get(
        f"/api/research/theme-decomposition/themes/{THEME_ID}/companies"
    )

    assert response.status_code == 200
    for payload in (read_model, response.json()):
        assert payload["total"] == 8
        assert {
            row["company_code"]: (
                row["beneficiary_tier"],
                row["business_materiality"],
                row["revenue_relevance"],
            )
            for row in payload["items"]
        } == expected
        by_company = {row["company_code"]: row for row in payload["items"]}
        for company_code in ("688041.SH", "688047.SH"):
            assert {
                item["evidence_type"]
                for item in by_company[company_code]["mapping_evidence"]
            } == {"product_relationship"}


def test_ai_logic_compute_source_pack_claim_links_are_bidirectionally_exact():
    theme = _read_json(THEME_PATH)
    source_pack = _read_json(SOURCE_PACK_PATH)
    expected_claim_ids_by_source = {
        source["source_id"]: {
            claim["claim_id"]
            for claim in theme["claims"]
            if source["source_id"]
            in {claim["source_id"], *claim["supporting_source_ids"]}
        }
        for source in source_pack["sources"]
    }

    assert {
        source["source_id"]: set(source["supported_claim_ids"])
        for source in source_pack["sources"]
    } == expected_claim_ids_by_source


def test_ai_logic_compute_matrix_covers_every_node_with_evidence_or_explicit_gap():
    _assert_bidirectional_source_and_matrix_links(
        THEME_PATH,
        SOURCE_PACK_PATH,
        MATRIX_PATH,
        exact_node_claim_coverage=False,
    )
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
    claim_ids = set(claim_by_id)

    assert {row["node_id"] for row in matrix["node_evidence_matrix"]} == node_ids
    assert len(matrix["node_evidence_matrix"]) == len(node_ids)
    for row in matrix["node_evidence_matrix"]:
        assert set(row["accepted_source_ids"]) <= accepted_source_ids
        assert set(row["supported_claim_ids"]) <= claim_ids
        assert row["accepted_source_ids"] or row["evidence_gap_status"] in {
            "evidence_gap",
            "technical_route_only",
        }
        for source_id in row["accepted_source_ids"]:
            source = source_by_id[source_id]
            assert row["node_id"] in source["supported_node_ids"]
            assert set(row["supported_claim_ids"]) & set(
                source["supported_claim_ids"]
            )
        for claim_id in row["supported_claim_ids"]:
            claim = claim_by_id[claim_id]
            assert row["node_id"] in claim["affected_theme_nodes"]
            assert set(row["accepted_source_ids"]) & {
                claim["source_id"],
                *claim["supporting_source_ids"],
            }


def test_ai_logic_compute_ucie_source_uses_exact_official_release_date():
    theme = _read_json(THEME_PATH)
    source_pack = _read_json(SOURCE_PACK_PATH)
    source_id = "ai_logic_ucie_3_specifications"
    theme_source = next(row for row in theme["sources"] if row["source_id"] == source_id)
    pack_source = next(
        row for row in source_pack["sources"] if row["source_id"] == source_id
    )

    assert theme_source["publish_date"] == "2025-08-05"
    assert pack_source["publish_date"] == theme_source["publish_date"]


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


def test_optical_interconnect_artifacts_load_through_canonical_packages():
    theme_package = load_theme_package()
    mapping_package = load_theme_company_mapping_package()
    priority_package = load_theme_research_priority_package()
    catalog = load_industry_catalog()

    assert OPTICAL_THEME_ID in {row["theme_id"] for row in theme_package["themes"]}
    assert OPTICAL_THEME_ID in {
        row["theme_id"] for row in mapping_package["company_mappings"]
    }
    assert OPTICAL_THEME_ID in {
        row["theme_id"] for row in priority_package["node_priorities"]
    }
    assert next(
        row for row in catalog["theme_links"] if row["theme_id"] == OPTICAL_THEME_ID
    )["node_links"] == []


def test_optical_interconnect_batch_row_is_ready_and_ai_logic_stays_ready():
    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_a")
    rows = {row["chain_id"]: row for row in report["theme_results"]}

    assert rows[OPTICAL_CHAIN_ID]["ready"] is True
    assert all(rows[OPTICAL_CHAIN_ID]["checks"].values())
    assert rows[CHAIN_ID]["ready"] is True
    assert all(rows[CHAIN_ID]["checks"].values())
    assert report["wave_results"]["wave_a"]["ready"] is True
    implemented_chain_ids = _implemented_wave_chain_ids("wave_a")
    assert {
        chain_id for chain_id, row in rows.items() if row["ready"]
    } == implemented_chain_ids
    assert report["wave_results"]["wave_a"]["ready_theme_count"] == len(
        implemented_chain_ids
    )
    assert report["wave_results"]["wave_a"]["not_ready_theme_count"] == (
        len(rows) - len(implemented_chain_ids)
    )
    assert report["completion_status"] == "ready"


def test_optical_interconnect_research_meets_evidence_and_mapping_gates():
    theme = _read_json(OPTICAL_THEME_PATH)
    mapping = _read_json(OPTICAL_MAPPING_PATH)
    source_pack = _read_json(OPTICAL_SOURCE_PACK_PATH)
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
        if row["source_type"]
        in {"company_filing", "official_report", "official_article"}
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


def test_optical_interconnect_company_beneficiary_tiers_are_exact():
    expected = {
        "300308.SZ": ("core_beneficiary", "core_business", "material"),
        "300502.SZ": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
        "002281.SZ": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
        "300394.SZ": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
        "688498.SH": ("core_beneficiary", "core_business", "material"),
        "688313.SH": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
        "000988.SZ": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
        "603083.SH": ("core_beneficiary", "meaningful_segment", "meaningful"),
        "300548.SZ": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
        "301205.SZ": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
    }
    read_model = list_theme_research_companies(OPTICAL_THEME_ID)
    response = TestClient(dashboard_app.create_app()).get(
        f"/api/research/theme-decomposition/themes/{OPTICAL_THEME_ID}/companies"
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


def test_optical_interconnect_source_and_matrix_links_are_bidirectionally_exact():
    _assert_bidirectional_source_and_matrix_links(
        OPTICAL_THEME_PATH,
        OPTICAL_SOURCE_PACK_PATH,
        OPTICAL_MATRIX_PATH,
        exact_node_claim_coverage=True,
    )
    theme = _read_json(OPTICAL_THEME_PATH)
    source_pack = _read_json(OPTICAL_SOURCE_PACK_PATH)
    matrix = _read_json(OPTICAL_MATRIX_PATH)
    expected_claim_ids_by_source = {
        source["source_id"]: {
            claim["claim_id"]
            for claim in theme["claims"]
            if source["source_id"]
            in {claim["source_id"], *claim["supporting_source_ids"]}
        }
        for source in source_pack["sources"]
    }
    node_ids = {row["node_id"] for row in theme["nodes"]}
    accepted_source_ids = {
        row["source_id"]
        for row in source_pack["sources"]
        if row["review_status"] == "accepted"
    }
    source_by_id = {row["source_id"]: row for row in source_pack["sources"]}
    claim_by_id = {row["claim_id"]: row for row in theme["claims"]}
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
        assert set(row["supported_claim_ids"]) == expected_claim_ids_by_node[
            row["node_id"]
        ]
        assert set(row["accepted_source_ids"]) <= accepted_source_ids
        assert set(row["supported_claim_ids"]) <= set(claim_by_id)
        assert row["accepted_source_ids"] or row["evidence_gap_status"] in {
            "evidence_gap",
            "technical_route_only",
        }
        for source_id in row["accepted_source_ids"]:
            source = source_by_id[source_id]
            assert row["node_id"] in source["supported_node_ids"]
            assert set(row["supported_claim_ids"]) & set(
                source["supported_claim_ids"]
            )
        for claim_id in row["supported_claim_ids"]:
            claim = claim_by_id[claim_id]
            assert row["node_id"] in claim["affected_theme_nodes"]
            assert set(row["accepted_source_ids"]) & {
                claim["source_id"],
                *claim["supporting_source_ids"],
            }


def test_optical_interconnect_profile_and_catalog_link_cover_every_node():
    theme = _read_json(OPTICAL_THEME_PATH)
    profile = theme["research_profile"]
    claim_ids = {row["claim_id"] for row in theme["claims"]}
    node_ids = {row["node_id"] for row in theme["nodes"]}
    catalog = load_industry_catalog()
    link = next(
        row for row in catalog["theme_links"] if row["theme_id"] == OPTICAL_THEME_ID
    )
    context = load_theme_research_priority_package()

    assert profile["catalyst_claim_ids"]
    assert profile["risk_claim_ids"]
    assert set(profile["catalyst_claim_ids"] + profile["risk_claim_ids"]) <= claim_ids
    assert link["node_links"] == []
    assert set(link["unmapped_theme_node_ids"]) == node_ids
    assert len(link["unmapped_theme_node_ids"]) == len(node_ids)

    result = verify_deep_theme_coverage(
        OPTICAL_THEME_ID,
        catalog=catalog,
        theme_context=context,
    )
    assert result["ready"] is True
    assert all(result["checks"].values())


def test_optical_new_ease_source_uses_exact_revenue_and_route_locators():
    theme = _read_json(OPTICAL_THEME_PATH)
    source_pack = _read_json(OPTICAL_SOURCE_PACK_PATH)
    source_id = "optical_300502_2025_report"
    theme_source = next(row for row in theme["sources"] if row["source_id"] == source_id)
    pack_source = next(
        row for row in source_pack["sources"] if row["source_id"] == source_id
    )

    assert pack_source["evidence_locator"] == (
        "第10-12页产品矩阵、产销量、营业收入和量产交付；"
        "第14-21页硅光、LPO/LRO、NPO/CPO、相干及研发项目"
    )
    assert theme_source["notes"] == f"{pack_source['evidence_locator']}已复核。"
    assert pack_source["title"] == theme_source["title"]
    assert pack_source["publisher"] == theme_source["publisher"]
    assert pack_source["publish_date"] == theme_source["publish_date"]
    assert pack_source["url"] == theme_source["url_or_ref"]


def test_optical_linktel_source_locator_covers_qualification_yield_and_delivery():
    theme = _read_json(OPTICAL_THEME_PATH)
    source_pack = _read_json(OPTICAL_SOURCE_PACK_PATH)
    source_id = "optical_301205_2025_report"
    theme_source = next(row for row in theme["sources"] if row["source_id"] == source_id)
    pack_source = next(
        row for row in source_pack["sources"] if row["source_id"] == source_id
    )

    assert pack_source["evidence_locator"] == (
        "第9页光模块主营和产品；第13-14页供应商开发与产品认证；"
        "第19-21、34页良率、规模制造和全球交付；"
        "第36-37页芯片供应风险；第93页收入审计事项"
    )
    assert theme_source["notes"] == f"{pack_source['evidence_locator']}已复核。"
    assert pack_source["title"] == theme_source["title"]
    assert pack_source["publisher"] == theme_source["publisher"]
    assert pack_source["publish_date"] == theme_source["publish_date"]
    assert pack_source["url"] == theme_source["url_or_ref"]


def test_optical_active_chip_claim_keeps_revenue_at_data_center_category_level():
    theme = _read_json(OPTICAL_THEME_PATH)
    claim_text = next(
        row["claim_text"]
        for row in theme["claims"]
        if row["claim_id"] == "optical_claim_01_active_chips"
    )

    assert (
        "源杰科技数据中心领域收入占比超过50%，主要产品为CW激光器芯片"
        in claim_text
    )
    assert "数据中心CW光源收入占比超过50%" not in claim_text
    assert "200G及以上EML仍以进口供应为主" in claim_text


def test_semiconductor_materials_artifacts_load_and_batch_row_is_ready():
    theme_package = load_theme_package()
    mapping_package = load_theme_company_mapping_package()
    priority_package = load_theme_research_priority_package()
    catalog = load_industry_catalog()

    assert SEMICONDUCTOR_MATERIALS_THEME_ID in {
        row["theme_id"] for row in theme_package["themes"]
    }
    assert SEMICONDUCTOR_MATERIALS_THEME_ID in {
        row["theme_id"] for row in mapping_package["company_mappings"]
    }
    assert SEMICONDUCTOR_MATERIALS_THEME_ID in {
        row["theme_id"] for row in priority_package["node_priorities"]
    }
    link = next(
        row
        for row in catalog["theme_links"]
        if row["theme_id"] == SEMICONDUCTOR_MATERIALS_THEME_ID
    )
    assert link["node_links"] == []

    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_a")
    rows = {row["chain_id"]: row for row in report["theme_results"]}
    implemented_chain_ids = _implemented_wave_chain_ids("wave_a")
    assert rows[SEMICONDUCTOR_MATERIALS_CHAIN_ID]["ready"] is True
    assert all(rows[SEMICONDUCTOR_MATERIALS_CHAIN_ID]["checks"].values())
    assert {chain_id for chain_id, row in rows.items() if row["ready"]} == (
        implemented_chain_ids
    )
    assert report["wave_results"]["wave_a"]["ready_theme_count"] == len(
        implemented_chain_ids
    )
    assert report["wave_results"]["wave_a"]["not_ready_theme_count"] == (
        len(rows) - len(implemented_chain_ids)
    )
    wave_is_complete = len(implemented_chain_ids) == len(rows)
    assert report["wave_results"]["wave_a"]["ready"] is wave_is_complete
    assert report["completion_status"] == (
        "ready" if wave_is_complete else "not_ready"
    )


def test_semiconductor_materials_evidence_mapping_and_semantic_links_are_exact():
    _assert_bidirectional_source_and_matrix_links(
        SEMICONDUCTOR_MATERIALS_THEME_PATH,
        SEMICONDUCTOR_MATERIALS_SOURCE_PACK_PATH,
        SEMICONDUCTOR_MATERIALS_MATRIX_PATH,
        exact_node_claim_coverage=True,
    )
    theme = _read_json(SEMICONDUCTOR_MATERIALS_THEME_PATH)
    mapping = _read_json(SEMICONDUCTOR_MATERIALS_MAPPING_PATH)
    source_pack = _read_json(SEMICONDUCTOR_MATERIALS_SOURCE_PACK_PATH)
    matrix = _read_json(SEMICONDUCTOR_MATERIALS_MATRIX_PATH)
    node_ids = {row["node_id"] for row in theme["nodes"]}
    accepted_source_by_id = validate_theme_evidence_sources(
        source_pack["sources"], node_ids
    )
    accepted_source_ids = {
        source_id
        for source_id, row in accepted_source_by_id.items()
        if row["review_status"] == "accepted"
    }
    reviewed_mappings = [
        row for row in mapping["company_mappings"] if row["review_status"] == "reviewed"
    ]
    mapping_sources = {row["source_id"]: row for row in mapping["sources"]}
    mapping_evidence = {row["evidence_id"]: row for row in mapping["evidence_items"]}

    assert len(accepted_source_ids) >= 10
    assert all(
        source_pack_row["source_type"] == "company_filing"
        and source_pack_row["reliability_level"] == "S0"
        for source_pack_row in source_pack["sources"]
        if source_pack_row["review_status"] == "accepted"
    )
    assert len(theme["claims"]) >= 10
    assert all(set(row) >= CLAIM_FIELDS for row in theme["claims"])
    assert len(reviewed_mappings) == 10
    assert len({row["company_code"] for row in reviewed_mappings}) == 10
    for row in reviewed_mappings:
        evidence = [
            {
                **mapping_evidence[evidence_id],
                "source": mapping_sources[mapping_evidence[evidence_id]["source_id"]],
            }
            for evidence_id in row["evidence_ids"]
        ]
        assert classify_beneficiary(row, evidence) != "concept_association"

    expected_claim_ids_by_source = {
        source["source_id"]: {
            claim["claim_id"]
            for claim in theme["claims"]
            if source["source_id"]
            in {claim["source_id"], *claim["supporting_source_ids"]}
        }
        for source in source_pack["sources"]
    }
    assert {
        source["source_id"]: set(source["supported_claim_ids"])
        for source in source_pack["sources"]
    } == expected_claim_ids_by_source

    source_by_id = {row["source_id"]: row for row in source_pack["sources"]}
    claim_by_id = {row["claim_id"]: row for row in theme["claims"]}
    expected_claim_ids_by_node = {
        node_id: {
            claim["claim_id"]
            for claim in theme["claims"]
            if node_id in claim["affected_theme_nodes"]
        }
        for node_id in node_ids
    }
    assert {row["node_id"] for row in matrix["node_evidence_matrix"]} == node_ids
    assert len(matrix["node_evidence_matrix"]) == len(node_ids)
    for row in matrix["node_evidence_matrix"]:
        assert set(row["supported_claim_ids"]) == expected_claim_ids_by_node[
            row["node_id"]
        ]
        assert set(row["accepted_source_ids"]) <= accepted_source_ids
        for source_id in row["accepted_source_ids"]:
            source = source_by_id[source_id]
            assert row["node_id"] in source["supported_node_ids"]
            assert set(row["supported_claim_ids"]) & set(source["supported_claim_ids"])
        for claim_id in row["supported_claim_ids"]:
            claim = claim_by_id[claim_id]
            assert row["node_id"] in claim["affected_theme_nodes"]
            assert set(row["accepted_source_ids"]) & {
                claim["source_id"],
                *claim["supporting_source_ids"],
            }


def test_semiconductor_materials_company_beneficiary_tiers_are_exact():
    expected = {
        "688019.SH": ("core_beneficiary", "core_business", "material"),
        "300054.SZ": ("core_beneficiary", "meaningful_segment", "meaningful"),
        "002409.SZ": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
        "300346.SZ": ("core_beneficiary", "core_business", "material"),
        "300666.SZ": ("core_beneficiary", "core_business", "material"),
        "688126.SH": ("core_beneficiary", "core_business", "material"),
        "300655.SZ": ("core_beneficiary", "core_business", "material"),
        "300236.SZ": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
        "688268.SH": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
        "688234.SH": ("core_beneficiary", "core_business", "material"),
    }
    read_model = list_theme_research_companies(SEMICONDUCTOR_MATERIALS_THEME_ID)
    response = TestClient(dashboard_app.create_app()).get(
        "/api/research/theme-decomposition/themes/"
        f"{SEMICONDUCTOR_MATERIALS_THEME_ID}/companies"
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


def test_semiconductor_materials_profile_and_catalog_link_cover_every_node():
    theme = _read_json(SEMICONDUCTOR_MATERIALS_THEME_PATH)
    profile = theme["research_profile"]
    claim_ids = {row["claim_id"] for row in theme["claims"]}
    node_ids = {row["node_id"] for row in theme["nodes"]}
    catalog = load_industry_catalog()
    link = next(
        row
        for row in catalog["theme_links"]
        if row["theme_id"] == SEMICONDUCTOR_MATERIALS_THEME_ID
    )

    assert profile["catalog_chain_id"] == SEMICONDUCTOR_MATERIALS_CHAIN_ID
    assert profile["research_kind"] == "industry_chain_deep_research"
    assert profile["catalyst_claim_ids"]
    assert profile["risk_claim_ids"]
    assert set(profile["catalyst_claim_ids"] + profile["risk_claim_ids"]) <= claim_ids
    assert link["node_links"] == []
    assert set(link["unmapped_theme_node_ids"]) == node_ids
    assert len(link["unmapped_theme_node_ids"]) == len(node_ids)

    result = verify_deep_theme_coverage(
        SEMICONDUCTOR_MATERIALS_THEME_ID,
        catalog=catalog,
        theme_context=load_theme_research_priority_package(),
    )
    assert result["ready"] is True
    assert all(result["checks"].values())


def test_yake_display_photoresists_are_excluded_from_wafer_photoresist_evidence():
    theme = _read_json(SEMICONDUCTOR_MATERIALS_THEME_PATH)
    source_pack = _read_json(SEMICONDUCTOR_MATERIALS_SOURCE_PACK_PATH)
    source_id = "semimat_002409_2025_report"
    claim = next(
        row
        for row in theme["claims"]
        if row["claim_id"] == "semimat_claim_03_photoresists"
    )
    source = next(
        row for row in source_pack["sources"] if row["source_id"] == source_id
    )

    assert source_id not in claim["supporting_source_ids"]
    assert "semimat_claim_03_photoresists" not in source["supported_claim_ids"]
    assert "photoresists_ancillaries" not in source["supported_node_ids"]
    assert "显示" in source["evidence_summary"]
    assert "晶圆光刻胶证据" in source["limitations"]


def test_industrial_automation_artifacts_load_and_batch_row_is_ready():
    theme_package = load_theme_package()
    mapping_package = load_theme_company_mapping_package()
    priority_package = load_theme_research_priority_package()
    catalog = load_industry_catalog()

    assert INDUSTRIAL_AUTOMATION_THEME_ID in {
        row["theme_id"] for row in theme_package["themes"]
    }
    assert INDUSTRIAL_AUTOMATION_THEME_ID in {
        row["theme_id"] for row in mapping_package["company_mappings"]
    }
    assert INDUSTRIAL_AUTOMATION_THEME_ID in {
        row["theme_id"] for row in priority_package["node_priorities"]
    }
    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_a")
    rows = {row["chain_id"]: row for row in report["theme_results"]}
    implemented_chain_ids = _implemented_wave_chain_ids("wave_a")

    assert rows[INDUSTRIAL_AUTOMATION_CHAIN_ID]["ready"] is True
    assert all(rows[INDUSTRIAL_AUTOMATION_CHAIN_ID]["checks"].values())
    assert {chain_id for chain_id, row in rows.items() if row["ready"]} == (
        implemented_chain_ids
    )


def test_industrial_automation_evidence_mapping_and_links_are_exact():
    _assert_bidirectional_source_and_matrix_links(
        INDUSTRIAL_AUTOMATION_THEME_PATH,
        INDUSTRIAL_AUTOMATION_SOURCE_PACK_PATH,
        INDUSTRIAL_AUTOMATION_MATRIX_PATH,
        exact_node_claim_coverage=True,
    )
    theme = _read_json(INDUSTRIAL_AUTOMATION_THEME_PATH)
    mapping = _read_json(INDUSTRIAL_AUTOMATION_MAPPING_PATH)
    source_pack = _read_json(INDUSTRIAL_AUTOMATION_SOURCE_PACK_PATH)
    node_ids = {row["node_id"] for row in theme["nodes"]}
    accepted = validate_theme_evidence_sources(source_pack["sources"], node_ids)
    reviewed_mappings = [
        row for row in mapping["company_mappings"] if row["review_status"] == "reviewed"
    ]

    assert len([row for row in accepted.values() if row["review_status"] == "accepted"]) == 10
    assert all(
        row["source_type"] == "company_filing"
        and row["reliability_level"] == "S0"
        for row in source_pack["sources"]
    )
    assert len(theme["nodes"]) == 10
    assert len(theme["claims"]) == 12
    assert len(reviewed_mappings) == 10
    assert all(set(row) >= CLAIM_FIELDS for row in theme["claims"])


def test_industrial_automation_company_beneficiary_tiers_are_exact():
    expected = {
        "300124.SZ": ("core_beneficiary", "meaningful_segment", "meaningful"),
        "688777.SH": ("core_beneficiary", "meaningful_segment", "meaningful"),
        "688320.SH": ("core_beneficiary", "core_business", "material"),
        "002979.SZ": ("core_beneficiary", "meaningful_segment", "material"),
        "603416.SH": ("core_beneficiary", "meaningful_segment", "meaningful"),
        "688698.SH": ("core_beneficiary", "core_business", "material"),
        "688160.SH": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
        "688188.SH": ("core_beneficiary", "core_business", "material"),
        "301510.SZ": ("core_beneficiary", "meaningful_segment", "meaningful"),
        "002334.SZ": ("core_beneficiary", "core_business", "material"),
    }
    read_model = list_theme_research_companies(INDUSTRIAL_AUTOMATION_THEME_ID)
    response = TestClient(dashboard_app.create_app()).get(
        "/api/research/theme-decomposition/themes/"
        f"{INDUSTRIAL_AUTOMATION_THEME_ID}/companies"
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


def test_industrial_automation_profile_and_catalog_cover_every_node():
    theme = _read_json(INDUSTRIAL_AUTOMATION_THEME_PATH)
    profile = theme["research_profile"]
    node_ids = {row["node_id"] for row in theme["nodes"]}
    claim_ids = {row["claim_id"] for row in theme["claims"]}
    catalog = load_industry_catalog()
    link = next(
        row
        for row in catalog["theme_links"]
        if row["theme_id"] == INDUSTRIAL_AUTOMATION_THEME_ID
    )

    assert profile["catalog_chain_id"] == INDUSTRIAL_AUTOMATION_CHAIN_ID
    assert profile["research_kind"] == "industry_chain_deep_research"
    assert set(profile["catalyst_claim_ids"] + profile["risk_claim_ids"]) <= claim_ids
    assert link["node_links"] == []
    assert set(link["unmapped_theme_node_ids"]) == node_ids
    result = verify_deep_theme_coverage(
        INDUSTRIAL_AUTOMATION_THEME_ID,
        catalog=catalog,
        theme_context=load_theme_research_priority_package(),
    )
    assert result["ready"] is True
    assert all(result["checks"].values())


def test_industrial_automation_revenue_claims_keep_product_boundaries():
    theme = _read_json(INDUSTRIAL_AUTOMATION_THEME_PATH)
    mapping = _read_json(INDUSTRIAL_AUTOMATION_MAPPING_PATH)
    claim_text = next(
        row["claim_text"]
        for row in theme["claims"]
        if row["claim_id"] == "iac_claim_10_direct_revenue"
    )
    evidence_by_id = {row["evidence_id"]: row for row in mapping["evidence_items"]}

    assert "PLC与HMI合并口径" in claim_text
    assert "控制系统总收入而非DCS收入" in claim_text
    assert "伺服与控制系统合并口径" in claim_text
    assert "控制系统包含HMI与PLC" in claim_text
    assert "解决方案包含软件、控制器与硬件" in claim_text
    assert "核心部件包含控制器、驱动器与编码器" in claim_text
    assert "工业自动化总收入不能下沉到PLC或伺服节点" in claim_text
    assert "18亿元为PLC与HMI合并口径" in evidence_by_id[
        "iac_ev_300124_revenue"
    ]["evidence_summary"]
    assert "控制系统总收入11.80亿元" in evidence_by_id[
        "iac_ev_688777_revenue"
    ]["evidence_summary"]
    assert "DCS或SIS独立收入" in evidence_by_id[
        "iac_ev_688777_revenue"
    ]["evidence_summary"]
    assert "包含HMI与PLC" in evidence_by_id["iac_ev_688160_revenue"][
        "evidence_summary"
    ]
    assert "5.765亿元为伺服与控制系统合并口径" in evidence_by_id[
        "iac_ev_688698_revenue"
    ]["evidence_summary"]
    assert "不是纯运动控制卡收入" in evidence_by_id[
        "iac_ev_688188_revenue"
    ]["evidence_summary"]
    assert "3.807亿元核心部件收入包含控制器、驱动器与编码器" in evidence_by_id[
        "iac_ev_301510_revenue"
    ]["evidence_summary"]
    assert "28.111亿元工业自动化总收入不能归入PLC或伺服" in evidence_by_id[
        "iac_ev_002334_revenue"
    ]["evidence_summary"]


def test_power_semiconductors_artifacts_load_and_complete_wave_a():
    theme_package = load_theme_package()
    mapping_package = load_theme_company_mapping_package()
    priority_package = load_theme_research_priority_package()
    catalog = load_industry_catalog()

    assert POWER_SEMICONDUCTORS_THEME_ID in {
        row["theme_id"] for row in theme_package["themes"]
    }
    assert POWER_SEMICONDUCTORS_THEME_ID in {
        row["theme_id"] for row in mapping_package["company_mappings"]
    }
    assert POWER_SEMICONDUCTORS_THEME_ID in {
        row["theme_id"] for row in priority_package["node_priorities"]
    }
    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_a")
    rows = {row["chain_id"]: row for row in report["theme_results"]}

    assert rows[POWER_SEMICONDUCTORS_CHAIN_ID]["ready"] is True
    assert all(rows[POWER_SEMICONDUCTORS_CHAIN_ID]["checks"].values())
    assert report["wave_results"]["wave_a"]["ready"] is True
    assert report["wave_results"]["wave_a"]["theme_count"] == 5
    assert report["wave_results"]["wave_a"]["ready_theme_count"] == 5
    assert report["wave_results"]["wave_a"]["not_ready_theme_count"] == 0
    assert report["completion_status"] == "ready"


def test_power_semiconductors_evidence_mapping_and_links_are_exact():
    _assert_bidirectional_source_and_matrix_links(
        POWER_SEMICONDUCTORS_THEME_PATH,
        POWER_SEMICONDUCTORS_SOURCE_PACK_PATH,
        POWER_SEMICONDUCTORS_MATRIX_PATH,
        exact_node_claim_coverage=True,
    )
    theme = _read_json(POWER_SEMICONDUCTORS_THEME_PATH)
    mapping = _read_json(POWER_SEMICONDUCTORS_MAPPING_PATH)
    source_pack = _read_json(POWER_SEMICONDUCTORS_SOURCE_PACK_PATH)
    node_ids = {row["node_id"] for row in theme["nodes"]}
    accepted = validate_theme_evidence_sources(source_pack["sources"], node_ids)
    reviewed_mappings = [
        row for row in mapping["company_mappings"] if row["review_status"] == "reviewed"
    ]
    evidence_by_id = {row["evidence_id"]: row for row in mapping["evidence_items"]}

    assert len([row for row in accepted.values() if row["review_status"] == "accepted"]) == 11
    assert all(
        row["source_type"] == "company_filing"
        and row["reliability_level"] == "S0"
        for row in source_pack["sources"]
    )
    assert len(theme["nodes"]) == 10
    assert len(theme["claims"]) == 14
    assert all(set(row) >= CLAIM_FIELDS for row in theme["claims"])
    assert len(reviewed_mappings) == 11
    assert len({row["company_code"] for row in reviewed_mappings}) == 11
    for row in reviewed_mappings:
        evidence = [evidence_by_id[evidence_id] for evidence_id in row["evidence_ids"]]
        assert any(
            item["evidence_type"] in {
                "product_relationship",
                "service_relationship",
                "customer_relationship",
            }
            for item in evidence
        )
        assert any(item["evidence_type"] == "revenue_materiality" for item in evidence)


def test_power_semiconductors_company_beneficiary_tiers_are_exact():
    expected = {
        "603290.SH": ("core_beneficiary", "core_business", "material"),
        "600460.SH": ("core_beneficiary", "core_business", "material"),
        "688396.SH": ("elastic_beneficiary", "meaningful_segment", "undisclosed"),
        "300373.SZ": ("elastic_beneficiary", "meaningful_segment", "undisclosed"),
        "300623.SZ": ("elastic_beneficiary", "meaningful_segment", "undisclosed"),
        "605111.SH": ("core_beneficiary", "core_business", "material"),
        "688261.SH": ("core_beneficiary", "core_business", "material"),
        "688187.SH": ("elastic_beneficiary", "meaningful_segment", "undisclosed"),
        "688711.SH": ("core_beneficiary", "core_business", "material"),
        "688234.SH": ("core_beneficiary", "core_business", "material"),
        "600703.SH": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
    }
    read_model = list_theme_research_companies(POWER_SEMICONDUCTORS_THEME_ID)
    response = TestClient(dashboard_app.create_app()).get(
        "/api/research/theme-decomposition/themes/"
        f"{POWER_SEMICONDUCTORS_THEME_ID}/companies"
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


def test_power_semiconductors_profile_catalog_and_gan_route_are_ready():
    theme = _read_json(POWER_SEMICONDUCTORS_THEME_PATH)
    matrix = _read_json(POWER_SEMICONDUCTORS_MATRIX_PATH)
    profile = theme["research_profile"]
    node_ids = {row["node_id"] for row in theme["nodes"]}
    claim_ids = {row["claim_id"] for row in theme["claims"]}
    catalog = load_industry_catalog()
    link = next(
        row
        for row in catalog["theme_links"]
        if row["theme_id"] == POWER_SEMICONDUCTORS_THEME_ID
    )
    gan_row = next(
        row for row in matrix["node_evidence_matrix"] if row["node_id"] == "gan_power_devices"
    )

    assert profile["catalog_chain_id"] == POWER_SEMICONDUCTORS_CHAIN_ID
    assert profile["research_kind"] == "industry_chain_deep_research"
    assert set(profile["catalyst_claim_ids"] + profile["risk_claim_ids"]) <= claim_ids
    assert {
        (row["theme_node_id"], row["catalog_node_id"])
        for row in link["node_links"]
    } == {
        ("device_design_process_platforms", "power_semiconductor_devices"),
        ("silicon_mosfet", "power_mosfet_device"),
        ("sic_power_devices", "silicon_carbide_power_device"),
        ("gan_power_devices", "gallium_nitride_power_device"),
    }
    linked_theme_node_ids = {row["theme_node_id"] for row in link["node_links"]}
    assert set(link["unmapped_theme_node_ids"]) == node_ids - linked_theme_node_ids
    assert gan_row["evidence_gap_status"] == "technical_route_only"
    assert gan_row["accepted_source_ids"]
    assert "power_claim_08_gan_early" in gan_row["supported_claim_ids"]
    result = verify_deep_theme_coverage(
        POWER_SEMICONDUCTORS_THEME_ID,
        catalog=catalog,
        theme_context=load_theme_research_priority_package(),
    )
    assert result["ready"] is True
    assert all(result["checks"].values())


def test_power_semiconductors_revenue_evidence_blocks_over_attribution():
    mapping = _read_json(POWER_SEMICONDUCTORS_MAPPING_PATH)
    by_id = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    mapped_nodes = {
        row["company_code"]: row["mapped_node_id"] for row in mapping["company_mappings"]
    }

    assert "60.28亿元产品与方案包含传感与控制" in by_id[
        "power_ev_688396_revenue"
    ]["evidence_summary"]
    assert "62.57亿元半导体器件收入包含多品类" in by_id[
        "power_ev_300373_revenue"
    ]["evidence_summary"]
    assert "芯片及器件收入未按节点拆分" in by_id[
        "power_ev_300623_revenue"
    ]["evidence_summary"]
    assert "53.60亿元半导体板块收入并非IGBT独立收入" in by_id[
        "power_ev_688187_revenue"
    ]["evidence_summary"]
    assert "29.16亿元集成电路收入包含多品类" in by_id[
        "power_ev_600703_revenue"
    ]["evidence_summary"]
    assert "32.73亿元为IGBT与SiC合计" in by_id[
        "power_ev_600460_revenue"
    ]["evidence_summary"]
    assert "10.3429亿元为模块封装收入，并非单独SiC收入" in by_id[
        "power_ev_688711_revenue"
    ]["evidence_summary"]
    assert "SiC收入约125.69万元" in by_id[
        "power_ev_688261_revenue"
    ]["evidence_summary"]
    assert mapped_nodes["688261.SH"] == "silicon_mosfet"
    assert mapped_nodes["603290.SH"] == "igbt_chips_modules"
    assert "gan_power_devices" not in {
        row["mapped_node_id"]
        for row in mapping["company_mappings"]
        if row["company_code"] == "603290.SH"
    }
    assert all("规划产能" not in row["relationship_summary"] for row in mapping["company_mappings"])
