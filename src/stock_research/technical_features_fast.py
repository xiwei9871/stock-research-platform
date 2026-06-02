from __future__ import annotations

import numpy as np
import pandas as pd

from stock_research.factors.base import numeric_series, prepare_daily_bars, safe_divide
from stock_research.technical_features import (
    TECHNICAL_FEATURE_COLUMNS,
    _cci,
    _rolling_max_drawdown,
)


def _wilder_average_fast(values: pd.Series, window: int) -> pd.Series:
    clean = pd.to_numeric(values, errors="coerce")
    clean_values = clean.to_numpy(dtype="float64", copy=False)
    result = np.full(len(clean_values), np.nan, dtype="float64")
    if len(clean_values) < window:
        return pd.Series(result, index=clean.index, dtype="float64")

    previous = np.nan
    consecutive_valid = 0
    for index, value in enumerate(clean_values):
        if np.isnan(value):
            previous = np.nan
            consecutive_valid = 0
            continue

        consecutive_valid += 1
        if np.isnan(previous):
            if consecutive_valid < window:
                continue
            start = index - window + 1
            seed_window = clean_values[start : index + 1]
            if np.isnan(seed_window).any():
                consecutive_valid = 0
                continue
            previous = float(seed_window.mean())
            result[index] = previous
            continue

        previous = ((window - 1) * previous + float(value)) / window
        result[index] = previous

    return pd.Series(result, index=clean.index, dtype="float64")


def _rsi_fast(close: pd.Series, window: int) -> pd.Series:
    clean = pd.to_numeric(close, errors="coerce")
    close_values = clean.to_numpy(dtype="float64", copy=False)
    result = np.full(len(close_values), np.nan, dtype="float64")
    if len(close_values) <= window:
        return pd.Series(result, index=clean.index, dtype="float64")

    gain = np.full(len(close_values), np.nan, dtype="float64")
    loss = np.full(len(close_values), np.nan, dtype="float64")
    for index in range(1, len(close_values)):
        current = close_values[index]
        previous = close_values[index - 1]
        if np.isnan(current) or np.isnan(previous):
            continue
        delta = current - previous
        gain[index] = max(delta, 0.0)
        loss[index] = max(-delta, 0.0)

    avg_gain = np.nan
    avg_loss = np.nan
    consecutive_valid = 0
    for index in range(1, len(close_values)):
        gain_value = gain[index]
        loss_value = loss[index]
        if np.isnan(gain_value) or np.isnan(loss_value):
            avg_gain = np.nan
            avg_loss = np.nan
            consecutive_valid = 0
            continue

        consecutive_valid += 1
        if np.isnan(avg_gain) or np.isnan(avg_loss):
            if consecutive_valid < window:
                continue
            start = index - window + 1
            seed_gain = gain[start : index + 1]
            seed_loss = loss[start : index + 1]
            if np.isnan(seed_gain).any() or np.isnan(seed_loss).any():
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
            result[index] = 100.0
        elif avg_gain == 0.0 and avg_loss > 0.0:
            result[index] = 0.0
        elif avg_gain == 0.0 and avg_loss == 0.0:
            result[index] = 50.0
        else:
            rs = avg_gain / avg_loss
            result[index] = 100.0 - 100.0 / (1.0 + rs)

    return pd.Series(result, index=clean.index, dtype="float64")


def _wilder_average_fast_last(values: pd.Series, window: int) -> float:
    clean_values = pd.to_numeric(values, errors="coerce").to_numpy(dtype="float64", copy=False)
    if len(clean_values) < window:
        return np.nan

    previous = np.nan
    consecutive_valid = 0
    for index, value in enumerate(clean_values):
        if np.isnan(value):
            previous = np.nan
            consecutive_valid = 0
            continue

        consecutive_valid += 1
        if np.isnan(previous):
            if consecutive_valid < window:
                continue
            start = index - window + 1
            seed_window = clean_values[start : index + 1]
            if np.isnan(seed_window).any():
                consecutive_valid = 0
                continue
            previous = float(seed_window.mean())
            continue

        previous = ((window - 1) * previous + float(value)) / window

    return previous


