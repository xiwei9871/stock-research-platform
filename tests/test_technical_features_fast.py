import numpy as np
import pandas as pd
import pytest

from stock_research.technical_features import (
    _adx,
    _rsi,
    _wilder_average,
    compute_daily_technical_features,
    compute_daily_technical_features_legacy,
    resolve_technical_feature_engine,
)
from stock_research.technical_features_fast import (
    _adx_fast,
    _rsi_fast,
    _wilder_average_fast,
    compute_daily_technical_features_fast,
)


def make_bars(closes: list[float]) -> pd.DataFrame:
    period_count = len(closes)
    return pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=period_count, freq="D"),
            "open": [close - 1.0 if not np.isnan(close) else np.nan for close in closes],
            "high": [close + 1.0 if not np.isnan(close) else np.nan for close in closes],
            "low": [close - 2.0 if not np.isnan(close) else np.nan for close in closes],
            "close": closes,
            "preclose": [np.nan] + closes[:-1],
            "volume": [1000.0 + index * 10.0 for index in range(period_count)],
            "amount": [10000.0 + index * 200.0 for index in range(period_count)],
            "turnover_rate": [1.0 + index * 0.02 for index in range(period_count)],
        }
    )


def test_wilder_average_fast_matches_legacy_with_missing_values():
    values = pd.Series(
        [1.0, 2.0, 3.0, np.nan, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
        dtype="float64",
    )

    legacy = _wilder_average(values, 3)
    fast = _wilder_average_fast(values, 3)

    pd.testing.assert_series_equal(fast, legacy, check_names=False)


def test_rsi_fast_matches_legacy_with_missing_values():
    close = pd.Series(
        [10.0, 11.0, 12.0, np.nan, 13.0, 12.0, 14.0, 15.0, 14.0, 16.0],
        dtype="float64",
    )

    legacy = _rsi(close, 3)
    fast = _rsi_fast(close, 3)

    pd.testing.assert_series_equal(fast, legacy, check_names=False)


def test_adx_fast_matches_legacy_with_missing_values():
    bars = make_bars([10.0, 11.0, 12.0, 13.0, np.nan, 14.0, 15.0, 14.0, 16.0, 17.0, 16.0, 18.0, 17.0, 19.0, 18.0, 20.0, 19.0, 21.0, 20.0, 22.0])
    legacy = _adx(bars["high"], bars["low"], bars["close"], 14)
    fast = _adx_fast(bars["high"], bars["low"], bars["close"], 14)

    pd.testing.assert_series_equal(fast, legacy, check_names=False)


def test_compute_daily_technical_features_fast_matches_legacy():
    bars = make_bars([10.0, 13.0, 12.0, 15.0, 14.0, 16.0, 15.0, 18.0, 17.0, 19.0, np.nan, 20.0, 19.0, 21.0, 20.0, 22.0, 21.0, 23.0, 22.0, 24.0, 23.0, 25.0, 24.0, 26.0, 25.0, 27.0, 26.0, 28.0, 27.0, 29.0])

    legacy = compute_daily_technical_features_legacy(bars)
    fast = compute_daily_technical_features_fast(bars)

    pd.testing.assert_frame_equal(fast, legacy)


def test_compute_daily_technical_features_defaults_to_fast():
    bars = make_bars([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0, 27.0, 28.0, 29.0])

    default_result = compute_daily_technical_features(bars)
    fast_result = compute_daily_technical_features_fast(bars)

    pd.testing.assert_frame_equal(default_result, fast_result)


def test_compute_daily_technical_features_supports_legacy_override():
    bars = make_bars([10.0, 13.0, 12.0, 15.0, 14.0, 16.0, 15.0, 18.0, 17.0, 19.0, 18.0, 20.0, 17.0, 19.0, 16.0, 18.0, 19.0, 17.0, 21.0, 20.0])

    override_result = compute_daily_technical_features(bars, engine="legacy")
    legacy_result = compute_daily_technical_features_legacy(bars)

    pd.testing.assert_frame_equal(override_result, legacy_result)


def test_compute_daily_technical_features_uses_environment_override(monkeypatch):
    monkeypatch.setenv("STOCK_RESEARCH_TECHNICAL_FEATURE_ENGINE", "legacy")
    bars = make_bars([float(index) for index in range(1, 25)])

    result = compute_daily_technical_features(bars)
    legacy = compute_daily_technical_features_legacy(bars)

    pd.testing.assert_frame_equal(result, legacy)


def test_resolve_technical_feature_engine_rejects_invalid_values():
    assert resolve_technical_feature_engine("fast") == "fast"
    assert resolve_technical_feature_engine("legacy") == "legacy"
    with pytest.raises(ValueError):
        resolve_technical_feature_engine("unknown")
