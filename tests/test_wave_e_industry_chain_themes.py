from __future__ import annotations

import json
import importlib.util
from pathlib import Path

from stock_research.dashboard.theme_research import (
    get_theme_research_theme,
    list_theme_research_claims,
    list_theme_research_companies,
)
from stock_research.technology_industry_catalog import load_industry_catalog
from stock_research.theme_company_mapping import validate_theme_company_mapping_artifact
from stock_research.theme_decomposition import validate_theme_decomposition_artifact


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/batch_manifests"
    / "wave_e_five_industry_chain_themes_v1.json"
)
SCRIPT_PATH = REPOSITORY_ROOT / "scripts/verify_industry_chain_theme_batch.py"
SPEC = importlib.util.spec_from_file_location("verify_wave_e_batch", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)

WAVE_E_CASES = {
    "satellite_communications_navigation_remote_sensing": (
        "satellite_communications_navigation_remote_sensing_value_chain_v1"
    ),
    "intelligent_transport_vehicle_road_cloud": (
        "intelligent_transport_vehicle_road_cloud_value_chain_v1"
    ),
    "brain_computer_interfaces_neural_engineering": (
        "brain_computer_interfaces_neural_engineering_value_chain_v1"
    ),
    "controlled_nuclear_fusion": "controlled_nuclear_fusion_value_chain_v1",
    "quantum_computing_communication_measurement": (
        "quantum_computing_communication_measurement_value_chain_v1"
    ),
}

E1_CHAIN_ID = "satellite_communications_navigation_remote_sensing"
E1_THEME_ID = "satellite_communications_navigation_remote_sensing_value_chain_v1"
E1_THEME_PATH = REPOSITORY_ROOT / f"artifacts/theme_decomposition/{E1_THEME_ID}.json"
E1_MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "satellite_communications_navigation_remote_sensing_company_mapping_v1.json"
)
E1_SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "satellite_communications_navigation_remote_sensing_source_pack_v1.json"
)
E1_MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "satellite_communications_navigation_remote_sensing_node_evidence_matrix_v1.json"
)

E1_NODE_IDS = {
    "satellite_capacity_service_access",
    "satellite_ground_access_terminal_integration",
    "satellite_communications_service_delivery",
    "satellite_navigation_pnt_augmentation_services",
    "remote_sensing_data_processing_distribution",
    "satellite_vertical_application_integration",
    "application_operations_utilization_pricing",
    "recurring_service_revenue_validation",
}

E1_COMPOSITIONS = {
    "satellite_capacity_service_access": "satellite_service_capacity_revenue_validation",
    "satellite_ground_access_terminal_integration": (
        "satellite_ground_tt_c_gateway_terminal_integration"
    ),
    "satellite_communications_service_delivery": (
        "satellite_service_capacity_revenue_validation"
    ),
    "remote_sensing_data_processing_distribution": (
        "communication_navigation_remote_sensing_payload_hardware"
    ),
}

E2_CHAIN_ID = "intelligent_transport_vehicle_road_cloud"
E2_THEME_ID = "intelligent_transport_vehicle_road_cloud_value_chain_v1"
E2_THEME_PATH = REPOSITORY_ROOT / f"artifacts/theme_decomposition/{E2_THEME_ID}.json"
E2_MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "intelligent_transport_vehicle_road_cloud_company_mapping_v1.json"
)
E2_SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "intelligent_transport_vehicle_road_cloud_source_pack_v1.json"
)
E2_MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "intelligent_transport_vehicle_road_cloud_node_evidence_matrix_v1.json"
)

E2_NODE_IDS = {
    "vehicle_data_control_interface_role",
    "roadside_perception_signal_control_role",
    "v2x_connectivity_edge_network_role",
    "transport_cloud_data_governance_role",
    "cooperative_driving_traffic_control_applications",
    "fleet_dispatch_mobility_operations",
    "project_integration_delivery_operations",
    "pilot_utilization_renewal_revenue_validation",
}

E2_COMPOSITIONS = {
    "vehicle_data_control_interface_role": ["vehicle_data_control_interface"],
    "roadside_perception_signal_control_role": [
        "roadside_perception_signal_control_infrastructure"
    ],
    "v2x_connectivity_edge_network_role": ["v2x_edge_network_infrastructure"],
    "transport_cloud_data_governance_role": [
        "transport_cloud_data_platform",
        "transport_data_security_governance",
    ],
}

E2_CANONICAL_TARGETS = {
    "vehicle_data_control_interface": "automotive_electronics_chip_applications",
    "roadside_perception_signal_control_infrastructure": "network_equipment_edge_iot",
    "v2x_edge_network_infrastructure": "network_equipment_edge_iot",
    "transport_cloud_data_platform": "cloud_data_center_infrastructure",
    "transport_data_security_governance": "cybersecurity_data_infrastructure",
}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _paths(chain_id: str, theme_id: str) -> dict[str, str]:
    return {
        "theme": f"artifacts/theme_decomposition/{theme_id}.json",
        "company_mapping": (
            "artifacts/theme_decomposition/company_mappings/"
            f"{chain_id}_company_mapping_v1.json"
        ),
        "source_pack": (
            "artifacts/theme_decomposition/source_packs/"
            f"{chain_id}_source_pack_v1.json"
        ),
        "node_evidence_matrix": (
            "artifacts/theme_decomposition/source_packs/"
            f"{chain_id}_node_evidence_matrix_v1.json"
        ),
    }


