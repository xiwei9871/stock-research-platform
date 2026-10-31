"""LEGACY_COMPAT execution: weight-space, close-to-close, regression only.

Reproduces the conventions of the pre-existing engines so that strategy
adapters can be checked against old results. It is NOT a realistic A-share
model: weights never drift, fills happen at a close price, costs are a flat
rate on weight turnover.

fill_lag:
  1 -> signal on day t, trade at the close of t+1 (vectorized_topn_backtest)
  0 -> signal on day t, trade at the close of t   (TB serenity engine, MT)
The equity row for the trade day t' is dated t'+1 and carries the
close(t') -> close(t'+1) return of the post-trade weights, net of the costs
charged on t'.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from stock_research.backtest_constraints import (
    BacktestExecutionConstraints,
    can_close_long,
    can_open_long,
    one_way_cost_rate,
)


@dataclass(frozen=True)
class LegacyCompatConfig:
    fill_lag: int = 1
    apply_constraints: bool = True
    constraints: BacktestExecutionConstraints = field(
        default_factory=BacktestExecutionConstraints
    )

    def __post_init__(self) -> None:
        if self.fill_lag not in (0, 1):
            raise ValueError("fill_lag must be 0 or 1")


def _sell(asset, prev, target, signal_date, day, bar, cfg, rate):
    if cfg.apply_constraints:
        ok, reason = can_close_long(bar, cfg.constraints)
        if not ok:
            return None, {"signal_date": signal_date, "execution_date": day, "asset_id": asset,
                          "side": "sell", "previous_weight": prev, "target_weight": target,
                          "executed_weight": prev, "transaction_cost": 0.0, "skip_reason": reason}
    turnover = abs(target - prev)
    return target, {"signal_date": signal_date, "execution_date": day, "asset_id": asset,
                    "side": "sell", "previous_weight": prev, "target_weight": target,
                    "executed_weight": target, "transaction_cost": turnover * rate,
                    "skip_reason": None}


def execute_legacy_compat(
    target_weights: pd.DataFrame,
    prices: pd.DataFrame,
    trading_dates: list[str],
    signal_dates: list[str],
    config: LegacyCompatConfig,
) -> dict[str, pd.DataFrame]:
    """target_weights: signal_date, asset_id, target_weight (any rows).
    signal_dates: every date on which a (possibly empty) target is issued.
    prices: trade_date, asset_id, close (+ constraint flag columns)."""
    dates = list(trading_dates)
    idx = {d: i for i, d in enumerate(dates)}
    close = prices.pivot_table(index="trade_date", columns="asset_id", values="close",
                               aggfunc="last").sort_index()
    returns = close.pct_change(fill_method=None)
    bars: dict[str, dict[str, dict[str, Any]]] = {}
    for rec in prices.to_dict("records"):
        bars.setdefault(str(rec["trade_date"]), {})[str(rec["asset_id"])] = rec
    tw = target_weights.copy()
    tw["signal_date"] = tw["signal_date"].astype(str)
    targets = {d: {} for d in signal_dates}
    for rec in tw.to_dict("records"):
        if rec["signal_date"] in targets:
            targets[rec["signal_date"]][str(rec["asset_id"])] = float(rec["target_weight"])

    cons = config.constraints
    rate_buy = one_way_cost_rate("buy", cons)
    rate_sell = one_way_cost_rate("sell", cons)
    weights: dict[str, float] = {}
    cash = 1.0
    pending: dict[str, dict[str, Any]] = {}
    equity = 1.0
    equity_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []

    for i in range(config.fill_lag, len(dates)):
        day = dates[i]
        signal_date = dates[i - config.fill_lag]
        day_bars = bars.get(day, {})
        rows: list[dict[str, Any]] = []
        target = targets.get(signal_date) if signal_date in targets else None
        new_pending: dict[str, dict[str, Any]] = {}
        if target is not None:
            for asset in sorted(a for a in set(weights) | set(target)
                                if weights.get(a, 0.0) > target.get(a, 0.0)):
                prev = float(weights.get(asset, 0.0))
                tgt = float(target.get(asset, 0.0))
                done, row = _sell(asset, prev, tgt, signal_date, day, day_bars.get(asset, {}),
                                  config, rate_sell)
                rows.append(row)
                if done is None:
                    new_pending[asset] = {"signal_date": signal_date, "target_weight": tgt}
                    continue
                cash += prev - done
                if done > 0:
                    weights[asset] = done
                else:
                    weights.pop(asset, None)
            for asset, tgt in target.items():
                cur = float(weights.get(asset, 0.0))
                if tgt <= cur:
                    continue
                if config.apply_constraints:
                    ok, reason = can_open_long(day_bars.get(asset, {}), cons)
                    if not ok:
                        rows.append({"signal_date": signal_date, "execution_date": day,
                                     "asset_id": asset, "side": "buy", "previous_weight": cur,
                                     "target_weight": tgt, "executed_weight": cur,
                                     "transaction_cost": 0.0, "skip_reason": reason})
                        continue
                delta = min(tgt - cur, cash)
                cash -= delta
                if cur + delta > 0:
                    weights[asset] = cur + delta
                rows.append({"signal_date": signal_date, "execution_date": day, "asset_id": asset,
                             "side": "buy", "previous_weight": cur, "target_weight": tgt,
                             "executed_weight": cur + delta,
                             "transaction_cost": abs(delta) * rate_buy,
                             "skip_reason": None if delta == tgt - cur else "insufficient_cash"})
        retry = pending if target is None else {a: o for a, o in pending.items() if a not in target}
        remaining: dict[str, dict[str, Any]] = {}
        for asset, order in sorted(retry.items(), key=lambda kv: (str(kv[1]["signal_date"]), kv[0])):
            prev = float(weights.get(asset, 0.0))
            tgt = float(target[asset]) if target is not None and asset in target else float(order["target_weight"])
            if prev <= tgt:
                continue
            done, row = _sell(asset, prev, tgt, order["signal_date"], day,
                              day_bars.get(asset, {}), config, rate_sell)
            rows.append(row)
            if done is None:
                remaining[asset] = order
                continue
            cash += prev - done
            if done > 0:
                weights[asset] = done
            else:
                weights.pop(asset, None)
        pending = {**remaining, **new_pending}

        cost = float(sum(r["transaction_cost"] for r in rows))
        turnover = float(sum(abs(r["executed_weight"] - r["previous_weight"]) for r in rows))
        trade_rows.extend(rows)
        if i + 1 >= len(dates):
            if rows:
                if equity_rows and equity_rows[-1]["date"] == day:
                    last = equity_rows[-1]
                    prev_eq = equity_rows[-2]["equity"] if len(equity_rows) > 1 else 1.0
                    combined = last["equity"] * (1.0 - cost)
                    last.update({"turnover": turnover,
                                 "transaction_cost": last["transaction_cost"] + cost,
                                 "net_return": combined / prev_eq - 1.0, "equity": combined,
                                 "holdings_count": len(weights)})
                    equity = combined
                else:
                    equity *= 1.0 - cost
                    equity_rows.append({"date": day, "gross_return": 0.0, "turnover": turnover,
                                        "transaction_cost": cost, "net_return": -cost,
                                        "equity": equity, "holdings_count": len(weights)})
            continue
        nxt = dates[i + 1]
        gross = 0.0
        if weights and nxt in returns.index:
            row = returns.loc[nxt]
            for asset, w in weights.items():
                r = row.get(asset)
                if r is None or pd.isna(r):
                    continue
                gross += float(w) * float(r)
        net = gross - cost
        equity *= 1.0 + net
        equity_rows.append({"date": nxt, "gross_return": gross, "turnover": turnover,
                            "transaction_cost": cost, "net_return": net, "equity": equity,
                            "holdings_count": len(weights)})

    curve = pd.DataFrame(equity_rows, columns=["date", "gross_return", "turnover",
                                               "transaction_cost", "net_return", "equity",
                                               "holdings_count"])
    if not curve.empty:
        curve["drawdown"] = curve["equity"] / curve["equity"].cummax() - 1.0
    return {"equity": curve, "trades": pd.DataFrame(trade_rows)}
