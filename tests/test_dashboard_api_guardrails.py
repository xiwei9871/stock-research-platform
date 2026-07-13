import pytest
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard.api_guardrails import GuardrailConfig, require_guarded_operation


def _ready_payload() -> dict:
    return {
        "status": "OK",
        "policy": {
            "status": "ready",
            "ready_for_dashboard": True,
            "ready_for_publication": True,
            "blocking_reasons": [],
            "warnings": [],
        },
    }


def _degraded_payload() -> dict:
    return {
        "status": "PARTIAL",
        "policy": {
            "status": "degraded_ready",
            "ready_for_dashboard": True,
            "ready_for_publication": False,
            "blocking_reasons": ["daily_status=partial_success"],
            "warnings": ["pipeline_status=DEGRADED_READY"],
        },
    }


def test_guard_allows_readonly_when_disabled():
    assert require_guarded_operation(
        operation="operator_decision_write",
        headers={},
        config=GuardrailConfig(enabled=False, shared_token=""),
    ) == {"operation": "operator_decision_write", "authenticated": False}


def test_guard_blocks_missing_token_when_enabled():
    with pytest.raises(PermissionError, match="missing_dashboard_write_token"):
        require_guarded_operation(
            operation="operator_decision_write",
            headers={},
            config=GuardrailConfig(enabled=True, shared_token="secret"),
        )


def test_guard_blocks_wrong_token_when_enabled():
    with pytest.raises(PermissionError, match="invalid_dashboard_write_token"):
        require_guarded_operation(
            operation="operator_decision_write",
            headers={"x-dashboard-write-token": "wrong"},
            config=GuardrailConfig(enabled=True, shared_token="secret"),
        )


def test_guard_accepts_correct_token_when_enabled():
    assert require_guarded_operation(
        operation="operator_decision_write",
        headers={"x-dashboard-write-token": "secret"},
        config=GuardrailConfig(enabled=True, shared_token="secret"),
    ) == {"operation": "operator_decision_write", "authenticated": True}


@pytest.mark.parametrize(
    ("path", "json_payload"),
    [
        ("/api/public-news/refresh", {}),
        ("/api/dashboard/cache/clear", {}),
        ("/api/backtests/run", {"strategy_id": "manual_v1_topn_rotation"}),
        ("/api/research/review-actions", {"case_id": "research_case:abc", "action_type": "acknowledge_gap"}),
    ],
)
def test_write_endpoints_block_missing_dashboard_write_token(monkeypatch, path, json_payload):
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_WRITE_GUARD", "true")
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_WRITE_TOKEN", "secret")
    monkeypatch.setattr(dashboard_app, "refresh_public_news_for_dashboard", lambda: {"stored": 0})
    monkeypatch.setattr(dashboard_app, "run_backtest", lambda payload: {"status": "ok"})
    client = TestClient(dashboard_app.create_app())

    response = client.post(path, json=json_payload)

    assert response.status_code == 403
    assert response.json()["detail"] == "missing_dashboard_write_token"


def test_write_endpoint_accepts_dashboard_write_token(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_WRITE_GUARD", "true")
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_WRITE_TOKEN", "secret")
    monkeypatch.setattr(dashboard_app, "refresh_public_news_for_dashboard", lambda: {"stored": 1})
    client = TestClient(dashboard_app.create_app())

    response = client.post("/api/public-news/refresh", headers={"X-Dashboard-Write-Token": "secret"})

    assert response.status_code == 200
    assert response.json()["stored"] == 1


def test_operator_decision_create_blocks_when_platform_not_publication_ready(monkeypatch):
    monkeypatch.setattr(dashboard_app, "build_platform_readiness", lambda score_version="manual_v1": _degraded_payload())

    def fail_if_called(payload):
        raise AssertionError("create_operator_decision should not be called")

    monkeypatch.setattr(dashboard_app, "create_operator_decision", fail_if_called)
    client = TestClient(dashboard_app.create_app())

    response = client.post(
        "/api/operator-decisions",
        json={
            "asset_id": "CN:SZ:000001",
            "operator_action": "watch",
            "decision_label": "observe",
            "evidence_artifact_id": "evidence_digest:test",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "platform_not_ready_for_publication"
    assert response.json()["detail"]["blocking_reasons"] == ["daily_status=partial_success"]


def test_operator_decision_create_allows_ready_platform(monkeypatch):
    monkeypatch.setattr(dashboard_app, "build_platform_readiness", lambda score_version="manual_v1": _ready_payload())
    monkeypatch.setattr(
        dashboard_app,
        "create_operator_decision",
        lambda payload: {
            "event_id": "operator_decision:test",
            "asset_id": payload["asset_id"],
            "operator_action": payload["operator_action"],
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.post(
        "/api/operator-decisions",
        json={
            "asset_id": "CN:SZ:000001",
            "operator_action": "watch",
            "decision_label": "observe",
            "evidence_artifact_id": "evidence_digest:test",
        },
    )

    assert response.status_code == 200
    assert response.json()["event_id"] == "operator_decision:test"


def test_operator_decision_create_rejects_invalid_asset_before_write(monkeypatch):
    monkeypatch.setattr(dashboard_app, "build_platform_readiness", lambda score_version="manual_v1": _ready_payload())

    def fail_if_called(payload):
        raise AssertionError("create_operator_decision should not be called")

    monkeypatch.setattr(dashboard_app, "create_operator_decision", fail_if_called)
    client = TestClient(dashboard_app.create_app())

    response = client.post(
        "/api/operator-decisions",
        json={"asset_id": "DROP TABLE review", "operator_action": "watch"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid_asset_id"


def test_operator_decision_create_rejects_follow_up_before_decision_date(monkeypatch):
    monkeypatch.setattr(dashboard_app, "build_platform_readiness", lambda score_version="manual_v1": _ready_payload())
    monkeypatch.setattr(dashboard_app, "create_operator_decision", lambda payload: {"event_id": "should-not-write"})
    client = TestClient(dashboard_app.create_app())

    response = client.post(
        "/api/operator-decisions",
        json={
            "asset_id": "CN:SZ:000001",
            "decision_date": "2026-06-30",
            "operator_action": "follow_up",
            "follow_up_date": "2026-06-29",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "follow_up_date_before_decision_date"


def test_api_response_generates_request_id(monkeypatch):
    monkeypatch.setattr(dashboard_app, "load_platform_summary", lambda **kwargs: {"latest_market_date": "2026-06-08"})
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/platform/summary")

    assert response.status_code == 200
    assert response.headers["x-request-id"]


def test_api_response_echoes_request_id(monkeypatch):
    monkeypatch.setattr(dashboard_app, "load_platform_summary", lambda **kwargs: {"latest_market_date": "2026-06-08"})
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/platform/summary", headers={"X-Request-ID": "expert-review-001"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "expert-review-001"
