"""Single place for performance metric definitions (252-day year).

Benchmark: a frame with columns date, benchmark_return (simple daily
returns on the engine's calendar). Excess = strategy - benchmark daily
return (arithmetic); tracking error and information ratio annualized
with sqrt(252). Days missing from the benchmark are excluded from excess
statistics and counted in benchmark_missing_days.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def _annualize(total: float, periods: int) -> float:
    if not periods or total <= -1:
        return float("nan")
    return (1.0 + total) ** (TRADING_DAYS_PER_YEAR / periods) - 1.0


def _sharpe(rets: pd.Series) -> float:
    if len(rets) < 2 or rets.std(ddof=1) == 0:
        return float("nan")
    return float(rets.mean() / rets.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR))


def benchmark_stats(equity: pd.DataFrame, benchmark: pd.DataFrame) -> dict[str, Any]:
    strat = equity[["date", "daily_return"]].iloc[1:].copy()
    bench = benchmark[["date", "benchmark_return"]].copy()
    bench["date"] = pd.to_datetime(bench["date"]).dt.strftime("%Y-%m-%d")
    merged = strat.merge(bench, on="date", how="left")
    missing = int(merged["benchmark_return"].isna().sum())
    merged = merged.dropna(subset=["benchmark_return"])
    if merged.empty:
        return {"benchmark_missing_days": missing}
    excess = merged["daily_return"] - merged["benchmark_return"]
    periods = len(merged)
    bench_total = float((1.0 + merged["benchmark_return"]).prod() - 1.0)
    strat_total = float((1.0 + merged["daily_return"]).prod() - 1.0)
    te = float(excess.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR)) if periods > 1 else float("nan")
    return {
        "benchmark_total_return": bench_total,
        "benchmark_annualized_return": _annualize(bench_total, periods),
        "excess_total_return": strat_total - bench_total,
        "excess_annualized_return": _annualize(strat_total, periods) - _annualize(bench_total, periods),
        "tracking_error": te,
        "information_ratio": _sharpe(excess),
        "benchmark_days": periods,
        "benchmark_missing_days": missing,
    }


def summarize(
    result: dict[str, Any],
    *,
    initial_cash: float,
    benchmark: pd.DataFrame | None = None,
) -> dict[str, Any]:
    equity = result["equity"]
    trades = result.get("trades", pd.DataFrame())
    if equity.empty:
        return {"periods": 0}
    nav = equity["nav_close"].astype(float)
    rets = equity["daily_return"].astype(float).iloc[1:]
    periods = len(rets)
    total = float(nav.iloc[-1] / initial_cash - 1.0)
    ann = _annualize(total, periods)
    vol = float(rets.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR)) if periods > 1 else float("nan")
    mdd = float((nav / nav.cummax() - 1.0).min())
    calmar = ann / abs(mdd) if mdd < 0 and not math.isnan(ann) else float("nan")
    out: dict[str, Any] = {
        "periods": periods, "total_return": total, "annualized_return": ann,
        "annualized_volatility": vol, "sharpe": _sharpe(rets), "max_drawdown": mdd,
        "calmar": calmar, "total_cost": float(equity["cumulative_cost"].iloc[-1]),
    }
    if not trades.empty:
        filled = trades[trades["execution_status"].isin(["filled", "partial"])]
        traded_value = float(filled["transaction_value"].sum())
        avg_nav = float(nav.mean())
        out["annualized_turnover"] = ((traded_value / 2.0 / avg_nav) * TRADING_DAYS_PER_YEAR / periods
                                      if periods and avg_nav else float("nan"))
        out["order_count"] = int(len(trades))
        out["fill_rate"] = float(len(filled) / len(trades))
        rejected = trades[trades["execution_status"] == "rejected"]
        out["buy_blocked"] = int((rejected["side"] == "buy").sum())
        out["sell_blocked"] = int((rejected["side"] == "sell").sum())
        out["suspension_blocked"] = int((rejected["rejection_reason"] == "suspended").sum())
        out["rejection_reasons"] = {str(k): int(v)
                                    for k, v in rejected["rejection_reason"].value_counts().items()}
    if benchmark is not None:
        out.update(benchmark_stats(equity, benchmark))
    return out
