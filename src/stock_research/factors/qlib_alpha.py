"""Qlib Alpha158/360-style adapter boundary.

Qlib is a reference for factor organization and Alpha158/360 price-shape ideas,
not a runtime dependency or the project framework.
"""

import pandas as pd

from stock_research.factors.base import prepare_daily_bars, safe_divide

SOURCE = "qlib"


def compute_qlib_alpha_factors(bars: pd.DataFrame) -> pd.DataFrame:
    """Return representative Qlib-style price shape and return factors.

    Inputs: trade_date, asset_id, open, high, low, close.
    Outputs:
    - qlib_klen: absolute candle body divided by open.
    - qlib_kupper: upper shadow divided by open.
    - qlib_klower: lower shadow divided by open.
    - qlib_ret_5: 5-day close return.
    Future data: no future rows are used.
    """
    frame = prepare_daily_bars(bars)
    pieces = []
    for _, group in frame.groupby("asset_id", sort=False):
        asset = group.sort_values("trade_date").copy()
        open_ = pd.to_numeric(asset["open"], errors="coerce")
        high = pd.to_numeric(asset["high"], errors="coerce")
        low = pd.to_numeric(asset["low"], errors="coerce")
        close = pd.to_numeric(asset["close"], errors="coerce")
        body_high = pd.concat([open_, close], axis=1).max(axis=1)
        body_low = pd.concat([open_, close], axis=1).min(axis=1)
        asset["qlib_klen"] = safe_divide((close - open_).abs(), open_)
        asset["qlib_kupper"] = safe_divide(high - body_high, open_)
        asset["qlib_klower"] = safe_divide(body_low - low, open_)
        asset["qlib_ret_5"] = safe_divide(close, close.shift(5)) - 1.0
        pieces.append(asset)
    result = pd.concat(pieces, ignore_index=True)
    return result[
        [
            "trade_date",
            "asset_id",
            "qlib_klen",
            "qlib_kupper",
            "qlib_klower",
            "qlib_ret_5",
        ]
    ]
