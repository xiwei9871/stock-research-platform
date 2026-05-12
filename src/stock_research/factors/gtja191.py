"""GTJA191-style adapter boundary.

These are small, tested short-horizon volume-price factors adapted to this
project. They are not a wholesale implementation of GTJA191.
"""

import pandas as pd

from stock_research.factors.base import prepare_daily_bars, rolling_corr, safe_divide

SOURCE = "gtja191"


def compute_gtja191_factors(bars: pd.DataFrame) -> pd.DataFrame:
    """Return representative GTJA191-style short-horizon price-volume factors.

    Inputs: trade_date, asset_id, high, low, close, volume, amount.
    Outputs:
    - gtja191_vp_corr_10: 10-day rolling price-volume correlation.
    - gtja191_amount_momentum_5_10: 5-day average amount divided by 10-day average amount.
    - gtja191_intraday_strength_6: 6-day mean close location inside high-low range.
    Future data: all rolling windows are backward-looking.
    """
    frame = prepare_daily_bars(bars)
    pieces = []
    for _, group in frame.groupby("asset_id", sort=False):
        asset = group.sort_values("trade_date").copy()
        close = pd.to_numeric(asset["close"], errors="coerce")
        high = pd.to_numeric(asset["high"], errors="coerce")
        low = pd.to_numeric(asset["low"], errors="coerce")
        amount = pd.to_numeric(asset["amount"], errors="coerce")
        asset["gtja191_vp_corr_10"] = rolling_corr(close, asset["volume"], window=10)
        asset["gtja191_amount_momentum_5_10"] = safe_divide(
            amount.rolling(5).mean(),
            amount.rolling(10).mean(),
        )
        asset["gtja191_intraday_strength_6"] = safe_divide(
            close - low,
            high - low,
        ).rolling(6).mean()
        pieces.append(asset)
    result = pd.concat(pieces, ignore_index=True)
    return result[
        [
            "trade_date",
            "asset_id",
            "gtja191_vp_corr_10",
            "gtja191_amount_momentum_5_10",
            "gtja191_intraday_strength_6",
        ]
    ]
