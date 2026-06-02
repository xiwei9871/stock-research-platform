from stock_research import technical_feature_backfill


def test_backfill_technical_features_daily_range_runs_each_date(monkeypatch):
    calls = []

    monkeypatch.setattr(
        technical_feature_backfill,
        "build_and_store_stock_technical_features_daily",
        lambda **kwargs: calls.append(kwargs) or 12,
    )

    result = technical_feature_backfill.backfill_technical_features_daily_range(
        start_date="2026-05-01",
        end_date="2026-05-02",
        lookback_bars=260,
        adjust_type="qfq",
        source_data_version="bars:v2",
        skip_complete=False,
        trading_days_only=False,
    )

    assert list(result["trade_date"]) == ["2026-05-01", "2026-05-02"]
    assert list(result["feature_rows"]) == [12, 12]
    assert calls == [
        {
            "trade_date": "2026-05-01",
            "lookback_bars": 260,
            "adjust_type": "qfq",
            "source_data_version": "bars:v2",
            "build_strategy": "latest_only",
        },
        {
            "trade_date": "2026-05-02",
            "lookback_bars": 260,
            "adjust_type": "qfq",
            "source_data_version": "bars:v2",
            "build_strategy": "latest_only",
        },
    ]


def test_backfill_technical_features_daily_range_uses_trade_dates_and_reports_progress(
    monkeypatch,
):
    events = []
    calls = []

    monkeypatch.setattr(
        technical_feature_backfill,
        "load_trade_dates_for_backfill",
        lambda **kwargs: ["2026-05-01", "2026-05-06"],
    )
    monkeypatch.setattr(
        technical_feature_backfill,
        "build_and_store_stock_technical_features_daily",
        lambda **kwargs: calls.append(kwargs) or 9,
    )

    result = technical_feature_backfill.backfill_technical_features_daily_range(
        start_date="2026-05-01",
        end_date="2026-05-06",
        source_data_version="bars:v2",
        progress=events.append,
        clock=_fake_clock([1.0, 2.25, 3.0, 4.0]),
    )

    assert list(result["trade_date"]) == ["2026-05-01", "2026-05-06"]
    assert [event["event"] for event in events] == ["start", "done", "start", "done"]
    assert events[1]["elapsed_seconds"] == 1.25
    assert events[1]["feature_rows"] == 9
    assert calls[0]["trade_date"] == "2026-05-01"
    assert calls[1]["trade_date"] == "2026-05-06"
    assert calls[0]["source_data_version"] == "bars:v2"
    assert calls[1]["source_data_version"] == "bars:v2"
    assert calls[0]["build_strategy"] == "latest_only"


def test_backfill_technical_features_daily_range_skips_complete_dates(monkeypatch):
    calls = []

    monkeypatch.setattr(
        technical_feature_backfill,
        "load_trade_dates_for_backfill",
        lambda **kwargs: ["2026-05-01", "2026-05-06"],
    )
    monkeypatch.setattr(
        technical_feature_backfill,
        "load_complete_technical_feature_dates",
        lambda **kwargs: {"2026-05-01"} if kwargs["source_data_version"] == "bars:v2" else set(),
    )
    monkeypatch.setattr(
        technical_feature_backfill,
        "build_and_store_stock_technical_features_daily",
        lambda **kwargs: calls.append(kwargs) or 7,
    )

    result = technical_feature_backfill.backfill_technical_features_daily_range(
        start_date="2026-05-01",
        end_date="2026-05-06",
        skip_complete=True,
        source_data_version="bars:v2",
    )

    assert list(result["trade_date"]) == ["2026-05-06"]
    assert calls == [
        {
            "trade_date": "2026-05-06",
            "lookback_bars": 260,
            "adjust_type": "qfq",
            "source_data_version": "bars:v2",
            "build_strategy": "latest_only",
        }
    ]


def test_backfill_technical_features_daily_range_passes_build_strategy(monkeypatch):
    calls = []

    monkeypatch.setattr(
        technical_feature_backfill,
        "build_and_store_stock_technical_features_daily",
        lambda **kwargs: calls.append(kwargs) or 5,
    )

    technical_feature_backfill.backfill_technical_features_daily_range(
        start_date="2026-05-01",
        end_date="2026-05-01",
        adjust_type="qfq",
        source_data_version="bars:v2",
        trading_days_only=False,
        build_strategy="latest_only",
    )

    assert calls == [
        {
            "trade_date": "2026-05-01",
            "lookback_bars": 260,
            "adjust_type": "qfq",
            "source_data_version": "bars:v2",
            "build_strategy": "latest_only",
        }
    ]


