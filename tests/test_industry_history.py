from stock_research import industry_history


class FakeClock:
    def __init__(self, values):
        self.values = list(values)

    def __call__(self):
        return self.values.pop(0)


def test_benchmark_industry_day_times_sync_and_build_steps():
    calls = []

    result = industry_history.benchmark_industry_day(
        trade_date="2024-05-31",
        industry_system="csrc",
        adjust_type="hfq",
        sync_func=lambda trade_date: calls.append(("sync", trade_date)) or 5326,
        build_func=lambda **kwargs: calls.append(("build", kwargs)),
        timer=FakeClock([10.0, 31.5, 31.5, 31.9]),
    )

    assert result == {
        "trade_date": "2024-05-31",
        "membership_rows": 5326,
        "sync_seconds": 21.5,
        "build_seconds": 0.4,
        "total_seconds": 21.9,
    }
    assert calls == [
        ("sync", "2024-05-31"),
        (
            "build",
            {
                "start_date": "2024-05-31",
                "end_date": "2024-05-31",
                "industry_system": "csrc",
                "adjust_type": "hfq",
            },
        ),
    ]


def test_build_industry_history_dates_honors_max_dates():
    assert industry_history.build_industry_history_dates(
        start_date="2024-05-29",
        end_date="2024-06-03",
        max_dates=3,
    ) == ["2024-05-29", "2024-05-30", "2024-05-31"]


def test_build_industry_history_dates_supports_monthly_frequency():
    assert industry_history.build_industry_history_dates(
        start_date="2024-05-10",
        end_date="2024-07-20",
        frequency="monthly",
    ) == ["2024-05-31", "2024-06-30", "2024-07-20"]


def test_build_industry_history_dates_supports_quarterly_frequency():
    assert industry_history.build_industry_history_dates(
        start_date="2024-02-10",
        end_date="2024-08-20",
        frequency="quarterly",
    ) == ["2024-03-31", "2024-06-30", "2024-08-20"]


def test_run_industry_history_range_reports_progress():
    progress = []

    result = industry_history.run_industry_history_range(
        start_date="2024-05-29",
        end_date="2024-05-30",
        max_dates=2,
        frequency="daily",
        industry_system="csrc",
        adjust_type="hfq",
        use_cache=True,
        benchmark_func=lambda trade_date, industry_system, adjust_type: {
            "trade_date": trade_date,
            "membership_rows": 10,
            "sync_seconds": 1.0,
            "build_seconds": 0.1,
            "total_seconds": 1.1,
        },
        progress=progress.append,
        timer=FakeClock([100.0, 102.5]),
    )

    assert result == {
        "dates": 2,
        "membership_rows": 20,
        "seconds": 2.5,
        "start_date": "2024-05-29",
        "end_date": "2024-05-30",
    }
    assert progress == [
        {
            "event": "date_done",
            "trade_date": "2024-05-29",
            "index": 1,
            "total": 2,
            "membership_rows": 10,
            "seconds": 1.1,
        },
        {
            "event": "date_done",
            "trade_date": "2024-05-30",
            "index": 2,
            "total": 2,
            "membership_rows": 10,
            "seconds": 1.1,
        },
    ]


def test_run_industry_history_range_uses_monthly_dates_and_cache_flag():
    calls = []

    result = industry_history.run_industry_history_range(
        start_date="2024-05-01",
        end_date="2024-06-15",
        max_dates=10,
        frequency="monthly",
        industry_system="csrc",
        adjust_type="hfq",
        use_cache=False,
        benchmark_func=lambda **kwargs: calls.append(kwargs) or {
            "trade_date": kwargs["trade_date"],
            "membership_rows": 1,
            "sync_seconds": 1.0,
            "build_seconds": 0.1,
            "total_seconds": 1.1,
        },
        timer=FakeClock([1.0, 3.0]),
    )

    assert [call["trade_date"] for call in calls] == ["2024-05-31", "2024-06-15"]
    assert all(call["use_cache"] is False for call in calls)
    assert result["dates"] == 2
