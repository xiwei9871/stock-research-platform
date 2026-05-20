import json
from pathlib import Path

import pandas as pd
import pytest

from stock_research import cli
import stock_research.retention_backtest as retention_backtest
from stock_research.backtest import BacktestSelection
from stock_research.backtest_constraints import BacktestExecutionConstraints
from stock_research.retention_backtest import (
    RetentionConfig,
    RetentionResult,
    simulate_retention_config,
)
from stock_research.services.universe_service import (
    UniverseConfig,
    UniverseMember,
    UniverseResult,
)


def _features(selection_date: str, assets: list[tuple[str, float]]) -> pd.DataFrame:
    rows = []
    for asset_id, ret_20d in assets:
        values = {
            "ret_5d": ret_20d / 4,
            "ret_20d": ret_20d,
            "ret_60d": ret_20d / 2,
            "amount_20d_avg": 100000000.0,
            "volatility_20d": 0.02,
            "ma20_deviation": 0.05,
            "max_drawdown_20d": -0.03,
        }
        for feature_name, feature_value in values.items():
            rows.append(
                {
                    "asset_id": asset_id,
                    "trade_date": selection_date,
                    "feature_name": feature_name,
                    "feature_value": feature_value,
                }
            )
    return pd.DataFrame(rows)


def _features_with_values(
    selection_date: str,
    assets: list[tuple[str, dict[str, float]]],
) -> pd.DataFrame:
    rows = []
    defaults = {
        "ret_5d": 0.03,
        "ret_20d": 0.10,
        "ret_60d": 0.05,
        "amount_20d_avg": 100000000.0,
        "volatility_20d": 0.02,
        "ma20_deviation": 0.05,
        "max_drawdown_20d": -0.03,
    }
    for asset_id, overrides in assets:
        values = defaults | overrides
        for feature_name, feature_value in values.items():
            rows.append(
                {
                    "asset_id": asset_id,
                    "trade_date": selection_date,
                    "feature_name": feature_name,
                    "feature_value": feature_value,
                }
            )
    return pd.DataFrame(rows)


def _bars(asset_prices: dict[str, dict[str, float | None]]) -> pd.DataFrame:
    rows = []
    for asset_id, prices_by_date in asset_prices.items():
        for trade_date, open_price in prices_by_date.items():
            rows.append(
                {
                    "asset_id": asset_id,
                    "trade_date": trade_date,
                    "open": open_price,
                    "preclose": open_price,
                    "close": open_price,
                    "amount": 100000000.0,
                    "turnover_rate": 1.0,
                    "trade_status": "1",
                    "is_st": False,
                }
            )
    return pd.DataFrame(rows)


def _universe_result(
    included: list[tuple[str, str]],
    excluded: list[tuple[str, str]] | None = None,
) -> UniverseResult:
    config = UniverseConfig(as_of_date="2026-01-02")
    members: list[UniverseMember] = []
    for asset_id, stock_code in included:
        members.append(
            UniverseMember(
                trade_date="2026-01-02",
                asset_id=asset_id,
                stock_code=stock_code,
                stock_name=stock_code,
                board="main",
                listed_days=1000,
                is_st=False,
                is_suspended=False,
                avg_turnover_amount=100000000.0,
                avg_volume=10000000.0,
                industry="Bank",
                included=True,
                include_reasons=["board_allowed:main"],
                exclude_reasons=[],
            )
        )
    for asset_id, stock_code in excluded or []:
        members.append(
            UniverseMember(
                trade_date="2026-01-02",
                asset_id=asset_id,
                stock_code=stock_code,
                stock_name=stock_code,
                board="main",
                listed_days=1000,
                is_st=False,
                is_suspended=False,
                avg_turnover_amount=100000000.0,
                avg_volume=10000000.0,
                industry="Bank",
                included=False,
                include_reasons=[],
                exclude_reasons=["manual_exclude"],
            )
        )
    return UniverseResult(
        config=config,
        as_of_date="2026-01-02",
        total_candidates=len(members),
        included_count=sum(1 for member in members if member.included),
        excluded_count=sum(1 for member in members if not member.included),
        members=members,
        included_codes=[member.stock_code for member in members if member.included],
        excluded_codes=[member.stock_code for member in members if not member.included],
        summary_by_reason={"include": {"board_allowed:main": len(included)}, "exclude": {}},
        warnings=[],
    )


def test_retention_holds_while_asset_stays_in_top20_and_exits_after_drop():
    feature_frame = pd.concat(
        [
            _features("2026-01-02", [("A", 0.30)]),
            _features("2026-01-05", [("A", 0.30)]),
            _features("2026-01-06", [("B", 0.40)]),
        ],
        ignore_index=True,
    )
    bar_frame = _bars(
        {
            "A": {
                "2026-01-02": 10.0,
                "2026-01-05": 10.0,
                "2026-01-06": 11.0,
                "2026-01-07": 12.0,
            },
            "B": {
                "2026-01-06": 20.0,
                "2026-01-07": 20.0,
            },
        }
    )
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-07",
        initial_cash=10000.0,
        max_positions=1,
        strategy_id="unit",
    )

    result = simulate_retention_config(feature_frame, bar_frame, config)

    closed = result.trades[result.trades["status"] == "closed"]
    assert len(closed) == 1
    trade = closed.iloc[0]
    assert trade["asset_id"] == "A"
    assert trade["selection_date"] == "2026-01-02"
    assert trade["buy_date"] == "2026-01-05"
    assert trade["sell_signal_date"] == "2026-01-06"
    assert trade["sell_date"] == "2026-01-07"
    assert trade["status"] == "closed"
    assert trade["exit_reason"] == "exit_top20"


def test_retention_does_not_rebuy_asset_sold_for_leaving_top20_on_same_signal_day():
    feature_frame = pd.concat(
        [
            _features("2026-01-02", [("A", 0.40), ("C", 0.30)]),
            _features("2026-01-05", [("B", 0.50), ("C", 0.30)]),
        ],
        ignore_index=True,
    )
    bar_frame = _bars(
        {
            "A": {
                "2026-01-02": 10.0,
                "2026-01-05": 10.0,
                "2026-01-06": 10.0,
            },
            "B": {
                "2026-01-05": 20.0,
                "2026-01-06": 20.0,
            },
            "C": {
                "2026-01-02": 40.0,
                "2026-01-05": 40.0,
                "2026-01-06": 40.0,
            },
        }
    )
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-06",
        initial_cash=20000.0,
        max_positions=2,
        strategy_id="unit",
    )

    result = simulate_retention_config(feature_frame, bar_frame, config)

    a_trades = result.trades[result.trades["asset_id"] == "A"]
    assert len(a_trades) == 1
    assert a_trades.iloc[0]["status"] == "closed"
    assert a_trades.iloc[0]["sell_signal_date"] == "2026-01-05"
    assert a_trades.iloc[0]["sell_date"] == "2026-01-06"

    bought_assets = set(result.trades.loc[result.trades["status"] != "skipped", "asset_id"])
    assert "B" in bought_assets


