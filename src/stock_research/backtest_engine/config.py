"""Execution configuration for the unified backtest engine (POC V0.1)."""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

ENGINE_VERSION = "unified_backtest_engine_v0.1"

MODE_REALISTIC = "REALISTIC_A_SHARE"
MODE_LEGACY_COMPAT = "LEGACY_COMPAT"
EXECUTION_MODES = (MODE_REALISTIC, MODE_LEGACY_COMPAT)

# Ordinary A-share seller stamp duty (bps). Halved from 10bp to 5bp on
# 2023-08-28 (MOF/STA announcement 2023 No.39).
DEFAULT_STAMP_DUTY_SCHEDULE: tuple[tuple[str, float], ...] = (
    ("1900-01-01", 10.0),
    ("2023-08-28", 5.0),
)


@dataclass(frozen=True)
class StampDutySchedule:
    """Piecewise-constant seller stamp duty keyed by effective date."""

    steps: tuple[tuple[str, float], ...] = DEFAULT_STAMP_DUTY_SCHEDULE

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError("stamp duty schedule must not be empty")
        dates = [step[0] for step in self.steps]
        if dates != sorted(dates):
            raise ValueError("stamp duty schedule must be sorted by date")
        for date, bps in self.steps:
            dt.date.fromisoformat(date)
            if bps < 0:
                raise ValueError("stamp duty bps must be non-negative")

    def bps_on(self, trade_date: str) -> float:
        rate = self.steps[0][1]
        for effective, bps in self.steps:
            if trade_date >= effective:
                rate = bps
            else:
                break
        return float(rate)


@dataclass(frozen=True)
class RealisticExecutionConfig:
    """REALISTIC_A_SHARE: share ledger, raw prices, dated costs."""

    initial_cash: float = 1_000_000.0
    fill_price: str = "next_open"  # next_open | next_close
    lot_size: int = 100
    commission_bps: float = 2.5
    min_commission: float = 5.0
    slippage_bps: float = 10.0
    stamp_duty: StampDutySchedule = field(default_factory=StampDutySchedule)
    # Signal cutoff on the signal date, exchange local time (HH:MM). 15:00 =
    # strict close-of-day signal; e.g. 20:30 = post-close EOD signal. Must match
    # the production decision time being simulated; never mix in one study.
    signal_cutoff: str = "15:00"
    timezone: str = "Asia/Shanghai"
    # Missing limit price / preclose blocks the order (fail-closed).
    block_missing_limit_state: bool = True
    # Opening at the limit-up price: assume the buy cannot be filled. This is
    # a conservative approximation; intraday re-opening is not modeled.
    block_buy_at_limit_up_open: bool = True
    block_sell_at_limit_down_open: bool = True
    # Corporate actions: scale held shares by the adjustment-factor ratio on
    # the ex-date (= dividends/bonus reinvested at the ex price).
    corporate_action_policy: str = "factor_reinvest"  # factor_reinvest | fail_closed
    max_gross_weight: float = 1.0

    def __post_init__(self) -> None:
        if self.fill_price not in {"next_open", "next_close"}:
            raise ValueError("fill_price must be next_open or next_close")
        if self.lot_size <= 0:
            raise ValueError("lot_size must be positive")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        for name in ("commission_bps", "min_commission", "slippage_bps"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.corporate_action_policy not in {"factor_reinvest", "fail_closed"}:
            raise ValueError("unsupported corporate_action_policy")
        if not 0 < self.max_gross_weight <= 1.0:
            raise ValueError("max_gross_weight must be in (0, 1] (no leverage)")
        dt.time.fromisoformat(self.signal_cutoff)
        ZoneInfo(self.timezone)


def config_payload(config: Any) -> dict[str, Any]:
    return json.loads(json.dumps(dataclasses.asdict(config), sort_keys=True, default=str))


def config_hash(config: Any) -> str:
    payload = json.dumps(config_payload(config), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
