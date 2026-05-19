from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BacktestExecutionConstraints:
    commission_bps: float = 0.0
    stamp_duty_bps: float = 0.0
    slippage_bps: float = 0.0
    min_amount: float | None = None
    block_suspended: bool = True
    block_limit_up_buy: bool = True
    block_limit_down_sell: bool = True


def can_open_long(
    bar: dict[str, Any],
    constraints: BacktestExecutionConstraints,
) -> tuple[bool, str | None]:
    if constraints.block_suspended and (
        bool(bar.get("is_suspended"))
        or str(bar.get("trade_status") or "1") != "1"
    ):
        return False, "suspended"
    if constraints.block_limit_up_buy and bool(bar.get("is_limit_up")):
        return False, "limit_up"
    if constraints.min_amount is not None and float(bar.get("amount") or 0.0) < float(
        constraints.min_amount
    ):
        return False, "low_amount"
    return True, None


def can_close_long(
    bar: dict[str, Any],
    constraints: BacktestExecutionConstraints,
) -> tuple[bool, str | None]:
    if constraints.block_suspended and (
        bool(bar.get("is_suspended"))
        or str(bar.get("trade_status") or "1") != "1"
    ):
        return False, "suspended"
    if constraints.block_limit_down_sell and bool(bar.get("is_limit_down")):
        return False, "limit_down"
    if constraints.min_amount is not None and float(bar.get("amount") or 0.0) < float(
        constraints.min_amount
    ):
        return False, "low_amount"
    return True, None


def one_way_cost_rate(side: str, constraints: BacktestExecutionConstraints) -> float:
    if side not in {"buy", "sell"}:
        raise ValueError(f"unsupported side: {side}")
    stamp_duty = constraints.stamp_duty_bps if side == "sell" else 0.0
    return (constraints.commission_bps + constraints.slippage_bps + stamp_duty) / 10000.0
