"""REALISTIC_A_SHARE execution: share/cash ledger on raw prices.

Order of events on each execution day D (D = next trading day after the
signal date):
  1. corporate actions: held shares scaled by adj_factor[D]/adj_factor[prev]
     (dividends/bonus treated as reinvested at the ex price);
  2. sells (new-signal sells, then retries of pending blocked sells);
  3. buys, sized from the pre-trade NAV marked at preclose (sells use the
     same reference), largest target weight first;
     a blocked buy is cancelled and the cash stays in the account;
  4. mark-to-market at the raw close.
Fills use the raw open (or raw close) of D, never an adjusted price.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from stock_research.backtest_engine.config import RealisticExecutionConfig
from stock_research.backtest_engine.contracts import (
    ContractError,
    validate_price_bars,
    validate_target_weights,
)

TICK = 0.01


@dataclass
class _Account:
    cash: float
    shares: dict[str, float] = field(default_factory=dict)
    bought_on: dict[str, str] = field(default_factory=dict)
    last_close: dict[str, float] = field(default_factory=dict)
    last_factor: dict[str, float] = field(default_factory=dict)
    cum_cost: float = 0.0


def _fill_reference(bar: dict[str, Any], config: RealisticExecutionConfig) -> float:
    return float(bar["open"] if config.fill_price == "next_open" else bar["close"])


def _check_tradable(bar: dict[str, Any] | None, side: str,
                    config: RealisticExecutionConfig) -> str | None:
    """Return a rejection reason, or None when the order may be attempted."""
    if bar is None:
        return "no_bar"
    if bar.get("is_suspended") is None:
        return "suspension_state_missing"
    if bar["is_suspended"]:
        return "suspended"
    price = _fill_reference(bar, config)
    if price is None or not math.isfinite(price) or price <= 0:
        return "no_price"
    limit_col = "limit_up_price" if side == "buy" else "limit_down_price"
    limit = bar.get(limit_col)
    if limit is None or not math.isfinite(limit):
        return "limit_state_missing" if config.block_missing_limit_state else None
    if side == "buy" and config.block_buy_at_limit_up_open and price >= limit - TICK / 2:
        return "limit_up_at_fill"
    if side == "sell" and config.block_sell_at_limit_down_open and price <= limit + TICK / 2:
        return "limit_down_at_fill"
    return None


def _commission(value: float, config: RealisticExecutionConfig) -> float:
    if value <= 0:
        return 0.0
    return max(value * config.commission_bps / 10000.0, config.min_commission)


def execute_target_weights(
    target_weights: pd.DataFrame,
    price_bars: pd.DataFrame,
    trading_calendar: list[str],
    config: RealisticExecutionConfig,
) -> dict[str, pd.DataFrame]:
    targets = validate_target_weights(
        target_weights, max_gross_weight=config.max_gross_weight,
        signal_cutoff=config.signal_cutoff,
    )
    bars = validate_price_bars(price_bars)
    calendar = sorted({pd.Timestamp(d).date().isoformat() for d in trading_calendar})
    if len(calendar) < 2:
        raise ContractError("trading calendar needs at least two days")
    bad_signal = sorted(set(targets["signal_date"]) - set(calendar))
    if bad_signal:
        raise ContractError(f"signal_date not a trading day: {bad_signal[0]}")
    bars_by_day: dict[str, dict[str, dict[str, Any]]] = {}
    for rec in bars.to_dict("records"):
        bars_by_day.setdefault(rec["trade_date"], {})[rec["asset_id"]] = rec
    targets_by_signal = {
        day: dict(zip(frame["asset_id"], frame["target_weight"].astype(float)))
        for day, frame in targets.groupby("signal_date")
    }
    first_signal = min(targets_by_signal)
    days = [d for d in calendar if d >= first_signal]

    acct = _Account(cash=float(config.initial_cash))
    pending: dict[str, dict[str, Any]] = {}  # asset -> {target_weight, signal_date}
    equity_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    action_rows: list[dict[str, Any]] = []
    prev_nav = float(config.initial_cash)
    latest_target: dict[str, float] = {}

    for i, day in enumerate(days):
        day_bars = bars_by_day.get(day, {})
        nav_open = prev_nav
        # 1. corporate actions on held shares
        for asset in sorted(acct.shares):
            bar = day_bars.get(asset)
            if bar is None:
                continue
            factor = bar.get("adj_factor")
            prev_factor = acct.last_factor.get(asset)
            if factor is None or not math.isfinite(factor):
                if config.corporate_action_policy == "fail_closed":
                    raise ContractError(f"adj_factor missing for held {asset} on {day}")
                continue
            if prev_factor is not None and abs(factor / prev_factor - 1.0) > 1e-12:
                ratio = factor / prev_factor
                before = acct.shares[asset]
                acct.shares[asset] = before * ratio
                action_rows.append({"date": day, "asset_id": asset, "factor_ratio": ratio,
                                    "shares_before": before, "shares_after": acct.shares[asset]})
            acct.last_factor[asset] = factor

        signal_day = days[i - 1] if i > 0 else None
        new_signal = targets_by_signal.get(signal_day) if signal_day else None
        if new_signal is not None:
            latest_target = new_signal
            orders = {a: {"target_weight": new_signal.get(a, 0.0), "signal_date": signal_day}
                      for a in set(acct.shares) | set(new_signal)}
        else:
            orders = {}
        sell_queue = {a: o for a, o in pending.items() if a not in orders}
        sell_queue.update(orders)
        pending = {}

        def _value_mark(asset: str) -> float:
            bar = day_bars.get(asset)
            if bar is not None and bar.get("preclose") is not None and math.isfinite(bar["preclose"]):
                return float(bar["preclose"])
            return float(acct.last_close.get(asset, 0.0))

        nav_ref = acct.cash + sum(q * _value_mark(a) for a, q in acct.shares.items())

        # 2. sells
        for asset in sorted(sell_queue):
            order = sell_queue[asset]
            held = acct.shares.get(asset, 0.0)
            if held <= 0:
                continue
            bar = day_bars.get(asset)
            ref = _fill_reference(bar, config) if bar else None
            target_qty = 0.0
            if order["target_weight"] > 0 and ref:
                target_qty = math.floor(order["target_weight"] * nav_ref / ref / config.lot_size) * config.lot_size
            if target_qty >= held:
                continue
            reason = _check_tradable(bar, "sell", config)
            if reason is None and acct.bought_on.get(asset) == day:
                reason = "t_plus_1_unsellable"
            qty = held - target_qty if target_qty == 0 else math.floor((held - target_qty) / config.lot_size) * config.lot_size
            if reason is None and qty <= 0:
                continue
            row = {"signal_date": order["signal_date"], "execution_date": day, "asset_id": asset,
                   "side": "sell", "requested_quantity": held - target_qty}
            if reason is not None:
                pending[asset] = order
                trade_rows.append({**row, "filled_quantity": 0.0, "fill_price": None,
                                   "transaction_value": 0.0, "commission": 0.0, "stamp_duty": 0.0,
                                   "slippage": 0.0, "execution_status": "rejected",
                                   "rejection_reason": reason})
                continue
            fill = ref * (1 - config.slippage_bps / 10000.0)
            value = qty * fill
            commission = _commission(value, config)
            stamp = value * config.stamp_duty.bps_on(day) / 10000.0
            slippage = qty * ref - value
            acct.cash += value - commission - stamp
            acct.cum_cost += commission + stamp + slippage
            remaining = held - qty
            if remaining > 1e-9:
                acct.shares[asset] = remaining
            else:
                acct.shares.pop(asset, None)
                acct.bought_on.pop(asset, None)
            trade_rows.append({**row, "filled_quantity": qty, "fill_price": fill,
                               "transaction_value": value, "commission": commission,
                               "stamp_duty": stamp, "slippage": slippage,
                               "execution_status": "filled", "rejection_reason": None})

        # 3. buys (only on new-signal days)
        if new_signal is not None:
            for asset, weight in sorted(new_signal.items(), key=lambda kv: (-kv[1], kv[0])):
                bar = day_bars.get(asset)
                held = acct.shares.get(asset, 0.0)
                ref = _fill_reference(bar, config) if bar else None
                want = (math.floor(weight * nav_ref / ref / config.lot_size) * config.lot_size
                        if ref and weight > 0 else 0.0)
                if want <= held:
                    continue
                row = {"signal_date": signal_day, "execution_date": day, "asset_id": asset,
                       "side": "buy", "requested_quantity": want - held}
                reason = _check_tradable(bar, "buy", config)
                qty = 0.0
                if reason is None:
                    fill = ref * (1 + config.slippage_bps / 10000.0)
                    qty = want - held
                    while qty > 0 and qty * fill + _commission(qty * fill, config) > acct.cash + 1e-9:
                        qty -= config.lot_size
                    if qty <= 0:
                        reason = "insufficient_cash"
                if reason is not None:
                    trade_rows.append({**row, "filled_quantity": 0.0, "fill_price": None,
                                       "transaction_value": 0.0, "commission": 0.0,
                                       "stamp_duty": 0.0, "slippage": 0.0,
                                       "execution_status": "rejected", "rejection_reason": reason})
                    continue
                value = qty * fill
                commission = _commission(value, config)
                slippage = value - qty * ref
                acct.cash -= value + commission
                acct.cum_cost += commission + slippage
                acct.shares[asset] = held + qty
                acct.bought_on[asset] = day
                if bar.get("adj_factor") is not None and math.isfinite(bar["adj_factor"]):
                    acct.last_factor[asset] = bar["adj_factor"]
                status = "filled" if qty == want - held else "partial"
                trade_rows.append({**row, "filled_quantity": qty, "fill_price": fill,
                                   "transaction_value": value, "commission": commission,
                                   "stamp_duty": 0.0, "slippage": slippage,
                                   "execution_status": status,
                                   "rejection_reason": None if status == "filled" else "insufficient_cash"})

        if acct.cash < -1e-6:
            raise AssertionError(f"negative cash on {day}: {acct.cash}")

        # 4. mark to market
        market_value = 0.0
        for asset in sorted(acct.shares):
            bar = day_bars.get(asset)
            if bar is not None and bar.get("close") is not None and math.isfinite(bar["close"]):
                acct.last_close[asset] = float(bar["close"])
            price = acct.last_close.get(asset)
            if price is None:
                raise ContractError(f"no price to value held {asset} on {day}")
            mv = acct.shares[asset] * price
            market_value += mv
            position_rows.append({"date": day, "asset_id": asset, "shares": acct.shares[asset],
                                  "price": price, "market_value": mv,
                                  "target_weight": latest_target.get(asset, 0.0)})
        nav = acct.cash + market_value
        if not math.isfinite(nav):
            raise AssertionError(f"non-finite NAV on {day}")
        for row in position_rows[len(position_rows) - len(acct.shares):]:
            row["weight"] = row["market_value"] / nav if nav else 0.0
        equity_rows.append({"date": day, "nav_open": nav_open, "nav_close": nav,
                            "daily_return": nav / nav_open - 1.0 if nav_open else 0.0,
                            "cash": acct.cash, "market_value": market_value,
                            "cumulative_cost": acct.cum_cost,
                            "pending_sells": len(pending)})
        prev_nav = nav

    equity = pd.DataFrame(equity_rows)
    if not equity.empty:
        equity["drawdown"] = equity["nav_close"] / equity["nav_close"].cummax() - 1.0
    return {
        "equity": equity,
        "positions": pd.DataFrame(position_rows),
        "trades": pd.DataFrame(trade_rows),
        "corporate_actions": pd.DataFrame(action_rows),
    }
