from __future__ import annotations

import pandas as pd

from stock_research.factor_eval.base import KEY_COLUMNS, merged_factor_returns, normalize_keys


def summarize_return_by_segment(
    factors: pd.DataFrame,
    returns: pd.DataFrame,
    segments: pd.DataFrame,
    segment_col: str,
    factor_col: str = "factor_value",
    return_col: str = "forward_return_5d",
) -> pd.DataFrame:
    merged = merged_factor_returns(factors, returns, factor_col, return_col)
    segment_frame = normalize_keys(segments)
    joined = merged.merge(segment_frame[KEY_COLUMNS + [segment_col]], on=KEY_COLUMNS, how="inner")
    if joined.empty:
        return pd.DataFrame(columns=[segment_col, "mean_return", "count"])
    result = (
        joined.groupby(segment_col, as_index=False)[return_col]
        .agg(mean_return="mean", count="count")
        .sort_values(segment_col)
        .reset_index(drop=True)
    )
    result["count"] = result["count"].astype(int)
    return result
