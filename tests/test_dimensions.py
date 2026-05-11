from stock_research import dimensions


class FakeConnection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.executed = []
        self.many = []


def fake_fetch_all(conn, sql, params=None):
    conn.executed.append((sql, params))
    return conn.rows


def fake_execute_many(conn, sql, rows):
    conn.many.append((sql, list(rows)))


def test_build_calendar_rows_expands_trade_dates_to_exchanges():
    rows = dimensions.build_calendar_rows(
        ["2024-01-02"],
        ["SH", "SZ"],
        source="derived:market_daily_bar",
        source_version="v1",
    )

    assert rows == [
        {
            "exchange": "SH",
            "trade_date": "2024-01-02",
            "is_open": True,
            "source": "derived:market_daily_bar",
            "source_version": "v1",
        },
        {
            "exchange": "SZ",
            "trade_date": "2024-01-02",
            "is_open": True,
            "source": "derived:market_daily_bar",
            "source_version": "v1",
        },
    ]


def test_upsert_trading_calendar_writes_rows(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(dimensions, "execute_many", fake_execute_many)

    count = dimensions.upsert_trading_calendar(
        conn,
        [
            {
                "exchange": "SH",
                "trade_date": "2024-01-02",
                "is_open": True,
                "source": "derived",
                "source_version": "v1",
            }
        ],
    )

    assert count == 1
    sql, rows = conn.many[0]
    assert "INSERT INTO market.trading_calendar" in sql
    assert "ON CONFLICT (exchange, trade_date, source_version)" in sql
    assert rows[0] == ("SH", "2024-01-02", True, "derived", "v1")


def test_build_lifecycle_rows_from_assets_creates_listed_and_delisted_events():
    rows = dimensions.build_lifecycle_rows_from_assets(
        [
            {
                "asset_id": "CN:SH:600000",
                "list_date": "1999-11-10",
                "delist_date": None,
            },
            {
                "asset_id": "CN:SZ:000001",
                "list_date": "1991-04-03",
                "delist_date": "2024-01-31",
            },
        ],
        source_version="core_asset_master_v1",
    )

    assert rows == [
        {
            "asset_id": "CN:SH:600000",
            "event_date": "1999-11-10",
            "event_type": "listed",
            "event_value": None,
            "source": "core.asset_master",
            "source_version": "core_asset_master_v1",
        },
        {
            "asset_id": "CN:SZ:000001",
            "event_date": "1991-04-03",
            "event_type": "listed",
            "event_value": None,
            "source": "core.asset_master",
            "source_version": "core_asset_master_v1",
        },
        {
            "asset_id": "CN:SZ:000001",
            "event_date": "2024-01-31",
            "event_type": "delisted",
            "event_value": None,
            "source": "core.asset_master",
            "source_version": "core_asset_master_v1",
        },
    ]


def test_upsert_asset_lifecycle_events_writes_rows(monkeypatch):
    conn = FakeConnection()
    monkeypatch.setattr(dimensions, "execute_many", fake_execute_many)

    count = dimensions.upsert_asset_lifecycle_events(
        conn,
        [
            {
                "asset_id": "CN:SH:600000",
                "event_date": "1999-11-10",
                "event_type": "listed",
                "event_value": None,
                "source": "core.asset_master",
                "source_version": "v1",
            }
        ],
    )

    assert count == 1
    sql, rows = conn.many[0]
    assert "INSERT INTO core.asset_lifecycle_event" in sql
    assert "ON CONFLICT (asset_id, event_date, event_type, source_version)" in sql
    assert rows[0] == ("CN:SH:600000", "1999-11-10", "listed", None, "core.asset_master", "v1")


def test_load_distinct_market_trade_dates_queries_bars(monkeypatch):
    conn = FakeConnection(rows=[{"trade_date": "2024-01-02"}, {"trade_date": "2024-01-03"}])

    class _context:
        def __enter__(self):
            return conn

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(dimensions, "connect", lambda service: _context())
    monkeypatch.setattr(dimensions, "fetch_all", fake_fetch_all)

    result = dimensions.load_distinct_market_trade_dates("2024-01-01", "2024-01-31")

    assert result == ["2024-01-02", "2024-01-03"]
    sql, params = conn.executed[0]
    assert "FROM market_daily_bar" in sql
    assert params == ["hfq", "2024-01-01", "2024-01-31"]
