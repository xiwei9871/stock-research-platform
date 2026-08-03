"""Point-in-time sector scoring for the rolling oversold workflow."""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from .contracts import GateStatus, RecoveryState


_NUMERIC_COLUMNS = (
    "ret_5d", "ret_10d", "ret_20d", "relative_ret_20d", "drawdown_60d",
    "drawdown_120d", "drawdown_252d", "price_position_252d", "below_ma20_ratio",
    "below_ma60_ratio", "new_low_60d_ratio", "up_ratio_20d", "amount_ratio_5_20",
    "turnover_or_activity_score", "dispersion_20d", "recent_recovery_ratio",
    "fundamental_quality_score", "valuation_support_score", "risk_concentration_score",
    "sector_oversold_score", "sector_repairability_score", "sector_direction_score",
    "sector_low_close_20d", "sector_low_close_30d", "sector_low_close_60d",
    "sector_recovery_from_low_20d", "sector_recovery_from_low_30d",
    "sector_recovery_from_low_60d", "sector_days_since_low_20d",
    "sector_days_since_low_30d", "sector_days_since_low_60d", "sector_return_1d",
    "sector_return_3d", "sector_return_5d", "sector_return_10d", "sector_return_20d",
    "sector_ma5", "sector_ma10", "sector_ma20", "sector_ma5_slope_5d",
    "sector_ma10_slope_10d", "sector_amount_ratio_5_20", "sector_volume_ratio_5_20",
    "sector_up_ratio_1d", "sector_up_ratio_5d", "sector_up_ratio_20d",
    "sector_above_ma5_ratio", "sector_above_ma20_ratio", "sector_new_low_ratio_20d",
    "sector_new_low_ratio_60d", "sector_leader_return_1d", "sector_leader_return_3d",
    "sector_leader_return_5d", "sector_leader_breadth", "sector_dispersion_20d",
)
_MISSING_SYSTEM = "__missing_sector_system__"
_MISSING_CODE = "__missing_sector_code__"
_LOW_POINT_WINDOWS = (20, 30, 60)
_MIN_FEATURE_HISTORY = 6
_REQUIRED_REPAIR_FEATURE_COLUMNS = (
    "sector_low_close_20d",
    "sector_low_date_20d",
    "sector_recovery_from_low_20d",
    "sector_days_since_low_20d",
    "sector_volume_ratio_5_20",
    "sector_ma5_slope_5d",
    "sector_ma10_slope_10d",
)


def score_sector_states(
    sector_bars: pd.DataFrame,
    *,
    membership: pd.DataFrame,
    market_regime: dict[str, object],
    anchor_date: date,
) -> pd.DataFrame:
    """Return one frozen score row for each bar or membership sector at the cutoff."""

    if not isinstance(anchor_date, date):
        raise TypeError("anchor_date must be a date")
    if not isinstance(sector_bars, pd.DataFrame) or not isinstance(membership, pd.DataFrame):
        raise TypeError("sector_bars and membership must be pandas DataFrames")
    bars = _canonicalize(sector_bars, is_membership=False, anchor_date=anchor_date)
    members = _canonicalize(membership, is_membership=True, anchor_date=anchor_date)
    membership_counts = (
        members.groupby(_internal_key_columns(), dropna=False)["asset_id"].nunique().to_dict()
        if not members.empty else {}
    )
    anchor_bars = bars.loc[bars["_usable_bar"]] if not bars.empty else bars
    future_bars = bars.loc[~bars["_usable_bar"]] if not bars.empty else bars
    mapped = pd.concat([anchor_bars, members], ignore_index=True, sort=False)
    mapping_metadata = _mapping_metadata(mapped)
    future_metadata = _mapping_metadata(future_bars)
    for key, metadata in future_metadata.items():
        mapping_metadata.setdefault(key, metadata)
    bar_keys = (
        set(map(tuple, bars[_internal_key_columns()].drop_duplicates().to_numpy()))
        if not bars.empty else set()
    )
    member_keys = set(membership_counts)
    rows = [
        _score_one_sector(
            bars, key, membership_counts.get(key, 0), mapping_metadata[key], market_regime
        )
        for key in sorted(bar_keys | member_keys)
    ]
    result = pd.DataFrame(rows)
    if result.empty:
        return _empty_result()
    result["turnover_or_activity_score"] = _activity_scores(result)
    result = _finalize_scores_and_states(result, market_regime)
    return result[_output_columns()].sort_values(_key_columns(), kind="stable").reset_index(drop=True)


