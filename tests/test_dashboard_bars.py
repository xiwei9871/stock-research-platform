import datetime as dt

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


def test_load_daily_bars_normalizes_tushare_units(monkeypatch):
    def fake_connect(service):
        return FakeConnect()

    def fake_fetch_all(conn, sql, params):
        return [
            {
                "time": "2026-06-18",
                "open": 10.74,
                "high": 10.77,
                "low": 10.52,
                "close": 10.52,
                "volume": 1426893.16,
                "amount": 1511009.56495,
                "source": "derived:tushare_raw_latest_factor",
            }
        ]

    monkeypatch.setattr(bars, "connect", fake_connect)
    monkeypatch.setattr(bars, "fetch_all", fake_fetch_all)

    result = bars.load_daily_bars("CN:SZ:000001", "2026-06-18", "2026-06-18", "qfq")

    assert result[0]["volume"] == 142689316.0
    assert result[0]["amount"] == 1511009564.95


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


def test_normalize_resolution_accepts_weekly_and_monthly_aliases():
    assert bars.normalize_resolution("1W") == "1W"
    assert bars.normalize_resolution("weekly") == "1W"
    assert bars.normalize_resolution("1M") == "1M"
    assert bars.normalize_resolution("monthly") == "1M"


def test_load_bars_aggregates_daily_rows_to_weekly(monkeypatch):
    captured = {}

    def fake_load_daily_bars(asset_id, start_date, end_date, adjust_type, service):
        captured["daily"] = [asset_id, start_date, end_date, adjust_type, service]
        return [
            {"time": "2026-06-01", "open": 10, "high": 11, "low": 9.8, "close": 10.5, "volume": 100, "amount": 1000},
            {"time": "2026-06-02", "open": 10.5, "high": 12, "low": 10.2, "close": 11.5, "volume": 120, "amount": 1300},
            {"time": "2026-06-05", "open": 11.5, "high": 12.4, "low": 11.0, "close": 12.1, "volume": 140, "amount": 1700},
            {"time": "2026-06-08", "open": 12.1, "high": 12.3, "low": 11.7, "close": 11.9, "volume": 90, "amount": 1100},
        ]

    monkeypatch.setattr(bars, "load_daily_bars", fake_load_daily_bars)

    result = bars.load_bars(
        asset_id="000001.SZ",
        start_date="2026-06-01",
        end_date="2026-06-08",
        resolution="1W",
        adjust_type="qfq",
        service="test",
    )

    assert captured["daily"] == ["000001.SZ", "2026-06-01", "2026-06-08", "qfq", "test"]
    assert result == [
        {
            "time": "2026-06-05",
            "open": 10.0,
            "high": 12.4,
            "low": 9.8,
            "close": 12.1,
            "volume": 360.0,
            "amount": 4000.0,
        },
        {
            "time": "2026-06-08",
            "open": 12.1,
            "high": 12.3,
            "low": 11.7,
            "close": 11.9,
            "volume": 90.0,
            "amount": 1100.0,
        },
    ]


def test_load_bars_aggregates_daily_rows_to_monthly(monkeypatch):
    def fake_load_daily_bars(asset_id, start_date, end_date, adjust_type, service):
        return [
            {"time": "2026-05-29", "open": 9, "high": 10, "low": 8.8, "close": 9.8, "volume": 80, "amount": 700},
            {"time": "2026-06-01", "open": 10, "high": 11, "low": 9.7, "close": 10.6, "volume": 100, "amount": 1000},
            {"time": "2026-06-30", "open": 10.6, "high": 12.5, "low": 10.1, "close": 12.2, "volume": 160, "amount": 2000},
        ]

    monkeypatch.setattr(bars, "load_daily_bars", fake_load_daily_bars)

    result = bars.load_bars(
        asset_id="000001.SZ",
        start_date="2026-05-01",
        end_date="2026-06-30",
        resolution="monthly",
        adjust_type="qfq",
    )

    assert [row["time"] for row in result] == ["2026-05-29", "2026-06-30"]
    assert result[1] == {
        "time": "2026-06-30",
        "open": 10.0,
        "high": 12.5,
        "low": 9.7,
        "close": 12.2,
        "volume": 260.0,
        "amount": 3000.0,
    }


def test_load_bars_uses_earliest_daily_bar_for_default_daily_window(monkeypatch):
    captured = {}

    def fake_earliest_daily_bar_date(asset_id, adjust_type, service):
        captured["earliest"] = [asset_id, adjust_type, service]
        return "1991-04-03"

    def fake_load_daily_bars(asset_id, start_date, end_date, adjust_type, service):
        captured["daily"] = [asset_id, start_date, end_date, adjust_type, service]
        return []

    monkeypatch.setattr(bars, "earliest_daily_bar_date", fake_earliest_daily_bar_date)
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
    assert captured["earliest"] == ["000001.SZ", "qfq", "test"]
    assert captured["daily"] == ["000001.SZ", "1991-04-03", "2026-05-29", "qfq", "test"]


def test_load_bars_keeps_full_default_weekly_history_after_aggregation(monkeypatch):
    captured = {}
    first_monday = dt.date(2020, 1, 6)

    def fake_earliest_daily_bar_date(asset_id, adjust_type, service):
        captured["earliest"] = [asset_id, adjust_type, service]
        return "2020-01-06"

    def fake_load_daily_bars(asset_id, start_date, end_date, adjust_type, service):
        captured["daily"] = [asset_id, start_date, end_date, adjust_type, service]
        return [
            {
                "time": (first_monday + dt.timedelta(days=7 * index)).isoformat(),
                "open": index,
                "high": index + 1,
                "low": index - 1,
                "close": index + 0.5,
                "volume": index + 100,
                "amount": index + 1000,
            }
            for index in range(260)
        ]

    monkeypatch.setattr(bars, "earliest_daily_bar_date", fake_earliest_daily_bar_date)
    monkeypatch.setattr(bars, "load_daily_bars", fake_load_daily_bars)

    result = bars.load_bars(
        asset_id="000001.SZ",
        start_date=None,
        end_date="2026-07-01",
        resolution="1W",
        adjust_type="qfq",
        service="test",
    )

    assert captured["earliest"] == ["000001.SZ", "qfq", "test"]
    assert captured["daily"] == ["000001.SZ", "2020-01-06", "2026-07-01", "qfq", "test"]
    assert result == bars.aggregate_daily_bars(fake_load_daily_bars("", "", "", "", ""), "1W")
