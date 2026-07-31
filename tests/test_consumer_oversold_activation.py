from __future__ import annotations

import importlib

import numpy as np
import pandas as pd
import pytest


TRADE_DATE = "2026-01-30"
RAW_COLUMNS = [
    "asset_id",
    "latest_trade_date",
    "return_5d",
    "return_10d",
    "return_20d",
    "relative_return_5d",
    "relative_return_10d",
    "relative_strength_improvement_5d",
    "ma5_slope_5d",
    "ma10_slope_5d",
    "distance_ma5",
    "distance_ma10",
    "distance_ma20",
    "position_20d",
    "amount_ratio_5d_20d",
    "turnover_change_5d_20d",
    "volatility_ratio_5d_20d",
    "new_low_20d_within_3d",
    "technical_feature_coverage",
]
SCORE_COLUMNS = [
    "trend_turn_score",
    "relative_strength_improvement_score",
    "volume_turnover_confirmation_score",
    "moving_average_location_score",
    "volatility_transition_score",
    "technical_readiness_score",
    "falling_knife",
]
EXPECTED_COLUMNS = RAW_COLUMNS + SCORE_COLUMNS


def _activation():
    return importlib.import_module("stock_research.consumer_oversold.activation")


def _bars(
    asset_id: str,
    closes: list[float],
    *,
    amounts: list[float] | None = None,
    turnovers: list[float] | None = None,
    start: str = "2026-01-01",
) -> pd.DataFrame:
    size = len(closes)
    return pd.DataFrame(
        {
            "asset_id": asset_id,
            "trade_date": pd.bdate_range(start, periods=size),
            "close": closes,
            "amount": amounts if amounts is not None else [100.0] * size,
            "turnover_rate": turnovers if turnovers is not None else [1.0] * size,
        }
    )


def _membership(*pairs: tuple[str, str]) -> pd.DataFrame:
    return pd.DataFrame(pairs, columns=["asset_id", "consumer_subindustry"])


def _complete_bars(asset_ids: tuple[str, ...] = ("a", "b", "c")) -> pd.DataFrame:
    return pd.concat(
        [
            _bars(
                asset_id,
                [float(value + offset) for value in range(1, 23)],
                amounts=[float(value + offset) for value in range(1, 23)],
                turnovers=[float(value + offset + 1) for value in range(1, 23)],
            )
            for offset, asset_id in enumerate(asset_ids)
        ],
        ignore_index=True,
    )


def _score_row(asset_id: str, level: float, *, volatility_ratio: float = 1.0) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "technical_feature_coverage": True,
        "return_5d": level,
        "ma5_slope_5d": level,
        "ma10_slope_5d": level,
        "relative_return_5d": level,
        "relative_strength_improvement_5d": level,
        "amount_ratio_5d_20d": level + 2.0,
        "turnover_change_5d_20d": level,
        "distance_ma5": level,
        "distance_ma10": level,
        "distance_ma20": level,
        "position_20d": level + 1.0,
        "volatility_ratio_5d_20d": volatility_ratio,
        "new_low_20d_within_3d": False,
    }


def _config():
    contracts = importlib.import_module("stock_research.consumer_oversold.contracts")
    return contracts.ConsumerOversoldConfig(trade_date=TRADE_DATE, ranking_version="v2")


ACTIVATION_CONTINUATION_FIELDS = (
    "limit_up_count_2y",
    "up_7pct_count_2y",
    "up_5pct_count_2y",
    "upside_tail_volatility_2y",
    "positive_after_big_up_1d_rate",
    "positive_after_big_up_3d_rate",
    "positive_after_big_up_5d_rate",
    "median_return_after_big_up_3d",
    "median_return_after_big_up_5d",
    "max_limit_up_streak_2y",
    "strong_move_retention_5d_rate",
)
ACTIVATION_RESIDUAL_FIELDS = (
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
)
ACTIVATION_CAPITAL_FIELDS = (
    "log_current_float_market_cap",
    "average_amount_20d",
    "average_turnover_rate_20d",
    "amount_to_float_cap_20d",
)
ACTIVATION_ADDED_FIELDS = (
    "continuation_character_score",
    "residual_price_space_score",
    "capital_efficiency_score",
    "catalyst_timing_score",
    "activation_coverage",
    "activation_score",
    "overextended",
    "activation_eligible",
    "activation_exclusion_reasons",
)


def _activation_row(asset_id: str, **overrides) -> dict[str, object]:
    row = {
        "asset_id": asset_id,
        "eligible": True,
        "stock_code": f"{len(asset_id):06d}",
        "stock_name": f"name-{asset_id}",
        "technical_feature_coverage": True,
        "return_5d": 0.01,
        "ma5_slope_5d": 0.01,
        "ma10_slope_5d": 0.01,
        "relative_return_5d": 0.01,
        "relative_strength_improvement_5d": 0.01,
        "amount_ratio_5d_20d": 1.10,
        "turnover_change_5d_20d": 0.10,
        "distance_ma5": 0.01,
        "distance_ma10": 0.01,
        "distance_ma20": 0.01,
        "position_20d": 0.50,
        "volatility_ratio_5d_20d": 1.0,
        "new_low_20d_within_3d": False,
        "trend_turn_score": 50.0,
        "relative_strength_improvement_score": 50.0,
        "volume_turnover_confirmation_score": 50.0,
        "moving_average_location_score": 50.0,
        "volatility_transition_score": 50.0,
        "technical_readiness_score": 60.0,
        "falling_knife": False,
        "return_10d": 0.05,
        "residual_deviation_coverage": True,
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
        "stock_character_coverage": True,
        "limit_up_count_2y": 2.0,
        "up_7pct_count_2y": 3.0,
        "up_5pct_count_2y": 5.0,
        "upside_tail_volatility_2y": 0.03,
        "positive_after_big_up_1d_rate": 0.50,
        "positive_after_big_up_3d_rate": 0.45,
        "positive_after_big_up_5d_rate": 0.40,
        "median_return_after_big_up_3d": 0.08,
        "median_return_after_big_up_5d": 0.12,
        "max_limit_up_streak_2y": 2.0,
        "strong_move_retention_5d_rate": 0.40,
        "log_current_float_market_cap": 20.0,
        "average_amount_20d": 200_000_000.0,
        "average_turnover_rate_20d": 2.0,
        "amount_to_float_cap_20d": 0.02,
        "market_capacity_coverage": True,
        "catalyst_verifiability_score": 70.0,
        "expected_validation_date": "",
    }
    row.update(overrides)
    return row