def _canonicalize(frame: pd.DataFrame, *, is_membership: bool, anchor_date: date) -> pd.DataFrame:
    result = frame.copy(deep=True)
    mappings = (
        ("industry_system", "industry_code", "industry_name"),
        ("concept_system", "concept_code", "concept_name"),
    )
    for canonical, index in zip(_key_columns() + ["sector_name"], range(3)):
        candidates = [mapping[index] for mapping in mappings if mapping[index] in result]
        fallback = result[candidates].bfill(axis=1).iloc[:, 0] if candidates else pd.Series(pd.NA, index=result.index)
        current = result[canonical] if canonical in result else pd.Series(pd.NA, index=result.index)
        current = current.astype("string").str.strip().replace("", pd.NA)
        result[canonical] = current.fillna(fallback)
    for column in _key_columns() + ["sector_name"]:
        result[column] = result[column].astype("string").str.strip().replace("", pd.NA)
    result["sector_mapping_reason"] = result.apply(_mapping_reason, axis=1)
    result["sector_mapping_valid"] = result["sector_mapping_reason"].eq("")
    result["_sector_key_system"] = result["sector_system"].fillna(_MISSING_SYSTEM)
    result["_sector_key_code"] = result["sector_code"].fillna(_MISSING_CODE)
    if is_membership:
        if "asset_id" not in result:
            result["asset_id"] = pd.NA
        result["asset_id"] = result["asset_id"].astype("string").str.strip()
        result = _active_membership(result, anchor_date)
        result = result.loc[result["asset_id"].notna()].copy()
        return result.sort_values(
            [*_internal_key_columns(), "asset_id", "sector_name"],
            kind="mergesort",
            na_position="first",
        )
    trade_dates = (
        result["trade_date"]
        if "trade_date" in result
        else pd.Series(pd.NaT, index=result.index, dtype="datetime64[ns]")
    )
    result["trade_date"] = pd.to_datetime(trade_dates, errors="coerce")
    result["close"] = pd.to_numeric(
        result.get("close", pd.Series(pd.NA, index=result.index)), errors="coerce"
    )
    result["amount"] = pd.to_numeric(
        result.get("amount", pd.Series(pd.NA, index=result.index)), errors="coerce"
    )
    result["volume"] = pd.to_numeric(
        result.get("volume", pd.Series(pd.NA, index=result.index)), errors="coerce"
    )
    for column in ("up_count", "down_count", "stock_count", "new_low_count", "dispersion_20d", *(_NUMERIC_COLUMNS[16:19])):
        if column in result:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    result["_usable_bar"] = (
        result["trade_date"].notna() & (result["trade_date"] <= pd.Timestamp(anchor_date))
    )
    duplicate_sort_columns = [
        column
        for column in (
            # Prefer the most informative optional score when duplicate
            # sector/date rows disagree.  The score must precede market fields
            # so a lower close/amount cannot override a higher-quality record.
            "fundamental_quality_score", "valuation_support_score", "risk_concentration_score",
            "sector_name", "close", "preclose", "high", "low", "amount", "volume",
            "up_count", "down_count", "stock_count", "new_low_count", "dispersion_20d",
        )
        if column in result
    ]
    result = result.sort_values(
        [*_internal_key_columns(), "trade_date", *duplicate_sort_columns],
        kind="mergesort",
        na_position="first",
    )
    # Keep one canonical row per sector/date after deterministic ordering.
    result = result.drop_duplicates([*_internal_key_columns(), "trade_date"], keep="last")
    return result.sort_values([*_internal_key_columns(), "trade_date"], kind="mergesort")


def _active_membership(frame: pd.DataFrame, anchor_date: date) -> pd.DataFrame:
    result = frame.copy()
    anchor_timestamp = pd.Timestamp(anchor_date)
    if "start_date" in result:
        starts = pd.to_datetime(result["start_date"], errors="coerce")
        result = result.loc[starts.isna() | (starts <= anchor_timestamp)]
    if "end_date" in result:
        ends = pd.to_datetime(result["end_date"], errors="coerce")
        result = result.loc[ends.isna() | (ends > anchor_timestamp)]
    return result


