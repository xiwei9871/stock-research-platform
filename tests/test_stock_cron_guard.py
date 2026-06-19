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