def test_features_use_daily_point_in_time_windows_and_preserve_inputs():
    activation = _activation()
    bars = _complete_bars()
    future = pd.DataFrame(
        [
            {
                "asset_id": "a",
                "trade_date": "2026-02-02",
                "close": 9999.0,
                "amount": 9999.0,
                "turnover_rate": 9999.0,
            }
        ]
    )
    bars = pd.concat([bars, future], ignore_index=True).sample(frac=1.0, random_state=17)
    membership = _membership(("c", "retail"), ("a", "retail"), ("b", "retail"))
    bars_before = bars.copy(deep=True)
    membership_before = membership.copy(deep=True)

    result = activation.compute_technical_readiness_features(
        bars, membership, trade_date=TRADE_DATE
    )
    row = result.set_index("asset_id").loc["a"]

    assert result.columns.tolist() == EXPECTED_COLUMNS
    assert result["asset_id"].tolist() == ["a", "b", "c"]
    assert row["latest_trade_date"] == pd.Timestamp("2026-01-30")
    assert row["return_5d"] == pytest.approx(22.0 / 17.0 - 1.0)
    assert row["return_10d"] == pytest.approx(22.0 / 12.0 - 1.0)
    assert row["return_20d"] == pytest.approx(22.0 / 2.0 - 1.0)

    current_5d = np.array([22 / 17 - 1, 23 / 18 - 1, 24 / 19 - 1])
    current_10d = np.array([22 / 12 - 1, 23 / 13 - 1, 24 / 14 - 1])
    prior_5d = np.array([17 / 12 - 1, 18 / 13 - 1, 19 / 14 - 1])
    expected_relative_5d = current_5d[0] - current_5d.mean()
    expected_prior_relative_5d = prior_5d[0] - prior_5d.mean()
    assert row["relative_return_5d"] == pytest.approx(expected_relative_5d)
    assert row["relative_return_10d"] == pytest.approx(
        current_10d[0] - current_10d.mean()
    )
    assert row["relative_strength_improvement_5d"] == pytest.approx(
        expected_relative_5d - expected_prior_relative_5d
    )

    assert row["ma5_slope_5d"] == pytest.approx(20.0 / 15.0 - 1.0)
    assert row["ma10_slope_5d"] == pytest.approx(17.5 / 12.5 - 1.0)
    assert row["distance_ma5"] == pytest.approx(22.0 / 20.0 - 1.0)
    assert row["distance_ma10"] == pytest.approx(22.0 / 17.5 - 1.0)
    assert row["distance_ma20"] == pytest.approx(22.0 / 12.5 - 1.0)
    assert row["position_20d"] == 1.0
    assert row["amount_ratio_5d_20d"] == pytest.approx(20.0 / 12.5)
    assert row["turnover_change_5d_20d"] == pytest.approx(21.0 / 13.5 - 1.0)
    daily_returns = pd.Series(np.arange(1.0, 23.0)).pct_change().dropna()
    assert row["volatility_ratio_5d_20d"] == pytest.approx(
        daily_returns.tail(5).std(ddof=1) / daily_returns.tail(20).std(ddof=1)
    )
    assert not row["new_low_20d_within_3d"]
    assert row["technical_feature_coverage"]
    assert 0.0 <= row["technical_readiness_score"] <= 100.0
    pd.testing.assert_frame_equal(bars, bars_before)
    pd.testing.assert_frame_equal(membership, membership_before)


def test_future_rows_are_isolated_before_asset_and_numeric_validation():
    activation = _activation()
    bars = _complete_bars()
    membership = _membership(("a", "retail"), ("b", "retail"), ("c", "retail"))
    baseline = activation.compute_technical_readiness_features(
        bars, membership, trade_date=TRADE_DATE
    )
    malformed_future = pd.DataFrame(
        [
            {
                "asset_id": None,
                "trade_date": "2026-02-02",
                "close": "bad",
                "amount": -1.0,
                "turnover_rate": np.inf,
            }
        ]
    )

    actual = activation.compute_technical_readiness_features(
        pd.concat([bars, malformed_future], ignore_index=True),
        membership,
        trade_date=TRADE_DATE,
    )

    pd.testing.assert_frame_equal(actual, baseline)


