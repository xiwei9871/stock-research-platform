from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app


def test_research_publication_preview_api_returns_whitelisted_package(monkeypatch):
    sent = {"called": False}

    def fake_send(*args, **kwargs):
        sent["called"] = True

    monkeypatch.setattr(dashboard_app, "send_openclaw_feishu_message", fake_send, raising=False)
    monkeypatch.setattr(
        dashboard_app,
        "build_research_publication_package",
        lambda **kwargs: {
            "trade_date": "2026-07-03",
            "package_id": "research_publication_package:abc",
            "publishable": False,
            "actual_publish_enabled": False,
            "gate": {"status": "blocked", "research_ready_for_publication": False, "actual_publish_enabled": False},
            "summary": {"case_count": 15, "claim_count": 90, "gap_count": 15},
            "sections": [
                {
                    "section_type": "blocked_cases",
                    "title": "发布阻塞项",
                    "items": [{"case_id": "research_case:alpha", "payload": {"must_not": "leak"}}],
                }
            ],
            "warnings": [],
            "blockers": [{"code": "pending_gap", "message": "14 gap cases have not been reviewed", "count": 14}],
            "payload": {"must_not": "leak"},
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/research/publication/preview?trade_date=2026-07-03")

    assert response.status_code == 200
    payload = response.json()
    assert payload["publishable"] is False
    assert payload["gate"]["status"] == "blocked"
    assert payload["blockers"][0]["code"] == "pending_gap"
    assert sent["called"] is False
    assert "payload" not in payload
    assert "payload" not in payload["sections"][0]["items"][0]


def test_research_publication_preview_api_requires_trade_date():
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/research/publication/preview")

    assert response.status_code == 422
