from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard.theme_research import (
    ThemeResearchNotFoundError,
    get_theme_research_theme,
    list_theme_research_claims,
    list_theme_research_companies,
    list_theme_research_nodes,
    list_theme_research_sources,
    list_theme_research_themes,
)


AI_POWER_THEME_ID = "ai_power_value_capture_v1"
ROBOTICS_THEME_ID = "humanoid_robotics_head_to_toe_v1"


def test_theme_index_aggregates_validated_phase_outputs():
    payload = list_theme_research_themes()

    assert payload["total"] == 2
    assert [row["theme_id"] for row in payload["items"]] == [
        AI_POWER_THEME_ID,
        ROBOTICS_THEME_ID,
    ]
    assert [
        (row["theme_name"], row["theme_id"]) for row in payload["items"]
    ] == sorted((row["theme_name"], row["theme_id"]) for row in payload["items"])
    ai_power = payload["items"][0]
    robotics = payload["items"][1]
    assert ai_power["node_count"] == 13
    assert ai_power["source_count"] == 10
    assert ai_power["claim_count"] == 10
    assert ai_power["company_count"] == 8
    assert ai_power["evidence_gap_count"] == 3
    assert ai_power["deep_research_node_count"] == 2
    assert ai_power["review_queue_count"] == 13
    assert robotics["node_count"] == 21
    assert robotics["company_count"] == 0
    assert ai_power["research_kind"] == "industry_chain_deep_research"
    assert ai_power["catalog_context"] == {
        "chain_id": "ai_data_center_power",
        "chain_name": "AI Data Center Power",
        "sector_id": "energy_technology_new_power_system",
        "catalog_route": "/theme-research/catalog/ai_data_center_power",
    }
    assert robotics["catalog_context"]["chain_id"] == (
        "humanoid_robots_embodied_intelligence"
    )
    assert all(row["research_only"] is True for row in payload["items"])
    assert all(row["used_for_signal"] is False for row in payload["items"])
    assert all(row["used_for_admission"] is False for row in payload["items"])


def test_theme_detail_contains_priority_and_evidence_distributions():
    detail = get_theme_research_theme(AI_POWER_THEME_ID)

    assert detail["theme"]["theme_name"] == "AI供电产业链：谁在拿走价值量"
    assert detail["theme"]["status"] == "reviewed"
    assert detail["node_summary"] == {
        "total": 13,
        "by_priority_class": {
            "deep_research_priority": 2,
            "evidence_collection_priority": 3,
            "monitor": 8,
        },
        "by_review_status": {
            "draft": 1,
            "needs_evidence": 8,
            "reviewed": 4,
        },
    }
    assert detail["company_summary"]["total"] == 8
    assert detail["company_summary"]["by_integration_status"] == {
        "coverage_gap": 2,
        "linked_existing_universe": 6,
    }
    assert detail["evidence_gap_summary"]["total"] == 3
    assert detail["source_reliability_distribution"]["S1"] == 7
    assert detail["claim_evidence_status_distribution"]["verified"] >= 1
    assert detail["review_queue_action_distribution"]
    assert detail["catalog_context"]["chain_id"] == "ai_data_center_power"
    assert detail["research_profile"]["catalog_chain_id"] == "ai_data_center_power"
    assert detail["beneficiary_summary"]["total"] == 8
    assert sum(detail["beneficiary_summary"]["by_tier"].values()) == 8
    assert detail["beneficiary_summary"]["reviewed_beneficiary_count"] == 8
    assert detail["top_node_priorities"][0]["theme_id"] == AI_POWER_THEME_ID
    assert all(row["used_for_signal"] is False for row in detail["top_node_priorities"])


def test_node_collection_is_scoped_joined_and_stably_sorted():
    payload = list_theme_research_nodes(AI_POWER_THEME_ID)

    assert payload["total"] == 13
    assert all(row["theme_id"] == AI_POWER_THEME_ID for row in payload["items"])
    assert all("description" in row for row in payload["items"])
    assert all("priority_score" in row for row in payload["items"])
    sort_keys = [
        (-row["priority_score"], row["node_id"])
        for row in payload["items"]
    ]
    assert sort_keys == sorted(sort_keys)
    liquid_cooling = next(
        row for row in payload["items"] if row["node_id"] == "liquid_cooling"
    )
    assert liquid_cooling["priority_class"] == "deep_research_priority"
    assert liquid_cooling["recommended_action"] == "deep_node_research"


