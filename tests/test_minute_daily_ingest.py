import datetime as dt
import json

import pytest

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
        "last_error": None,
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
        "last_error": None,
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
    assert sleep_calls == [0.25]
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
        "last_error": None,
    }


def test_run_baostock_minute_daily_counts_success_by_symbol_not_rows(monkeypatch):
    target_date = dt.date(2024, 1, 8)
    rows = [
        {"code": "sh.600000", "date": "2024-01-08", "time": "20240108093500000"},
        {"code": "sh.600000", "date": "2024-01-08", "time": "20240108094000000"},
    ]

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
    monkeypatch.setattr(minute_daily_ingest, "_try_acquire_daily_lock", lambda path: "lock-handle")
    monkeypatch.setattr(minute_daily_ingest, "_release_daily_lock", lambda handle: None)
    monkeypatch.setattr(
        minute_daily_ingest,
        "load_active_baostock_codes",
        lambda limit_assets=None: ["sh.600000"],
    )
    monkeypatch.setattr(minute_daily_ingest, "login_or_raise", lambda: None)
    monkeypatch.setattr(
        minute_daily_ingest,
        "query_baostock_minute_rows_once",
        lambda code, start_date, end_date, *, freq, adjust_type: rows,
    )
    monkeypatch.setattr(
        minute_daily_ingest,
        "upsert_stock_minute_bars",
        lambda queried_rows, *, freq, adjust_type, params: len(queried_rows),
    )
    monkeypatch.setattr(minute_daily_ingest.bs, "logout", lambda: None)

    result = minute_daily_ingest.run_baostock_minute_daily(trade_date="2024-01-08")

    assert result == {
        "status": "success",
        "trade_date": "2024-01-08",
        "symbol_count": 1,
        "success_count": 1,
        "empty_count": 0,
        "failed_count": 0,
        "retry_count": 0,
        "relogin_count": 0,
        "rows_written": 2,
        "failed_symbols": [],
        "last_error": None,
    }


