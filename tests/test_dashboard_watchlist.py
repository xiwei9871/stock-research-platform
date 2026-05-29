from stock_research.dashboard import watchlist


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_watchlist_signals_maps_json_tags(monkeypatch):
    def fake_connect(service):
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        return [
            {
                "watchlist_id": "default",
                "trade_date": "2026-05-29",
                "asset_id": "000001.SZ",
                "stock_code": "000001",
                "stock_name": "平安银行",
                "priority": 10,
                "signal_score": 81.5,
                "primary_signal": "observe",
                "signal_tags": ["trend_ok"],
                "risk_tags": ["overheated"],
                "must_watch": True,
                "reason_json": {"score": 81.5},
            }
        ]

    monkeypatch.setattr(watchlist, "connect", fake_connect)
    monkeypatch.setattr(watchlist, "fetch_all", fake_fetch_all)

    result = watchlist.load_watchlist_signals_for_dashboard("default", "2026-05-29")

    assert result[0]["asset_id"] == "000001.SZ"
    assert result[0]["signal_tags"] == ["trend_ok"]
    assert result[0]["must_watch"] is True
