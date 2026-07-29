from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stock_research.consumer_oversold.features import (
    compute_already_priced_features,
    compute_oversold_score,
    compute_price_features,
)


TRADE_DATE = "2026-07-29"
EXPECTED_COLUMNS = [
    "asset_id",
    "latest_trade_date",
    "latest_close",
    "history_bars",
    "price_history_complete",
    "return_6m",
    "return_60d",
    "max_drawdown_12m",
    "rebound_from_low_60d",
    "ma120",
    "ma250",
    "distance_ma120",
    "distance_ma250",
    "consumer_subindustry",
    "industry_peer_count",
    "industry_return_6m",
    "relative_return_6m",
    "industry_return_60d",
    "relative_return_60d",
    "relative_return_coverage",
]


def _bars(asset_id: str, closes: list[float], *, start: str = "2025-01-01") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"asset_id": asset_id, "trade_date": dates, "close": closes})


def test_price_features_use_exact_windows_sort_input_and_ignore_future_bars():
    closes = [float(value) for value in range(1, 253)]
    bars = _bars("b", [10.0] * 251 + [6.0])
    bars = pd.concat(
        [
            bars,
            _bars("a", closes),
            pd.DataFrame([{"asset_id": "a", "trade_date": "2026-08-03", "close": 9999.0}]),
        ],
        ignore_index=True,
    ).sample(frac=1, random_state=7)
    membership = pd.DataFrame(
        [("b", "retail"), ("a", "solo")],
        columns=["asset_id", "consumer_subindustry"],
    )

    result = compute_price_features(bars, membership, trade_date=TRADE_DATE)
    row = result.set_index("asset_id").loc["a"]

    assert list(result.columns) == EXPECTED_COLUMNS
    assert result["asset_id"].tolist() == ["a", "b"]
    assert row["latest_trade_date"] == pd.Timestamp("2025-12-18")
    assert row["latest_close"] == 252.0
    assert row["history_bars"] == 252
    assert row["price_history_complete"]
    assert row["return_6m"] == pytest.approx(252 / 127 - 1)
    assert row["return_60d"] == pytest.approx(252 / 193 - 1)
    assert row["max_drawdown_12m"] == 0.0
    assert row["rebound_from_low_60d"] == pytest.approx(252 / 193 - 1)
    assert row["ma120"] == pytest.approx(np.mean(range(133, 253)))
    assert row["ma250"] == pytest.approx(np.mean(range(3, 253)))
    assert row["distance_ma120"] == pytest.approx(252 / np.mean(range(133, 253)) - 1)
    assert row["distance_ma250"] == pytest.approx(252 / np.mean(range(3, 253)) - 1)
    assert result.set_index("asset_id").loc["b", "max_drawdown_12m"] == pytest.approx(-0.4)


def test_industry_relative_returns_require_three_non_null_peers():
    bars = pd.concat(
        [
            _bars("a", [100.0] * 125 + [80.0]),
            _bars("b", [100.0] * 125 + [90.0]),
            _bars("c", [100.0] * 125 + [110.0]),
            _bars("d", [100.0] * 125 + [120.0]),
            _bars("x", [100.0] * 125 + [70.0]),
            _bars("y", [100.0] * 125 + [60.0]),
        ],
        ignore_index=True,
    )
    membership = pd.DataFrame(
        [("a", "large"), ("b", "large"), ("c", "large"), ("d", "large"), ("x", "small"), ("y", "small")],
        columns=["asset_id", "consumer_subindustry"],
    )

    result = compute_price_features(bars, membership, trade_date=TRADE_DATE).set_index("asset_id")

    assert result.loc["a", "industry_peer_count"] == 4
    assert result.loc["a", "industry_return_6m"] == pytest.approx(0.0)
    assert result.loc["a", "relative_return_6m"] == pytest.approx(-0.2)
    assert result.loc["a", "relative_return_coverage"]
    assert result.loc["x", "industry_peer_count"] == 2
    assert pd.isna(result.loc["x", "industry_return_6m"])
    assert pd.isna(result.loc["x", "relative_return_6m"])
    assert pd.isna(result.loc["x", "industry_return_60d"])
    assert pd.isna(result.loc["x", "relative_return_60d"])
    assert not result.loc["x", "relative_return_coverage"]


