from __future__ import annotations

import pandas as pd

from stock_research.scoring.base import normalize_trade_keys, numeric_column


def zscore_by_date(
    frame: pd.DataFrame,
    value_col: str,
    output_col: str | None = None,
) -> pd.DataFrame:
    result = normalize_trade_keys(frame)
    output = output_col or f"{value_col}_zscore"
    result[value_col] = numeric_column(result, value_col)

    scored_frames = []
    for _, group in result.groupby("trade_date", sort=True):
        values = group[value_col]
        mean = values.mean()
        std = values.std(ddof=0)
        scored = group.copy()
        if pd.isna(std) or std == 0.0:
            scored[output] = 0.0
        else:
            scored[output] = (values - mean) / std
        scored_frames.append(scored)
    if not scored_frames:
        result[output] = pd.Series(dtype="float64")
        return result
    return pd.concat(scored_frames, ignore_index=True)
