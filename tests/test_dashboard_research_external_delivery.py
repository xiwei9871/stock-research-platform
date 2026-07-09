import json

from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app


def _plan() -> dict:
    return {
        "delivery_plan_id": "research_external_delivery_plan:abc",
        "publication_snapshot_id": "publication_snapshot:research_queue_internal:abc",
        "trade_date": "2026-07-06",
        "channel": "feishu_preview",
        "dry_run": True,
        "external_send_enabled": False,
        "status": "preview_ready",
        "message": {
            "title": "Research Queue Snapshot 2026-07-06",
            "summary": "Cases 2, claims 3, evidence 4, gaps 0. Gate research_ready.",
            "sections": [{"section_type": "research_queue_summary", "title": "研究队列摘要", "items": []}],
        },
        "source": {
            "package_id": "research_publication_package:abc",
            "gate_status": "research_ready",
            "snapshot_channel": "research_queue_internal",
        },
        "blockers": [],
        "warnings": ["External delivery is not connected in this version."],
    }


def test_delivery_plan_api_returns_whitelisted_plan_without_write_token(monkeypatch):
    sent = {"feishu": False, "strategy": False}
    monkeypatch.setattr(dashboard_app, "send_openclaw_feishu_message", lambda *args, **kwargs: sent.update(feishu=True), raising=False)
    monkeypatch.setattr(dashboard_app, "publish_strategy_eod", lambda *args, **kwargs: sent.update(strategy=True), raising=False)
    monkeypatch.setattr(dashboard_app, "build_research_external_delivery_plan", lambda **kwargs: _plan())
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/research/publication/delivery-plan"
        "?publication_snapshot_id=publication_snapshot:research_queue_internal:abc&channel=feishu_preview"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "preview_ready"
    assert payload["external_send_enabled"] is False
    assert payload["message"]["title"] == "Research Queue Snapshot 2026-07-06"
    encoded = json.dumps(payload, ensure_ascii=False).lower()
    assert "payload" not in encoded
    assert "internal_metadata" not in encoded
    assert "webhook" not in encoded
    assert "token" not in encoded
    assert sent == {"feishu": False, "strategy": False}


def test_delivery_plan_api_returns_404_for_missing_snapshot(monkeypatch):
    missing = _plan()
    missing["status"] = "snapshot_not_found"
    monkeypatch.setattr(dashboard_app, "build_research_external_delivery_plan", lambda **kwargs: missing)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/research/publication/delivery-plan"
        "?publication_snapshot_id=publication_snapshot:missing&channel=feishu_preview"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "publication_snapshot_not_found"


def test_delivery_plan_api_returns_400_for_unsupported_channel(monkeypatch):
    unsupported = _plan()
    unsupported["status"] = "unsupported_channel"
    monkeypatch.setattr(dashboard_app, "build_research_external_delivery_plan", lambda **kwargs: unsupported)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/research/publication/delivery-plan"
        "?publication_snapshot_id=publication_snapshot:research_queue_internal:abc&channel=live_feishu"
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "unsupported_delivery_channel"
