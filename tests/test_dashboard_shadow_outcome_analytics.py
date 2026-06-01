from psycopg import errors as psycopg_errors

from stock_research.dashboard import shadow_outcome_analytics


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_shadow_outcome_analytics_summary_returns_read_only_rows(monkeypatch):
    captured = {}

    def fake_connect(service):
        captured["service"] = service
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "analytics_group_id": "operator_shadow_outcome_analytics:trend-ready",
                "run_id": "p14-shadow-outcome-analytics-2026-06-30-2026-08-29",
                "review_start_date": "2026-06-30",
                "review_end_date": "2026-08-29",
                "group_key": "trend_shadow|shadow_ready",
                "shadow_layer": "trend_shadow",
                "shadow_status": "shadow_ready",
                "sample_count": 2,
                "complete_count": 2,
                "insufficient_data_count": 0,
                "source_p12_shadow_run_count": 1,
                "source_p11_replay_run_count": 1,
                "source_p10_proposal_run_count": 1,
                "source_p9_analytics_run_count": 1,
                "horizon_metrics": {"20": {"forward_return_mean": 0.12, "forward_win_rate": 1.0}},
                "analytics_artifact_path": "outputs/p14/analytics.json",
                "manual_review_required": False,
                "auto_trade_enabled": True,
                "production_watchlist_enabled": True,
                "production_write_enabled": True,
            }
        ]

    monkeypatch.setattr(shadow_outcome_analytics, "connect", fake_connect)
    monkeypatch.setattr(shadow_outcome_analytics, "fetch_all", fake_fetch_all)

    result = shadow_outcome_analytics.load_shadow_outcome_analytics_summary(
        start_date="2026-06-01",
        end_date="2026-08-31",
        limit=10,
        service="stock_research_test",
    )

    assert "FROM ops.operator_shadow_watchlist_outcome_analytics_group" in captured["sql"]
    assert "review_end_date BETWEEN %s AND %s" in captured["sql"]
    assert "ORDER BY review_end_date DESC, sample_count DESC, group_key" in captured["sql"]
    assert captured["params"] == ["2026-06-01", "2026-08-31", 10]
    assert captured["service"] == "stock_research_test"
    assert result[0]["analytics_group_id"] == "operator_shadow_outcome_analytics:trend-ready"
    assert result[0]["group_key"] == "trend_shadow|shadow_ready"
    assert result[0]["horizon_metrics"]["20"]["forward_return_mean"] == 0.12
    assert result[0]["manual_review_required"] is True
    assert result[0]["auto_trade_enabled"] is False
    assert result[0]["production_watchlist_enabled"] is False
    assert result[0]["production_write_enabled"] is False


def test_load_shadow_outcome_analytics_summary_normalizes_json_metrics(monkeypatch):
    def fake_fetch_all(conn, sql, params):
        return [
            {
                "analytics_group_id": "operator_shadow_outcome_analytics:risk-observe",
                "run_id": "p14-shadow-outcome-analytics-2026-06-30-2026-08-29",
                "review_start_date": "2026-06-30",
                "review_end_date": "2026-08-29",
                "group_key": "risk_shadow|shadow_observe",
                "shadow_layer": "risk_shadow",
                "shadow_status": "shadow_observe",
                "sample_count": 3,
                "complete_count": 1,
                "insufficient_data_count": 2,
                "source_p12_shadow_run_count": 1,
                "source_p11_replay_run_count": 1,
                "source_p10_proposal_run_count": 1,
                "source_p9_analytics_run_count": 1,
                "horizon_metrics": (
                    '{"20":{"forward_return_mean":"0.08","forward_win_rate":"bad",'
                    '"max_low_drawdown_worst": null, "nan_metric": NaN}}'
                ),
                "analytics_artifact_path": "outputs/p14/analytics.json",
            }
        ]

    monkeypatch.setattr(shadow_outcome_analytics, "connect", lambda service: FakeConnect())
    monkeypatch.setattr(shadow_outcome_analytics, "fetch_all", fake_fetch_all)

    result = shadow_outcome_analytics.load_shadow_outcome_analytics_summary(
        start_date="2026-06-01",
        end_date="2026-08-31",
    )

    assert result[0]["horizon_metrics"]["20"] == {
        "forward_return_mean": 0.08,
        "forward_win_rate": None,
        "max_low_drawdown_worst": None,
        "nan_metric": None,
    }


def test_load_shadow_outcome_analytics_summary_returns_empty_when_table_missing(monkeypatch):
    def fake_fetch_all(conn, sql, params):
        raise psycopg_errors.UndefinedTable("missing P14 analytics table")

    monkeypatch.setattr(shadow_outcome_analytics, "connect", lambda service: FakeConnect())
    monkeypatch.setattr(shadow_outcome_analytics, "fetch_all", fake_fetch_all)

    assert (
        shadow_outcome_analytics.load_shadow_outcome_analytics_summary(
            start_date="2026-06-01",
            end_date="2026-08-31",
        )
        == []
    )


def test_load_shadow_outcome_analytics_summary_returns_empty_when_schema_missing(monkeypatch):
    def fake_fetch_all(conn, sql, params):
        raise psycopg_errors.InvalidSchemaName("missing ops schema")

    monkeypatch.setattr(shadow_outcome_analytics, "connect", lambda service: FakeConnect())
    monkeypatch.setattr(shadow_outcome_analytics, "fetch_all", fake_fetch_all)

    assert (
        shadow_outcome_analytics.load_shadow_outcome_analytics_summary(
            start_date="2026-06-01",
            end_date="2026-08-31",
        )
        == []
    )
