import json

import pytest

from stock_research.operator_decision import write_service


class _Cursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))


class _Connection:
    def __init__(self):
        self.cursor_obj = _Cursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_obj


def _linked_context():
    return {
        "run_id": "eod-2026-06-12-local",
        "digest_key": "2026-06-12:manual_v1:000001.SZ",
        "review_item_snapshot_id": "review_item_snapshot:abc",
        "evidence_digest_snapshot_id": "evidence_digest_snapshot:def",
        "review_item_payload_hash": "review-hash",
        "evidence_digest_payload_hash": "digest-hash",
        "snapshot_linkage_status": "linked",
        "snapshot_linkage_warnings": [],
        "review_item_as_of": "2026-06-12T18:00:00+08:00",
        "evidence_as_of": "2026-06-12T18:01:00+08:00",
        "source_type": "score_topn",
        "source_name": "manual_v1_topn",
    }


def test_create_operator_decision_writes_linked_snapshot_context(monkeypatch):
    conn = _Connection()
    captured = {}
    monkeypatch.setattr(write_service, "connect", lambda service: conn)

    def fake_resolver(context, service="stock_research"):
        captured.update(context)
        return _linked_context()

    monkeypatch.setattr(write_service, "resolve_decision_snapshot_linkage", fake_resolver)

    result = write_service.create_operator_decision(
        {
            "asset_id": "000001.SZ",
            "stock_code": "000001.SZ",
            "stock_name": "Ping An Bank",
            "decision_date": "2026-06-12",
            "operator_action": "watch",
            "decision_status": "open",
            "operator_note": "observe after pullback",
            "run_id": "eod-2026-06-12-local",
            "digest_key": "2026-06-12:manual_v1:000001.SZ",
            "source_context": {"entry": "review_queue", "note_source": "dashboard"},
        },
        service="stock_research_test",
    )

    assert captured["run_id"] == "eod-2026-06-12-local"
    assert captured["digest_key"] == "2026-06-12:manual_v1:000001.SZ"
    assert result["operator_action"] == "watch"
    assert result["decision_label"] == "observe"
    assert result["snapshot_linkage_status"] == "linked"
    assert result["review_item_snapshot_id"] == "review_item_snapshot:abc"
    assert result["warnings"] == []
    session_sql, session_params = conn.cursor_obj.calls[0]
    event_sql, event_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO ops.operator_review_session" in session_sql
    assert session_params["review_session_id"] == "operator-decision-api-2026-06-12"
    assert "INSERT INTO ops.operator_decision_event" in event_sql
    assert event_params["asset_id"] == "000001.SZ"
    assert event_params["decision_label"] == "observe"
    assert event_params["requires_follow_up"] is False
    context = json.loads(event_params["source_context"])
    assert context["entry"] == "review_queue"
    assert context["operator_action"] == "watch"
    assert context["snapshot_linkage_status"] == "linked"
    assert context["review_item_payload_hash"] == "review-hash"


def test_create_operator_decision_uses_explicit_snapshot_ids(monkeypatch):
    conn = _Connection()
    captured = {}
    monkeypatch.setattr(write_service, "connect", lambda service: conn)

    def fake_resolver(context, service="stock_research"):
        captured.update(context)
        return {
            **_linked_context(),
            "review_item_snapshot_id": context["review_item_snapshot_id"],
            "evidence_digest_snapshot_id": context["evidence_digest_snapshot_id"],
        }

    monkeypatch.setattr(write_service, "resolve_decision_snapshot_linkage", fake_resolver)

    result = write_service.create_operator_decision(
        {
            "stock_code": "000001.SZ",
            "decision_date": "2026-06-12",
            "operator_action": "add_to_shadow",
            "review_item_snapshot_id": "review_item_snapshot:explicit",
            "evidence_digest_snapshot_id": "evidence_digest_snapshot:explicit",
        },
        service="stock_research_test",
    )

    assert captured["review_item_snapshot_id"] == "review_item_snapshot:explicit"
    assert captured["evidence_digest_snapshot_id"] == "evidence_digest_snapshot:explicit"
    assert result["asset_id"] == "000001.SZ"
    assert result["decision_label"] == "candidate"
    assert result["review_item_snapshot_id"] == "review_item_snapshot:explicit"


