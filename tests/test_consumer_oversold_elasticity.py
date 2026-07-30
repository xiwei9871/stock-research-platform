from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import numpy as np
import pandas as pd
import pytest

from stock_research.consumer_oversold.contracts import ConsumerOversoldConfig
from stock_research.consumer_oversold.elasticity import (
    compute_market_capacity_features,
    compute_residual_price_features,
    compute_stock_character_features,
    is_limit_up_day,
    score_rebound_elasticity,
)


TRADE_DATE = "2026-07-29"
CONFIG = ConsumerOversoldConfig(trade_date=TRADE_DATE)
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
    "distance_hfq_ma120",
    "distance_hfq_ma250",
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
MARKET_CAPACITY_COLUMNS = [
    "asset_id",
    "latest_trade_date",
    "history_sessions",
    "current_total_market_cap",
    "current_float_market_cap",
    "log_current_float_market_cap",
    "market_cap_source",
    "average_amount_20d",
    "average_turnover_rate_20d",
    "amount_to_float_cap_20d",
    "market_capacity_coverage",
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


def _capacity_bars(
    asset_id: str,
    *,
    sessions: int = 20,
    raw_close: object = 10.0,
    amount: object = 200.0,
    turnover_rate: object = 2.0,
    end: str = TRADE_DATE,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "asset_id": asset_id,
            "trade_date": pd.bdate_range(end=end, periods=sessions),
            "raw_close": [raw_close] * sessions,
            "amount": [amount] * sessions,
            "turnover_rate": [turnover_rate] * sessions,
        }
    )


def _capacity_shares(
    asset_id: str,
    *,
    total_share: object = 100.0,
    float_share: object = 80.0,
    free_float_share: object = 60.0,
) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "total_share": total_share,
        "float_share": float_share,
        "free_float_share": free_float_share,
    }


