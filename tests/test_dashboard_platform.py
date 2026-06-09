from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import platform


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_platform_summary_combines_coverage_and_topn(monkeypatch):
    calls = []

    def fake_connect(service):
        return FakeConnect()

    def fake_fetch_all(conn, sql, params=None):
        calls.append(sql)
        if "max(trade_date) AS latest_market_date" in sql:
            return [{"latest_market_date": "2026-06-08", "market_asset_count": 5207}]
        if "max(trade_date) AS latest_score_date" in sql:
            return [{"latest_score_date": "2026-06-08", "score_asset_count": 5207}]
        if "count(DISTINCT factor_name)" in sql:
            return [{"factor_count": 43, "latest_factor_date": "2026-06-08"}]
        if "SELECT DISTINCT score_version" in sql:
            return [{"score_version": "manual_v1"}]
        if "FROM factor.stock_score_daily" in sql:
            return [
                {
                    "trade_date": "2026-06-08",
                    "asset_id": "CN:SZ:300951",
                    "rank": 1,
                    "score_total": 89.9,
                    "score_version": "manual_v1",
                    "score_components": {"ret_20_score": 97.4},
                }
            ]
        raise AssertionError(sql)

    monkeypatch.setattr(platform, "connect", fake_connect)
    monkeypatch.setattr(platform, "fetch_all", fake_fetch_all)

    result = platform.load_platform_summary()

    assert result["latest_market_date"] == "2026-06-08"
    assert result["latest_score_date"] == "2026-06-08"
    assert result["market_asset_count"] == 5207
    assert result["factor_count"] == 43
    assert result["score_versions"] == ["manual_v1"]
    assert result["topn_preview"][0]["asset_id"] == "CN:SZ:300951"


def test_platform_summary_route(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-06-08", "topn_preview": []},
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/platform/summary")

    assert response.status_code == 200
    assert response.json()["latest_market_date"] == "2026-06-08"
