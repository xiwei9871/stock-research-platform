from stock_research.dashboard import decisions


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_asset_decision_history_returns_read_only_rows(monkeypatch):
    captured = {}

    def fake_connect(service):
        captured["service"] = service
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "review_date": "2026-05-30",
                "review_session_id": "morning-review",
                "event_id": "operator_decision:morning-review:0:abc",
                "asset_id": "000001.SZ",
                "stock_code": "000001.SZ",
                "stock_name": "Alpha",
                "decision_label": "candidate",
                "evidence_artifact_id": "dashboard:topn:2026-05-30",
                "evidence_path": "outputs/p6/topn.json",
                "source_context": "dashboard_topn",
                "requires_follow_up": True,
                "follow_up_note": "check next close strength",
                "notes": "strong score",
                "manual_review_required": True,
                "auto_trade_enabled": False,
            }
        ]

    monkeypatch.setattr(decisions, "connect", fake_connect)
    monkeypatch.setattr(decisions, "fetch_all", fake_fetch_all)

    result = decisions.load_asset_decision_history(
        "000001.SZ",
        start_date="2026-05-01",
        end_date="2026-05-30",
        limit=10,
        service="stock_research_test",
    )

    assert "FROM ops.operator_decision_event" in captured["sql"]
    assert "ORDER BY review_date DESC" in captured["sql"]
    assert captured["params"] == ["000001.SZ", "2026-05-01", "2026-05-30", 10]
    assert captured["service"] == "stock_research_test"
    assert result == [
        {
            "review_date": "2026-05-30",
            "review_session_id": "morning-review",
            "event_id": "operator_decision:morning-review:0:abc",
            "asset_id": "000001.SZ",
            "stock_code": "000001.SZ",
            "stock_name": "Alpha",
            "decision_label": "candidate",
            "evidence_artifact_id": "dashboard:topn:2026-05-30",
            "evidence_path": "outputs/p6/topn.json",
            "source_context": "dashboard_topn",
            "requires_follow_up": True,
            "follow_up_note": "check next close strength",
            "notes": "strong score",
            "manual_review_required": True,
            "auto_trade_enabled": False,
        }
    ]