def test_create_operator_decision_missing_snapshot_is_nonblocking(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(write_service, "connect", lambda service: conn)
    monkeypatch.setattr(
        write_service,
        "resolve_decision_snapshot_linkage",
        lambda context, service="stock_research": {
            "run_id": "eod-2026-06-12-local",
            "digest_key": "bad-digest",
            "review_item_snapshot_id": "",
            "evidence_digest_snapshot_id": "",
            "review_item_payload_hash": "",
            "evidence_digest_payload_hash": "",
            "snapshot_linkage_status": "missing",
            "snapshot_linkage_warnings": ["No evidence_digest_snapshot found for run_id + digest_key"],
            "review_item_as_of": "",
            "evidence_as_of": "",
        },
    )

    result = write_service.create_operator_decision(
        {
            "asset_id": "000001.SZ",
            "decision_date": "2026-06-12",
            "operator_action": "note",
            "run_id": "eod-2026-06-12-local",
            "digest_key": "bad-digest",
            "source_context": "manual_note",
        },
        service="stock_research_test",
    )

    assert result["snapshot_linkage_status"] == "missing"
    assert result["warnings"] == ["No evidence_digest_snapshot found for run_id + digest_key"]
    _, event_params = conn.cursor_obj.calls[1]
    context = json.loads(event_params["source_context"])
    assert context["source_context_label"] == "manual_note"
    assert context["snapshot_linkage_status"] == "missing"


def test_create_operator_decision_source_context_merge_preserves_old_fields(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(write_service, "connect", lambda service: conn)
    monkeypatch.setattr(write_service, "resolve_decision_snapshot_linkage", lambda context, service="stock_research": _linked_context())

    write_service.create_operator_decision(
        {
            "asset_id": "000001.SZ",
            "decision_date": "2026-06-12",
            "operator_action": "follow_up",
            "follow_up_date": "2026-06-17",
            "source_context": {"custom": "keep", "run_id": "old-run"},
        },
        service="stock_research_test",
    )

    _, event_params = conn.cursor_obj.calls[1]
    context = json.loads(event_params["source_context"])
    assert context["custom"] == "keep"
    assert context["run_id"] == "eod-2026-06-12-local"
    assert context["operator_action"] == "follow_up"
    assert context["follow_up_date"] == "2026-06-17"
    assert event_params["requires_follow_up"] is True


def test_watch_decision_upserts_manual_review_watchlist_item(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(write_service, "connect", lambda service: conn)
    monkeypatch.setattr(write_service, "resolve_decision_snapshot_linkage", lambda context, service="stock_research": _linked_context())

    result = write_service.create_operator_decision(
        {
            "asset_id": "000001.SZ",
            "stock_code": "000001",
            "stock_name": "平安银行",
            "decision_date": "2026-06-12",
            "operator_action": "watch",
            "operator_note": "回踩十日线继续观察",
        },
        service="stock_research_test",
    )

    watchlist_sql, watchlist_params = conn.cursor_obj.calls[2]
    assert "INSERT INTO watchlist.watchlist_item" in watchlist_sql
    assert watchlist_params["watchlist_id"] == "manual_review"
    assert watchlist_params["asset_id"] == "000001.SZ"
    assert watchlist_params["stock_code"] == "000001"
    assert watchlist_params["stock_name"] == "平安银行"
    assert watchlist_params["active"] is True
    assert watchlist_params["note"] == "回踩十日线继续观察"
    assert watchlist_params["source"] == "operator_decision:watch"
    assert result["workflow_effects"] == [
        {
            "type": "watchlist_item",
            "status": "upserted",
            "watchlist_id": "manual_review",
            "asset_id": "000001.SZ",
        }
    ]


def test_close_decision_deactivates_manual_review_watchlist_item(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(write_service, "connect", lambda service: conn)
    monkeypatch.setattr(write_service, "resolve_decision_snapshot_linkage", lambda context, service="stock_research": _linked_context())

    result = write_service.create_operator_decision(
        {
            "asset_id": "000001.SZ",
            "stock_code": "000001",
            "stock_name": "平安银行",
            "decision_date": "2026-06-12",
            "operator_action": "close",
            "operator_note": "复盘链条结束",
        },
        service="stock_research_test",
    )

    watchlist_sql, watchlist_params = conn.cursor_obj.calls[2]
    assert "INSERT INTO watchlist.watchlist_item" in watchlist_sql
    assert watchlist_params["watchlist_id"] == "manual_review"
    assert watchlist_params["asset_id"] == "000001.SZ"
    assert watchlist_params["active"] is False
    assert watchlist_params["note"] == "复盘链条结束"
    assert watchlist_params["source"] == "operator_decision:close"
    assert result["workflow_effects"][0]["status"] == "deactivated"


def test_create_operator_decision_rejects_invalid_action():
    with pytest.raises(ValueError, match="invalid_operator_action"):
        write_service.create_operator_decision(
            {"asset_id": "000001.SZ", "decision_date": "2026-06-12", "operator_action": "buy"}
        )


def test_create_operator_decision_requires_asset_or_stock_code():
    with pytest.raises(ValueError, match="asset_id_or_stock_code_required"):
        write_service.create_operator_decision(
            {"decision_date": "2026-06-12", "operator_action": "watch"}
        )


def test_create_operator_decision_rejects_bad_dates():
    with pytest.raises(ValueError, match="invalid_decision_date"):
        write_service.create_operator_decision(
            {"asset_id": "000001.SZ", "decision_date": "20260612", "operator_action": "watch"}
        )
    with pytest.raises(ValueError, match="invalid_follow_up_date"):
        write_service.create_operator_decision(
            {
                "asset_id": "000001.SZ",
                "decision_date": "2026-06-12",
                "operator_action": "follow_up",
                "follow_up_date": "20260617",
            }
        )
