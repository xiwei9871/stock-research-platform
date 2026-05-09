import pandas as pd

from stock_research.factors.base import numeric_series, prepare_daily_bars


def compute_momentum_factors(bars: pd.DataFrame) -> pd.DataFrame:
    frame = prepare_daily_bars(bars)
    close = numeric_series(frame, "close")

    for window in (5, 10, 20, 60, 120):
        frame[f"ret_{window}"] = close / close.shift(window) - 1.0
        frame[f"absolute_momentum_{window}"] = frame[f"ret_{window}"]

    frame["momentum_20_5"] = frame["ret_20"] - frame["ret_5"]
    frame["momentum_60_5"] = frame["ret_60"] - frame["ret_5"]
    return frame