def test_features_are_independent_of_duplicate_input_index_labels():
    activation = _activation()
    bars = _complete_bars()
    membership = _membership(("a", "retail"), ("b", "retail"), ("c", "retail"))
    duplicate_index_bars = pd.concat(
        [
            bars.loc[bars["asset_id"].eq(asset_id)].reset_index(drop=True)
            for asset_id in ("a", "b", "c")
        ],
        ignore_index=False,
    )
    duplicate_index_membership = pd.concat(
        [membership.iloc[[0]], membership.iloc[[1]], membership.iloc[[2]]],
        ignore_index=False,
    )

    expected = activation.compute_technical_readiness_features(
        bars.reset_index(drop=True),
        membership.reset_index(drop=True),
        trade_date=TRADE_DATE,
    )
    actual = activation.compute_technical_readiness_features(
        duplicate_index_bars,
        duplicate_index_membership,
        trade_date=TRADE_DATE,
    )

    pd.testing.assert_frame_equal(actual, expected)


@pytest.mark.parametrize(
    ("frame_name", "frame", "missing"),
    [
        (
            "bars",
            pd.DataFrame(
                {
                    "asset_id": ["a"],
                    "trade_date": [TRADE_DATE],
                    "close": [1.0],
                    "amount": [1.0],
                }
            ),
            "turnover_rate",
        ),
        ("membership", pd.DataFrame({"asset_id": ["a"]}), "consumer_subindustry"),
    ],
)
def test_features_require_input_columns(frame_name, frame, missing):
    activation = _activation()
    bars = _bars("a", [1.0])
    membership = _membership(("a", "retail"))
    arguments = {"bars": bars, "membership": membership, frame_name: frame}

    with pytest.raises(ValueError, match=missing):
        activation.compute_technical_readiness_features(
            **arguments, trade_date=TRADE_DATE
        )


def test_features_reject_invalid_dates_duplicates_and_malformed_numeric_values():
    activation = _activation()
    membership = _membership(("a", "retail"))
    invalid_date = _bars("a", [1.0])
    invalid_date["trade_date"] = invalid_date["trade_date"].astype(object)
    invalid_date.loc[0, "trade_date"] = "not-a-date"
    with pytest.raises(ValueError, match="trade_date"):
        activation.compute_technical_readiness_features(
            invalid_date, membership, trade_date=TRADE_DATE
        )

    duplicate = pd.concat([_bars("a", [1.0]), _bars("a", [2.0])], ignore_index=True)
    with pytest.raises(ValueError, match=r"duplicate.*a.*2026-01-01"):
        activation.compute_technical_readiness_features(
            duplicate, membership, trade_date=TRADE_DATE
        )

    for field, invalid in (
        ("close", "1.0"),
        ("close", 0.0),
        ("amount", -1.0),
        ("turnover_rate", np.inf),
    ):
        malformed = _bars("a", [1.0])
        malformed[field] = invalid
        with pytest.raises(ValueError, match=field):
            activation.compute_technical_readiness_features(
                malformed, membership, trade_date=TRADE_DATE
            )

    with pytest.raises(ValueError, match="trade_date cutoff"):
        activation.compute_technical_readiness_features(
            _bars("a", [1.0]), membership, trade_date="not-a-date"
        )


@pytest.mark.parametrize(
    "bar_date",
    ["2026-01-01 09:35:00", pd.Timestamp("2026-01-01", tz="Asia/Shanghai")],
)
def test_features_reject_intraday_and_timezone_aware_bars(bar_date):
    activation = _activation()
    bars = _bars("a", [1.0])
    bars["trade_date"] = pd.Series([bar_date], dtype=object)

    with pytest.raises(ValueError, match="trade_date"):
        activation.compute_technical_readiness_features(
            bars, _membership(("a", "retail")), trade_date=TRADE_DATE
        )


@pytest.mark.parametrize(
    "cutoff",
    ["2026-01-30 09:35:00", pd.Timestamp("2026-01-30", tz="Asia/Shanghai")],
)
def test_features_reject_intraday_and_timezone_aware_cutoffs(cutoff):
    activation = _activation()

    with pytest.raises(ValueError, match="trade_date cutoff"):
        activation.compute_technical_readiness_features(
            _bars("a", [1.0]), _membership(("a", "retail")), trade_date=cutoff
        )


@pytest.mark.parametrize(
    "asset_id",
    [None, pd.NA, np.nan, "", "   "],
)
@pytest.mark.parametrize("frame_name", ["bars", "membership"])
def test_features_reject_null_or_blank_asset_ids(asset_id, frame_name):
    activation = _activation()
    bars = _bars("a", [1.0])
    membership = _membership(("a", "retail"))
    if frame_name == "bars":
        bars["asset_id"] = asset_id
    else:
        membership["asset_id"] = asset_id

    with pytest.raises(ValueError, match="asset_id"):
        activation.compute_technical_readiness_features(
            bars, membership, trade_date=TRADE_DATE
        )


def test_membership_requires_unique_assets_and_nonempty_subindustry():
    activation = _activation()
    bars = _bars("a", [1.0])
    duplicate = _membership(("a", "retail"), ("a", "auto"))
    with pytest.raises(ValueError, match=r"duplicate.*a"):
        activation.compute_technical_readiness_features(
            bars, duplicate, trade_date=TRADE_DATE
        )

    for invalid in ("", "   ", None, pd.NA, np.nan):
        with pytest.raises(ValueError, match=r"subindustry.*a"):
            activation.compute_technical_readiness_features(
                bars, _membership(("a", invalid)), trade_date=TRADE_DATE
            )