def _elasticity_row(**overrides):
    row = {
        "asset_id": "A",
        "eligible": True,
        "automatic_eligible": True,
        "drawdown_from_high_1y": -0.40,
        "drawdown_from_high_2y": -0.50,
        "price_position_1y": 0.20,
        "price_position_2y": 0.25,
        "distance_hfq_ma120": -0.10,
        "distance_hfq_ma250": -0.15,
        "rebound_from_low_60d": 0.10,
        "rebound_from_low_120d": 0.15,
        "relative_return_6m": -0.20,
        "valuation_percentile": 0.20,
        "residual_deviation_coverage": True,
        "limit_up_count_2y": 2.0,
        "up_7pct_count_2y": 3.0,
        "up_5pct_count_2y": 5.0,
        "upside_tail_volatility_2y": 0.03,
        "positive_after_big_up_1d_rate": 0.50,
        "positive_after_big_up_3d_rate": 0.45,
        "positive_after_big_up_5d_rate": 0.40,
        "stock_character_coverage": True,
        "log_current_float_market_cap": 20.0,
        "market_capacity_coverage": True,
        "catalyst_verifiability_score": 70.0,
        "average_amount_20d": 200_000_000.0,
        "average_turnover_rate_20d": 2.0,
        "amount_to_float_cap_20d": 0.02,
    }
    row.update(overrides)
    return row


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
    assert row["distance_hfq_ma120"] == pytest.approx(
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
        ("300001", True, 19.8),
        ("301001", True, 19.8),
        ("688001", True, 19.8),
        ("689001", True, 19.8),
        ("430001", True, 29.8),
        ("830001", True, 29.8),
        ("920422", True, 29.8),
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


@pytest.mark.parametrize("trade_date", ["2024-12-31", "2027-01-01"])
def test_limit_up_api_rejects_unsupported_analysis_trade_dates(trade_date):
    with pytest.raises(
        ValueError,
        match="trade_date must be between 2025-01-01 and 2026-12-31",
    ):
        is_limit_up_day("000001", False, 9.8, trade_date=trade_date)


@pytest.mark.parametrize("trade_date", ["2025-01-01", "2026-12-31"])
def test_limit_up_api_accepts_supported_analysis_trade_date_boundaries(trade_date):
    assert is_limit_up_day("000001", False, 9.8, trade_date=trade_date)


@pytest.mark.parametrize("trade_date", ["2024-12-31", "2027-01-01"])
def test_stock_character_rejects_unsupported_analysis_trade_dates(trade_date):
    with pytest.raises(
        ValueError,
        match="trade_date must be between 2025-01-01 and 2026-12-31",
    ):
        compute_stock_character_features(
            _character_bars("A", [0.0], end="2024-01-01"),
            trade_date=trade_date,
        )


@pytest.mark.parametrize("trade_date", ["2025-01-01", "2026-12-31"])
def test_stock_character_accepts_supported_analysis_trade_date_boundaries(trade_date):
    result = compute_stock_character_features(
        _character_bars("A", [0.0], end="2024-01-01"),
        trade_date=trade_date,
    )

    assert result["asset_id"].tolist() == ["A"]


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
    assert row["return_volatility_2y"] == pytest.approx(np.std(returns, ddof=1))
    assert row["upside_tail_volatility_2y"] == pytest.approx(
        np.std(positive_returns, ddof=1)
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


@pytest.mark.parametrize("pct_chg", [[0.0, -1.0], [5.0, -1.0]])
def test_upside_tail_volatility_requires_two_positive_return_samples(pct_chg):
    row = compute_stock_character_features(
        _character_bars("A", pct_chg), trade_date=TRADE_DATE
    ).iloc[0]

    assert pd.isna(row["upside_tail_volatility_2y"])


def test_return_volatility_requires_two_valid_return_samples():
    row = compute_stock_character_features(
        _character_bars("A", [5.0, None]), trade_date=TRADE_DATE
    ).iloc[0]

    assert pd.isna(row["return_volatility_2y"])
    assert pd.isna(row["upside_tail_volatility_2y"])


def test_return_volatilities_use_sample_standard_deviation():
    returns = np.array([0.05, 0.07])
    row = compute_stock_character_features(
        _character_bars("A", [5.0, 7.0]), trade_date=TRADE_DATE
    ).iloc[0]

    expected = np.std(returns, ddof=1)
    assert row["return_volatility_2y"] == pytest.approx(expected)
    assert row["upside_tail_volatility_2y"] == pytest.approx(expected)


def test_pct_change_coverage_requires_400_valid_sessions_but_not_big_up_events():
    insufficient = compute_stock_character_features(
        _character_bars("A", [0.0] * 399 + [None] * 105), trade_date=TRADE_DATE
    ).iloc[0]
    complete = compute_stock_character_features(
        _character_bars("A", [0.0] * 400 + [None] * 104), trade_date=TRADE_DATE
    ).iloc[0]

    assert not insufficient["stock_character_coverage"]
    assert complete["stock_character_coverage"]
    assert pd.isna(complete["upside_tail_volatility_2y"])
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


def test_rebound_elasticity_percentiles_directions_and_weights_are_exact():
    component_fields = {
        "residual": [
            "drawdown_from_high_1y",
            "drawdown_from_high_2y",
            "price_position_1y",
            "price_position_2y",
            "distance_hfq_ma120",
            "distance_hfq_ma250",
            "rebound_from_low_60d",
            "rebound_from_low_120d",
            "relative_return_6m",
            "valuation_percentile",
        ],
        "stock": [
            "limit_up_count_2y",
            "up_7pct_count_2y",
            "up_5pct_count_2y",
            "upside_tail_volatility_2y",
            "positive_after_big_up_1d_rate",
            "positive_after_big_up_3d_rate",
            "positive_after_big_up_5d_rate",
        ],
        "catalyst": [
            "catalyst_verifiability_score",
            "average_amount_20d",
            "average_turnover_rate_20d",
            "amount_to_float_cap_20d",
        ],
    }
    rows = []
    for asset_id, level in (("A", 1.0), ("B", 2.0), ("C", 3.0)):
        overrides = {"asset_id": asset_id, "log_current_float_market_cap": level}
        for fields in component_fields.values():
            overrides.update({field: level for field in fields})
        rows.append(_elasticity_row(**overrides))

    result = score_rebound_elasticity(pd.DataFrame(rows), CONFIG).set_index("asset_id")

    assert result.loc["A", "residual_deviation_score"] == 100.0
    assert result.loc["A", "stock_character_score"] == 0.0
    assert result.loc["A", "market_capacity_score"] == 95.0
    assert result.loc["A", "catalyst_liquidity_score"] == 0.0
    assert result.loc["A", "elasticity_score"] == pytest.approx(54.0)
    assert result.loc["A", "automatic_elasticity_score"] == pytest.approx(68.75)
    assert result.loc["B", "elasticity_score"] == 50.0
    assert result.loc["B", "automatic_elasticity_score"] == 50.0
    assert result.loc["C", "market_capacity_score"] == 5.0
    assert result.loc["C", "elasticity_score"] == pytest.approx(46.0)
    assert result.loc["C", "automatic_elasticity_score"] == pytest.approx(31.25)
    assert result["elasticity_coverage"].all()
    assert result["automatic_elasticity_coverage"].all()


def test_market_cap_percentiles_clip_endpoints_in_independent_cross_sections():
    rows = []
    for index, market_cap in enumerate([1.0, 2.0, 3.0, 4.0, 5.0]):
        rows.append(
            _elasticity_row(
                asset_id=chr(ord("A") + index),
                eligible=index < 3,
                log_current_float_market_cap=market_cap,
            )
        )

    result = score_rebound_elasticity(pd.DataFrame(rows), CONFIG).set_index("asset_id")

    assert result.loc[["A", "B", "C"], "market_capacity_score"].tolist() == [
        95.0,
        50.0,
        5.0,
    ]
    assert result.loc["A", "market_capacity_score"] < 100.0
    assert result.loc["C", "market_capacity_score"] > 0.0
    assert result.loc[["A", "B", "C"], "market_capacity_score"].is_monotonic_decreasing
    automatic_scores = result.loc[
        ["A", "B", "C", "D", "E"], "automatic_elasticity_score"
    ].tolist()
    assert automatic_scores == pytest.approx([61.25, 56.25, 50.0, 43.75, 38.75])


def test_stock_character_inputs_are_winsorized_before_percentiles():
    rows = []
    for index, count in enumerate([0.0] * 19 + [100.0, 1000.0]):
        rows.append(_elasticity_row(asset_id=f"A{index:02d}", limit_up_count_2y=count))

    result = score_rebound_elasticity(pd.DataFrame(rows), CONFIG).set_index("asset_id")

    assert result.loc["A19", "stock_character_score"] == pytest.approx(
        result.loc["A20", "stock_character_score"]
    )


def test_continuation_rate_extremes_are_not_winsorized_into_a_tie():
    rows = []
    rates = [0.0] * 19 + [0.9, 1.0]
    for index, rate in enumerate(rates):
        rows.append(
            _elasticity_row(
                asset_id=f"A{index:02d}",
                positive_after_big_up_1d_rate=rate,
                positive_after_big_up_3d_rate=rate,
                positive_after_big_up_5d_rate=rate,
            )
        )

    result = score_rebound_elasticity(pd.DataFrame(rows), CONFIG).set_index("asset_id")

    assert result.loc["A20", "stock_character_score"] > result.loc[
        "A19", "stock_character_score"
    ]


def test_no_big_up_events_can_use_zero_continuation_without_faking_tail_volatility():
    no_events = _elasticity_row(
        up_7pct_count_2y=0.0,
        positive_after_big_up_1d_rate=np.nan,
        positive_after_big_up_3d_rate=np.nan,
        positive_after_big_up_5d_rate=np.nan,
    )
    result = score_rebound_elasticity(pd.DataFrame([no_events]), CONFIG).iloc[0]

    assert result["stock_character_coverage"]
    assert result["stock_character_score"] == 50.0

    missing_tail = score_rebound_elasticity(
        pd.DataFrame([_elasticity_row(up_7pct_count_2y=0.0, upside_tail_volatility_2y=np.nan)]),
        CONFIG,
    ).iloc[0]
    assert not missing_tail["stock_character_component_coverage"]
    assert pd.isna(missing_tail["stock_character_score"])


def test_component_missingness_does_not_default_to_zero_or_disable_automatic_score():
    row = _elasticity_row(catalyst_verifiability_score=np.nan)
    result = score_rebound_elasticity(pd.DataFrame([row]), CONFIG).iloc[0]

    assert not result["catalyst_liquidity_coverage"]
    assert pd.isna(result["catalyst_liquidity_score"])
    assert not result["elasticity_coverage"]
    assert pd.isna(result["elasticity_score"])
    assert result["automatic_elasticity_coverage"]
    assert result["automatic_elasticity_score"] == 50.0


def test_final_elasticity_cross_section_ignores_rows_outside_final_universe():
    base_rows = pd.DataFrame(
        [_elasticity_row(asset_id="A"), _elasticity_row(asset_id="B")]
    )
    baseline = score_rebound_elasticity(base_rows, CONFIG).set_index("asset_id")
    contaminated = score_rebound_elasticity(
        pd.concat(
            [
                base_rows,
                pd.DataFrame(
                    [
                        _elasticity_row(
                            asset_id="X",
                            drawdown_from_high_1y=-100.0,
                            drawdown_from_high_2y=-100.0,
                            catalyst_verifiability_score=np.nan,
                        )
                    ]
                ),
            ],
            ignore_index=True,
        ),
        CONFIG,
    ).set_index("asset_id")

    pd.testing.assert_series_equal(
        contaminated.loc[["A", "B"], "elasticity_score"],
        baseline.loc[["A", "B"], "elasticity_score"],
    )
    assert pd.isna(contaminated.loc["X", "residual_deviation_score"])
    assert pd.isna(contaminated.loc["X", "elasticity_score"])


def test_automatic_elasticity_uses_an_independent_eligible_cross_section():
    base_rows = pd.DataFrame(
        [_elasticity_row(asset_id="A"), _elasticity_row(asset_id="B")]
    )
    baseline = score_rebound_elasticity(base_rows, CONFIG).set_index("asset_id")
    contaminated = score_rebound_elasticity(
        pd.concat(
            [
                base_rows,
                pd.DataFrame(
                    [
                        _elasticity_row(
                            asset_id="X",
                            eligible=False,
                            automatic_eligible=False,
                            drawdown_from_high_1y=-100.0,
                            drawdown_from_high_2y=-100.0,
                        )
                    ]
                ),
            ],
            ignore_index=True,
        ),
        CONFIG,
    ).set_index("asset_id")

    pd.testing.assert_series_equal(
        contaminated.loc[["A", "B"], "automatic_elasticity_score"],
        baseline.loc[["A", "B"], "automatic_elasticity_score"],
    )
    assert pd.isna(contaminated.loc["X", "automatic_elasticity_score"])


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("drawdown_from_high_1y", True),
        ("limit_up_count_2y", "2"),
        ("log_current_float_market_cap", Fraction(20, 1)),
        ("average_amount_20d", np.inf),
        ("residual_deviation_coverage", 1),
        ("stock_character_coverage", "true"),
        ("market_capacity_coverage", None),
        ("eligible", 1),
        ("automatic_eligible", "true"),
    ],
)
def test_rebound_elasticity_rejects_non_strict_values(field, invalid):
    with pytest.raises(ValueError, match=field):
        score_rebound_elasticity(
            pd.DataFrame([_elasticity_row(**{field: invalid})]), CONFIG
        )


