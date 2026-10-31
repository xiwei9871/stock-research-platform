"""Single place for performance metric definitions (252-day year)."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def summarize(result: dict[str, pd.DataFrame], *, initial_cash: float) -> dict[str, Any]:
    equity = result["equity"]
    trades = result.get("trades", pd.DataFrame())
    if equity.empty:
        return {"periods": 0}
    nav = equity["nav_close"].astype(float)
    rets = equity["daily_return"].astype(float).iloc[1:]
    periods = len(rets)
    total = float(nav.iloc[-1] / initial_cash - 1.0)
    ann = (1.0 + total) ** (TRADING_DAYS_PER_YEAR / periods) - 1.0 if periods and total > -1 else float("nan")
    vol = float(rets.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR)) if periods > 1 else float("nan")
    sharpe = float(rets.mean() / rets.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR)) if periods > 1 and rets.std(ddof=1) > 0 else float("nan")
    mdd = float((nav / nav.cummax() - 1.0).min())
    calmar = ann / abs(mdd) if mdd < 0 and not math.isnan(ann) else float("nan")
    out: dict[str, Any] = {
        "periods": periods, "total_return": total, "annualized_return": ann,
        "annualized_volatility": vol, "sharpe": sharpe, "max_drawdown": mdd, "calmar": calmar,
        "total_cost": float(equity["cumulative_cost"].iloc[-1]),
    }
    if not trades.empty:
        filled = trades[trades["execution_status"].isin(["filled", "partial"])]
        traded_value = float(filled["transaction_value"].sum())
        avg_nav = float(nav.mean())
        out["annualized_turnover"] = (traded_value / 2.0 / avg_nav) * TRADING_DAYS_PER_YEAR / periods if periods and avg_nav else float("nan")
        out["order_count"] = int(len(trades))
        out["fill_rate"] = float(len(filled) / len(trades))
        rejected = trades[trades["execution_status"] == "rejected"]
        out["buy_blocked"] = int((rejected["side"] == "buy").sum())
        out["sell_blocked"] = int((rejected["side"] == "sell").sum())
        out["suspension_blocked"] = int((rejected["rejection_reason"] == "suspended").sum())
        out["rejection_reasons"] = {str(k): int(v) for k, v in rejected["rejection_reason"].value_counts().items()}
    return out
