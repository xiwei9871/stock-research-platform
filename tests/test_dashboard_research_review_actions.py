from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app


def _review_action(**overrides):
    item = {
        "review_action_id": "review_action:abc",
        "case_id": "research_case:abc",
        "trade_date": "2026-07-03",
        "asset_id": "CN:SZ:000001",
        "action_type": "request_more_evidence",
        "gap_reasons": ["missing_evidence"],
        "reviewer": "operator",
        "comment": "需要补充公告证据",
        "created_at": "2026-07-08T10:00:00+08:00",
        "source_context": {"from": "home_cockpit_gap_detail"},
        "metadata": {"must_not": "leak"},
        "payload": {"must_not": "leak"},
    }
    item.update(overrides)
    return item


def test_review_action_post_requires_write_token(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_WRITE_GUARD", "true")
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_WRITE_TOKEN", "secret")
    monkeypatch.setattr(dashboard_app, "record_review_action", lambda payload: "review_action:abc", raising=False)
    client = TestClient(dashboard_app.create_app())

    response = client.post(
        "/api/research/review-actions",
        json={"case_id": "research_case:abc", "action_type": "acknowledge_gap"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "missing_dashboard_write_token"


def test_review_action_post_records_with_write_token(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_WRITE_GUARD", "true")
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_WRITE_TOKEN", "secret")
    captured = {}

    def fake_record(payload):
        captured.update(payload)
        return "review_action:abc"

    monkeypatch.setattr(dashboard_app, "record_review_action", fake_record, raising=False)
    client = TestClient(dashboard_app.create_app())

    response = client.post(
        "/api/research/review-actions",
        headers={"X-Dashboard-Write-Token": "secret"},
        json={
            "case_id": "research_case:abc",
            "trade_date": "2026-07-03",
            "asset_id": "CN:SZ:000001",
            "action_type": "request_more_evidence",
            "gap_reasons": ["missing_evidence"],
            "comment": "需要补充公告证据",
            "source_context": {"from": "home_cockpit_gap_detail"},
        },
    )

    assert response.status_code == 200
    assert response.json() == {"review_action_id": "review_action:abc", "status": "recorded"}
    assert captured["action_type"] == "request_more_evidence"


def test_review_action_post_rejects_invalid_payload(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_DASHBOARD_WRITE_GUARD", "false")
    client = TestClient(dashboard_app.create_app())

    response = client.post(
        "/api/research/review-actions",
        json={"case_id": "research_case:abc", "action_type": "publish"},
    )

    assert response.status_code == 400


def test_review_actions_get_returns_whitelisted_items(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "list_review_actions",
        lambda **kwargs: [_review_action()],
        raising=False,
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/research/review-actions?case_id=research_case:abc&limit=500")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["review_action_id"] == "review_action:abc"
    assert item["source_context"] == {"from": "home_cockpit_gap_detail"}
    assert "metadata" not in item
    assert "payload" not in item