def test_retention_retries_replacement_buy_after_exit_sell_rolls_forward():
    feature_frame = pd.concat(
        [
            _features("2026-01-02", [("A", 0.30)]),
            _features("2026-01-05", [("A", 0.30)]),
            _features("2026-01-06", [("B", 0.40)]),
        ],
        ignore_index=True,
    )
    bar_frame = _bars(
        {
            "A": {
                "2026-01-02": 10.0,
                "2026-01-05": 10.0,
                "2026-01-06": 10.0,
                "2026-01-07": None,
                "2026-01-08": 11.0,
            },
            "B": {
                "2026-01-06": 20.0,
                "2026-01-07": 20.0,
                "2026-01-08": 20.0,
            },
        }
    )
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-07",
        initial_cash=10000.0,
        max_positions=1,
        strategy_id="unit",
    )

    result = simulate_retention_config(feature_frame, bar_frame, config)

    a_trade = result.trades[result.trades["asset_id"] == "A"].iloc[0]
    assert a_trade["status"] == "closed"
    assert a_trade["sell_signal_date"] == "2026-01-06"
    assert a_trade["sell_date"] == "2026-01-08"

    b_trades = result.trades[result.trades["asset_id"] == "B"]
    assert len(b_trades) == 1
    b_trade = b_trades.iloc[0]
    assert b_trade["status"] == "open"
    assert b_trade["buy_date"] == "2026-01-08"
    assert b_trade["skip_reason"] is None
    assert not (
        (result.trades["asset_id"] == "B")
        & (result.trades["skip_reason"] == "no_capacity")
    ).any()


def test_retention_sizes_pending_buy_with_execution_day_equity():
    feature_frame = pd.concat(
        [
            _features("2026-01-02", [("A", 0.40)]),
            _features("2026-01-05", [("A", 0.40), ("B", 0.30)]),
        ],
        ignore_index=True,
    )
    bar_frame = _bars(
        {
            "A": {
                "2026-01-02": 12.0,
                "2026-01-05": 12.0,
                "2026-01-06": 20.0,
            },
            "B": {
                "2026-01-05": 37.0,
                "2026-01-06": 37.0,
            },
        }
    )
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-06",
        initial_cash=22000.0,
        max_positions=2,
        strategy_id="unit",
    )

    result = simulate_retention_config(feature_frame, bar_frame, config)

    b_trade = result.trades[result.trades["asset_id"] == "B"].iloc[0]
    assert b_trade["status"] == "open"
    assert b_trade["buy_date"] == "2026-01-06"
    assert b_trade["shares"] == 300
    assert b_trade["buy_value"] == pytest.approx(11100.0)


def test_retention_does_not_open_new_positions_after_end_date():
    feature_frame = _features("2026-01-05", [("A", 0.30)])
    bar_frame = _bars(
        {
            "A": {
                "2026-01-05": 10.0,
                "2026-01-06": 10.0,
            },
        }
    )
    config = RetentionConfig(
        start_date="2026-01-05",
        end_date="2026-01-05",
        initial_cash=10000.0,
        max_positions=1,
        strategy_id="unit",
    )

    result = simulate_retention_config(feature_frame, bar_frame, config)

    assert result.trades.empty
    assert list(result.equity_curve["date"]) == ["2026-01-05"]
    assert result.equity_curve.iloc[-1]["open_positions"] == 0


def test_retention_uses_target_equal_weight_integer_lots():
    feature_frame = _features("2026-01-02", [("A", 0.30)])
    bar_frame = _bars(
        {
            "A": {
                "2026-01-02": 37.0,
                "2026-01-05": 37.0,
            },
        }
    )
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-05",
        initial_cash=500000.0,
        max_positions=5,
        strategy_id="unit",
    )

    result = simulate_retention_config(feature_frame, bar_frame, config)

    assert len(result.trades) == 1
    trade = result.trades.iloc[0]
    assert trade["asset_id"] == "A"
    assert trade["buy_date"] == "2026-01-05"
    assert trade["shares"] == 2700
    assert trade["buy_value"] == pytest.approx(99900.0)


def test_retention_skips_limit_up_buy_via_shared_constraints():
    feature_frame = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-01-05", "feature_name": "ret_5d", "feature_value": 0.05},
            {"asset_id": "A", "trade_date": "2026-01-05", "feature_name": "ret_20d", "feature_value": 0.15},
            {"asset_id": "A", "trade_date": "2026-01-05", "feature_name": "ret_60d", "feature_value": 0.10},
            {"asset_id": "A", "trade_date": "2026-01-05", "feature_name": "amount_20d_avg", "feature_value": 100000000.0},
            {"asset_id": "A", "trade_date": "2026-01-05", "feature_name": "volatility_20d", "feature_value": 0.02},
            {"asset_id": "A", "trade_date": "2026-01-05", "feature_name": "ma20_deviation", "feature_value": 0.05},
            {"asset_id": "A", "trade_date": "2026-01-05", "feature_name": "max_drawdown_20d", "feature_value": -0.03},
        ]
    )
    bar_frame = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-01-05", "open": 10.0, "close": 10.0, "preclose": 9.7, "amount": 100000000.0, "trade_status": "1", "is_st": False, "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
            {"asset_id": "A", "trade_date": "2026-01-06", "open": 10.5, "close": 10.5, "preclose": 10.0, "amount": 100000000.0, "trade_status": "1", "is_st": False, "is_limit_up": True, "is_limit_down": False, "is_suspended": False},
        ]
    )
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-06",
        max_positions=1,
        execution_constraints=BacktestExecutionConstraints(),
    )

    result = simulate_retention_config(feature_frame, bar_frame, config)

    skipped = result.trades[result.trades["skip_reason"] == "limit_up"]
    assert len(skipped) == 1


def test_retention_rolls_limit_down_sell_until_executable():
    feature_frame = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ret_5d", "feature_value": 0.05},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ret_20d", "feature_value": 0.15},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ret_60d", "feature_value": 0.10},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "amount_20d_avg", "feature_value": 100000000.0},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "volatility_20d", "feature_value": 0.02},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ma20_deviation", "feature_value": 0.05},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "max_drawdown_20d", "feature_value": -0.03},
            {"asset_id": "B", "trade_date": "2026-01-05", "feature_name": "ret_5d", "feature_value": 0.01},
            {"asset_id": "B", "trade_date": "2026-01-05", "feature_name": "ret_20d", "feature_value": 0.02},
            {"asset_id": "B", "trade_date": "2026-01-05", "feature_name": "ret_60d", "feature_value": 0.03},
            {"asset_id": "B", "trade_date": "2026-01-05", "feature_name": "amount_20d_avg", "feature_value": 100000000.0},
            {"asset_id": "B", "trade_date": "2026-01-05", "feature_name": "volatility_20d", "feature_value": 0.02},
            {"asset_id": "B", "trade_date": "2026-01-05", "feature_name": "ma20_deviation", "feature_value": 0.01},
            {"asset_id": "B", "trade_date": "2026-01-05", "feature_name": "max_drawdown_20d", "feature_value": -0.01},
        ]
    )
    bar_frame = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-01-02", "open": 10.0, "close": 10.0, "preclose": 9.7, "amount": 100000000.0, "trade_status": "1", "is_st": False, "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
            {"asset_id": "A", "trade_date": "2026-01-05", "open": 10.0, "close": 10.0, "preclose": 10.0, "amount": 100000000.0, "trade_status": "1", "is_st": False, "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
            {"asset_id": "A", "trade_date": "2026-01-06", "open": 10.0, "close": 10.0, "preclose": 10.0, "amount": 100000000.0, "trade_status": "1", "is_st": False, "is_limit_up": False, "is_limit_down": True, "is_suspended": False},
            {"asset_id": "A", "trade_date": "2026-01-07", "open": 9.8, "close": 9.8, "preclose": 9.8, "amount": 100000000.0, "trade_status": "1", "is_st": False, "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
        ]
    )
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-07",
        max_positions=1,
        execution_constraints=BacktestExecutionConstraints(),
    )

    result = simulate_retention_config(feature_frame, bar_frame, config)

    closed = result.trades[result.trades["status"] == "closed"].iloc[0]
    assert closed["sell_date"] == "2026-01-07"


