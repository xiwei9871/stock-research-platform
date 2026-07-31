from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta, tzinfo
import json

from fastapi.testclient import TestClient
import pytest

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import theme_research
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


class _BrokenTimezone(tzinfo):
    def utcoffset(self, dt):
        raise RuntimeError("invalid timezone")


class _StatefulTimezone(tzinfo):
    def __init__(self) -> None:
        self.calls = 0

    def utcoffset(self, dt):
        self.calls += 1
        return timedelta(hours=8) if self.calls == 1 else None


def _context() -> dict:
    return deepcopy(theme_research._load_artifact_context())


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
    assert ai_power["claim_count"] == 8
    assert ai_power["company_count"] == 4
    assert ai_power["evidence_gap_count"] == 3
    assert ai_power["deep_research_node_count"] == 2
    assert ai_power["review_queue_count"] == 9
    assert robotics["node_count"] == 21
    assert robotics["company_count"] == 0
    assert all(row["research_only"] is True for row in payload["items"])
    assert all(row["used_for_signal"] is False for row in payload["items"])
    assert all(row["used_for_admission"] is False for row in payload["items"])
    assert all(
        row["analysis_report"] == {"status": "researching"}
        for row in payload["items"]
    )


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
    assert detail["company_summary"]["total"] == 4
    assert detail["company_summary"]["by_integration_status"] == {
        "coverage_gap": 2,
        "linked_existing_universe": 2,
    }
    assert detail["evidence_gap_summary"]["total"] == 3
    assert detail["source_reliability_distribution"]["S1"] == 7
    assert detail["claim_evidence_status_distribution"]["verified"] >= 1
    assert detail["review_queue_action_distribution"]
    assert detail["top_node_priorities"][0]["theme_id"] == AI_POWER_THEME_ID
    assert all(row["used_for_signal"] is False for row in detail["top_node_priorities"])
    assert detail["theme"]["analysis_report"] == {"status": "researching"}


def test_theme_list_and_detail_share_safe_published_report_summary() -> None:
    context = _context()
    context["analysis_reports_by_theme"] = {
        AI_POWER_THEME_ID: {
            "report_version_id": "report-v2",
            "version": "2026-08-01-v2",
            "published_at": "2026-08-01T09:30:00+08:00",
            "has_pdf": True,
            "markdown_relative_path": "private/report.md",
            "manifest_sha256": "secret-checksum",
            "generator_name": "private-generator",
            "rejection_reason": "private-reason",
            "metadata": {"secret": True},
        }
    }

    index = theme_research._list_theme_research_themes(context)
    detail = theme_research._get_theme_research_theme(context, AI_POWER_THEME_ID)
    expected = {
        "status": "published",
        "report_version_id": "report-v2",
        "version": "2026-08-01-v2",
        "published_at": "2026-08-01T09:30:00+08:00",
        "has_pdf": True,
    }

    index_row = next(
        row for row in index["items"] if row["theme_id"] == AI_POWER_THEME_ID
    )
    assert index_row["analysis_report"] == expected
    assert detail["theme"]["analysis_report"] == expected
    serialized = json.dumps(
        {
            "index": index_row["analysis_report"],
            "detail": detail["theme"]["analysis_report"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    assert "pending_review" not in serialized
    assert "rejected" not in serialized
    assert "private" not in serialized


@pytest.mark.parametrize(
    "published_at",
    [
        None,
        "",
        "   ",
        "not-a-date",
        "2026-13-01T09:30:00+08:00",
        "2026-08-01Q09:30:00+08:00",
        "2026-08-01T09:30:00",
        datetime(2026, 8, 1, 9, 30),
        datetime(2026, 8, 1, 9, 30, tzinfo=_BrokenTimezone()),
        datetime(2026, 8, 1, 9, 30, tzinfo=_StatefulTimezone()),
    ],
)
def test_invalid_or_naive_published_timestamp_fails_closed_for_list_and_detail(
    published_at,
) -> None:
    context = _context()
    context["analysis_reports_by_theme"] = {
        AI_POWER_THEME_ID: {
            "report_version_id": "dirty-report",
            "version": "v1",
            "published_at": published_at,
            "has_pdf": False,
            "metadata": {"secret": "must-not-leak"},
        }
    }

    index = theme_research._list_theme_research_themes(context)
    detail = theme_research._get_theme_research_theme(context, AI_POWER_THEME_ID)
    index_row = next(
        row for row in index["items"] if row["theme_id"] == AI_POWER_THEME_ID
    )

    assert index_row["analysis_report"] == {"status": "researching"}
    assert detail["theme"]["analysis_report"] == {"status": "researching"}


@pytest.mark.parametrize(
    ("published_at", "expected"),
    [
        ("2026-08-01T01:30:00Z", "2026-08-01T01:30:00+00:00"),
        (
            datetime(2026, 8, 1, 1, 30, tzinfo=UTC),
            "2026-08-01T01:30:00+00:00",
        ),
    ],
)
def test_timezone_aware_published_timestamp_is_normalized_for_list_and_detail(
    published_at,
    expected,
) -> None:
    context = _context()
    context["analysis_reports_by_theme"] = {
        AI_POWER_THEME_ID: {
            "report_version_id": "published-report",
            "version": "v1",
            "published_at": published_at,
            "has_pdf": True,
        }
    }

    index = theme_research._list_theme_research_themes(context)
    detail = theme_research._get_theme_research_theme(context, AI_POWER_THEME_ID)
    index_row = next(
        row for row in index["items"] if row["theme_id"] == AI_POWER_THEME_ID
    )

    assert index_row["analysis_report"]["published_at"] == expected
    assert detail["theme"]["analysis_report"]["published_at"] == expected


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
    assert claims["total"] == 8
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

    assert payload["total"] == 4
    assert [row["company_code"] for row in payload["items"]] == [
        "002837.SZ",
        "002364.SZ",
        "300870.SZ",
        "002335.SZ",
    ]
    envicool = payload["items"][0]
    assert envicool["mapped_node"]["node_id"] == "liquid_cooling"
    assert envicool["company_research_priority_score"] == 78.8
    assert envicool["integration_status"] == "linked_existing_universe"
    assert envicool["existing_review_context"]["status"] == "pending_review"
    assert envicool["tech_bottleneck_stock_path"] == (
        "/tech-bottleneck/stock/002837.SZ?source=theme_research"
    )
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