def test_wave_e_manifest_freezes_research_scope() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    expected_completion_gates = {
        "min_accepted_sources": 10,
        "min_primary_sources": 8,
        "min_claims": 12,
        "min_reviewed_mappings": 8,
        "require_node_evidence_matrix_coverage": True,
        "require_bidirectional_evidence_contract": True,
        "require_precise_mapping_locators": True,
        "required_readable_sections": [
            {
                "name": "研究结论",
                "non_empty": [
                    "theme:research_profile.investment_summary",
                    "theme:research_profile.industry_stage",
                    "theme:research_profile.central_conflict",
                ],
            },
            {
                "name": "价值链",
                "non_empty": [
                    "theme:research_profile.value_flow_summary",
                    "theme:nodes",
                ],
            },
            {
                "name": "利润池与竞争壁垒",
                "non_empty": ["theme:research_profile.profit_pool_summary"],
            },
            {
                "name": "催化、验证信号与风险",
                "non_empty": [
                    "theme:research_profile.catalyst_claim_ids",
                    "theme:research_profile.risk_claim_ids",
                    "theme:research_profile.validation_signals",
                ],
            },
            {
                "name": "受益公司",
                "non_empty": ["company_mapping:company_mappings"],
            },
            {
                "name": "来源证据",
                "non_empty": ["source_pack:sources"],
            },
            {
                "name": "证据缺口与更新",
                "non_empty": [
                    "theme:research_profile.evidence_gap_summary",
                    "node_evidence_matrix:node_evidence_matrix",
                ],
            },
        ],
    }
    expected_themes = {
        chain_id: {
            "theme_id": theme_id,
            "artifacts": _paths(chain_id, theme_id),
        }
        for chain_id, theme_id in WAVE_E_CASES.items()
    }

    assert manifest["schema_version"] == "industry_chain_theme_batch_v1"
    assert manifest["batch_id"] == "wave_e_five_industry_chain_themes_v1"
    assert manifest["target_theme_count"] == 5
    assert manifest["artifact_base"] == "../../.."
    assert manifest["primary_source_types"] == [
        "company_filing",
        "official_report",
        "official_article",
    ]
    assert manifest["completion_gates"] == expected_completion_gates
    assert manifest["waves"] == {"wave_e": list(WAVE_E_CASES)}
    assert manifest["themes"] == expected_themes
    assert list(manifest["themes"]) == list(WAVE_E_CASES)


def test_satellite_communications_e1_four_research_artifacts_exist_before_validation() -> None:
    for path in (
        E1_THEME_PATH,
        E1_MAPPING_PATH,
        E1_SOURCE_PACK_PATH,
        E1_MATRIX_PATH,
    ):
        assert path.is_file(), path


def test_satellite_communications_e1_theme_meets_strict_wave_e_gate_and_exact_node_scope() -> None:
    theme = _read_json(E1_THEME_PATH)
    mapping = _read_json(E1_MAPPING_PATH)
    validate_theme_decomposition_artifact(theme, expected_theme_id=E1_THEME_ID)
    validate_theme_company_mapping_artifact(mapping, theme)
    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_e")
    row = next(item for item in report["theme_results"] if item["chain_id"] == E1_CHAIN_ID)

    assert theme["artifact_version"] == "theme_decomposition_v1_6"
    assert theme["theme"]["status"] == "reviewed"
    assert theme["theme"]["created_from"] == "mixed"
    assert theme["research_profile"]["catalog_chain_id"] == E1_CHAIN_ID
    assert theme["research_profile"]["research_kind"] == "industry_chain_deep_research"
    assert {node["node_id"] for node in theme["nodes"]} == E1_NODE_IDS
    assert len(theme["sources"]) == 10
    assert len(theme["claims"]) == 15
    assert len(
        [item for item in mapping["company_mappings"] if item["review_status"] == "reviewed"]
    ) == 8
    assert {row["node_id"] for row in theme["value_capture_assessments"]} == E1_NODE_IDS
    assert row["ready"] is True
    assert row["checks"]["bidirectional_evidence_contract"] is True
    assert row["checks"]["precise_mapping_locators"] is True


