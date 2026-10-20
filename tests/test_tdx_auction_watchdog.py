from stock_research.tdx_auction_watchdog import (
    build_daily_partitions,
    completed_month_summaries,
    newly_completed_months,
    send_monthly_completion_reports,
)


def test_build_daily_partitions_keeps_one_task_per_trading_date():
    partitions = build_daily_partitions(["2018-02-14", "2018-02-15"])

    assert partitions == [
        {
            "partition_key": "2018-02-14",
            "start_date": "2018-02-14",
            "end_date": "2018-02-14",
        },
        {
            "partition_key": "2018-02-15",
            "start_date": "2018-02-15",
            "end_date": "2018-02-15",
        },
    ]


def test_completed_month_summaries_only_marks_month_when_all_days_succeed():
    rows = [
        {"trade_date": "2018-02-14", "status": "success", "rows_written": 2},
        {"trade_date": "2018-02-15", "status": "success", "rows_written": 3},
        {"trade_date": "2018-03-01", "status": "pending", "rows_written": 0},
    ]

    summaries = completed_month_summaries(rows)

    assert summaries == [
        {
            "month": "2018-02",
            "total_days": 2,
            "success_days": 2,
            "rows_written": 5,
        }
    ]


def test_completed_month_summaries_rolls_up_symbol_quality_metrics():
    rows = [
        {
            "trade_date": "2018-02-14",
            "status": "success",
            "rows_written": 2,
            "params": {"failed_symbols": 3, "missing_symbols": 4},
        },
    ]

    assert completed_month_summaries(rows) == [
        {
            "month": "2018-02",
            "total_days": 1,
            "success_days": 1,
            "rows_written": 2,
            "failed_symbols": 3,
            "missing_symbols": 4,
        }
    ]


def test_completed_month_summaries_rolls_up_unsupported_payload_metrics():
    rows = [
        {
            "trade_date": "2018-02-14",
            "status": "success",
            "rows_written": 2,
            "params": {"unsupported_symbols": 11, "excluded_symbols": 11},
        },
    ]

    assert completed_month_summaries(rows) == [
        {
            "month": "2018-02",
            "total_days": 1,
            "success_days": 1,
            "rows_written": 2,
            "excluded_symbols": 11,
            "unsupported_symbols": 11,
        }
    ]

def test_newly_completed_months_excludes_reported_months():
    rows = [
        {"trade_date": "2018-02-14", "status": "success", "rows_written": 2},
    ]

    assert newly_completed_months(rows, reported_months={"2018-01"}) == ["2018-02"]
    assert newly_completed_months(rows, reported_months={"2018-02"}) == []


def test_monthly_completion_report_is_idempotent(tmp_path):
    rows = [
        {
            "trade_date": "2018-02-14",
            "status": "success",
            "rows_written": 2,
            "params": {
                "requested_symbols": 100,
                "missing_symbols": 4,
                "unsupported_symbols": 11,
                "failed_symbols": 0,
                "excluded_symbols": 11,
            },
        },
    ]
    sent = []

    def fake_send(**kwargs):
        sent.append(kwargs["message"])

    ledger = tmp_path / "reported_months.json"
    first = send_monthly_completion_reports(
        rows=rows,
        ledger_path=ledger,
        report_target="chat:test",
        send=fake_send,
    )
    second = send_monthly_completion_reports(
        rows=rows,
        ledger_path=ledger,
        report_target="chat:test",
        send=fake_send,
    )

    assert first[0]["sent"] is True
    assert "TDX格式不支持=11" in first[0]["message"]
    assert "请求异常=0" in first[0]["message"]
    assert "当前退市未请求=11" in first[0]["message"]
    assert second == []
    assert len(sent) == 1


def test_adapter_run_id_override_keeps_daily_tasks_claimable(monkeypatch):
    """Stable run_id lets a failed date re-claim on later daily runs."""

    from stock_research import tdx_auction_watchdog as w

    created = {}

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(w, "connect", lambda service: FakeConn())
    monkeypatch.setattr(
        w, "_load_tdx_trade_dates", lambda **kw: ["2026-10-21"]
    )
    monkeypatch.setattr(
        w, "create_backfill_run",
        lambda conn, **kw: created.update(kw),
    )
    monkeypatch.setattr(
        w, "_load_status_rows",
        lambda *, run_id, service: [{"run_id_seen": run_id}],
    )

    adapter = w.TdxAuctionBackfillAdapter(
        start_date="2026-10-21",
        end_date="2026-10-21",
        run_id="tdx-auction-open:test:daily",
    )
    scope = adapter.load_scope()
    assert created["run_id"] == "tdx-auction-open:test:daily"
    assert created["start_date"] == "2026-10-21"
    assert scope["run_id"] == "tdx-auction-open:test:daily"
    rows = adapter.load_status_rows()
    assert rows == [{"run_id_seen": "tdx-auction-open:test:daily"}]