def test_source_and_claim_collections_preserve_quality_gates():
    sources = list_theme_research_sources(AI_POWER_THEME_ID)
    claims = list_theme_research_claims(AI_POWER_THEME_ID)

    assert sources["total"] == 10
    assert claims["total"] == 10
    assert all(row["theme_id"] == AI_POWER_THEME_ID for row in sources["items"])
    assert all(row["theme_id"] == AI_POWER_THEME_ID for row in claims["items"])
    video = next(
        row for row in sources["items"] if row["source_id"] == "ai_power_video_claim_lead"
    )
    assert video["reliability_level"] == "S4"
    assert video["review_status"] == "lead_only"
    assert video["claim_count"] >= 1
    assert all("platform_use_status" in row for row in claims["items"])
    assert all(row["used_for_signal"] is False for row in claims["items"])
    architecture_claim = next(
        row for row in claims["items"] if row["claim_id"] == "ai_power_claim_800v_architecture"
    )
    assert architecture_claim["supporting_sources"] == [
        {
            "source_id": "ai_power_nvidia_800v_ecosystem_blog_2025",
            "title": "Building the 800 VDC Ecosystem for Efficient, Scalable AI Factories",
            "reliability_level": "S1",
            "review_status": "accepted",
        }
    ]


def test_company_collection_joins_mapping_priority_and_crosswalk_context():
    payload = list_theme_research_companies(AI_POWER_THEME_ID)

    assert payload["total"] == 8
    assert [row["company_code"] for row in payload["items"]] == [
        "002837.SZ",
        "301018.SZ",
        "000811.SZ",
        "002364.SZ",
        "300499.SZ",
        "300870.SZ",
        "002335.SZ",
        "300442.SZ",
    ]
    envicool = payload["items"][0]
    assert envicool["mapped_node"]["node_id"] == "liquid_cooling"
    assert envicool["company_research_priority_score"] == 78.8
    assert envicool["integration_status"] == "linked_existing_universe"
    assert envicool["existing_review_context"]["status"] == "pending_review"
    assert envicool["tech_bottleneck_stock_path"] == (
        "/tech-bottleneck/stock/002837.SZ?source=theme_research"
    )
    assert envicool["beneficiary_tier"] == "elastic_beneficiary"
    assert envicool["mapping_evidence"]
    assert envicool["mapping_evidence"][0]["source"]["review_status"] == "accepted"
    assert all(row["research_only"] is True for row in payload["items"])
    assert all(row["used_for_signal"] is False for row in payload["items"])
    assert all(row["used_for_admission"] is False for row in payload["items"])


def test_unknown_theme_is_rejected_by_every_detail_read_model():
    readers = (
        get_theme_research_theme,
        list_theme_research_nodes,
        list_theme_research_sources,
        list_theme_research_claims,
        list_theme_research_companies,
    )

    for reader in readers:
        with pytest.raises(ThemeResearchNotFoundError):
            reader("missing-theme")


def test_theme_ids_must_match_exactly_instead_of_returning_empty_aggregates():
    with pytest.raises(ThemeResearchNotFoundError):
        get_theme_research_theme(f" {AI_POWER_THEME_ID} ")


def test_theme_research_api_exposes_six_get_only_routes():
    client = TestClient(dashboard_app.create_app())
    base = "/api/research/theme-decomposition/themes"

    responses = {
        "themes": client.get(base),
        "detail": client.get(f"{base}/{AI_POWER_THEME_ID}"),
        "nodes": client.get(f"{base}/{AI_POWER_THEME_ID}/nodes"),
        "sources": client.get(f"{base}/{AI_POWER_THEME_ID}/sources"),
        "claims": client.get(f"{base}/{AI_POWER_THEME_ID}/claims"),
        "companies": client.get(f"{base}/{AI_POWER_THEME_ID}/companies"),
    }

    assert all(response.status_code == 200 for response in responses.values())
    assert responses["themes"].json()["total"] == 2
    assert responses["detail"].json()["theme"]["theme_id"] == AI_POWER_THEME_ID
    for name in ("nodes", "sources", "claims", "companies"):
        assert all(
            row["theme_id"] == AI_POWER_THEME_ID
            for row in responses[name].json()["items"]
        )
    assert client.post(base, json={}).status_code == 405
    assert client.patch(f"{base}/{AI_POWER_THEME_ID}", json={}).status_code == 405
    assert client.delete(f"{base}/{AI_POWER_THEME_ID}").status_code == 405


def test_theme_research_api_returns_404_for_unknown_theme():
    client = TestClient(dashboard_app.create_app())
    base = "/api/research/theme-decomposition/themes/missing-theme"

    for suffix in ("", "/nodes", "/sources", "/claims", "/companies"):
        response = client.get(f"{base}{suffix}")
        assert response.status_code == 404
        assert response.json()["detail"] == "theme_not_found"

    whitespace = client.get(
        "/api/research/theme-decomposition/themes/%20ai_power_value_capture_v1%20"
    )
    assert whitespace.status_code == 404
    assert whitespace.json()["detail"] == "theme_not_found"