def test_rebound_elasticity_validates_assets_columns_and_empty_schema():
    rows = pd.DataFrame([_elasticity_row()])
    with pytest.raises(ValueError, match="distance_hfq_ma250"):
        score_rebound_elasticity(rows.drop(columns="distance_hfq_ma250"), CONFIG)
    with pytest.raises(ValueError, match="automatic_eligible"):
        score_rebound_elasticity(rows.drop(columns="automatic_eligible"), CONFIG)
    with pytest.raises(ValueError, match="duplicate asset_id"):
        score_rebound_elasticity(pd.concat([rows, rows], ignore_index=True), CONFIG)
    with pytest.raises(ValueError, match="asset_id"):
        score_rebound_elasticity(pd.DataFrame([_elasticity_row(asset_id=" ")]), CONFIG)

    empty = score_rebound_elasticity(pd.DataFrame(columns=rows.columns), CONFIG)
    assert empty.empty
    assert "elasticity_score" in empty.columns
    assert "automatic_elasticity_score" in empty.columns


def test_market_capacity_prefers_free_float_then_float_then_total_share():
    bars = pd.concat(
        [_capacity_bars(asset_id) for asset_id in ("A", "B", "C")],
        ignore_index=True,
    )
    shares = pd.DataFrame(
        [
            _capacity_shares("A"),
            _capacity_shares("B", free_float_share=np.nan),
            _capacity_shares("C", float_share=np.nan, free_float_share=np.nan),
        ]
    )

    result = compute_market_capacity_features(
        bars, shares, trade_date=TRADE_DATE
    ).set_index("asset_id")

    assert result.loc["A", "current_float_market_cap"] == pytest.approx(600.0)
    assert result.loc["A", "market_cap_source"] == "free_float_share"
    assert result.loc["B", "current_float_market_cap"] == pytest.approx(800.0)
    assert result.loc["B", "market_cap_source"] == "float_share"
    assert result.loc["C", "current_float_market_cap"] == pytest.approx(1000.0)
    assert result.loc["C", "market_cap_source"] == "total_share_fallback"
    assert result["market_capacity_coverage"].all()