def test_asset_ids_are_trimmed_for_matching_and_logical_duplicate_detection():
    activation = _activation()
    bars = _complete_bars(("A", "B", "C"))
    bars.loc[bars["asset_id"].eq("A"), "asset_id"] = " A "
    membership = _membership(("A", "retail"), ("B", "retail"), ("C", "retail"))

    result = activation.compute_technical_readiness_features(
        bars, membership, trade_date=TRADE_DATE
    )

    assert result["asset_id"].tolist() == ["A", "B", "C"]
    assert result.loc[result["asset_id"].eq("A"), "technical_feature_coverage"].item()

    duplicate_membership = _membership(("A", "retail"), (" A ", "retail"))
    with pytest.raises(ValueError, match=r"duplicate.*A"):
        activation.compute_technical_readiness_features(
            bars, duplicate_membership, trade_date=TRADE_DATE
        )

    duplicate_bars = pd.DataFrame(
        {
            "asset_id": ["A", " A "],
            "trade_date": ["2026-01-02", "2026-01-02"],
            "close": [1.0, 2.0],
            "amount": [1.0, 2.0],
            "turnover_rate": [1.0, 2.0],
        }
    )
    with pytest.raises(ValueError, match=r"duplicate.*A.*2026-01-02"):
        activation.compute_technical_readiness_features(
            duplicate_bars,
            _membership(("A", "retail")),
            trade_date=TRADE_DATE,
        )


def test_full_coverage_requires_22_sessions_and_three_covered_peers():
    activation = _activation()
    bars_21 = pd.concat(
        [_bars(asset_id, [float(value) for value in range(1, 22)]) for asset_id in ("a", "b", "c")],
        ignore_index=True,
    )
    membership = _membership(("a", "retail"), ("b", "retail"), ("c", "retail"))
    result_21 = activation.compute_technical_readiness_features(
        bars_21, membership, trade_date=TRADE_DATE
    )
    assert not result_21["technical_feature_coverage"].any()

    result_22 = activation.compute_technical_readiness_features(
        _complete_bars(), membership, trade_date=TRADE_DATE
    )
    assert result_22["technical_feature_coverage"].all()
    assert result_22["relative_return_5d"].notna().all()

    two_peer_membership = membership.iloc[:2].copy()
    two_peer_result = activation.compute_technical_readiness_features(
        _complete_bars(("a", "b")), two_peer_membership, trade_date=TRADE_DATE
    )
    assert two_peer_result["relative_return_5d"].isna().all()
    assert two_peer_result["relative_return_10d"].isna().all()
    assert two_peer_result["relative_strength_improvement_5d"].isna().all()
    assert not two_peer_result["technical_feature_coverage"].any()


def test_zero_denominators_and_flat_range_do_not_fabricate_features():
    activation = _activation()
    bars = pd.concat(
        [
            _bars(
                asset_id,
                [10.0] * 22,
                amounts=[0.0] * 22,
                turnovers=[0.0] * 22,
            )
            for asset_id in ("a", "b", "c")
        ],
        ignore_index=True,
    )
    result = activation.compute_technical_readiness_features(
        bars,
        _membership(("a", "retail"), ("b", "retail"), ("c", "retail")),
        trade_date=TRADE_DATE,
    )

    assert result["position_20d"].isna().all()
    assert result["amount_ratio_5d_20d"].isna().all()
    assert result["turnover_change_5d_20d"].isna().all()
    assert result["volatility_ratio_5d_20d"].isna().all()
    assert result["new_low_20d_within_3d"].all()
    assert not result["technical_feature_coverage"].any()
    assert result["technical_readiness_score"].isna().all()


def test_scoring_components_follow_direction_weights_and_control_volatility():
    activation = _activation()
    features = pd.DataFrame(
        [
            _score_row("low", -1.0, volatility_ratio=0.0),
            _score_row("middle", 0.0, volatility_ratio=1.0),
            _score_row("high", 1.0, volatility_ratio=3.0),
        ]
    )

    result = activation.score_technical_readiness(features).set_index("asset_id")

    for field in (
        "trend_turn_score",
        "relative_strength_improvement_score",
        "volume_turnover_confirmation_score",
        "moving_average_location_score",
    ):
        assert result.loc[["low", "middle", "high"], field].tolist() == [0.0, 50.0, 100.0]
    assert result.loc[["low", "middle", "high"], "volatility_transition_score"].tolist() == [
        25.0,
        100.0,
        25.0,
    ]
    assert result.loc["low", "technical_readiness_score"] == pytest.approx(2.5)
    assert result.loc["middle", "technical_readiness_score"] == pytest.approx(55.0)
    assert result.loc["high", "technical_readiness_score"] == pytest.approx(92.5)


def test_scoring_ties_singletons_and_uncovered_rows_are_deterministic_without_mutation():
    activation = _activation()
    tied = _score_row("a", 0.0)
    singleton = pd.DataFrame([tied])
    singleton_before = singleton.copy(deep=True)
    singleton_result = activation.score_technical_readiness(singleton)
    assert singleton_result["technical_readiness_score"].iloc[0] == 50.0
    pd.testing.assert_frame_equal(singleton, singleton_before)

    rows = pd.DataFrame([tied, _score_row("b", 0.0), _score_row("ignored", 999.0)])
    rows.loc[2, "technical_feature_coverage"] = False
    result = activation.score_technical_readiness(rows).set_index("asset_id")
    assert result.loc[["a", "b"], "technical_readiness_score"].tolist() == [50.0, 50.0]
    assert pd.isna(result.loc["ignored", "technical_readiness_score"])
    assert not result.loc["ignored", "falling_knife"]


def test_scoring_is_independent_of_duplicate_feature_index_labels():
    activation = _activation()
    features = pd.DataFrame(
        [
            _score_row("low", -1.0, volatility_ratio=0.0),
            _score_row("middle", 0.0, volatility_ratio=1.0),
            _score_row("high", 1.0, volatility_ratio=3.0),
        ]
    )
    duplicate_index_features = features.copy(deep=True)
    duplicate_index_features.index = [0, 0, 1]

    expected = activation.score_technical_readiness(features.reset_index(drop=True))
    actual = activation.score_technical_readiness(duplicate_index_features)

    pd.testing.assert_frame_equal(actual, expected)


