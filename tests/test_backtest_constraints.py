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


def test_one_way_cost_rate_adds_commission_stamp_duty_and_slippage():
    constraints = BacktestExecutionConstraints(
        commission_bps=5.0,
        stamp_duty_bps=10.0,
        slippage_bps=8.0,
    )

    assert one_way_cost_rate("buy", constraints) == 0.0013
    assert one_way_cost_rate("sell", constraints) == 0.0023
