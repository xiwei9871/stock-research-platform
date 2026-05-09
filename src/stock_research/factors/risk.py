import numpy as np
import pandas as pd

from stock_research.factors.base import (
    max_drawdown,
    numeric_series,
    prepare_daily_bars,
    safe_divide,
)


def compute_risk_factors(bars: pd.DataFrame) -> pd.DataFrame:
    frame = prepare_daily_bars(bars)
    close = numeric_series(frame, "close")
    high = numeric_series(frame, "high")
    low = numeric_series(frame, "low")
    open_ = numeric_series(frame, "open")
    preclose = numeric_series(frame, "preclose").fillna(close.shift(1))

    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    true_range = pd.concat(
        [
            high - low,
            (high - preclose).abs(),
            (low - preclose).abs(),
        ],
        axis=1,
    ).max(axis=1)

    frame["volatility_20"] = close.pct_change().rolling(20).std()
    frame["max_drawdown_20"] = close.rolling(20).apply(max_drawdown, raw=False)
    frame["atr_14"] = true_range.rolling(14).mean()
    frame["atr_pct"] = safe_divide(frame["atr_14"], close)
    frame["distance_ma20"] = close / ma20 - 1.0
    frame["distance_ma60"] = close / ma60 - 1.0

    upper_shadow = high - pd.concat([open_, close], axis=1).max(axis=1)
    full_range = (high - low).replace(0, np.nan)
    frame["upper_shadow_ratio"] = upper_shadow / full_range
    frame["large_volume_down_day"] = (close < preclose) & (
        numeric_series(frame, "amount") > numeric_series(frame, "amount").rolling(20).mean() * 1.5
    )
    return frame
