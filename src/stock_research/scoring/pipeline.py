from __future__ import annotations

import pandas as pd

from stock_research.scoring import composite_score, rank_score
from stock_research.scoring.base import normalize_trade_keys


def score_factor_daily(
    factor_daily: pd.DataFrame,
    factor_directions: dict[str, str],
    weights: dict[str, float],
    score_version: str,
) -> pd.DataFrame:
    frame = normalize_trade_keys(factor_daily)
    frame["factor_name"] = frame["factor_name"].astype(str)
    frame["factor_value"] = pd.to_numeric(frame["factor_value"], errors="coerce")
    wide = (
        frame.pivot_table(
            index=["trade_date", "asset_id"],
            columns="factor_name",
            values="factor_value",
            aggfunc="first",
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )

    scored = wide
    for factor_name, direction in factor_directions.items():
        if factor_name not in scored.columns:
            continue
        if direction not in {"higher", "lower"}:
            raise ValueError(f"unsupported factor direction: {direction}")
        scored = rank_score.rank_score_by_date(
            scored,
            value_col=factor_name,
            ascending=direction == "lower",
            output_col=f"{factor_name}_score",
        )

    return composite_score.build_composite_scores(
        scored,
        weights=weights,
        score_version=score_version,
    )