def test_industry_relative_returns_have_coverage_at_exactly_three_valid_peers():
    bars = pd.concat(
        [
            _bars("a", [100.0] * 125 + [70.0]),
            _bars("b", [100.0] * 125 + [90.0]),
            _bars("c", [100.0] * 125 + [110.0]),
        ],
        ignore_index=True,
    )
    membership = pd.DataFrame(
        [("a", "exactly_three"), ("b", "exactly_three"), ("c", "exactly_three")],
        columns=["asset_id", "consumer_subindustry"],
    )

    result = compute_price_features(bars, membership, trade_date=TRADE_DATE).set_index("asset_id")

    assert result.loc["a", "industry_peer_count"] == 3
    assert result.loc["a", "relative_return_coverage"]
    assert result.loc["a", "industry_return_6m"] == pytest.approx(-0.1)
    assert result.loc["a", "relative_return_6m"] == pytest.approx(-0.2)
    assert result.loc["a", "industry_return_60d"] == pytest.approx(-0.1)
    assert result.loc["a", "relative_return_60d"] == pytest.approx(-0.2)


def test_incomplete_history_is_retained_without_fabricating_long_windows():
    bars = pd.concat([_bars("short", list(range(1, 121))), _bars("tiny", [5.0] * 10)])
    membership = pd.DataFrame(
        [("short", "one"), ("tiny", "one"), ("missing", "one")],
        columns=["asset_id", "consumer_subindustry"],
    )

    result = compute_price_features(bars, membership, trade_date=TRADE_DATE).set_index("asset_id")

    assert not result.loc["short", "price_history_complete"]
    assert pd.isna(result.loc["short", "return_6m"])
    assert result.loc["short", "return_60d"] == pytest.approx(120 / 61 - 1)
    assert result.loc["short", "ma120"] == pytest.approx(60.5)
    assert pd.isna(result.loc["short", "max_drawdown_12m"])
    assert pd.isna(result.loc["short", "ma250"])
    assert result.loc["missing", "history_bars"] == 0
    assert pd.isna(result.loc["missing", "latest_close"])


@pytest.mark.parametrize(
    ("frame_name", "frame", "missing"),
    [
        ("bars", pd.DataFrame({"asset_id": ["a"], "trade_date": [TRADE_DATE]}), "close"),
        ("membership", pd.DataFrame({"asset_id": ["a"]}), "consumer_subindustry"),
    ],
)
def test_price_features_reject_missing_columns(frame_name, frame, missing):
    bars = _bars("a", [1.0])
    membership = pd.DataFrame({"asset_id": ["a"], "consumer_subindustry": ["x"]})
    arguments = {"bars": bars, "membership": membership, frame_name: frame}

    with pytest.raises(ValueError, match=missing):
        compute_price_features(**arguments, trade_date=TRADE_DATE)


def test_price_features_reject_duplicate_dates_and_invalid_close_with_context():
    membership = pd.DataFrame({"asset_id": ["a"], "consumer_subindustry": ["x"]})
    duplicate = pd.DataFrame(
        {"asset_id": ["a", "a"], "trade_date": ["2026-01-02", "2026-01-02"], "close": [1.0, 2.0]}
    )
    with pytest.raises(ValueError, match=r"a.*2026-01-02"):
        compute_price_features(duplicate, membership, trade_date=TRADE_DATE)

    invalid = pd.DataFrame({"asset_id": ["a"], "trade_date": ["2026-01-02"], "close": [np.inf]})
    with pytest.raises(ValueError, match=r"a.*2026-01-02"):
        compute_price_features(invalid, membership, trade_date=TRADE_DATE)


def test_oversold_score_percentile_direction_exact_weights_and_name():
    frame = pd.DataFrame(
        {
            "max_drawdown_12m": [-0.50, -0.30, -0.10],
            "return_6m": [-0.40, -0.20, 0.0],
            "relative_return_6m": [-0.30, -0.10, 0.10],
            "valuation_depression_percentile": [1.0, 0.5, 0.0],
            "distance_ma120": [-0.20, -0.10, 0.0],
            "distance_ma250": [-0.40, -0.20, 0.0],
        }
    )

    scores = compute_oversold_score(frame)

    assert scores.name == "oversold_score"
    assert scores.tolist() == pytest.approx([100.0, 190.0 / 3.0, 80.0 / 3.0])


