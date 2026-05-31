from __future__ import annotations

from typing import Any

import pandas as pd


ANALYTICS_GROUP_LEVELS = ["decision_label", "source_context", "review_session_id", "asset_id"]
DEFAULT_ANALYTICS_HORIZONS = [1, 3, 5, 10, 20, 60]


def build_decision_outcome_analytics_from_frames(
    *,
    outcome_events: pd.DataFrame,
    horizons: list[int] | None = None,
) -> pd.DataFrame:
    selected_horizons = _selected_horizons(horizons)
    normalized = _normalize_outcomes(outcome_events, selected_horizons)
    columns = _analytics_columns(selected_horizons)
    if normalized.empty:
        return pd.DataFrame(columns=columns)

    frames = [
        _analytics_frame(
            normalized,
            group_column=group_column,
            analytics_level=group_column,
            horizons=selected_horizons,
        )
        for group_column in ANALYTICS_GROUP_LEVELS
    ]
    result = pd.concat(frames, ignore_index=True)
    for column in columns:
        if column not in result.columns:
            result[column] = pd.NA
    return result.loc[:, columns]


def build_decision_outcome_analytics(
    *,
    start_date: str,
    end_date: str,
    outcome_events: pd.DataFrame,
    horizons: list[int] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    selected_horizons = _selected_horizons(horizons)
    groups = build_decision_outcome_analytics_from_frames(
        outcome_events=outcome_events,
        horizons=selected_horizons,
    )
    source_count = int(len(outcome_events))
    return {
        "run_id": run_id or f"p9-outcome-analytics-{start_date}-{end_date}",
        "review_start_date": str(start_date),
        "review_end_date": str(end_date),
        "status": "analytics_ready" if source_count else "no_outcomes_recorded",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "horizons": selected_horizons,
        "source_outcome_count": source_count,
        "group_count": int(len(groups)),
        "groups": _records(groups),
    }


def _normalize_outcomes(outcomes: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    normalized = outcomes.copy()
    for column in [
        "decision_label",
        "source_context",
        "review_session_id",
        "asset_id",
        "outcome_status",
        "manual_review_required",
        "auto_trade_enabled",
        "metadata",
    ]:
        if column not in normalized.columns:
            normalized[column] = pd.NA
    if normalized.empty:
        return normalized

    if normalized["auto_trade_enabled"].map(_bool_value).eq(True).any():
        raise ValueError("auto_trade_not_allowed")
    if normalized["manual_review_required"].map(_bool_value).ne(True).any():
        raise ValueError("manual_review_required")

    for column in ["decision_label", "source_context", "review_session_id", "asset_id", "outcome_status"]:
        normalized[column] = normalized[column].fillna("").astype(str)
    normalized["requires_follow_up"] = normalized.apply(_requires_follow_up, axis=1)
    normalized["is_complete"] = normalized["outcome_status"].eq("complete")
    normalized["is_insufficient_data"] = normalized["outcome_status"].eq("insufficient_data")

    for horizon in horizons:
        normalized[f"forward_{horizon}d_return"] = normalized.apply(
            lambda row: _metric_value(row, "forward_returns", f"forward_{horizon}d_return", horizon),
            axis=1,
        )
        normalized[f"max_high_return_{horizon}d"] = normalized.apply(
            lambda row: _metric_value(row, "max_high_returns", f"max_high_return_{horizon}d", horizon),
            axis=1,
        )
        normalized[f"max_low_drawdown_{horizon}d"] = normalized.apply(
            lambda row: _metric_value(row, "max_low_drawdowns", f"max_low_drawdown_{horizon}d", horizon),
            axis=1,
        )
        for column in [
            f"forward_{horizon}d_return",
            f"max_high_return_{horizon}d",
            f"max_low_drawdown_{horizon}d",
        ]:
            normalized.loc[~normalized["is_complete"], column] = pd.NA
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    return normalized


def _analytics_frame(
    outcomes: pd.DataFrame,
    *,
    group_column: str,
    analytics_level: str,
    horizons: list[int],
) -> pd.DataFrame:
    grouped = outcomes.groupby(group_column, dropna=False, sort=True)
    result = grouped.size().reset_index(name="sample_count")
    complete = (
        outcomes[outcomes["is_complete"]]
        .groupby(group_column, dropna=False)
        .size()
        .reset_index(name="complete_count")
    )
    insufficient = (
        outcomes[outcomes["is_insufficient_data"]]
        .groupby(group_column, dropna=False)
        .size()
        .reset_index(name="insufficient_data_count")
    )
    follow_up = grouped["requires_follow_up"].mean().reset_index(name="follow_up_required_rate")
    result = result.merge(complete, on=group_column, how="left")
    result = result.merge(insufficient, on=group_column, how="left")
    result = result.merge(follow_up, on=group_column, how="left")
    result.insert(0, "analytics_level", analytics_level)
    result["complete_count"] = result["complete_count"].fillna(0).astype(int)
    result["insufficient_data_count"] = result["insufficient_data_count"].fillna(0).astype(int)

    complete_rows = outcomes[outcomes["is_complete"]].copy()
    for horizon in horizons:
        forward = f"forward_{horizon}d_return"
        max_high = f"max_high_return_{horizon}d"
        max_low = f"max_low_drawdown_{horizon}d"
        stats = grouped_complete_stats(complete_rows, group_column, forward, max_high, max_low, horizon)
        result = result.merge(stats, on=group_column, how="left")

    for column in ANALYTICS_GROUP_LEVELS:
        if column not in result.columns:
            result[column] = ""
    if group_column in result.columns:
        result[group_column] = result[group_column].fillna("").astype(str)
    return result


def grouped_complete_stats(
    complete_rows: pd.DataFrame,
    group_column: str,
    forward: str,
    max_high: str,
    max_low: str,
    horizon: int,
) -> pd.DataFrame:
    if complete_rows.empty:
        return pd.DataFrame(columns=[group_column, *_metric_columns_for_horizon(horizon)])
    grouped = complete_rows.groupby(group_column, dropna=False, sort=True)
    stats = grouped.agg(
        **{
            f"forward_{horizon}d_return_mean": (forward, "mean"),
            f"forward_{horizon}d_return_median": (forward, "median"),
            f"max_high_return_{horizon}d_mean": (max_high, "mean"),
            f"max_low_drawdown_{horizon}d_mean": (max_low, "mean"),
            f"max_low_drawdown_{horizon}d_worst": (max_low, "min"),
        }
    ).reset_index()
    win_rate = (
        complete_rows.assign(_win=complete_rows[forward] > 0)
        .groupby(group_column, dropna=False)["_win"]
        .mean()
        .reset_index(name=f"forward_{horizon}d_win_rate")
    )
    return stats.merge(win_rate, on=group_column, how="left")


def _analytics_columns(horizons: list[int]) -> list[str]:
    columns = [
        "analytics_level",
        "decision_label",
        "source_context",
        "review_session_id",
        "asset_id",
        "sample_count",
        "complete_count",
        "insufficient_data_count",
        "follow_up_required_rate",
    ]
    for horizon in horizons:
        columns.extend(_metric_columns_for_horizon(horizon))
    return columns


def _metric_columns_for_horizon(horizon: int) -> list[str]:
    return [
        f"forward_{horizon}d_return_mean",
        f"forward_{horizon}d_return_median",
        f"forward_{horizon}d_win_rate",
        f"max_high_return_{horizon}d_mean",
        f"max_low_drawdown_{horizon}d_mean",
        f"max_low_drawdown_{horizon}d_worst",
    ]


def _selected_horizons(horizons: list[int] | None) -> list[int]:
    return sorted({int(value) for value in (horizons or DEFAULT_ANALYTICS_HORIZONS) if int(value) > 0})


def _requires_follow_up(row: pd.Series) -> bool:
    if "requires_follow_up" in row and pd.notna(row.get("requires_follow_up")):
        return bool(row.get("requires_follow_up"))
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        return bool(metadata.get("requires_follow_up"))
    return False


def _metric_value(row: pd.Series, map_column: str, flat_column: str, horizon: int) -> Any:
    if flat_column in row and pd.notna(row.get(flat_column)):
        return row.get(flat_column)
    value = row.get(map_column)
    if isinstance(value, dict):
        return value.get(str(horizon), value.get(horizon))
    return pd.NA


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return [_json_safe(record) for record in frame.to_dict("records")]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value


def _bool_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None or value is pd.NA:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    return None