def test_satellite_communications_e1_catalog_roles_links_and_compositions_preserve_d4_ownership() -> None:
    catalog = load_industry_catalog()
    chain_nodes = [row for row in catalog["nodes"] if row["chain_id"] == E1_CHAIN_ID]
    assert {row["node_id"] for row in chain_nodes} == E1_NODE_IDS
    assert all(row["node_kind"] == "application_role" for row in chain_nodes)
    assert all(row["canonical_key"] == "" for row in chain_nodes)
    assert {row["level"] for row in chain_nodes} == {"L3", "L4"}

    link = next(row for row in catalog["theme_links"] if row["theme_id"] == E1_THEME_ID)
    assert link["chain_id"] == E1_CHAIN_ID
    assert link["unmapped_theme_node_ids"] == []
    assert {row["theme_node_id"] for row in link["node_links"]} == E1_NODE_IDS
    assert {row["catalog_node_id"] for row in link["node_links"]} == E1_NODE_IDS

    composition_path = (
        REPOSITORY_ROOT
        / "artifacts/technology_industry_catalog/v1/theme_compositions"
        / "satellite_communications_navigation_remote_sensing_v1.json"
    )
    compositions = _read_json(composition_path)["theme_compositions"]
    actual = {
        row["role_node_id"]: row["canonical_node_refs"][0] for row in compositions
    }
    assert actual == E1_COMPOSITIONS
    assert all(row["relationship_type"] == "depends_on" for row in compositions)
    catalog_node_ids = {row["node_id"] for row in catalog["nodes"]}
    assert set(E1_COMPOSITIONS.values()) <= catalog_node_ids


def test_satellite_communications_e1_company_evidence_uses_sources_roles_and_locators() -> None:
    theme = _read_json(E1_THEME_PATH)
    mapping = _read_json(E1_MAPPING_PATH)
    source_pack = _read_json(E1_SOURCE_PACK_PATH)
    matrix = _read_json(E1_MATRIX_PATH)

    theme_source_ids = {row["source_id"] for row in theme["sources"]}
    mapping_source_ids = {row["source_id"] for row in mapping["sources"]}
    source_pack_ids = {row["source_id"] for row in source_pack["sources"]}
    assert theme_source_ids == mapping_source_ids == source_pack_ids

    def source_identity(rows: list[dict]) -> dict[str, tuple]:
        return {
            row["source_id"]: (
                row["source_type"],
                row["title"],
                row["publisher"],
                row["author"],
                row["publish_date"],
                row.get("url_or_ref", row.get("url")),
                row["access_level"],
                row["reliability_level"],
                row["review_status"],
            )
            for row in rows
        }

    assert source_identity(theme["sources"]) == source_identity(mapping["sources"])
    assert source_identity(theme["sources"]) == source_identity(source_pack["sources"])
    assert len(
        [row for row in source_pack["sources"] if row["source_type"] in {
            "company_filing", "official_report", "official_article"
        }]
    ) >= 8
    assert {row["node_id"] for row in matrix["node_evidence_matrix"]} == E1_NODE_IDS
    assert {
        row["company_code"] for row in mapping["company_mappings"]
        if row["review_status"] == "reviewed"
    } == {
        "601698.SH",
        "688568.SH",
        "688066.SH",
        "300627.SZ",
        "002151.SZ",
        "300101.SZ",
        "688592.SH",
        "002383.SZ",
    }

    evidence_by_id = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    for row in mapping["company_mappings"]:
        evidence = [evidence_by_id[evidence_id] for evidence_id in row["evidence_ids"]]
        assert len(evidence) == 3
        assert {item["evidence_type"] for item in evidence} in (
            {"product_relationship", "revenue_materiality", "business_stage"},
            {"service_relationship", "revenue_materiality", "business_stage"},
        )
        assert len({item["excerpt_locator"] for item in evidence}) == 3
        assert all("页" in item["excerpt_locator"] for item in evidence)


def test_satellite_communications_e1_dashboard_explains_capacity_and_recurring_revenue() -> None:
    detail = get_theme_research_theme(E1_THEME_ID)
    summary = detail["research_profile"]["investment_summary"]
    assert "在轨容量" in summary
    assert "服务利用" in summary
    assert "经常性收入" in summary

    claims = list_theme_research_claims(E1_THEME_ID)["items"]
    claim_types = {row["claim_type"] for row in claims}
    assert {
        "value_capture", "bottleneck", "tech_route", "catalyst", "risk", "company_mapping"
    } <= claim_types
    assert any("验证" in row["claim_text"] for row in claims)

    companies = list_theme_research_companies(E1_THEME_ID)["items"]
    assert {row["company_code"]: row["beneficiary_tier"] for row in companies} == {
        "601698.SH": "core_beneficiary",
        "688568.SH": "core_beneficiary",
        "688066.SH": "core_beneficiary",
        "300627.SZ": "core_beneficiary",
        "002151.SZ": "core_beneficiary",
        "300101.SZ": "elastic_beneficiary",
        "688592.SH": "elastic_beneficiary",
        "002383.SZ": "elastic_beneficiary",
    }


