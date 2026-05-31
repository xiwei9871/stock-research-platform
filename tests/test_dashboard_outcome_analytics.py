from stock_research.dashboard import outcome_analytics


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_outcome_analytics_summary_returns_read_only_groups(monkeypatch):
    captured = {}

    def fake_connect(service):
        captured["service"] = service
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "run_id": "p9-outcome-analytics-2026-05-01-2026-06-30",
                "review_start_date": "2026-05-01",
                "review_end_date": "2026-06-30",
                "analytics_level": "decision_label",
                "group_value": "candidate",
                "sample_count": 2,
                "complete_count": 2,
                "insufficient_data_count": 0,
                "follow_up_required_rate": 0.5,
                "horizon_metrics": {
                    "5": {
                        "forward_return_mean": 0.15,
                        "forward_win_rate": 1.0,
                        "max_low_drawdown_worst": -0.08,
                    }
                },
                "analytics_artifact_path": "outputs/p9/operator_decision_outcome_analytics.json",
            }
        ]

    monkeypatch.setattr(outcome_analytics, "connect", fake_connect)
    monkeypatch.setattr(outcome_analytics, "fetch_all", fake_fetch_all)

    result = outcome_analytics.load_outcome_analytics_summary(
        start_date="2026-05-01",
        end_date="2026-06-30",
        review_session_id="morning-review",
        limit=10,
        service="stock_research_test",
    )

    assert "FROM ops.operator_decision_outcome_analytics_group" in captured["sql"]
    assert "analytics_level IN ('decision_label', 'source_context')" in captured["sql"]
    assert "review_session_id = %s" in captured["sql"]
    assert "ORDER BY review_end_date DESC" in captured["sql"]
    assert captured["params"] == ["2026-05-01", "2026-06-30", "morning-review", 10]
    assert captured["service"] == "stock_research_test"
    assert result == [
        {
            "run_id": "p9-outcome-analytics-2026-05-01-2026-06-30",
            "review_start_date": "2026-05-01",
            "review_end_date": "2026-06-30",
            "analytics_level": "decision_label",
            "group_value": "candidate",
            "sample_count": 2,
            "complete_count": 2,
            "insufficient_data_count": 0,
            "follow_up_required_rate": 0.5,
            "horizon_metrics": {
                "5": {
                    "forward_return_mean": 0.15,
                    "forward_win_rate": 1.0,
                    "max_low_drawdown_worst": -0.08,
                }
            },
            "analytics_artifact_path": "outputs/p9/operator_decision_outcome_analytics.json",
            "manual_review_required": True,
            "auto_trade_enabled": False,
        }
    ]


def test_load_outcome_analytics_summary_without_session_filter(monkeypatch):
    captured = {}

    monkeypatch.setattr(outcome_analytics, "connect", lambda service: FakeConnect())

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return []

    monkeypatch.setattr(outcome_analytics, "fetch_all", fake_fetch_all)

    result = outcome_analytics.load_outcome_analytics_summary(
        start_date="2026-05-01",
        end_date="2026-06-30",
        limit=5,
        service="stock_research_test",
    )

    assert result == []
    assert "review_session_id = %s" not in captured["sql"]
    assert captured["params"] == ["2026-05-01", "2026-06-30", 5]
