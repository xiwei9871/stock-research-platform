from __future__ import annotations

from datetime import date

from stock_research import stock_cron_guard


def test_decide_stock_cron_run_allows_open_trading_day(monkeypatch):
    monkeypatch.setattr(
        stock_cron_guard,
        "trading_calendar_status",
        lambda service, trade_date, exchanges: "open",
    )

    decision = stock_cron_guard.decide_stock_cron_run(
        service="test",
        trade_date=date(2026, 6, 18),
    )

    assert decision.should_run is True
    assert decision.calendar_status == "open"
    assert decision.reason == "trading_day"


def test_decide_stock_cron_run_skips_closed_trading_day(monkeypatch):
    monkeypatch.setattr(
        stock_cron_guard,
        "trading_calendar_status",
        lambda service, trade_date, exchanges: "closed",
    )

    decision = stock_cron_guard.decide_stock_cron_run(
        service="test",
        trade_date=date(2026, 6, 19),
        sync_missing_calendar=False,
    )

    assert decision.should_run is False
    assert decision.calendar_status == "closed"
    assert decision.reason == "non_trading_day"


def test_decide_stock_cron_run_skips_missing_calendar_row(monkeypatch):
    monkeypatch.setattr(
        stock_cron_guard,
        "trading_calendar_status",
        lambda service, trade_date, exchanges: "unknown",
    )

    decision = stock_cron_guard.decide_stock_cron_run(
        service="test",
        trade_date=date(2026, 6, 19),
    )

    assert decision.should_run is False
    assert decision.calendar_status == "unknown"
    assert decision.reason == "missing_trading_calendar_row"


def test_decide_stock_cron_run_syncs_missing_calendar_then_allows_open_day(monkeypatch):
    statuses = iter(["unknown", "open"])
    refresh_calls = []
    monkeypatch.setattr(
        stock_cron_guard,
        "trading_calendar_status",
        lambda service, trade_date, exchanges: next(statuses),
    )
    monkeypatch.setattr(
        stock_cron_guard,
        "refresh_trading_calendar_from_tushare",
        lambda **kwargs: refresh_calls.append(kwargs) or 2,
    )

    decision = stock_cron_guard.decide_stock_cron_run(
        service="test",
        trade_date=date(2026, 6, 22),
    )

    assert decision.should_run is True
    assert decision.calendar_status == "open"
    assert refresh_calls[0]["exchanges"] == ("SH", "SZ")


def test_decide_stock_cron_run_skips_when_calendar_sync_fails(monkeypatch):
    monkeypatch.setattr(
        stock_cron_guard,
        "trading_calendar_status",
        lambda service, trade_date, exchanges: "unknown",
    )

    def fail_refresh(**kwargs):
        raise RuntimeError("source unavailable")

    monkeypatch.setattr(stock_cron_guard, "refresh_trading_calendar_from_tushare", fail_refresh)

    decision = stock_cron_guard.decide_stock_cron_run(
        service="test",
        trade_date=date(2026, 6, 19),
    )

    assert decision.should_run is False
    assert decision.calendar_status == "unknown"
    assert decision.reason == "missing_trading_calendar_row"


def test_main_returns_skip_exit_code_for_non_trading_day(monkeypatch, capsys):
    monkeypatch.setattr(
        stock_cron_guard,
        "trading_calendar_status",
        lambda service, trade_date, exchanges: "closed",
    )

    rc = stock_cron_guard.main(["--date", "2026-06-19", "--service", "test"])

    assert rc == stock_cron_guard.SKIP_EXIT_CODE
    expected = (
        "stock_cron_guard|action|skip|trade_date|2026-06-19|"
        "calendar_status|closed|reason|non_trading_day"
    )
    assert (
        capsys.readouterr().out.strip() == expected
    )


def test_main_force_allows_run_when_calendar_is_missing(monkeypatch):
    monkeypatch.setattr(
        stock_cron_guard,
        "trading_calendar_status",
        lambda service, trade_date, exchanges: "unknown",
    )

    rc = stock_cron_guard.main(["--date", "2026-06-19", "--service", "test", "--force"])

    assert rc == 0


