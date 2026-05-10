from stock_research.factor_backfill import build_trade_date_range
from stock_research import factor_backfill


def test_build_trade_date_range_returns_inclusive_daily_strings():
    assert build_trade_date_range("2026-05-01", "2026-05-03") == [
        "2026-05-01",
        "2026-05-02",
        "2026-05-03",
    ]


def test_backfill_factor_daily_range_runs_each_date(monkeypatch):
    calls = []

    monkeypatch.setattr(
        factor_backfill,
        "build_and_store_factor_daily",
        lambda **kwargs: calls.append(kwargs) or 10,
    )

    result = factor_backfill.backfill_factor_daily_range(
        start_date="2026-05-01",
        end_date="2026-05-02",
        lookback_bars=130,
        industry_system="csrc",
        trading_days_only=False,
    )

    assert list(result["trade_date"]) == ["2026-05-01", "2026-05-02"]
    assert list(result["factor_rows"]) == [10, 10]
    assert calls[0]["trade_date"] == "2026-05-01"
    assert calls[1]["trade_date"] == "2026-05-02"


def test_load_trade_dates_for_backfill_queries_market_calendar(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params):
        calls.append((sql, params))
        return [{"trade_date": "2026-05-01"}, {"trade_date": "2026-05-04"}]

    monkeypatch.setattr(factor_backfill, "connect", lambda service: _context(object()))
    monkeypatch.setattr(factor_backfill, "fetch_all", fake_fetch_all)

    result = factor_backfill.load_trade_dates_for_backfill(
        "2026-05-01",
        "2026-05-04",
        adjust_type="hfq",
    )

    assert result == ["2026-05-01", "2026-05-04"]
    assert "SELECT DISTINCT trade_date" in calls[0][0]
    assert calls[0][1] == ["hfq", "2026-05-01", "2026-05-04"]


def test_backfill_factor_daily_range_uses_trade_dates_and_reports_progress(monkeypatch):
    events = []
    calls = []

    monkeypatch.setattr(
        factor_backfill,
        "load_trade_dates_for_backfill",
        lambda **kwargs: ["2026-05-01", "2026-05-04"],
    )
    monkeypatch.setattr(
        factor_backfill,
        "build_and_store_factor_daily",
        lambda **kwargs: calls.append(kwargs) or 10,
    )

    result = factor_backfill.backfill_factor_daily_range(
        start_date="2026-05-01",
        end_date="2026-05-04",
        progress=events.append,
        clock=_fake_clock([1.0, 2.5, 3.0, 4.0]),
    )

    assert list(result["trade_date"]) == ["2026-05-01", "2026-05-04"]
    assert [event["event"] for event in events] == [
        "start",
        "done",
        "start",
        "done",
    ]
    assert events[1]["elapsed_seconds"] == 1.5
    assert calls[0]["trade_date"] == "2026-05-01"
    assert calls[1]["trade_date"] == "2026-05-04"


class _context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False


def _fake_clock(values):
    iterator = iter(values)
    return lambda: next(iterator)