def test_satellite_communications_e1_boundary_excludes_hardware_only_beneficiaries() -> None:
    theme = _read_json(E1_THEME_PATH)
    mapping = _read_json(E1_MAPPING_PATH)
    all_text = json.dumps({"theme": theme, "mapping": mapping}, ensure_ascii=False)
    assert "satellite_manufacturing_space_infrastructure" in all_text
    assert "平台" in all_text and "载荷硬件" in all_text and "组批制造" in all_text
    assert "600118.SH" not in {
        row["company_code"] for row in mapping["company_mappings"]
        if row["review_status"] == "reviewed"
    }
    assert {"002405.SZ", "002465.SZ"}.isdisjoint({
        row["company_code"] for row in mapping["company_mappings"]
        if row["review_status"] == "reviewed"
    })
    assert "四维图新" in all_text and "通用地图或智云收入" in all_text
    assert "海格通信" in all_text and "终端、信关站研发或试运行" in all_text
    forbidden_mapping_types = {"component_supplier", "equipment_supplier"}
    assert not {
        row["mapping_id"] for row in mapping["company_mappings"]
        if row["mapping_type"] in forbidden_mapping_types
        and row["mapped_node_id"] == "satellite_capacity_service_access"
    }


def test_satellite_communications_e1_strength_and_gap_statuses_are_conservative() -> None:
    theme = _read_json(E1_THEME_PATH)
    matrix = _read_json(E1_MATRIX_PATH)
    theme_nodes = {row["node_id"]: row for row in theme["nodes"]}
    matrix_nodes = {row["node_id"]: row for row in matrix["node_evidence_matrix"]}

    for node_id in (
        "application_operations_utilization_pricing",
        "recurring_service_revenue_validation",
    ):
        assert theme_nodes[node_id]["node_review_status"] == "draft"
        assert theme_nodes[node_id]["evidence_strength"] <= 3
        assert matrix_nodes[node_id]["node_review_status"] == "draft"
        assert matrix_nodes[node_id]["evidence_strength_after"] == theme_nodes[node_id][
            "evidence_strength"
        ]
        assert matrix_nodes[node_id]["evidence_gap_status"] == "evidence_gap"

    for node_id, node in theme_nodes.items():
        matrix_row = matrix_nodes[node_id]
        if node["evidence_strength"] == 5 and matrix_row["evidence_gap_status"] == "covered":
            next_evidence = matrix_row["next_evidence_needed"]
            assert not any(metric in next_evidence for metric in node["key_metrics"])


def test_satellite_communications_e1_value_capture_assessments_only_use_node_claims() -> None:
    theme = _read_json(E1_THEME_PATH)
    claims = {row["claim_id"]: row for row in theme["claims"]}

    for assessment in theme["value_capture_assessments"]:
        for claim_id in assessment["evidence_ids"]:
            assert assessment["node_id"] in claims[claim_id]["affected_theme_nodes"]


def test_vehicle_road_cloud_e2_four_research_artifacts_exist_before_validation() -> None:
    for path in (
        E2_THEME_PATH,
        E2_MAPPING_PATH,
        E2_SOURCE_PACK_PATH,
        E2_MATRIX_PATH,
    ):
        assert path.is_file(), path


def test_vehicle_road_cloud_e2_theme_meets_strict_wave_e_gate_and_exact_node_scope() -> None:
    theme = _read_json(E2_THEME_PATH)
    mapping = _read_json(E2_MAPPING_PATH)
    validate_theme_decomposition_artifact(theme, expected_theme_id=E2_THEME_ID)
    validate_theme_company_mapping_artifact(mapping, theme)
    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_e")
    row = next(item for item in report["theme_results"] if item["chain_id"] == E2_CHAIN_ID)

    assert theme["artifact_version"] == "theme_decomposition_v1_6"
    assert theme["theme"]["status"] == "reviewed"
    assert theme["theme"]["created_from"] == "mixed"
    assert theme["research_profile"]["catalog_chain_id"] == E2_CHAIN_ID
    assert theme["research_profile"]["research_kind"] == "industry_chain_deep_research"
    assert len(theme["nodes"]) == len(E2_NODE_IDS)
    assert {node["node_id"] for node in theme["nodes"]} == E2_NODE_IDS
    assert len(theme["value_capture_assessments"]) == len(E2_NODE_IDS)
    assert {row["node_id"] for row in theme["value_capture_assessments"]} == E2_NODE_IDS
    assert len(theme["sources"]) == 10
    assert len(theme["claims"]) == 12
    assert len(
        [item for item in mapping["company_mappings"] if item["review_status"] == "reviewed"]
    ) == 8
    assert row["ready"] is True
    assert row["checks"]["bidirectional_evidence_contract"] is True
    assert row["checks"]["precise_mapping_locators"] is True


