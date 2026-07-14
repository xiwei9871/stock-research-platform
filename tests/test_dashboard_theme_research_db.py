from __future__ import annotations

import copy
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

    artifact = theme_research.list_theme_research_themes(read_source="artifact")
    database = theme_research.list_theme_research_themes(read_source="db")

    assert database == artifact


def test_theme_package_preserves_wave_a_research_profiles() -> None:
    package = normalize_artifact_package()
    wave_a_theme_ids = {
        "ai_logic_compute_chips_value_chain_v1",
        "optical_communications_data_center_interconnect_value_chain_v1",
        "semiconductor_materials_electronic_chemicals_value_chain_v1",
        "power_semiconductors_value_chain_v1",
        "industrial_automation_control_value_chain_v1",
    }
    artifact_profiles = {
        row["theme_id"]: row["artifact_metadata"]["research_profile"]
        for row in package.themes
        if row["theme_id"] in wave_a_theme_ids
    }
    assert set(artifact_profiles) == wave_a_theme_ids

    database_package = theme_research_db._theme_package(package)

    assert {
        row["theme_id"]: row
        for row in database_package["research_profiles"]
        if row["theme_id"] in wave_a_theme_ids
    } == {
        theme_id: {**profile, "theme_id": theme_id}
        for theme_id, profile in artifact_profiles.items()
    }
    detail_fields = {
        "industry_stage",
        "central_conflict",
        "investment_summary",
        "value_flow_summary",
        "profit_pool_summary",
        "catalyst_claim_ids",
        "risk_claim_ids",
        "validation_signals",
        "evidence_gap_summary",
    }
    assert all(detail_fields <= set(row) for row in artifact_profiles.values())


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
