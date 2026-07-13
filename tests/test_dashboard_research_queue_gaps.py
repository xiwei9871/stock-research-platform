from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import research_queue_gaps


def _gap_row(**overrides):
    row = {
        "case_id": "research_case:abc",
        "trade_date": "2026-07-03",
        "asset_id": "CN:SZ:000001",
        "theme": "bank_reversal",
        "title": "Bank reversal candidate",
        "status": "open",
        "priority": 30,
        "source_type": "review_item_snapshot",
        "source_id": "review_item_snapshot:abc",
        "evidence_status": "partial",
        "missing_evidence_count": 0,
        "partial_evidence_count": 2,
        "claim_count": 6,
        "evidence_count": 2,
        "latest_action_type": None,
        "latest_review_action_id": None,
        "latest_reviewer": None,
        "latest_review_comment": None,
        "latest_review_created_at": None,
        "payload": {"must_not": "leak"},
        "metadata": {"must_not": "leak"},
    }
    row.update(overrides)
    return row


def test_gap_reason_mapper_uses_whitelisted_fields():
    no_evidence = research_queue_gaps.gap_reasons_for_case(_gap_row(evidence_count=0, evidence_status="complete", partial_evidence_count=0))
    missing = research_queue_gaps.gap_reasons_for_case(_gap_row(missing_evidence_count=1, evidence_status="complete", partial_evidence_count=0))
    partial = research_queue_gaps.gap_reasons_for_case(_gap_row(partial_evidence_count=1, evidence_status="complete"))
    status = research_queue_gaps.gap_reasons_for_case(_gap_row(evidence_status="pending", partial_evidence_count=0))
    unknown = research_queue_gaps.gap_reasons_for_case(
        _gap_row(evidence_count=2, evidence_status="", missing_evidence_count=0, partial_evidence_count=0),
        force_gap=True,
    )

    assert no_evidence == ["no_evidence"]
    assert missing == ["missing_evidence"]
    assert partial == ["partial_evidence"]
    assert status == ["incomplete_evidence_status"]
    assert unknown == ["unknown_gap"]


def test_list_research_queue_gaps_returns_summary_and_clamps_limit(monkeypatch):
    captured = {}

    class _Context:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_fetch_all(_conn, sql, params=None):
        if "LIMIT %s" in sql:
            captured["params"] = params
            return [_gap_row()]
        return [
            {
                "gap_case_count": 3,
                "no_evidence_count": 1,
                "missing_evidence_count": 1,
                "partial_evidence_count": 2,
                "incomplete_evidence_status_count": 2,
                "unknown_gap_count": 0,
            }
        ]

    monkeypatch.setattr(research_queue_gaps, "connect", lambda service: _Context())
    monkeypatch.setattr(research_queue_gaps, "fetch_all", fake_fetch_all)

    payload = research_queue_gaps.list_research_queue_gaps(trade_date="2026-07-03", limit=500, service="research")

    assert captured["params"][-1] == 100
    assert payload["trade_date"] == "2026-07-03"
    assert payload["items"][0]["gap_reasons"] == ["partial_evidence", "incomplete_evidence_status"]
    assert payload["items"][0]["gap_summary"] == "partial evidence signal found; evidence status is partial"
    assert payload["items"][0]["review_status"] == "pending"
    assert payload["items"][0]["latest_review_action"] is None
    assert payload["summary"]["gap_case_count"] == 3
    assert payload["summary"]["partial_evidence_count"] == 2
    assert payload["summary"]["incomplete_evidence_status_count"] == 2
    assert "payload" not in payload["items"][0]
    assert "metadata" not in payload["items"][0]


def test_gap_read_model_includes_latest_review_status():
    item = research_queue_gaps.gap_case_read_model(
        _gap_row(
            latest_action_type="request_more_evidence",
            latest_review_action_id="review_action:abc",
            latest_review_created_at="2026-07-08T10:00:00+08:00",
            latest_review_comment="需要补证",
            latest_reviewer="operator",
        )
    )

    assert item["review_status"] == "request_more_evidence"
    assert item["latest_review_action"]["review_action_id"] == "review_action:abc"
    assert item["latest_review_action"]["comment"] == "需要补证"


def test_list_research_queue_gaps_empty(monkeypatch):
    class _Context:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(research_queue_gaps, "connect", lambda service: _Context())
    monkeypatch.setattr(research_queue_gaps, "fetch_all", lambda _conn, sql, params=None: [])

    payload = research_queue_gaps.list_research_queue_gaps(trade_date="2026-07-03", service="research")

    assert payload["items"] == []
    assert payload["summary"]["gap_case_count"] == 0


def test_research_queue_gaps_route_returns_whitelist(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "list_research_queue_gaps",
        lambda **kwargs: {
            "trade_date": "2026-07-03",
            "items": [_gap_row()],
            "summary": {
                "gap_case_count": 1,
                "no_evidence_count": 0,
                "missing_evidence_count": 0,
                "partial_evidence_count": 1,
                "incomplete_evidence_status_count": 1,
                "unknown_gap_count": 0,
            },
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/research/queue/gaps?trade_date=2026-07-03&limit=500")

    assert response.status_code == 200
    payload = response.json()
    assert payload["trade_date"] == "2026-07-03"
    assert payload["items"][0]["case_id"] == "research_case:abc"
    assert "payload" not in payload["items"][0]
    assert "metadata" not in payload["items"][0]
