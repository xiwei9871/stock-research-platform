from __future__ import annotations

import importlib.util
import json
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
    / "wave_d_five_industry_chain_themes_v1.json"
)
SCRIPT_PATH = REPOSITORY_ROOT / "scripts/verify_industry_chain_theme_batch.py"
SPEC = importlib.util.spec_from_file_location("verify_wave_d_batch", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)

D1_CHAIN_ID = "semiconductor_eda_ip_design_services"
D1_THEME_ID = "semiconductor_eda_ip_design_services_value_chain_v1"
D1_THEME_PATH = REPOSITORY_ROOT / f"artifacts/theme_decomposition/{D1_THEME_ID}.json"
D1_MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "semiconductor_eda_ip_design_services_company_mapping_v1.json"
)
D1_SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "semiconductor_eda_ip_design_services_source_pack_v1.json"
)
D1_MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "semiconductor_eda_ip_design_services_node_evidence_matrix_v1.json"
)

D1_NODE_IDS = {
    "eda_frontend_design_verification",
    "eda_backend_physical_design_signoff",
    "analog_rf_mixed_signal_eda",
    "semiconductor_ip_cores_interfaces",
    "chiplet_package_design_enablement",
    "ic_design_services_verification_tapeout",
    "foundry_pdk_ecosystem_qualification",
    "licensing_subscription_royalty_model",
    "customer_adoption_revenue_validation",
}

D1_CATALOG_LINKS = {
    "eda_frontend_design_verification": {
        "eda_frontend_design_verification",
        "rtl_synthesis_design_entry",
        "functional_verification_formal",
        "hardware_emulation_prototyping",
    },
    "eda_backend_physical_design_signoff": {
        "eda_physical_design_signoff",
        "place_route_timing_signoff",
        "power_integrity_thermal_signoff",
        "dfm_mask_data_preparation",
    },
    "analog_rf_mixed_signal_eda": {"analog_rf_mixed_signal_design_eda"},
    "semiconductor_ip_cores_interfaces": {
        "semiconductor_ip_cores_interfaces",
        "processor_architecture_ip_core",
        "high_speed_interface_ip",
        "analog_mixed_signal_ip",
    },
    "chiplet_package_design_enablement": {"chiplet_package_co_design"},
    "ic_design_services_verification_tapeout": {
        "chip_design_services_tapeout",
        "ic_design_customization_service",
        "functional_verification_service",
        "physical_design_tapeout_service",
    },
    "foundry_pdk_ecosystem_qualification": {
        "design_enablement_ecosystem",
        "foundry_pdk_design_enablement",
    },
}

D2_CHAIN_ID = "memory_chips_storage_control"
D2_THEME_ID = "memory_chips_storage_control_value_chain_v1"
D2_THEME_PATH = REPOSITORY_ROOT / f"artifacts/theme_decomposition/{D2_THEME_ID}.json"
D2_MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "memory_chips_storage_control_company_mapping_v1.json"
)
D2_SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "memory_chips_storage_control_source_pack_v1.json"
)
D2_MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "memory_chips_storage_control_node_evidence_matrix_v1.json"
)

D2_NODE_IDS = {
    "dram_nand_memory_die_products",
    "high_bandwidth_memory_advanced_memory",
    "specialty_nor_slc_nand_memory",
    "memory_controller_ssd_control_soc",
    "enterprise_ssd_storage_systems",
    "memory_module_packaging_integration",
    "storage_firmware_interface_ecosystem",
    "capacity_cycle_pricing_inventory",
    "customer_qualification_revenue_validation",
}

D2_CATALOG_LINKS = {
    "dram_nand_memory_die_products": {
        "memory_die_devices",
        "dram_memory_devices",
        "nand_flash_devices",
    },
    "high_bandwidth_memory_advanced_memory": {"advanced_memory_hbm"},
    "specialty_nor_slc_nand_memory": {"specialty_nor_slc_memory"},
    "memory_controller_ssd_control_soc": {
        "storage_controller_soc",
        "nand_flash_controller",
        "enterprise_ssd_controller",
    },
    "enterprise_ssd_storage_systems": {
        "enterprise_ssd_products",
        "enterprise_storage_systems",
        "all_flash_storage_array",
        "distributed_storage_system",
    },
    "memory_module_packaging_integration": {
        "memory_modules_ssd_products",
        "memory_module_integration",
        "embedded_storage_ufs_emmc",
        "client_industrial_ssd",
    },
    "storage_firmware_interface_ecosystem": {
        "storage_firmware_controller_ecosystem",
        "memory_interface_interconnect_chips",
        "memory_buffer_clock_driver_chips",
    },
}