def test_current_total_market_cap_is_independent_of_float_share_selection():
    row = compute_market_capacity_features(
        _capacity_bars("A"),
        pd.DataFrame([_capacity_shares("A")]),
        trade_date=TRADE_DATE,
    ).iloc[0]

    assert row["current_total_market_cap"] == pytest.approx(1000.0)
    assert row["current_float_market_cap"] == pytest.approx(600.0)


def test_scenario_market_cap_is_neither_an_input_nor_an_output():
    bars = _capacity_bars("A")
    bars["base_scenario_market_cap"] = 999_999.0
    shares = pd.DataFrame([_capacity_shares("A")])
    shares["scenario_market_cap"] = 888_888.0

    result = compute_market_capacity_features(bars, shares, trade_date=TRADE_DATE)

    assert result.iloc[0]["current_total_market_cap"] == pytest.approx(1000.0)
    assert "base_scenario_market_cap" not in result.columns
    assert "scenario_market_cap" not in result.columns


def test_market_capacity_actual_numeric_case_is_exact():
    bars = _capacity_bars(
        "A", raw_close=12.5, amount=200_000_000.0, turnover_rate=2.5
    )
    shares = pd.DataFrame(
        [
            _capacity_shares(
                "A",
                total_share=100_000_000.0,
                float_share=80_000_000.0,
                free_float_share=60_000_000.0,
            )
        ]
    )

    row = compute_market_capacity_features(bars, shares, trade_date=TRADE_DATE).iloc[0]

    assert row["latest_trade_date"] == pd.Timestamp(TRADE_DATE)
    assert row["history_sessions"] == 20
    assert row["current_total_market_cap"] == pytest.approx(1_250_000_000.0)
    assert row["current_float_market_cap"] == pytest.approx(750_000_000.0)
    assert row["log_current_float_market_cap"] == pytest.approx(np.log(750_000_000.0))
    assert row["average_amount_20d"] == pytest.approx(200_000_000.0)
    assert row["average_turnover_rate_20d"] == pytest.approx(2.5)
    assert row["amount_to_float_cap_20d"] == pytest.approx(200 / 750)
    assert row["market_capacity_coverage"]


