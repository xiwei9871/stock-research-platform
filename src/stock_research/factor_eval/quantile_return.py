from __future__ import annotations

import pandas as pd

from stock_research.factor_eval.base import merged_factor_returns


def calc_quantile_return(
    factors: pd.DataFrame,
    returns: pd.DataFrame,
    factor_col: str = "factor_value",
    return_col: str = "forward_return_5d",
    quantiles: int = 5,
    merged_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    merged = (
        merged_factor_returns(factors, returns, factor_col, return_col)
        if merged_frame is None
        else merged_frame.copy()
    )
    if merged.empty:
        return pd.DataFrame(columns=["trade_date", "quantile", "mean_return", "count"])

    assigned_frames = [
        _assign_quantiles(group, factor_col, quantiles)
        for _, group in merged.groupby("trade_date", sort=True)
    ]
    assigned = pd.concat(assigned_frames, ignore_index=True) if assigned_frames else pd.DataFrame()
    if assigned.empty:
        return pd.DataFrame(columns=["trade_date", "quantile", "mean_return", "count"])

    result = (
        assigned.groupby(["trade_date", "quantile"], as_index=False)[return_col]
        .agg(mean_return="mean", count="count")
        .sort_values(["trade_date", "quantile"])
        .reset_index(drop=True)
    )
    result["count"] = result["count"].astype(int)
    return result


def calc_top_bottom_spread(quantile_returns: pd.DataFrame) -> pd.DataFrame:
    if quantile_returns.empty:
        return pd.DataFrame(columns=["trade_date", "top_quantile", "bottom_quantile", "top_bottom_spread"])

    rows = []
    for trade_date, group in quantile_returns.groupby("trade_date", sort=True):
        clean = group.dropna(subset=["quantile", "mean_return"]).copy()
        if clean.empty:
            continue
        clean["quantile"] = pd.to_numeric(clean["quantile"], errors="coerce")
        clean["mean_return"] = pd.to_numeric(clean["mean_return"], errors="coerce")
        clean = clean.dropna(subset=["quantile", "mean_return"])
        if clean.empty:
            continue
        bottom = clean.loc[clean["quantile"].idxmin()]
        top = clean.loc[clean["quantile"].idxmax()]
        rows.append(
            {
                "trade_date": trade_date,
                "top_quantile": int(top["quantile"]),
                "bottom_quantile": int(bottom["quantile"]),
                "top_bottom_spread": float(top["mean_return"] - bottom["mean_return"]),
            }
        )
    return pd.DataFrame(
        rows,
        columns=["trade_date", "top_quantile", "bottom_quantile", "top_bottom_spread"],
    )


def _assign_quantiles(group: pd.DataFrame, factor_col: str, quantiles: int) -> pd.DataFrame:
    if group[factor_col].nunique(dropna=True) < quantiles:
        return pd.DataFrame(columns=list(group.columns) + ["quantile"])
    result = group.copy()
    quantile_codes = pd.qcut(
        result[factor_col],
        q=quantiles,
        labels=False,
        duplicates="drop",
    )
    result["quantile"] = quantile_codes + 1
    return result.dropna(subset=["quantile"])