def test_backfill_technical_features_daily_range_returns_empty_frame_when_all_dates_complete(
    monkeypatch,
):
    class RaisingExecutor:
        def __init__(self, **kwargs):
            raise AssertionError("executor should not start when no dates need work")

    monkeypatch.setattr(
        technical_feature_backfill,
        "load_trade_dates_for_backfill",
        lambda **kwargs: ["2026-05-01", "2026-05-06"],
    )
    monkeypatch.setattr(
        technical_feature_backfill,
        "load_complete_technical_feature_dates",
        lambda **kwargs: {"2026-05-01", "2026-05-06"},
    )
    monkeypatch.setattr(
        technical_feature_backfill,
        "ProcessPoolExecutor",
        RaisingExecutor,
    )

    result = technical_feature_backfill.backfill_technical_features_daily_range(
        start_date="2026-05-01",
        end_date="2026-05-06",
        skip_complete=True,
        workers=2,
    )

    assert result.empty
    assert list(result.columns) == ["trade_date", "feature_rows"]


def test_derive_technical_feature_backfill_window_uses_market_bounds_and_lookback(
    monkeypatch,
):
    monkeypatch.setattr(
        technical_feature_backfill,
        "load_market_date_bounds",
        lambda adjust_type="qfq": {
            "start_date": "1990-12-19",
            "end_date": "2026-05-08",
            "date_count": 8200,
        },
    )
    window = technical_feature_backfill.derive_technical_feature_backfill_window(
        lookback_bars=260,
        adjust_type="qfq",
    )

    assert window == {
        "start_date": "1990-12-19",
        "end_date": "2026-05-08",
        "date_count": 8200,
    }


def test_load_complete_technical_feature_dates_matches_asset_sets_not_only_counts(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params):
        calls.append((sql, params))
        return [{"trade_date": "2026-05-01"}]

    monkeypatch.setattr(
        technical_feature_backfill,
        "connect",
        lambda service: _context(object()),
    )
    monkeypatch.setattr(technical_feature_backfill, "fetch_all", fake_fetch_all)

    result = technical_feature_backfill.load_complete_technical_feature_dates(
        start_date="2026-05-01",
        end_date="2026-05-06",
        adjust_type="qfq",
        calc_version="v1",
        source_data_version="market_daily_bar:qfq@v2",
    )

    assert result == {"2026-05-01"}
    assert "expected_assets" in calls[0][0]
    assert "actual_assets" in calls[0][0]
    assert "asset_id" in calls[0][0]
    assert "NOT EXISTS" in calls[0][0]


def test_load_complete_technical_feature_dates_uses_per_date_asset_completeness(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params):
        calls.append((sql, params))
        return [{"trade_date": "2026-05-01"}, {"trade_date": "2026-05-06"}]

    monkeypatch.setattr(
        technical_feature_backfill,
        "connect",
        lambda service: _context(object()),
    )
    monkeypatch.setattr(technical_feature_backfill, "fetch_all", fake_fetch_all)

    result = technical_feature_backfill.load_complete_technical_feature_dates(
        start_date="2026-05-01",
        end_date="2026-05-06",
        adjust_type="qfq",
        calc_version="v1",
        source_data_version="market_daily_bar:qfq",
    )

    assert result == {"2026-05-01", "2026-05-06"}
    assert "market_daily_bar" in calls[0][0]
    assert "stock_technical_features_daily" in calls[0][0]
    assert calls[0][1] == [
        "qfq",
        "2026-05-01",
        "2026-05-06",
        "qfq",
        "technical_features",
        "market_daily_bar:qfq",
        "v1",
        "2026-05-01",
        "2026-05-06",
    ]


def test_backfill_technical_features_daily_range_worker_progress_uses_scheduled_date_order(
    monkeypatch,
):
    progress_events = []

    class ImmediateExecutor:
        def __init__(self, **kwargs):
            self.futures = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args, **kwargs):
            from concurrent.futures import Future

            future = Future()
            future.set_result(fn(*args, **kwargs))
            self.futures.append(future)
            return future

    monkeypatch.setattr(technical_feature_backfill, "ProcessPoolExecutor", ImmediateExecutor)
    monkeypatch.setattr(
        technical_feature_backfill,
        "load_trade_dates_for_backfill",
        lambda **kwargs: ["2026-05-01", "2026-05-02"],
    )
    monkeypatch.setattr(
        technical_feature_backfill,
        "build_and_store_stock_technical_features_daily",
        lambda **kwargs: 5 if kwargs["trade_date"] == "2026-05-01" else 6,
    )
    monkeypatch.setattr(
        technical_feature_backfill,
        "as_completed",
        lambda futures: [list(futures)[1], list(futures)[0]],
    )

    result = technical_feature_backfill.backfill_technical_features_daily_range(
        start_date="2026-05-01",
        end_date="2026-05-02",
        workers=2,
        progress=progress_events.append,
    )

    assert list(result["trade_date"]) == ["2026-05-01", "2026-05-02"]
    assert progress_events == [
        {
            "event": "done",
            "trade_date": "2026-05-02",
            "feature_rows": 6,
            "elapsed_seconds": progress_events[0]["elapsed_seconds"],
            "index": 2,
            "total": 2,
        },
        {
            "event": "done",
            "trade_date": "2026-05-01",
            "feature_rows": 5,
            "elapsed_seconds": progress_events[1]["elapsed_seconds"],
            "index": 1,
            "total": 2,
        },
    ]


