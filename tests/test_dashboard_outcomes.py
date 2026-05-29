from stock_research.dashboard import outcomes


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_asset_outcome_history_returns_read_only_rows(monkeypatch):
    captured = {}

    def fake_connect(service):
        captured["service"] = service
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "outcome_event_id": "operator_decision_outcome:p8:abc",
                "run_id": "p8-outcome-2026-05-01-2026-05-30",
                "decision_event_id": "operator_decision:morning-review:0:abc",
                "review_session_id": "morning-review",
                "review_date": "2026-05-30",
                "asset_id": "000001.SZ",
                "stock_code": "000001.SZ",
                "stock_name": "Alpha",
                "decision_label": "candidate",
                "source_context": "dashboard_topn",
                "outcome_status": "complete",
                "available_future_bars": 20,
                "base_trade_date": "2026-05-30",
                "base_close": 10.0,
                "forward_returns": {"1": 0.1, "5": 0.2},
                "max_high_returns": {"1": 0.12, "5": 0.25},
                "max_low_drawdowns": {"1": 0.0, "5": -0.04},
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "source_artifact_path": "outputs/p7/operator_decision_journal.json",
                "outcome_artifact_path": "outputs/p8/operator_decision_outcome_review.json",
            }
        ]

    monkeypatch.setattr(outcomes, "connect", fake_connect)
    monkeypatch.setattr(outcomes, "fetch_all", fake_fetch_all)

    result = outcomes.load_asset_outcome_history(
        "000001.SZ",
        start_date="2026-05-01",
        end_date="2026-05-30",
        review_session_id="morning-review",
        limit=10,
        service="stock_research_test",
    )

    assert "FROM ops.operator_decision_outcome_event" in captured["sql"]
    assert "review_session_id = %s" in captured["sql"]
    assert "ORDER BY review_date DESC" in captured["sql"]
    assert captured["params"] == ["000001.SZ", "2026-05-01", "2026-05-30", "morning-review", 10]
    assert captured["service"] == "stock_research_test"
    assert result == [
        {
            "outcome_event_id": "operator_decision_outcome:p8:abc",
            "run_id": "p8-outcome-2026-05-01-2026-05-30",
            "decision_event_id": "operator_decision:morning-review:0:abc",
            "review_session_id": "morning-review",
            "review_date": "2026-05-30",
            "asset_id": "000001.SZ",
            "stock_code": "000001.SZ",
            "stock_name": "Alpha",
            "decision_label": "candidate",
            "source_context": "dashboard_topn",
            "outcome_status": "complete",
            "available_future_bars": 20,
            "base_trade_date": "2026-05-30",
            "base_close": 10.0,
            "forward_returns": {"1": 0.1, "5": 0.2},
            "max_high_returns": {"1": 0.12, "5": 0.25},
            "max_low_drawdowns": {"1": 0.0, "5": -0.04},
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "source_artifact_path": "outputs/p7/operator_decision_journal.json",
            "outcome_artifact_path": "outputs/p8/operator_decision_outcome_review.json",
        }
    ]


def test_load_asset_outcome_history_without_session_filter(monkeypatch):
    captured = {}

    monkeypatch.setattr(outcomes, "connect", lambda service: FakeConnect())

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return []

    monkeypatch.setattr(outcomes, "fetch_all", fake_fetch_all)

    result = outcomes.load_asset_outcome_history(
        "000001.SZ",
        start_date="2026-05-01",
        end_date="2026-05-30",
        limit=5,
        service="stock_research_test",
    )

    assert result == []
    assert "review_session_id = %s" not in captured["sql"]
    assert captured["params"] == ["000001.SZ", "2026-05-01", "2026-05-30", 5]
