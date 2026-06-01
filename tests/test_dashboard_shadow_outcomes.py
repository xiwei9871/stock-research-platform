from stock_research.dashboard import shadow_outcomes


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_shadow_outcomes_summary_returns_read_only_rows(monkeypatch):
    captured = {}

    def fake_connect(service):
        captured["service"] = service
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "shadow_outcome_id": "operator_shadow_outcome:p13:001",
                "run_id": "p13-shadow-outcomes-2026-07-31",
                "shadow_candidate_id": "p12-shadow:001",
                "source_p12_shadow_run_id": "p12-shadow-watchlist-2026-06-30",
                "replay_result_id": "p11-replay:001",
                "source_p11_replay_run_id": "p11-replay-run-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "candidate_date": "2026-06-30",
                "asset_id": "000001.SZ",
                "stock_code": "000001",
                "stock_name": "Ping An Bank",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "outcome_status": "complete",
                "available_future_bars": 20,
                "base_trade_date": "2026-06-30",
                "base_close": 10.0,
                "forward_returns": {"5": 0.5},
                "max_high_returns": {"5": 0.6},
                "max_low_drawdowns": {"5": -0.1},
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(shadow_outcomes, "connect", fake_connect)
    monkeypatch.setattr(shadow_outcomes, "fetch_all", fake_fetch_all)

    result = shadow_outcomes.load_shadow_outcomes_summary(
        start_date="2026-06-01",
        end_date="2026-07-31",
        outcome_status="complete",
        limit=10,
        service="stock_research_test",
    )

    assert "FROM ops.operator_shadow_watchlist_outcome_candidate" in captured["sql"]
    assert "outcome_status = %s" in captured["sql"]
    assert "ORDER BY candidate_date DESC" in captured["sql"]
    assert captured["params"] == ["2026-06-01", "2026-07-31", "complete", 10]
    assert captured["service"] == "stock_research_test"
    assert result[0]["shadow_candidate_id"] == "p12-shadow:001"
    assert result[0]["forward_returns"] == {"5": 0.5}
    assert result[0]["production_watchlist_enabled"] is False


def test_load_shadow_outcomes_summary_normalizes_json_metric_maps(monkeypatch):
    def fake_connect(service):
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        return [
            {
                "shadow_outcome_id": "operator_shadow_outcome:p13:001",
                "run_id": "p13-shadow-outcomes-2026-07-31",
                "shadow_candidate_id": "p12-shadow:001",
                "source_p12_shadow_run_id": "p12-shadow-watchlist-2026-06-30",
                "replay_result_id": "p11-replay:001",
                "source_p11_replay_run_id": "p11-replay-run-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "candidate_date": "2026-06-30",
                "asset_id": "000001.SZ",
                "stock_code": "000001",
                "stock_name": "Ping An Bank",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "outcome_status": "complete",
                "available_future_bars": 20,
                "base_trade_date": "2026-06-30",
                "base_close": 10.0,
                "forward_returns": '{"5": "0.5", "20": "bad", "60": null}',
                "max_high_returns": {"5": "0.6", 20: None},
                "max_low_drawdowns": ["not", "a", "map"],
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(shadow_outcomes, "connect", fake_connect)
    monkeypatch.setattr(shadow_outcomes, "fetch_all", fake_fetch_all)

    result = shadow_outcomes.load_shadow_outcomes_summary(
        start_date="2026-06-01",
        end_date="2026-07-31",
    )

    assert result[0]["forward_returns"] == {"5": 0.5, "20": None, "60": None}
    assert result[0]["max_high_returns"] == {"5": 0.6, "20": None}
    assert result[0]["max_low_drawdowns"] == {}