def _score_one_sector(
    bars: pd.DataFrame,
    key: tuple[str, str],
    membership_count: int,
    mapping: dict[str, object],
    market_regime: dict[str, object],
) -> dict[str, object]:
    all_sector_bars = (
        bars.loc[(bars[_internal_key_columns()] == list(key)).all(axis=1)].copy()
        if not bars.empty else bars
    )
    sector = all_sector_bars.loc[all_sector_bars["_usable_bar"]].copy() if not all_sector_bars.empty else all_sector_bars
    if not sector.empty:
        sector = sector.drop_duplicates("trade_date", keep="last")
    close_rows = (
        sector.loc[sector["trade_date"].notna()]
        if not sector.empty
        else sector
    )
    closes = (
        _numeric_series(close_rows["close"]).to_numpy(dtype=float)
        if not close_rows.empty
        else np.array([], dtype=float)
    )
    dates = (
        close_rows["trade_date"].tolist()
        if not close_rows.empty
        else []
    )
    history = len(closes)
    amounts = (
        sector["amount"].dropna().to_numpy(dtype=float)
        if not sector.empty
        else np.array([], dtype=float)
    )
    volumes = (
        _numeric_series(sector["volume"]).to_numpy(dtype=float)
        if not sector.empty and "volume" in sector
        else np.array([], dtype=float)
    )
    low_features = _low_point_features(closes, dates, windows=_LOW_POINT_WINDOWS)
    trend_features = _trend_features(closes, dates)
    volume_features = _volume_features(volumes, amounts)
    breadth_features = _breadth_features(sector)
    breadth_data_status = breadth_features.pop("_breadth_data_status", "ok")
    features = {
        "sector_system": mapping["sector_system"], "sector_code": mapping["sector_code"],
        "sector_name": mapping["sector_name"], "sector_mapping_valid": mapping["valid"],
        "sector_mapping_reason": mapping["reason"],
        "data_cutoff_date": sector["trade_date"].max().date() if not sector.empty else pd.NaT,
        "membership_count": int(membership_count), "history_observations": history,
        "ret_5d": trend_features["sector_return_5d"],
        "ret_10d": trend_features["sector_return_10d"],
        "ret_20d": trend_features["sector_return_20d"],
        "relative_ret_20d": _relative_return(_return(closes, 20), market_regime),
        "drawdown_60d": _drawdown(closes, 60), "drawdown_120d": _drawdown(closes, 120),
        "drawdown_252d": _drawdown(closes, 252), "price_position_252d": _position(closes, 252),
        "below_ma20_ratio": _breadth_or_price(sector, closes, 20),
        "below_ma60_ratio": _breadth_or_price(sector, closes, 60),
        "new_low_60d_ratio": _new_low_ratio(sector, closes), "up_ratio_20d": _up_ratio(sector, closes),
        "amount_ratio_5_20": volume_features["sector_amount_ratio_5_20"],
        "turnover_or_activity_score": float("nan"),
        "amount_20d": float(np.mean(amounts[-20:])) if len(amounts) else float("nan"),
        "dispersion_20d": breadth_features["sector_dispersion_20d"],
        "recent_recovery_ratio": low_features["sector_recovery_from_low_20d"],
        "fundamental_quality_score": _optional_score(sector, "fundamental_quality_score"),
        "valuation_support_score": _optional_score(sector, "valuation_support_score"),
        "risk_concentration_score": _optional_score(sector, "risk_concentration_score"),
    }
    features.update(low_features)
    features.update(trend_features)
    features.update(volume_features)
    features.update(breadth_features)
    features["sector_feature_data_status"] = _feature_data_status(
        features,
        history_observations=history,
        breadth_data_status=breadth_data_status,
    )
    return features


def _activity_scores(result: pd.DataFrame) -> pd.Series:
    size = result["amount_20d"].copy()
    usable = size.notna()
    scores = pd.Series(float("nan"), index=result.index, dtype="float64")
    if usable.any():
        size_ranks = _percentile_ranks(size[usable])
        ratio_ranks = _percentile_ranks(result.loc[usable, "amount_ratio_5_20"])
        scores.loc[usable] = size_ranks * 0.60 + ratio_ranks.reindex(size_ranks.index).fillna(50.0) * 0.40
    return scores


def _finalize_scores_and_states(result: pd.DataFrame, market_regime: dict[str, object]) -> pd.DataFrame:
    for column in _NUMERIC_COLUMNS:
        if column not in result:
            result[column] = float("nan")
    dd = result["drawdown_60d"]
    pos = result["price_position_252d"]
    result["sector_oversold_score"] = _weighted_score(
        result,
        ((dd.abs() / 0.15 * 100.0, 0.65), ((1.0 - pos) / 0.25 * 100.0, 0.15),
         (result["below_ma20_ratio"] * 100.0, 0.15), (result["new_low_60d_ratio"] * 100.0, 0.05)),
    )
    direction = (
        50.0
        + result["recent_recovery_ratio"].fillna(0.0) * 1000.0
        + result["ret_5d"].fillna(0.0) * 80.0
        + (result["price_position_252d"].fillna(0.5) - 0.5) * 20.0
    )
    regime = str(market_regime.get("market_regime", "neutral"))
    direction += {"risk_on": 5.0, "risk_off": -10.0, "panic_rebound_watch": -3.0}.get(regime, 0.0)
    result["sector_direction_score"] = direction.clip(0.0, 100.0)
    recovery_component = (result["recent_recovery_ratio"] / 0.03 * 100.0).clip(0.0, 100.0)
    result["sector_repairability_score"] = _weighted_score(
        result,
        ((recovery_component, 0.65), (result["up_ratio_20d"] * 100.0, 0.20),
         (result["sector_direction_score"], 0.15)),
    )
    insufficient_history = result["history_observations"] < 6
    invalid_mapping = ~result["sector_mapping_valid"].astype(bool)
    result.loc[
        insufficient_history | invalid_mapping,
        ["sector_oversold_score", "sector_repairability_score", "sector_direction_score"],
    ] = float("nan")
    result["sector_recovery_state"] = result.apply(_recovery_state, axis=1)
    result["sector_gate_status"] = result.apply(lambda row: _gate_status(row, regime), axis=1)
    result["sector_research_eligibility"] = result.apply(_research_eligibility, axis=1)
    return result


