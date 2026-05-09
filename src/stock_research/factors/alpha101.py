"""WorldQuant Alpha101-style adapter boundary.

These are small representative price-volume factors inspired by Alpha101
building blocks. They are rewritten for this project's daily bar schema and do
not import external Alpha101 implementations.
"""

import pandas as pd

from stock_research.factors.base import (
    cross_sectional_rank,
    decay_linear,
    delta,
    prepare_daily_bars,
    rolling_corr,
)

SOURCE = "alpha101"


def compute_alpha101_factors(bars: pd.DataFrame) -> pd.DataFrame:
    """Return representative Alpha101-style factors.

    Inputs: trade_date, asset_id, open, close, volume.
    Outputs:
    - alpha101_delta_close_1_rank: cross-sectional rank of negative 1-day close delta.
    - alpha101_corr_open_volume_10: negative rolling correlation between open and volume.
    - alpha101_decay_delta_close_5: 5-day linear-decayed close delta.
    Future data: no future rows are used; all rolling windows are backward-looking.
    """
    frame = prepare_daily_bars(bars)
    pieces = []
    for _, group in frame.groupby("asset_id", sort=False):
        asset = group.sort_values("trade_date").copy()
        asset["_delta_close_1"] = delta(asset["close"], 1)
        asset["alpha101_corr_open_volume_10"] = -rolling_corr(
            asset["open"],
            asset["volume"],
            window=10,
        )
        asset["alpha101_decay_delta_close_5"] = decay_linear(
            delta(asset["close"], 1),
            window=5,
        )
        pieces.append(asset)

    result = pd.concat(pieces, ignore_index=True)
    result["alpha101_delta_close_1_rank"] = cross_sectional_rank(
        result.assign(_negative_delta=-result["_delta_close_1"]),
        "_negative_delta",
    )
    return result[
        [
            "trade_date",
            "asset_id",
            "alpha101_delta_close_1_rank",
            "alpha101_corr_open_volume_10",
            "alpha101_decay_delta_close_5",
        ]
    ]