def test_vehicle_road_cloud_e2_catalog_supporting_nodes_roles_links_and_compositions() -> None:
    catalog = load_industry_catalog()
    chain_nodes = [row for row in catalog["nodes"] if row["chain_id"] == E2_CHAIN_ID]
    assert len(chain_nodes) == len(E2_NODE_IDS)
    assert {row["node_id"] for row in chain_nodes} == E2_NODE_IDS
    assert all(row["node_kind"] == "application_role" for row in chain_nodes)
    assert all(row["canonical_key"] == "" for row in chain_nodes)
    assert {row["level"] for row in chain_nodes} == {"L3", "L4"}

    nodes_by_id = {row["node_id"]: row for row in catalog["nodes"]}
    assert {
        node_id: nodes_by_id[node_id]["chain_id"] for node_id in E2_CANONICAL_TARGETS
    } == E2_CANONICAL_TARGETS
    for node_id in E2_CANONICAL_TARGETS:
        node = nodes_by_id[node_id]
        assert node["level"] == "L4"
        assert node["node_kind"] == "canonical"
        assert node["canonical_key"]
        parent = nodes_by_id[node["parent_node_id"]]
        assert parent["level"] == "L3"
        assert parent["chain_id"] == node["chain_id"]
        assert parent["canonical_key"] == ""

    link = next(row for row in catalog["theme_links"] if row["theme_id"] == E2_THEME_ID)
    assert link["chain_id"] == E2_CHAIN_ID
    assert link["unmapped_theme_node_ids"] == []
    assert len(link["node_links"]) == len(E2_NODE_IDS)
    assert {row["theme_node_id"] for row in link["node_links"]} == E2_NODE_IDS
    assert {row["catalog_node_id"] for row in link["node_links"]} == E2_NODE_IDS

    composition_path = (
        REPOSITORY_ROOT
        / "artifacts/technology_industry_catalog/v1/theme_compositions"
        / "intelligent_transport_vehicle_road_cloud_v1.json"
    )
    compositions = _read_json(composition_path)["theme_compositions"]
    assert len(compositions) == len(E2_COMPOSITIONS)
    assert {
        row["role_node_id"]: row["canonical_node_refs"] for row in compositions
    } == E2_COMPOSITIONS
    assert all(row["relationship_type"] == "depends_on" for row in compositions)


def test_vehicle_road_cloud_e2_source_identity_reverse_contract_and_filing_locators() -> None:
    theme = _read_json(E2_THEME_PATH)
    mapping = _read_json(E2_MAPPING_PATH)
    source_pack = _read_json(E2_SOURCE_PACK_PATH)
    matrix = _read_json(E2_MATRIX_PATH)

    def source_identity(rows: list[dict]) -> dict[str, tuple]:
        return {
            row["source_id"]: (
                row["source_type"],
                row["title"],
                row["publisher"],
                row["author"],
                row["publish_date"],
                row.get("url_or_ref", row.get("url")),
                row["access_level"],
                row["reliability_level"],
                row["review_status"],
            )
            for row in rows
        }

    assert source_identity(theme["sources"]) == source_identity(mapping["sources"])
    assert source_identity(theme["sources"]) == source_identity(source_pack["sources"])
    accepted_source_ids = {
        row["source_id"] for row in source_pack["sources"]
        if row["review_status"] == "accepted"
    }
    accepted_primary_sources = [
        row for row in source_pack["sources"]
        if row["review_status"] == "accepted"
        and row["source_id"] in accepted_source_ids
        if row["source_type"] in {"company_filing", "official_report", "official_article"}
    ]
    assert len(accepted_source_ids) >= 10
    assert len(accepted_primary_sources) >= 8

    claims = {row["claim_id"]: row for row in theme["claims"]}
    matrix_by_node = {row["node_id"]: row for row in matrix["node_evidence_matrix"]}
    assert set(matrix_by_node) == E2_NODE_IDS
    for source in source_pack["sources"]:
        expected_claim_ids = {
            claim_id for claim_id, claim in claims.items()
            if claim["source_id"] == source["source_id"]
            or source["source_id"] in claim["supporting_source_ids"]
        }
        assert set(source["supported_claim_ids"]) == expected_claim_ids
        assert set(source["supported_node_ids"]) == {
            node_id for claim_id in expected_claim_ids
            for node_id in claims[claim_id]["affected_theme_nodes"]
        }
    for node_id, matrix_row in matrix_by_node.items():
        assert set(matrix_row["supported_claim_ids"]) == {
            claim_id for claim_id, claim in claims.items()
            if node_id in claim["affected_theme_nodes"]
        }
        assert set(matrix_row["accepted_source_ids"]) <= accepted_source_ids

    evidence_by_id = {row["evidence_id"]: row for row in mapping["evidence_items"]}
    for row in mapping["company_mappings"]:
        evidence = [evidence_by_id[evidence_id] for evidence_id in row["evidence_ids"]]
        assert len(evidence) == 3
        assert {item["evidence_type"] for item in evidence} in (
            {"product_relationship", "revenue_materiality", "business_stage"},
            {"service_relationship", "revenue_materiality", "business_stage"},
        )
        assert len({item["excerpt_locator"] for item in evidence}) == 3
        assert all("页" in item["excerpt_locator"] for item in evidence)


