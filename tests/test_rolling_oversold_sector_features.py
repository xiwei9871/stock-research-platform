from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from stock_research.rolling_oversold.sector_scoring import score_sector_states


ANCHOR = date(2026, 7, 31)


def membership_for_one_sector() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "asset_id": ["CN:SH:000001"],
            "concept_system": ["ths"],
            "concept_code": ["300238"],
            "concept_name": ["核电"],
            "start_date": [date(2020, 1, 1)],
            "end_date": [pd.NaT],
        }
    )


def make_sector_bars(
    closes: list[float],
    *,
    volumes: list[float] | None = None,
    amounts: list[float] | None = None,
    anchor_date: date = ANCHOR,
) -> pd.DataFrame:
    start = anchor_date - timedelta(days=len(closes) - 1)
    frame: dict[str, object] = {
        "concept_system": ["ths"] * len(closes),
        "concept_code": ["300238"] * len(closes),
        "concept_name": ["核电"] * len(closes),
        "trade_date": [start + timedelta(days=index) for index in range(len(closes))],
        "close": closes,
    }
    if volumes is not None:
        frame["volume"] = volumes
    if amounts is not None:
        frame["amount"] = amounts
    return pd.DataFrame(frame)


def make_scored_sector_row(bars: pd.DataFrame, *, anchor_date: date = ANCHOR) -> pd.Series:
    result = score_sector_states(
        sector_bars=bars,
        membership=membership_for_one_sector(),
        market_regime={"market_regime": "risk_off"},
        anchor_date=anchor_date,
    )
    return result.loc[result["sector_code"].eq("300238")].iloc[0]


def test_recovery_from_recent_low_and_days_since_low() -> None:
    bars = make_sector_bars(
        [100, 95, 90, 88, 92, 94],
        volumes=[100, 100, 120, 140, 180, 220],
        amounts=[1000, 1000, 1200, 1400, 1800, 2200],
    )

    row = make_scored_sector_row(bars)

    assert row["sector_low_close_20d"] == 88
    assert row["sector_recovery_from_low_20d"] == pytest.approx(94 / 88 - 1)
    assert row["sector_days_since_low_20d"] == 2
    assert row["sector_low_date_20d"] == "2026-07-29"
    assert row["sector_volume_ratio_5_20"] > 1
    assert row["sector_amount_ratio_5_20"] > 1


def test_sector_feature_columns_are_emitted() -> None:
    row = make_scored_sector_row(
        make_sector_bars(
            [100, 95, 90, 88, 92, 94],
            volumes=[100, 100, 120, 140, 180, 220],
            amounts=[1000, 1000, 1200, 1400, 1800, 2200],
        )
    )

    expected = {
        *(f"sector_low_close_{window}d" for window in (20, 30, 60)),
        *(f"sector_low_date_{window}d" for window in (20, 30, 60)),
        *(f"sector_recovery_from_low_{window}d" for window in (20, 30, 60)),
        *(f"sector_days_since_low_{window}d" for window in (20, 30, 60)),
        *(f"sector_return_{period}d" for period in (1, 3, 5, 10, 20)),
        "sector_ma5",
        "sector_ma10",
        "sector_ma20",
        "sector_ma5_slope_5d",
        "sector_ma10_slope_10d",
        "sector_ma5_cross_ma10",
        "sector_close_above_ma5",
        "sector_close_above_ma20",
        "sector_amount_ratio_5_20",
        "sector_volume_ratio_5_20",
        "sector_up_ratio_1d",
        "sector_up_ratio_5d",
        "sector_up_ratio_20d",
        "sector_above_ma5_ratio",
        "sector_above_ma20_ratio",
        "sector_new_low_ratio_20d",
        "sector_new_low_ratio_60d",
        "sector_leader_return_1d",
        "sector_leader_return_3d",
        "sector_leader_return_5d",
        "sector_leader_breadth",
        "sector_dispersion_20d",
        "sector_research_eligibility",
        "sector_feature_data_status",
    }

    assert expected.issubset(row.index)


def test_missing_volume_does_not_substitute_amount_ratio() -> None:
    row = make_scored_sector_row(
        make_sector_bars(
            [100, 95, 90, 88, 92, 94],
            amounts=[1000, 1000, 1200, 1400, 1800, 2200],
        )
    )

    assert pd.isna(row["sector_volume_ratio_5_20"])
    assert row["sector_amount_ratio_5_20"] > 1
    assert row["sector_research_eligibility"] == "blocked_data"
    assert row["sector_feature_data_status"] == "missing_volume"