def test_market_capacity_requires_exactly_20_amount_sessions_but_not_turnover():
    bars = pd.concat(
        [
            _capacity_bars("A19", sessions=19),
            _capacity_bars("A20", sessions=20, turnover_rate=None),
        ],
        ignore_index=True,
    )
    shares = pd.DataFrame([_capacity_shares("A19"), _capacity_shares("A20")])

    result = compute_market_capacity_features(
        bars, shares, trade_date=TRADE_DATE
    ).set_index("asset_id")

    assert pd.isna(result.loc["A19", "average_amount_20d"])
    assert not result.loc["A19", "market_capacity_coverage"]
    assert result.loc["A20", "average_amount_20d"] == pytest.approx(200.0)
    assert pd.isna(result.loc["A20", "average_turnover_rate_20d"])
    assert result.loc["A20", "market_capacity_coverage"]


def test_future_market_bars_are_ignored_and_future_only_assets_are_absent():
    history = _capacity_bars("A")
    valid_shares = pd.DataFrame([_capacity_shares("A")])
    expected = compute_market_capacity_features(
        history, valid_shares, trade_date=TRADE_DATE
    )
    shares = pd.DataFrame(
        [
            _capacity_shares("A"),
            _capacity_shares("FUTURE", free_float_share="bad"),
            _capacity_shares("FUTURE", total_share=-1.0),
        ]
    )
    future = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "trade_date": "2026-07-30",
                "raw_close": "bad",
                "amount": -1.0,
                "turnover_rate": Fraction(1, 2),
            },
            {
                "asset_id": "FUTURE",
                "trade_date": "2026-07-30",
                "raw_close": 10.0,
                "amount": 100.0,
                "turnover_rate": 1.0,
            },
        ]
    )

    actual = compute_market_capacity_features(
        pd.concat([future, history], ignore_index=True),
        shares,
        trade_date=TRADE_DATE,
    )

    pd.testing.assert_frame_equal(actual, expected)
    assert actual["asset_id"].tolist() == ["A"]


