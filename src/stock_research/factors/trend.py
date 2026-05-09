import pandas as pd

from stock_research.factors.base import (
    numeric_series,
    prepare_daily_bars,
    rolling_r2,
    rolling_slope,
)


def compute_trend_factors(bars: pd.DataFrame) -> pd.DataFrame:
    frame = prepare_daily_bars(bars)
    close = numeric_series(frame, "close")
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    frame["ma20"] = ma20
    frame["ma60"] = ma60
    frame["close_above_ma20"] = close > ma20
    frame["close_above_ma60"] = close > ma60
    frame["ma20_slope"] = ma20 - ma20.shift(5)
    frame["ma60_slope"] = ma60 - ma60.shift(5)
    frame["ma_alignment"] = (close > ma20) & (ma20 > ma60)
    frame["new_high_20"] = close >= close.rolling(20).max()
    frame["new_high_60"] = close >= close.rolling(60).max()
    frame["trend_slope_20"] = rolling_slope(close, 20)
    frame["trend_r2_20"] = rolling_r2(close, 20)
    return frame