def test_oversold_score_propagates_missing_components_and_validates_valuation():
    frame = pd.DataFrame(
        {
            "max_drawdown_12m": [-0.5, -0.2],
            "return_6m": [-0.4, -0.1],
            "relative_return_6m": [-0.3, np.nan],
            "valuation_depression_percentile": [0.8, 0.2],
            "distance_ma120": [-0.2, -0.1],
            "distance_ma250": [-0.3, -0.2],
        }
    )
    assert pd.isna(compute_oversold_score(frame).iloc[1])

    frame.loc[0, "valuation_depression_percentile"] = 1.01
    with pytest.raises(ValueError, match="valuation_depression_percentile"):
        compute_oversold_score(frame)


@pytest.mark.parametrize("invalid", ["bad", np.inf, -0.1, 1.1])
def test_oversold_score_rejects_non_numeric_non_finite_or_out_of_range_valuation(invalid):
    frame = pd.DataFrame(
        {
            "max_drawdown_12m": [-0.5],
            "return_6m": [-0.4],
            "relative_return_6m": [-0.3],
            "valuation_depression_percentile": [invalid],
            "distance_ma120": [-0.2],
            "distance_ma250": [-0.3],
        }
    )

    with pytest.raises(ValueError, match="valuation_depression_percentile"):
        compute_oversold_score(frame)


@pytest.mark.parametrize("missing", [None, np.nan, pd.NA])
def test_oversold_score_allows_missing_valuation_to_propagate(missing):
    frame = pd.DataFrame(
        {
            "max_drawdown_12m": [-0.5],
            "return_6m": [-0.4],
            "relative_return_6m": [-0.3],
            "valuation_depression_percentile": [missing],
            "distance_ma120": [-0.2],
            "distance_ma250": [-0.3],
        }
    )

    assert pd.isna(compute_oversold_score(frame).iloc[0])


def test_already_priced_penalty_individual_triggers_total_cap_and_missing_coverage():
    result = compute_already_priced_features(
        {"rebound_from_low_60d": 0.25, "relative_return_60d": 0.10},
        {"valuation_percentile": 0.50},
        evidence_revision_state="broadly_priced",
    )
    assert result == {
        "priced_in_penalty": 20.0,
        "priced_in_rebound_trigger": True,
        "priced_in_relative_return_trigger": True,
        "priced_in_valuation_trigger": True,
        "priced_in_evidence_revision_trigger": True,
        "priced_in_rebound_coverage": True,
        "priced_in_relative_return_coverage": True,
        "priced_in_valuation_coverage": True,
    }

    missing = compute_already_priced_features({}, {})
    assert missing["priced_in_penalty"] == 0.0
    assert not missing["priced_in_rebound_trigger"]
    assert not missing["priced_in_relative_return_trigger"]
    assert not missing["priced_in_valuation_trigger"]
    assert not missing["priced_in_rebound_coverage"]
    assert not missing["priced_in_relative_return_coverage"]
    assert not missing["priced_in_valuation_coverage"]

    for invalid in (-0.01, 1.01, np.inf):
        with pytest.raises(ValueError, match="valuation_percentile"):
            compute_already_priced_features({}, {"valuation_percentile": invalid})


@pytest.mark.parametrize(
    ("price_row", "valuation_row", "revision", "penalty", "trigger"),
    [
        ({"rebound_from_low_60d": 0.25}, {}, "", 6.0, "priced_in_rebound_trigger"),
        ({"relative_return_60d": 0.10}, {}, "", 4.0, "priced_in_relative_return_trigger"),
        ({}, {"valuation_percentile": 0.50}, "", 5.0, "priced_in_valuation_trigger"),
        ({}, {}, "broadly_priced", 5.0, "priced_in_evidence_revision_trigger"),
    ],
)
def test_already_priced_penalty_components_trigger_individually(
    price_row, valuation_row, revision, penalty, trigger
):
    result = compute_already_priced_features(
        price_row, valuation_row, evidence_revision_state=revision
    )

    assert result["priced_in_penalty"] == penalty
    assert result[trigger]
