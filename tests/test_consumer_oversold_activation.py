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
