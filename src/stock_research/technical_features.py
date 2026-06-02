from __future__ import annotations

import os
import numpy as np
import pandas as pd

from stock_research.factors.base import (
    numeric_series,
    prepare_daily_bars,
    safe_divide,
)


TECHNICAL_FEATURE_COLUMNS = [
    "ma5",
    "ma10",
    "ma20",
    "ma60",
    "ma120",
    "ema12",
    "ema26",
    "macd_dif",
    "macd_dea",
    "macd_hist",
    "rsi6",
    "rsi12",
    "rsi24",
    "boll_upper_20",
    "boll_mid_20",
    "boll_lower_20",
    "atr14",
    "cci14",
    "kdj_k",
    "kdj_d",
    "kdj_j",
    "adx14",
    "obv",
    "ret_1d",
    "ret_20d",
    "close_position_in_day",
    "amount_vs_20d",
    "high_to_close_drawdown",
    "volatility_5d",
    "max_drawdown_20d",
    "atr_pct14",
]

TECHNICAL_FEATURE_ENGINE_ENV = "STOCK_RESEARCH_TECHNICAL_FEATURE_ENGINE"
DEFAULT_TECHNICAL_FEATURE_ENGINE = "fast"


def _wilder_average(values: pd.Series, window: int) -> pd.Series:
    clean = pd.to_numeric(values, errors="coerce")
    result = pd.Series(np.nan, index=clean.index, dtype="float64")
    if len(clean) < window:
        return result

    previous = np.nan
    consecutive_valid = 0

    for index, value in enumerate(clean):
        if pd.isna(value):
            previous = np.nan
            consecutive_valid = 0
            continue

        consecutive_valid += 1

        if pd.isna(previous):
            if consecutive_valid < window:
                continue
            start = index - window + 1
            seed_window = clean.iloc[start : index + 1]
            if seed_window.isna().any():
                consecutive_valid = 0
                continue
            previous = float(seed_window.mean())
            result.iloc[index] = previous
            continue

        previous = ((window - 1) * previous + float(value)) / window
        result.iloc[index] = previous

    return result


def _rsi(close: pd.Series, window: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    result = pd.Series(np.nan, index=close.index, dtype="float64")
    if len(close) <= window:
        return result

    avg_gain = np.nan
    avg_loss = np.nan
    consecutive_valid = 0

    for index in range(1, len(close)):
        gain_value = gain.iloc[index]
        loss_value = loss.iloc[index]
        if pd.isna(gain_value) or pd.isna(loss_value):
            avg_gain = np.nan
            avg_loss = np.nan
            consecutive_valid = 0
            continue

        consecutive_valid += 1
        if pd.isna(avg_gain) or pd.isna(avg_loss):
            if consecutive_valid < window:
                continue
            start = index - window + 1
            seed_gain = gain.iloc[start : index + 1]
            seed_loss = loss.iloc[start : index + 1]
            if seed_gain.isna().any() or seed_loss.isna().any():
                avg_gain = np.nan
                avg_loss = np.nan
                consecutive_valid = 0
                continue
            avg_gain = float(seed_gain.mean())
            avg_loss = float(seed_loss.mean())
        else:
            avg_gain = ((window - 1) * avg_gain + float(gain_value)) / window
            avg_loss = ((window - 1) * avg_loss + float(loss_value)) / window
        if avg_loss == 0.0 and avg_gain > 0.0:
            result.iloc[index] = 100.0
        elif avg_gain == 0.0 and avg_loss > 0.0:
            result.iloc[index] = 0.0
        elif avg_gain == 0.0 and avg_loss == 0.0:
            result.iloc[index] = 50.0
        else:
            rs = avg_gain / avg_loss
            result.iloc[index] = 100.0 - 100.0 / (1.0 + rs)
    return result


def _mean_absolute_deviation(values: np.ndarray) -> float:
    if np.isnan(values).any():
        return np.nan
    center = float(values.mean())
    return float(np.abs(values - center).mean())


def _cci(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> pd.Series:
    typical_price = (high + low + close) / 3.0
    mean_tp = typical_price.rolling(window).mean()
    mean_dev = typical_price.rolling(window).apply(_mean_absolute_deviation, raw=True)
    return safe_divide(typical_price - mean_tp, 0.015 * mean_dev)


def _atr(high: pd.Series, low: pd.Series, preclose: pd.Series, window: int) -> pd.Series:
    true_range = pd.concat(
        [
            high - low,
            (high - preclose).abs(),
            (low - preclose).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return _wilder_average(true_range, window)


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> pd.Series:
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0.0), up_move, 0.0),
        index=high.index,
        dtype="float64",
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0.0), down_move, 0.0),
        index=high.index,
        dtype="float64",
    )
    atr = _atr(high, low, close.shift(1), window)
    plus_dm_smoothed = _wilder_average(plus_dm, window)
    minus_dm_smoothed = _wilder_average(minus_dm, window)
    plus_di = safe_divide(100.0 * plus_dm_smoothed, atr)
    minus_di = safe_divide(100.0 * minus_dm_smoothed, atr)
    dx = safe_divide((plus_di - minus_di).abs(), plus_di + minus_di) * 100.0
    adx = pd.Series(np.nan, index=high.index, dtype="float64")
    first_dx_index = window - 1
    smoothed_dx = _wilder_average(dx.iloc[first_dx_index:].reset_index(drop=True), window)
    for offset, value in enumerate(smoothed_dx):
        adx.iloc[first_dx_index + offset] = value
    return adx