def _recovery_state(row: pd.Series) -> str:
    if not row["sector_mapping_valid"] or row["history_observations"] < 6:
        return RecoveryState.UNKNOWN.value
    if row["price_position_252d"] >= 0.95 or (
        row["recent_recovery_ratio"] >= 0.05 and row["drawdown_60d"] > -0.05
    ):
        return RecoveryState.REPAIRED.value
    if row["sector_direction_score"] < 30.0 and row["fundamental_quality_score"] < 40.0:
        return RecoveryState.STRUCTURALLY_WEAK.value
    if row["drawdown_60d"] <= -0.10 and row["recent_recovery_ratio"] >= 0.015:
        return RecoveryState.REPAIRING.value
    if row["drawdown_60d"] <= -0.10:
        return RecoveryState.FRESH_OVERSOLD.value
    return RecoveryState.UNKNOWN.value


def _gate_status(row: pd.Series, regime: str) -> str:
    if not row["sector_mapping_valid"] or row["membership_count"] == 0 or row["history_observations"] < 6:
        return GateStatus.BLOCKED.value
    if row["sector_recovery_state"] in {RecoveryState.REPAIRED.value, RecoveryState.STRUCTURALLY_WEAK.value, RecoveryState.UNKNOWN.value}:
        return GateStatus.WATCH.value
    repair_threshold, direction_threshold = (65.0, 50.0) if regime == "risk_off" else (60.0, 45.0)
    if (
        row["sector_recovery_state"] == RecoveryState.REPAIRING.value
        and row["sector_oversold_score"] >= 70.0
        and row["sector_repairability_score"] >= repair_threshold
        and row["sector_direction_score"] >= direction_threshold
    ):
        return GateStatus.CONFIRMED.value
    return GateStatus.WATCH.value


def _research_eligibility(row: pd.Series) -> str:
    """Map the legacy gate to the explicit research visibility status.

    Task 3 may refine this policy.  For now, preserve the legacy gate semantics
    while distinguishing data blockage from an ordinary watch row.
    """

    if (
        not bool(row.get("sector_mapping_valid", False))
        or int(row.get("history_observations", 0) or 0) < _MIN_FEATURE_HISTORY
        or int(row.get("membership_count", 0) or 0) == 0
        or row.get("sector_feature_data_status") != "ok"
        or any(pd.isna(row.get(column)) for column in _REQUIRED_REPAIR_FEATURE_COLUMNS)
    ):
        return "blocked_data"
    if row.get("sector_gate_status") == GateStatus.CONFIRMED.value:
        return "eligible"
    return "watch"


def _feature_data_status(
    features: dict[str, object],
    *,
    history_observations: int,
    breadth_data_status: str = "ok",
) -> str:
    """Classify whether required repair features are publishable at this cutoff."""

    if pd.isna(features.get("sector_volume_ratio_5_20")):
        return "missing_volume"
    if breadth_data_status != "ok":
        return breadth_data_status
    if any(
        pd.isna(features.get(column)) for column in _REQUIRED_REPAIR_FEATURE_COLUMNS
    ):
        return "insufficient_history" if history_observations < 20 else "missing_feature_data"
    return "ok"


def _low_point_features(
    closes: object,
    dates: object,
    windows: tuple[int, ...] = _LOW_POINT_WINDOWS,
) -> dict[str, object]:
    """Return recent-low levels, dates, recovery, and trading-day distance.

    A complete six-observation sector history is the minimum needed for a
    research feature row.  Longer named windows intentionally use the available
    point-in-time history when a synthetic or newly listed sector has fewer than
    the nominal 20/30/60 sessions.
    """

    result: dict[str, object] = {}
    for window in windows:
        result.update(
            {
                f"sector_low_close_{window}d": float("nan"),
                f"sector_low_date_{window}d": pd.NaT,
                f"sector_recovery_from_low_{window}d": float("nan"),
                f"sector_days_since_low_{window}d": float("nan"),
            }
        )
    close_values = _numeric_series(closes)
    date_values = _date_array(dates)
    length = min(len(close_values), len(date_values))
    if length < _MIN_FEATURE_HISTORY:
        return result
    frame = pd.DataFrame(
        {
            "close": close_values.iloc[:length].to_numpy(dtype=float),
            "trade_date": date_values[:length],
        }
    )
    if len(frame) < _MIN_FEATURE_HISTORY:
        return result
    frame = frame.sort_values("trade_date", kind="mergesort").reset_index(drop=True)
    for window in windows:
        subset = frame.tail(int(window)).reset_index(drop=True)
        if (
            len(subset) < _MIN_FEATURE_HISTORY
            or subset["close"].isna().any()
            or subset["trade_date"].isna().any()
        ):
            continue
        latest_close = float(subset["close"].iloc[-1])
        low_value = float(subset["close"].min())
        # “Recent low” means the latest occurrence when equal lows repeat.
        low_positions = np.flatnonzero(np.isclose(subset["close"].to_numpy(), low_value))
        low_position = int(low_positions[-1]) if len(low_positions) else 0
        low_date = pd.Timestamp(subset["trade_date"].iloc[low_position]).date()
        result[f"sector_low_close_{window}d"] = low_value
        result[f"sector_low_date_{window}d"] = low_date.isoformat()
        result[f"sector_recovery_from_low_{window}d"] = (
            latest_close / low_value - 1.0 if low_value > 0 else float("nan")
        )
        result[f"sector_days_since_low_{window}d"] = float(
            len(subset) - 1 - low_position
        )
    return result