def test_six_bar_history_is_blocked_when_required_repair_features_are_missing() -> None:
    row = make_scored_sector_row(
        make_sector_bars(
            [100, 95, 90, 88, 92, 94],
            volumes=[100, 100, 120, 140, 180, 220],
            amounts=[1000, 1000, 1200, 1400, 1800, 2200],
        )
    )

    assert row["sector_research_eligibility"] == "blocked_data"
    assert row["sector_feature_data_status"] == "insufficient_history"
    assert pd.isna(row["sector_ma5_slope_5d"])
    assert pd.isna(row["sector_ma10_slope_10d"])


def test_complete_history_has_ok_feature_status() -> None:
    row = make_scored_sector_row(
        make_sector_bars(
            [120 - index for index in range(19)] + [100, 95, 90, 88, 92, 94],
            volumes=[100] * 19 + [100, 100, 120, 140, 180, 220],
            amounts=[1000] * 19 + [1000, 1000, 1200, 1400, 1800, 2200],
        )
    )

    assert row["sector_feature_data_status"] == "ok"
    assert row["sector_research_eligibility"] in {"eligible", "watch"}


@pytest.mark.parametrize("missing_index", [10, 24])
def test_partial_volume_history_is_blocked_instead_of_dropna_substitution(
    missing_index: int,
) -> None:
    volumes = [100.0] * 25
    volumes[missing_index] = float("nan")
    row = make_scored_sector_row(
        make_sector_bars(
            [120 - index for index in range(19)] + [100, 95, 90, 88, 92, 94],
            volumes=volumes,
            amounts=[1000] * 25,
        )
    )

    assert pd.isna(row["sector_volume_ratio_5_20"])
    assert row["sector_feature_data_status"] == "missing_volume"
    assert row["sector_research_eligibility"] == "blocked_data"


@pytest.mark.parametrize("missing_index", [10, 24])
def test_partial_close_history_does_not_compress_trading_day_windows(
    missing_index: int,
) -> None:
    closes = [120 - index for index in range(19)] + [100, 95, 90, 88, 92, 94]
    closes[missing_index] = float("nan")
    row = make_scored_sector_row(
        make_sector_bars(
            closes,
            volumes=[100] * 25,
            amounts=[1000] * 25,
        )
    )

    assert pd.isna(row["sector_low_close_20d"])
    assert pd.isna(row["sector_return_20d"])
    if missing_index == 10:
        assert pd.isna(row["sector_ma20"])
    else:
        assert pd.isna(row["sector_ma5"])
        assert pd.isna(row["sector_ma10"])
        assert pd.isna(row["sector_ma20"])
    assert row["sector_feature_data_status"] == "missing_feature_data"
    assert row["sector_research_eligibility"] == "blocked_data"


def test_future_bar_after_anchor_does_not_change_frozen_features() -> None:
    history = make_sector_bars(
        [100, 95, 90, 88, 92, 94],
        volumes=[100, 100, 120, 140, 180, 220],
        amounts=[1000, 1000, 1200, 1400, 1800, 2200],
    )
    future = history.iloc[[-1]].copy()
    future["trade_date"] = ANCHOR + timedelta(days=1)
    future["close"] = 200
    future["volume"] = 1000
    future["amount"] = 10000

    base = make_scored_sector_row(history)
    frozen = make_scored_sector_row(pd.concat([history, future], ignore_index=True))

    columns = [
        "data_cutoff_date",
        "history_observations",
        "sector_low_close_20d",
        "sector_low_date_20d",
        "sector_recovery_from_low_20d",
        "sector_days_since_low_20d",
        "sector_return_1d",
        "sector_ma5",
        "sector_amount_ratio_5_20",
        "sector_volume_ratio_5_20",
    ]
    pd.testing.assert_series_equal(
        base.loc[columns], frozen.loc[columns], check_names=False
    )


def test_short_history_returns_empty_low_and_trend_features() -> None:
    row = make_scored_sector_row(
        make_sector_bars(
            [100, 95, 90],
            volumes=[100, 100, 120],
            amounts=[1000, 1000, 1200],
        )
    )

    for column in (
        "sector_low_close_20d",
        "sector_low_date_20d",
        "sector_recovery_from_low_20d",
        "sector_days_since_low_20d",
        "sector_ma5",
        "sector_ma10",
        "sector_ma20",
        "sector_ma5_slope_5d",
        "sector_ma10_slope_10d",
    ):
        assert pd.isna(row[column]), column
