from stock_research.dashboard import shadow_watchlist


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_shadow_watchlist_summary_returns_read_only_rows(monkeypatch):
    captured = {}

    def fake_connect(service):
        captured["service"] = service
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "shadow_candidate_id": "p12-shadow:001",
                "run_id": "p12-shadow-watchlist-2026-06-30",
                "replay_result_id": "p11-replay:001",
                "source_p11_replay_run_id": "p11-replay-run-2026-06-30",
                "source_p10_proposal_run_id": "p10-proposals-2026-06-30",
                "source_p9_analytics_run_id": "p9-outcome-analytics-2026-05-01-2026-05-31",
                "candidate_date": "2026-06-30",
                "asset_id": "000001.SZ",
                "stock_code": "000001",
                "stock_name": "Ping An Bank",
                "shadow_layer": "trend_shadow",
                "candidate_reason": "Passed replay with acceptable drawdown.",
                "evidence_artifact_paths": ["outputs/p11/replay.json"],
                "metric_summary": {"win_rate": 0.75},
                "reviewer_id": "reviewer-a",
                "status": "shadow_ready",
                "review_notes": "Observe only.",
                "shadow_artifact_path": "outputs/p12/operator_shadow_watchlist_2026-06-30.json",
                "manual_review_required": True,
                "auto_trade_enabled": False,
                "production_watchlist_enabled": False,
                "production_write_enabled": False,
            }
        ]

    monkeypatch.setattr(shadow_watchlist, "connect", fake_connect)
    monkeypatch.setattr(shadow_watchlist, "fetch_all", fake_fetch_all)

    result = shadow_watchlist.load_shadow_watchlist_summary(
        start_date="2026-06-01",
        end_date="2026-06-30",
        status="shadow_ready",
        limit=10,
        service="stock_research_test",
    )

    assert "FROM ops.operator_shadow_watchlist_candidate" in captured["sql"]
    assert "status = %s" in captured["sql"]
    assert "ORDER BY candidate_date DESC" in captured["sql"]
    assert captured["params"] == ["2026-06-01", "2026-06-30", "shadow_ready", 10]
    assert captured["service"] == "stock_research_test"
    assert result[0]["shadow_candidate_id"] == "p12-shadow:001"
    assert result[0]["production_watchlist_enabled"] is False
