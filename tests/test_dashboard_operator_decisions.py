from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app


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


def _base_decision_payload() -> dict:
    return {
        "asset_id": "CN:SZ:000001",
        "stock_code": "000001.SZ",
        "operator_action": "watch",
        "decision_label": "observe",
        "decision_status": "open",
        "evidence_artifact_id": "evidence_digest:2026-06-12:manual_v1:000001.SZ",
        "manual_review_required": True,
        "auto_trade_enabled": False,
    }


def test_operator_decision_create_requires_evidence_linkage(monkeypatch):
    monkeypatch.setattr(dashboard_app, "build_platform_readiness", lambda score_version="manual_v1": _ready_payload())
    monkeypatch.setattr(dashboard_app, "create_operator_decision", lambda payload: {"event_id": "should-not-write"})
    payload = _base_decision_payload()
    payload.pop("evidence_artifact_id")
    client = TestClient(dashboard_app.create_app())

    response = client.post("/api/operator-decisions", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "operator_decision_missing_evidence_linkage"


def test_operator_decision_create_forbids_auto_trade(monkeypatch):
    monkeypatch.setattr(dashboard_app, "build_platform_readiness", lambda score_version="manual_v1": _ready_payload())
    monkeypatch.setattr(dashboard_app, "create_operator_decision", lambda payload: {"event_id": "should-not-write"})
    payload = {**_base_decision_payload(), "auto_trade_enabled": True}
    client = TestClient(dashboard_app.create_app())

    response = client.post("/api/operator-decisions", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "operator_decision_auto_trade_forbidden"


def test_operator_decision_create_forces_manual_review_and_no_auto_trade(monkeypatch):
    captured = {}
    monkeypatch.setattr(dashboard_app, "build_platform_readiness", lambda score_version="manual_v1": _ready_payload())

    def fake_create(payload):
        captured.update(payload)
        return {
            "event_id": "operator_decision:test",
            "asset_id": payload["asset_id"],
            "operator_action": payload["operator_action"],
        }

    monkeypatch.setattr(dashboard_app, "create_operator_decision", fake_create)
    payload = {**_base_decision_payload(), "manual_review_required": False}
    client = TestClient(dashboard_app.create_app())

    response = client.post("/api/operator-decisions", json=payload)

    assert response.status_code == 200
    assert captured["manual_review_required"] is True
    assert captured["auto_trade_enabled"] is False
