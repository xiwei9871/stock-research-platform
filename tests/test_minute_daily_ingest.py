import datetime as dt

import stock_research.minute_daily_ingest as minute_daily_ingest


def test_run_baostock_minute_daily_skips_non_trading_day(monkeypatch):
    monkeypatch.setattr(
        minute_daily_ingest,
        "parse_trade_date",
        lambda value, timezone: dt.date(2024, 1, 6),
    )
    monkeypatch.setattr(
        minute_daily_ingest,
        "decide_stock_cron_run",
        lambda **kwargs: minute_daily_ingest.StockCronGuardDecision(
            trade_date=dt.date(2024, 1, 6),
            calendar_status="closed",
            should_run=False,
            reason="non_trading_day",
        ),
    )

    result = minute_daily_ingest.run_baostock_minute_daily(trade_date="2024-01-06")

    assert result == {
        "status": "skipped_non_trading_day",
        "trade_date": "2024-01-06",
        "symbol_count": 0,
        "success_count": 0,
        "empty_count": 0,
        "failed_count": 0,
        "retry_count": 0,
        "relogin_count": 0,
        "rows_written": 0,
        "failed_symbols": [],
    }


def test_run_baostock_minute_daily_skips_when_lock_is_busy(monkeypatch):
    lock_path = minute_daily_ingest.DEFAULT_MINUTE_DAILY_LOCK

    monkeypatch.setattr(
        minute_daily_ingest,
        "parse_trade_date",
        lambda value, timezone: dt.date(2024, 1, 8),
    )
    monkeypatch.setattr(
        minute_daily_ingest,
        "decide_stock_cron_run",
        lambda **kwargs: minute_daily_ingest.StockCronGuardDecision(
            trade_date=dt.date(2024, 1, 8),
            calendar_status="open",
            should_run=True,
            reason="trading_day",
        ),
    )
    seen = []

    def fake_try_acquire(path):
        seen.append(path)
        return None

    monkeypatch.setattr(minute_daily_ingest, "_try_acquire_daily_lock", fake_try_acquire)

    result = minute_daily_ingest.run_baostock_minute_daily(trade_date="2024-01-08")

    assert seen == [lock_path]
    assert result == {
        "status": "skipped_locked",
        "trade_date": "2024-01-08",
        "symbol_count": 0,
        "success_count": 0,
        "empty_count": 0,
        "failed_count": 0,
        "retry_count": 0,
        "relogin_count": 0,
        "rows_written": 0,
        "failed_symbols": [],
    }


def test_run_baostock_minute_daily_queries_one_trade_date_per_symbol(monkeypatch):
    target_date = dt.date(2024, 1, 8)
    events = []
    queries = []
    upserts = []
    sleep_calls = []
    rows_by_code = {
        "sh.600000": [{"code": "sh.600000", "date": "2024-01-08", "time": "20240108093500000"}],
        "sz.000001": [],
    }

    monkeypatch.setattr(
        minute_daily_ingest,
        "parse_trade_date",
        lambda value, timezone: target_date,
    )
    monkeypatch.setattr(
        minute_daily_ingest,
        "decide_stock_cron_run",
        lambda **kwargs: minute_daily_ingest.StockCronGuardDecision(
            trade_date=target_date,
            calendar_status="open",
            should_run=True,
            reason="trading_day",
        ),
    )
    monkeypatch.setattr(
        minute_daily_ingest,
        "_try_acquire_daily_lock",
        lambda path: events.append(("lock", path)) or "lock-handle",
    )
    monkeypatch.setattr(
        minute_daily_ingest,
        "_release_daily_lock",
        lambda handle: events.append(("unlock", handle)),
    )
    monkeypatch.setattr(
        minute_daily_ingest,
        "load_active_baostock_codes",
        lambda limit_assets=None: events.append(("load_codes", limit_assets))
        or ["sh.600000", "sz.000001"],
    )
    monkeypatch.setattr(
        minute_daily_ingest,
        "login_or_raise",
        lambda: events.append(("login", None)),
    )

    def fake_query(code, start_date, end_date, *, freq, adjust_type):
        events.append(("query", code))
        queries.append((code, start_date, end_date, freq, adjust_type))
        return rows_by_code[code]

    monkeypatch.setattr(
        minute_daily_ingest,
        "query_baostock_minute_rows_once",
        fake_query,
    )

    def fake_upsert(rows, *, freq, adjust_type, params):
        code = rows[0]["code"] if rows else "sz.000001"
        events.append(("upsert", code, len(rows)))
        upserts.append((rows, freq, adjust_type, params))
        return len(rows)

    monkeypatch.setattr(
        minute_daily_ingest,
        "upsert_stock_minute_bars",
        fake_upsert,
    )
    monkeypatch.setattr(
        minute_daily_ingest.time,
        "sleep",
        lambda seconds: sleep_calls.append(seconds),
    )
    monkeypatch.setattr(
        minute_daily_ingest.bs,
        "logout",
        lambda: events.append(("logout", None)),
    )

    result = minute_daily_ingest.run_baostock_minute_daily(
        trade_date="2024-01-08",
        limit_assets=2,
        sleep_seconds=0.25,
    )

    assert queries == [
        ("sh.600000", target_date, target_date, "5min", "raw"),
        ("sz.000001", target_date, target_date, "5min", "raw"),
    ]
    assert upserts == [
        (
            rows_by_code["sh.600000"],
            "5min",
            "raw",
            {
                "code": "sh.600000",
                "fields": minute_daily_ingest.MINUTE_FIELDS,
                "start_date": "2024-01-08",
                "end_date": "2024-01-08",
                "frequency": "5",
                "adjustflag": "3",
            },
        ),
        (
            rows_by_code["sz.000001"],
            "5min",
            "raw",
            {
                "code": "sz.000001",
                "fields": minute_daily_ingest.MINUTE_FIELDS,
                "start_date": "2024-01-08",
                "end_date": "2024-01-08",
                "frequency": "5",
                "adjustflag": "3",
            },
        ),
    ]
    assert events == [
        ("lock", minute_daily_ingest.DEFAULT_MINUTE_DAILY_LOCK),
        ("load_codes", 2),
        ("login", None),
        ("query", "sh.600000"),
        ("upsert", "sh.600000", 1),
        ("query", "sz.000001"),
        ("upsert", "sz.000001", 0),
        ("logout", None),
        ("unlock", "lock-handle"),
    ]
    assert sleep_calls == [0.25, 0.25]
    assert result == {
        "status": "success",
        "trade_date": "2024-01-08",
        "symbol_count": 2,
        "success_count": 1,
        "empty_count": 1,
        "failed_count": 0,
        "retry_count": 0,
        "relogin_count": 0,
        "rows_written": 1,
        "failed_symbols": [],
    }