D3_CHAIN_ID = "industrial_machine_tools_cnc"
D3_THEME_ID = "industrial_machine_tools_cnc_value_chain_v1"
D3_THEME_PATH = REPOSITORY_ROOT / f"artifacts/theme_decomposition/{D3_THEME_ID}.json"
D3_MAPPING_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/company_mappings"
    / "industrial_machine_tools_cnc_company_mapping_v1.json"
)
D3_SOURCE_PACK_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "industrial_machine_tools_cnc_source_pack_v1.json"
)
D3_MATRIX_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/source_packs"
    / "industrial_machine_tools_cnc_node_evidence_matrix_v1.json"
)

D3_NODE_IDS = {
    "high_end_cnc_control_systems",
    "machine_tool_servo_drive_feedback_integration",
    "precision_machine_bodies_castings",
    "spindle_ball_screw_linear_guide",
    "metal_cutting_grinding_machine_tools",
    "multi_axis_composite_processing_centers",
    "tooling_fixtures_measurement_integration",
    "installed_base_retrofit_service",
    "orders_delivery_acceptance_revenue_validation",
}

D3_CATALOG_LINKS = {
    "high_end_cnc_control_systems": {
        "cnc_control_motion_integration",
        "high_end_cnc_systems",
    },
    "machine_tool_servo_drive_feedback_integration": {
        "machine_tool_servo_drive_integration",
        "machine_tool_feedback_measurement_integration",
    },
    "precision_machine_bodies_castings": {
        "machine_tool_structure_component_integration",
        "precision_machine_body_casting_integration",
    },
    "spindle_ball_screw_linear_guide": {
        "spindle_drive_toolholder_integration",
        "feed_screw_guide_integration",
    },
    "metal_cutting_grinding_machine_tools": {
        "machine_tool_equipment",
        "metal_cutting_grinding_machine_tools",
    },
    "multi_axis_composite_processing_centers": {
        "multi_axis_composite_machining_centers"
    },
    "tooling_fixtures_measurement_integration": {
        "tooling_fixture_in_process_measurement"
    },
    "installed_base_retrofit_service": {
        "machine_tool_lifecycle_services",
        "retrofit_maintenance_digital_service",
    },
}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_d1_four_artifacts_exist_before_validation():
    for path in (
        D1_THEME_PATH,
        D1_MAPPING_PATH,
        D1_SOURCE_PACK_PATH,
        D1_MATRIX_PATH,
    ):
        assert path.is_file(), path


def test_d1_theme_meets_wave_d_gate_and_exact_node_scope():
    theme = _read_json(D1_THEME_PATH)
    mapping = _read_json(D1_MAPPING_PATH)
    validate_theme_decomposition_artifact(theme, expected_theme_id=D1_THEME_ID)
    validate_theme_company_mapping_artifact(mapping, theme)
    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_d")
    row = next(item for item in report["theme_results"] if item["chain_id"] == D1_CHAIN_ID)

    assert {node["node_id"] for node in theme["nodes"]} == D1_NODE_IDS
    assert len(theme["sources"]) >= 10
    assert len(theme["claims"]) >= 12
    assert len(
        [item for item in mapping["company_mappings"] if item["review_status"] == "reviewed"]
    ) >= 8
    assert row["ready"] is True
    assert row["checks"]["bidirectional_evidence_contract"] is True
    assert row["checks"]["precise_mapping_locators"] is True


