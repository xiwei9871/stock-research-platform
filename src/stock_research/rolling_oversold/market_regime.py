"""Point-in-time market-regime features for rolling oversold research."""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd


def compute_market_regime_features(source: Any, *, anchor_date: date) -> dict[str, object]:
    """Return one frozen market-state record for the anchor cutoff.

    ``source`` may be a mapping or an object exposing ``index_bars``,
    ``stock_bars``, and optionally ``stock_status`` data frames.  This function
    deliberately performs no loading: every statistic is calculated from rows
    at or before ``anchor_date``.
    """

    if not isinstance(anchor_date, date):
        raise TypeError("anchor_date must be a date")

    index_bars = _as_frame(_source_value(source, "index_bars"), "index_bars")
    index_bars = _prepare_bars(index_bars, identifier="index_id", anchor_date=anchor_date)
    index_bars = index_bars.loc[index_bars["close"].notna()].copy()
    if index_bars.empty:
        raise ValueError("no usable index row exists on or before anchor_date")

    cutoff = index_bars["trade_date"].max().date()
    index_bars = index_bars.loc[index_bars["trade_date"].dt.date <= cutoff].copy()
    stock_bars = _prepare_bars(
        _as_frame(_source_value(source, "stock_bars", pd.DataFrame()), "stock_bars"),
        identifier="asset_id",
        anchor_date=cutoff,
    )
    stock_status = _prepare_status(
        _as_frame(_source_value(source, "stock_status", pd.DataFrame()), "stock_status"), cutoff
    )

    index_return_1d = _mean_latest_return(index_bars, periods=1)
    index_return_5d = _mean_latest_return(index_bars, periods=5)
    index_return_20d = _mean_latest_return(index_bars, periods=20)
    index_drawdown_20d = _mean_drawdown(index_bars, periods=20)
    latest_stock = _latest_stock_state(stock_bars, stock_status)
    valid_stock = latest_stock.loc[latest_stock["eligible"]].copy()
    stock_count = int(len(valid_stock))
    breadth_below_ma20 = _mean_or_nan(valid_stock.get("below_ma20"))
    breadth_below_ma60 = _mean_or_nan(valid_stock.get("below_ma60"))
    recent_rebound_breadth = _mean_or_nan(valid_stock.get("last_return") > 0)
    amount_ratio_5_20 = _amount_ratio(stock_bars)
    dispersion_20d = _dispersion_20d(stock_bars)
    recent_down_breadth = _recent_down_breadth(stock_bars, cutoff)
    status_stress_ratio = (
        (_count_true(latest_stock.get("is_st")) + _count_true(latest_stock.get("is_suspended")))
        / len(latest_stock)
        if len(latest_stock)
        else float("nan")
    )

    direction_score = _clip(
        50.0
        + _zero_if_nan(index_return_5d) * 200.0
        + (0.5 - _default(breadth_below_ma20, 0.5)) * 40.0
        + (0.5 - _default(breadth_below_ma60, 0.5)) * 20.0
        + np.clip(_default(amount_ratio_5_20, 1.0) - 1.0, -0.5, 0.5) * 10.0
        - min(_default(dispersion_20d, 0.0), 0.10) * 30.0
        - _default(status_stress_ratio, 0.0) * 20.0,
        0.0,
        100.0,
    )
    shock = (
        _default(index_drawdown_20d, 0.0) <= -0.08
        and (
            _default(recent_down_breadth, 0.0) >= 0.60
            or _default(breadth_below_ma20, 0.0) >= 0.65
        )
    )
    rebound = (
        _default(index_return_1d, 0.0) > 0.01
        and _default(recent_rebound_breadth, 0.0) >= 0.50
    )
    if shock and rebound and _default(breadth_below_ma20, 0.0) > 0.50:
        market_regime = "panic_rebound_watch"
    elif (
        direction_score < 40.0 and _default(breadth_below_ma20, 0.5) >= 0.55
    ) or _default(index_drawdown_20d, 0.0) <= -0.12:
        market_regime = "risk_off"
    elif (
        direction_score >= 60.0
        and _default(breadth_below_ma20, 0.5) < 0.45
        and _default(recent_rebound_breadth, 0.0) >= 0.45
    ):
        market_regime = "risk_on"
    else:
        market_regime = "neutral"

    return {
        "market_regime": market_regime,
        "market_direction_score": direction_score,
        "breadth_below_ma20": breadth_below_ma20,
        "breadth_below_ma60": breadth_below_ma60,
        "amount_ratio_5_20": amount_ratio_5_20,
        "data_cutoff_date": cutoff,
        "index_return_1d": index_return_1d,
        "index_return_5d": index_return_5d,
        "index_return_20d": index_return_20d,
        "index_drawdown_20d": index_drawdown_20d,
        "recent_rebound_breadth": recent_rebound_breadth,
        "recent_down_breadth": recent_down_breadth,
        "dispersion_20d": dispersion_20d,
        "status_stress_ratio": status_stress_ratio,
        "eligible_stock_count": stock_count,
        "below_ma20_count": _count_true(valid_stock.get("below_ma20")),
        "below_ma60_count": _count_true(valid_stock.get("below_ma60")),
        "rebound_stock_count": _count_true(valid_stock.get("last_return") > 0),
        "st_stock_count": _count_true(latest_stock.get("is_st")),
        "suspended_stock_count": _count_true(latest_stock.get("is_suspended")),
    }


