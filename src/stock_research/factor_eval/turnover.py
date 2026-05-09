from __future__ import annotations

import pandas as pd

from stock_research.factor_eval.base import normalize_keys


def calc_factor_turnover(
    factors: pd.DataFrame,
    factor_col: str = "factor_value",
    top_n: int = 20,
) -> pd.DataFrame:
    frame = normalize_keys(factors)
    frame[factor_col] = pd.to_numeric(frame[factor_col], errors="coerce")
    frame = frame.dropna(subset=[factor_col]).sort_values(["trade_date", factor_col, "asset_id"])

    top_by_date = {
        trade_date: set(
            group.sort_values([factor_col, "asset_id"], ascending=[False, True])
            .head(top_n)["asset_id"]
            .astype(str)
            .tolist()
        )
        for trade_date, group in frame.groupby("trade_date", sort=True)
    }

    rows = []
    previous_date = None
    previous_assets: set[str] | None = None
    for trade_date, assets in top_by_date.items():
        if previous_assets is not None and previous_date is not None:
            overlap = len(previous_assets & assets)
            denominator = min(top_n, len(previous_assets))
            rows.append(
                {
                    "trade_date": trade_date,
                    "previous_trade_date": previous_date,
                    "top_n": int(top_n),
                    "overlap_count": int(overlap),
                    "turnover": None if denominator == 0 else 1.0 - overlap / denominator,
                }
            )
        previous_date = trade_date
        previous_assets = assets

    return pd.DataFrame(
        rows,
        columns=["trade_date", "previous_trade_date", "top_n", "overlap_count", "turnover"],
    )
