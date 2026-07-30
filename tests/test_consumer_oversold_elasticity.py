from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import numpy as np
import pandas as pd
import pytest

from stock_research.consumer_oversold.elasticity import (
    compute_residual_price_features,
)


TRADE_DATE = "2026-07-29"
EXPECTED_COLUMNS = [
    "asset_id",
    "latest_trade_date",
    "history_sessions",
    "price_series_source",
    "return_1d",
    "drawdown_from_high_1y",
    "drawdown_from_high_2y",
    "price_position_1y",
    "price_position_2y",
    "distance_raw_ma120",
    "distance_raw_ma250",
    "rebound_from_low_60d",
    "rebound_from_low_120d",
    "residual_deviation_coverage",
]


def _bars(
    asset_id: str,
    closes: list[object],
    *,
    raw_closes: list[object] | None = None,
    end: str = TRADE_DATE,
) -> pd.DataFrame:
    dates = pd.bdate_range(end=end, periods=len(closes))
    data: dict[str, object] = {
        "asset_id": asset_id,
        "trade_date": dates,
        "close": closes,
    }
    if raw_closes is not None:
        data["raw_close"] = raw_closes
    return pd.DataFrame(data)


def test_hfq_features_capture_large_remaining_deviation_after_a_10_percent_rise():
    close = [40.0] * 504
    close[300] = 100.0
    close[350] = 35.0
    close[-1] = 44.0
    result = compute_residual_price_features(
        _bars("A", close, raw_closes=[np.nan] * 504), trade_date=TRADE_DATE
    ).iloc[0]

    assert result["price_series_source"] == "hfq"
    assert result["return_1d"] == pytest.approx(0.10)
    assert result["drawdown_from_high_1y"] < -0.50
    assert result["drawdown_from_high_2y"] < -0.50
    assert result["price_position_1y"] < 0.20
    assert result["price_position_2y"] < 0.20
    assert result["residual_deviation_coverage"]


def test_hfq_features_capture_a_large_rebound_from_the_120_session_low():
    close = [80.0] * 504
    close[-120] = 40.0
    close[-1] = 70.0

    row = compute_residual_price_features(_bars("A", close), trade_date=TRADE_DATE).iloc[0]

    assert row["rebound_from_low_120d"] == pytest.approx(0.75)
    assert row["rebound_from_low_120d"] > 0.70


def test_one_and_two_year_windows_require_exactly_252_and_504_sessions():
    bars = pd.concat(
        [
            _bars("A251", [100.0] * 250 + [50.0]),
            _bars("A252", [100.0] + [50.0] * 251),
            _bars("A503", [100.0] + [50.0] * 300 + [80.0] + [50.0] * 201),
            _bars("A504", [100.0] + [50.0] * 300 + [80.0] + [50.0] * 202),
        ],
        ignore_index=True,
    )

    result = compute_residual_price_features(bars, trade_date=TRADE_DATE).set_index("asset_id")

    assert pd.isna(result.loc["A251", "drawdown_from_high_1y"])
    assert result.loc["A252", "drawdown_from_high_1y"] == pytest.approx(-0.50)
    assert pd.isna(result.loc["A503", "drawdown_from_high_2y"])
    assert result.loc["A504", "drawdown_from_high_2y"] == pytest.approx(-0.50)
    assert not result.loc["A503", "residual_deviation_coverage"]
    assert result.loc["A504", "residual_deviation_coverage"]


def test_future_bars_are_ignored_before_validation_and_do_not_change_results():
    history = _bars("A", [float(value) for value in range(1, 521)])
    expected = compute_residual_price_features(history, trade_date=TRADE_DATE)
    future = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "trade_date": "2026-07-30",
                "close": -1.0,
                "raw_close": "not-a-number",
            }
        ]
    )

    actual = compute_residual_price_features(
        pd.concat([future, history], ignore_index=True), trade_date=TRADE_DATE
    )

    pd.testing.assert_frame_equal(actual, expected)
    assert actual.iloc[0]["history_sessions"] == 520


def test_asset_present_only_after_cutoff_is_not_in_the_output_universe():
    future_only = pd.DataFrame(
        [
            {
                "asset_id": "FUTURE",
                "trade_date": "2026-07-30",
                "close": -1.0,
                "raw_close": "not-a-number",
            }
        ]
    )

    result = compute_residual_price_features(future_only, trade_date=TRADE_DATE)

    assert result.empty
    assert result.columns.tolist() == EXPECTED_COLUMNS


def test_input_order_does_not_change_sorted_asset_results():
    bars = pd.concat(
        [_bars("B", [20.0] * 504), _bars("A", [10.0] * 504)], ignore_index=True
    )
    shuffled = bars.sample(frac=1.0, random_state=17).reset_index(drop=True)

    result = compute_residual_price_features(shuffled, trade_date=TRADE_DATE)

    assert result["asset_id"].tolist() == ["A", "B"]
    assert result.set_index("asset_id").loc["A", "latest_trade_date"] == pd.Timestamp(
        TRADE_DATE
    )


