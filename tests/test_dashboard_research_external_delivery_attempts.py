import json

from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app


def _attempt() -> dict:
    return {
        "delivery_attempt_id": "external_delivery_attempt:abc",
        "publication_snapshot_id": "publication_snapshot:research_queue_internal:abc",
        "trade_date": "2026-07-06",
        "channel": "feishu_preview",
        "mode": "dry_run",
        "status": "preview_recorded",
        "dry_run": True,
        "external_send_enabled": False,
        "delivery_plan_id": "research_external_delivery_plan:abc",
        "message_title": "Research Queue Snapshot 2026-07-06",
        "created_by": "operator",
        "created_at": "2026-07-08T10:00:00+08:00",
        "error_code": "",
        "error_message": "",
    }


def _detail() -> dict:
    item = _attempt()
    item.update(
        {
            "finished_at": "2026-07-08T10:00:01+08:00",
            "events": [
                {
                    "delivery_event_id": "external_delivery_event:abc",
                    "delivery_attempt_id": "external_delivery_attempt:abc",
                    "event_index": 0,
                    "event_type": "plan_built",
                    "status": "ok",
                    "payload": {"delivery_plan_id": "research_external_delivery_plan:abc"},
                    "created_at": "2026-07-08T10:00:00+08:00",
                }
            ],
            "source_summary": {
                "delivery_plan_id": "research_external_delivery_plan:abc",
                "message_title": "Research Queue Snapshot 2026-07-06",
            },
            "warnings": ["External delivery is not connected in this version."],
        }
    )
    return item


def test_delivery_attempts_api_lists_whitelisted_items_without_write_token(monkeypatch):
    sent = {"feishu": False, "strategy": False}
    monkeypatch.setattr(dashboard_app, "send_openclaw_feishu_message", lambda *args, **kwargs: sent.update(feishu=True), raising=False)
    monkeypatch.setattr(dashboard_app, "publish_strategy_eod", lambda *args, **kwargs: sent.update(strategy=True), raising=False)
    monkeypatch.setattr(dashboard_app, "list_external_delivery_attempts", lambda **kwargs: [_attempt()])
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/research/publication/delivery-attempts"
        "?publication_snapshot_id=publication_snapshot:research_queue_internal:abc&limit=500"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["delivery_attempt_id"] == "external_delivery_attempt:abc"
    assert payload["items"][0]["external_send_enabled"] is False
    encoded = json.dumps(payload, ensure_ascii=False).lower()
    assert "metadata" not in encoded
    assert "payload" not in encoded
    assert "token" not in encoded
    assert sent == {"feishu": False, "strategy": False}


def test_delivery_attempt_detail_api_supports_colon_id(monkeypatch):
    monkeypatch.setattr(dashboard_app, "get_external_delivery_attempt", lambda delivery_attempt_id, **kwargs: _detail())
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/research/publication/delivery-attempts/external_delivery_attempt:abc")

    assert response.status_code == 200
    payload = response.json()
    assert payload["delivery_attempt_id"] == "external_delivery_attempt:abc"
    assert payload["events"][0]["event_type"] == "plan_built"
    assert "payload" in payload["events"][0]
    assert "secret" not in json.dumps(payload, ensure_ascii=False).lower()


def test_delivery_attempt_detail_api_returns_404(monkeypatch):
    monkeypatch.setattr(dashboard_app, "get_external_delivery_attempt", lambda delivery_attempt_id, **kwargs: None)
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/research/publication/delivery-attempts/external_delivery_attempt:missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "delivery_attempt_not_found"