def _trend_features(closes: object, dates: object) -> dict[str, object]:
    """Return point-in-time returns, moving averages, and trend states."""

    result: dict[str, object] = {
        f"sector_return_{period}d": float("nan")
        for period in (1, 3, 5, 10, 20)
    }
    result.update(
        {
            "sector_ma5": float("nan"),
            "sector_ma10": float("nan"),
            "sector_ma20": float("nan"),
            "sector_ma5_slope_5d": float("nan"),
            "sector_ma10_slope_10d": float("nan"),
            "sector_ma5_cross_ma10": pd.NA,
            "sector_close_above_ma5": np.nan,
            "sector_close_above_ma20": np.nan,
        }
    )
    values = _numeric_series(closes).to_numpy(dtype=float)
    if len(values) < _MIN_FEATURE_HISTORY:
        return result
    for period in (1, 3, 5, 10, 20):
        result[f"sector_return_{period}d"] = _return(values, period)
    series = pd.Series(values, dtype="float64")
    moving = {
        window: _moving_average_value(values, window)
        for window in (5, 10, 20)
    }
    result["sector_ma5"] = moving[5]
    result["sector_ma10"] = moving[10]
    result["sector_ma20"] = moving[20]
    result["sector_ma5_slope_5d"] = _moving_average_slope(values, 5, 5)
    result["sector_ma10_slope_10d"] = _moving_average_slope(values, 10, 10)
    latest = float(series.iloc[-1])
    if np.isfinite(latest) and np.isfinite(moving[5]):
        result["sector_close_above_ma5"] = bool(latest > moving[5])
    if np.isfinite(latest) and np.isfinite(moving[20]):
        result["sector_close_above_ma20"] = bool(latest > moving[20])
    if np.isfinite(moving[5]) and np.isfinite(moving[10]):
        previous_ma5 = _moving_average_value(values, 5, offset=1)
        previous_ma10 = _moving_average_value(values, 10, offset=1)
        if np.isfinite(previous_ma5) and np.isfinite(previous_ma10):
            if moving[5] > moving[10] and previous_ma5 <= previous_ma10:
                result["sector_ma5_cross_ma10"] = "golden_cross"
            elif moving[5] < moving[10] and previous_ma5 >= previous_ma10:
                result["sector_ma5_cross_ma10"] = "death_cross"
            elif moving[5] > moving[10]:
                result["sector_ma5_cross_ma10"] = "above"
            elif moving[5] < moving[10]:
                result["sector_ma5_cross_ma10"] = "below"
            else:
                result["sector_ma5_cross_ma10"] = "flat"
    return result


def _volume_features(volume: object, amount: object) -> dict[str, float]:
    """Return independent 5/20 volume and amount ratios."""

    return {
        "sector_volume_ratio_5_20": _volume_ratio_5_20(volume),
        "sector_amount_ratio_5_20": _ratio_5_20(_numeric_array(amount)),
    }