def test_adapter_default_run_id_derives_from_window():
    from stock_research.tdx_auction_watchdog import TdxAuctionBackfillAdapter

    adapter = TdxAuctionBackfillAdapter(
        start_date="2026-10-20", end_date="2026-10-20"
    )
    assert adapter._run_id().endswith(":2026-10-20:2026-10-20")


def test_latest_open_trade_date_queries_calendar(monkeypatch):
    from stock_research import tdx_auction_watchdog as w

    calls = []

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(w, "connect", lambda service: FakeConn())
    monkeypatch.setattr(
        w, "fetch_all",
        lambda conn, sql, params: calls.append((sql, params)) or [
            {"latest": "2026-10-20"}
        ],
    )
    assert w.latest_open_trade_date(service="s", on_or_before="2026-10-20") == "2026-10-20"
    sql, params = calls[0]
    assert "is_open" in sql
    assert "trading_calendar" in sql
    assert params == ["2026-10-20"]


def test_partial_run_lines_report_coverage_and_errors():
    from stock_research.tdx_auction_watchdog import TdxAuctionBackfillAdapter

    adapter = TdxAuctionBackfillAdapter(
        start_date="2026-10-20", end_date="2026-10-20"
    )
    lines = adapter.format_extra_status_lines(
        rows=[],
        summary=None,
        scope={},
        run_result={
            "success": 0, "failed": 0, "partial": 1,
            "errors": ["2026-10-20: coverage 3100/5181 = 59.8% below required 98%"],
            "requested": 5181, "missing": 2081, "failed_symbols": 0,
            "unsupported_symbols": 0, "excluded_symbols": 0, "rows": 3100,
        },
        status=None,
    )
    text = "\n".join(lines)
    assert "run_partial=1" in text
    assert "min_coverage_ratio" in text
    assert any("coverage" in line for line in lines)


