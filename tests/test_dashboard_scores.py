from stock_research.dashboard import scores


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_search_assets_limits_and_maps_rows(monkeypatch):
    captured = {}

    def fake_connect(service):
        captured["service"] = service
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "asset_id": "000001.SZ",
                "symbol": "000001",
                "name": "平安银行",
                "exchange": "SZ",
                "board": "main",
                "is_active": True,
            }
        ]

    monkeypatch.setattr(scores, "connect", fake_connect)
    monkeypatch.setattr(scores, "fetch_all", fake_fetch_all)

    result = scores.search_assets("平安", limit=5, service="stock_research")

    assert captured["params"] == ["%平安%", "%平安%", "%平安%", 5]
    assert result == [
        {
            "asset_id": "000001.SZ",
            "symbol": "000001",
            "name": "平安银行",
            "exchange": "SZ",
            "board": "main",
            "is_active": True,
        }
    ]


def test_load_top_scores_returns_ranked_rows(monkeypatch):
    def fake_connect(service):
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        return [
            {
                "trade_date": "2026-05-29",
                "asset_id": "000001.SZ",
                "rank": 1,
                "score_total": 91.2,
                "score_version": "manual_v1",
                "score_components": {"trend": 88},
            }
        ]

    monkeypatch.setattr(scores, "connect", fake_connect)
    monkeypatch.setattr(scores, "fetch_all", fake_fetch_all)

    result = scores.load_top_scores_for_dashboard("2026-05-29", "manual_v1", 20)

    assert result[0]["asset_id"] == "000001.SZ"
    assert result[0]["score_total"] == 91.2
