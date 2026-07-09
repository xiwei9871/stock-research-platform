from psycopg import errors as psycopg_errors

from stock_research.dashboard.read_models import build_platform_summary_read_model


class _Context:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return False


def test_platform_summary_read_model_uses_fallback_when_no_materialized_rows(monkeypatch):
    calls = []

    def fake_fetch_all(_conn, sql, params=None):
        calls.append((sql, params))
        if "ops.dashboard_platform_summary_daily" in sql:
            return []
        if "max(trade_date) AS latest_market_date" in sql:
            return [{"latest_market_date": "2026-07-03", "market_asset_count": 5190}]
        if "max(trade_date) AS latest_score_date" in sql:
            return [{"latest_score_date": "2026-07-03", "score_asset_count": 5190}]
        if "count(DISTINCT factor_name)" in sql:
            return [{"factor_count": 2, "latest_factor_date": "2026-07-03"}]
        if "latest_market_monitor_date" in sql:
            return [{"latest_market_monitor_date": "2026-07-03"}]
        if "SELECT DISTINCT score_version" in sql:
            return [{"score_version": "manual_v1"}]
        if "ORDER BY rank" in sql:
            return [
                {
                    "trade_date": "2026-07-03",
                    "asset_id": "000001.SZ",
                    "rank": 1,
                    "score_total": 99.0,
                    "score_version": "manual_v1",
                    "score_components": {},
                }
            ]
        return []

    monkeypatch.setattr("stock_research.dashboard.read_models.fetch_all", fake_fetch_all)
    monkeypatch.setattr("stock_research.dashboard.read_models.connect", lambda _service: _Context())

    payload = build_platform_summary_read_model(score_version="manual_v1", top_n=5, service="research")

    assert payload["latest_market_date"] == "2026-07-03"
    assert payload["latest_score_date"] == "2026-07-03"
    assert payload["score_versions"] == ["manual_v1"]
    assert payload["topn_preview"][0]["asset_id"] == "000001.SZ"
    assert payload["source"] == "base_table_fallback"
    assert any("ops.dashboard_platform_summary_daily" in sql for sql, _params in calls)


def test_platform_summary_read_model_uses_fallback_when_materialized_schema_missing(monkeypatch):
    def fake_fetch_all(_conn, sql, params=None):
        if "ops.dashboard_platform_summary_daily" in sql:
            raise psycopg_errors.InvalidSchemaName("missing schema")
        if "max(trade_date) AS latest_market_date" in sql:
            return [{"latest_market_date": "2026-07-06", "market_asset_count": 5191}]
        if "max(trade_date) AS latest_score_date" in sql:
            return [{"latest_score_date": "2026-07-06", "score_asset_count": 5191}]
        if "count(DISTINCT factor_name)" in sql:
            return [{"factor_count": 38, "latest_factor_date": "2026-07-06"}]
        if "latest_market_monitor_date" in sql:
            return [{"latest_market_monitor_date": "2026-07-06"}]
        if "SELECT DISTINCT score_version" in sql:
            return [{"score_version": "manual_v1"}]
        if "ORDER BY rank" in sql:
            return []
        return []

    monkeypatch.setattr("stock_research.dashboard.read_models.fetch_all", fake_fetch_all)
    monkeypatch.setattr("stock_research.dashboard.read_models.connect", lambda _service: _Context())

    payload = build_platform_summary_read_model(score_version="manual_v1", top_n=5, service="research")

    assert payload["latest_market_date"] == "2026-07-06"
    assert payload["source"] == "base_table_fallback"


def test_platform_summary_read_model_uses_materialized_row_when_available(monkeypatch):
    def fake_fetch_all(_conn, sql, params=None):
        if "ops.dashboard_platform_summary_daily" in sql:
            return [
                {
                    "latest_market_date": "2026-07-04",
                    "latest_market_monitor_date": "2026-07-04",
                    "latest_score_date": "2026-07-04",
                    "latest_factor_date": "2026-07-04",
                    "market_asset_count": 5200,
                    "score_asset_count": 5200,
                    "factor_count": 3,
                    "score_versions": ["manual_v1", "manual_v2"],
                    "topn_preview": [{"asset_id": "000002.SZ", "rank": 1}],
                }
            ]
        raise AssertionError(sql)

    monkeypatch.setattr("stock_research.dashboard.read_models.fetch_all", fake_fetch_all)
    monkeypatch.setattr("stock_research.dashboard.read_models.connect", lambda _service: _Context())

    payload = build_platform_summary_read_model(score_version="manual_v1", top_n=5, service="research")

    assert payload["latest_market_date"] == "2026-07-04"
    assert payload["source"] == "materialized_view"
    assert payload["topn_preview"] == [{"asset_id": "000002.SZ", "rank": 1}]