def test_daily_scope_three_day_downtime_registers_gap():
    """3 open days missed while host down -> window covers all of them."""

    from stock_research.tdx_auction_watchdog import resolve_daily_backfill_scope
    import datetime as dt
    from zoneinfo import ZoneInfo

    open_dates = ["2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20"]
    done = {"2026-10-15", "2026-10-16"}  # last complete = Fri 10-16
    now = dt.datetime(2026, 10, 20, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    scope = resolve_daily_backfill_scope(
        open_dates=open_dates, done_dates=done, now=now
    )

    assert scope.window_start == "2026-10-19"
    assert scope.window_end == "2026-10-20"
    assert scope.incomplete_dates == ["2026-10-19", "2026-10-20"]
    assert scope.latest_collectible == "2026-10-20"


def test_daily_scope_weekend_recovery_uses_open_days_only():
    """Machine off Sat/Sun, Mon reboot -> only open days enter the window."""

    from stock_research.tdx_auction_watchdog import resolve_daily_backfill_scope
    import datetime as dt
    from zoneinfo import ZoneInfo

    open_dates = ["2026-10-16", "2026-10-19"]  # Fri then Mon
    done = {"2026-10-16"}
    now = dt.datetime(2026, 10, 19, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    scope = resolve_daily_backfill_scope(
        open_dates=open_dates, done_dates=done, now=now
    )

    assert scope.incomplete_dates == ["2026-10-19"]
    assert scope.window_start == "2026-10-19"


def test_daily_scope_failed_task_stays_in_window_for_reclaim():
    """A failed/partial ledger entry is treated as incomplete -> re-registered."""

    from stock_research.tdx_auction_watchdog import resolve_daily_backfill_scope
    import datetime as dt
    from zoneinfo import ZoneInfo

    open_dates = ["2026-10-19", "2026-10-20"]
    done = {"2026-10-20"}  # 10-19 failed in ledger -> not in done set
    now = dt.datetime(2026, 10, 20, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    scope = resolve_daily_backfill_scope(
        open_dates=open_dates, done_dates=done, now=now
    )

    assert scope.incomplete_dates == ["2026-10-19"]
    assert scope.window_start == "2026-10-19"
    assert scope.window_end == "2026-10-20"


def test_daily_scope_hole_before_last_success_is_found():
    """Missing date earlier than the last success still re-opens the window."""

    from stock_research.tdx_auction_watchdog import resolve_daily_backfill_scope
    import datetime as dt
    from zoneinfo import ZoneInfo

    open_dates = ["2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20"]
    done = {"2026-10-15", "2026-10-19", "2026-10-20"}  # 10-16 never registered
    now = dt.datetime(2026, 10, 20, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    scope = resolve_daily_backfill_scope(
        open_dates=open_dates, done_dates=done, now=now
    )

    assert scope.incomplete_dates == ["2026-10-16"]
    assert scope.window_start == "2026-10-16"


def test_daily_scope_all_complete_returns_no_window():
    from stock_research.tdx_auction_watchdog import resolve_daily_backfill_scope
    import datetime as dt
    from zoneinfo import ZoneInfo

    open_dates = ["2026-10-19", "2026-10-20"]
    done = {"2026-10-19", "2026-10-20"}
    now = dt.datetime(2026, 10, 20, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    scope = resolve_daily_backfill_scope(
        open_dates=open_dates, done_dates=done, now=now
    )

    assert scope.window_start is None
    assert scope.incomplete_dates == []


def test_daily_scope_same_day_not_collectible_before_cutoff():
    """RunAtLoad mid-trading-day must not target today before publish cutoff."""

    from stock_research.tdx_auction_watchdog import resolve_daily_backfill_scope
    import datetime as dt
    from zoneinfo import ZoneInfo

    open_dates = ["2026-10-19", "2026-10-20"]
    done = {"2026-10-19"}
    # 10:00 Shanghai on an open day -> today excluded from collectibility
    now = dt.datetime(2026, 10, 20, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    scope = resolve_daily_backfill_scope(
        open_dates=open_dates, done_dates=done, now=now
    )

    assert scope.latest_collectible == "2026-10-19"
    assert scope.incomplete_dates == []
    assert scope.window_start is None


def test_daily_scope_same_day_collectible_after_cutoff():
    from stock_research.tdx_auction_watchdog import resolve_daily_backfill_scope
    import datetime as dt
    from zoneinfo import ZoneInfo

    open_dates = ["2026-10-19", "2026-10-20"]
    done = {"2026-10-19"}
    now = dt.datetime(2026, 10, 20, 17, 30, tzinfo=ZoneInfo("Asia/Shanghai"))

    scope = resolve_daily_backfill_scope(
        open_dates=open_dates, done_dates=done, now=now
    )

    assert scope.latest_collectible == "2026-10-20"
    assert scope.incomplete_dates == ["2026-10-20"]


def test_load_daily_scope_combines_ledger_and_table_coverage(monkeypatch):
    """Ledger-success OR destination coverage >=98% counts a date as done."""

    from stock_research import tdx_auction_watchdog as w
    import datetime as dt
    from zoneinfo import ZoneInfo

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_fetch_all(conn, sql, params):
        if "trading_calendar" in sql:
            return [
                {"trade_date": "2026-10-19"},
                {"trade_date": "2026-10-20"},
            ]
        if "backfill_task" in sql:
            return [{"trade_date": "2026-10-19"}]  # ledger success
        if "stock_auction_bar" in sql:
            return [{"trade_date": "2026-10-20", "rows": 5000}]
        if "market_daily_bar" in sql:
            return [{"trade_date": "2026-10-20", "universe": 5000}]
        raise AssertionError(f"unexpected sql: {sql}")

    monkeypatch.setattr(w, "connect", lambda service: FakeConn())
    monkeypatch.setattr(w, "fetch_all", fake_fetch_all)

    scope = w.load_daily_backfill_scope(
        service="s",
        run_id="r",
        now=dt.datetime(2026, 10, 20, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    # 10-19 done via ledger, 10-20 done via table coverage -> nothing to do
    assert scope.incomplete_dates == []
    assert scope.window_start is None


def test_load_daily_scope_table_gap_reopens_date(monkeypatch):
    """Date absent from ledger AND under-covered in the table is incomplete."""

    from stock_research import tdx_auction_watchdog as w
    import datetime as dt
    from zoneinfo import ZoneInfo

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_fetch_all(conn, sql, params):
        if "trading_calendar" in sql:
            return [{"trade_date": "2026-10-20"}]
        if "backfill_task" in sql:
            return []
        if "stock_auction_bar" in sql:
            return [{"trade_date": "2026-10-20", "rows": 3000}]
        if "market_daily_bar" in sql:
            return [{"trade_date": "2026-10-20", "universe": 5000}]
        raise AssertionError(sql)

    monkeypatch.setattr(w, "connect", lambda service: FakeConn())
    monkeypatch.setattr(w, "fetch_all", fake_fetch_all)

    scope = w.load_daily_backfill_scope(
        service="s",
        run_id="r",
        now=dt.datetime(2026, 10, 20, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert scope.incomplete_dates == ["2026-10-20"]
    assert scope.window_start == "2026-10-20"