def _rsi_fast_last(close: pd.Series, window: int) -> float:
    clean = pd.to_numeric(close, errors="coerce")
    close_values = clean.to_numpy(dtype="float64", copy=False)
    if len(close_values) <= window:
        return np.nan

    gain = np.full(len(close_values), np.nan, dtype="float64")
    loss = np.full(len(close_values), np.nan, dtype="float64")
    for index in range(1, len(close_values)):
        current = close_values[index]
        previous = close_values[index - 1]
        if np.isnan(current) or np.isnan(previous):
            continue
        delta = current - previous
        gain[index] = max(delta, 0.0)
        loss[index] = max(-delta, 0.0)

    avg_gain = np.nan
    avg_loss = np.nan
    consecutive_valid = 0
    latest = np.nan
    for index in range(1, len(close_values)):
        gain_value = gain[index]
        loss_value = loss[index]
        if np.isnan(gain_value) or np.isnan(loss_value):
            avg_gain = np.nan
            avg_loss = np.nan
            consecutive_valid = 0
            continue

        consecutive_valid += 1
        if np.isnan(avg_gain) or np.isnan(avg_loss):
            if consecutive_valid < window:
                continue
            start = index - window + 1
            seed_gain = gain[start : index + 1]
            seed_loss = loss[start : index + 1]
            if np.isnan(seed_gain).any() or np.isnan(seed_loss).any():
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
            latest = 100.0
        elif avg_gain == 0.0 and avg_loss > 0.0:
            latest = 0.0
        elif avg_gain == 0.0 and avg_loss == 0.0:
            latest = 50.0
        else:
            rs = avg_gain / avg_loss
            latest = 100.0 - 100.0 / (1.0 + rs)

    return latest


def _atr_fast(high: pd.Series, low: pd.Series, preclose: pd.Series, window: int) -> pd.Series:
    high_values = pd.to_numeric(high, errors="coerce").to_numpy(dtype="float64", copy=False)
    low_values = pd.to_numeric(low, errors="coerce").to_numpy(dtype="float64", copy=False)
    preclose_values = pd.to_numeric(preclose, errors="coerce").to_numpy(dtype="float64", copy=False)
    high_low = high_values - low_values
    high_preclose = np.abs(high_values - preclose_values)
    low_preclose = np.abs(low_values - preclose_values)
    stack = np.column_stack([high_low, high_preclose, low_preclose])
    true_range = np.full(len(high_values), np.nan, dtype="float64")
    valid = ~np.isnan(stack).all(axis=1)
    if valid.any():
        true_range[valid] = np.nanmax(stack[valid], axis=1)
    return _wilder_average_fast(pd.Series(true_range, index=high.index, dtype="float64"), window)


