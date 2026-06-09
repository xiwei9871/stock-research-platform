from stock_research.dashboard import bars


class FakeConnection:
    pass


class FakeConnect:
    def __enter__(self):
        return FakeConnection()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_load_daily_bars_uses_market_daily_bar(monkeypatch):
    captured = {}

    def fake_connect(service):
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {
                "time": "2026-05-29",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "volume": 1000,
                "amount": 2000,
            }
        ]

    monkeypatch.setattr(bars, "connect", fake_connect)
    monkeypatch.setattr(bars, "fetch_all", fake_fetch_all)

    result = bars.load_daily_bars("000001.SZ", "2026-01-01", "2026-05-29", "qfq")

    assert "FROM market_daily_bar" in captured["sql"]
    assert captured["params"] == ["CN:SZ:000001", "2026-01-01", "2026-05-29", "qfq"]
    assert result[0]["time"] == "2026-05-29"


def test_load_minute_bars_uses_partitioned_minute_table(monkeypatch):
    captured = {}

    def fake_connect(service):
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return []

    monkeypatch.setattr(bars, "connect", fake_connect)
    monkeypatch.setattr(bars, "fetch_all", fake_fetch_all)

    result = bars.load_minute_bars(
        asset_id="000001.SZ",
        start_time="2026-05-29T09:30:00",
        end_time="2026-05-29T15:00:00",
        freq="5min",
        adjust_type="qfq",
    )

    assert "FROM market.stock_minute_bar" in captured["sql"]
    assert "AND source = %s" in captured["sql"]
    assert captured["params"] == [
        "CN:SZ:000001",
        "2026-05-29T09:30:00",
        "2026-05-29T15:00:00",
        "5min",
        "qfq",
        "baostock",
    ]
    assert result == []


def test_load_daily_bars_keeps_canonical_asset_id(monkeypatch):
    captured = {}

    def fake_connect(service):
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        captured["params"] = params
        return []

    monkeypatch.setattr(bars, "connect", fake_connect)
    monkeypatch.setattr(bars, "fetch_all", fake_fetch_all)

    result = bars.load_daily_bars("CN:SH:600000", "2026-06-01", "2026-06-08", "qfq")

    assert captured["params"] == ["CN:SH:600000", "2026-06-01", "2026-06-08", "qfq"]
    assert result == []
