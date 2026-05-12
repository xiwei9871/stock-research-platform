from __future__ import annotations

import numpy as np
import pandas as pd


def prepare_daily_bars(bars: pd.DataFrame) -> pd.DataFrame:
    frame = bars.copy()
    if "trade_date" in frame.columns:
        frame = frame.sort_values("trade_date")
    return frame.reset_index(drop=True)


def numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    clean_numerator = pd.to_numeric(numerator, errors="coerce")
    clean_denominator = pd.to_numeric(denominator, errors="coerce").replace(0, np.nan)
    result = clean_numerator / clean_denominator
    return result.replace([np.inf, -np.inf], np.nan)


def cross_sectional_rank(frame: pd.DataFrame, column: str) -> pd.Series:
    values = numeric_series(frame, column)
    return values.groupby(frame["trade_date"]).rank(pct=True)


def ts_rank(values: pd.Series, window: int) -> pd.Series:
    clean = pd.to_numeric(values, errors="coerce")

    def rank_latest(window_values: pd.Series) -> float:
        if window_values.isna().any():
            return np.nan
        return float(window_values.rank(pct=True).iloc[-1])

    return clean.rolling(window).apply(rank_latest, raw=False)


def decay_linear(values: pd.Series, window: int) -> pd.Series:
    clean = pd.to_numeric(values, errors="coerce")
    weights = np.arange(1, window + 1, dtype="float64")
    denominator = float(weights.sum())

    def weighted(window_values: np.ndarray) -> float:
        if np.isnan(window_values).any():
            return np.nan
        return float(np.dot(window_values, weights) / denominator)

    return clean.rolling(window).apply(weighted, raw=True)


def delta(values: pd.Series, period: int = 1) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").diff(period)


def delay(values: pd.Series, period: int = 1) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").shift(period)


def signed_power(values: pd.Series, power: float) -> pd.Series:
    clean = pd.to_numeric(values, errors="coerce")
    return clean.abs().pow(power) * np.sign(clean)


def rolling_corr(left: pd.Series, right: pd.Series, window: int) -> pd.Series:
    return pd.to_numeric(left, errors="coerce").rolling(window).corr(
        pd.to_numeric(right, errors="coerce")
    )


def rolling_cov(left: pd.Series, right: pd.Series, window: int) -> pd.Series:
    return pd.to_numeric(left, errors="coerce").rolling(window).cov(
        pd.to_numeric(right, errors="coerce")
    )


def max_drawdown(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return np.nan
    drawdown = clean / clean.cummax() - 1.0
    return float(drawdown.min())


def rolling_slope(values: pd.Series, window: int) -> pd.Series:
    x = np.arange(window, dtype="float64")

    def slope(window_values: np.ndarray) -> float:
        if np.isnan(window_values).any():
            return np.nan
        return float(np.polyfit(x, window_values, 1)[0])

    return values.rolling(window).apply(slope, raw=True)


def rolling_r2(values: pd.Series, window: int) -> pd.Series:
    x = np.arange(window, dtype="float64")

    def r2(window_values: np.ndarray) -> float:
        if np.isnan(window_values).any():
            return np.nan
        y_mean = float(window_values.mean())
        total = float(((window_values - y_mean) ** 2).sum())
        if total == 0.0:
            return np.nan
        coefficients = np.polyfit(x, window_values, 1)
        fitted = coefficients[0] * x + coefficients[1]
        residual = float(((window_values - fitted) ** 2).sum())
        return float(1.0 - residual / total)

    return values.rolling(window).apply(r2, raw=True)
