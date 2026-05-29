import json

import pytest

from stock_research.operator_decision.read_model import (
    import_decision_journal,
    load_decision_journal_read_model_rows,
)


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

    def cursor(self):
        return self.cursor_obj


class _Context:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def _journal_payload() -> dict:
    return {
        "review_date": "2026-05-30",
        "review_session_id": "morning-review",
        "reviewer_id": "operator",
        "source_artifact_root": "outputs",
        "status": "review_recorded",
        "decision_count": 2,
        "decision_label_counts": {"candidate": 1, "caution": 1},
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "issues": [],
        "items": [
            {
                "review_date": "2026-05-30",
                "review_session_id": "morning-review",
                "reviewer_id": "operator",
                "asset_id": "CN:SH:600001",
                "stock_code": "600001.SH",
                "stock_name": "Alpha",
                "decision_label": "candidate",
                "evidence_artifact_id": "dashboard:topn:2026-05-30",
                "evidence_path": "outputs/p6/topn.json",
                "source_context": "dashboard_topn",
                "requires_follow_up": True,
                "follow_up_note": "check next close strength",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "notes": "strong score",
            },
            {
                "review_date": "2026-05-30",
                "review_session_id": "morning-review",
                "reviewer_id": "operator",
                "asset_id": "CN:SZ:000001",
                "stock_code": "000001.SZ",
                "stock_name": "Beta",
                "decision_label": "caution",
                "evidence_artifact_id": "watchlist:2026-05-30",
                "evidence_path": "outputs/p5/watchlist.json",
                "source_context": "watchlist",
                "requires_follow_up": False,
                "follow_up_note": "",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "notes": "risk signal",
            },
        ],
    }


def test_load_decision_journal_read_model_rows_preserves_session_and_event_paths(tmp_path):
    json_path = tmp_path / "operator_decision_journal_2026-05-30_morning-review.json"
    json_path.write_text(json.dumps(_journal_payload()), encoding="utf-8")
    (tmp_path / "operator_decision_journal_2026-05-30_morning-review.csv").write_text(
        "asset_id\nCN:SH:600001\n",
        encoding="utf-8",
    )
    (tmp_path / "operator_decision_journal_2026-05-30_morning-review.md").write_text(
        "# Journal\n",
        encoding="utf-8",
    )

    rows = load_decision_journal_read_model_rows(json_path)

    assert rows["session"]["review_session_id"] == "morning-review"
    assert rows["session"]["review_date"] == "2026-05-30"
    assert rows["session"]["decision_count"] == 2
    assert rows["session"]["json_path"] == str(json_path)
    assert rows["session"]["csv_path"].endswith(".csv")
    assert rows["session"]["markdown_path"].endswith(".md")
    assert rows["events"][0]["asset_id"] == "CN:SH:600001"
    assert rows["events"][0]["decision_label"] == "candidate"
    assert rows["events"][0]["source_artifact_path"] == str(json_path)
    assert rows["events"][0]["requires_follow_up"] is True


def test_load_decision_journal_read_model_rows_rejects_unsafe_execution_fields(tmp_path):
    payload = _journal_payload()
    payload["items"][0]["order_id"] = "order-1"
    json_path = tmp_path / "operator_decision_journal_2026-05-30_morning-review.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="execution_field_not_allowed"):
        load_decision_journal_read_model_rows(json_path)


def test_import_decision_journal_upserts_session_and_events(monkeypatch, tmp_path):
    from stock_research.operator_decision import read_model

    json_path = tmp_path / "operator_decision_journal_2026-05-30_morning-review.json"
    json_path.write_text(json.dumps(_journal_payload()), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(read_model, "connect", lambda service: _Context(conn))

    result = import_decision_journal(json_path, service="stock_research_test")

    assert result["imported_count"] == 1
    assert result["session_ids"] == ["morning-review"]
    assert result["event_count"] == 2
    session_sql, session_params = conn.cursor_obj.calls[0]
    assert "INSERT INTO ops.operator_review_session" in session_sql
    assert "ON CONFLICT (review_session_id)" in session_sql
    assert session_params["review_session_id"] == "morning-review"
    assert session_params["decision_count"] == 2
    event_sql, event_params = conn.cursor_obj.calls[1]
    assert "INSERT INTO ops.operator_decision_event" in event_sql
    assert "ON CONFLICT (event_id)" in event_sql
    assert event_params["asset_id"] == "CN:SH:600001"
    assert event_params["decision_label"] == "candidate"


def test_import_decision_journal_accepts_directory(monkeypatch, tmp_path):
    from stock_research.operator_decision import read_model

    first = _journal_payload()
    second = {
        **_journal_payload(),
        "review_date": "2026-05-31",
        "review_session_id": "afternoon-review",
    }
    (tmp_path / "operator_decision_journal_2026-05-30_morning-review.json").write_text(
        json.dumps(first),
        encoding="utf-8",
    )
    (tmp_path / "operator_decision_journal_2026-05-31_afternoon-review.json").write_text(
        json.dumps(second),
        encoding="utf-8",
    )
    (tmp_path / "ignore_me.json").write_text(json.dumps(first), encoding="utf-8")
    conn = _Connection()
    monkeypatch.setattr(read_model, "connect", lambda service: _Context(conn))

    result = import_decision_journal(tmp_path, service="stock_research_test")

    assert result["imported_count"] == 2
    assert result["session_ids"] == ["morning-review", "afternoon-review"]
    assert result["event_count"] == 4
