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


def test_backfill_factor_daily_range_skips_complete_dates(monkeypatch):
    calls = []

    monkeypatch.setattr(
        factor_backfill,
        "load_trade_dates_for_backfill",
        lambda **kwargs: ["2026-05-01", "2026-05-04"],
    )
    monkeypatch.setattr(
        factor_backfill,
        "load_complete_factor_dates",
        lambda **kwargs: {"2026-05-01"},
    )
    monkeypatch.setattr(
        factor_backfill,
        "build_and_store_factor_daily",
        lambda **kwargs: calls.append(kwargs) or 10,
    )

    result = factor_backfill.backfill_factor_daily_range(
        start_date="2026-05-01",
        end_date="2026-05-04",
        skip_complete=True,
    )

    assert list(result["trade_date"]) == ["2026-05-04"]
    assert calls == [
        {
            "trade_date": "2026-05-04",
            "lookback_bars": 130,
            "industry_system": "csrc",
        }
    ]


def test_derive_factor_backfill_window_uses_market_bounds_and_lookback(monkeypatch):
    calls = []
    monkeypatch.setattr(
        factor_backfill,
        "load_market_date_bounds",
        lambda adjust_type="hfq": {
            "start_date": "1990-12-19",
            "end_date": "2026-05-08",
            "date_count": 8200,
        },
    )
    monkeypatch.setattr(
        factor_backfill,
        "derive_feature_window",
        lambda **kwargs: calls.append(kwargs)
        or {
            "start_date": "1991-06-20",
            "end_date": "2026-05-08",
            "date_count": 8071,
        },
    )

    window = factor_backfill.derive_factor_backfill_window(lookback_bars=130)

    assert window == {
        "start_date": "1991-06-20",
        "end_date": "2026-05-08",
        "date_count": 8071,
    }
    assert calls == [
        {
            "start_date": "1990-12-19",
            "end_date": "2026-05-08",
            "lookback_bars": 130,
            "adjust_type": "hfq",
        }
    ]


def test_backfill_factor_daily_range_returns_empty_frame_when_all_dates_complete(monkeypatch):
    class RaisingExecutor:
        def __init__(self, **kwargs):
            raise AssertionError("executor should not start when no dates need work")

    monkeypatch.setattr(
        factor_backfill,
        "load_trade_dates_for_backfill",
        lambda **kwargs: ["2026-05-01", "2026-05-04"],
    )
    monkeypatch.setattr(
        factor_backfill,
        "load_complete_factor_dates",
        lambda **kwargs: {"2026-05-01", "2026-05-04"},
    )
    monkeypatch.setattr(factor_backfill, "ProcessPoolExecutor", RaisingExecutor)

    result = factor_backfill.backfill_factor_daily_range(
        start_date="2026-05-01",
        end_date="2026-05-04",
        skip_complete=True,
        workers=2,
    )

    assert result.empty
    assert list(result.columns) == ["trade_date", "factor_rows"]


def test_backfill_factor_daily_range_runs_dates_with_workers(monkeypatch):
    calls = []
    executor_kwargs = []

    class ImmediateExecutor:
        def __init__(self, **kwargs):
            executor_kwargs.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args, **kwargs):
            from concurrent.futures import Future

            future = Future()
            future.set_result(fn(*args, **kwargs))
            return future

    monkeypatch.setattr(factor_backfill, "ProcessPoolExecutor", ImmediateExecutor)
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
        workers=2,
    )

    assert sorted(result["trade_date"]) == ["2026-05-01", "2026-05-04"]
    assert [call["trade_date"] for call in calls] == ["2026-05-01", "2026-05-04"]
    assert executor_kwargs == [{"max_workers": 2, "max_tasks_per_child": 1}]


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
