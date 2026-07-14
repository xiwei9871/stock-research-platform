from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scripts.verify_industry_chain_theme_batch import load_theme_batch_manifest
from stock_research.dashboard import app as dashboard_app
from stock_research.industry_chain_theme_research import NEXT_FIFTEEN_CHAIN_THEMES
from stock_research.technology_industry_catalog import load_industry_catalog


CATALOG_PATH = "/api/research/technology-industry-catalog"
CHAIN_PATH = f"{CATALOG_PATH}/chains/ai_data_center_power"
NEXT_FIFTEEN_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1]
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
    assert len(deep_rows) == 20
    research_statuses = [row["deep_research"]["research_status"] for row in deep_rows]
    assert research_statuses.count("reviewed") == 5
    assert research_statuses.count("not_started") == 15
    ai_power = next(row for row in deep_rows if row["chain_id"] == "ai_data_center_power")
    assert ai_power["deep_research"]["theme_id"] == "ai_power_value_capture_v1"
    assert ai_power["deep_research"]["research_status"] == "reviewed"
    ai_logic = next(row for row in deep_rows if row["chain_id"] == "ai_logic_compute_chips")
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


def test_next_fifteen_chain_detail_exposes_registered_unfinished_theme():
    response = TestClient(dashboard_app.create_app()).get(
        f"{CATALOG_PATH}/chains/ai_logic_compute_chips"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chain"]["chain_id"] == "ai_logic_compute_chips"
    assert payload["nodes"] == []
    assert payload["theme_links"] == [
        {
            "theme_id": "ai_logic_compute_chips_value_chain_v1",
            "chain_id": "ai_logic_compute_chips",
            "node_links": [],
            "unmapped_theme_node_ids": [],
        }
    ]
    assert payload["deep_research"]["theme_id"] == (
        "ai_logic_compute_chips_value_chain_v1"
    )
    assert payload["deep_research"]["theme_route"] == (
        "/theme-research/ai_logic_compute_chips_value_chain_v1"
    )
    assert payload["deep_research"]["research_status"] == "not_started"


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
        assert links_by_chain[chain_id] == [
            {
                "theme_id": metadata["theme_id"],
                "chain_id": chain_id,
                "node_links": [],
                "unmapped_theme_node_ids": [],
            }
        ]


@pytest.mark.parametrize("method", ["post", "patch", "put", "delete"])
@pytest.mark.parametrize("path", [CATALOG_PATH, CHAIN_PATH])
def test_technology_industry_catalog_api_is_read_only(method: str, path: str):
    response = TestClient(dashboard_app.create_app()).request(method, path, json={})

    assert response.status_code == 405
