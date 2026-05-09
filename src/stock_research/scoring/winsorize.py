from __future__ import annotations

import pandas as pd

from stock_research.scoring.base import normalize_trade_keys, numeric_column


def winsorize_by_date(
    frame: pd.DataFrame,
    value_col: str,
    lower_quantile: float = 0.01,
    upper_quantile: float = 0.99,
    output_col: str | None = None,
) -> pd.DataFrame:
    result = normalize_trade_keys(frame)
    output = output_col or f"{value_col}_winsorized"
    result[value_col] = numeric_column(result, value_col)

    clipped_frames = []
    for _, group in result.groupby("trade_date", sort=True):
        lower = group[value_col].quantile(lower_quantile)
        upper = group[value_col].quantile(upper_quantile)
        clipped = group.copy()
        clipped[output] = clipped[value_col].clip(lower=lower, upper=upper)
        clipped_frames.append(clipped)
    if not clipped_frames:
        result[output] = pd.Series(dtype="float64")
        return result
    return pd.concat(clipped_frames, ignore_index=True)