def test_d1_catalog_projection_preserves_approved_one_to_many_links():
    catalog = load_industry_catalog()
    link = next(row for row in catalog["theme_links"] if row["theme_id"] == D1_THEME_ID)
    actual: dict[str, set[str]] = {}
    for row in link["node_links"]:
        actual.setdefault(row["theme_node_id"], set()).add(row["catalog_node_id"])

    assert actual == D1_CATALOG_LINKS
    assert set(link["unmapped_theme_node_ids"]) == {
        "licensing_subscription_royalty_model",
        "customer_adoption_revenue_validation",
    }

    chain_nodes = {
        row["node_id"]
        for row in catalog["nodes"]
        if row["chain_id"] == D1_CHAIN_ID
    }
    assert chain_nodes == set().union(*D1_CATALOG_LINKS.values())


def test_d1_company_evidence_uses_exact_sources_and_three_distinct_roles():
    theme = _read_json(D1_THEME_PATH)
    mapping = _read_json(D1_MAPPING_PATH)
    source_pack = _read_json(D1_SOURCE_PACK_PATH)

    theme_source_ids = {row["source_id"] for row in theme["sources"]}
    mapping_source_ids = {row["source_id"] for row in mapping["sources"]}
    source_pack_ids = {row["source_id"] for row in source_pack["sources"]}
    assert theme_source_ids == mapping_source_ids == source_pack_ids
    assert {
        row["company_code"] for row in mapping["company_mappings"]
    } == {
        "301269.SZ",
        "688206.SH",
        "301095.SZ",
        "688521.SH",
        "688691.SH",
        "688262.SH",
        "688259.SH",
        "688047.SH",
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


def test_d1_readable_detail_preserves_revenue_boundaries_and_beneficiary_tiers():
    detail = get_theme_research_theme(D1_THEME_ID)
    assert "EDA 授权" in detail["research_profile"]["investment_summary"]
    risk_claim_text = next(
        row["claim_text"]
        for row in list_theme_research_claims(D1_THEME_ID)["items"]
        if row["claim_id"] == "eda_ip_claim_12"
    )
    assert "IP 许可费与版税要分开" in risk_claim_text

    companies = list_theme_research_companies(D1_THEME_ID)["items"]
    assert {row["company_name"]: row["beneficiary_tier"] for row in companies} == {
        "华大九天": "core_beneficiary",
        "概伦电子": "core_beneficiary",
        "芯原股份": "core_beneficiary",
        "广立微": "core_beneficiary",
        "灿芯股份": "core_beneficiary",
        "创耀科技": "core_beneficiary",
        "国芯科技": "elastic_beneficiary",
        "龙芯中科": "elastic_beneficiary",
    }


def test_d1_chiplet_claim_only_uses_sources_with_precise_declared_pages():
    theme = _read_json(D1_THEME_PATH)
    claim = next(row for row in theme["claims"] if row["claim_id"] == "eda_ip_claim_05")

    assert {claim["source_id"], *claim["supporting_source_ids"]} == {
        "eda_ip_301269_filing",
        "eda_ip_688521_filing",
    }


def test_d2_four_artifacts_exist_before_validation():
    for path in (
        D2_THEME_PATH,
        D2_MAPPING_PATH,
        D2_SOURCE_PACK_PATH,
        D2_MATRIX_PATH,
    ):
        assert path.is_file(), path


def test_d2_theme_meets_wave_d_gate_and_exact_node_scope():
    theme = _read_json(D2_THEME_PATH)
    mapping = _read_json(D2_MAPPING_PATH)
    validate_theme_decomposition_artifact(theme, expected_theme_id=D2_THEME_ID)
    validate_theme_company_mapping_artifact(mapping, theme)
    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_d")
    row = next(item for item in report["theme_results"] if item["chain_id"] == D2_CHAIN_ID)

    assert {node["node_id"] for node in theme["nodes"]} == D2_NODE_IDS
    assert len(theme["sources"]) >= 10
    assert len(theme["claims"]) >= 12
    assert len(
        [item for item in mapping["company_mappings"] if item["review_status"] == "reviewed"]
    ) >= 8
    assert row["ready"] is True
    assert row["checks"]["bidirectional_evidence_contract"] is True
    assert row["checks"]["precise_mapping_locators"] is True


def test_d2_catalog_projection_preserves_approved_one_to_many_links():
    catalog = load_industry_catalog()
    link = next(row for row in catalog["theme_links"] if row["theme_id"] == D2_THEME_ID)
    actual: dict[str, set[str]] = {}
    for row in link["node_links"]:
        actual.setdefault(row["theme_node_id"], set()).add(row["catalog_node_id"])

    assert actual == D2_CATALOG_LINKS
    assert set(link["unmapped_theme_node_ids"]) == {
        "capacity_cycle_pricing_inventory",
        "customer_qualification_revenue_validation",
    }

    chain_nodes = {
        row["node_id"]
        for row in catalog["nodes"]
        if row["chain_id"] == D2_CHAIN_ID
    }
    assert chain_nodes == set().union(*D2_CATALOG_LINKS.values())


def test_d2_company_evidence_is_precise_and_never_maps_hbm_without_direct_proof():
    theme = _read_json(D2_THEME_PATH)
    mapping = _read_json(D2_MAPPING_PATH)
    source_pack = _read_json(D2_SOURCE_PACK_PATH)
    matrix = _read_json(D2_MATRIX_PATH)

    source_ids = {row["source_id"] for row in theme["sources"]}
    assert source_ids == {row["source_id"] for row in mapping["sources"]}
    assert source_ids == {row["source_id"] for row in source_pack["sources"]}
    assert all(
        row["mapped_node_id"] != "high_bandwidth_memory_advanced_memory"
        for row in mapping["company_mappings"]
    )

    hbm_node = next(
        row for row in theme["nodes"]
        if row["node_id"] == "high_bandwidth_memory_advanced_memory"
    )
    hbm_matrix = next(
        row for row in matrix["node_evidence_matrix"]
        if row["node_id"] == "high_bandwidth_memory_advanced_memory"
    )
    assert (hbm_node["node_review_status"], hbm_node["evidence_strength"]) == (
        "draft",
        2,
    )
    assert (
        hbm_matrix["node_review_status"],
        hbm_matrix["evidence_strength_after"],
        hbm_matrix["evidence_gap_status"],
    ) == ("draft", 2, "technical_route_only")
    hbm_claim = next(
        row for row in theme["claims"] if row["claim_id"] == "memory_claim_07"
    )
    assert {hbm_claim["source_id"], *hbm_claim["supporting_source_ids"]} == {
        "memory_603986_filing",
        "memory_300223_filing",
        "memory_688110_filing",
        "memory_688008_filing",
    }
    assert set(hbm_matrix["accepted_source_ids"]) == {
        "memory_603986_filing",
        "memory_300223_filing",
        "memory_688110_filing",
        "memory_688008_filing",
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


def test_d2_readable_detail_keeps_controller_module_and_hbm_boundaries():
    detail = get_theme_research_theme(D2_THEME_ID)
    assert "HBM" in detail["research_profile"]["central_conflict"]
    guardrail = next(
        row["claim_text"]
        for row in list_theme_research_claims(D2_THEME_ID)["items"]
        if row["claim_id"] == "memory_claim_07"
    )
    assert "自产颗粒、直接客户认证或明确收入证据" in guardrail

    companies = list_theme_research_companies(D2_THEME_ID)["items"]
    assert {row["company_name"]: row["beneficiary_tier"] for row in companies} == {
        "兆易创新": "core_beneficiary",
        "北京君正": "core_beneficiary",
        "东芯股份": "core_beneficiary",
        "普冉股份": "core_beneficiary",
        "澜起科技": "core_beneficiary",
        "江波龙": "core_beneficiary",
        "佰维存储": "core_beneficiary",
        "德明利": "elastic_beneficiary",
        "同有科技": "core_beneficiary",
        "国科微": "elastic_beneficiary",
    }


def test_d3_four_artifacts_exist_before_validation():
    for path in (
        D3_THEME_PATH,
        D3_MAPPING_PATH,
        D3_SOURCE_PACK_PATH,
        D3_MATRIX_PATH,
    ):
        assert path.is_file(), path


def test_d3_theme_meets_wave_d_gate_and_exact_node_scope():
    theme = _read_json(D3_THEME_PATH)
    mapping = _read_json(D3_MAPPING_PATH)
    validate_theme_decomposition_artifact(theme, expected_theme_id=D3_THEME_ID)
    validate_theme_company_mapping_artifact(mapping, theme)
    report = VERIFIER.build_theme_batch_report(MANIFEST_PATH, wave="wave_d")
    row = next(item for item in report["theme_results"] if item["chain_id"] == D3_CHAIN_ID)

    assert {node["node_id"] for node in theme["nodes"]} == D3_NODE_IDS
    assert len(theme["sources"]) >= 10
    assert len(theme["claims"]) >= 12
    assert len(
        [item for item in mapping["company_mappings"] if item["review_status"] == "reviewed"]
    ) >= 8
    assert row["ready"] is True
    assert row["checks"]["bidirectional_evidence_contract"] is True
    assert row["checks"]["precise_mapping_locators"] is True


def test_d3_catalog_projection_preserves_component_ownership_and_links():
    catalog = load_industry_catalog()
    link = next(row for row in catalog["theme_links"] if row["theme_id"] == D3_THEME_ID)
    actual: dict[str, set[str]] = {}
    for row in link["node_links"]:
        actual.setdefault(row["theme_node_id"], set()).add(row["catalog_node_id"])

    assert actual == D3_CATALOG_LINKS
    assert set(link["unmapped_theme_node_ids"]) == {
        "orders_delivery_acceptance_revenue_validation"
    }
    chain_nodes = {
        row["node_id"]
        for row in catalog["nodes"]
        if row["chain_id"] == D3_CHAIN_ID
    }
    assert chain_nodes == set().union(*D3_CATALOG_LINKS.values())
    assert all(
        "generic component ownership remains" in row["description"].lower()
        for row in catalog["nodes"]
        if row["node_id"] in {
            "machine_tool_servo_drive_integration",
            "machine_tool_feedback_measurement_integration",
            "spindle_drive_toolholder_integration",
            "feed_screw_guide_integration",
        }
    )


def test_d3_company_evidence_is_precise_and_does_not_claim_generic_components():
    theme = _read_json(D3_THEME_PATH)
    mapping = _read_json(D3_MAPPING_PATH)
    source_pack = _read_json(D3_SOURCE_PACK_PATH)

    source_ids = {row["source_id"] for row in theme["sources"]}
    assert source_ids == {row["source_id"] for row in mapping["sources"]}
    assert source_ids == {row["source_id"] for row in source_pack["sources"]}
    assert {
        row["mapped_node_id"] for row in mapping["company_mappings"]
    } <= {
        "high_end_cnc_control_systems",
        "metal_cutting_grinding_machine_tools",
        "multi_axis_composite_processing_centers",
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


def test_d3_readable_detail_separates_orders_delivery_acceptance_and_revenue():
    detail = get_theme_research_theme(D3_THEME_ID)
    assert "订单、排产、发货" in detail["research_profile"]["central_conflict"]
    assert "高风险核心受益" in detail["research_profile"]["investment_summary"]
    boundary_claim = next(
        row
        for row in list_theme_research_claims(D3_THEME_ID)["items"]
        if row["claim_id"] == "machine_claim_09"
    )
    assert "在手订单、合同负债和发出商品不得当作已确认收入" in boundary_claim[
        "claim_text"
    ]

    mapping = _read_json(D3_MAPPING_PATH)
    genesis_revenue = next(
        row for row in mapping["evidence_items"]
        if row["evidence_id"] == "machine_300083_revenue"
    )
    rifa_stage = next(
        row for row in mapping["evidence_items"]
        if row["evidence_id"] == "machine_002520_stage"
    )
    assert "4205台已发货未验收" in genesis_revenue["evidence_summary"]
    assert "保留意见" in rifa_stage["evidence_summary"]
    assert "第69-70页" in rifa_stage["excerpt_locator"]
    assert "第111-113页" in rifa_stage["excerpt_locator"]

    rifa_company = next(
        row
        for row in list_theme_research_companies(D3_THEME_ID)["items"]
        if row["company_code"] == "002520.SZ"
    )
    assert rifa_company["beneficiary_tier"] == "core_beneficiary"
    assert "审计保留意见" in rifa_company["relationship_summary"]
