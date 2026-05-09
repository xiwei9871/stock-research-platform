from __future__ import annotations

import pandas as pd

from stock_research.scoring.base import normalize_trade_keys


def build_composite_scores(
    frame: pd.DataFrame,
    weights: dict[str, float],
    score_version: str,
    output_col: str = "score_total",
) -> pd.DataFrame:
    if not weights:
        raise ValueError("weights must not be empty")

    result = normalize_trade_keys(frame)
    normalized_weights = _normalize_weights(weights)
    result[output_col] = 0.0
    for column, weight in normalized_weights.items():
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0.0)
        result[output_col] += result[column] * weight

    ranked_frames = []
    for _, group in result.groupby("trade_date", sort=True):
        ranked = group.copy().sort_values([output_col, "asset_id"], ascending=[False, True])
        ranked["rank"] = range(1, len(ranked) + 1)
        ranked["score_version"] = score_version
        ranked_frames.append(ranked)

    if not ranked_frames:
        result["rank"] = pd.Series(dtype="int64")
        result["score_version"] = score_version
        return result
    columns = ["trade_date", "asset_id", "rank", output_col, "score_version"] + list(weights.keys())
    return pd.concat(ranked_frames, ignore_index=True).reindex(columns=columns)


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    numeric_weights = {key: float(value) for key, value in weights.items()}
    total = sum(abs(value) for value in numeric_weights.values())
    if total == 0.0:
        raise ValueError("at least one weight must be non-zero")
    return {key: value / total for key, value in numeric_weights.items()}
