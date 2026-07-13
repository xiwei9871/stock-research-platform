from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import research_publish_gate


def _health_payload(**summary_overrides):
    summary = {
        "case_count": 15,
        "open_case_count": 15,
        "claim_count": 90,
        "evidence_artifact_count": 30,
        "evidence_link_count": 120,
        "evidence_gap_count": 15,
        "pending_gap_count": 14,
        "reviewed_gap_count": 0,
        "request_more_evidence_count": 1,
        "deferred_gap_count": 0,
        "unmatched_digest_count": 0,
        "error_count": 0,
    }
    summary.update(summary_overrides)
    return {
        "trade_date": "2026-07-03",
        "status": "partial",
        "can_review": summary["open_case_count"] > 0,
        "can_publish_research_queue": False,
        "summary": summary,
        "last_refresh": None,
        "top_gap_cases": [],
        "warnings": [],
    }


def _gap_payload(review_status="pending"):
    return {
        "trade_date": "2026-07-03",
        "items": [
            {
                "case_id": "research_case:alpha",
                "trade_date": "2026-07-03",
                "asset_id": "CN:SZ:000001",
                "theme": "bank_reversal",
                "title": "Bank reversal candidate",
                "status": "open",
                "priority": 20,
                "evidence_count": 2,
                "claim_count": 6,
                "gap_reasons": ["partial_evidence"],
                "gap_summary": "partial evidence signal found",
                "review_status": review_status,
                "latest_review_action": {"payload": {"must_not": "leak"}},
                "source_type": "review_item_snapshot",
                "source_id": "review_item_snapshot:alpha",
                "payload": {"must_not": "leak"},
            }
        ],
        "summary": {},
    }


def test_publish_gate_marks_empty_queue(monkeypatch):
    monkeypatch.setattr(
        research_publish_gate,
        "load_research_queue_health",
        lambda **kwargs: _health_payload(
            case_count=0,
            open_case_count=0,
            claim_count=0,
            evidence_artifact_count=0,
            evidence_link_count=0,
            evidence_gap_count=0,
            pending_gap_count=0,
            request_more_evidence_count=0,
        ),
    )
    monkeypatch.setattr(research_publish_gate, "list_research_queue_gaps", lambda **kwargs: {"items": []})

    gate = research_publish_gate.get_research_publish_gate(trade_date="2026-07-03")

    assert gate["status"] == "empty"
    assert gate["research_ready_for_publication"] is False
    assert gate["actual_publish_enabled"] is False
    assert gate["publication_entrypoint_status"] == "scaffolded"
    assert gate["internal_snapshot_enabled"] is False
    assert gate["external_delivery_enabled"] is False


def test_publish_gate_blocks_pending_request_and_deferred_gaps(monkeypatch):
    monkeypatch.setattr(
        research_publish_gate,
        "load_research_queue_health",
        lambda **kwargs: _health_payload(
            evidence_gap_count=6,
            pending_gap_count=3,
            request_more_evidence_count=2,
            deferred_gap_count=1,
        ),
    )
    monkeypatch.setattr(research_publish_gate, "list_research_queue_gaps", lambda **kwargs: _gap_payload("pending"))

    gate = research_publish_gate.get_research_publish_gate(trade_date="2026-07-03")

    assert gate["status"] == "blocked"
    assert gate["research_ready_for_publication"] is False
    assert {blocker["code"]: blocker["count"] for blocker in gate["blockers"]} == {
        "pending_gap": 3,
        "request_more_evidence": 2,
        "deferred_gap": 1,
        "external_delivery_not_connected": 1,
    }
    assert gate["top_blocked_cases"][0]["case_id"] == "research_case:alpha"
    assert "payload" not in gate["top_blocked_cases"][0]


def test_publish_gate_blocks_unmatched_digest_and_missing_links(monkeypatch):
    monkeypatch.setattr(
        research_publish_gate,
        "load_research_queue_health",
        lambda **kwargs: _health_payload(
            evidence_gap_count=0,
            pending_gap_count=0,
            request_more_evidence_count=0,
            unmatched_digest_count=2,
            evidence_link_count=0,
        ),
    )
    monkeypatch.setattr(research_publish_gate, "list_research_queue_gaps", lambda **kwargs: {"items": []})

    gate = research_publish_gate.get_research_publish_gate(trade_date="2026-07-03")

    assert gate["status"] == "blocked"
    assert [blocker["code"] for blocker in gate["blockers"]] == [
        "unmatched_digest",
        "missing_evidence_links",
        "external_delivery_not_connected",
    ]


def test_publish_gate_marks_errors_failed(monkeypatch):
    monkeypatch.setattr(
        research_publish_gate,
        "load_research_queue_health",
        lambda **kwargs: _health_payload(error_count=1),
    )
    monkeypatch.setattr(research_publish_gate, "list_research_queue_gaps", lambda **kwargs: _gap_payload("pending"))

    gate = research_publish_gate.get_research_publish_gate(trade_date="2026-07-03")

    assert gate["status"] == "failed"
    assert gate["blockers"][0]["code"] == "refresh_errors"
    assert gate["research_ready_for_publication"] is False


def test_publish_gate_marks_all_reviewed_gaps_research_ready_but_publish_disabled(monkeypatch):
    monkeypatch.setattr(
        research_publish_gate,
        "load_research_queue_health",
        lambda **kwargs: _health_payload(
            evidence_gap_count=15,
            pending_gap_count=0,
            reviewed_gap_count=15,
            request_more_evidence_count=0,
            deferred_gap_count=0,
        ),
    )
    monkeypatch.setattr(research_publish_gate, "list_research_queue_gaps", lambda **kwargs: _gap_payload("reviewed"))

    gate = research_publish_gate.get_research_publish_gate(trade_date="2026-07-03")

    assert gate["status"] == "research_ready"
    assert gate["research_ready_for_publication"] is True
    assert gate["actual_publish_enabled"] is False
    assert gate["internal_snapshot_enabled"] is True
    assert gate["external_delivery_enabled"] is False
    assert gate["blockers"] == []
    assert gate["warnings"][0]["code"] == "external_delivery_not_connected"


def test_publish_gate_api_is_read_only_and_whitelisted(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "get_research_publish_gate",
        lambda **kwargs: {
            "trade_date": "2026-07-03",
            "status": "blocked",
            "research_ready_for_publication": False,
            "actual_publish_enabled": False,
            "publication_entrypoint_status": "scaffolded",
            "internal_snapshot_enabled": False,
            "external_delivery_enabled": False,
            "summary": {"case_count": 1, "pending_gap_count": 1},
            "blockers": [{"code": "pending_gap", "message": "1 gap case has not been reviewed", "count": 1}],
            "warnings": [],
            "top_blocked_cases": [{"case_id": "research_case:alpha", "payload": {"must_not": "leak"}}],
            "payload": {"must_not": "leak"},
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/research/queue/publish-gate?trade_date=2026-07-03")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["actual_publish_enabled"] is False
    assert payload["top_blocked_cases"][0]["case_id"] == "research_case:alpha"
    assert "payload" not in payload
    assert "payload" not in payload["top_blocked_cases"][0]