def test_retention_blocks_execution_day_st_buy_even_with_shared_constraints():
    feature_frame = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ret_5d", "feature_value": 0.05},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ret_20d", "feature_value": 0.15},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ret_60d", "feature_value": 0.10},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "amount_20d_avg", "feature_value": 100000000.0},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "volatility_20d", "feature_value": 0.02},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ma20_deviation", "feature_value": 0.05},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "max_drawdown_20d", "feature_value": -0.03},
        ]
    )
    bar_frame = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-01-02", "open": 10.0, "close": 10.0, "preclose": 9.7, "amount": 100000000.0, "trade_status": "1", "is_st": False, "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
            {"asset_id": "A", "trade_date": "2026-01-05", "open": 10.5, "close": 10.5, "preclose": 10.4, "amount": 100000000.0, "trade_status": "1", "is_st": True, "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
        ]
    )
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-05",
        max_positions=1,
        execution_constraints=BacktestExecutionConstraints(),
    )

    result = simulate_retention_config(feature_frame, bar_frame, config)

    skipped = result.trades[result.trades["skip_reason"] == "st"]
    assert len(skipped) == 1


def test_retention_applies_default_low_liquidity_buy_protection():
    feature_frame = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ret_5d", "feature_value": 0.05},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ret_20d", "feature_value": 0.15},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ret_60d", "feature_value": 0.10},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "amount_20d_avg", "feature_value": 100000000.0},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "volatility_20d", "feature_value": 0.02},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ma20_deviation", "feature_value": 0.05},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "max_drawdown_20d", "feature_value": -0.03},
        ]
    )
    bar_frame = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-01-02", "open": 10.0, "close": 10.0, "preclose": 9.7, "amount": 100000000.0, "trade_status": "1", "is_st": False, "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
            {"asset_id": "A", "trade_date": "2026-01-05", "open": 10.5, "close": 10.5, "preclose": 10.4, "amount": 100000000.0, "trade_status": "1", "is_st": False, "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
        ]
    )
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-05",
        max_positions=1,
        execution_constraints=BacktestExecutionConstraints(),
    )
    signal_cache = {
        "2026-01-02": {
            "selections": [
                BacktestSelection("2026-01-02", "A", 1, 10.0, 0.15, 10000000.0)
            ],
            "feature_values": {"A": {"amount_20d_avg": 10000000.0}},
            "market_allows_entry": True,
            "entry_allowed_assets": None,
        }
    }

    result = simulate_retention_config(feature_frame, bar_frame, config, signal_cache=signal_cache)

    skipped = result.trades[result.trades["skip_reason"] == "low_liquidity"]
    assert len(skipped) == 1


def test_retention_skips_missing_execution_day_amount_as_low_liquidity():
    feature_frame = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ret_5d", "feature_value": 0.05},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ret_20d", "feature_value": 0.15},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ret_60d", "feature_value": 0.10},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "amount_20d_avg", "feature_value": 100000000.0},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "volatility_20d", "feature_value": 0.02},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ma20_deviation", "feature_value": 0.05},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "max_drawdown_20d", "feature_value": -0.03},
        ]
    )
    bar_frame = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-01-02", "open": 10.0, "close": 10.0, "preclose": 9.7, "amount": 100000000.0, "trade_status": "1", "is_st": False, "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
            {"asset_id": "A", "trade_date": "2026-01-05", "open": 10.5, "close": 10.5, "preclose": 10.4, "amount": None, "trade_status": "1", "is_st": False, "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
        ]
    )
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-05",
        max_positions=1,
        execution_constraints=BacktestExecutionConstraints(),
    )
    signal_cache = {
        "2026-01-02": {
            "selections": [
                BacktestSelection("2026-01-02", "A", 1, 10.0, 0.15, 100000000.0)
            ],
            "feature_values": {"A": {"amount_20d_avg": 100000000.0}},
            "market_allows_entry": True,
            "entry_allowed_assets": None,
        }
    }

    result = simulate_retention_config(feature_frame, bar_frame, config, signal_cache=signal_cache)

    skipped = result.trades[result.trades["skip_reason"] == "low_liquidity"]
    assert len(skipped) == 1


def test_retention_ignores_non_trading_signal_dates_without_extra_equity_rows():
    feature_frame = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-01-03", "feature_name": "ret_5d", "feature_value": 0.05},
            {"asset_id": "A", "trade_date": "2026-01-03", "feature_name": "ret_20d", "feature_value": 0.15},
            {"asset_id": "A", "trade_date": "2026-01-03", "feature_name": "ret_60d", "feature_value": 0.10},
            {"asset_id": "A", "trade_date": "2026-01-03", "feature_name": "amount_20d_avg", "feature_value": 100000000.0},
            {"asset_id": "A", "trade_date": "2026-01-03", "feature_name": "volatility_20d", "feature_value": 0.02},
            {"asset_id": "A", "trade_date": "2026-01-03", "feature_name": "ma20_deviation", "feature_value": 0.05},
            {"asset_id": "A", "trade_date": "2026-01-03", "feature_name": "max_drawdown_20d", "feature_value": -0.03},
        ]
    )
    bar_frame = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-01-05", "open": 10.0, "close": 10.0, "preclose": 9.7, "amount": 100000000.0, "trade_status": "1", "is_st": False, "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
            {"asset_id": "A", "trade_date": "2026-01-06", "open": 10.2, "close": 10.2, "preclose": 10.0, "amount": 100000000.0, "trade_status": "1", "is_st": False, "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
        ]
    )
    config = RetentionConfig(
        start_date="2026-01-03",
        end_date="2026-01-06",
        max_positions=1,
        execution_constraints=BacktestExecutionConstraints(),
    )

    result = simulate_retention_config(feature_frame, bar_frame, config)

    assert list(result.equity_curve["date"]) == ["2026-01-05", "2026-01-06"]
    assert result.trades.empty