def test_falling_knife_requires_every_condition():
    activation = _activation()
    target = _score_row("target", -5.0)
    target.update(
        {
            "distance_ma5": -0.2,
            "distance_ma10": -0.3,
            "ma5_slope_5d": -0.1,
            "relative_return_5d": -5.0,
            "new_low_20d_within_3d": True,
        }
    )
    peers = [_score_row(f"peer{index}", float(index)) for index in range(5)]
    base = pd.DataFrame([target, *peers])
    assert activation.score_technical_readiness(base).set_index("asset_id").loc[
        "target", "falling_knife"
    ]

    missing_one_cases = {
        "distance_ma5": 0.0,
        "distance_ma10": 0.0,
        "ma5_slope_5d": 0.0,
        "relative_return_5d": 10.0,
        "new_low_20d_within_3d": False,
    }
    for field, replacement in missing_one_cases.items():
        changed = base.copy(deep=True)
        changed.loc[changed["asset_id"].eq("target"), field] = replacement
        assert not activation.score_technical_readiness(changed).set_index("asset_id").loc[
            "target", "falling_knife"
        ], field


def test_activation_capital_sweet_spot_boundaries_and_ties_are_deterministic():
    activation = _activation()
    rows = []
    for percentile in range(101):
        rows.append(
            _activation_row(
                f"A{percentile:03d}",
                log_current_float_market_cap=float(percentile),
            )
        )

    result = activation.score_activation_candidates(
        pd.DataFrame(rows), _config()
    ).set_index("asset_id")

    assert result.loc["A015", "capital_efficiency_score"] == pytest.approx(61.25)
    assert result.loc["A065", "capital_efficiency_score"] == pytest.approx(61.25)
    assert result.loc["A014", "capital_efficiency_score"] == pytest.approx(60.25)
    assert result.loc["A066", "capital_efficiency_score"] == pytest.approx(
        (95.0 - 60.0 / 35.0 + 150.0) / 4.0
    )
    assert result.loc["A015", "capital_efficiency_score"] > result.loc[
        "A000", "capital_efficiency_score"
    ]
    assert result.loc["A065", "capital_efficiency_score"] > result.loc[
        "A100", "capital_efficiency_score"
    ]

    tied = pd.DataFrame(
        [_activation_row("T1"), _activation_row("T2"), _activation_row("T3")]
    )
    tied_result = activation.score_activation_candidates(tied, _config())
    assert tied_result["capital_efficiency_score"].tolist() == [61.25, 61.25, 61.25]


def test_activation_continuation_uses_documented_v2_groups_and_no_asymmetry_field():
    activation = _activation()
    rows = []
    for asset_id, level in (("low", 1.0), ("middle", 2.0), ("high", 3.0)):
        overrides = {field: level for field in ACTIVATION_CONTINUATION_FIELDS}
        rows.append(_activation_row(asset_id, **overrides))

    result = activation.score_activation_candidates(
        pd.DataFrame(rows), _config()
    ).set_index("asset_id")

    assert result.loc[["low", "middle", "high"], "continuation_character_score"].tolist() == [
        0.0,
        50.0,
        100.0,
    ]
    assert not any("asymmetry" in column for column in pd.DataFrame(rows).columns)


def test_activation_no_big_up_history_zero_fills_only_covered_post_event_metrics():
    activation = _activation()
    post_event_fields = (
        "positive_after_big_up_1d_rate",
        "positive_after_big_up_3d_rate",
        "positive_after_big_up_5d_rate",
        "median_return_after_big_up_3d",
        "median_return_after_big_up_5d",
        "strong_move_retention_5d_rate",
    )
    no_history = _activation_row("none", up_7pct_count_2y=0.0)
    missing_history = _activation_row("missing", up_7pct_count_2y=1.0)
    for field in post_event_fields:
        no_history[field] = np.nan
        missing_history[field] = np.nan

    result = activation.score_activation_candidates(
        pd.DataFrame([no_history, missing_history]), _config()
    ).set_index("asset_id")

    assert result.loc["none", "activation_coverage"]
    assert np.isfinite(result.loc["none", "continuation_character_score"])
    assert not result.loc["missing", "activation_coverage"]
    assert pd.isna(result.loc["missing", "continuation_character_score"])


@pytest.mark.parametrize(
    "missing_field",
    (
        "technical_readiness_score",
        "return_10d",
        *ACTIVATION_CONTINUATION_FIELDS,
        *ACTIVATION_RESIDUAL_FIELDS,
        *ACTIVATION_CAPITAL_FIELDS,
        "catalyst_verifiability_score",
    ),
)
def test_activation_missing_required_value_never_fabricates_a_score(missing_field):
    activation = _activation()
    row = _activation_row("missing")
    row[missing_field] = np.nan

    result = activation.score_activation_candidates(
        pd.DataFrame([row]), _config()
    ).iloc[0]

    assert not result["activation_coverage"]
    for field in ACTIVATION_ADDED_FIELDS[:4] + ("activation_score",):
        assert pd.isna(result[field]), field
    assert not result["activation_eligible"]
    assert result["activation_exclusion_reasons"] == "activation_coverage_incomplete"


