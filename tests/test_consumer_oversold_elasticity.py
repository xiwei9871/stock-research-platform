from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import numpy as np
import pandas as pd
import pytest

from stock_research.consumer_oversold.elasticity import (
    compute_residual_price_features,
    compute_stock_character_features,
    is_limit_up_day,
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
STOCK_CHARACTER_COLUMNS = [
    "asset_id",
    "history_sessions",
    "limit_up_count_2y",
    "up_7pct_count_2y",
    "up_5pct_count_2y",
    "mean_abs_return_2y",
    "return_volatility_2y",
    "upside_tail_volatility_2y",
    "max_limit_up_streak_2y",
    "positive_after_big_up_1d_rate",
    "positive_after_big_up_3d_rate",
    "positive_after_big_up_5d_rate",
    "stock_character_coverage",
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


def _character_bars(
    asset_id: str,
    pct_chg: list[object],
    *,
    stock_code: str = "000001",
    closes: list[object] | None = None,
    is_st: object = False,
    end: str = TRADE_DATE,
) -> pd.DataFrame:
    dates = pd.bdate_range(end=end, periods=len(pct_chg))
    return pd.DataFrame(
        {
            "asset_id": asset_id,
            "stock_code": stock_code,
            "trade_date": dates,
            "close": closes if closes is not None else [100.0] * len(pct_chg),
            "pct_chg": pct_chg,
            "is_st": [is_st] * len(pct_chg),
        }
    )


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


def test_fraction_close_is_rejected_with_asset_and_date_context():
    bars = _bars("A", [10.0, Fraction(3, 4)])

    with pytest.raises(ValueError, match=r"close.*A.*2026-07-29"):
        compute_residual_price_features(bars, trade_date=TRADE_DATE)


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


@pytest.mark.parametrize(
    ("stock_code", "is_st", "threshold"),
    [
        ("000001", False, 9.8),
        ("300001", False, 19.8),
        ("301001", False, 19.8),
        ("688001", False, 19.8),
        ("689001", False, 19.8),
        ("430001", False, 29.8),
        ("830001", False, 29.8),
        ("920422", False, 29.8),
        ("302132", False, 9.8),
        ("000001", True, 4.8),
    ],
)
def test_limit_up_thresholds_match_current_market_rules(stock_code, is_st, threshold):
    assert is_limit_up_day(
        stock_code, is_st, threshold, trade_date=TRADE_DATE
    )
    assert not is_limit_up_day(
        stock_code, is_st, threshold - 0.01, trade_date=TRADE_DATE
    )


def test_missing_pct_change_is_not_a_limit_up_day():
    assert not is_limit_up_day("000001", False, None, trade_date=TRADE_DATE)


def test_stock_character_counts_volatility_and_maximum_limit_up_streak_are_exact():
    pct_chg = [0.0] * 504
    pct_chg[:8] = [9.8, 10.0, 10.1, 0.0, 7.0, 5.0, -5.0, None]

    row = compute_stock_character_features(
        _character_bars("A", pct_chg), trade_date=TRADE_DATE
    ).iloc[0]

    returns = np.array([value for value in pct_chg if value is not None]) / 100.0
    positive_returns = returns[returns > 0.0]
    assert row["history_sessions"] == 504
    assert row["limit_up_count_2y"] == 3
    assert row["up_7pct_count_2y"] == 4
    assert row["up_5pct_count_2y"] == 5
    assert row["max_limit_up_streak_2y"] == 3
    assert row["mean_abs_return_2y"] == pytest.approx(np.mean(np.abs(returns)))
    assert row["return_volatility_2y"] == pytest.approx(np.std(returns, ddof=0))
    assert row["upside_tail_volatility_2y"] == pytest.approx(
        np.std(positive_returns, ddof=0)
    )
    assert row["stock_character_coverage"]


def test_big_up_continuation_rates_exclude_events_without_each_forward_horizon():
    pct_chg = [0.0] * 12
    for position in (0, 4, 8, 11):
        pct_chg[position] = 7.0
    closes = [100.0, 110.0, 100.0, 90.0, 100.0, 90.0, 100.0, 110.0, 100.0, 110.0, 100.0, 120.0]

    row = compute_stock_character_features(
        _character_bars("A", pct_chg, closes=closes), trade_date=TRADE_DATE
    ).iloc[0]

    assert row["positive_after_big_up_1d_rate"] == pytest.approx(2 / 3)
    assert row["positive_after_big_up_3d_rate"] == pytest.approx(2 / 3)
    assert row["positive_after_big_up_5d_rate"] == pytest.approx(1 / 2)


def test_future_stock_character_bars_are_ignored_before_asset_validation():
    history = _character_bars("A", [0.0] * 400)
    expected = compute_stock_character_features(history, trade_date=TRADE_DATE)
    future = pd.DataFrame(
        [
            {
                "asset_id": "",
                "stock_code": "",
                "trade_date": "2026-07-30",
                "close": "bad",
                "pct_chg": Fraction(1, 2),
                "is_st": "false",
            }
        ]
    )

    actual = compute_stock_character_features(
        pd.concat([future, history], ignore_index=True), trade_date=TRADE_DATE
    )

    pd.testing.assert_frame_equal(actual, expected)


def test_asset_present_only_after_cutoff_is_absent_from_stock_character_output():
    future_only = _character_bars("FUTURE", [9.8], end="2026-07-30")

    result = compute_stock_character_features(future_only, trade_date=TRADE_DATE)

    assert result.empty
    assert result.columns.tolist() == STOCK_CHARACTER_COLUMNS


def test_stock_character_results_are_sorted_and_duplicate_sessions_are_rejected():
    bars = pd.concat(
        [_character_bars("B", [0.0] * 10), _character_bars("A", [0.0] * 10)],
        ignore_index=True,
    ).sample(frac=1.0, random_state=9)

    result = compute_stock_character_features(bars, trade_date=TRADE_DATE)

    assert result["asset_id"].tolist() == ["A", "B"]
    duplicate = pd.concat([bars, bars.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        compute_stock_character_features(duplicate, trade_date=TRADE_DATE)


@pytest.mark.parametrize(
    ("column", "invalid"),
    [
        ("close", True),
        ("close", "100"),
        ("close", Fraction(100, 1)),
        ("close", Decimal("1e10000")),
        ("close", Decimal("1e-10000")),
        ("pct_chg", False),
        ("pct_chg", "9.8"),
        ("pct_chg", Fraction(49, 5)),
        ("pct_chg", Decimal("1e10000")),
        ("pct_chg", Decimal("sNaN")),
        ("is_st", 0),
        ("is_st", "false"),
    ],
)
def test_stock_character_inputs_reject_non_strict_or_nonfinite_values(column, invalid):
    bars = _character_bars("A", [0.0, 0.0])
    bars[column] = bars[column].astype(object)
    bars.loc[bars.index[-1], column] = invalid

    with pytest.raises(ValueError, match=column):
        compute_stock_character_features(bars, trade_date=TRADE_DATE)


def test_stock_character_accepts_numpy_numeric_decimal_and_numpy_boolean_values():
    bars = _character_bars(
        "A",
        [np.float64(9.8), Decimal("7.0"), np.int64(5), None],
        closes=[np.int64(100), Decimal("110.0"), np.float64(120.0), 121.0],
        is_st=np.bool_(False),
    )

    row = compute_stock_character_features(bars, trade_date=TRADE_DATE).iloc[0]

    assert row["limit_up_count_2y"] == 1
    assert row["up_7pct_count_2y"] == 2
    assert row["up_5pct_count_2y"] == 3


def test_pct_change_coverage_requires_400_valid_sessions_but_not_big_up_events():
    insufficient = compute_stock_character_features(
        _character_bars("A", [0.0] * 399 + [None] * 105), trade_date=TRADE_DATE
    ).iloc[0]
    complete = compute_stock_character_features(
        _character_bars("A", [0.0] * 400 + [None] * 104), trade_date=TRADE_DATE
    ).iloc[0]

    assert not insufficient["stock_character_coverage"]
    assert complete["stock_character_coverage"]
    assert pd.isna(complete["positive_after_big_up_1d_rate"])
    assert pd.isna(complete["positive_after_big_up_3d_rate"])
    assert pd.isna(complete["positive_after_big_up_5d_rate"])


@pytest.mark.parametrize(
    "missing",
    ["asset_id", "stock_code", "trade_date", "close", "pct_chg", "is_st"],
)
def test_required_stock_character_columns_are_enforced(missing):
    bars = _character_bars("A", [0.0]).drop(columns=missing)

    with pytest.raises(ValueError, match=missing):
        compute_stock_character_features(bars, trade_date=TRADE_DATE)


@pytest.mark.parametrize(("column", "invalid"), [("asset_id", "  "), ("stock_code", None)])
def test_stock_character_asset_and_code_must_be_nonempty(column, invalid):
    bars = _character_bars("A", [0.0])
    bars.loc[0, column] = invalid

    with pytest.raises(ValueError, match=column):
        compute_stock_character_features(bars, trade_date=TRADE_DATE)


@pytest.mark.parametrize("column", ["asset_id", "stock_code"])
@pytest.mark.parametrize("invalid", [123, True, False, Decimal("1")])
def test_stock_character_identifiers_reject_non_strings_with_value_context(
    column, invalid
):
    bars = _character_bars("A", [0.0])
    bars[column] = bars[column].astype(object)
    bars.loc[0, column] = invalid

    with pytest.raises(ValueError) as exc_info:
        compute_stock_character_features(bars, trade_date=TRADE_DATE)

    message = str(exc_info.value)
    assert column in message
    assert repr(invalid) in message


@pytest.mark.parametrize(
    "invalid",
    ["000001.SZ", "12345", "1234567", "ABCDEF", "０００００１"],
)
def test_stock_character_stock_code_must_be_six_ascii_digits(invalid):
    bars = _character_bars("A", [0.0], stock_code=invalid)

    with pytest.raises(ValueError, match=rf"stock_code.*{invalid}"):
        compute_stock_character_features(bars, trade_date=TRADE_DATE)


@pytest.mark.parametrize("invalid", [123, True, Decimal("1")])
def test_limit_up_api_rejects_non_string_stock_code_with_value_context(invalid):
    with pytest.raises(ValueError) as exc_info:
        is_limit_up_day(invalid, False, 9.8, trade_date=TRADE_DATE)

    message = str(exc_info.value)
    assert "stock_code" in message
    assert repr(invalid) in message


@pytest.mark.parametrize("invalid", ["000001.SZ", "12345", "ABCDEF", "０００００１"])
def test_limit_up_api_rejects_non_six_ascii_digit_stock_code(invalid):
    with pytest.raises(ValueError, match=rf"stock_code.*{invalid}"):
        is_limit_up_day(invalid, False, 9.8, trade_date=TRADE_DATE)


def test_empty_stock_character_input_returns_stable_schema():
    empty = pd.DataFrame(
        columns=["asset_id", "stock_code", "trade_date", "close", "pct_chg", "is_st"]
    )

    result = compute_stock_character_features(empty, trade_date=TRADE_DATE)

    assert result.empty
    assert result.columns.tolist() == STOCK_CHARACTER_COLUMNS