def test_retention_v2_observes_one_day_outside_top20_before_exiting():
    feature_frame = pd.concat(
        [
            _features("2026-01-02", [("A", 0.50)]),
            _features(
                "2026-01-05",
                [(f"N{i:02d}", 1.0 - i * 0.01) for i in range(20)] + [("A", 0.20)],
            ),
            _features(
                "2026-01-06",
                [(f"N{i:02d}", 1.0 - i * 0.01) for i in range(20)] + [("A", 0.20)],
            ),
        ],
        ignore_index=True,
    )
    bar_frame = _bars(
        {
            asset_id: {
                "2026-01-02": 10.0,
                "2026-01-05": 10.0,
                "2026-01-06": 10.0,
                "2026-01-07": 10.0,
            }
            for asset_id in ["A"] + [f"N{i:02d}" for i in range(20)]
        }
    )
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-07",
        initial_cash=10000.0,
        max_positions=1,
        strategy_id="unit-v2",
        entry_top_n=20,
        observe_top_n=30,
        exit_confirm_days=2,
    )

    result = simulate_retention_config(feature_frame, bar_frame, config)

    trade = result.trades[result.trades["asset_id"] == "A"].iloc[0]
    assert trade["status"] == "closed"
    assert trade["sell_signal_date"] == "2026-01-06"
    assert trade["sell_date"] == "2026-01-07"
    assert trade["exit_reason"] == "exit_confirmed_out_top20"


def test_retention_v2_exits_immediately_when_asset_drops_out_of_top30():
    feature_frame = pd.concat(
        [
            _features("2026-01-02", [("A", 0.50)]),
            _features("2026-01-05", [(f"N{i:02d}", 1.0 - i * 0.01) for i in range(30)]),
        ],
        ignore_index=True,
    )
    bar_frame = _bars(
        {
            asset_id: {
                "2026-01-02": 10.0,
                "2026-01-05": 10.0,
                "2026-01-06": 10.0,
            }
            for asset_id in ["A"] + [f"N{i:02d}" for i in range(30)]
        }
    )
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-06",
        initial_cash=10000.0,
        max_positions=1,
        strategy_id="unit-v2",
        entry_top_n=20,
        observe_top_n=30,
        exit_confirm_days=2,
    )

    result = simulate_retention_config(feature_frame, bar_frame, config)

    trade = result.trades[result.trades["asset_id"] == "A"].iloc[0]
    assert trade["status"] == "closed"
    assert trade["sell_signal_date"] == "2026-01-05"
    assert trade["sell_date"] == "2026-01-06"
    assert trade["exit_reason"] == "exit_observe_pool"


def test_retention_v2_exits_when_ma20_trend_breaks_even_if_still_top20():
    feature_frame = pd.concat(
        [
            _features("2026-01-02", [("A", 0.50)]),
            _features_with_values(
                "2026-01-05",
                [("A", {"ret_20d": 0.50, "ret_60d": 0.25, "ma20_deviation": -0.01})],
            ),
        ],
        ignore_index=True,
    )
    bar_frame = _bars(
        {
            "A": {
                "2026-01-02": 10.0,
                "2026-01-05": 10.0,
                "2026-01-06": 10.0,
            }
        }
    )
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-06",
        initial_cash=10000.0,
        max_positions=1,
        strategy_id="unit-v2",
        entry_top_n=20,
        observe_top_n=30,
        exit_confirm_days=2,
        ma20_exit=True,
    )

    result = simulate_retention_config(feature_frame, bar_frame, config)

    trade = result.trades[result.trades["asset_id"] == "A"].iloc[0]
    assert trade["status"] == "closed"
    assert trade["sell_signal_date"] == "2026-01-05"
    assert trade["exit_reason"] == "exit_ma20"


def test_retention_v2_adjusted_score_penalizes_short_term_overheat():
    feature_frame = _features_with_values(
        "2026-01-02",
        [
            (
                "HOT",
                {
                    "ret_5d": 0.45,
                    "ret_20d": 0.30,
                    "ret_60d": 0.15,
                    "volatility_20d": 0.09,
                    "ma20_deviation": 0.35,
                    "max_drawdown_20d": -0.18,
                },
            ),
            (
                "STEADY",
                {
                    "ret_5d": 0.06,
                    "ret_20d": 0.24,
                    "ret_60d": 0.12,
                    "volatility_20d": 0.025,
                    "ma20_deviation": 0.08,
                    "max_drawdown_20d": -0.04,
                },
            ),
        ],
    )
    bar_frame = _bars(
        {
            "HOT": {"2026-01-02": 10.0},
            "STEADY": {"2026-01-02": 10.0},
        }
    )
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-02",
        strategy_id="unit-v2",
        use_adjusted_score=True,
    )

    selections = retention_backtest.select_retention_candidates(
        feature_frame,
        bar_frame,
        "2026-01-02",
        config,
    )

    assert [selection.asset_id for selection in selections[:2]] == ["STEADY", "HOT"]


def test_retention_v31_hard_entry_filter_excludes_overheated_candidate():
    feature_frame = _features_with_values(
        "2026-01-02",
        [
            ("HOT", {"ret_5d": 0.24, "ret_20d": 0.32, "ma20_deviation": 0.24}),
            ("STEADY", {"ret_5d": 0.06, "ret_20d": 0.22, "ma20_deviation": 0.08}),
        ],
    )
    bar_frame = _bars(
        {
            "HOT": {"2026-01-02": 10.0},
            "STEADY": {"2026-01-02": 10.0},
        }
    )
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-02",
        strategy_id="unit-v31",
        use_adjusted_score=True,
        hard_entry_filters=True,
    )

    selections = retention_backtest.select_retention_candidates(
        feature_frame,
        bar_frame,
        "2026-01-02",
        config,
    )

    assert [selection.asset_id for selection in selections] == ["STEADY"]


def test_select_retention_candidates_filters_by_universe_result():
    feature_frame = _features("2026-01-02", [("A", 0.30), ("B", 0.40)])
    bar_frame = _bars({"A": {"2026-01-02": 10.0}, "B": {"2026-01-02": 10.0}})
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-02",
        strategy_id="unit",
    )
    universe_result = _universe_result(included=[("B", "B")], excluded=[("A", "A")])

    selections = retention_backtest.select_retention_candidates(
        feature_frame,
        bar_frame,
        "2026-01-02",
        config,
        universe_result=universe_result,
    )

    assert [selection.asset_id for selection in selections] == ["B"]


def test_simulate_retention_config_filters_signal_cache_by_universe_result():
    feature_frame = _features("2026-01-02", [("A", 0.30), ("B", 0.40)])
    bar_frame = _bars(
        {
            "A": {"2026-01-02": 10.0, "2026-01-05": 10.0},
            "B": {"2026-01-02": 10.0, "2026-01-05": 10.0},
        }
    )
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-05",
        initial_cash=10000.0,
        max_positions=1,
        strategy_id="unit",
    )
    signal_cache = {
        "2026-01-02": {
            "selections": [
                BacktestSelection("2026-01-02", "A", 1, 10.0, 0.30, 100000000.0),
                BacktestSelection("2026-01-02", "B", 2, 9.0, 0.40, 100000000.0),
            ],
            "feature_values": {"A": {}, "B": {}},
            "market_allows_entry": True,
            "entry_allowed_assets": {"A", "B"},
        }
    }
    universe_result = _universe_result(included=[("B", "B")], excluded=[("A", "A")])

    result = simulate_retention_config(
        feature_frame,
        bar_frame,
        config,
        signal_cache=signal_cache,
        universe_result=universe_result,
    )

    assert set(result.trades["asset_id"]) == {"B"}


def test_filter_retention_signal_cache_keeps_none_when_universe_is_none():
    assert retention_backtest._filter_retention_signal_cache_by_universe(None, None) is None