def test_duplicate_asset_session_is_rejected_after_date_normalization():
    bars = pd.DataFrame(
        {
            "asset_id": ["A", "A"],
            "trade_date": ["2026-07-29 09:30:00", "2026-07-29 15:00:00"],
            "close": [10.0, 11.0],
            "raw_close": [10.0, 11.0],
        }
    )

    with pytest.raises(ValueError, match=r"duplicate.*A.*2026-07-29"):
        compute_residual_price_features(bars, trade_date=TRADE_DATE)


@pytest.mark.parametrize("invalid", ["10", np.nan, np.inf, 0.0, -1.0, True])
def test_invalid_hfq_close_is_rejected_with_asset_and_date_context(invalid):
    bars = _bars("A", [10.0, 11.0])
    bars["close"] = bars["close"].astype(object)
    bars.loc[bars.index[-1], "close"] = invalid

    with pytest.raises(ValueError, match=r"close.*A.*2026-07-29"):
        compute_residual_price_features(bars, trade_date=TRADE_DATE)


@pytest.mark.parametrize("invalid", [Decimal("1e10000"), Decimal("1e-10000")])
def test_decimal_close_must_still_be_finite_and_positive_after_float_conversion(invalid):
    bars = _bars("A", [10.0, invalid])
    bars["close"] = bars["close"].astype(object)

    with pytest.raises(ValueError, match=r"close.*A.*2026-07-29"):
        compute_residual_price_features(bars, trade_date=TRADE_DATE)


def test_positive_real_close_types_are_accepted():
    row = compute_residual_price_features(
        _bars("A", [Fraction(1, 2), Fraction(3, 4)]), trade_date=TRADE_DATE
    ).iloc[0]

    assert row["return_1d"] == pytest.approx(0.50)


def test_complete_hfq_history_has_coverage_when_all_raw_close_values_are_missing():
    close = [40.0] * 504
    close[0] = 100.0
    close[300] = 80.0
    close[-1] = 50.0
    bars = _bars("A", close, raw_closes=[np.nan] * 504)

    row = compute_residual_price_features(bars, trade_date=TRADE_DATE).iloc[0]

    assert row["price_series_source"] == "hfq"
    assert row["residual_deviation_coverage"]
    assert row["drawdown_from_high_2y"] == pytest.approx(-0.50)
    assert row["drawdown_from_high_1y"] == pytest.approx(50.0 / 80.0 - 1.0)
    assert row["distance_raw_ma120"] == pytest.approx(
        50.0 / np.mean(close[-120:]) - 1.0
    )


def test_raw_close_values_do_not_change_hfq_residual_features():
    close = [40.0] * 504
    close[0] = 100.0
    close[300] = 80.0
    close[-1] = 50.0
    missing_raw = _bars("A", close, raw_closes=[np.nan] * 504)
    unrelated_raw = _bars("A", close, raw_closes=[float(value) for value in range(1, 505)])

    missing_result = compute_residual_price_features(missing_raw, trade_date=TRADE_DATE)
    unrelated_result = compute_residual_price_features(unrelated_raw, trade_date=TRADE_DATE)

    pd.testing.assert_frame_equal(missing_result, unrelated_result)


def test_flat_price_windows_have_missing_positions_and_no_coverage():
    row = compute_residual_price_features(
        _bars("A", [10.0] * 504), trade_date=TRADE_DATE
    ).iloc[0]

    assert pd.isna(row["price_position_1y"])
    assert pd.isna(row["price_position_2y"])
    assert not row["residual_deviation_coverage"]


@pytest.mark.parametrize("trade_date", ["2026-7-29", "2026-02-30", "20260729", None])
def test_trade_date_must_be_a_real_strict_iso_date(trade_date):
    with pytest.raises(ValueError, match="trade_date must use YYYY-MM-DD"):
        compute_residual_price_features(_bars("A", [10.0]), trade_date=trade_date)


@pytest.mark.parametrize("asset_id", ["", "   ", None, pd.NA, np.nan])
def test_asset_id_must_be_nonempty(asset_id):
    with pytest.raises(ValueError, match="asset_id must be non-empty"):
        compute_residual_price_features(_bars(asset_id, [10.0]), trade_date=TRADE_DATE)


@pytest.mark.parametrize("missing", ["asset_id", "trade_date", "close"])
def test_required_market_columns_are_enforced(missing):
    bars = _bars("A", [10.0]).drop(columns=missing)

    with pytest.raises(ValueError, match=missing):
        compute_residual_price_features(bars, trade_date=TRADE_DATE)


def test_empty_input_returns_stable_schema():
    empty = pd.DataFrame(columns=["asset_id", "trade_date", "close"])

    result = compute_residual_price_features(empty, trade_date=TRADE_DATE)

    assert result.empty
    assert result.columns.tolist() == EXPECTED_COLUMNS