def _breadth_features(sector_frame: pd.DataFrame) -> dict[str, object]:
    """Derive available breadth fields without inventing missing constituents."""

    result: dict[str, object] = {
        "sector_up_ratio_1d": float("nan"),
        "sector_up_ratio_5d": float("nan"),
        "sector_up_ratio_20d": float("nan"),
        "sector_above_ma5_ratio": float("nan"),
        "sector_above_ma20_ratio": float("nan"),
        "sector_new_low_ratio_20d": float("nan"),
        "sector_new_low_ratio_60d": float("nan"),
        "sector_leader_return_1d": float("nan"),
        "sector_leader_return_3d": float("nan"),
        "sector_leader_return_5d": float("nan"),
        "sector_leader_breadth": float("nan"),
        "sector_dispersion_20d": float("nan"),
        "_breadth_data_status": "ok",
    }
    if not isinstance(sector_frame, pd.DataFrame) or sector_frame.empty:
        result["_breadth_data_status"] = "insufficient_history"
        return result
    frame = (
        sector_frame.sort_values("trade_date", kind="mergesort")
        if "trade_date" in sector_frame
        else sector_frame.copy(deep=True)
    )
    closes = _numeric_series(frame.get("close", []))
    if len(closes) < _MIN_FEATURE_HISTORY:
        result["_breadth_data_status"] = "insufficient_history"
        return result
    if closes.tail(min(20, len(closes))).isna().any() or pd.isna(closes.iloc[-1]):
        result["_breadth_data_status"] = "missing_feature_data"
        return result

    breadth_status = "ok"
    count_windows: dict[str, tuple[bool, pd.Series, bool]] = {}
    for column in ("up_count", "down_count", "new_low_count"):
        count_windows[column] = _count_window_ratio(frame, column, window=20)
        present, _, complete = count_windows[column]
        if present and not complete:
            breadth_status = "missing_feature_data"

    daily_up = np.diff(closes.to_numpy(dtype=float)) > 0
    has_up_counts, count_ratio, up_complete = count_windows["up_count"]
    if has_up_counts and up_complete:
        result["sector_up_ratio_1d"] = float(count_ratio.iloc[-1])
        result["sector_up_ratio_5d"] = float(count_ratio.tail(5).mean())
        result["sector_up_ratio_20d"] = float(count_ratio.tail(20).mean())
    elif not has_up_counts:
        result["sector_up_ratio_1d"] = float(daily_up[-1])
        result["sector_up_ratio_5d"] = float(np.mean(daily_up[-5:]))
        result["sector_up_ratio_20d"] = float(np.mean(daily_up[-20:]))

    for window, output in ((5, "sector_above_ma5_ratio"), (20, "sector_above_ma20_ratio")):
        if len(closes) >= window:
            moving = closes.rolling(window, min_periods=window).mean()
            valid = (closes > moving).dropna()
            if not valid.empty:
                result[output] = float(valid.tail(20).mean())
    for window, output in ((20, "sector_new_low_ratio_20d"), (60, "sector_new_low_ratio_60d")):
        has_new_low_counts, count_ratio, new_low_complete = count_windows["new_low_count"]
        if has_new_low_counts and new_low_complete:
            result[output] = float(count_ratio.tail(window).mean())
        elif not has_new_low_counts:
            result[output] = float(
                closes.iloc[-1] <= np.min(closes.to_numpy(dtype=float)[-window:])
            )

    for period in (1, 3, 5):
        leader_columns = (
            f"leader_return_{period}d",
            f"sector_leader_return_{period}d",
            f"top_return_{period}d",
        )
        result[f"sector_leader_return_{period}d"] = _last_optional_feature(
            frame, leader_columns
        )
        if any(column in frame for column in leader_columns) and pd.isna(
            result[f"sector_leader_return_{period}d"]
        ):
            breadth_status = "missing_feature_data"
    result["sector_leader_breadth"] = _last_optional_feature(
        frame, ("leader_breadth", "sector_leader_breadth")
    )
    if any(column in frame for column in ("leader_breadth", "sector_leader_breadth")) and pd.isna(
        result["sector_leader_breadth"]
    ):
        breadth_status = "missing_feature_data"
    if (
        pd.isna(result["sector_leader_breadth"])
        and "leader_count" in frame
        and "stock_count" in frame
    ):
        leader_count = pd.to_numeric(frame["leader_count"], errors="coerce")
        stock_count = pd.to_numeric(frame["stock_count"], errors="coerce")
        ratio = leader_count / stock_count.replace(0, np.nan)
        if not ratio.empty and pd.notna(ratio.iloc[-1]):
            result["sector_leader_breadth"] = float(ratio.iloc[-1])
        else:
            breadth_status = "missing_feature_data"

    if "dispersion_20d" in frame:
        supplied_dispersion = pd.to_numeric(frame["dispersion_20d"], errors="coerce")
        dispersion_window = supplied_dispersion.tail(min(20, len(supplied_dispersion)))
        if not dispersion_window.empty and not dispersion_window.isna().any():
            result["sector_dispersion_20d"] = float(dispersion_window.mean())
        else:
            breadth_status = "missing_feature_data"
    elif len(closes) >= 3:
        close_values = closes.to_numpy(dtype=float)
        returns = np.diff(close_values[-20:]) / close_values[-20:-1]
        result["sector_dispersion_20d"] = (
            float(np.std(returns)) if len(returns) else float("nan")
        )
    result["_breadth_data_status"] = breadth_status
    return result


def _numeric_array(values: object) -> np.ndarray:
    if values is None:
        return np.array([], dtype=float)
    if isinstance(values, pd.Series):
        numeric = pd.to_numeric(values, errors="coerce")
    else:
        numeric = pd.to_numeric(pd.Series(values), errors="coerce")
    return numeric.dropna().to_numpy(dtype=float)


def _numeric_series(values: object) -> pd.Series:
    if values is None:
        return pd.Series(dtype="float64")
    if isinstance(values, pd.Series):
        return pd.to_numeric(values, errors="coerce").reset_index(drop=True)
    return pd.to_numeric(pd.Series(values), errors="coerce").reset_index(drop=True)


def _date_array(values: object) -> pd.Series:
    if values is None:
        return pd.Series(dtype="datetime64[ns]")
    if isinstance(values, pd.Series):
        dates = pd.to_datetime(values, errors="coerce")
    else:
        dates = pd.to_datetime(pd.Series(values), errors="coerce")
    return dates.reset_index(drop=True)


