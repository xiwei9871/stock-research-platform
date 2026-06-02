import numpy as np
import pandas as pd
import pytest

from stock_research.factors.base import max_drawdown
from stock_research.technical_features import (
    TECHNICAL_FEATURE_COLUMNS,
    _rolling_max_drawdown,
    compute_daily_technical_features,
)


def make_bars(closes: list[float]) -> pd.DataFrame:
    period_count = len(closes)
    return pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=period_count, freq="D"),
            "open": [close - 1.0 for close in closes],
            "high": [close + 1.0 for close in closes],
            "low": [close - 2.0 for close in closes],
            "close": closes,
            "preclose": [np.nan] + closes[:-1],
            "volume": [1000.0 + index * 10.0 for index in range(period_count)],
            "amount": [10000.0 + index * 200.0 for index in range(period_count)],
            "turnover_rate": [1.0 + index * 0.02 for index in range(period_count)],
        }
    )


def wilder_rsi(closes: list[float], window: int) -> float:
    deltas = np.diff(np.array(closes, dtype="float64"))
    gains = np.clip(deltas, 0.0, None)
    losses = np.clip(-deltas, 0.0, None)
    avg_gain = gains[:window].mean()
    avg_loss = losses[:window].mean()

    for gain, loss in zip(gains[window:], losses[window:], strict=False):
        avg_gain = ((window - 1) * avg_gain + gain) / window
        avg_loss = ((window - 1) * avg_loss + loss) / window

    if avg_loss == 0.0 and avg_gain > 0.0:
        return 100.0
    if avg_gain == 0.0 and avg_loss > 0.0:
        return 0.0
    if avg_gain == 0.0 and avg_loss == 0.0:
        return 50.0

    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