def test_build_trading_calendar_rows_from_tushare_records_includes_closed_days():
    rows = stock_cron_guard.build_trading_calendar_rows_from_tushare_records(
        [
            {"cal_date": "20260619", "is_open": 0},
            {"cal_date": "20260622", "is_open": 1},
        ],
        exchanges=("SH", "SZ"),
        source_version="tushare_trade_cal_v1",
    )

    assert rows == [
        {
            "exchange": "SH",
            "trade_date": "2026-06-19",
            "is_open": False,
            "source": "tushare",
            "source_version": "tushare_trade_cal_v1",
        },
        {
            "exchange": "SZ",
            "trade_date": "2026-06-19",
            "is_open": False,
            "source": "tushare",
            "source_version": "tushare_trade_cal_v1",
        },
        {
            "exchange": "SH",
            "trade_date": "2026-06-22",
            "is_open": True,
            "source": "tushare",
            "source_version": "tushare_trade_cal_v1",
        },
        {
            "exchange": "SZ",
            "trade_date": "2026-06-22",
            "is_open": True,
            "source": "tushare",
            "source_version": "tushare_trade_cal_v1",
        },
    ]


def test_sync_trading_calendar_range_from_tushare_writes_range(monkeypatch):
    upserted = []

    class FakeFrame:
        empty = False

        def to_dict(self, orient):
            assert orient == "records"
            return [
                {"cal_date": "20260619", "is_open": 0},
                {"cal_date": "20260622", "is_open": 1},
            ]

    class FakePro:
        def trade_cal(self, **kwargs):
            assert kwargs == {
                "exchange": "",
                "start_date": "20260619",
                "end_date": "20260622",
            }
            return FakeFrame()

    class FakeTs:
        @staticmethod
        def pro_api(token):
            assert token == "token"
            return FakePro()

    class FakeConnect:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setitem(__import__("sys").modules, "tushare", FakeTs)
    monkeypatch.setattr(stock_cron_guard, "connect", lambda service: FakeConnect())
    monkeypatch.setattr(
        stock_cron_guard,
        "upsert_trading_calendar",
        lambda conn, rows: upserted.extend(rows) or len(rows),
    )

    count = stock_cron_guard.sync_trading_calendar_range_from_tushare(
        service="test",
        start_date=date(2026, 6, 19),
        end_date=date(2026, 6, 22),
        exchanges=("SH", "SZ"),
        token="token",
    )

    assert count == 4
    assert {row["trade_date"] for row in upserted} == {"2026-06-19", "2026-06-22"}
    assert {row["is_open"] for row in upserted} == {False, True}


def test_sync_trading_calendar_range_from_tushare_retries_rate_limit(monkeypatch):
    attempts = []

    class FakeFrame:
        empty = False

        def to_dict(self, orient):
            return [{"cal_date": "20260622", "is_open": 1}]

    class FakePro:
        def trade_cal(self, **kwargs):
            attempts.append(kwargs)
            if len(attempts) == 1:
                raise Exception("频率超限")
            return FakeFrame()

    class FakeTs:
        @staticmethod
        def pro_api(token):
            return FakePro()

    class FakeConnect:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setitem(__import__("sys").modules, "tushare", FakeTs)
    monkeypatch.setattr(stock_cron_guard, "connect", lambda service: FakeConnect())
    monkeypatch.setattr(stock_cron_guard, "upsert_trading_calendar", lambda conn, rows: len(rows))
    monkeypatch.setattr(stock_cron_guard.time, "sleep", lambda seconds: None)

    count = stock_cron_guard.sync_trading_calendar_range_from_tushare(
        service="test",
        start_date=date(2026, 6, 22),
        end_date=date(2026, 6, 22),
        exchanges=("SH", "SZ"),
        token="token",
        max_retries=2,
        retry_sleep_seconds=0,
    )

    assert count == 2
    assert len(attempts) == 2