def test_vehicle_road_cloud_e2_stage_boundaries_and_generic_hardware_exclusions() -> None:
    theme = _read_json(E2_THEME_PATH)
    mapping = _read_json(E2_MAPPING_PATH)
    all_text = json.dumps({"theme": theme, "mapping": mapping}, ensure_ascii=False)
    for boundary in (
        "试点批复不等于项目中标",
        "框架或联合体入围不等于合同",
        "合同不等于系统交付",
        "交付不等于验收",
        "验收不等于收入确认",
        "基础设施收入不等于平台利用率",
        "利用率不等于续约或经常性运维收入",
    ):
        assert boundary in all_text
    reviewed_codes = {
        row["company_code"] for row in mapping["company_mappings"]
        if row["review_status"] == "reviewed"
    }
    assert {"002405.SZ", "300496.SZ", "300098.SZ", "300020.SZ"}.isdisjoint(
        reviewed_codes
    )
    assert "通用摄像头、雷达、芯片、交换机、服务器、云设施或汽车零部件" in all_text
    assert "intelligent_driving_smart_cockpit" in all_text
    assert "automotive_electronics_chip_applications" in all_text


def test_vehicle_road_cloud_e2_utilization_and_renewal_maturity_is_conservative() -> None:
    theme = _read_json(E2_THEME_PATH)
    matrix = _read_json(E2_MATRIX_PATH)
    theme_nodes = {row["node_id"]: row for row in theme["nodes"]}
    matrix_nodes = {row["node_id"]: row for row in matrix["node_evidence_matrix"]}
    node_id = "pilot_utilization_renewal_revenue_validation"
    assert theme_nodes[node_id]["node_review_status"] == "draft"
    assert theme_nodes[node_id]["evidence_strength"] <= 3
    assert matrix_nodes[node_id]["node_review_status"] == "draft"
    assert matrix_nodes[node_id]["evidence_gap_status"] == "evidence_gap"
    assert "会计政策" in matrix_nodes[node_id]["next_evidence_needed"]
    assert "续约" in matrix_nodes[node_id]["next_evidence_needed"]


def test_vehicle_road_cloud_e2_value_capture_assessments_only_use_node_claims() -> None:
    theme = _read_json(E2_THEME_PATH)
    claims = {row["claim_id"]: row for row in theme["claims"]}

    for assessment in theme["value_capture_assessments"]:
        for claim_id in assessment["evidence_ids"]:
            assert assessment["node_id"] in claims[claim_id]["affected_theme_nodes"]


def test_vehicle_road_cloud_e2_stage_claims_only_assert_filing_observations() -> None:
    theme = _read_json(E2_THEME_PATH)
    claims = {row["claim_id"]: row for row in theme["claims"]}
    delivery_claim = claims["vehicle_road_cloud_claim_11"]
    recognition_claim = claims["vehicle_road_cloud_claim_12"]

    assert delivery_claim["source_id"] == "vehicle_road_cloud_002373_filing"
    assert "解决方案" in delivery_claim["claim_text"]
    assert "研发交付" in delivery_claim["claim_text"]
    assert "智慧交通收入" in delivery_claim["claim_text"]
    assert "证据缺口" in delivery_claim["claim_text"]
    assert "必须逐级验证" not in delivery_claim["claim_text"]
    assert "批复、入围、中标、合同、交付、验收、收入确认与回款" not in delivery_claim[
        "claim_text"
    ]
    assert "任何前序阶段都不能替代后序商业兑现" not in delivery_claim["claim_text"]
    assert set(delivery_claim["affected_theme_nodes"]) == {
        "project_integration_delivery_operations",
        "pilot_utilization_renewal_revenue_validation",
    }

    assert recognition_claim["source_id"] == "vehicle_road_cloud_301339_filing"
    assert "客户验收后确认收入" in recognition_claim["claim_text"]
    assert "合同执行期逐月确认" in recognition_claim["claim_text"]
    assert "不证明试点利用率、续约或经常性运维收入" in recognition_claim["claim_text"]
    assert "基础设施收入不等于平台利用率" not in recognition_claim["claim_text"]
    assert set(recognition_claim["affected_theme_nodes"]) == {
        "project_integration_delivery_operations",
        "pilot_utilization_renewal_revenue_validation",
    }


def test_vehicle_road_cloud_e2_project_stage_evidence_remains_partial() -> None:
    theme = _read_json(E2_THEME_PATH)
    matrix = _read_json(E2_MATRIX_PATH)
    theme_node = next(
        row for row in theme["nodes"]
        if row["node_id"] == "project_integration_delivery_operations"
    )
    matrix_node = next(
        row for row in matrix["node_evidence_matrix"]
        if row["node_id"] == "project_integration_delivery_operations"
    )

    assert theme_node["evidence_strength"] == 4
    assert matrix_node["evidence_strength_after"] == 4
    assert matrix_node["evidence_gap_status"] == "supported"
    assert "批复" in matrix_node["next_evidence_needed"]
    assert "入围" in matrix_node["next_evidence_needed"]
    assert "正式授标" in matrix_node["next_evidence_needed"]
    assert "合同" in matrix_node["next_evidence_needed"]
    assert "回款" in matrix_node["next_evidence_needed"]