def test_constant_lists_full_technical_feature_schema():
    assert TECHNICAL_FEATURE_COLUMNS == [
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


def test_compute_daily_technical_features_preserves_rows_and_trade_dates():
    bars = make_bars([10.0, 11.0, 12.0])

    result = compute_daily_technical_features(bars)

    assert list(result["trade_date"]) == list(bars["trade_date"])
    assert len(result) == len(bars)
    assert list(result.columns) == ["trade_date", *TECHNICAL_FEATURE_COLUMNS]


def test_compute_daily_technical_features_outputs_expected_latest_values():
    bars = make_bars([float(index) for index in range(1, 31)])

    result = compute_daily_technical_features(bars)
    latest = result.iloc[-1]
    close = pd.Series([float(index) for index in range(1, 31)], dtype="float64")
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_dif = ema12 - ema26
    macd_dea = macd_dif.ewm(span=9, adjust=False).mean()
    rolling_std = close.rolling(20).std()
    amount = pd.Series([10000.0 + index * 200.0 for index in range(30)], dtype="float64")
    ret_1d = close.pct_change()

    assert latest["ma20"] == pytest.approx(close.tail(20).mean())
    assert latest["ret_20d"] == pytest.approx(30.0 / 10.0 - 1.0)
    assert latest["ema12"] == pytest.approx(float(ema12.iloc[-1]))
    assert latest["macd_dif"] == pytest.approx(float(macd_dif.iloc[-1]))
    assert latest["macd_dea"] == pytest.approx(float(macd_dea.iloc[-1]))
    assert latest["macd_hist"] == pytest.approx(float(2.0 * (macd_dif - macd_dea).iloc[-1]))
    assert latest["boll_mid_20"] == pytest.approx(close.tail(20).mean())
    assert latest["boll_upper_20"] == pytest.approx(float(close.tail(20).mean() + 2.0 * rolling_std.iloc[-1]))
    assert latest["boll_lower_20"] == pytest.approx(float(close.tail(20).mean() - 2.0 * rolling_std.iloc[-1]))
    assert latest["close_position_in_day"] == pytest.approx((30.0 - 28.0) / (31.0 - 28.0))
    assert latest["amount_vs_20d"] == pytest.approx(float(amount.iloc[-1] / amount.tail(20).mean()))
    assert latest["high_to_close_drawdown"] == pytest.approx((31.0 - 30.0) / 31.0)
    assert latest["volatility_5d"] == pytest.approx(float(ret_1d.tail(5).std()))
    assert latest["max_drawdown_20d"] == pytest.approx(0.0)
    assert latest["atr_pct14"] == pytest.approx(float(latest["atr14"] / 30.0))


def test_compute_daily_technical_features_uses_sorted_trade_dates_for_history():
    bars = make_bars([10.0, 11.0, 12.0, 13.0]).iloc[[2, 0, 3, 1]].reset_index(drop=True)

    result = compute_daily_technical_features(bars)

    sorted_dates = list(pd.to_datetime(bars["trade_date"]).sort_values())
    assert list(result["trade_date"]) == sorted_dates
    assert result.iloc[-1]["ret_1d"] == pytest.approx(13.0 / 12.0 - 1.0)


def test_compute_daily_technical_features_emits_nan_for_short_history_fields():
    bars = make_bars([10.0, 11.0, 12.0])

    result = compute_daily_technical_features(bars)

    assert pd.isna(result.iloc[-1]["ma20"])
    assert result.iloc[0]["ret_1d"] != result.iloc[0]["ret_1d"]
    assert result.iloc[-1]["ret_1d"] == pytest.approx(12.0 / 11.0 - 1.0)
    assert "adx14" in result.columns
    assert pd.isna(result.iloc[-1]["adx14"])


def test_compute_daily_technical_features_returns_full_rsi_for_monotonic_rise():
    bars = make_bars([float(index) for index in range(1, 15)])

    result = compute_daily_technical_features(bars)

    assert result.iloc[-1]["rsi6"] == pytest.approx(100.0)


def test_compute_daily_technical_features_returns_zero_rsi_for_monotonic_fall():
    bars = make_bars([float(index) for index in range(15, 1, -1)])

    result = compute_daily_technical_features(bars)

    assert result.iloc[-1]["rsi6"] == pytest.approx(0.0)


def test_compute_daily_technical_features_uses_wilder_rsi_smoothing():
    closes = [10.0, 13.0, 12.0, 15.0, 14.0, 16.0, 15.0, 18.0, 17.0, 19.0, 18.0]
    bars = make_bars(closes)

    result = compute_daily_technical_features(bars)

    assert result.iloc[-1]["rsi6"] == pytest.approx(wilder_rsi(closes, window=6))


def test_rolling_max_drawdown_matches_pandas_reference_with_missing_values():
    close = pd.Series(
        [
            10.0,
            12.0,
            11.0,
            13.0,
            9.0,
            8.0,
            9.0,
            7.0,
            8.0,
            10.0,
            np.nan,
            9.0,
            8.0,
            11.0,
            10.0,
            12.0,
            11.0,
            13.0,
            12.0,
            14.0,
            13.0,
            15.0,
        ],
        dtype="float64",
    )

    expected = close.rolling(20).apply(max_drawdown, raw=False)
    result = _rolling_max_drawdown(close, window=20)

    pd.testing.assert_series_equal(result, expected, check_names=False)


def test_compute_daily_technical_features_recovers_atr_after_interior_missing_bar():
    bars = make_bars([float(index) for index in range(1, 41)])
    bars.loc[18, "high"] = np.nan
    bars.loc[18, "low"] = np.nan

    result = compute_daily_technical_features(bars)

    assert pd.isna(result.iloc[18]["atr14"])
    assert pd.isna(result.iloc[31]["atr14"])
    assert not pd.isna(result.iloc[-1]["atr14"])


def test_compute_daily_technical_features_recovers_rsi_after_interior_missing_close():
    bars = make_bars([float(index) for index in range(1, 26)])
    bars.loc[10, "close"] = np.nan

    result = compute_daily_technical_features(bars)

    assert pd.isna(result.iloc[10]["rsi6"])
    assert pd.isna(result.iloc[16]["rsi6"])
    assert result.iloc[-1]["rsi6"] == pytest.approx(100.0)
