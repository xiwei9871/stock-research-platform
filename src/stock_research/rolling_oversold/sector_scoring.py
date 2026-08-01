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
)
_MISSING_SYSTEM = "__missing_sector_system__"
_MISSING_CODE = "__missing_sector_code__"


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
    result["close"] = pd.to_numeric(result.get("close"), errors="coerce")
    result["amount"] = pd.to_numeric(result.get("amount"), errors="coerce")
    for column in ("up_count", "down_count", "stock_count", "new_low_count", "dispersion_20d", *(_NUMERIC_COLUMNS[16:19])):
        if column in result:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    result["_usable_bar"] = (
        result["trade_date"].notna() & (result["trade_date"].dt.date <= anchor_date)
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
    if "start_date" in result:
        starts = pd.to_datetime(result["start_date"], errors="coerce")
        result = result.loc[starts.isna() | (starts.dt.date <= anchor_date)]
    if "end_date" in result:
        ends = pd.to_datetime(result["end_date"], errors="coerce")
        result = result.loc[ends.isna() | (ends.dt.date > anchor_date)]
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
    closes = sector["close"].dropna().to_numpy(dtype=float) if not sector.empty else np.array([], dtype=float)
    history = len(closes)
    amounts = sector["amount"].dropna().to_numpy(dtype=float) if not sector.empty else np.array([], dtype=float)
    features = {
        "sector_system": mapping["sector_system"], "sector_code": mapping["sector_code"],
        "sector_name": mapping["sector_name"], "sector_mapping_valid": mapping["valid"],
        "sector_mapping_reason": mapping["reason"],
        "data_cutoff_date": sector["trade_date"].max().date() if not sector.empty else pd.NaT,
        "membership_count": int(membership_count), "history_observations": history,
        "ret_5d": _return(closes, 5), "ret_10d": _return(closes, 10), "ret_20d": _return(closes, 20),
        "relative_ret_20d": _relative_return(_return(closes, 20), market_regime),
        "drawdown_60d": _drawdown(closes, 60), "drawdown_120d": _drawdown(closes, 120),
        "drawdown_252d": _drawdown(closes, 252), "price_position_252d": _position(closes, 252),
        "below_ma20_ratio": _breadth_or_price(sector, closes, 20),
        "below_ma60_ratio": _breadth_or_price(sector, closes, 60),
        "new_low_60d_ratio": _new_low_ratio(sector, closes), "up_ratio_20d": _up_ratio(sector, closes),
        "amount_ratio_5_20": _amount_ratio(amounts), "turnover_or_activity_score": float("nan"),
        "amount_20d": float(np.mean(amounts[-20:])) if len(amounts) else float("nan"),
        "dispersion_20d": _dispersion(sector, closes), "recent_recovery_ratio": _recovery(closes),
        "fundamental_quality_score": _optional_score(sector, "fundamental_quality_score"),
        "valuation_support_score": _optional_score(sector, "valuation_support_score"),
        "risk_concentration_score": _optional_score(sector, "risk_concentration_score"),
    }
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


def _return(values: np.ndarray, periods: int) -> float:
    if len(values) <= periods or values[-periods - 1] == 0:
        return float("nan")
    return float(values[-1] / values[-periods - 1] - 1.0)


def _drawdown(values: np.ndarray, window: int) -> float:
    subset = values[-window:]
    return float(subset[-1] / np.max(subset) - 1.0) if len(subset) and np.max(subset) > 0 else float("nan")


def _position(values: np.ndarray, window: int) -> float:
    subset = values[-window:]
    if not len(subset) or np.max(subset) == np.min(subset):
        return 1.0 if len(subset) else float("nan")
    return float((subset[-1] - np.min(subset)) / (np.max(subset) - np.min(subset)))


def _breadth_or_price(sector: pd.DataFrame, closes: np.ndarray, window: int) -> float:
    if "down_count" in sector and "stock_count" in sector:
        ratios = (sector["down_count"] / sector["stock_count"].replace(0, np.nan)).dropna()
        if len(ratios):
            return float(ratios.tail(window).mean())
    if len(closes) < 2:
        return float("nan")
    series = pd.Series(closes)
    return float((series < series.rolling(window, min_periods=1).mean()).tail(window).mean())


def _new_low_ratio(sector: pd.DataFrame, closes: np.ndarray) -> float:
    if "new_low_count" in sector and "stock_count" in sector:
        ratios = (sector["new_low_count"] / sector["stock_count"].replace(0, np.nan)).dropna()
        if len(ratios):
            return float(ratios.iloc[-1])
    return float(closes[-1] <= np.min(closes[-60:])) if len(closes) else float("nan")


def _up_ratio(sector: pd.DataFrame, closes: np.ndarray) -> float:
    if "up_count" in sector and "stock_count" in sector:
        ratios = (sector["up_count"] / sector["stock_count"].replace(0, np.nan)).dropna()
        if len(ratios):
            return float(ratios.tail(20).mean())
    if len(closes) < 2:
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
        *_NUMERIC_COLUMNS, "sector_recovery_state",
        "sector_gate_status",
    ]


def _empty_result() -> pd.DataFrame:
    return pd.DataFrame(columns=_output_columns())
