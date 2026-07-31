from __future__ import annotations

import copy
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from stock_research.dashboard import theme_research
from stock_research.dashboard import theme_research_db
from stock_research.dashboard import app as dashboard_app
from stock_research.theme_research_db_models import ThemeResearchDomainError
from stock_research.theme_research_import import normalize_artifact_package


def test_db_context_matches_artifact_context_contract(monkeypatch) -> None:
    package = normalize_artifact_package()
    monkeypatch.setattr(theme_research_db, "load_database_package", lambda service: package)
    monkeypatch.setattr(
        theme_research_db,
        "_load_published_report_summaries",
        lambda service: {},
    )

    artifact = theme_research.list_theme_research_themes(read_source="artifact")
    database = theme_research.list_theme_research_themes(read_source="db")

    assert database == artifact


def test_theme_package_preserves_research_profiles() -> None:
    package = normalize_artifact_package()
    theme_id = "ai_power_value_capture_v1"
    themes = [copy.deepcopy(row) for row in package.themes]
    profile = {
        "research_kind": "industry_chain_deep_research",
        "industry_stage": "commercial_scaling",
    }
    for row in themes:
        if row["theme_id"] == theme_id:
            row["artifact_metadata"]["research_profile"] = profile
    enriched = package.__class__.build(
        artifact_version=package.artifact_version,
        themes=themes,
        nodes=package.nodes,
        sources=package.sources,
        theme_sources=package.theme_sources,
        claims=package.claims,
        claim_sources=package.claim_sources,
        claim_nodes=package.claim_nodes,
        assessments=package.assessments,
        assessment_evidence=package.assessment_evidence,
        company_mappings=package.company_mappings,
        mapping_evidence_items=package.mapping_evidence_items,
        company_mapping_evidence=package.company_mapping_evidence,
    )

    database_package = theme_research_db._theme_package(enriched)

    assert database_package["research_profiles"] == [
        {**profile, "theme_id": theme_id}
    ]


def test_db_context_survives_missing_optional_priority_support(monkeypatch) -> None:
    package = normalize_artifact_package()
    expected_theme_package = theme_research_db._theme_package(package)
    expected_mapping_package = theme_research_db._mapping_package(package, expected_theme_package)
    monkeypatch.setattr(theme_research_db, "load_database_package", lambda service: package)
    monkeypatch.setattr(
        theme_research_db,
        "_load_published_report_summaries",
        lambda service: {},
    )
    monkeypatch.setattr(
        theme_research_db.priority,
        "load_theme_research_priority_package",
        lambda: (_ for _ in ()).throw(AssertionError("full artifact context must not be loaded")),
    )
    monkeypatch.setattr(
        theme_research_db,
        "_load_workflow_priority_support",
        lambda: (_ for _ in ()).throw(FileNotFoundError("policy unavailable")),
    )

    context = theme_research_db.load_db_context()

    assert context["theme_package"] == expected_theme_package
    assert context["mapping_package"] == expected_mapping_package
    assert context["priority_status"] == "unavailable"
    assert context["policy"] is None
    assert context["node_priorities"] == []
    assert context["company_priorities"] == []
    assert context["evidence_gap_priorities"] == []
    assert context["review_queue"] == []


def test_scoped_priority_support_failure_does_not_block_core_context(monkeypatch) -> None:
    monkeypatch.setattr(
        theme_research_db,
        "_load_workflow_priority_support",
        lambda: (_ for _ in ()).throw(FileNotFoundError("policy unavailable")),
    )

    result = theme_research_db._build_scoped_priority_context([], [])

    assert result == {
        "policy": None,
        "node_priorities": [],
        "company_priorities": [],
        "evidence_gap_priorities": [],
        "review_queue": [],
        "priority_status": "unavailable",
    }


def test_compare_mode_surfaces_semantic_mismatch(monkeypatch) -> None:
    artifact_context = theme_research._load_artifact_context()
    database_context = copy.deepcopy(artifact_context)
    database_context["theme_package"]["themes"][0]["theme_name"] = "changed"
    monkeypatch.setattr(theme_research_db, "load_db_context", lambda service=None: database_context)

    payload = theme_research.list_theme_research_themes(read_source="compare")

    assert payload["comparison"]["status"] == "mismatch"
    assert payload["comparison"]["differences"]