def _rolling_max_drawdown(values: pd.Series, window: int) -> pd.Series:
    clean = pd.to_numeric(values, errors="coerce")
    result = pd.Series(np.nan, index=clean.index, dtype="float64")
    if len(clean) < window:
        return result

    window_values = np.lib.stride_tricks.sliding_window_view(
        clean.to_numpy(dtype="float64", copy=False),
        window_shape=window,
    )
    valid = ~np.isnan(window_values).any(axis=1)
    if not valid.any():
        return result

    valid_windows = window_values[valid]
    running_max = np.maximum.accumulate(valid_windows, axis=1)
    drawdowns = valid_windows / running_max - 1.0
    result_values = drawdowns.min(axis=1)

    result_array = result.to_numpy(dtype="float64", copy=True)
    result_array[np.flatnonzero(valid) + window - 1] = result_values
    return pd.Series(result_array, index=clean.index, dtype="float64")


def resolve_technical_feature_engine(engine: str | None = None) -> str:
    resolved = str(engine or os.environ.get(TECHNICAL_FEATURE_ENGINE_ENV) or DEFAULT_TECHNICAL_FEATURE_ENGINE)
    if resolved not in {"fast", "legacy"}:
        raise ValueError(
            f"unsupported technical feature engine: {resolved}"
        )
    return resolved


def compute_daily_technical_features_legacy(bars: pd.DataFrame) -> pd.DataFrame:
    frame = prepare_daily_bars(bars)
    if frame.empty:
        return pd.DataFrame(columns=["trade_date", *TECHNICAL_FEATURE_COLUMNS])

    close = numeric_series(frame, "close")
    high = numeric_series(frame, "high")
    low = numeric_series(frame, "low")
    preclose = numeric_series(frame, "preclose").fillna(close.shift(1))
    volume = numeric_series(frame, "volume")
    amount = numeric_series(frame, "amount")

    result = pd.DataFrame({"trade_date": frame["trade_date"]})

    for window in (5, 10, 20, 60, 120):
        result[f"ma{window}"] = close.rolling(window).mean()

    result["ema12"] = close.ewm(span=12, adjust=False).mean()
    result["ema26"] = close.ewm(span=26, adjust=False).mean()
    result["macd_dif"] = result["ema12"] - result["ema26"]
    result["macd_dea"] = result["macd_dif"].ewm(span=9, adjust=False).mean()
    result["macd_hist"] = 2.0 * (result["macd_dif"] - result["macd_dea"])

    result["rsi6"] = _rsi(close, 6)
    result["rsi12"] = _rsi(close, 12)
    result["rsi24"] = _rsi(close, 24)

    rolling_std_20 = close.rolling(20).std()
    result["boll_mid_20"] = result["ma20"]
    result["boll_upper_20"] = result["boll_mid_20"] + 2.0 * rolling_std_20
    result["boll_lower_20"] = result["boll_mid_20"] - 2.0 * rolling_std_20

    result["atr14"] = _atr(high, low, preclose, 14)
    result["cci14"] = _cci(high, low, close, 14)

    low14 = low.rolling(14).min()
    high14 = high.rolling(14).max()
    rsv = safe_divide(close - low14, high14 - low14) * 100.0
    result["kdj_k"] = rsv.ewm(com=2, adjust=False).mean()
    result["kdj_d"] = result["kdj_k"].ewm(com=2, adjust=False).mean()
    result["kdj_j"] = 3.0 * result["kdj_k"] - 2.0 * result["kdj_d"]

    result["adx14"] = _adx(high, low, close, 14)

    direction = close.diff().fillna(0.0).apply(
        lambda value: 1.0 if value > 0.0 else -1.0 if value < 0.0 else 0.0
    )
    result["obv"] = (direction * volume.fillna(0.0)).cumsum()

    result["ret_1d"] = safe_divide(close, close.shift(1)) - 1.0
    result["ret_20d"] = safe_divide(close, close.shift(20)) - 1.0
    result["close_position_in_day"] = safe_divide(close - low, high - low)
    result["amount_vs_20d"] = safe_divide(amount, amount.rolling(20).mean())
    result["high_to_close_drawdown"] = safe_divide(high - close, high)
    result["volatility_5d"] = result["ret_1d"].rolling(5).std()
    result["max_drawdown_20d"] = _rolling_max_drawdown(close, window=20)
    result["atr_pct14"] = safe_divide(result["atr14"], close)

    return result[["trade_date", *TECHNICAL_FEATURE_COLUMNS]]


def compute_daily_technical_features(
    bars: pd.DataFrame,
    *,
    engine: str | None = None,
) -> pd.DataFrame:
    resolved_engine = resolve_technical_feature_engine(engine)
    if resolved_engine == "legacy":
        return compute_daily_technical_features_legacy(bars)

    from stock_research.technical_features_fast import (
        compute_daily_technical_features_fast,
    )

    return compute_daily_technical_features_fast(bars)