def _adx_fast(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> pd.Series:
    high_series = pd.to_numeric(high, errors="coerce")
    low_series = pd.to_numeric(low, errors="coerce")
    close_series = pd.to_numeric(close, errors="coerce")
    up_move = high_series.diff()
    down_move = -low_series.diff()
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
    atr = _atr_fast(high_series, low_series, close_series.shift(1), window)
    plus_dm_smoothed = _wilder_average_fast(plus_dm, window)
    minus_dm_smoothed = _wilder_average_fast(minus_dm, window)
    plus_di = safe_divide(100.0 * plus_dm_smoothed, atr)
    minus_di = safe_divide(100.0 * minus_dm_smoothed, atr)
    dx = safe_divide((plus_di - minus_di).abs(), plus_di + minus_di) * 100.0
    adx = pd.Series(np.nan, index=high.index, dtype="float64")
    first_dx_index = window - 1
    smoothed_dx = _wilder_average_fast(dx.iloc[first_dx_index:].reset_index(drop=True), window)
    for offset, value in enumerate(smoothed_dx):
        adx.iloc[first_dx_index + offset] = value
    return adx


def compute_latest_technical_features_fast(bars: pd.DataFrame) -> dict[str, object]:
    frame = prepare_daily_bars(bars)
    if frame.empty:
        return {"trade_date": None, **{column: np.nan for column in TECHNICAL_FEATURE_COLUMNS}}

    close = numeric_series(frame, "close")
    high = numeric_series(frame, "high")
    low = numeric_series(frame, "low")
    preclose = numeric_series(frame, "preclose").fillna(close.shift(1))
    volume = numeric_series(frame, "volume")
    amount = numeric_series(frame, "amount")

    ema12_series = close.ewm(span=12, adjust=False).mean()
    ema26_series = close.ewm(span=26, adjust=False).mean()
    macd_dif_series = ema12_series - ema26_series
    macd_dea_series = macd_dif_series.ewm(span=9, adjust=False).mean()
    rolling_std_20 = close.rolling(20).std()
    low14 = low.rolling(14).min()
    high14 = high.rolling(14).max()
    rsv = safe_divide(close - low14, high14 - low14) * 100.0
    kdj_k_series = rsv.ewm(com=2, adjust=False).mean()
    kdj_d_series = kdj_k_series.ewm(com=2, adjust=False).mean()
    direction = close.diff().fillna(0.0).apply(
        lambda value: 1.0 if value > 0.0 else -1.0 if value < 0.0 else 0.0
    )
    obv_series = (direction * volume.fillna(0.0)).cumsum()
    ret_1d_series = safe_divide(close, close.shift(1)) - 1.0

    result = {
        "trade_date": frame["trade_date"].iloc[-1],
        "ma5": _rolling_last_mean(close, 5),
        "ma10": _rolling_last_mean(close, 10),
        "ma20": _rolling_last_mean(close, 20),
        "ma60": _rolling_last_mean(close, 60),
        "ma120": _rolling_last_mean(close, 120),
        "ema12": _last_scalar(ema12_series),
        "ema26": _last_scalar(ema26_series),
        "macd_dif": _last_scalar(macd_dif_series),
        "macd_dea": _last_scalar(macd_dea_series),
        "macd_hist": _scalar_subtract(_last_scalar(macd_dif_series), _last_scalar(macd_dea_series), factor=2.0),
        "rsi6": _rsi_fast_last(close, 6),
        "rsi12": _rsi_fast_last(close, 12),
        "rsi24": _rsi_fast_last(close, 24),
        "boll_upper_20": _scalar_add(_rolling_last_mean(close, 20), _last_scalar(rolling_std_20), factor=2.0),
        "boll_mid_20": _rolling_last_mean(close, 20),
        "boll_lower_20": _scalar_add(_rolling_last_mean(close, 20), _last_scalar(rolling_std_20), factor=-2.0),
        "atr14": _last_scalar(_atr_fast(high, low, preclose, 14)),
        "cci14": _cci_last(high, low, close, 14),
        "kdj_k": _last_scalar(kdj_k_series),
        "kdj_d": _last_scalar(kdj_d_series),
        "kdj_j": _scalar_linear_combo(_last_scalar(kdj_k_series), _last_scalar(kdj_d_series), 3.0, -2.0),
        "adx14": _last_scalar(_adx_fast(high, low, close, 14)),
        "obv": _last_scalar(obv_series),
        "ret_1d": _last_scalar(ret_1d_series),
        "ret_20d": _return_last(close, 20),
        "close_position_in_day": _safe_last_ratio(_last_scalar(close) - _last_scalar(low), _last_scalar(high) - _last_scalar(low)),
        "amount_vs_20d": _safe_last_ratio(_last_scalar(amount), _rolling_last_mean(amount, 20)),
        "high_to_close_drawdown": _safe_last_ratio(_last_scalar(high) - _last_scalar(close), _last_scalar(high)),
        "volatility_5d": _rolling_last_std(ret_1d_series, 5),
        "max_drawdown_20d": _rolling_last_max_drawdown(close, 20),
        "atr_pct14": _safe_last_ratio(_last_scalar(_atr_fast(high, low, preclose, 14)), _last_scalar(close)),
    }
    return result


def compute_daily_technical_features_fast(bars: pd.DataFrame) -> pd.DataFrame:
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

    result["rsi6"] = _rsi_fast(close, 6)
    result["rsi12"] = _rsi_fast(close, 12)
    result["rsi24"] = _rsi_fast(close, 24)

    rolling_std_20 = close.rolling(20).std()
    result["boll_mid_20"] = result["ma20"]
    result["boll_upper_20"] = result["boll_mid_20"] + 2.0 * rolling_std_20
    result["boll_lower_20"] = result["boll_mid_20"] - 2.0 * rolling_std_20

    result["atr14"] = _atr_fast(high, low, preclose, 14)
    result["cci14"] = _cci(high, low, close, 14)

    low14 = low.rolling(14).min()
    high14 = high.rolling(14).max()
    rsv = safe_divide(close - low14, high14 - low14) * 100.0
    result["kdj_k"] = rsv.ewm(com=2, adjust=False).mean()
    result["kdj_d"] = result["kdj_k"].ewm(com=2, adjust=False).mean()
    result["kdj_j"] = 3.0 * result["kdj_k"] - 2.0 * result["kdj_d"]

    result["adx14"] = _adx_fast(high, low, close, 14)

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


def _rolling_last_mean(values: pd.Series, window: int) -> float:
    if len(values) < window:
        return np.nan
    window_values = pd.to_numeric(values, errors="coerce").iloc[-window:]
    if window_values.isna().any():
        return np.nan
    return float(window_values.mean())


def _rolling_last_std(values: pd.Series, window: int) -> float:
    if len(values) < window:
        return np.nan
    window_values = pd.to_numeric(values, errors="coerce").iloc[-window:]
    if window_values.isna().any():
        return np.nan
    return float(window_values.std())


def _rolling_last_max_drawdown(values: pd.Series, window: int) -> float:
    if len(values) < window:
        return np.nan
    window_values = pd.to_numeric(values, errors="coerce").to_numpy(dtype="float64", copy=False)[-window:]
    if np.isnan(window_values).any():
        return np.nan
    running_max = np.maximum.accumulate(window_values)
    drawdowns = window_values / running_max - 1.0
    return float(drawdowns.min())


def _return_last(values: pd.Series, period: int) -> float:
    clean = pd.to_numeric(values, errors="coerce")
    if len(clean) <= period:
        return np.nan
    current = clean.iloc[-1]
    previous = clean.iloc[-(period + 1)]
    return _safe_last_ratio(current, previous) - 1.0 if not np.isnan(_safe_last_ratio(current, previous)) else np.nan


def _cci_last(high: pd.Series, low: pd.Series, close: pd.Series, window: int) -> float:
    if len(close) < window:
        return np.nan
    typical_price = (pd.to_numeric(high, errors="coerce") + pd.to_numeric(low, errors="coerce") + pd.to_numeric(close, errors="coerce")) / 3.0
    window_values = typical_price.iloc[-window:]
    if window_values.isna().any():
        return np.nan
    mean_tp = float(window_values.mean())
    mean_dev = float(np.abs(window_values.to_numpy(dtype="float64", copy=False) - mean_tp).mean())
    if mean_dev == 0.0:
        return np.nan
    return float((window_values.iloc[-1] - mean_tp) / (0.015 * mean_dev))


def _last_scalar(values: pd.Series) -> float:
    if values.empty:
        return np.nan
    value = pd.to_numeric(values, errors="coerce").iloc[-1]
    return np.nan if pd.isna(value) else float(value)


def _safe_last_ratio(numerator: float, denominator: float) -> float:
    if np.isnan(numerator) or np.isnan(denominator) or denominator == 0.0:
        return np.nan
    return float(numerator / denominator)


def _scalar_add(left: float, right: float, *, factor: float = 1.0) -> float:
    if np.isnan(left) or np.isnan(right):
        return np.nan
    return float(left + factor * right)


def _scalar_subtract(left: float, right: float, *, factor: float = 1.0) -> float:
    if np.isnan(left) or np.isnan(right):
        return np.nan
    return float(factor * (left - right))


def _scalar_linear_combo(left: float, right: float, left_factor: float, right_factor: float) -> float:
    if np.isnan(left) or np.isnan(right):
        return np.nan
    return float(left_factor * left + right_factor * right)
