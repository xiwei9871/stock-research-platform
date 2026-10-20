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