def _source_value(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _as_frame(value: Any, name: str) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()
    if not isinstance(value, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame")
    return value.copy(deep=True)


def _prepare_bars(frame: pd.DataFrame, *, identifier: str, anchor_date: date) -> pd.DataFrame:
    required = {identifier, "trade_date", "close"}
    missing = required - set(frame.columns)
    if missing:
        if frame.empty:
            return pd.DataFrame(columns=[identifier, "trade_date", "close", "amount", "pct_chg"])
        raise ValueError(f"bars missing required columns: {', '.join(sorted(missing))}")
    result = frame.copy(deep=True)
    result[identifier] = result[identifier].astype("string").str.strip()
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce")
    result["close"] = pd.to_numeric(result["close"], errors="coerce")
    result["amount"] = pd.to_numeric(result.get("amount"), errors="coerce")
    result["pct_chg"] = _normalize_returns(result.get("pct_chg"), result.index)
    result = result.loc[
        result[identifier].notna()
        & result["trade_date"].notna()
        & (result["trade_date"].dt.date <= anchor_date)
    ].copy()
    duplicate_sort_columns = [
        column
        for column in ("close", "preclose", "high", "low", "amount", "volume", "pct_chg")
        if column in result
    ]
    result = result.sort_values(
        [identifier, "trade_date", *duplicate_sort_columns],
        kind="mergesort",
        na_position="first",
    )
    # Duplicate bars use the deterministic last row after nulls and values are
    # ordered.  This makes equal inputs independent of source row ordering.
    result = result.drop_duplicates([identifier, "trade_date"], keep="last")
    return result.sort_values([identifier, "trade_date"], kind="mergesort")


def _prepare_status(frame: pd.DataFrame, cutoff: date) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["asset_id", "trade_date"])
    if not {"asset_id", "trade_date"}.issubset(frame.columns):
        return pd.DataFrame(columns=["asset_id", "trade_date"])
    result = frame.copy(deep=True)
    result["asset_id"] = result["asset_id"].astype("string").str.strip()
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce")
    result = result.loc[
        result["asset_id"].notna()
        & result["trade_date"].notna()
        & (result["trade_date"].dt.date <= cutoff)
    ].copy()
    for column in ("is_trade", "is_st", "is_suspended", "is_limit_up", "is_limit_down"):
        result[column] = _as_bool(
            result.get(column), default=(column == "is_trade"), index=result.index
        )
    duplicate_sort_columns = [
        column
        for column in ("is_trade", "is_st", "is_suspended", "is_limit_up", "is_limit_down")
        if column in result
    ]
    result = result.sort_values(
        ["asset_id", "trade_date", *duplicate_sort_columns],
        kind="mergesort",
        na_position="first",
    )
    result = result.drop_duplicates(["asset_id", "trade_date"], keep="last")
    return result.sort_values(["asset_id", "trade_date"], kind="mergesort")


def _latest_stock_state(bars: pd.DataFrame, status: pd.DataFrame) -> pd.DataFrame:
    columns = ["asset_id", "below_ma20", "below_ma60", "last_return", "eligible", "is_st", "is_suspended"]
    if bars.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, object]] = []
    latest_status = status.groupby("asset_id", sort=False).tail(1).set_index("asset_id") if not status.empty else pd.DataFrame()
    for asset_id, group in bars.groupby("asset_id", sort=False):
        closes = group["close"].dropna().to_numpy(dtype=float)
        if not len(closes):
            continue
        latest = closes[-1]
        last_return = group["pct_chg"].iloc[-1]
        if pd.isna(last_return) and len(closes) > 1:
            last_return = latest / closes[-2] - 1.0
        flags = latest_status.loc[asset_id] if asset_id in latest_status.index else None
        is_trade = bool(flags["is_trade"]) if flags is not None else True
        is_st = bool(flags["is_st"]) if flags is not None else False
        is_suspended = bool(flags["is_suspended"]) if flags is not None else False
        rows.append(
            {
                "asset_id": asset_id,
                "below_ma20": bool(latest < np.mean(closes[-20:])),
                "below_ma60": bool(latest < np.mean(closes[-60:])),
                "last_return": last_return,
                "eligible": is_trade and not is_st and not is_suspended,
                "is_st": is_st,
                "is_suspended": is_suspended,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _mean_latest_return(bars: pd.DataFrame, *, periods: int) -> float:
    returns = []
    for _, group in bars.groupby("index_id", sort=False):
        closes = group["close"].dropna().to_numpy(dtype=float)
        if len(closes) > periods and closes[-periods - 1] != 0:
            returns.append(closes[-1] / closes[-periods - 1] - 1.0)
    return _mean_or_nan(pd.Series(returns, dtype="float64"))


def _mean_drawdown(bars: pd.DataFrame, *, periods: int) -> float:
    values = []
    for _, group in bars.groupby("index_id", sort=False):
        closes = group["close"].dropna().to_numpy(dtype=float)[-periods:]
        if len(closes) and np.max(closes) > 0:
            values.append(closes[-1] / np.max(closes) - 1.0)
    return _mean_or_nan(pd.Series(values, dtype="float64"))


def _amount_ratio(bars: pd.DataFrame) -> float:
    if bars.empty or bars["amount"].notna().sum() < 6:
        return float("nan")
    daily = bars.groupby("trade_date", sort=True)["amount"].sum(min_count=1).dropna()
    if len(daily) < 6:
        return float("nan")
    baseline = daily.tail(20).mean()
    return float(daily.tail(5).mean() / baseline) if baseline else float("nan")


def _dispersion_20d(bars: pd.DataFrame) -> float:
    if bars.empty:
        return float("nan")
    recent_dates = bars["trade_date"].drop_duplicates().sort_values().tail(20)
    values = bars.loc[bars["trade_date"].isin(recent_dates), "pct_chg"].dropna()
    return float(values.std(ddof=0)) if len(values) > 1 else float("nan")


def _recent_down_breadth(bars: pd.DataFrame, cutoff: date) -> float:
    if bars.empty:
        return float("nan")
    eligible = bars.loc[bars["trade_date"].dt.date <= cutoff]
    recent_dates = eligible["trade_date"].drop_duplicates().sort_values().tail(5)
    recent = eligible.loc[eligible["trade_date"].isin(recent_dates)]
    if recent.empty:
        return float("nan")
    grouped = recent.dropna(subset=["pct_chg"]).groupby("trade_date")["pct_chg"]
    ratios = [float((values < 0).mean()) for _, values in grouped if len(values)]
    return max(ratios) if ratios else float("nan")


def _normalize_returns(values: Any, index: pd.Index) -> pd.Series:
    if values is None:
        return pd.Series(float("nan"), index=index, dtype="float64")
    series = pd.to_numeric(values, errors="coerce")
    return series.where(series.abs() <= 1.0, series / 100.0)


def _as_bool(values: Any, *, default: bool, index: pd.Index) -> pd.Series:
    if values is None:
        return pd.Series(default, index=index, dtype=bool)
    if values.dtype == bool:
        return values.fillna(default)
    return values.map({True: True, False: False, 1: True, 0: False, "1": True, "0": False, "true": True, "false": False}).fillna(default).astype(bool)


def _mean_or_nan(values: Any) -> float:
    if values is None:
        return float("nan")
    series = pd.Series(values, dtype="float64").dropna()
    return float(series.mean()) if len(series) else float("nan")


def _count_true(values: Any) -> int:
    return int(pd.Series(values, dtype="bool").sum()) if values is not None else 0


def _default(value: float, fallback: float) -> float:
    return fallback if pd.isna(value) else float(value)


def _zero_if_nan(value: float) -> float:
    return 0.0 if pd.isna(value) else float(value)


def _clip(value: float, lower: float, upper: float) -> float:
    return float(min(max(value, lower), upper))
