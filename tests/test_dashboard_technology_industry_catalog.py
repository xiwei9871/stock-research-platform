import pytest
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app


CATALOG_PATH = "/api/research/technology-industry-catalog"
CHAIN_PATH = f"{CATALOG_PATH}/chains/ai_data_center_power"
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
    assert len(deep_rows) == 5
    ai_power = next(row for row in deep_rows if row["chain_id"] == "ai_data_center_power")
    assert ai_power["deep_research"]["theme_id"] == "ai_power_value_capture_v1"
    assert ai_power["deep_research"]["research_status"] == "researching"
    industrial_software = next(
        row for row in payload["chains"] if row["chain_id"] == "industrial_software"
    )
    assert industrial_software["deep_research"] is None
    assert payload["summary"]["deep_research_chain_count"] == 5
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
    assert payload["deep_research"]["source_count"] == 10
    assert payload["deep_research"]["reviewed_company_count"] == 4
    assert {key: payload[key] for key in EXPECTED_GUARDRAILS} == EXPECTED_GUARDRAILS


def test_technology_industry_catalog_chain_api_returns_404_for_unknown_chain():
    response = TestClient(dashboard_app.create_app()).get(
        f"{CATALOG_PATH}/chains/missing-chain"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "chain_not_found"


@pytest.mark.parametrize("method", ["post", "patch", "put", "delete"])
@pytest.mark.parametrize("path", [CATALOG_PATH, CHAIN_PATH])
def test_technology_industry_catalog_api_is_read_only(method: str, path: str):
    response = TestClient(dashboard_app.create_app()).request(method, path, json={})

    assert response.status_code == 405
