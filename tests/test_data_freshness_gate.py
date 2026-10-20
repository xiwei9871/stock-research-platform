from __future__ import annotations

import pandas as pd
import pytest

from stock_research.data_freshness_gate import (
    BLOCKED,
    DEGRADED,
    READY,
    NOT_EVALUATED,
    InputSpec,
    check_table_input,
    evaluate_input_status,
    expected_trade_date_for_window,
    missing_trading_days,
)


CAL = pd.DataFrame(
    {
        "trade_date": [
            "2026-10-16",  # Fri open
            "2026-10-17",  # Sat closed
            "2026-10-18",  # Sun closed
            "2026-10-19",  # Mon open
            "2026-10-20",  # Tue open
        ],
        "is_open": [True, False, False, True, True],
    }
)


def test_expected_trade_date_skips_weekend_for_post_close():
    # as_of 10-19 (Mon, open day already closed) -> expected = 10-19
    assert expected_trade_date_for_window(CAL, "2026-10-19", window="post_close") == "2026-10-19"
    # as_of 10-18 (Sun, closed) -> expected = 10-16
    assert expected_trade_date_for_window(CAL, "2026-10-18", window="post_close") == "2026-10-16"


def test_expected_trade_date_intraday_window_uses_today_when_open():
    # 09:25 snapshot window on an open day may legitimately target today
    assert expected_trade_date_for_window(CAL, "2026-10-20", window="intraday") == "2026-10-20"


def test_missing_trading_days_finds_intermediate_gap_not_just_max():
    present = ["2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19"]
    cal_days = ["2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20"]
    missing = missing_trading_days(present, cal_days)
    assert missing == ["2026-10-20"]


def test_missing_trading_days_detects_gap_behind_fresh_latest():
    # latest looks fresh but a mid-range hole must still surface
    present = ["2026-10-14", "2026-10-16", "2026-10-19", "2026-10-20"]
    cal_days = ["2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20"]
    assert missing_trading_days(present, cal_days) == ["2026-10-15"]


def test_required_input_missing_day_is_blocked():
    status = evaluate_input_status(
        category="required_daily",
        expected_date="2026-10-19",
        latest_date="2026-10-16",
        missing_dates=["2026-10-19"],
        coverage_actual=5000,
        coverage_min=5000,
    )
    assert status == BLOCKED


def test_required_input_low_coverage_is_blocked_even_if_date_fresh():
    status = evaluate_input_status(
        category="required_daily",
        expected_date="2026-10-19",
        latest_date="2026-10-19",
        missing_dates=[],
        coverage_actual=10,  # suspended/partial day
        coverage_min=5000,
    )
    assert status == BLOCKED


def test_optional_enhancement_stale_is_degraded_not_blocked():
    status = evaluate_input_status(
        category="optional_enhancement",
        expected_date="2026-10-19",
        latest_date="2026-09-07",
        missing_dates=["2026-10-19"],
        coverage_actual=0,
        coverage_min=None,
    )
    assert status == DEGRADED


def test_static_frozen_input_never_date_compared():
    status = evaluate_input_status(
        category="static_frozen",
        expected_date="2026-10-19",
        latest_date="2026-06-12",  # frozen by design
        missing_dates=[],
        coverage_actual=None,
        coverage_min=None,
        file_exists=True,
    )
    assert status == READY


def test_static_frozen_missing_file_is_blocked():
    status = evaluate_input_status(
        category="static_frozen",
        expected_date="2026-10-19",
        latest_date=None,
        missing_dates=[],
        coverage_actual=None,
        coverage_min=None,
        file_exists=False,
    )
    assert status == BLOCKED


def test_unused_input_is_not_evaluated():
    status = evaluate_input_status(
        category="unused",
        expected_date="2026-10-19",
        latest_date="2026-06-09",
        missing_dates=["2026-10-19"],
        coverage_actual=58,
        coverage_min=None,
    )
    assert status == NOT_EVALUATED


def test_check_table_input_uses_injected_fetcher():
    spec = InputSpec(
        name="market_daily_bar",
        category="required_daily",
        kind="table",
        table="public.market_daily_bar",
        date_column="trade_date",
        coverage_column="asset_id",
        min_daily_rows=5000,
        consumers=("tech_bottleneck", "mid_trend", "lhb_shortline"),
    )
    cal = CAL.copy()

    def fake_fetcher(sql, params):
        if "trading_calendar" in sql:
            return cal.to_dict("records")
        if "DISTINCT" in sql:
            return [{"trade_date": "2026-10-16"}, {"trade_date": "2026-10-19"}]
        return [{"row_count": 5200, "asset_count": 5200, "latest_trade_date": "2026-10-19"}]

    health = check_table_input(spec, as_of_date="2026-10-19", fetcher=fake_fetcher)
    assert health["expected_trade_date"] == "2026-10-19"
    assert health["actual_latest_date"] == "2026-10-19"
    assert health["freshness_status"] == READY
    assert health["consumer"] == spec.consumers
    assert "coverage" in health