@pytest.mark.parametrize(
    "missing_field",
    (
        "technical_feature_coverage",
        "falling_knife",
        "residual_deviation_coverage",
        "stock_character_coverage",
        "market_capacity_coverage",
    ),
)
def test_activation_missing_required_boolean_is_coverage_incomplete_only(missing_field):
    activation = _activation()
    row = _activation_row("missing")
    row[missing_field] = pd.NA

    result = activation.score_activation_candidates(
        pd.DataFrame([row]), _config()
    ).iloc[0]

    assert not result["activation_coverage"]
    assert pd.isna(result["activation_score"])
    assert result["activation_exclusion_reasons"] == "activation_coverage_incomplete"


def test_activation_overextension_requires_all_three_conditions():
    activation = _activation()
    peers = []
    for index in range(10):
        residual = {field: -10.0 for field in ACTIVATION_RESIDUAL_FIELDS}
        residual["rebound_from_low_60d"] = 0.10
        peers.append(_activation_row(f"peer{index}", return_10d=float(index), **residual))
    target_residual = {field: 10.0 for field in ACTIVATION_RESIDUAL_FIELDS}
    target_residual["rebound_from_low_60d"] = 0.40
    target = _activation_row("target", return_10d=10.0, **target_residual)
    base = pd.DataFrame([*peers, target])

    assert activation.score_activation_candidates(base, _config()).set_index(
        "asset_id"
    ).loc["target", "overextended"]

    changed = base.copy(deep=True)
    changed.loc[changed["asset_id"].eq("target"), "return_10d"] = -1.0
    assert not activation.score_activation_candidates(changed, _config()).set_index(
        "asset_id"
    ).loc["target", "overextended"]

    changed = base.copy(deep=True)
    changed.loc[changed["asset_id"].eq("target"), "rebound_from_low_60d"] = 0.29
    assert not activation.score_activation_candidates(changed, _config()).set_index(
        "asset_id"
    ).loc["target", "overextended"]

    changed = base.copy(deep=True)
    for field in ACTIVATION_RESIDUAL_FIELDS:
        if field != "rebound_from_low_60d":
            changed.loc[changed["asset_id"].eq("target"), field] = -20.0
    assert not activation.score_activation_candidates(changed, _config()).set_index(
        "asset_id"
    ).loc["target", "overextended"]


def test_activation_gate_reasons_are_exact_sorted_and_all_pass_is_eligible():
    activation = _activation()
    technical_raw = {
        "return_5d": -10.0,
        "ma5_slope_5d": -10.0,
        "ma10_slope_5d": -10.0,
        "relative_return_5d": 0.0,
        "relative_strength_improvement_5d": -10.0,
        "amount_ratio_5d_20d": -10.0,
        "turnover_change_5d_20d": -10.0,
        "distance_ma5": -10.0,
        "distance_ma10": -10.0,
        "distance_ma20": -10.0,
        "position_20d": -10.0,
        "volatility_ratio_5d_20d": 3.0,
    }
    knife_raw = {
        "return_5d": 10.0,
        "ma5_slope_5d": -1.0,
        "ma10_slope_5d": 10.0,
        "relative_return_5d": -5.0,
        "relative_strength_improvement_5d": 10.0,
        "amount_ratio_5d_20d": 10.0,
        "turnover_change_5d_20d": 10.0,
        "distance_ma5": -0.20,
        "distance_ma10": -0.30,
        "distance_ma20": 10.0,
        "position_20d": 10.0,
        "volatility_ratio_5d_20d": 1.0,
        "new_low_20d_within_3d": True,
    }
    rows = [
        _activation_row("pass"),
        _activation_row("technical", technical_readiness_score=34.99, **technical_raw),
        _activation_row("knife", falling_knife=True, **knife_raw),
        _activation_row("capacity", market_capacity_coverage=False),
        _activation_row("coverage", catalyst_verifiability_score=np.nan),
    ]
    result = activation.score_activation_candidates(
        pd.DataFrame(rows), _config()
    ).set_index("asset_id")

    assert result.loc["pass", "activation_eligible"]
    assert result.loc["pass", "activation_exclusion_reasons"] == ""
    assert result.loc["technical", "activation_exclusion_reasons"] == (
        "technical_readiness_below_threshold"
    )
    assert result.loc["knife", "activation_exclusion_reasons"] == "falling_knife"
    assert result.loc["capacity", "activation_exclusion_reasons"] == "|".join(
        sorted(
            {
                "activation_coverage_incomplete",
                "market_capacity_coverage_insufficient",
            }
        )
    )
    assert result.loc["coverage", "activation_exclusion_reasons"] == (
        "activation_coverage_incomplete"
    )

    combined_raw = {
        "return_5d": -10.0,
        "ma5_slope_5d": -10.0,
        "ma10_slope_5d": -10.0,
        "relative_return_5d": -10.0,
        "relative_strength_improvement_5d": -10.0,
        "amount_ratio_5d_20d": -10.0,
        "turnover_change_5d_20d": -10.0,
        "distance_ma5": -10.0,
        "distance_ma10": -10.0,
        "distance_ma20": -10.0,
        "position_20d": -10.0,
        "volatility_ratio_5d_20d": 3.0,
        "new_low_20d_within_3d": True,
    }
    combined = pd.DataFrame(
        [
            _activation_row(
                "combined",
                technical_readiness_score=0.0,
                falling_knife=True,
                market_capacity_coverage=False,
                catalyst_verifiability_score=np.nan,
                **combined_raw,
            ),
            _activation_row("combined-peer-1", return_5d=1.0, relative_return_5d=1.0),
            _activation_row("combined-peer-2", return_5d=2.0, relative_return_5d=2.0),
            _activation_row("combined-peer-3", return_5d=3.0, relative_return_5d=3.0),
        ]
    )
    reason = activation.score_activation_candidates(combined, _config()).set_index(
        "asset_id"
    ).loc["combined", "activation_exclusion_reasons"]
    assert reason == "|".join(
        sorted(
            {
                "activation_coverage_incomplete",
                "technical_readiness_below_threshold",
                "falling_knife",
                "market_capacity_coverage_insufficient",
            }
        )
    )


