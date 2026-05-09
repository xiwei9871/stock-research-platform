import numpy as np
import pandas as pd

from stock_research.factors.base import numeric_series, prepare_daily_bars, safe_divide


def compute_volume_price_factors(bars: pd.DataFrame) -> pd.DataFrame:
    frame = prepare_daily_bars(bars)
    close = numeric_series(frame, "close")
    volume = numeric_series(frame, "volume")
    amount = numeric_series(frame, "amount")
    turnover = numeric_series(frame, "turnover_rate")

    frame["amount_ratio_5_20"] = safe_divide(amount.rolling(5).mean(), amount.rolling(20).mean())
    frame["volume_ratio_5_20"] = safe_divide(volume.rolling(5).mean(), volume.rolling(20).mean())
    frame["turnover_ratio_5_20"] = safe_divide(turnover.rolling(5).mean(), turnover.rolling(20).mean())
    frame["price_volume_corr_10"] = close.rolling(10).corr(volume).replace([np.inf, -np.inf], np.nan)

    price_direction = close.diff().fillna(0.0).apply(lambda value: 1.0 if value > 0 else -1.0 if value < 0 else 0.0)
    frame["obv"] = (price_direction * volume.fillna(0.0)).cumsum()
    frame["obv_trend_20"] = frame["obv"] - frame["obv"].shift(20)
    frame["volume_breakout"] = volume >= volume.rolling(20).max()
    frame["amount_breakout"] = amount >= amount.rolling(20).max()
    return frame
