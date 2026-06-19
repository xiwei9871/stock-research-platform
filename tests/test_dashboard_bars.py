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
    assert captured["params"] == ["000001.SZ", "2026-01-01", "2026-05-29", "qfq"]
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
        "000001.SZ",
        "2026-05-29T09:30:00",
        "2026-05-29T15:00:00",
        "5min",
        "qfq",
        "baostock",
    ]
    assert result == []


def test_load_bars_aggregates_5min_rows_to_30m(monkeypatch):
    captured = {}

    def fake_load_minute_bars(asset_id, start_time, end_time, freq, adjust_type, source, service):
        captured["args"] = [asset_id, start_time, end_time, freq, adjust_type, source, service]
        return [
            {
                "time": "2026-05-29 09:35:00",
                "open": 10,
                "high": 10.5,
                "low": 9.8,
                "close": 10.2,
                "volume": 100,
                "amount": 1000,
            },
            {
                "time": "2026-05-29 09:40:00",
                "open": 10.2,
                "high": 10.8,
                "low": 10.1,
                "close": 10.7,
                "volume": 120,
                "amount": 1200,
            },
            {
                "time": "2026-05-29 10:00:00",
                "open": 10.7,
                "high": 11,
                "low": 10.6,
                "close": 10.9,
                "volume": 150,
                "amount": 1500,
            },
        ]

    monkeypatch.setattr(bars, "load_minute_bars", fake_load_minute_bars)

    result = bars.load_bars(
        asset_id="000001.SZ",
        start_date="2026-05-29",
        end_date="2026-05-29",
        resolution="30m",
        adjust_type="raw",
        source="akshare",
    )

    assert captured["args"] == [
        "000001.SZ",
        "2026-05-29 09:30:00",
        "2026-05-29 15:00:00",
        "5min",
        "raw",
        "akshare",
        "stock_research",
    ]
    assert result == [
        {
            "time": "2026-05-29 10:00:00",
            "open": 10.0,
            "high": 11.0,
            "low": 9.8,
            "close": 10.9,
            "volume": 370.0,
            "amount": 3700.0,
        }
    ]


def test_load_bars_uses_trading_calendar_for_default_window(monkeypatch):
    captured = {}

    def fake_recent_trade_date_window(*, end_date, trading_days, service):
        captured["calendar"] = [end_date, trading_days, service]
        return "2026-05-20", "2026-05-29"

    def fake_load_daily_bars(asset_id, start_date, end_date, adjust_type, service):
        captured["daily"] = [asset_id, start_date, end_date, adjust_type, service]
        return []

    monkeypatch.setattr(bars, "recent_trade_date_window", fake_recent_trade_date_window)
    monkeypatch.setattr(bars, "load_daily_bars", fake_load_daily_bars)

    result = bars.load_bars(
        asset_id="000001.SZ",
        start_date=None,
        end_date="2026-05-29",
        resolution="1D",
        adjust_type="qfq",
        service="test",
    )

    assert result == []
    assert captured["calendar"] == ["2026-05-29", 90, "test"]
    assert captured["daily"] == ["000001.SZ", "2026-05-20", "2026-05-29", "qfq", "test"]