def test_backfill_technical_features_daily_range_reuses_workers_for_parallel_dates(
    monkeypatch,
):
    executor_kwargs = []

    class ImmediateExecutor:
        def __init__(self, **kwargs):
            executor_kwargs.append(kwargs)
            self.futures = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args, **kwargs):
            from concurrent.futures import Future

            future = Future()
            future.set_result(fn(*args, **kwargs))
            self.futures.append(future)
            return future

    monkeypatch.setattr(technical_feature_backfill, "ProcessPoolExecutor", ImmediateExecutor)
    monkeypatch.setattr(
        technical_feature_backfill,
        "load_trade_dates_for_backfill",
        lambda **kwargs: ["2026-05-01", "2026-05-02"],
    )
    monkeypatch.setattr(
        technical_feature_backfill,
        "build_and_store_stock_technical_features_daily",
        lambda **kwargs: 5,
    )

    technical_feature_backfill.backfill_technical_features_daily_range(
        start_date="2026-05-01",
        end_date="2026-05-02",
        workers=2,
    )

    assert executor_kwargs == [{"max_workers": 2}]


def test_run_technical_feature_backfill_benchmark_current_uses_serial_workers(monkeypatch):
    calls = []

    monkeypatch.setattr(
        technical_feature_backfill,
        "backfill_technical_features_daily_range",
        lambda **kwargs: calls.append(kwargs)
        or __import__("pandas").DataFrame(
            [
                {"trade_date": "2026-05-01", "feature_rows": 10},
                {"trade_date": "2026-05-02", "feature_rows": 20},
            ]
        ),
    )

    result = technical_feature_backfill.run_technical_feature_backfill_benchmark(
        start_date="2026-05-01",
        end_date="2026-05-02",
        adjust_type="qfq",
        lookback_bars=260,
        workers=4,
        strategy="current",
        source_data_version="market_daily_bar:qfq@bench_demo",
    )

    assert calls == [
        {
            "start_date": "2026-05-01",
            "end_date": "2026-05-02",
            "lookback_bars": 260,
            "adjust_type": "qfq",
            "source_data_version": "market_daily_bar:qfq@bench_demo",
            "workers": 1,
            "skip_complete": False,
            "build_strategy": "legacy",
            "trading_days_only": True,
            "progress": None,
        }
    ]
    assert result["strategy"] == "current"
    assert result["workers"] == 1
    assert result["dates"] == 2
    assert result["rows"] == 30


def test_run_technical_feature_backfill_benchmark_parallel_dates_uses_requested_workers(monkeypatch):
    calls = []

    monkeypatch.setattr(
        technical_feature_backfill,
        "backfill_technical_features_daily_range",
        lambda **kwargs: calls.append(kwargs)
        or __import__("pandas").DataFrame(
            [{"trade_date": "2026-05-01", "feature_rows": 15}]
        ),
    )

    result = technical_feature_backfill.run_technical_feature_backfill_benchmark(
        start_date="2026-05-01",
        end_date="2026-05-01",
        adjust_type="qfq",
        lookback_bars=260,
        workers=4,
        strategy="parallel_dates",
        source_data_version="market_daily_bar:qfq@bench_demo",
    )

    assert calls == [
        {
            "start_date": "2026-05-01",
            "end_date": "2026-05-01",
            "lookback_bars": 260,
            "adjust_type": "qfq",
            "source_data_version": "market_daily_bar:qfq@bench_demo",
            "workers": 4,
            "skip_complete": False,
            "build_strategy": "legacy",
            "trading_days_only": True,
            "progress": None,
        }
    ]
    assert result["strategy"] == "parallel_dates"
    assert result["workers"] == 4
    assert result["dates"] == 1
    assert result["rows"] == 15


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
