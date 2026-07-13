from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import research_publication_snapshots


def _snapshot_row(snapshot_id: str = "publication_snapshot:research_queue_internal:abc") -> dict:
    return {
        "publication_snapshot_id": snapshot_id,
        "trade_date": "2026-07-06",
        "channel": "research_queue_internal",
        "title": "Research Queue Internal Snapshot 2026-07-06",
        "created_by": "research_queue_publish",
        "created_at": "2026-07-08T10:00:00+08:00",
        "payload": {
            "run_id": "research_queue_publish:abc",
            "channel": "research_queue_internal",
            "package_id": "research_publication_package:abc",
            "publishable": True,
            "actual_publish_enabled": False,
            "internal_snapshot_enabled": True,
            "external_delivery_enabled": False,
            "gate": {
                "status": "research_ready",
                "research_ready_for_publication": True,
                "actual_publish_enabled": False,
                "internal_snapshot_enabled": True,
                "external_delivery_enabled": False,
                "payload": {"must_not": "leak"},
            },
            "summary": {
                "case_count": 2,
                "claim_count": 3,
                "evidence_count": 4,
                "evidence_link_count": 5,
                "gap_count": 0,
                "reviewed_gap_count": 0,
                "pending_gap_count": 0,
                "request_more_evidence_count": 0,
                "deferred_gap_count": 0,
                "unmatched_digest_count": 0,
                "error_count": 0,
            },
            "sections": [
                {
                    "section_type": "research_queue_summary",
                    "title": "研究队列摘要",
                    "items": [
                        {
                            "case_count": 2,
                            "claim_count": 3,
                            "payload": {"must_not": "leak"},
                            "metadata": {"must_not": "leak"},
                        }
                    ],
                }
            ],
            "warnings": [{"code": "external_delivery_not_connected", "message": "External delivery is not connected", "count": 1}],
            "blockers": [],
            "payload": {"must_not": "leak"},
            "internal_metadata": {"must_not": "leak"},
        },
    }


def test_publication_snapshot_read_model_filters_payload_and_metadata():
    item = research_publication_snapshots.publication_snapshot_list_item_read_model(_snapshot_row())

    assert item["publication_snapshot_id"] == "publication_snapshot:research_queue_internal:abc"
    assert item["package_id"] == "research_publication_package:abc"
    assert item["gate_status"] == "research_ready"
    assert item["research_ready_for_publication"] is True
    assert item["actual_external_delivery_enabled"] is False
    assert item["case_count"] == 2
    assert item["claim_count"] == 3
    assert item["evidence_count"] == 4
    assert item["gap_count"] == 0
    assert item["blocker_count"] == 0
    assert "payload" not in item
    assert "metadata" not in item


def test_publication_snapshot_detail_filters_raw_payload():
    detail = research_publication_snapshots.publication_snapshot_detail_read_model(_snapshot_row())

    assert detail["publication_snapshot_id"] == "publication_snapshot:research_queue_internal:abc"
    assert detail["gate"]["status"] == "research_ready"
    assert detail["summary"]["case_count"] == 2
    assert detail["sections"][0]["items"][0]["claim_count"] == 3
    assert detail["source_trace_summary"]["run_id"] == "research_queue_publish:abc"
    assert detail["source_trace_summary"]["channel"] == "research_queue_internal"
    assert "payload" not in detail
    assert "payload" not in detail["gate"]
    assert "payload" not in detail["sections"][0]["items"][0]
    assert "internal_metadata" not in detail


def test_list_publication_snapshots_clamps_limit_and_filters(monkeypatch):
    captured = {}

    class _Context:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_fetch_all(_conn, sql, params=None):
        captured["sql"] = sql
        captured["params"] = params
        return [_snapshot_row()]

    monkeypatch.setattr(research_publication_snapshots, "connect", lambda service: _Context())
    monkeypatch.setattr(research_publication_snapshots, "fetch_all", fake_fetch_all)

    rows = research_publication_snapshots.list_publication_snapshots(
        trade_date="2026-07-06",
        channel="research_queue_internal",
        limit=500,
        service="research",
    )

    assert rows[0]["publication_snapshot_id"] == "publication_snapshot:research_queue_internal:abc"
    assert captured["params"] == ["2026-07-06", "research_queue_internal", 100]
    assert "payload" not in rows[0]


def test_get_publication_snapshot_returns_none(monkeypatch):
    class _Context:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(research_publication_snapshots, "connect", lambda service: _Context())
    monkeypatch.setattr(research_publication_snapshots, "fetch_all", lambda _conn, sql, params=None: [])

    assert research_publication_snapshots.get_publication_snapshot("publication_snapshot:missing", service="research") is None


def test_publication_snapshots_api_returns_whitelisted_items(monkeypatch):
    sent = {"called": False}
    monkeypatch.setattr(dashboard_app, "send_openclaw_feishu_message", lambda *args, **kwargs: sent.update(called=True), raising=False)
    monkeypatch.setattr(dashboard_app, "list_publication_snapshots", lambda **kwargs: [research_publication_snapshots.publication_snapshot_list_item_read_model(_snapshot_row())])
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/research/publication/snapshots?trade_date=2026-07-06&limit=500")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["package_id"] == "research_publication_package:abc"
    assert "payload" not in payload["items"][0]
    assert sent["called"] is False


def test_publication_snapshot_detail_api_supports_colon_id(monkeypatch):
    monkeypatch.setattr(dashboard_app, "get_publication_snapshot", lambda publication_snapshot_id, **kwargs: research_publication_snapshots.publication_snapshot_detail_read_model(_snapshot_row(publication_snapshot_id)))
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/research/publication/snapshots/publication_snapshot:research_queue_internal:abc")

    assert response.status_code == 200
    assert response.json()["publication_snapshot_id"] == "publication_snapshot:research_queue_internal:abc"


def test_publication_snapshot_detail_api_returns_404(monkeypatch):
    monkeypatch.setattr(dashboard_app, "get_publication_snapshot", lambda publication_snapshot_id, **kwargs: None)
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/research/publication/snapshots/publication_snapshot:missing")

    assert response.status_code == 404
