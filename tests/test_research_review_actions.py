import pytest

from stock_research import research_objects
from stock_research import research_review_actions


class _Cursor:
    def __init__(self, captured):
        self.captured = captured

    def execute(self, sql, params=None):
        self.captured.append((sql, params))


class _Conn:
    def __init__(self, captured):
        self.captured = captured

    def cursor(self):
        return self

    def __enter__(self):
        return _Cursor(self.captured)

    def __exit__(self, exc_type, exc, tb):
        return False


class _Ctx:
    def __init__(self, captured):
        self.captured = captured

    def __enter__(self):
        return _Conn(self.captured)

    def __exit__(self, exc_type, exc, tb):
        return False


def test_research_schema_contains_review_action_table():
    sql = research_objects.RESEARCH_OBJECTS_SQL

    assert "CREATE TABLE IF NOT EXISTS research.review_action" in sql
    assert "review_action_id text PRIMARY KEY" in sql
    assert "action_type text NOT NULL" in sql
    assert "auto_trade" not in sql


def test_record_review_action_writes_append_only_sql(monkeypatch):
    captured = []
    monkeypatch.setattr(research_review_actions, "connect", lambda service: _Ctx(captured))

    action_id = research_review_actions.record_review_action(
        {
            "case_id": "research_case:abc",
            "trade_date": "2026-07-03",
            "asset_id": "CN:SZ:000001",
            "action_type": "request_more_evidence",
            "gap_reasons": ["missing_evidence"],
            "reviewer": "operator",
            "comment": "需要补充公告证据",
            "source_context": {"from": "home_cockpit_gap_detail", "raw": "hidden"},
        },
        service="research",
    )

    assert action_id.startswith("review_action:")
    sql, params = captured[0]
    assert "INSERT INTO research.review_action" in sql
    assert "ON CONFLICT" not in sql
    assert params["case_id"] == "research_case:abc"
    assert params["action_type"] == "request_more_evidence"
    assert "home_cockpit_gap_detail" in params["source_context"]
    assert "raw" not in params["source_context"]


def test_record_review_action_rejects_invalid_action_type():
    with pytest.raises(ValueError, match="invalid_review_action_type"):
        research_review_actions.record_review_action(
            {"case_id": "research_case:abc", "action_type": "publish"},
            service="research",
        )


def test_record_review_action_rejects_auto_trade_payload():
    with pytest.raises(ValueError, match="review_action_forbidden_field"):
        research_review_actions.record_review_action(
            {
                "case_id": "research_case:abc",
                "action_type": "mark_reviewed",
                "auto_trade_enabled": True,
            },
            service="research",
        )


def test_review_action_read_model_whitelists_fields():
    item = research_review_actions.review_action_read_model(
        {
            "review_action_id": "review_action:abc",
            "case_id": "research_case:abc",
            "trade_date": "2026-07-03",
            "asset_id": "CN:SZ:000001",
            "action_type": "defer",
            "gap_reasons": ["partial_evidence"],
            "reviewer": "operator",
            "comment": "明日处理",
            "created_at": "2026-07-08T10:00:00+08:00",
            "source_context": {"from": "home_cockpit_gap_detail", "raw": "hidden"},
            "metadata": {"must_not": "leak"},
            "payload": {"must_not": "leak"},
        }
    )

    assert item["action_type"] == "defer"
    assert item["source_context"] == {"from": "home_cockpit_gap_detail"}
    assert "metadata" not in item
    assert "payload" not in item
