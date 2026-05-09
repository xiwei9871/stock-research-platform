from __future__ import annotations

import pandas as pd


def summarize_ic_by_year(ic_frame: pd.DataFrame, ic_col: str = "ic") -> pd.DataFrame:
    if ic_frame.empty:
        return pd.DataFrame(columns=["year", "mean_ic", "ic_count"])
    frame = ic_frame.copy()
    frame["year"] = pd.to_datetime(frame["trade_date"]).dt.year
    frame[ic_col] = pd.to_numeric(frame[ic_col], errors="coerce")
    result = (
        frame.dropna(subset=[ic_col])
        .groupby("year", as_index=False)[ic_col]
        .agg(mean_ic="mean", ic_count="count")
        .sort_values("year")
        .reset_index(drop=True)
    )
    result["ic_count"] = result["ic_count"].astype(int)
    return result


def summarize_spread_by_year(spread_frame: pd.DataFrame) -> pd.DataFrame:
    if spread_frame.empty:
        return pd.DataFrame(columns=["year", "mean_top_bottom_spread", "spread_count"])
    frame = spread_frame.copy()
    frame["year"] = pd.to_datetime(frame["trade_date"]).dt.year
    frame["top_bottom_spread"] = pd.to_numeric(frame["top_bottom_spread"], errors="coerce")
    result = (
        frame.dropna(subset=["top_bottom_spread"])
        .groupby("year", as_index=False)["top_bottom_spread"]
        .agg(mean_top_bottom_spread="mean", spread_count="count")
        .sort_values("year")
        .reset_index(drop=True)
    )
    result["spread_count"] = result["spread_count"].astype(int)
    return result