def test_compare_mode_ignores_analysis_report_runtime_overlay(monkeypatch) -> None:
    database_context = copy.deepcopy(theme_research._load_artifact_context())
    database_context["analysis_reports_by_theme"] = {
        "ai_power_value_capture_v1": {
            "report_version_id": "published-report",
            "version": "v1",
            "published_at": "2026-08-01T01:00:00+00:00",
            "has_pdf": True,
        }
    }
    monkeypatch.setattr(
        theme_research_db,
        "load_db_context",
        lambda service=None: database_context,
    )

    payload = theme_research.list_theme_research_themes(read_source="compare")

    assert payload["comparison"]["status"] == "match"
    assert payload["comparison"]["differences"] == []
    assert (
        payload["comparison"]["artifact_sha256"]
        == payload["comparison"]["database_sha256"]
    )


def test_compare_mode_keeps_nested_stable_analysis_report_fields() -> None:
    left = {
        "total": 1,
        "items": [
            {
                "theme_id": "theme-a",
                "theme_name": "Theme A",
                "node_count": 0,
                "analysis_report": {"status": "researching"},
                "artifact_metadata": {"analysis_report": {"schema_version": 1}},
            }
        ],
    }
    right = copy.deepcopy(left)
    right["items"][0]["analysis_report"] = {
        "status": "published",
        "report_version_id": "report-a",
        "version": "v1",
        "published_at": "2026-08-01T00:00:00+00:00",
        "has_pdf": False,
    }
    right["items"][0]["artifact_metadata"]["analysis_report"]["schema_version"] = 2

    comparison = theme_research._compare_payloads(left, right)

    assert comparison["status"] == "mismatch"
    assert comparison["differences"] == [
        "$.items[0].artifact_metadata.analysis_report.schema_version"
    ]


def test_db_context_loads_published_report_summaries_once_and_safely(monkeypatch) -> None:
    package = normalize_artifact_package()
    queries: list[tuple[str, object]] = []
    connection = object()

    @contextmanager
    def fake_connect(service):
        assert service == "runtime"
        yield connection

    def fake_fetch_all(conn, sql, params=None):
        assert conn is connection
        queries.append((sql, params))
        return [
            {
                "theme_id": "ai_power_value_capture_v1",
                "report_version_id": "published-report",
                "version": "v2",
                "published_at": datetime(2026, 8, 1, 1, 30, tzinfo=UTC),
                "has_pdf": True,
            }
        ]

    monkeypatch.setattr(theme_research_db, "load_database_package", lambda service: package)
    monkeypatch.setattr(theme_research_db, "connect", fake_connect)
    monkeypatch.setattr(theme_research_db, "fetch_all", fake_fetch_all)

    context = theme_research_db.load_db_context(service="runtime")

    assert len(queries) == 1
    normalized_sql = " ".join(queries[0][0].split()).lower()
    assert "from research.theme_research_report_version" in normalized_sql
    assert "status = 'published'" in normalized_sql
    assert "pending_review" not in normalized_sql
    assert "rejected" not in normalized_sql
    assert "nullif(btrim(pdf_relative_path), '') is not null" in normalized_sql
    assert context["analysis_reports_by_theme"] == {
        "ai_power_value_capture_v1": {
            "report_version_id": "published-report",
            "version": "v2",
            "published_at": "2026-08-01T01:30:00+00:00",
            "has_pdf": True,
        }
    }


def test_published_report_summary_query_failure_is_not_hidden(monkeypatch) -> None:
    package = normalize_artifact_package()

    @contextmanager
    def fake_connect(service):
        yield object()

    monkeypatch.setattr(theme_research_db, "load_database_package", lambda service: package)
    monkeypatch.setattr(theme_research_db, "connect", fake_connect)
    monkeypatch.setattr(
        theme_research_db,
        "fetch_all",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("db unavailable")),
    )

    with pytest.raises(RuntimeError, match="db unavailable"):
        theme_research_db.load_db_context(service="runtime")