def test_activation_gate_marks_an_overextended_covered_row_with_exact_reason():
    activation = _activation()
    peers = []
    for index in range(10):
        residual = {field: -10.0 for field in ACTIVATION_RESIDUAL_FIELDS}
        residual["rebound_from_low_60d"] = 0.10
        peers.append(_activation_row(f"peer{index}", return_10d=float(index), **residual))
    residual = {field: 10.0 for field in ACTIVATION_RESIDUAL_FIELDS}
    residual["rebound_from_low_60d"] = 0.40
    rows = pd.DataFrame(
        [*peers, _activation_row("target", return_10d=10.0, **residual)]
    )

    target = activation.score_activation_candidates(rows, _config()).set_index(
        "asset_id"
    ).loc["target"]

    assert target["activation_coverage"]
    assert target["overextended"]
    assert not target["activation_eligible"]
    assert target["activation_exclusion_reasons"] == "overextended"


def test_activation_catalyst_timing_windows_and_strict_date_validation():
    activation = _activation()
    rows = pd.DataFrame(
        [
            _activation_row("d28", expected_validation_date="2026-02-27"),
            _activation_row("d84", expected_validation_date="2026-04-24"),
            _activation_row("missing", expected_validation_date=""),
            _activation_row("past", expected_validation_date="2026-01-29"),
            _activation_row("late", expected_validation_date="2026-04-25"),
        ]
    )
    result = activation.score_activation_candidates(rows, _config()).set_index(
        "asset_id"
    )

    assert result.loc["d28", "catalyst_timing_score"] == 75.0
    assert result.loc["d84", "catalyst_timing_score"] == 55.0
    assert result.loc[["missing", "past", "late"], "catalyst_timing_score"].tolist() == [
        35.0,
        35.0,
        35.0,
    ]

    invalid = pd.DataFrame(
        [_activation_row("bad", expected_validation_date="2026-2-01")]
    )
    with pytest.raises(ValueError, match=r"expected_validation_date.*bad"):
        activation.score_activation_candidates(invalid, _config())


def test_activation_score_uses_configured_exact_weights():
    activation = _activation()
    result = activation.score_activation_candidates(
        pd.DataFrame([_activation_row("A")]), _config()
    ).iloc[0]

    expected = (
        0.30 * result["technical_readiness_score"]
        + 0.25 * result["continuation_character_score"]
        + 0.20 * result["residual_price_space_score"]
        + 0.15 * result["capital_efficiency_score"]
        + 0.10 * result["catalyst_timing_score"]
    )
    assert result["activation_score"] == pytest.approx(expected)


def test_activation_has_no_name_or_code_specific_branches():
    activation = _activation()
    identities = (
        ("A", "600733", "北汽蓝谷"),
        ("B", "601127", "赛力斯"),
        ("C", "600702", "舍得酒业"),
        ("D", "600418", "江淮汽车"),
    )
    rows = []
    for asset_id, stock_code, stock_name in identities:
        rows.append(
            _activation_row(asset_id, stock_code=stock_code, stock_name=stock_name)
        )

    result = activation.score_activation_candidates(pd.DataFrame(rows), _config())

    for field in ACTIVATION_ADDED_FIELDS[:6]:
        assert result[field].nunique(dropna=False) == 1, field


def test_activation_normalizes_ids_resets_index_preserves_order_and_input():
    activation = _activation()
    rows = pd.DataFrame(
        [_activation_row(" B "), _activation_row("A"), _activation_row(" C")],
        index=[7, 7, 2],
    )
    before = rows.copy(deep=True)

    result = activation.score_activation_candidates(rows, _config())

    assert result.index.equals(pd.RangeIndex(3))
    assert result["asset_id"].tolist() == ["B", "A", "C"]
    assert result.columns[-len(ACTIVATION_ADDED_FIELDS) :].tolist() == list(
        ACTIVATION_ADDED_FIELDS
    )
    pd.testing.assert_frame_equal(rows, before)

    duplicate = pd.DataFrame([_activation_row("A"), _activation_row(" A ")])
    with pytest.raises(ValueError, match=r"duplicate.*A"):
        activation.score_activation_candidates(duplicate, _config())


