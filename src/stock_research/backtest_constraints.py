from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class BacktestExecutionConstraints:
    commission_bps: float = 0.0
    stamp_duty_bps: float = 0.0
    slippage_bps: float = 0.0
    min_amount: float | None = None
    block_suspended: bool = True
    block_limit_up_buy: bool = True
    block_limit_down_sell: bool = True

    def __post_init__(self) -> None:
        _validate_non_negative("commission_bps", self.commission_bps)
        _validate_non_negative("stamp_duty_bps", self.stamp_duty_bps)
        _validate_non_negative("slippage_bps", self.slippage_bps)
        if self.min_amount is not None:
            _validate_non_negative("min_amount", self.min_amount)


def can_open_long(
    bar: dict[str, Any],
    constraints: BacktestExecutionConstraints,
) -> tuple[bool, str | None]:
    if constraints.block_suspended and (
        _flag_is_true(bar.get("is_suspended"))
        or not _is_tradable_trade_status(bar.get("trade_status"))
    ):
        return False, "suspended"
    if constraints.block_limit_up_buy and _flag_is_true(bar.get("is_limit_up")):
        return False, "limit_up"
    amount = bar.get("amount")
    if constraints.min_amount is not None and (
        pd.isna(amount) or float(amount) < float(constraints.min_amount)
    ):
        return False, "low_amount"
    return True, None


def can_close_long(
    bar: dict[str, Any],
    constraints: BacktestExecutionConstraints,
) -> tuple[bool, str | None]:
    if constraints.block_suspended and (
        _flag_is_true(bar.get("is_suspended"))
        or not _is_tradable_trade_status(bar.get("trade_status"))
    ):
        return False, "suspended"
    if constraints.block_limit_down_sell and _flag_is_true(bar.get("is_limit_down")):
        return False, "limit_down"
    amount = bar.get("amount")
    if constraints.min_amount is not None and (
        pd.isna(amount) or float(amount) < float(constraints.min_amount)
    ):
        return False, "low_amount"
    return True, None


def one_way_cost_rate(side: str, constraints: BacktestExecutionConstraints) -> float:
    if side not in {"buy", "sell"}:
        raise ValueError(f"unsupported side: {side}")
    stamp_duty = constraints.stamp_duty_bps if side == "sell" else 0.0
    return (constraints.commission_bps + constraints.slippage_bps + stamp_duty) / 10000.0


def _validate_non_negative(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _flag_is_true(value: Any) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 1
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "f", "no", "n", "off", ""}:
            return False
        return False
    return False


def _is_tradable_trade_status(value: Any) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value is True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 1
    if isinstance(value, str):
        return value.strip() == "1"
    return False
