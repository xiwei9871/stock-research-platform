from __future__ import annotations

import pandas as pd

from stock_research.scoring.base import normalize_trade_keys, numeric_column


def rank_score_by_date(
    frame: pd.DataFrame,
    value_col: str,
    ascending: bool = False,
    output_col: str | None = None,
) -> pd.DataFrame:
    result = normalize_trade_keys(frame)
    output = output_col or f"{value_col}_score"
    result[value_col] = numeric_column(result, value_col)

    scored_frames = []
    for _, group in result.groupby("trade_date", sort=True):
        scored = group.copy()
        valid = scored[value_col].notna()
        count = int(valid.sum())
        scored[output] = pd.NA
        if count == 1:
            scored.loc[valid, output] = 100.0
        elif count > 1:
            rank = scored.loc[valid, value_col].rank(method="average", ascending=ascending)
            scored.loc[valid, output] = (count - rank) / (count - 1) * 100.0
        scored_frames.append(scored)
    if not scored_frames:
        result[output] = pd.Series(dtype="float64")
        return result
    combined = pd.concat(scored_frames, ignore_index=True)
    combined[output] = pd.to_numeric(combined[output], errors="coerce")
    return combined