def test_missing_latest_raw_share_or_window_amount_disables_coverage():
    raw_missing = _capacity_bars("RAW")
    raw_missing.loc[raw_missing.index[-1], "raw_close"] = np.nan
    amount_missing = _capacity_bars("AMOUNT")
    amount_missing.loc[amount_missing.index[-1], "amount"] = np.nan
    bars = pd.concat(
        [raw_missing, amount_missing, _capacity_bars("SHARE")], ignore_index=True
    )
    shares = pd.DataFrame(
        [_capacity_shares("RAW"), _capacity_shares("AMOUNT")]
    )

    result = compute_market_capacity_features(
        bars, shares, trade_date=TRADE_DATE
    ).set_index("asset_id")

    assert pd.isna(result.loc["RAW", "current_total_market_cap"])
    assert not result.loc["RAW", "market_capacity_coverage"]
    assert pd.isna(result.loc["AMOUNT", "average_amount_20d"])
    assert pd.isna(result.loc["AMOUNT", "amount_to_float_cap_20d"])
    assert not result.loc["AMOUNT", "market_capacity_coverage"]
    assert pd.isna(result.loc["SHARE", "current_float_market_cap"])
    assert pd.isna(result.loc["SHARE", "market_cap_source"])
    assert not result.loc["SHARE", "market_capacity_coverage"]


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("raw_close", -1.0),
        ("raw_close", np.inf),
        ("raw_close", "10"),
        ("raw_close", Fraction(10, 1)),
        ("raw_close", Decimal("1e10000")),
        ("raw_close", Decimal("1e-10000")),
        ("amount", -1.0),
        ("amount", np.inf),
        ("amount", Fraction(1, 2)),
        ("turnover_rate", -1.0),
        ("turnover_rate", Decimal("1e10000")),
    ],
)
def test_market_bar_numbers_reject_invalid_values_with_context(field, invalid):
    bars = _capacity_bars("A")
    bars[field] = bars[field].astype(object)
    bars.loc[bars.index[-1], field] = invalid

    with pytest.raises(ValueError, match=rf"{field}.*A.*2026-07-29"):
        compute_market_capacity_features(
            bars, pd.DataFrame([_capacity_shares("A")]), trade_date=TRADE_DATE
        )


