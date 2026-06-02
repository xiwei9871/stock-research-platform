import pandas as pd
import pytest

from stock_research.backtest_constraints import (
    BacktestExecutionConstraints,
    can_close_long,
    can_open_long,
    one_way_cost_rate,
)


def test_can_open_long_blocks_suspended_and_limit_up_bars():
    constraints = BacktestExecutionConstraints()

    allowed, reason = can_open_long(
        {
            "trade_status": "1",
            "is_suspended": True,
            "is_limit_up": False,
            "amount": 100_000_000.0,
        },
        constraints,
    )
    assert allowed is False
    assert reason == "suspended"

    allowed, reason = can_open_long(
        {
            "trade_status": "1",
            "is_suspended": False,
            "is_limit_up": True,
            "amount": 100_000_000.0,
        },
        constraints,
    )
    assert allowed is False
    assert reason == "limit_up"


def test_can_close_long_blocks_limit_down_when_enabled():
    constraints = BacktestExecutionConstraints(block_limit_down_sell=True)

    allowed, reason = can_close_long(
        {
            "trade_status": "1",
            "is_suspended": False,
            "is_limit_down": True,
            "amount": 100_000_000.0,
        },
        constraints,
    )

    assert allowed is False
    assert reason == "limit_down"


def test_can_open_long_treats_nan_amount_as_low_amount_when_min_amount_is_set():
    constraints = BacktestExecutionConstraints(min_amount=10.0)

    allowed, reason = can_open_long(
        {
            "trade_status": "1",
            "is_suspended": False,
            "is_limit_up": False,
            "amount": float("nan"),
        },
        constraints,
    )

    assert allowed is False
    assert reason == "low_amount"


def test_flag_parsing_handles_string_and_na_like_values_safely():
    constraints = BacktestExecutionConstraints()

    allowed, reason = can_open_long(
        {
            "trade_status": "1",
            "is_suspended": "false",
            "is_limit_up": "0",
            "amount": 100.0,
        },
        constraints,
    )
    assert allowed is True
    assert reason is None

    allowed, reason = can_close_long(
        {
            "trade_status": "1",
            "is_suspended": pd.NA,
            "is_limit_down": "no",
            "amount": 100.0,
        },
        constraints,
    )
    assert allowed is True
    assert reason is None


@pytest.mark.parametrize("trade_status", [None, "bad", pd.NA, 1, 1.0, True])
def test_non_exact_trade_status_values_block_when_suspended_checks_are_enabled(trade_status):
    constraints = BacktestExecutionConstraints()

    allowed, reason = can_open_long(
        {
            "trade_status": trade_status,
            "is_suspended": False,
            "is_limit_up": False,
            "amount": 100.0,
        },
        constraints,
    )

    assert allowed is False
    assert reason == "suspended"


def test_exact_string_trade_status_one_is_allowed_under_suspended_checks():
    constraints = BacktestExecutionConstraints()

    allowed, reason = can_open_long(
        {
            "trade_status": "1",
            "is_suspended": False,
            "is_limit_up": False,
            "amount": 100.0,
        },
        constraints,
    )

    assert allowed is True
    assert reason is None


def test_one_way_cost_rate_adds_commission_stamp_duty_and_slippage():
    constraints = BacktestExecutionConstraints(
        commission_bps=5.0,
        stamp_duty_bps=10.0,
        slippage_bps=8.0,
    )

    assert one_way_cost_rate("buy", constraints) == 0.0013
    assert one_way_cost_rate("sell", constraints) == 0.0023


def test_one_way_cost_rate_rejects_unsupported_side():
    constraints = BacktestExecutionConstraints()

    with pytest.raises(ValueError, match="unsupported side"):
        one_way_cost_rate("hold", constraints)


@pytest.mark.parametrize(
    ("field", "kwargs"),
    [
        ("commission_bps", {"commission_bps": -0.1}),
        ("stamp_duty_bps", {"stamp_duty_bps": -0.1}),
        ("slippage_bps", {"slippage_bps": -0.1}),
        ("min_amount", {"min_amount": -1.0}),
    ],
)
def test_negative_config_values_are_rejected(field, kwargs):
    with pytest.raises(ValueError, match=field):
        BacktestExecutionConstraints(**kwargs)


@pytest.mark.parametrize(
    ("field", "kwargs"),
    [
        ("commission_bps", {"commission_bps": float("nan")}),
        ("stamp_duty_bps", {"stamp_duty_bps": float("nan")}),
        ("slippage_bps", {"slippage_bps": float("nan")}),
        ("min_amount", {"min_amount": float("nan")}),
    ],
)
def test_nan_config_values_are_rejected(field, kwargs):
    with pytest.raises(ValueError, match=field):
        BacktestExecutionConstraints(**kwargs)


def test_malformed_amount_is_rejected_as_low_amount():
    constraints = BacktestExecutionConstraints(min_amount=10.0)

    allowed, reason = can_open_long(
        {
            "trade_status": "1",
            "is_suspended": False,
            "is_limit_up": False,
            "amount": "not-a-number",
        },
        constraints,
    )

    assert allowed is False
    assert reason == "low_amount"