def _moving_average_value(values: np.ndarray, window: int, *, offset: int = 0) -> float:
    end = len(values) - offset
    start = end - window
    if start < 0 or end <= 0:
        return float("nan")
    subset = values[start:end]
    return float(np.mean(subset)) if len(subset) == window else float("nan")


def _moving_average_slope(values: np.ndarray, window: int, lookback: int) -> float:
    current = _moving_average_value(values, window)
    previous = _moving_average_value(values, window, offset=lookback)
    if not np.isfinite(current) or not np.isfinite(previous) or previous == 0:
        return float("nan")
    return float(current / previous - 1.0)


def _ratio_5_20(values: np.ndarray) -> float:
    if len(values) < _MIN_FEATURE_HISTORY:
        return float("nan")
    recent = float(np.mean(values[-5:]))
    baseline = float(np.mean(values[-20:]))
    return float(recent / baseline) if baseline else float("nan")


def _volume_ratio_5_20(values: object) -> float:
    """Return a volume ratio only when both windows are fully observed.

    With six to nineteen observations, ``tail(20)`` is the available history
    rather than an invented twenty-session baseline; any missing value in that
    available baseline still makes the ratio unavailable.
    """

    series = _numeric_series(values)
    if len(series) < _MIN_FEATURE_HISTORY:
        return float("nan")
    recent = series.tail(5)
    baseline = series.tail(20)
    if recent.isna().any() or baseline.isna().any():
        return float("nan")
    recent_mean = float(recent.mean())
    baseline_mean = float(baseline.mean())
    return float(recent_mean / baseline_mean) if baseline_mean else float("nan")


def _count_ratio(frame: pd.DataFrame, numerator_column: str) -> pd.Series | None:
    if numerator_column not in frame or "stock_count" not in frame:
        return None
    numerator = pd.to_numeric(frame[numerator_column], errors="coerce")
    denominator = pd.to_numeric(frame["stock_count"], errors="coerce").replace(0, np.nan)
    ratio = numerator / denominator
    return ratio if not ratio.empty and pd.notna(ratio.iloc[-1]) else None


def _count_window_ratio(
    frame: pd.DataFrame, numerator_column: str, *, window: int
) -> tuple[bool, pd.Series, bool]:
    if numerator_column not in frame or "stock_count" not in frame:
        return False, pd.Series(dtype="float64"), False
    numerator = pd.to_numeric(frame[numerator_column], errors="coerce")
    denominator = pd.to_numeric(frame["stock_count"], errors="coerce").replace(0, np.nan)
    ratio = numerator / denominator
    recent = ratio.tail(min(window, len(ratio)))
    return True, ratio, bool(not recent.empty and not recent.isna().any())


def _last_optional_feature(frame: pd.DataFrame, columns: tuple[str, ...]) -> float:
    for column in columns:
        if column not in frame:
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        recent = values.tail(min(20, len(values)))
        if not recent.empty and not recent.isna().any():
            return float(recent.iloc[-1])
        return float("nan")
    return float("nan")


def _return(values: np.ndarray, periods: int) -> float:
    if len(values) <= periods:
        return float("nan")
    subset = values[-periods - 1 :]
    if not np.isfinite(subset).all() or subset[0] == 0:
        return float("nan")
    return float(subset[-1] / subset[0] - 1.0)


def _drawdown(values: np.ndarray, window: int) -> float:
    subset = values[-window:]
    if not len(subset) or not np.isfinite(subset).all() or np.max(subset) <= 0:
        return float("nan")
    return float(subset[-1] / np.max(subset) - 1.0)


def _position(values: np.ndarray, window: int) -> float:
    subset = values[-window:]
    if not len(subset) or not np.isfinite(subset).all():
        return float("nan")
    if np.max(subset) == np.min(subset):
        return 1.0 if len(subset) else float("nan")
    return float((subset[-1] - np.min(subset)) / (np.max(subset) - np.min(subset)))


def _breadth_or_price(sector: pd.DataFrame, closes: np.ndarray, window: int) -> float:
    has_counts = {"down_count", "stock_count"}.issubset(sector.columns)
    if has_counts:
        _, ratios, complete = _count_window_ratio(sector, "down_count", window=window)
        if complete:
            return float(ratios.tail(window).mean())
        return float("nan")
    if len(closes) < _MIN_FEATURE_HISTORY or not np.isfinite(closes).all():
        return float("nan")
    series = pd.Series(closes)
    return float((series < series.rolling(window, min_periods=1).mean()).tail(window).mean())


def _new_low_ratio(sector: pd.DataFrame, closes: np.ndarray) -> float:
    has_counts = {"new_low_count", "stock_count"}.issubset(sector.columns)
    if has_counts:
        _, ratios, complete = _count_window_ratio(sector, "new_low_count", window=60)
        return float(ratios.iloc[-1]) if complete else float("nan")
    if len(closes) < _MIN_FEATURE_HISTORY or not np.isfinite(closes).all():
        return float("nan")
    return float(closes[-1] <= np.min(closes[-60:]))