@pytest.mark.parametrize("field", ["total_share", "float_share", "free_float_share"])
@pytest.mark.parametrize(
    "invalid",
    [0.0, -1.0, np.inf, "100", Fraction(100, 1), Decimal("1e10000"), Decimal("1e-10000")],
)
def test_share_numbers_reject_invalid_nonmissing_values_with_context(field, invalid):
    shares = pd.DataFrame([_capacity_shares("A")])
    shares[field] = shares[field].astype(object)
    shares.loc[0, field] = invalid

    with pytest.raises(ValueError, match=rf"{field}.*A"):
        compute_market_capacity_features(
            _capacity_bars("A"), shares, trade_date=TRADE_DATE
        )


def test_market_capacity_accepts_supported_numpy_and_decimal_numbers():
    bars = _capacity_bars(
        "A",
        raw_close=Decimal("10"),
        amount=np.int64(200),
        turnover_rate=np.float64(2.0),
    )
    shares = pd.DataFrame(
        [
            _capacity_shares(
                "A",
                total_share=np.int64(100),
                float_share=Decimal("80"),
                free_float_share=np.float64(60.0),
            )
        ]
    )

    row = compute_market_capacity_features(bars, shares, trade_date=TRADE_DATE).iloc[0]

    assert row["current_total_market_cap"] == pytest.approx(1000.0)
    assert row["market_capacity_coverage"]


def test_market_capacity_sorts_input_and_rejects_duplicate_bars_and_shares():
    bars = pd.concat([_capacity_bars("B"), _capacity_bars("A")], ignore_index=True)
    shares = pd.DataFrame([_capacity_shares("B"), _capacity_shares("A")])

    result = compute_market_capacity_features(
        bars.sample(frac=1.0, random_state=11),
        shares.sample(frac=1.0, random_state=12),
        trade_date=TRADE_DATE,
    )

    assert result["asset_id"].tolist() == ["A", "B"]
    duplicate_bar = pd.concat([bars, bars.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match=r"duplicate.*B"):
        compute_market_capacity_features(
            duplicate_bar, shares, trade_date=TRADE_DATE
        )
    duplicate_shares = pd.concat([shares, shares.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match=r"duplicate.*B"):
        compute_market_capacity_features(
            bars, duplicate_shares, trade_date=TRADE_DATE
        )


@pytest.mark.parametrize("frame_name", ["bars", "shares"])
@pytest.mark.parametrize("invalid", ["", "   ", None, 123, True])
def test_market_capacity_asset_ids_must_be_nonempty_strings(frame_name, invalid):
    bars = _capacity_bars("A")
    shares = pd.DataFrame([_capacity_shares("A")])
    frame = bars if frame_name == "bars" else shares
    frame["asset_id"] = frame["asset_id"].astype(object)
    frame.loc[frame.index[0], "asset_id"] = invalid

    with pytest.raises(ValueError, match="asset_id"):
        compute_market_capacity_features(bars, shares, trade_date=TRADE_DATE)


@pytest.mark.parametrize(
    ("frame_name", "missing"),
    [
        ("bars", "asset_id"),
        ("bars", "trade_date"),
        ("bars", "raw_close"),
        ("bars", "amount"),
        ("bars", "turnover_rate"),
        ("shares", "asset_id"),
        ("shares", "total_share"),
        ("shares", "float_share"),
        ("shares", "free_float_share"),
    ],
)
def test_market_capacity_required_columns_are_enforced(frame_name, missing):
    bars = _capacity_bars("A")
    shares = pd.DataFrame([_capacity_shares("A")])
    if frame_name == "bars":
        bars = bars.drop(columns=missing)
    else:
        shares = shares.drop(columns=missing)

    with pytest.raises(ValueError, match=missing):
        compute_market_capacity_features(bars, shares, trade_date=TRADE_DATE)


def test_empty_market_capacity_input_returns_stable_schema():
    bars = pd.DataFrame(
        columns=["asset_id", "trade_date", "raw_close", "amount", "turnover_rate"]
    )
    shares = pd.DataFrame(
        columns=["asset_id", "total_share", "float_share", "free_float_share"]
    )

    result = compute_market_capacity_features(bars, shares, trade_date=TRADE_DATE)

    assert result.empty
    assert result.columns.tolist() == MARKET_CAPACITY_COLUMNS