def test_activation_scoring_is_isolated_from_complete_first_gate_ineligible_outlier():
    activation = _activation()
    rows = []
    for asset_id, level in (("low", -10.0), ("middle", 0.0), ("target", 10.0)):
        overrides = {field: level for field in ACTIVATION_CONTINUATION_FIELDS}
        overrides.update({field: level for field in ACTIVATION_RESIDUAL_FIELDS})
        overrides.update(
            {
                "return_10d": level,
                "rebound_from_low_60d": 0.40 if asset_id == "target" else 0.10,
                "log_current_float_market_cap": level,
                "average_amount_20d": level + 20.0,
                "average_turnover_rate_20d": level + 20.0,
                "amount_to_float_cap_20d": level + 20.0,
                "catalyst_verifiability_score": level + 20.0,
            }
        )
        rows.append(_activation_row(asset_id, **overrides))
    baseline = pd.DataFrame(rows)
    outlier_overrides = {
        field: 1_000_000.0
        for field in (
            *ACTIVATION_CONTINUATION_FIELDS,
            *ACTIVATION_RESIDUAL_FIELDS,
            *ACTIVATION_CAPITAL_FIELDS,
        )
    }
    outlier = _activation_row(
        "outlier",
        eligible=False,
        return_10d=1_000_000.0,
        catalyst_verifiability_score=1_000_000.0,
        **outlier_overrides,
    )

    expected = activation.score_activation_candidates(baseline, _config()).set_index(
        "asset_id"
    )
    actual = activation.score_activation_candidates(
        pd.concat([baseline, pd.DataFrame([outlier])], ignore_index=True), _config()
    ).set_index("asset_id")

    comparison_fields = (
        "continuation_character_score",
        "residual_price_space_score",
        "capital_efficiency_score",
        "catalyst_timing_score",
        "activation_score",
        "overextended",
        "activation_eligible",
    )
    pd.testing.assert_frame_equal(
        actual.loc[expected.index, list(comparison_fields)],
        expected.loc[:, list(comparison_fields)],
    )
    assert expected.loc["target", "overextended"]
    assert not actual.loc["outlier", "activation_coverage"]
    for field in ACTIVATION_ADDED_FIELDS[:4] + ("activation_score",):
        assert pd.isna(actual.loc["outlier", field]), field
    assert not actual.loc["outlier", "activation_eligible"]
    assert actual.loc["outlier", "activation_exclusion_reasons"] == ""


@pytest.mark.parametrize("invalid", [None, pd.NA, np.nan, 1, 0, "true", "false"])
def test_activation_requires_strict_boolean_first_gate_eligibility(invalid):
    activation = _activation()

    with pytest.raises(ValueError, match=r"eligible.*strict boolean"):
        activation.score_activation_candidates(
            pd.DataFrame([_activation_row("A", eligible=invalid)]), _config()
        )


def test_activation_recomputes_technical_scores_inside_first_gate_eligible_pool():
    activation = _activation()
    target = _activation_row(
        "target",
        return_5d=-1.0,
        ma5_slope_5d=-0.10,
        ma10_slope_5d=-0.05,
        relative_return_5d=-5.0,
        relative_strength_improvement_5d=-1.0,
        amount_ratio_5d_20d=0.5,
        turnover_change_5d_20d=-0.5,
        distance_ma5=-0.20,
        distance_ma10=-0.30,
        distance_ma20=-0.40,
        position_20d=0.0,
        volatility_ratio_5d_20d=3.0,
        new_low_20d_within_3d=True,
        technical_readiness_score=99.0,
        falling_knife=False,
    )
    peers = []
    for index, level in enumerate((0.0, 1.0, 2.0)):
        peers.append(
            _activation_row(
                f"peer{index}",
                return_5d=level,
                ma5_slope_5d=level,
                ma10_slope_5d=level,
                relative_return_5d=level,
                relative_strength_improvement_5d=level,
                amount_ratio_5d_20d=level + 1.0,
                turnover_change_5d_20d=level,
                distance_ma5=level,
                distance_ma10=level,
                distance_ma20=level,
                position_20d=level,
                volatility_ratio_5d_20d=1.0,
                technical_readiness_score=99.0,
                falling_knife=False,
            )
        )
    baseline = pd.DataFrame([target, *peers])
    raw_outlier = {
        field: 1_000_000.0
        for field in (
            "return_5d",
            "ma5_slope_5d",
            "ma10_slope_5d",
            "relative_strength_improvement_5d",
            "amount_ratio_5d_20d",
            "turnover_change_5d_20d",
            "distance_ma5",
            "distance_ma10",
            "distance_ma20",
            "position_20d",
        )
    }
    outlier = _activation_row(
        "outlier",
        eligible=False,
        relative_return_5d=-1_000_000.0,
        volatility_ratio_5d_20d=1_000_000.0,
        new_low_20d_within_3d=True,
        technical_readiness_score=99.0,
        falling_knife=False,
        **raw_outlier,
    )

    expected = activation.score_activation_candidates(baseline, _config()).set_index(
        "asset_id"
    )
    actual = activation.score_activation_candidates(
        pd.concat([baseline, pd.DataFrame([outlier])], ignore_index=True), _config()
    ).set_index("asset_id")

    comparison_fields = (*SCORE_COLUMNS, "activation_score", "activation_eligible")
    pd.testing.assert_frame_equal(
        actual.loc[expected.index, list(comparison_fields)],
        expected.loc[:, list(comparison_fields)],
    )
    assert expected.loc["target", "falling_knife"]
    assert expected.loc["target", "technical_readiness_score"] != 99.0
    for field in SCORE_COLUMNS[:-1]:
        assert pd.isna(actual.loc["outlier", field]), field
    assert not actual.loc["outlier", "falling_knife"]


def test_activation_zero_verifiability_forces_zero_catalyst_timing_for_singleton():
    activation = _activation()
    result = activation.score_activation_candidates(
        pd.DataFrame([_activation_row("zero", catalyst_verifiability_score=0.0)]),
        _config(),
    ).iloc[0]

    assert result["activation_coverage"]
    assert result["catalyst_timing_score"] == 0.0


def test_activation_all_zero_verifiability_forces_zero_catalyst_timing():
    activation = _activation()
    rows = pd.DataFrame(
        [
            _activation_row("A", catalyst_verifiability_score=0.0),
            _activation_row("B", catalyst_verifiability_score=0.0),
            _activation_row("C", catalyst_verifiability_score=0.0),
        ]
    )

    result = activation.score_activation_candidates(rows, _config())

    assert result["activation_coverage"].all()
    assert result["catalyst_timing_score"].tolist() == [0.0, 0.0, 0.0]