def test_vehicle_road_cloud_e2_company_tiers_and_revenue_materiality_are_exact() -> None:
    expected = {
        "002373.SZ": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
        "300552.SZ": ("elastic_beneficiary", "emerging_segment", "limited"),
        "002869.SZ": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
        "301339.SZ": ("core_beneficiary", "core_business", "material"),
        "300212.SZ": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
        "002331.SZ": ("core_beneficiary", "core_business", "material"),
        "002401.SZ": ("elastic_beneficiary", "emerging_segment", "undisclosed"),
        "300807.SZ": ("core_beneficiary", "core_business", "material"),
    }
    payload = list_theme_research_companies(E2_THEME_ID)

    assert payload["total"] == len(expected)
    assert {
        row["company_code"]: (
            row["beneficiary_tier"],
            row["business_materiality"],
            row["revenue_relevance"],
        )
        for row in payload["items"]
    } == expected

    theme = _read_json(E2_THEME_PATH)
    summary = theme["research_profile"]["investment_summary"]
    assert "千方科技、中远海科" in summary
    assert "弹性受益" in summary


def test_vehicle_road_cloud_e2_toll_revenue_separates_issuance_and_service() -> None:
    theme = _read_json(E2_THEME_PATH)
    mapping = _read_json(E2_MAPPING_PATH)
    source_pack = _read_json(E2_SOURCE_PACK_PATH)
    claim = next(
        row for row in theme["claims"]
        if row["claim_id"] == "vehicle_road_cloud_claim_04"
    )
    revenue_evidence = next(
        row for row in mapping["evidence_items"]
        if row["evidence_id"] == "vehicle_road_cloud_301339_revenue"
    )
    company = next(
        row for row in mapping["company_mappings"]
        if row["company_code"] == "301339.SZ"
    )
    source = next(
        row for row in source_pack["sources"]
        if row["source_id"] == "vehicle_road_cloud_301339_filing"
    )
    matrix = next(
        row for row in _read_json(E2_MATRIX_PATH)["node_evidence_matrix"]
        if row["node_id"] == "fleet_dispatch_mobility_operations"
    )
    all_text = json.dumps(
        {
            "claim": claim,
            "revenue_evidence": revenue_evidence,
            "company": company,
            "source": source,
            "matrix": matrix,
        },
        ensure_ascii=False,
    )

    assert "运营管理系统业务收入6.405亿元" in claim["claim_text"]
    assert "ETC发行与销售2.476亿元" in claim["claim_text"]
    assert "电子收费服务1.463亿元" in claim["claim_text"]
    assert "电子收费业务合计3.938亿元" in claim["claim_text"]
    for amount in ("64,052.64万元", "24,756.81万元", "14,626.08万元"):
        assert amount in revenue_evidence["evidence_summary"]
    assert "6.405亿元" in company["relationship_summary"]
    assert "1.463亿元" in company["relationship_summary"]
    assert "14,626.08万元" in source["evidence_summary"]
    assert "14,626.08万元" in matrix["rationale"]
    assert "电子收费服务收入3.938亿元" not in all_text


def test_vehicle_road_cloud_e2_four_dimensional_projects_are_acknowledged_but_excluded() -> None:
    theme = _read_json(E2_THEME_PATH)
    source_pack = _read_json(E2_SOURCE_PACK_PATH)
    matrix = _read_json(E2_MATRIX_PATH)
    mapping = _read_json(E2_MAPPING_PATH)
    claim = next(
        row for row in theme["claims"]
        if row["claim_id"] == "vehicle_road_cloud_claim_10"
    )
    source = next(
        row for row in source_pack["sources"]
        if row["source_id"] == "vehicle_road_cloud_002405_boundary_filing"
    )
    matrix_by_node = {
        row["node_id"]: row for row in matrix["node_evidence_matrix"]
    }

    assert "已完成北京、深圳、无锡、湖南等多地车路云项目" in claim["claim_text"]
    for gap in ("项目具体范围", "E2收入材料性", "平台利用率", "经常性运营或续约"):
        assert gap in claim["claim_text"]
    assert set(claim["affected_theme_nodes"]) == {
        "pilot_utilization_renewal_revenue_validation"
    }
    assert "第10-11页" in source["evidence_locator"]
    assert "北京、深圳、无锡、湖南" in source["evidence_summary"]
    assert set(source["supported_node_ids"]) == {
        "pilot_utilization_renewal_revenue_validation"
    }
    for node_id in (
        "vehicle_data_control_interface_role",
        "transport_cloud_data_governance_role",
    ):
        assert "vehicle_road_cloud_002405_boundary_filing" not in matrix_by_node[
            node_id
        ]["accepted_source_ids"]
        assert "vehicle_road_cloud_claim_10" not in matrix_by_node[node_id][
            "supported_claim_ids"
        ]
    assert "vehicle_road_cloud_002405_boundary_filing" in matrix_by_node[
        "pilot_utilization_renewal_revenue_validation"
    ]["accepted_source_ids"]
    assert "002405.SZ" not in {
        row["company_code"] for row in mapping["company_mappings"]
    }


