from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from .contracts import ConsumerOversoldConfig


BAR_COLUMNS = ("asset_id", "trade_date", "close", "amount", "turnover_rate")
MEMBERSHIP_COLUMNS = ("asset_id", "consumer_subindustry")
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
OUTPUT_COLUMNS = RAW_COLUMNS + SCORE_COLUMNS

_STRICT_NUMERIC_TYPES = (int, float, np.integer, np.floating, Decimal)
_TECHNICAL_VALUE_COLUMNS = (
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
)
_SCORE_INPUT_COLUMNS = (
    "return_5d",
    "ma5_slope_5d",
    "ma10_slope_5d",
    "relative_return_5d",
    "relative_strength_improvement_5d",
    "amount_ratio_5d_20d",
    "turnover_change_5d_20d",
    "distance_ma5",
    "distance_ma10",
    "distance_ma20",
    "position_20d",
    "volatility_ratio_5d_20d",
    "new_low_20d_within_3d",
    "technical_feature_coverage",
)
_ACTIVATION_CONTINUATION_FIELDS = (
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
_ACTIVATION_TECHNICAL_RAW_NUMERIC_FIELDS = (
    "return_5d",
    "ma5_slope_5d",
    "ma10_slope_5d",
    "relative_return_5d",
    "relative_strength_improvement_5d",
    "amount_ratio_5d_20d",
    "turnover_change_5d_20d",
    "distance_ma5",
    "distance_ma10",
    "distance_ma20",
    "position_20d",
    "volatility_ratio_5d_20d",
)
_ACTIVATION_POST_EVENT_FIELDS = (
    "positive_after_big_up_1d_rate",
    "positive_after_big_up_3d_rate",
    "positive_after_big_up_5d_rate",
    "median_return_after_big_up_3d",
    "median_return_after_big_up_5d",
    "strong_move_retention_5d_rate",
)
_ACTIVATION_RESIDUAL_FIELDS = (
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
_ACTIVATION_CAPITAL_FIELDS = (
    "log_current_float_market_cap",
    "average_amount_20d",
    "average_turnover_rate_20d",
    "amount_to_float_cap_20d",
)
_ACTIVATION_NUMERIC_FIELDS = (
    "technical_readiness_score",
    "return_10d",
    *_ACTIVATION_TECHNICAL_RAW_NUMERIC_FIELDS,
    *_ACTIVATION_CONTINUATION_FIELDS,
    *_ACTIVATION_RESIDUAL_FIELDS,
    *_ACTIVATION_CAPITAL_FIELDS,
    "catalyst_verifiability_score",
)
_ACTIVATION_BOOLEAN_FIELDS = (
    "technical_feature_coverage",
    "new_low_20d_within_3d",
    "falling_knife",
    "residual_deviation_coverage",
    "stock_character_coverage",
    "market_capacity_coverage",
)
_ACTIVATION_REQUIRED_COLUMNS = (
    "asset_id",
    "eligible",
    *_ACTIVATION_NUMERIC_FIELDS,
    *_ACTIVATION_BOOLEAN_FIELDS,
    "expected_validation_date",
)
_ACTIVATION_ADDED_COLUMNS = (
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


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {', '.join(missing)}")


def _parse_cutoff(trade_date: object) -> pd.Timestamp:
    if isinstance(trade_date, (bool, int, float, np.number, Decimal)):
        raise ValueError(f"invalid trade_date cutoff: {trade_date!r}")
    try:
        cutoff = pd.Timestamp(trade_date)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"invalid trade_date cutoff: {trade_date!r}") from exc
    if (
        pd.isna(cutoff)
        or cutoff.tzinfo is not None
        or cutoff != cutoff.normalize()
    ):
        raise ValueError(f"invalid trade_date cutoff: {trade_date!r}")
    return cutoff


def _parse_bar_dates(frame: pd.DataFrame) -> pd.Series:
    parsed: list[pd.Timestamp] = []
    for value in frame["trade_date"]:
        if isinstance(value, (bool, int, float, np.number, Decimal)):
            raise ValueError("bars trade_date contains an invalid date")
        try:
            timestamp = pd.Timestamp(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("bars trade_date contains an invalid date") from exc
        if (
            pd.isna(timestamp)
            or timestamp.tzinfo is not None
            or timestamp != timestamp.normalize()
        ):
            raise ValueError("bars trade_date contains an invalid date")
        parsed.append(timestamp)
    return pd.Series(parsed, index=frame.index, dtype="datetime64[ns]")


def _validate_asset_ids(frame: pd.DataFrame, name: str) -> None:
    invalid = frame["asset_id"].map(
        lambda value: pd.isna(value) or not str(value).strip()
    )
    if invalid.any():
        raise ValueError(f"{name} asset_id must be non-null and non-empty")


def _strict_numeric_value(value: object, *, field: str, asset_id: str, date: pd.Timestamp) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, _STRICT_NUMERIC_TYPES):
        raise ValueError(
            f"bars {field} must be finite numeric for asset {asset_id} "
            f"on {date.date().isoformat()}"
        )
    if isinstance(value, Decimal) and not value.is_finite():
        raise ValueError(
            f"bars {field} must be finite numeric for asset {asset_id} "
            f"on {date.date().isoformat()}"
        )
    try:
        number = float(value)
    except (OverflowError, ValueError):
        number = math.nan
    if not math.isfinite(number):
        raise ValueError(
            f"bars {field} must be finite numeric for asset {asset_id} "
            f"on {date.date().isoformat()}"
        )
    return number


def _validate_numeric_bars(frame: pd.DataFrame) -> None:
    for index, row in frame.iterrows():
        asset_id = str(row["asset_id"])
        date = row["trade_date"]
        for field in ("close", "amount", "turnover_rate"):
            number = _strict_numeric_value(
                row[field], field=field, asset_id=asset_id, date=date
            )
            if field == "close" and number <= 0.0:
                raise ValueError(
                    f"bars close must be positive for asset {asset_id} "
                    f"on {date.date().isoformat()}"
                )
            if field != "close" and number < 0.0:
                raise ValueError(
                    f"bars {field} must be nonnegative for asset {asset_id} "
                    f"on {date.date().isoformat()}"
                )
            frame.at[index, field] = number
    for field in ("close", "amount", "turnover_rate"):
        frame[field] = frame[field].astype(float)


def _validate_membership(membership: pd.DataFrame) -> pd.DataFrame:
    frame = membership.loc[:, MEMBERSHIP_COLUMNS].copy().reset_index(drop=True)
    _validate_asset_ids(frame, "membership")
    frame["asset_id"] = frame["asset_id"].astype(str).str.strip()
    duplicate = frame["asset_id"].duplicated(keep=False)
    if duplicate.any():
        asset_id = frame.loc[duplicate, "asset_id"].sort_values(kind="stable").iloc[0]
        raise ValueError(f"membership contains duplicate asset_id {asset_id}")
    invalid_subindustry = frame["consumer_subindustry"].map(
        lambda value: pd.isna(value) or not str(value).strip()
    )
    if invalid_subindustry.any():
        asset_id = (
            frame.loc[invalid_subindustry, "asset_id"].sort_values(kind="stable").iloc[0]
        )
        raise ValueError(f"membership consumer_subindustry is empty for asset {asset_id}")
    return frame.sort_values("asset_id", kind="stable").reset_index(drop=True)


def _period_return(close: pd.Series, sessions: int) -> float:
    """Return close[t] / close[t-sessions] - 1 using complete endpoints."""
    if len(close) <= sessions:
        return math.nan
    return float(close.iloc[-1] / close.iloc[-sessions - 1] - 1.0)


def _moving_average(close: pd.Series, sessions: int, *, offset: int = 0) -> float:
    end = len(close) - offset
    start = end - sessions
    if start < 0 or end <= 0:
        return math.nan
    return float(close.iloc[start:end].mean())


def _safe_ratio(numerator: float, denominator: float, *, subtract_one: bool = False) -> float:
    if not math.isfinite(numerator) or not math.isfinite(denominator) or denominator == 0.0:
        return math.nan
    ratio = numerator / denominator
    return ratio - 1.0 if subtract_one else ratio


def _position_20d(close: pd.Series) -> float:
    if len(close) < 20:
        return math.nan
    window = close.tail(20)
    low = float(window.min())
    high = float(window.max())
    if high == low:
        return math.nan
    return float((close.iloc[-1] - low) / (high - low))


def _volatility_ratio(close: pd.Series) -> float:
    if len(close) < 21:
        return math.nan
    daily_returns = close.pct_change(fill_method=None).dropna()
    short_volatility = float(daily_returns.tail(5).std(ddof=1))
    long_volatility = float(daily_returns.tail(20).std(ddof=1))
    return _safe_ratio(short_volatility, long_volatility)


def _new_low_within_last_three(close: pd.Series) -> bool:
    # Twenty-two closes are needed so every one of the final three sessions has
    # its own complete trailing 20-session window. Each comparison is backward-only.
    if len(close) < 22:
        return False
    for endpoint in range(len(close) - 3, len(close)):
        rolling_low = float(close.iloc[endpoint - 19 : endpoint + 1].min())
        if float(close.iloc[endpoint]) == rolling_low:
            return True
    return False


def _raw_asset_features(history: pd.DataFrame | None) -> dict[str, object]:
    if history is None or history.empty:
        return {
            "latest_trade_date": pd.NaT,
            **{column: math.nan for column in _TECHNICAL_VALUE_COLUMNS},
            "new_low_20d_within_3d": False,
            "_prior_return_5d": math.nan,
            "_history_sessions": 0,
        }

    close = history["close"].reset_index(drop=True)
    amount = history["amount"].reset_index(drop=True)
    turnover = history["turnover_rate"].reset_index(drop=True)
    latest_close = float(close.iloc[-1])
    ma5 = _moving_average(close, 5)
    ma10 = _moving_average(close, 10)
    ma20 = _moving_average(close, 20)
    prior_ma5 = _moving_average(close, 5, offset=5)
    prior_ma10 = _moving_average(close, 10, offset=5)
    amount_5d = float(amount.tail(5).mean()) if len(amount) >= 5 else math.nan
    amount_20d = float(amount.tail(20).mean()) if len(amount) >= 20 else math.nan
    turnover_5d = float(turnover.tail(5).mean()) if len(turnover) >= 5 else math.nan
    turnover_20d = float(turnover.tail(20).mean()) if len(turnover) >= 20 else math.nan

    return {
        "latest_trade_date": history["trade_date"].iloc[-1],
        "return_5d": _period_return(close, 5),
        "return_10d": _period_return(close, 10),
        "return_20d": _period_return(close, 20),
        "relative_return_5d": math.nan,
        "relative_return_10d": math.nan,
        "relative_strength_improvement_5d": math.nan,
        "ma5_slope_5d": _safe_ratio(ma5, prior_ma5, subtract_one=True),
        "ma10_slope_5d": _safe_ratio(ma10, prior_ma10, subtract_one=True),
        "distance_ma5": _safe_ratio(latest_close, ma5, subtract_one=True),
        "distance_ma10": _safe_ratio(latest_close, ma10, subtract_one=True),
        "distance_ma20": _safe_ratio(latest_close, ma20, subtract_one=True),
        "position_20d": _position_20d(close),
        "amount_ratio_5d_20d": _safe_ratio(amount_5d, amount_20d),
        "turnover_change_5d_20d": _safe_ratio(
            turnover_5d, turnover_20d, subtract_one=True
        ),
        "volatility_ratio_5d_20d": _volatility_ratio(close),
        "new_low_20d_within_3d": _new_low_within_last_three(close),
        "_prior_return_5d": (
            float(close.iloc[-6] / close.iloc[-11] - 1.0)
            if len(close) >= 11
            else math.nan
        ),
        "_history_sessions": len(close),
    }


def _add_relative_features(frame: pd.DataFrame) -> None:
    grouped = frame.groupby("_consumer_subindustry", dropna=False)
    for source, target in (
        ("return_5d", "relative_return_5d"),
        ("return_10d", "relative_return_10d"),
        ("_prior_return_5d", "_prior_relative_return_5d"),
    ):
        peer_count = grouped[source].transform("count")
        peer_mean = grouped[source].transform("mean")
        covered = peer_count.ge(3) & frame[source].notna()
        frame[target] = (frame[source] - peer_mean).where(covered)
    frame["relative_strength_improvement_5d"] = (
        frame["relative_return_5d"] - frame["_prior_relative_return_5d"]
    )


def _cross_sectional_percentile(values: pd.Series) -> pd.Series:
    result = pd.Series(math.nan, index=values.index, dtype="float64")
    valid = values.dropna()
    if valid.empty:
        return result
    if len(valid) == 1 or valid.nunique(dropna=True) == 1:
        result.loc[valid.index] = 50.0
        return result
    ranks = valid.rank(method="average", ascending=True)
    result.loc[valid.index] = (ranks - 1.0) / (len(valid) - 1.0) * 100.0
    return result


def _component_score(
    frame: pd.DataFrame, fields: tuple[str, ...], coverage: pd.Series
) -> pd.Series:
    percentiles = {
        field: _cross_sectional_percentile(frame[field].where(coverage))
        for field in fields
    }
    return pd.DataFrame(percentiles, index=frame.index).mean(
        axis=1, skipna=False
    ).where(coverage)


def score_technical_readiness(
    features: pd.DataFrame,
    *,
    scoring_universe: pd.Series | None = None,
) -> pd.DataFrame:
    """Add direction-aware technical scores and the falling-knife guard.

    Volatility transition uses ``max(0, 1 - abs(ratio - 1))`` before ranking.
    It rewards a controlled transition around a 1.0 short/long volatility ratio;
    both contraction toward zero and expansion to 2.0 or beyond score lower.
    """
    _require_columns(features, _SCORE_INPUT_COLUMNS, "features")
    frame = features.copy(deep=True).reset_index(drop=True)
    coverage = frame["technical_feature_coverage"].eq(True)
    if scoring_universe is not None:
        universe = pd.Series(scoring_universe).reset_index(drop=True)
        if len(universe) != len(frame):
            raise ValueError("scoring_universe length must match features")
        if not universe.map(lambda value: isinstance(value, (bool, np.bool_))).all():
            raise ValueError("scoring_universe must contain strict booleans")
        coverage &= universe.astype(bool)

    frame["trend_turn_score"] = _component_score(
        frame, ("return_5d", "ma5_slope_5d", "ma10_slope_5d"), coverage
    )
    frame["relative_strength_improvement_score"] = _component_score(
        frame,
        ("relative_return_5d", "relative_strength_improvement_5d"),
        coverage,
    )
    frame["volume_turnover_confirmation_score"] = _component_score(
        frame, ("amount_ratio_5d_20d", "turnover_change_5d_20d"), coverage
    )
    frame["moving_average_location_score"] = _component_score(
        frame,
        ("distance_ma5", "distance_ma10", "distance_ma20", "position_20d"),
        coverage,
    )
    volatility_desirability = (
        1.0 - (frame["volatility_ratio_5d_20d"] - 1.0).abs()
    ).clip(lower=0.0, upper=1.0)
    frame["volatility_transition_score"] = _cross_sectional_percentile(
        volatility_desirability.where(coverage)
    ).where(coverage)
    frame["technical_readiness_score"] = (
        0.30 * frame["trend_turn_score"]
        + 0.25 * frame["relative_strength_improvement_score"]
        + 0.20 * frame["volume_turnover_confirmation_score"]
        + 0.15 * frame["moving_average_location_score"]
        + 0.10 * frame["volatility_transition_score"]
    ).clip(lower=0.0, upper=100.0)

    relative_percentile = _cross_sectional_percentile(
        frame["relative_return_5d"].where(coverage)
    )
    frame["falling_knife"] = (
        coverage
        & frame["distance_ma5"].lt(0.0)
        & frame["distance_ma10"].lt(0.0)
        & frame["ma5_slope_5d"].lt(0.0)
        & relative_percentile.le(20.0)
        & frame["new_low_20d_within_3d"].eq(True)
    ).astype(bool)
    return frame


def _is_missing_scalar(value: object) -> bool:
    if value is None or value is pd.NA:
        return True
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(missing) if isinstance(missing, (bool, np.bool_)) else False


def _activation_numeric_value(value: object, *, field: str, asset_id: str) -> float:
    if _is_missing_scalar(value):
        return math.nan
    if isinstance(value, (bool, np.bool_)) or not isinstance(
        value, _STRICT_NUMERIC_TYPES
    ):
        raise ValueError(f"rows asset {asset_id} field {field} must be finite numeric")
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(
            f"rows asset {asset_id} field {field} must be finite numeric"
        ) from exc
    if not math.isfinite(number):
        if math.isnan(number):
            return math.nan
        raise ValueError(f"rows asset {asset_id} field {field} must be finite numeric")
    return number


def _activation_boolean_value(
    value: object, *, field: str, asset_id: str
) -> tuple[bool, bool]:
    if _is_missing_scalar(value):
        return False, False
    if not isinstance(value, (bool, np.bool_)):
        raise ValueError(f"rows asset {asset_id} field {field} must be a strict boolean")
    return bool(value), True


def _activation_expected_date(value: object, *, asset_id: str) -> date | None:
    if _is_missing_scalar(value) or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise ValueError(
            f"expected_validation_date for asset {asset_id} must use YYYY-MM-DD"
        )
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"expected_validation_date for asset {asset_id} must use YYYY-MM-DD"
        ) from exc
    if parsed.isoformat() != value:
        raise ValueError(
            f"expected_validation_date for asset {asset_id} must use YYYY-MM-DD"
        )
    return parsed


def _activation_percentile(
    values: pd.Series,
    coverage: pd.Series,
    *,
    favorable_low: bool = False,
    winsorize: bool = False,
) -> pd.Series:
    selected = values.where(coverage)
    valid = selected.dropna()
    result = pd.Series(math.nan, index=values.index, dtype="float64")
    if valid.empty:
        return result
    if winsorize:
        valid = valid.clip(
            lower=float(valid.quantile(0.05)),
            upper=float(valid.quantile(0.95)),
        )
    if len(valid) == 1 or valid.nunique(dropna=True) == 1:
        result.loc[valid.index] = 50.0
        return result
    ranks = valid.rank(method="average", ascending=not favorable_low)
    result.loc[valid.index] = (ranks - 1.0) / (len(valid) - 1.0) * 100.0
    return result


def _activation_percentile_mean(
    frame: pd.DataFrame,
    fields: tuple[str, ...],
    coverage: pd.Series,
    *,
    favorable_low: bool = False,
    winsorize_fields: tuple[str, ...] = (),
) -> pd.Series:
    percentiles = {
        field: _activation_percentile(
            frame[field],
            coverage,
            favorable_low=favorable_low,
            winsorize=field in winsorize_fields,
        )
        for field in fields
    }
    return pd.DataFrame(percentiles, index=frame.index).mean(
        axis=1, skipna=False
    ).where(coverage)


def score_activation_candidates(
    rows: pd.DataFrame,
    config: ConsumerOversoldConfig,
) -> pd.DataFrame:
    """Score the fully covered V2 activation cross-section and apply its gate.

    The first V2 implementation deliberately uses upside-tail volatility alone
    for the 15% upside-tail/asymmetry group. No stable asymmetry input exists in
    the current candidate contract, so its absence must not reduce coverage.
    """
    _require_columns(rows, _ACTIVATION_REQUIRED_COLUMNS, "rows")
    frame = rows.copy(deep=True).reset_index(drop=True)
    frame = frame.drop(
        columns=[column for column in _ACTIVATION_ADDED_COLUMNS if column in frame]
    )
    _validate_asset_ids(frame, "rows")
    frame["asset_id"] = frame["asset_id"].astype(str).str.strip()
    duplicate = frame["asset_id"].duplicated(keep=False)
    if duplicate.any():
        asset_id = frame.loc[duplicate, "asset_id"].sort_values(kind="stable").iloc[0]
        raise ValueError(f"rows contains duplicate asset_id {asset_id}")

    eligible_values: list[bool] = []
    for value, asset_id in zip(frame["eligible"], frame["asset_id"], strict=True):
        if not isinstance(value, (bool, np.bool_)):
            raise ValueError(
                f"rows asset {asset_id} field eligible must be a strict boolean"
            )
        eligible_values.append(bool(value))
    frame["eligible"] = eligible_values

    for field in _ACTIVATION_NUMERIC_FIELDS:
        frame[field] = [
            _activation_numeric_value(value, field=field, asset_id=asset_id)
            for value, asset_id in zip(
                frame[field], frame["asset_id"], strict=True
            )
        ]

    boolean_present = pd.DataFrame(index=frame.index)
    for field in _ACTIVATION_BOOLEAN_FIELDS:
        parsed = [
            _activation_boolean_value(value, field=field, asset_id=asset_id)
            for value, asset_id in zip(
                frame[field], frame["asset_id"], strict=True
            )
        ]
        frame[field] = [value for value, _ in parsed]
        boolean_present[field] = [present for _, present in parsed]

    expected_dates = [
        _activation_expected_date(value, asset_id=asset_id)
        for value, asset_id in zip(
            frame["expected_validation_date"], frame["asset_id"], strict=True
        )
    ]

    no_big_up_history = (
        frame["stock_character_coverage"] & frame["up_7pct_count_2y"].eq(0.0)
    )
    for field in _ACTIVATION_POST_EVENT_FIELDS:
        frame.loc[no_big_up_history & frame[field].isna(), field] = 0.0

    numeric_complete = frame[list(_ACTIVATION_NUMERIC_FIELDS)].notna().all(axis=1)
    coverage_flags = (
        frame["technical_feature_coverage"]
        & frame["residual_deviation_coverage"]
        & frame["stock_character_coverage"]
        & frame["market_capacity_coverage"]
    )
    component_coverage = (
        numeric_complete
        & boolean_present.all(axis=1)
        & coverage_flags
    ).astype(bool)
    activation_coverage = (frame["eligible"] & component_coverage).astype(bool)

    technical_scored = score_technical_readiness(
        frame,
        scoring_universe=activation_coverage,
    )
    for field in SCORE_COLUMNS:
        frame[field] = technical_scored[field]

    strong_move_score = _activation_percentile_mean(
        frame,
        ("limit_up_count_2y", "up_7pct_count_2y", "up_5pct_count_2y"),
        activation_coverage,
        winsorize_fields=(
            "limit_up_count_2y",
            "up_7pct_count_2y",
            "up_5pct_count_2y",
        ),
    )
    upside_tail_score = _activation_percentile_mean(
        frame,
        ("upside_tail_volatility_2y",),
        activation_coverage,
    )
    positive_rate_score = _activation_percentile_mean(
        frame,
        (
            "positive_after_big_up_1d_rate",
            "positive_after_big_up_3d_rate",
            "positive_after_big_up_5d_rate",
        ),
        activation_coverage,
    )
    cumulative_return_score = _activation_percentile_mean(
        frame,
        ("median_return_after_big_up_3d", "median_return_after_big_up_5d"),
        activation_coverage,
    )
    streak_retention_score = _activation_percentile_mean(
        frame,
        ("max_limit_up_streak_2y", "strong_move_retention_5d_rate"),
        activation_coverage,
    )
    frame["continuation_character_score"] = (
        0.20 * strong_move_score
        + 0.15 * upside_tail_score
        + 0.35 * positive_rate_score
        + 0.20 * cumulative_return_score
        + 0.10 * streak_retention_score
    ).where(activation_coverage)

    frame["residual_price_space_score"] = _activation_percentile_mean(
        frame,
        _ACTIVATION_RESIDUAL_FIELDS,
        activation_coverage,
        favorable_low=True,
    )

    float_cap_percentile = _activation_percentile(
        frame["log_current_float_market_cap"], activation_coverage
    )
    sweet_base = pd.Series(
        np.select(
            [float_cap_percentile.lt(15.0), float_cap_percentile.le(65.0)],
            [
                35.0 + 4.0 * float_cap_percentile,
                95.0,
            ],
            default=95.0 - (60.0 / 35.0) * (float_cap_percentile - 65.0),
        ),
        index=frame.index,
        dtype="float64",
    ).clip(lower=35.0, upper=95.0).where(activation_coverage)
    liquidity_percentiles = pd.DataFrame(
        {
            field: _activation_percentile(frame[field], activation_coverage)
            for field in (
                "average_amount_20d",
                "average_turnover_rate_20d",
                "amount_to_float_cap_20d",
            )
        },
        index=frame.index,
    )
    frame["capital_efficiency_score"] = pd.concat(
        [sweet_base.rename("sweet_base"), liquidity_percentiles], axis=1
    ).mean(axis=1, skipna=False).where(activation_coverage)

    verification_percentile = _activation_percentile(
        frame["catalyst_verifiability_score"], activation_coverage
    )
    trade_date = date.fromisoformat(config.trade_date)
    timing_window_values: list[float] = []
    for verifiability, expected_date in zip(
        frame["catalyst_verifiability_score"], expected_dates, strict=True
    ):
        if not math.isfinite(verifiability):
            timing_window_values.append(math.nan)
        elif verifiability <= 0.0:
            timing_window_values.append(0.0)
        elif expected_date is None:
            timing_window_values.append(20.0)
        else:
            future_days = (expected_date - trade_date).days
            if 0 < future_days <= 28:
                timing_window_values.append(100.0)
            elif future_days <= 84 and future_days > 0:
                timing_window_values.append(60.0)
            else:
                timing_window_values.append(20.0)
    timing_window_score = pd.Series(
        timing_window_values, index=frame.index, dtype="float64"
    )
    catalyst_timing_score = (
        0.50 * verification_percentile + 0.50 * timing_window_score
    ).where(activation_coverage)
    frame["catalyst_timing_score"] = catalyst_timing_score.mask(
        activation_coverage & frame["catalyst_verifiability_score"].le(0.0),
        0.0,
    )

    frame["activation_coverage"] = activation_coverage
    frame["activation_score"] = (
        config.technical_readiness_weight * frame["technical_readiness_score"]
        + config.continuation_character_weight
        * frame["continuation_character_score"]
        + config.residual_price_space_weight * frame["residual_price_space_score"]
        + config.capital_efficiency_weight * frame["capital_efficiency_score"]
        + config.catalyst_timing_weight * frame["catalyst_timing_score"]
    ).where(activation_coverage)

    covered_returns = frame["return_10d"].where(activation_coverage).dropna()
    return_90th = (
        float(covered_returns.quantile(0.90))
        if not covered_returns.empty
        else math.nan
    )
    frame["overextended"] = (
        activation_coverage
        & frame["return_10d"].ge(return_90th)
        & frame["rebound_from_low_60d"].ge(0.30)
        & frame["residual_price_space_score"].lt(25.0)
    ).astype(bool)
    frame["activation_eligible"] = (
        activation_coverage
        & frame["technical_readiness_score"].ge(
            config.v2_min_technical_readiness_score
        )
        & ~frame["falling_knife"]
        & ~frame["overextended"]
        & frame["market_capacity_coverage"]
    ).astype(bool)

    reason_values: list[str] = []
    for index in frame.index:
        if not bool(frame.at[index, "eligible"]):
            reason_values.append("")
            continue
        reasons: list[str] = []
        if not bool(frame.at[index, "activation_coverage"]):
            reasons.append("activation_coverage_incomplete")
        technical_score = frame.at[index, "technical_readiness_score"]
        if math.isfinite(technical_score) and (
            technical_score < config.v2_min_technical_readiness_score
        ):
            reasons.append("technical_readiness_below_threshold")
        if bool(frame.at[index, "falling_knife"]):
            reasons.append("falling_knife")
        if bool(frame.at[index, "overextended"]):
            reasons.append("overextended")
        if (
            bool(boolean_present.at[index, "market_capacity_coverage"])
            and not bool(frame.at[index, "market_capacity_coverage"])
        ):
            reasons.append("market_capacity_coverage_insufficient")
        reason_values.append("|".join(sorted(reasons)))
    frame["activation_exclusion_reasons"] = reason_values
    return frame.reset_index(drop=True)


def compute_technical_readiness_features(
    bars: pd.DataFrame,
    membership: pd.DataFrame,
    *,
    trade_date: object,
) -> pd.DataFrame:
    """Compute and score daily point-in-time technical readiness features.

    Full coverage requires 22 sessions: a 20-session return needs 21 closes,
    while evaluating all final three new-low observations needs 22 closes.
    """
    _require_columns(bars, BAR_COLUMNS, "bars")
    _require_columns(membership, MEMBERSHIP_COLUMNS, "membership")
    cutoff = _parse_cutoff(trade_date)

    frame = bars.loc[:, BAR_COLUMNS].copy().reset_index(drop=True)
    frame["trade_date"] = _parse_bar_dates(frame)
    frame = frame.loc[frame["trade_date"].le(cutoff)].copy()
    _validate_asset_ids(frame, "bars")
    frame["asset_id"] = frame["asset_id"].astype(str).str.strip()
    duplicate = frame.duplicated(["asset_id", "trade_date"], keep=False)
    if duplicate.any():
        row = frame.loc[duplicate, ["asset_id", "trade_date"]].sort_values(
            ["asset_id", "trade_date"], kind="stable"
        ).iloc[0]
        raise ValueError(
            f"duplicate bar for asset {row['asset_id']} on "
            f"{row['trade_date'].date().isoformat()}"
        )
    _validate_numeric_bars(frame)
    frame = frame.sort_values(["asset_id", "trade_date"], kind="stable")

    members = _validate_membership(membership)
    histories = {
        asset_id: history
        for asset_id, history in frame.groupby("asset_id", sort=False)
    }
    rows: list[dict[str, object]] = []
    for member in members.itertuples(index=False):
        row = {"asset_id": member.asset_id}
        row.update(_raw_asset_features(histories.get(member.asset_id)))
        row["_consumer_subindustry"] = member.consumer_subindustry
        rows.append(row)

    if not rows:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    result = pd.DataFrame(rows)
    _add_relative_features(result)
    finite_values = result.loc[:, _TECHNICAL_VALUE_COLUMNS].apply(
        lambda column: pd.to_numeric(column, errors="coerce")
    )
    result["technical_feature_coverage"] = (
        result["_history_sessions"].ge(22)
        & finite_values.notna().all(axis=1)
        & np.isfinite(finite_values).all(axis=1)
    )
    scored = score_technical_readiness(result)
    return scored.loc[:, OUTPUT_COLUMNS].reset_index(drop=True)