def test_retention_v31_market_filter_blocks_new_entries():
    feature_frame = _features("2026-01-02", [("A", 0.30)])
    bar_frame = _bars({"A": {"2026-01-02": 10.0, "2026-01-05": 10.0}})
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-05",
        initial_cash=10000.0,
        max_positions=1,
        strategy_id="unit-v31",
        market_entry_filter=True,
    )
    signal_cache = {
        "2026-01-02": {
            "selections": [
                BacktestSelection("2026-01-02", "A", 1, 10.0, 0.30, 100000000.0)
            ],
            "feature_values": {"A": {}},
            "market_allows_entry": False,
            "entry_allowed_assets": {"A"},
        }
    }

    result = simulate_retention_config(
        feature_frame,
        bar_frame,
        config,
        signal_cache=signal_cache,
    )

    assert result.trades.empty


def test_retention_v31_board_filter_blocks_weak_board_entries():
    feature_frame = _features("2026-01-02", [("CN:SH:600001", 0.30)])
    bar_frame = _bars(
        {"CN:SH:600001": {"2026-01-02": 10.0, "2026-01-05": 10.0}}
    )
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-05",
        initial_cash=10000.0,
        max_positions=1,
        strategy_id="unit-v31",
        board_entry_filter=True,
    )
    signal_cache = {
        "2026-01-02": {
            "selections": [
                BacktestSelection(
                    "2026-01-02",
                    "CN:SH:600001",
                    1,
                    10.0,
                    0.30,
                    100000000.0,
                )
            ],
            "feature_values": {"CN:SH:600001": {}},
            "market_allows_entry": True,
            "entry_allowed_assets": set(),
        }
    }

    result = simulate_retention_config(
        feature_frame,
        bar_frame,
        config,
        signal_cache=signal_cache,
    )

    assert result.trades.empty


def test_entry_allowed_assets_uses_close_preclose_when_pct_chg_missing():
    features = {
        "CN:SH:600001": {"ret_5d": 0.02, "ret_20d": 0.08},
        "CN:SH:600002": {"ret_5d": 0.03, "ret_20d": 0.10},
        "CN:SH:600003": {"ret_5d": 0.01, "ret_20d": 0.06},
    }
    current = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600001",
                "open": 10.0,
                "preclose": 10.0,
                "close": 10.5,
                "amount": 100000000.0,
                "trade_status": "1",
            },
            {
                "asset_id": "CN:SH:600002",
                "open": 10.0,
                "preclose": 10.0,
                "close": 10.4,
                "amount": 100000000.0,
                "trade_status": "1",
            },
            {
                "asset_id": "CN:SH:600003",
                "open": 10.0,
                "preclose": 10.0,
                "close": 9.8,
                "amount": 100000000.0,
                "trade_status": "1",
            },
        ]
    )

    allowed = retention_backtest._entry_allowed_assets_from_daily(features, current)

    assert allowed == {"CN:SH:600001", "CN:SH:600002", "CN:SH:600003"}


def test_retention_v31_stop_loss_exits_before_ma20_or_rank_break():
    feature_frame = pd.concat(
        [
            _features("2026-01-02", [("A", 0.30)]),
            _features("2026-01-05", [("A", 0.30)]),
            _features("2026-01-06", [("A", 0.30)]),
        ],
        ignore_index=True,
    )
    bar_frame = _bars(
        {
            "A": {
                "2026-01-02": 100.0,
                "2026-01-05": 100.0,
                "2026-01-06": 89.0,
                "2026-01-07": 89.0,
            }
        }
    )
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-07",
        initial_cash=10000.0,
        max_positions=1,
        strategy_id="unit-v31",
        stop_loss_pct=0.10,
        entry_top_n=20,
        observe_top_n=30,
        exit_confirm_days=2,
        ma20_exit=True,
    )

    result = simulate_retention_config(feature_frame, bar_frame, config)

    trade = result.trades[result.trades["asset_id"] == "A"].iloc[0]
    assert trade["status"] == "closed"
    assert trade["sell_signal_date"] == "2026-01-06"
    assert trade["sell_date"] == "2026-01-07"
    assert trade["exit_reason"] == "exit_stop_loss"


def test_retention_v31_market_helpers_handle_missing_pct_chg_column():
    bars = _bars(
        {
            "A": {"2026-01-02": 10.0},
            "B": {"2026-01-02": 12.0},
        }
    )

    stats = retention_backtest._limit_stats(bars)

    assert stats["limit_down_count"] == 0.0
    assert stats["limit_up_down_ratio"] == 999.0


def test_build_retention_signal_cache_normalizes_bars_once(monkeypatch):
    feature_frame = pd.concat(
        [
            _features("2026-01-02", [("A", 0.30)]),
            _features("2026-01-05", [("A", 0.30)]),
        ],
        ignore_index=True,
    )
    bar_frame = _bars(
        {
            "A": {
                "2026-01-02": 10.0,
                "2026-01-05": 10.0,
            },
            "B": {
                "2026-01-02": 8.0,
                "2026-01-05": 8.0,
            },
        }
    )
    calls = []

    def fail_if_old_daily_copy_path(bar_frame, trade_date):
        calls.append(trade_date)
        raise AssertionError("_bars_for_date should not be used inside signal cache")

    monkeypatch.setattr(retention_backtest, "_bars_for_date", fail_if_old_daily_copy_path)
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-05",
        strategy_id="unit-v31",
        use_adjusted_score=True,
        market_entry_filter=True,
        board_entry_filter=True,
        hard_entry_filters=True,
    )

    cache = retention_backtest._build_retention_signal_cache(
        feature_frame,
        bar_frame,
        config,
    )

    assert calls == []
    assert sorted(cache) == ["2026-01-02", "2026-01-05"]
    assert "market_allows_entry" in cache["2026-01-02"]
    assert isinstance(cache["2026-01-02"]["entry_allowed_assets"], set)