def test_vehicle_road_cloud_e2_node_maturity_and_boundary_evidence_are_conservative() -> None:
    theme = _read_json(E2_THEME_PATH)
    matrix = _read_json(E2_MATRIX_PATH)
    theme_nodes = {row["node_id"]: row for row in theme["nodes"]}
    matrix_nodes = {
        row["node_id"]: row for row in matrix["node_evidence_matrix"]
    }
    expected = {
        "vehicle_data_control_interface_role": (3, "needs_evidence", "evidence_gap"),
        "v2x_connectivity_edge_network_role": (4, "reviewed", "supported"),
        "transport_cloud_data_governance_role": (4, "reviewed", "supported"),
        "cooperative_driving_traffic_control_applications": (4, "reviewed", "supported"),
        "fleet_dispatch_mobility_operations": (4, "reviewed", "supported"),
    }

    for node_id, (strength, review_status, gap_status) in expected.items():
        assert theme_nodes[node_id]["evidence_strength"] == strength
        assert theme_nodes[node_id]["node_review_status"] == review_status
        assert matrix_nodes[node_id]["evidence_strength_after"] == strength
        assert matrix_nodes[node_id]["node_review_status"] == review_status
        assert matrix_nodes[node_id]["evidence_gap_status"] == gap_status

    required_gaps = {
        "vehicle_data_control_interface_role": (
            "独立接口授权",
            "接入车型车辆数",
            "接口可用率",
        ),
        "v2x_connectivity_edge_network_role": (
            "活跃连接",
            "消息量",
            "SLA",
        ),
        "transport_cloud_data_governance_role": (
            "API调用",
            "模型推理与使用",
            "应用治理结果",
        ),
        "cooperative_driving_traffic_control_applications": (
            "处置率",
            "效率改善",
            "活跃用户车辆",
            "持续使用",
        ),
        "fleet_dispatch_mobility_operations": (
            "活跃用户",
            "交易笔数",
            "续约率",
        ),
    }
    for node_id, required_terms in required_gaps.items():
        next_evidence = matrix_nodes[node_id]["next_evidence_needed"]
        assert all(term in next_evidence for term in required_terms)

    for node_id, node in theme_nodes.items():
        matrix_row = matrix_nodes[node_id]
        assert node["evidence_strength"] == matrix_row["evidence_strength_after"]
        assert node["node_review_status"] == matrix_row["node_review_status"]
        if node["evidence_strength"] == 5 and matrix_row["evidence_gap_status"] == "covered":
            assert not any(
                metric in matrix_row["next_evidence_needed"]
                for metric in node["key_metrics"]
            )

    claims = {row["claim_id"]: row for row in theme["claims"]}
    boundary_claim_ids = {
        claim_id for claim_id, claim in claims.items()
        if claim["source_id"].endswith("_boundary_filing")
    }
    for assessment in theme["value_capture_assessments"]:
        assert set(assessment["evidence_ids"]).isdisjoint(boundary_claim_ids)
    for node_id, matrix_row in matrix_nodes.items():
        if theme_nodes[node_id]["evidence_strength"] >= 4:
            assert set(matrix_row["supported_claim_ids"]) - boundary_claim_ids


def test_vehicle_road_cloud_e2_transport_governance_ownership_is_sharp() -> None:
    theme = _read_json(E2_THEME_PATH)
    catalog = load_industry_catalog()
    theme_node = next(
        row for row in theme["nodes"]
        if row["node_id"] == "transport_cloud_data_governance_role"
    )
    role_node = next(
        row for row in catalog["nodes"]
        if row["node_id"] == "transport_cloud_data_governance_role"
    )
    canonical_node = next(
        row for row in catalog["nodes"]
        if row["node_id"] == "transport_data_security_governance"
    )

    assert "应用工作流与治理结果" in theme_node["description"]
    assert "归transport_data_security_governance canonical node" in theme_node[
        "description"
    ]
    assert "最小权限" not in theme_node["description"]
    assert "审计留痕" not in theme_node["description"]
    assert "安全监控" not in theme_node["description"]
    assert "application workflow and governance outcomes" in role_node["description"]
    assert "remain canonical dependencies" in role_node["description"]
    assert "least-privilege" not in role_node["description"]
    assert "audit trails" not in role_node["description"]
    assert "reusable permission, audit, and security controls" in canonical_node[
        "description"
    ].lower()