def _up_ratio(sector: pd.DataFrame, closes: np.ndarray) -> float:
    has_counts = {"up_count", "stock_count"}.issubset(sector.columns)
    if has_counts:
        _, ratios, complete = _count_window_ratio(sector, "up_count", window=20)
        if complete:
            return float(ratios.tail(20).mean())
        return float("nan")
    if len(closes) < _MIN_FEATURE_HISTORY or not np.isfinite(closes).all():
        return float("nan")
    return float((np.diff(closes[-20:]) > 0).mean())


def _amount_ratio(amounts: np.ndarray) -> float:
    if len(amounts) < 6:
        return float("nan")
    baseline = np.mean(amounts[-20:])
    return float(np.mean(amounts[-5:]) / baseline) if baseline else float("nan")


def _dispersion(sector: pd.DataFrame, closes: np.ndarray) -> float:
    if "dispersion_20d" in sector and sector["dispersion_20d"].notna().any():
        return float(sector["dispersion_20d"].dropna().tail(20).mean())
    if len(closes) < 3:
        return float("nan")
    returns = np.diff(closes[-20:]) / closes[-20:-1]
    return float(np.std(returns)) if len(returns) else float("nan")


def _recovery(closes: np.ndarray) -> float:
    subset = closes[-20:]
    return float(subset[-1] / np.min(subset) - 1.0) if len(subset) and np.min(subset) > 0 else float("nan")


def _optional_score(sector: pd.DataFrame, column: str) -> float:
    if column not in sector or sector[column].dropna().empty:
        return 50.0
    return float(np.clip(sector[column].dropna().iloc[-1], 0.0, 100.0))


def _relative_return(value: float, market_regime: dict[str, object]) -> float:
    benchmark = market_regime.get("index_return_20d", market_regime.get("market_return_20d"))
    benchmark_value = pd.to_numeric(pd.Series([benchmark]), errors="coerce").iloc[0]
    return float(value - benchmark_value) if pd.notna(value) and pd.notna(benchmark_value) else float("nan")


def _weighted_score(frame: pd.DataFrame, components: tuple[tuple[pd.Series, float], ...]) -> pd.Series:
    numerator = pd.Series(0.0, index=frame.index)
    denominator = pd.Series(0.0, index=frame.index)
    for values, weight in components:
        valid = values.notna()
        numerator.loc[valid] += values.loc[valid].clip(0.0, 100.0) * weight
        denominator.loc[valid] += weight
    return (numerator / denominator.replace(0.0, np.nan)).clip(0.0, 100.0)


def _mapping_reason(row: pd.Series) -> str:
    missing = [
        f"missing_{column}"
        for column in (*_key_columns(), "sector_name")
        if pd.isna(row[column])
    ]
    return "|".join(missing)


def _mapping_metadata(frame: pd.DataFrame) -> dict[tuple[str, str], dict[str, object]]:
    metadata: dict[tuple[str, str], dict[str, object]] = {}
    for key, group in frame.groupby(_internal_key_columns(), dropna=False, sort=False):
        reasons = list(dict.fromkeys(reason for reason in group["sector_mapping_reason"] if reason))
        metadata[key] = {
            column: _last_known(group[column])
            for column in (*_key_columns(), "sector_name")
        }
        metadata[key]["valid"] = bool(group["sector_mapping_valid"].all())
        metadata[key]["reason"] = ";".join(reasons)
    return metadata


def _last_known(values: pd.Series) -> object:
    known = values.dropna()
    return known.iloc[-1] if not known.empty else pd.NA


def _percentile_ranks(values: pd.Series) -> pd.Series:
    valid = values.dropna()
    if valid.empty:
        return pd.Series(dtype="float64")
    if len(valid) == 1:
        return pd.Series(50.0, index=valid.index, dtype="float64")
    clipped = valid.clip(valid.quantile(0.05), valid.quantile(0.95))
    return clipped.rank(method="average", pct=True) * 100.0


def _key_columns() -> list[str]:
    return ["sector_system", "sector_code"]


def _internal_key_columns() -> list[str]:
    return ["_sector_key_system", "_sector_key_code"]


def _output_columns() -> list[str]:
    return [
        "sector_system", "sector_code", "sector_name", "data_cutoff_date", "membership_count",
        "history_observations", "sector_mapping_valid", "sector_mapping_reason", "amount_20d",
        *_NUMERIC_COLUMNS,
        "sector_low_date_20d", "sector_low_date_30d", "sector_low_date_60d",
        "sector_ma5_cross_ma10", "sector_close_above_ma5", "sector_close_above_ma20",
        "sector_research_eligibility", "sector_feature_data_status", "sector_recovery_state",
        "sector_gate_status",
    ]


def _empty_result() -> pd.DataFrame:
    return pd.DataFrame(columns=_output_columns())
