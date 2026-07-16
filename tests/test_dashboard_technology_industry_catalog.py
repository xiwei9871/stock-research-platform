import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.industry_chain_theme_research import (
    COMPLETED_CHAIN_THEMES,
    NEXT_FIFTEEN_CHAIN_THEMES,
    SELECTED_CHAIN_THEMES,
)
from stock_research.technology_industry_catalog import load_industry_catalog
from stock_research.theme_decomposition import load_theme_package


CATALOG_PATH = "/api/research/technology-industry-catalog"
CHAIN_PATH = f"{CATALOG_PATH}/chains/ai_data_center_power"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts/verify_industry_chain_theme_batch.py"
SPEC = importlib.util.spec_from_file_location(
    "verify_industry_chain_theme_batch_dashboard_test",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)
load_theme_batch_manifest = VERIFIER.load_theme_batch_manifest
NEXT_FIFTEEN_MANIFEST_PATH = (
    REPOSITORY_ROOT
    / "artifacts/theme_decomposition/batch_manifests"
    / "next_fifteen_industry_chain_themes_v1.json"
)
EXPECTED_GUARDRAILS = {
    "research_only": True,
    "used_for_signal": False,
    "used_for_admission": False,
}


def test_technology_industry_catalog_api_returns_repository_summary_and_guardrails():
    response = TestClient(dashboard_app.create_app()).get(CATALOG_PATH)

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["sector_count"] == 10
    assert payload["summary"]["chain_count"] == 82
    assert len(payload["sectors"]) == 10
    assert len(payload["chains"]) == 82
    deep_rows = [row for row in payload["chains"] if row["deep_research"] is not None]
    deep_by_chain = {row["chain_id"]: row for row in deep_rows}
    assert set(deep_by_chain) == set(SELECTED_CHAIN_THEMES)
    not_started_chain_ids = {
        chain_id
        for chain_id, row in deep_by_chain.items()
        if row["deep_research"]["research_status"] == "not_started"
    }
    implemented_theme_ids = {
        row["theme_id"] for row in load_theme_package()["themes"]
    }
    expected_not_started = {
        chain_id
        for chain_id, theme_id in NEXT_FIFTEEN_CHAIN_THEMES.items()
        if theme_id not in implemented_theme_ids
    }
    assert not_started_chain_ids == expected_not_started
    assert all(
        deep_by_chain[chain_id]["deep_research"]["research_status"] != "not_started"
        for chain_id in COMPLETED_CHAIN_THEMES
    )
    ai_power = deep_by_chain["ai_data_center_power"]
    assert ai_power["deep_research"]["theme_id"] == "ai_power_value_capture_v1"
    ai_logic = deep_by_chain["ai_logic_compute_chips"]
    assert ai_logic["deep_research"]["theme_id"] == (
        "ai_logic_compute_chips_value_chain_v1"
    )
    assert ai_logic["deep_research"]["theme_route"] == (
        "/theme-research/ai_logic_compute_chips_value_chain_v1"
    )
    industrial_software = next(
        row for row in payload["chains"] if row["chain_id"] == "industrial_software"
    )
    assert industrial_software["deep_research"] is None
    assert payload["summary"]["deep_research_chain_count"] == 20
    assert {key: payload[key] for key in EXPECTED_GUARDRAILS} == EXPECTED_GUARDRAILS