def test_run_retention_v31_uses_local_cache_for_signals(monkeypatch, tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    asset_features = cache_dir / "asset_features.csv"
    market_regime = cache_dir / "market_regime.csv"
    board_regime = cache_dir / "board_regime.csv"
    candidates = cache_dir / "retention_candidates_v3_1.csv"
    manifest = cache_dir / "manifest.json"

    asset_features.write_text(
        "\n".join(
            [
                "trade_date,asset_id,ret_5d,ret_20d,ret_60d,amount_20d_avg,turnover_20d_avg,volatility_20d,ma20_deviation,max_drawdown_20d",
                "2026-01-02,CN:SH:600001,0.05,0.20,0.10,100000000.0,1.0,0.02,0.08,-0.03",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    market_regime.write_text(
        "trade_date,total_amount,amount_ratio_20d,up_ratio,limit_up_count,limit_down_count,limit_up_down_ratio,market_allows_entry\n"
        "2026-01-02,100000000.0,1.0,0.8,0,0,999.0,True\n",
        encoding="utf-8",
    )
    board_regime.write_text(
        "trade_date,board,ret_5d_median,ret_20d_median,up_ratio,amount,board_allows_entry\n"
        "2026-01-02,SH_MAIN,0.05,0.20,0.8,100000000.0,True\n",
        encoding="utf-8",
    )
    candidates.write_text(
        "trade_date,asset_id,rank,score,hard_filter_pass,board_filter_pass,market_filter_pass\n"
        "2026-01-02,CN:SH:600001,1,10.0,True,True,True\n",
        encoding="utf-8",
    )
    manifest.write_text(
        "{"
        '"start_date":"2026-01-01",'
        '"end_date":"2026-01-10",'
        f'"paths":{{"asset_features":"{asset_features}","market_regime":"{market_regime}","board_regime":"{board_regime}","retention_candidates":"{candidates}","manifest":"{manifest}"}},'
        '"counts":{"asset_features":1,"market_regime":1,"board_regime":1,"retention_candidates":1}'
        "}",
        encoding="utf-8",
    )

    bar_frame = _bars(
        {
            "CN:SH:600001": {
                "2026-01-02": 10.0,
                "2026-01-05": 10.0,
            }
        }
    )
    load_inputs_called = False

    def fail_load_backtest_inputs(*args, **kwargs):
        nonlocal load_inputs_called
        load_inputs_called = True
        raise AssertionError("v3.1 should use cached signals instead of loading features")

    monkeypatch.setattr(retention_backtest, "load_backtest_inputs", fail_load_backtest_inputs)
    monkeypatch.setattr(retention_backtest, "load_backtest_bars", lambda *args, **kwargs: bar_frame)

    result = retention_backtest.run_retention_backtest(
        "2026-01-02",
        "2026-01-05",
        initial_cash=10000.0,
        top_ks=(1,),
        reports_dir=tmp_path / "reports",
        variant="v3.1",
        cache_dir=cache_dir,
    )

    assert load_inputs_called is False
    assert len(result["trades"]) == 1
    assert result["trades"].iloc[0]["asset_id"] == "CN:SH:600001"


def test_summarize_retention_result_reports_holding_days_and_turnover():
    result = RetentionResult(
        config=RetentionConfig(
            start_date="2026-01-01",
            end_date="2026-01-10",
            initial_cash=500000.0,
            max_positions=5,
            strategy_id="retention:2026-01-01:2026-01-10:top5:cash500000",
        ),
        equity_curve=pd.DataFrame(
            [
                {
                    "strategy_id": "retention:2026-01-01:2026-01-10:top5:cash500000",
                    "date": "2026-01-01",
                    "cash": 500000.0,
                    "market_value": 0.0,
                    "equity": 500000.0,
                    "drawdown": 0.0,
                    "open_positions": 0,
                },
                {
                    "strategy_id": "retention:2026-01-01:2026-01-10:top5:cash500000",
                    "date": "2026-01-10",
                    "cash": 100000.0,
                    "market_value": 425000.0,
                    "equity": 525000.0,
                    "drawdown": -0.04,
                    "open_positions": 1,
                },
            ]
        ),
        trades=pd.DataFrame(
            [
                {
                    "strategy_id": "retention:2026-01-01:2026-01-10:top5:cash500000",
                    "max_positions": 5,
                    "buy_date": "2026-01-02",
                    "sell_date": "2026-01-05",
                    "status": "closed",
                    "return_value": 0.10,
                    "skip_reason": None,
                },
                {
                    "strategy_id": "retention:2026-01-01:2026-01-10:top5:cash500000",
                    "max_positions": 5,
                    "buy_date": "2026-01-03",
                    "sell_date": "2026-01-10",
                    "status": "closed",
                    "return_value": -0.02,
                    "skip_reason": None,
                },
                {
                    "strategy_id": "retention:2026-01-01:2026-01-10:top5:cash500000",
                    "max_positions": 5,
                    "buy_date": "2026-01-08",
                    "sell_date": None,
                    "status": "open",
                    "return_value": None,
                    "skip_reason": None,
                },
                {
                    "strategy_id": "retention:2026-01-01:2026-01-10:top5:cash500000",
                    "max_positions": 5,
                    "buy_date": "2026-01-09",
                    "sell_date": None,
                    "status": "skipped",
                    "return_value": None,
                    "skip_reason": "insufficient_lot_cash",
                },
                {
                    "strategy_id": "retention:2026-01-01:2026-01-10:top5:cash500000",
                    "max_positions": 5,
                    "buy_date": "2026-01-09",
                    "sell_date": None,
                    "status": "skipped",
                    "return_value": None,
                    "skip_reason": "suspended",
                },
            ]
        ),
    )

    summary = retention_backtest.summarize_retention_result(result)

    assert summary["strategy_id"] == result.config.strategy_id
    assert summary["max_positions"] == 5
    assert summary["initial_cash"] == 500000.0
    assert summary["final_equity"] == pytest.approx(525000.0)
    assert summary["total_return"] == pytest.approx(0.05)
    assert summary["max_drawdown"] == pytest.approx(-0.04)
    assert summary["closed_trades"] == 2
    assert summary["open_trades"] == 1
    assert summary["skipped_trades"] == 2
    assert summary["win_rate"] == pytest.approx(0.5)
    assert summary["mean_trade_return"] == pytest.approx(0.04)
    assert summary["average_holding_days"] == pytest.approx(5.0)
    assert summary["max_holding_days"] == 7
    assert summary["turnover_count"] == 2
    assert summary["average_capital_utilization"] == pytest.approx(0.425)
    assert summary["insufficient_lot_cash_skips"] == 1
    assert summary["execution_skips"] == 1


def test_write_retention_report_writes_markdown_and_csv_outputs(tmp_path):
    result = RetentionResult(
        config=RetentionConfig(
            start_date="2026-01-01",
            end_date="2026-05-07",
            initial_cash=500000.0,
            max_positions=5,
            strategy_id="retention:2026-01-01:2026-05-07:top5:cash500000",
        ),
        equity_curve=pd.DataFrame(
            [
                {
                    "strategy_id": "retention:2026-01-01:2026-05-07:top5:cash500000",
                    "date": "2026-01-01",
                    "cash": 500000.0,
                    "market_value": 0.0,
                    "equity": 500000.0,
                    "drawdown": 0.0,
                    "open_positions": 0,
                },
                {
                    "strategy_id": "retention:2026-01-01:2026-05-07:top5:cash500000",
                    "date": "2026-05-07",
                    "cash": 120000.0,
                    "market_value": 410000.0,
                    "equity": 530000.0,
                    "drawdown": -0.03,
                    "open_positions": 2,
                },
            ]
        ),
        trades=pd.DataFrame(
            [
                {
                    "strategy_id": "retention:2026-01-01:2026-05-07:top5:cash500000",
                    "max_positions": 5,
                    "status": "closed",
                    "buy_date": "2026-01-02",
                    "sell_date": "2026-01-06",
                    "return_value": 0.08,
                    "skip_reason": None,
                },
                {
                    "strategy_id": "retention:2026-01-01:2026-05-07:top5:cash500000",
                    "max_positions": 5,
                    "status": "skipped",
                    "buy_date": "2026-01-03",
                    "sell_date": None,
                    "return_value": None,
                    "skip_reason": "insufficient_lot_cash",
                },
            ]
        ),
    )
    summary = pd.DataFrame([retention_backtest.summarize_retention_result(result)])

    paths = retention_backtest.write_retention_report(
        [result],
        summary,
        start_date="2026-01-01",
        end_date="2026-05-07",
        initial_cash=500000.0,
        top_ks=(5, 10),
        reports_dir=tmp_path,
    )

    expected_stem = "retention_2026-01-01_2026-05-07_cash500000_top5-10"
    assert paths == {
        "report_path": str(tmp_path / f"{expected_stem}.md"),
        "equity_curve_path": str(tmp_path / f"{expected_stem}_equity.csv"),
        "trades_path": str(tmp_path / f"{expected_stem}_trades.csv"),
        "summary_path": str(tmp_path / f"{expected_stem}_summary.csv"),
    }

    markdown = (tmp_path / f"{expected_stem}.md").read_text(encoding="utf-8")
    assert "Top20 留存策略账户回测报告" in markdown
    assert "跌出 Top20 退出" in markdown
    assert "资金曲线" in markdown
    assert "最大回撤" in markdown
    assert "仅作为研究验证，不构成交易指令" in markdown
    assert "买入建议" not in markdown
    assert "卖出建议" not in markdown
    assert "仓位建议" not in markdown
    assert "下单" not in markdown
    assert "自动交易指令" not in markdown

    equity = pd.read_csv(paths["equity_curve_path"])
    trades = pd.read_csv(paths["trades_path"])
    written_summary = pd.read_csv(paths["summary_path"])
    assert not equity.empty
    assert not trades.empty
    assert not written_summary.empty
    assert "equity" in equity.columns
    assert "status" in trades.columns
    assert "average_holding_days" in written_summary.columns


def test_write_retention_report_handles_empty_summary_with_headers(tmp_path):
    paths = retention_backtest.write_retention_report(
        [],
        pd.DataFrame(),
        start_date="2026-01-01",
        end_date="2026-05-07",
        initial_cash=500000.0,
        top_ks=(5,),
        reports_dir=tmp_path,
    )

    summary = pd.read_csv(paths["summary_path"])
    equity = pd.read_csv(paths["equity_curve_path"])
    trades = pd.read_csv(paths["trades_path"])

    assert summary.empty
    assert list(summary.columns) == retention_backtest.RETENTION_SUMMARY_COLUMNS
    assert equity.empty
    assert list(equity.columns) == (
        retention_backtest.RETENTION_EQUITY_COLUMNS + ["max_positions"]
    )
    assert trades.empty
    assert list(trades.columns) == retention_backtest.RETENTION_TRADE_COLUMNS


def test_run_retention_backtest_runs_top5_and_top10_configs(monkeypatch, tmp_path):
    calls = []

    def fake_load(start_date, end_date, future_buffer_days=30):
        calls.append(("load", start_date, end_date, future_buffer_days))
        return pd.DataFrame({"feature": [1]}), pd.DataFrame({"bar": [1]})

    def fake_simulate(features, bars, config, signal_cache=None):
        calls.append(("simulate", features, bars, config))
        return RetentionResult(
            config=config,
            equity_curve=pd.DataFrame(
                [
                    {
                        "strategy_id": config.strategy_id,
                        "date": config.end_date,
                        "cash": config.initial_cash,
                        "market_value": float(config.max_positions),
                        "equity": config.initial_cash + config.max_positions,
                        "drawdown": 0.0,
                        "open_positions": 0,
                    }
                ]
            ),
            trades=pd.DataFrame(
                [
                    {
                        "strategy_id": config.strategy_id,
                        "max_positions": config.max_positions,
                        "status": "closed",
                        "buy_date": "2026-01-02",
                        "sell_date": "2026-01-06",
                        "return_value": 0.01,
                        "skip_reason": None,
                    }
                ]
            ),
        )

    monkeypatch.setattr(retention_backtest, "load_backtest_inputs", fake_load)
    monkeypatch.setattr(retention_backtest, "simulate_retention_config", fake_simulate)

    output = retention_backtest.run_retention_backtest(
        "2026-01-01",
        "2026-05-07",
        initial_cash=123000.0,
        reports_dir=tmp_path,
    )

    assert calls[0] == ("load", "2026-01-01", "2026-05-07", 30)
    simulate_calls = [call for call in calls if call[0] == "simulate"]
    configs = [call[3] for call in simulate_calls]
    assert [config.max_positions for config in configs] == [5, 10]
    for config in configs:
        assert config.start_date == "2026-01-01"
        assert config.end_date == "2026-05-07"
        assert config.initial_cash == 123000.0
        assert f"top{config.max_positions}" in config.strategy_id
        assert "cash123000" in config.strategy_id

    assert set(output) >= {
        "results",
        "equity_curve",
        "trades",
        "summary",
        "report_path",
        "report_paths",
    }
    assert len(output["results"]) == 2
    assert output["equity_curve"].shape[0] == 2
    assert output["trades"].shape[0] == 2
    assert output["summary"].shape[0] == 2
    assert Path(output["report_path"]).exists()
    assert Path(output["run_card"]["run_card_json_path"]).exists()
    assert Path(output["run_card"]["run_card_md_path"]).exists()
    assert Path(output["run_card"]["metrics_json_path"]).exists()
    assert Path(output["run_card"]["config_snapshot_path"]).exists()
    assert Path(output["run_card"]["warnings_md_path"]).exists()
    assert Path(output["run_card"]["data_coverage_json_path"]).exists()
    coverage = json.loads(Path(output["run_card"]["data_coverage_json_path"]).read_text(encoding="utf-8"))
    assert coverage["coverage_ratio"] is None
    assert coverage["missing_dates"] is None
    assert coverage["missing_assets"] is None


def test_run_retention_backtest_applies_v2_variant_config(monkeypatch, tmp_path):
    configs = []

    def fake_load(start_date, end_date, future_buffer_days=30):
        return pd.DataFrame({"feature": [1]}), pd.DataFrame({"bar": [1]})

    def fake_simulate(features, bars, config, signal_cache=None):
        configs.append(config)
        return RetentionResult(
            config=config,
            equity_curve=pd.DataFrame(
                [
                    {
                        "strategy_id": config.strategy_id,
                        "date": config.end_date,
                        "cash": config.initial_cash,
                        "market_value": 0.0,
                        "equity": config.initial_cash,
                        "drawdown": 0.0,
                        "open_positions": 0,
                    }
                ]
            ),
            trades=pd.DataFrame(),
        )

    monkeypatch.setattr(retention_backtest, "load_backtest_inputs", fake_load)
    monkeypatch.setattr(retention_backtest, "simulate_retention_config", fake_simulate)

    output = retention_backtest.run_retention_backtest(
        "2026-01-01",
        "2026-05-07",
        initial_cash=500000.0,
        top_ks=(10,),
        reports_dir=tmp_path,
        variant="v2",
    )

    assert len(configs) == 1
    config = configs[0]
    assert config.entry_top_n == 20
    assert config.observe_top_n == 30
    assert config.exit_confirm_days == 2
    assert config.ma20_exit is True
    assert config.use_adjusted_score is True
    assert config.strategy_id.startswith("retention_v2:")
    assert "retention_v2_" in Path(output["report_path"]).name


def test_run_retention_backtest_creates_unique_run_card_directories(monkeypatch, tmp_path):
    def fake_load(start_date, end_date, future_buffer_days=30):
        return pd.DataFrame({"feature": [1]}), pd.DataFrame({"bar": [1]})

    def fake_simulate(features, bars, config, signal_cache=None):
        return RetentionResult(
            config=config,
            equity_curve=pd.DataFrame(
                [
                    {
                        "strategy_id": config.strategy_id,
                        "date": config.end_date,
                        "cash": config.initial_cash,
                        "market_value": float(config.max_positions),
                        "equity": config.initial_cash + config.max_positions,
                        "drawdown": 0.0,
                        "open_positions": 0,
                    }
                ]
            ),
            trades=pd.DataFrame(
                [
                    {
                        "strategy_id": config.strategy_id,
                        "max_positions": config.max_positions,
                        "status": "closed",
                        "buy_date": "2026-01-02",
                        "sell_date": "2026-01-06",
                        "return_value": 0.01,
                        "skip_reason": None,
                    }
                ]
            ),
        )

    monkeypatch.setattr(retention_backtest, "load_backtest_inputs", fake_load)
    monkeypatch.setattr(retention_backtest, "simulate_retention_config", fake_simulate)

    first = retention_backtest.run_retention_backtest(
        "2026-01-01",
        "2026-05-07",
        initial_cash=123000.0,
        reports_dir=tmp_path,
    )
    first_path = Path(first["run_card"]["run_card_json_path"])
    first_payload = json.loads(first_path.read_text(encoding="utf-8"))

    second = retention_backtest.run_retention_backtest(
        "2026-01-01",
        "2026-05-07",
        initial_cash=123000.0,
        reports_dir=tmp_path,
    )
    second_path = Path(second["run_card"]["run_card_json_path"])

    assert first["run_card"]["run_card_dir"] != second["run_card"]["run_card_dir"]
    assert first["run_card"]["run_card_json_path"] != second["run_card"]["run_card_json_path"]
    assert first_path.exists()
    assert second_path.exists()
    assert json.loads(first_path.read_text(encoding="utf-8")) == first_payload


def test_run_retention_backtest_reuses_signal_cache_across_topk_configs(
    monkeypatch,
    tmp_path,
):
    calls = []
    captured_caches = []

    def fake_load(start_date, end_date, future_buffer_days=30):
        return _features("2026-01-02", [("A", 0.30)]), _bars(
            {
                "A": {
                    "2026-01-02": 10.0,
                    "2026-01-05": 10.0,
                }
            }
        )

    original_select = retention_backtest.select_retention_candidates

    def counting_select(*args, **kwargs):
        calls.append(args[2])
        return original_select(*args, **kwargs)

    def fake_simulate(features, bars, config, signal_cache=None):
        captured_caches.append(signal_cache)
        return RetentionResult(
            config=config,
            equity_curve=pd.DataFrame(
                [
                    {
                        "strategy_id": config.strategy_id,
                        "date": config.end_date,
                        "cash": config.initial_cash,
                        "market_value": 0.0,
                        "equity": config.initial_cash,
                        "drawdown": 0.0,
                        "open_positions": 0,
                    }
                ]
            ),
            trades=pd.DataFrame(),
        )

    monkeypatch.setattr(retention_backtest, "load_backtest_inputs", fake_load)
    monkeypatch.setattr(retention_backtest, "select_retention_candidates", counting_select)
    monkeypatch.setattr(retention_backtest, "simulate_retention_config", fake_simulate)

    retention_backtest.run_retention_backtest(
        "2026-01-01",
        "2026-01-05",
        top_ks=(5, 8, 10),
        reports_dir=tmp_path,
        variant="v2",
    )

    assert calls == ["2026-01-02", "2026-01-05"]
    assert len(captured_caches) == 3
    assert len({id(cache) for cache in captured_caches}) == 1


def test_run_retention_backtest_returns_stable_columns_with_partial_frames(
    monkeypatch,
    tmp_path,
):
    def fake_load(start_date, end_date, future_buffer_days=30):
        return pd.DataFrame({"feature": [1]}), pd.DataFrame({"bar": [1]})

    def fake_simulate(features, bars, config, signal_cache=None):
        return RetentionResult(
            config=config,
            equity_curve=pd.DataFrame(
                [
                    {
                        "date": config.end_date,
                        "equity": config.initial_cash + config.max_positions,
                    }
                ]
            ),
            trades=pd.DataFrame([{"status": "closed"}]),
        )

    monkeypatch.setattr(retention_backtest, "load_backtest_inputs", fake_load)
    monkeypatch.setattr(retention_backtest, "simulate_retention_config", fake_simulate)

    output = retention_backtest.run_retention_backtest(
        "2026-01-01",
        "2026-05-07",
        initial_cash=123000.0,
        reports_dir=tmp_path,
    )

    assert list(output["equity_curve"].columns) == (
        retention_backtest.RETENTION_EQUITY_COLUMNS + ["max_positions"]
    )
    assert list(output["trades"].columns) == retention_backtest.RETENTION_TRADE_COLUMNS
    assert list(output["summary"].columns) == retention_backtest.RETENTION_SUMMARY_COLUMNS


def test_cli_parser_accepts_retention_backtest_arguments():
    args = cli.build_parser().parse_args(
        [
            "retention-backtest",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-07",
            "--initial-cash",
            "500000",
            "--top-ks",
            "5,10",
            "--variant",
            "v2",
        ]
    )

    assert args.command == "retention-backtest"
    assert args.start_date == "2026-01-01"
    assert args.end_date == "2026-05-07"
    assert args.initial_cash == 500000.0
    assert args.top_ks == [5, 10]
    assert args.variant == "v2"


def test_cli_parser_retention_defaults_are_not_shared_mutable_lists():
    parser = cli.build_parser()

    first = parser.parse_args(
        [
            "retention-backtest",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-07",
        ]
    )
    first.top_ks.append(99)

    second = parser.parse_args(
        [
            "retention-backtest",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-07",
        ]
    )

    assert second.top_ks == [5, 10]


def test_cli_main_runs_retention_backtest_and_prints_outputs(monkeypatch, capsys):
    calls = []

    def fake_run_retention_backtest(*args, **kwargs):
        calls.append((args, kwargs))
        return {
            "report_path": "/tmp/retention.md",
            "report_paths": {"summary_path": "/tmp/retention_summary.csv"},
            "summary": pd.DataFrame([{}, {}]),
        }

    monkeypatch.setattr(cli, "run_retention_backtest", fake_run_retention_backtest)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "retention-backtest",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-07",
            "--initial-cash",
            "500000",
                "--top-ks",
                "5,10",
                "--variant",
                "v2",
            ],
        )

    cli.main()

    assert calls == [
        (
            ("2026-01-01", "2026-05-07"),
            {
                "initial_cash": 500000.0,
                "top_ks": [5, 10],
                "variant": "v2",
                "reports_dir": "/Users/xiwei/stock_research/reports",
                "execution_constraints": BacktestExecutionConstraints(),
            },
        )
    ]
    assert capsys.readouterr().out.splitlines() == [
        "retention_backtest_report|/tmp/retention.md",
        "retention_backtest_summary|/tmp/retention_summary.csv",
        "retention_backtest_configs|2",
    ]