def test_invalid_read_source_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("THEME_RESEARCH_READ_SOURCE", "invalid")

    with pytest.raises(ThemeResearchDomainError) as exc_info:
        theme_research.configured_theme_research_read_source()

    assert exc_info.value.code == "THEME_RESEARCH_READ_SOURCE_INVALID"


def test_review_api_requires_authentication(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_app, "load_current_user_from_session", lambda token: None)
    client = TestClient(dashboard_app.create_app())

    response = client.post(
        "/api/research/theme-decomposition/sources/source-1/review",
        json={
            "to_status": "accepted",
            "expected_row_version": 1,
            "comment": "Reviewed full text.",
            "idempotency_key": "review-1",
        },
    )

    assert response.status_code == 401


def test_review_api_requires_csrf(monkeypatch) -> None:
    user = SimpleNamespace(user_id="user-1", role="user")
    monkeypatch.setattr(dashboard_app, "load_current_user_from_session", lambda token: user)
    client = TestClient(dashboard_app.create_app())

    response = client.post(
        "/api/research/theme-decomposition/sources/source-1/review",
        cookies={"stock_research_session": "session-1"},
        json={
            "to_status": "accepted",
            "expected_row_version": 1,
            "comment": "Reviewed full text.",
            "idempotency_key": "review-1",
        },
    )

    assert response.status_code == 403


def test_review_api_allows_user_and_maps_version_conflict(monkeypatch) -> None:
    user = SimpleNamespace(user_id="user-1", role="user")
    monkeypatch.setattr(dashboard_app, "load_current_user_from_session", lambda token: user)
    monkeypatch.setattr(dashboard_app, "validate_csrf", lambda **kwargs: None)
    captured = {}

    def review(**kwargs):
        captured.update(kwargs)
        return {"status": "reviewed", "row_version": 2}

    monkeypatch.setattr(dashboard_app, "review_theme_research_source", review)
    client = TestClient(dashboard_app.create_app())
    response = client.post(
        "/api/research/theme-decomposition/sources/source-1/review",
        cookies={"stock_research_session": "session-1"},
        headers={"x-csrf-token": "csrf-1", "x-request-id": "request-1"},
        json={
            "to_status": "accepted",
            "expected_row_version": 1,
            "comment": "Reviewed full text.",
            "idempotency_key": "review-1",
        },
    )
    assert response.status_code == 200
    assert captured["actor_role"] == "user"
    assert captured["request_id"] == "request-1"

    def conflict(**kwargs):
        raise ThemeResearchDomainError(
            "version conflict",
            code="THEME_RESEARCH_VERSION_CONFLICT",
            details={"current_row_version": 2},
        )

    monkeypatch.setattr(dashboard_app, "review_theme_research_source", conflict)
    conflict_response = client.post(
        "/api/research/theme-decomposition/sources/source-1/review",
        cookies={"stock_research_session": "session-1"},
        headers={"x-csrf-token": "csrf-1"},
        json={
            "to_status": "accepted",
            "expected_row_version": 1,
            "comment": "Reviewed full text.",
            "idempotency_key": "review-2",
        },
    )
    assert conflict_response.status_code == 409
    assert conflict_response.json()["detail"]["error_code"] == "THEME_RESEARCH_VERSION_CONFLICT"


def test_rollback_api_requires_admin(monkeypatch) -> None:
    user = SimpleNamespace(user_id="user-1", role="user")
    monkeypatch.setattr(dashboard_app, "load_current_user_from_session", lambda token: user)
    monkeypatch.setattr(dashboard_app, "validate_csrf", lambda **kwargs: None)
    client = TestClient(dashboard_app.create_app())

    response = client.post(
        "/api/research/theme-decomposition/themes/theme-1/rollback",
        cookies={"stock_research_session": "session-1"},
        headers={"x-csrf-token": "csrf-1"},
        json={
            "snapshot_id": "snapshot-1",
            "expected_theme_version": 1,
            "comment": "Unauthorized rollback.",
            "idempotency_key": "rollback-1",
        },
    )

    assert response.status_code == 403