def test_technology_industry_catalog_chain_api_trims_id_and_returns_theme_links():
    response = TestClient(dashboard_app.create_app()).get(
        f"{CATALOG_PATH}/chains/%20ai_data_center_power%20"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chain"]["chain_id"] == "ai_data_center_power"
    assert {node["level"] for node in payload["nodes"]} >= {"L3", "L4"}
    assert [link["theme_id"] for link in payload["theme_links"]] == [
        "ai_power_value_capture_v1"
    ]
    assert payload["deep_research"]["theme_id"] == "ai_power_value_capture_v1"
    assert payload["deep_research"]["source_count"] == 13
    assert payload["deep_research"]["reviewed_company_count"] == 8
    assert {key: payload[key] for key in EXPECTED_GUARDRAILS} == EXPECTED_GUARDRAILS


def test_technology_industry_catalog_chain_api_returns_404_for_unknown_chain():
    response = TestClient(dashboard_app.create_app()).get(
        f"{CATALOG_PATH}/chains/missing-chain"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "chain_not_found"


def test_ai_logic_compute_chain_detail_exposes_reviewed_theme():
    response = TestClient(dashboard_app.create_app()).get(
        f"{CATALOG_PATH}/chains/ai_logic_compute_chips"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chain"]["chain_id"] == "ai_logic_compute_chips"
    assert payload["nodes"] == []
    link = payload["theme_links"][0]
    assert link["theme_id"] == "ai_logic_compute_chips_value_chain_v1"
    assert link["chain_id"] == "ai_logic_compute_chips"
    assert link["node_links"] == []
    assert len(link["unmapped_theme_node_ids"]) >= 9
    assert payload["deep_research"]["theme_id"] == (
        "ai_logic_compute_chips_value_chain_v1"
    )
    assert payload["deep_research"]["theme_route"] == (
        "/theme-research/ai_logic_compute_chips_value_chain_v1"
    )
    assert payload["deep_research"]["research_status"] == "reviewed"
    assert payload["deep_research"]["source_count"] >= 10
    assert payload["deep_research"]["reviewed_company_count"] >= 8


def test_optical_interconnect_chain_detail_exposes_reviewed_theme():
    response = TestClient(dashboard_app.create_app()).get(
        f"{CATALOG_PATH}/chains/optical_communications_data_center_interconnect"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chain"]["chain_id"] == (
        "optical_communications_data_center_interconnect"
    )
    assert payload["nodes"] == []
    link = payload["theme_links"][0]
    assert link["theme_id"] == (
        "optical_communications_data_center_interconnect_value_chain_v1"
    )
    assert link["node_links"] == []
    assert len(link["unmapped_theme_node_ids"]) >= 9
    assert payload["deep_research"]["research_status"] == "reviewed"
    assert payload["deep_research"]["source_count"] >= 10
    assert payload["deep_research"]["reviewed_company_count"] >= 8


def test_semiconductor_materials_chain_detail_exposes_reviewed_theme():
    response = TestClient(dashboard_app.create_app()).get(
        f"{CATALOG_PATH}/chains/semiconductor_materials_electronic_chemicals"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chain"]["chain_id"] == (
        "semiconductor_materials_electronic_chemicals"
    )
    assert payload["nodes"] == []
    link = payload["theme_links"][0]
    assert link["theme_id"] == (
        "semiconductor_materials_electronic_chemicals_value_chain_v1"
    )
    assert link["node_links"] == []
    assert len(link["unmapped_theme_node_ids"]) >= 9
    assert payload["deep_research"]["research_status"] == "reviewed"
    assert payload["deep_research"]["source_count"] >= 10
    assert payload["deep_research"]["reviewed_company_count"] == 10


def test_cloud_data_center_chain_detail_exposes_one_to_many_reviewed_theme():
    response = TestClient(dashboard_app.create_app()).get(
        f"{CATALOG_PATH}/chains/cloud_data_center_infrastructure"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chain"]["chain_id"] == "cloud_data_center_infrastructure"
    link = payload["theme_links"][0]
    assert link["theme_id"] == "cloud_data_center_infrastructure_value_chain_v1"
    assert len(link["node_links"]) == 20
    assert len(link["unmapped_theme_node_ids"]) == 4
    assert payload["deep_research"]["theme_id"] == (
        "cloud_data_center_infrastructure_value_chain_v1"
    )
    assert payload["deep_research"]["theme_route"] == (
        "/theme-research/cloud_data_center_infrastructure_value_chain_v1"
    )
    assert payload["deep_research"]["research_status"] == "reviewed"
    assert payload["deep_research"]["source_count"] == 11
    assert payload["deep_research"]["reviewed_company_count"] == 11


def test_next_fifteen_catalog_theme_links_match_canonical_batch_manifest():
    catalog = load_industry_catalog()
    manifest = load_theme_batch_manifest(NEXT_FIFTEEN_MANIFEST_PATH)
    links_by_chain = {}
    for link in catalog["theme_links"]:
        links_by_chain.setdefault(link["chain_id"], []).append(link)

    assert {
        chain_id: metadata["theme_id"]
        for chain_id, metadata in manifest["themes"].items()
    } == NEXT_FIFTEEN_CHAIN_THEMES
    for chain_id, metadata in manifest["themes"].items():
        node_links = []
        if chain_id == "power_semiconductors":
            node_links = [
                {
                    "theme_node_id": "device_design_process_platforms",
                    "catalog_node_id": "power_semiconductor_devices",
                },
                {
                    "theme_node_id": "silicon_mosfet",
                    "catalog_node_id": "power_mosfet_device",
                },
                {
                    "theme_node_id": "sic_power_devices",
                    "catalog_node_id": "silicon_carbide_power_device",
                },
                {
                    "theme_node_id": "gan_power_devices",
                    "catalog_node_id": "gallium_nitride_power_device",
                },
            ]
        if chain_id == "new_power_system_smart_grid":
            node_links = [
                {
                    "theme_node_id": "uhv_hvdc_flexible_dc",
                    "catalog_node_id": "grid_connection_transmission_protection",
                },
                {
                    "theme_node_id": "primary_power_transformers",
                    "catalog_node_id": "power_transformer",
                },
            ]
        unmapped_theme_node_ids = links_by_chain[chain_id][0][
            "unmapped_theme_node_ids"
        ]
        expected_link = {
            "theme_id": metadata["theme_id"],
            "chain_id": chain_id,
            "node_links": node_links,
            "unmapped_theme_node_ids": unmapped_theme_node_ids,
        }
        if chain_id == "new_power_system_smart_grid":
            expected_link["notes"] = (
                "uhv_hvdc_flexible_dc -> grid_connection_transmission_protection "
                "仅用于阶段级L3覆盖，不是柔直或换流阀产品等价映射；具体产品与收入"
                "口径以主题 claim 和公司 mapping 边界为准。"
            )
            if chain_id == "core_mechanical_components":
                expected_link["notes"] = (
                    "core_mechanical_components catalog仍为L2 skeleton，尚无可承接这些"
                    "主题节点的自有L3/L4 canonical node，因此本轮不建立部分等价或一对多"
                    "链接；不映射整机、机器人关节、机床系统或人形机器人场景节点，待该"
                    "canonical chain扩展精确基础件节点后再逐项回填。"
                )
            if chain_id == "industrial_inspection_metrology_machine_vision":
                expected_link["notes"] = (
                    "industrial_inspection_metrology_machine_vision catalog仍为L2 "
                    "skeleton，尚无可承接相机、光路、采集、算法、专用检测、计量、集成"
                    "或服务节点的自有L3/L4 canonical node；目录仅做语义精确映射，宽节点"
                    "不得映到窄节点，因此本轮全部保持unmapped，待canonical chain扩展后"
                    "逐项回填。"
                )
            assert links_by_chain[chain_id] == [expected_link]


@pytest.mark.parametrize("method", ["post", "patch", "put", "delete"])
@pytest.mark.parametrize("path", [CATALOG_PATH, CHAIN_PATH])
def test_technology_industry_catalog_api_is_read_only(method: str, path: str):
    response = TestClient(dashboard_app.create_app()).request(method, path, json={})

    assert response.status_code == 405
