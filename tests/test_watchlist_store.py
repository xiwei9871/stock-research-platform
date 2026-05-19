import pandas as pd

from stock_research.watchlist import store


def _context(conn):
    class _Manager:
        def __enter__(self):
            return conn

        def __exit__(self, exc_type, exc, tb):
            return False

    return _Manager()


def test_upsert_watchlist_items_writes_rows(monkeypatch):
    calls = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def executemany(self, sql, rows):
            calls.append((sql, list(rows)))

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr(store, "connect", lambda service: _context(FakeConn()))
    frame = pd.DataFrame(
        [
            {
                "watchlist_id": "core",
                "asset_id": "CN:SH:600000",
                "stock_code": "600000.SH",
                "stock_name": "PF Bank",
                "priority": 10,
                "active": True,
                "note": "core holding candidate",
                "source": "manual",
            }
        ]
    )

    count = store.upsert_watchlist_items(frame)

    assert count == 1
    assert "INSERT INTO watchlist.watchlist_item" in calls[0][0]
    assert calls[0][1][0]["watchlist_id"] == "core"
    assert list(calls[0][1][0].keys()) == store.WATCHLIST_ITEM_COLUMNS


def test_upsert_watchlist_items_applies_defaultable_fields(monkeypatch):
    calls = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def executemany(self, sql, rows):
            calls.append((sql, list(rows)))

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr(store, "connect", lambda service: _context(FakeConn()))
    frame = pd.DataFrame(
        [
            {
                "watchlist_id": "core",
                "asset_id": "CN:SH:600001",
                "stock_code": "600001.SH",
                "stock_name": "Example Bank",
                "note": None,
                "source": "manual",
            }
        ]
    )

    count = store.upsert_watchlist_items(frame)

    assert count == 1
    row = calls[0][1][0]
    assert row["priority"] == 100
    assert row["active"] is True
    assert row["source"] == "manual"


def test_load_watchlist_items_filters_active_members(monkeypatch):
    monkeypatch.setattr(
        store,
        "fetch_all",
        lambda conn, sql, params=None: [
            {
                "watchlist_id": "core",
                "asset_id": "CN:SH:600000",
                "stock_code": "600000.SH",
                "stock_name": "PF Bank",
                "priority": 10,
                "active": True,
                "note": None,
                "source": "manual",
            }
        ],
    )
    monkeypatch.setattr(store, "connect", lambda service: _context(object()))

    frame = store.load_watchlist_items("core", active_only=True)

    assert list(frame["asset_id"]) == ["CN:SH:600000"]


def test_load_watchlist_items_returns_empty_frame_with_expected_columns(monkeypatch):
    monkeypatch.setattr(store, "fetch_all", lambda conn, sql, params=None: [])
    monkeypatch.setattr(store, "connect", lambda service: _context(object()))

    frame = store.load_watchlist_items("core", active_only=True)

    assert frame.empty
    assert list(frame.columns) == store.WATCHLIST_ITEM_COLUMNS


def test_store_watchlist_daily_signals_writes_json_fields(monkeypatch):
    calls = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def executemany(self, sql, rows):
            calls.append((sql, list(rows)))

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr(store, "connect", lambda service: _context(FakeConn()))
    frame = pd.DataFrame(
        [
            {
                "watchlist_id": "core",
                "trade_date": "2026-05-20",
                "asset_id": "CN:SH:600000",
                "stock_code": "600000.SH",
                "stock_name": "PF Bank",
                "priority": 10,
                "signal_score": 88.5,
                "primary_signal": "candidate",
                "signal_tags": ["candidate", "must_watch"],
                "risk_tags": [],
                "must_watch": True,
                "reason_json": {"score_rank": 1},
                "output_version": "v1",
            }
        ]
    )

    count = store.store_watchlist_daily_signals(frame)

    assert count == 1
    assert "INSERT INTO watchlist.watchlist_daily_signal" in calls[0][0]
    assert calls[0][1][0]["signal_tags"] == '["candidate", "must_watch"]'
    assert list(calls[0][1][0].keys()) == store.WATCHLIST_SIGNAL_COLUMNS


def test_store_watchlist_daily_signals_applies_defaults_and_sanitizes_missing_json(monkeypatch):
    calls = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def executemany(self, sql, rows):
            calls.append((sql, list(rows)))

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    monkeypatch.setattr(store, "connect", lambda service: _context(FakeConn()))
    frame = pd.DataFrame(
        [
            {
                "watchlist_id": "core",
                "trade_date": "2026-05-20",
                "asset_id": "CN:SH:600001",
                "stock_code": "600001.SH",
                "stock_name": "Example Bank",
                "signal_score": 77.0,
                "primary_signal": "candidate",
                "signal_tags": pd.NA,
                "risk_tags": float("nan"),
                "reason_json": pd.NA,
                "output_version": "v1",
            }
        ]
    )

    count = store.store_watchlist_daily_signals(frame)

    assert count == 1
    row = calls[0][1][0]
    assert row["priority"] == 100
    assert row["must_watch"] is False
    assert row["signal_tags"] == "[]"
    assert row["risk_tags"] == "[]"
    assert row["reason_json"] == "{}"
    assert row["primary_signal"] == "candidate"
    assert row["output_version"] == "v1"


def test_load_watchlist_daily_signals_returns_empty_frame_with_expected_columns(monkeypatch):
    monkeypatch.setattr(store, "fetch_all", lambda conn, sql, params=None: [])
    monkeypatch.setattr(store, "connect", lambda service: _context(object()))

    frame = store.load_watchlist_daily_signals("core")

    assert frame.empty
    assert list(frame.columns) == store.WATCHLIST_SIGNAL_COLUMNS
