from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import research_cases


def test_research_cases_route_returns_items(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "list_research_cases",
        lambda **kwargs: [
            {
                "case_id": "research_case:abc",
                "trade_date": "2026-07-06",
                "asset_id": "CN:SZ:000001",
                "theme": "bank_reversal",
                "title": "Bank reversal candidate",
                "status": "open",
                "priority": 30,
                "source_type": "review_item_snapshot",
                "source_id": "review_item_snapshot:abc",
                "evidence_status": "partial",
                "missing_evidence_count": 1,
                "partial_evidence_count": 2,
                "evidence_count": 2,
                "claim_count": 1,
                "payload": {"must_not": "leak"},
                "metadata": {"must_not": "leak"},
            }
        ],
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/research/cases?trade_date=2026-07-06&status=open&limit=500")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["case_id"] == "research_case:abc"
    assert item["source_type"] == "review_item_snapshot"
    assert item["source_id"] == "review_item_snapshot:abc"
    assert item["evidence_status"] == "partial"
    assert item["missing_evidence_count"] == 1
    assert item["partial_evidence_count"] == 2
    assert "payload" not in item
    assert "metadata" not in item


def test_research_case_detail_route_returns_whitelisted_claims_and_evidence(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "load_research_case_detail",
        lambda case_id, **kwargs: {
            "case": {
                "case_id": case_id,
                "trade_date": "2026-07-06",
                "asset_id": "CN:SZ:000001",
                "theme": "bank_reversal",
                "title": "Bank reversal candidate",
                "status": "open",
                "priority": 30,
                "source_type": "review_item_snapshot",
                "source_id": "review_item_snapshot:abc",
                "payload": {"must_not": "leak"},
                "metadata": {"must_not": "leak"},
            },
            "claims": [
                {
                    "claim_id": "research_claim:1",
                    "claim_type": "risk",
                    "claim_text": "evidence_status=partial, missing=1, partial=2",
                    "confidence": None,
                    "status": "draft",
                    "source_type": "review_item_snapshot",
                    "source_id": "review_item_snapshot:abc",
                    "metadata": {"must_not": "leak"},
                }
            ],
            "evidence": [
                {
                    "evidence_id": "evidence_artifact:1",
                    "source_type": "review_item_snapshot",
                    "source_id": "review_item_snapshot:abc",
                    "asset_id": "CN:SZ:000001",
                    "trade_date": "2026-07-06",
                    "title": "Evidence",
                    "uri": "",
                    "content_hash": "hash",
                    "relation": "supports",
                    "target_type": "research_case",
                    "target_id": case_id,
                    "allowed_metadata": {"digest_key": "digest:1"},
                    "payload": {"must_not": "leak"},
                    "metadata": {"must_not": "leak"},
                }
            ],
            "summary": {"claim_count": 1, "evidence_count": 1, "missing_or_partial_evidence_count": 3},
            "gap_reasons": ["missing_evidence", "partial_evidence", "incomplete_evidence_status"],
            "gap_summary": "missing evidence signal found; partial evidence signal found; evidence status is partial",
            "review_status": "request_more_evidence",
            "latest_review_action": {
                "review_action_id": "review_action:abc",
                "case_id": case_id,
                "trade_date": "2026-07-06",
                "asset_id": "CN:SZ:000001",
                "action_type": "request_more_evidence",
                "gap_reasons": ["missing_evidence"],
                "reviewer": "operator",
                "comment": "需要补证",
                "created_at": "2026-07-08T10:00:00+08:00",
                "source_context": {"from": "home_cockpit_gap_detail"},
                "metadata": {"must_not": "leak"},
            },
            "review_actions": [
                {
                    "review_action_id": "review_action:abc",
                    "case_id": case_id,
                    "trade_date": "2026-07-06",
                    "asset_id": "CN:SZ:000001",
                    "action_type": "request_more_evidence",
                    "gap_reasons": ["missing_evidence"],
                    "reviewer": "operator",
                    "comment": "需要补证",
                    "created_at": "2026-07-08T10:00:00+08:00",
                    "source_context": {"from": "home_cockpit_gap_detail"},
                    "payload": {"must_not": "leak"},
                }
            ],
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/research/cases/research_case:abc")

    assert response.status_code == 200
    payload = response.json()
    assert payload["case"]["case_id"] == "research_case:abc"
    assert payload["case"]["source_type"] == "review_item_snapshot"
    assert payload["claims"][0]["source_id"] == "review_item_snapshot:abc"
    assert payload["evidence"][0]["allowed_metadata"] == {"digest_key": "digest:1"}
    assert payload["summary"]["missing_or_partial_evidence_count"] == 3
    assert payload["gap_reasons"] == ["missing_evidence", "partial_evidence", "incomplete_evidence_status"]
    assert payload["gap_summary"] == "missing evidence signal found; partial evidence signal found; evidence status is partial"
    assert payload["review_status"] == "request_more_evidence"
    assert payload["latest_review_action"]["action_type"] == "request_more_evidence"
    assert payload["review_actions"][0]["comment"] == "需要补证"
    assert "payload" not in payload["case"]
    assert "metadata" not in payload["case"]
    assert "metadata" not in payload["claims"][0]
    assert "payload" not in payload["evidence"][0]
    assert "metadata" not in payload["latest_review_action"]
    assert "payload" not in payload["review_actions"][0]


def test_research_case_detail_route_returns_404(monkeypatch):
    monkeypatch.setattr(dashboard_app, "load_research_case_detail", lambda case_id, **kwargs: None)
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/research/cases/research_case:missing")

    assert response.status_code == 404


def test_list_research_cases_clamps_limit(monkeypatch):
    captured = {}

    class _Context:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_fetch_all(_conn, sql, params=None):
        captured["params"] = params
        return []

    monkeypatch.setattr(research_cases, "connect", lambda service: _Context())
    monkeypatch.setattr(research_cases, "fetch_all", fake_fetch_all)

    rows = research_cases.list_research_cases(limit=500, service="research")

    assert rows == []
    assert captured["params"][-1] == 100


def test_load_research_case_detail_clamps_child_limit_and_uses_whitelist(monkeypatch):
    captured = []

    class _Context:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_fetch_all(_conn, sql, params=None):
        captured.append(params)
        if "FROM research.research_case c" in sql:
            return [
                {
                    "case_id": "research_case:abc",
                    "trade_date": "2026-07-06",
                    "asset_id": "CN:SZ:000001",
                    "theme": "bank_reversal",
                    "title": "Bank reversal candidate",
                    "status": "open",
                    "priority": 30,
                    "source_type": "review_item_snapshot",
                    "source_id": "review_item_snapshot:abc",
                    "evidence_status": "partial",
                    "missing_evidence_count": 1,
                    "partial_evidence_count": 2,
                    "claim_count": 1,
                    "evidence_count": 1,
                    "metadata": {"must_not": "leak"},
                }
            ]
        if "FROM research.evidence_link l" in sql:
            return [
                {
                    "evidence_id": "evidence_artifact:1",
                    "source_type": "review_item_snapshot",
                    "source_id": "review_item_snapshot:abc",
                    "asset_id": "CN:SZ:000001",
                    "trade_date": "2026-07-06",
                    "title": "Evidence",
                    "uri": "",
                    "content_hash": "hash",
                    "relation": "supports",
                    "target_type": "research_case",
                    "target_id": "research_case:abc",
                    "evidence_metadata": {"digest_key": "digest:1", "raw": "hidden"},
                    "link_metadata": {"seed_version": "research_case_seed_v1", "internal": "hidden"},
                }
            ]
        if "FROM research.research_claim" in sql:
            return [
                {
                    "claim_id": "research_claim:1",
                    "claim_type": "risk",
                    "claim_text": "Needs evidence",
                    "confidence": None,
                    "status": "draft",
                    "metadata": {"source_type": "review_item_snapshot", "source_id": "review_item_snapshot:abc", "raw": "hidden"},
                }
            ]
        return []

    monkeypatch.setattr(research_cases, "connect", lambda service: _Context())
    monkeypatch.setattr(research_cases, "fetch_all", fake_fetch_all)

    detail = research_cases.load_research_case_detail("research_case:abc", limit=500, service="research")

    assert detail is not None
    assert captured[1][-1] == 100
    assert captured[2][-1] == 100
    assert detail["case"]["source_id"] == "review_item_snapshot:abc"
    assert detail["claims"][0]["source_type"] == "review_item_snapshot"
    assert detail["claims"][0]["source_id"] == "review_item_snapshot:abc"
    assert detail["evidence"][0]["allowed_metadata"] == {
        "digest_key": "digest:1",
        "seed_version": "research_case_seed_v1",
    }
    assert detail["summary"]["missing_or_partial_evidence_count"] == 3
    assert detail["gap_reasons"] == ["missing_evidence", "partial_evidence", "incomplete_evidence_status"]
    assert "missing evidence signal found" in detail["gap_summary"]
    assert "metadata" not in detail["case"]
