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