def test_run_baostock_minute_daily_retries_same_session_before_relogin(monkeypatch):
    target_date = dt.date(2024, 1, 8)
    events = []
    attempts = {"sh.600000": 0}
    sleep_calls = []
    rows = [
        {"code": "sh.600000", "date": "2024-01-08", "time": "20240108093500000"},
    ]

    monkeypatch.setattr(minute_daily_ingest, "parse_trade_date", lambda value, timezone: target_date)
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
    monkeypatch.setattr(minute_daily_ingest, "_try_acquire_daily_lock", lambda path: "lock-handle")
    monkeypatch.setattr(minute_daily_ingest, "_release_daily_lock", lambda handle: None)
    monkeypatch.setattr(
        minute_daily_ingest,
        "load_active_baostock_codes",
        lambda limit_assets=None: ["sh.600000"],
    )
    monkeypatch.setattr(
        minute_daily_ingest,
        "login_or_raise",
        lambda: events.append(("login", None)),
    )
    monkeypatch.setattr(
        minute_daily_ingest,
        "relogin_or_raise",
        lambda: events.append(("relogin", None)),
    )

    def fake_query(code, start_date, end_date, *, freq, adjust_type):
        attempts[code] += 1
        events.append(("query", code, attempts[code]))
        if attempts[code] < 3:
            raise RuntimeError("10002007 session busy")
        return rows

    monkeypatch.setattr(minute_daily_ingest, "query_baostock_minute_rows_once", fake_query)
    monkeypatch.setattr(
        minute_daily_ingest,
        "upsert_stock_minute_bars",
        lambda queried_rows, *, freq, adjust_type, params: len(queried_rows),
    )
    monkeypatch.setattr(minute_daily_ingest.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(minute_daily_ingest.bs, "logout", lambda: events.append(("logout", None)))

    result = minute_daily_ingest.run_baostock_minute_daily(
        trade_date="2024-01-08",
        retry_limit=2,
    )

    assert attempts == {"sh.600000": 3}
    assert ("relogin", None) not in events
    assert result["status"] == "success"
    assert result["success_count"] == 1
    assert result["failed_count"] == 0
    assert result["retry_count"] == 2
    assert result["relogin_count"] == 0
    assert result["rows_written"] == 1
    assert result["last_error"] is None
    assert sleep_calls == [1.0, 1.0]


def test_run_baostock_minute_daily_retries_failed_symbols_only_in_retry_queue(monkeypatch):
    target_date = dt.date(2024, 1, 8)
    attempts = {"sh.600000": 0, "sz.000001": 0, "bj.430001": 0}
    outcomes = {
        "sh.600000": [
            [{"code": "sh.600000", "date": "2024-01-08", "time": "20240108093500000"}],
        ],
        "sz.000001": [
            RuntimeError("10002007 main pass failed"),
            [{"code": "sz.000001", "date": "2024-01-08", "time": "20240108093500000"}],
        ],
        "bj.430001": [
            [{"code": "bj.430001", "date": "2024-01-08", "time": "20240108093500000"}],
        ],
    }

    monkeypatch.setattr(minute_daily_ingest, "parse_trade_date", lambda value, timezone: target_date)
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
    monkeypatch.setattr(minute_daily_ingest, "_try_acquire_daily_lock", lambda path: "lock-handle")
    monkeypatch.setattr(minute_daily_ingest, "_release_daily_lock", lambda handle: None)
    monkeypatch.setattr(
        minute_daily_ingest,
        "load_active_baostock_codes",
        lambda limit_assets=None: ["sh.600000", "sz.000001", "bj.430001"],
    )
    monkeypatch.setattr(minute_daily_ingest, "login_or_raise", lambda: None)

    def fake_query(code, start_date, end_date, *, freq, adjust_type):
        attempts[code] += 1
        outcome = outcomes[code].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(minute_daily_ingest, "query_baostock_minute_rows_once", fake_query)
    monkeypatch.setattr(
        minute_daily_ingest,
        "upsert_stock_minute_bars",
        lambda queried_rows, *, freq, adjust_type, params: len(queried_rows),
    )
    monkeypatch.setattr(minute_daily_ingest.bs, "logout", lambda: None)

    result = minute_daily_ingest.run_baostock_minute_daily(
        trade_date="2024-01-08",
        retry_limit=0,
    )

    assert attempts == {"sh.600000": 1, "sz.000001": 2, "bj.430001": 1}
    assert result["status"] == "success"
    assert result["success_count"] == 3
    assert result["failed_count"] == 0
    assert result["failed_symbols"] == []
    assert result["last_error"] is None


def test_run_baostock_minute_daily_relogins_after_three_consecutive_failed_symbols(monkeypatch):
    target_date = dt.date(2024, 1, 8)
    events = []
    sleep_calls = []

    monkeypatch.setattr(minute_daily_ingest, "parse_trade_date", lambda value, timezone: target_date)
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
    monkeypatch.setattr(minute_daily_ingest, "_try_acquire_daily_lock", lambda path: "lock-handle")
    monkeypatch.setattr(minute_daily_ingest, "_release_daily_lock", lambda handle: None)
    monkeypatch.setattr(
        minute_daily_ingest,
        "load_active_baostock_codes",
        lambda limit_assets=None: ["sh.600000", "sz.000001", "bj.430001", "sh.600004"],
    )
    monkeypatch.setattr(minute_daily_ingest, "login_or_raise", lambda: events.append(("login", None)))
    monkeypatch.setattr(
        minute_daily_ingest,
        "relogin_or_raise",
        lambda: events.append(("relogin", None)),
    )

    def fake_query(code, start_date, end_date, *, freq, adjust_type):
        events.append(("query", code))
        if code == "sh.600004":
            return [{"code": code, "date": "2024-01-08", "time": "20240108093500000"}]
        raise RuntimeError("10002007 retryable failure")

    monkeypatch.setattr(minute_daily_ingest, "query_baostock_minute_rows_once", fake_query)
    monkeypatch.setattr(
        minute_daily_ingest,
        "upsert_stock_minute_bars",
        lambda queried_rows, *, freq, adjust_type, params: len(queried_rows),
    )
    monkeypatch.setattr(minute_daily_ingest.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(minute_daily_ingest.bs, "logout", lambda: events.append(("logout", None)))

    result = minute_daily_ingest.run_baostock_minute_daily(
        trade_date="2024-01-08",
        retry_limit=0,
        cooldown_seconds=7,
    )

    assert events[:5] == [
        ("login", None),
        ("query", "sh.600000"),
        ("query", "sz.000001"),
        ("query", "bj.430001"),
        ("relogin", None),
    ]
    assert events[5] == ("query", "sh.600004")
    assert events[-2:] == [("relogin", None), ("logout", None)]
    assert sleep_calls == [7, 7]
    assert result["status"] == "partial"
    assert result["relogin_count"] == 2
    assert result["failed_count"] == 3
    assert result["failed_symbols"] == ["sh.600000", "sz.000001", "bj.430001"]
    assert result["last_error"] == "10002007 retryable failure"


def test_run_baostock_minute_daily_enters_cooldown_after_failure_burst(monkeypatch):
    target_date = dt.date(2024, 1, 8)
    sleep_calls = []

    monkeypatch.setattr(minute_daily_ingest, "parse_trade_date", lambda value, timezone: target_date)
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
    monkeypatch.setattr(minute_daily_ingest, "_try_acquire_daily_lock", lambda path: "lock-handle")
    monkeypatch.setattr(minute_daily_ingest, "_release_daily_lock", lambda handle: None)
    monkeypatch.setattr(
        minute_daily_ingest,
        "load_active_baostock_codes",
        lambda limit_assets=None: ["sh.600000", "sz.000001", "bj.430001", "sh.600004"],
    )
    monkeypatch.setattr(minute_daily_ingest, "login_or_raise", lambda: None)
    monkeypatch.setattr(minute_daily_ingest, "relogin_or_raise", lambda: None)

    def fake_query(code, start_date, end_date, *, freq, adjust_type):
        if code == "sh.600004":
            return [{"code": code, "date": "2024-01-08", "time": "20240108093500000"}]
        raise RuntimeError("10002007 retryable failure")

    monkeypatch.setattr(minute_daily_ingest, "query_baostock_minute_rows_once", fake_query)
    monkeypatch.setattr(
        minute_daily_ingest,
        "upsert_stock_minute_bars",
        lambda queried_rows, *, freq, adjust_type, params: len(queried_rows),
    )
    monkeypatch.setattr(minute_daily_ingest.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(minute_daily_ingest.bs, "logout", lambda: None)

    minute_daily_ingest.run_baostock_minute_daily(
        trade_date="2024-01-08",
        retry_limit=0,
        sleep_seconds=0.25,
        cooldown_seconds=9,
    )

    assert sleep_calls == [0.25, 0.25, 9, 0.25, 9]


def test_run_baostock_minute_daily_writes_summary_and_failed_symbols(monkeypatch, tmp_path):
    target_date = dt.date(2024, 1, 8)

    monkeypatch.setattr(minute_daily_ingest, "parse_trade_date", lambda value, timezone: target_date)
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
    monkeypatch.setattr(minute_daily_ingest, "_try_acquire_daily_lock", lambda path: "lock-handle")
    monkeypatch.setattr(minute_daily_ingest, "_release_daily_lock", lambda handle: None)
    monkeypatch.setattr(
        minute_daily_ingest,
        "load_active_baostock_codes",
        lambda limit_assets=None: ["sh.600000", "sz.000001"],
    )
    monkeypatch.setattr(minute_daily_ingest, "login_or_raise", lambda: None)

    def fake_query(code, start_date, end_date, *, freq, adjust_type):
        if code == "sh.600000":
            return [{"code": code, "date": "2024-01-08", "time": "20240108093500000"}]
        raise RuntimeError("10002007 retry me")

    monkeypatch.setattr(minute_daily_ingest, "query_baostock_minute_rows_once", fake_query)
    monkeypatch.setattr(
        minute_daily_ingest,
        "upsert_stock_minute_bars",
        lambda queried_rows, *, freq, adjust_type, params: len(queried_rows),
    )
    monkeypatch.setattr(minute_daily_ingest.bs, "logout", lambda: None)

    result = minute_daily_ingest.run_baostock_minute_daily(
        trade_date="2024-01-08",
        retry_limit=0,
        output_dir=tmp_path,
    )

    artifact_dir = tmp_path / "baostock_minute_daily" / "2024-01-08"
    summary = json.loads((artifact_dir / "summary.json").read_text(encoding="utf-8"))
    failed_symbols = (artifact_dir / "failed_symbols.txt").read_text(encoding="utf-8")

    assert result["status"] == "partial"
    assert summary["status"] == "partial"
    assert summary["trade_date"] == "2024-01-08"
    assert summary["failed_symbols"] == ["sz.000001"]
    assert summary["last_error"] == "10002007 retry me"
    assert failed_symbols == "sz.000001\n"


def test_run_baostock_minute_daily_continues_after_upsert_failure(monkeypatch):
    target_date = dt.date(2024, 1, 8)
    events = []

    rows_by_code = {
        "sh.600000": [{"code": "sh.600000", "date": "2024-01-08", "time": "20240108093500000"}],
        "sz.000001": [{"code": "sz.000001", "date": "2024-01-08", "time": "20240108093500000"}],
    }

    monkeypatch.setattr(minute_daily_ingest, "parse_trade_date", lambda value, timezone: target_date)
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
    monkeypatch.setattr(minute_daily_ingest, "_try_acquire_daily_lock", lambda path: "lock-handle")
    monkeypatch.setattr(minute_daily_ingest, "_release_daily_lock", lambda handle: None)
    monkeypatch.setattr(
        minute_daily_ingest,
        "load_active_baostock_codes",
        lambda limit_assets=None: ["sh.600000", "sz.000001"],
    )
    monkeypatch.setattr(minute_daily_ingest, "login_or_raise", lambda: events.append(("login", None)))
    monkeypatch.setattr(
        minute_daily_ingest,
        "query_baostock_minute_rows_once",
        lambda code, start_date, end_date, *, freq, adjust_type: events.append(("query", code))
        or rows_by_code[code],
    )

    def fake_upsert(queried_rows, *, freq, adjust_type, params):
        code = queried_rows[0]["code"]
        events.append(("upsert", code))
        if code == "sh.600000":
            raise RuntimeError("db write failed")
        return len(queried_rows)

    monkeypatch.setattr(minute_daily_ingest, "upsert_stock_minute_bars", fake_upsert)
    monkeypatch.setattr(minute_daily_ingest.bs, "logout", lambda: events.append(("logout", None)))

    result = minute_daily_ingest.run_baostock_minute_daily(
        trade_date="2024-01-08",
        retry_limit=0,
    )

    assert result == {
        "status": "partial",
        "trade_date": "2024-01-08",
        "symbol_count": 2,
        "success_count": 1,
        "empty_count": 0,
        "failed_count": 1,
        "retry_count": 0,
        "relogin_count": 0,
        "rows_written": 1,
        "failed_symbols": ["sh.600000"],
        "last_error": "db write failed",
    }
    assert events == [
        ("login", None),
        ("query", "sh.600000"),
        ("upsert", "sh.600000"),
        ("query", "sz.000001"),
        ("upsert", "sz.000001"),
        ("logout", None),
    ]


def test_run_baostock_minute_daily_applies_relogin_policy_in_retry_queue(monkeypatch):
    target_date = dt.date(2024, 1, 8)
    events = []
    sleep_calls = []
    attempts = {
        "sh.600000": 0,
        "sz.000001": 0,
        "bj.430001": 0,
        "sh.600004": 0,
        "sz.000005": 0,
    }

    monkeypatch.setattr(minute_daily_ingest, "parse_trade_date", lambda value, timezone: target_date)
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
    monkeypatch.setattr(minute_daily_ingest, "_try_acquire_daily_lock", lambda path: "lock-handle")
    monkeypatch.setattr(minute_daily_ingest, "_release_daily_lock", lambda handle: None)
    monkeypatch.setattr(
        minute_daily_ingest,
        "load_active_baostock_codes",
        lambda limit_assets=None: [
            "sh.600000",
            "sz.000001",
            "bj.430001",
            "sh.600004",
            "sz.000005",
        ],
    )
    monkeypatch.setattr(minute_daily_ingest, "login_or_raise", lambda: events.append(("login", None)))
    monkeypatch.setattr(minute_daily_ingest, "relogin_or_raise", lambda: events.append(("relogin", None)))

    def fake_query(code, start_date, end_date, *, freq, adjust_type):
        attempts[code] += 1
        events.append(("query", code, attempts[code]))
        if attempts[code] == 1:
            if code in {"sh.600000", "bj.430001", "sz.000005"}:
                raise RuntimeError("10002007 retryable failure")
            return [{"code": code, "date": "2024-01-08", "time": "20240108093500000"}]
        if code in {"sh.600000", "bj.430001", "sz.000005"}:
            raise RuntimeError("10002007 retryable failure")
        return [{"code": code, "date": "2024-01-08", "time": "20240108093500000"}]

    monkeypatch.setattr(minute_daily_ingest, "query_baostock_minute_rows_once", fake_query)
    monkeypatch.setattr(
        minute_daily_ingest,
        "upsert_stock_minute_bars",
        lambda queried_rows, *, freq, adjust_type, params: len(queried_rows),
    )
    monkeypatch.setattr(minute_daily_ingest.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(minute_daily_ingest.bs, "logout", lambda: events.append(("logout", None)))

    result = minute_daily_ingest.run_baostock_minute_daily(
        trade_date="2024-01-08",
        retry_limit=0,
        cooldown_seconds=11,
    )

    assert events == [
        ("login", None),
        ("query", "sh.600000", 1),
        ("query", "sz.000001", 1),
        ("query", "bj.430001", 1),
        ("query", "sh.600004", 1),
        ("query", "sz.000005", 1),
        ("query", "sh.600000", 2),
        ("query", "bj.430001", 2),
        ("query", "sz.000005", 2),
        ("relogin", None),
        ("logout", None),
    ]
    assert sleep_calls == [11]
    assert result["status"] == "partial"
    assert result["relogin_count"] == 1
    assert result["failed_count"] == 3
    assert result["failed_symbols"] == ["sh.600000", "bj.430001", "sz.000005"]
    assert result["last_error"] == "10002007 retryable failure"


def test_run_baostock_minute_daily_rejects_negative_retry_limit(monkeypatch):
    target_date = dt.date(2024, 1, 8)

    monkeypatch.setattr(minute_daily_ingest, "parse_trade_date", lambda value, timezone: target_date)
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
    monkeypatch.setattr(minute_daily_ingest, "_try_acquire_daily_lock", lambda path: "lock-handle")
    monkeypatch.setattr(minute_daily_ingest, "_release_daily_lock", lambda handle: None)
    monkeypatch.setattr(minute_daily_ingest.bs, "logout", lambda: None)

    with pytest.raises(ValueError, match="retry_limit must be >= 0"):
        minute_daily_ingest.run_baostock_minute_daily(
            trade_date="2024-01-08",
            retry_limit=-1,
        )


def test_run_baostock_minute_daily_releases_lock_and_logs_out_when_login_fails(monkeypatch):
    target_date = dt.date(2024, 1, 8)
    events = []

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
        lambda limit_assets=None: ["sh.600000"],
    )

    def raise_login():
        raise RuntimeError("login failed")

    monkeypatch.setattr(minute_daily_ingest, "login_or_raise", raise_login)
    monkeypatch.setattr(
        minute_daily_ingest.bs,
        "logout",
        lambda: events.append(("logout", None)),
    )

    with pytest.raises(RuntimeError, match="login failed"):
        minute_daily_ingest.run_baostock_minute_daily(trade_date="2024-01-08")

    assert events == [
        ("lock", minute_daily_ingest.DEFAULT_MINUTE_DAILY_LOCK),
        ("logout", None),
        ("unlock", "lock-handle"),
    ]


def test_run_baostock_minute_daily_releases_lock_and_logs_out_after_query_failure(monkeypatch):
    target_date = dt.date(2024, 1, 8)
    events = []

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
        lambda limit_assets=None: ["sh.600000"],
    )
    monkeypatch.setattr(
        minute_daily_ingest,
        "login_or_raise",
        lambda: events.append(("login", None)),
    )

    def raise_query(code, start_date, end_date, *, freq, adjust_type):
        events.append(("query", code))
        raise RuntimeError("query failed")

    monkeypatch.setattr(
        minute_daily_ingest,
        "query_baostock_minute_rows_once",
        raise_query,
    )
    monkeypatch.setattr(
        minute_daily_ingest.bs,
        "logout",
        lambda: events.append(("logout", None)),
    )

    result = minute_daily_ingest.run_baostock_minute_daily(trade_date="2024-01-08")

    assert result == {
        "status": "partial",
        "trade_date": "2024-01-08",
        "symbol_count": 1,
        "success_count": 0,
        "empty_count": 0,
        "failed_count": 1,
        "retry_count": 0,
        "relogin_count": 0,
        "rows_written": 0,
        "failed_symbols": ["sh.600000"],
        "last_error": "query failed",
    }
    assert events == [
        ("lock", minute_daily_ingest.DEFAULT_MINUTE_DAILY_LOCK),
        ("login", None),
        ("query", "sh.600000"),
        ("query", "sh.600000"),
        ("logout", None),
        ("unlock", "lock-handle"),
    ]
