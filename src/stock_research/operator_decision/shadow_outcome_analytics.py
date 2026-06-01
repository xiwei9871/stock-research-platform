from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_SHADOW_OUTCOME_ANALYTICS_HORIZONS = [1, 3, 5, 10, 20, 60]

UNSAFE_EXECUTION_FIELDS = {
    "account_id",
    "broker",
    "broker_id",
    "cash",
    "execution_id",
    "fill_id",
    "limit_price",
    "notional",
    "order_id",
    "order_side",
    "position_id",
    "price",
    "quantity",
    "shares",
    "side",
    "stop_price",
    "trade_id",
}

REQUIRED_TEXT_COLUMNS = [
    "shadow_layer",
    "shadow_status",
    "source_p12_shadow_run_id",
    "replay_result_id",
    "source_p11_replay_run_id",
    "source_p10_proposal_run_id",
    "source_p9_analytics_run_id",
    "candidate_date",
    "asset_id",
    "outcome_status",
]

GROUP_BY = ["shadow_layer", "shadow_status"]


def build_shadow_outcome_analytics_from_frames(
    *,
    shadow_outcomes: pd.DataFrame,
    horizons: list[int] | None = None,
) -> pd.DataFrame:
    """Return one row per shadow_layer + shadow_status group."""
    selected_horizons = _normalize_horizons(horizons)
    normalized = _normalize_shadow_outcomes(shadow_outcomes, selected_horizons)
    columns = _analytics_columns(selected_horizons)
    if normalized.empty:
        return pd.DataFrame(columns=columns)

    grouped = normalized.groupby(GROUP_BY, dropna=False, sort=True)
    result = grouped.size().reset_index(name="sample_count")
    complete = (
        normalized[normalized["is_complete"]]
        .groupby(GROUP_BY, dropna=False)
        .size()
        .reset_index(name="complete_count")
    )
    insufficient = (
        normalized[normalized["is_insufficient_data"]]
        .groupby(GROUP_BY, dropna=False)
        .size()
        .reset_index(name="insufficient_data_count")
    )
    result = result.merge(complete, on=GROUP_BY, how="left")
    result = result.merge(insufficient, on=GROUP_BY, how="left")
    result["complete_count"] = result["complete_count"].fillna(0).astype(int)
    result["insufficient_data_count"] = result["insufficient_data_count"].fillna(0).astype(int)

    for column in [
        "source_p12_shadow_run_id",
        "source_p11_replay_run_id",
        "source_p10_proposal_run_id",
        "source_p9_analytics_run_id",
    ]:
        counts = grouped[column].nunique().reset_index(name=f"{column.removesuffix('_id')}_count")
        result = result.merge(counts, on=GROUP_BY, how="left")

    complete_rows = normalized[normalized["is_complete"]].copy()
    for horizon in selected_horizons:
        result = result.merge(_horizon_stats(complete_rows, horizon), on=GROUP_BY, how="left")

    result.insert(0, "group_key", result["shadow_layer"] + "|" + result["shadow_status"])
    result["manual_review_required"] = True
    result["auto_trade_enabled"] = False
    result["production_watchlist_enabled"] = False
    result["production_write_enabled"] = False
    for column in [
        "manual_review_required",
        "auto_trade_enabled",
        "production_watchlist_enabled",
        "production_write_enabled",
    ]:
        result[column] = result[column].astype(object)
    for column in columns:
        if column not in result.columns:
            result[column] = pd.NA
    return result.loc[:, columns]


def build_shadow_outcome_analytics(
    *,
    review_start_date: str,
    review_end_date: str,
    shadow_outcomes: pd.DataFrame,
    horizons: list[int] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Return the JSON-serializable P14 analytics artifact payload."""
    selected_horizons = _normalize_horizons(horizons)
    groups = build_shadow_outcome_analytics_from_frames(
        shadow_outcomes=shadow_outcomes,
        horizons=selected_horizons,
    )
    source_count = int(len(shadow_outcomes))
    return {
        "run_id": run_id or f"p14-shadow-outcome-analytics-{review_start_date}-{review_end_date}",
        "review_start_date": str(review_start_date),
        "review_end_date": str(review_end_date),
        "status": "shadow_outcome_analytics_ready" if source_count else "no_shadow_outcomes_recorded",
        "group_by": GROUP_BY.copy(),
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
        "horizons": selected_horizons,
        "source_outcome_count": source_count,
        "group_count": int(len(groups)),
        "groups": _records(groups),
    }


def write_shadow_outcome_analytics(analytics: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    """Write JSON, groups CSV, and Markdown artifacts."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    start_date = _safe_path_part(analytics.get("review_start_date") or "unknown-start")
    end_date = _safe_path_part(analytics.get("review_end_date") or "unknown-end")
    stem = f"operator_shadow_outcome_analytics_{start_date}_{end_date}"

    json_path = output_path / f"{stem}.json"
    groups_csv_path = output_path / f"{stem}_groups.csv"
    markdown_path = output_path / f"{stem}.md"

    payload = _json_safe(analytics)
    horizons = _normalize_horizons(payload.get("horizons"))
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    pd.DataFrame(payload.get("groups", []), columns=_analytics_columns(horizons)).to_csv(
        groups_csv_path,
        index=False,
    )
    markdown_path.write_text(_render_shadow_outcome_analytics_markdown(payload), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "groups_csv_path": str(groups_csv_path),
        "markdown_path": str(markdown_path),
    }


def _normalize_shadow_outcomes(outcomes: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    _reject_unsafe_execution_fields(outcomes)
    normalized = outcomes.copy()
    for column in _base_columns():
        if column not in normalized.columns:
            normalized[column] = _default_value(column)
    for horizon in horizons:
        for column in _source_metric_columns(horizon):
            if column not in normalized.columns:
                normalized[column] = pd.NA

    if normalized.empty:
        return normalized

    for column in REQUIRED_TEXT_COLUMNS:
        normalized[column] = normalized[column].map(_required_text(column))
    _normalize_safety_fields(normalized)
    normalized["is_complete"] = normalized["outcome_status"].eq("complete")
    normalized["is_insufficient_data"] = normalized["outcome_status"].eq("insufficient_data")

    for horizon in horizons:
        for column in _source_metric_columns(horizon):
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
            normalized.loc[~normalized["is_complete"], column] = pd.NA
    return normalized


def _horizon_stats(complete_rows: pd.DataFrame, horizon: int) -> pd.DataFrame:
    columns = [*GROUP_BY, *_metric_columns_for_horizon(horizon)]
    if complete_rows.empty:
        return pd.DataFrame(columns=columns)

    forward = f"forward_{horizon}d_return"
    max_high = f"max_high_return_{horizon}d"
    max_low = f"max_low_drawdown_{horizon}d"
    grouped = complete_rows.groupby(GROUP_BY, dropna=False, sort=True)
    stats = grouped.agg(
        **{
            f"forward_{horizon}d_return_mean": (forward, "mean"),
            f"forward_{horizon}d_return_median": (forward, "median"),
            f"max_high_return_{horizon}d_mean": (max_high, "mean"),
            f"max_low_drawdown_{horizon}d_mean": (max_low, "mean"),
            f"max_low_drawdown_{horizon}d_worst": (max_low, "min"),
        }
    ).reset_index()
    win_rows = complete_rows[complete_rows[forward].notna()].copy()
    if win_rows.empty:
        win_rate = pd.DataFrame(columns=[*GROUP_BY, f"forward_{horizon}d_win_rate"])
    else:
        win_rate = (
            win_rows.assign(_win=win_rows[forward] > 0)
            .groupby(GROUP_BY, dropna=False)["_win"]
            .mean()
            .reset_index(name=f"forward_{horizon}d_win_rate")
        )
    return stats.merge(win_rate, on=GROUP_BY, how="left").loc[:, columns]


def _normalize_safety_fields(frame: pd.DataFrame) -> None:
    frame["manual_review_required"] = frame["manual_review_required"].map(
        lambda value: _parse_safety_value(value, column="manual_review_required", default=True)
    )
    if frame["manual_review_required"].ne(True).any():
        raise ValueError("manual_review_required")
    frame["manual_review_required"] = True

    frame["auto_trade_enabled"] = frame["auto_trade_enabled"].map(
        lambda value: _parse_safety_value(value, column="auto_trade_enabled", default=False)
    )
    if frame["auto_trade_enabled"].eq(True).any():
        raise ValueError("auto_trade_not_allowed")
    frame["auto_trade_enabled"] = False

    frame["production_watchlist_enabled"] = frame["production_watchlist_enabled"].map(
        lambda value: _parse_safety_value(value, column="production_watchlist_enabled", default=False)
    )
    if frame["production_watchlist_enabled"].eq(True).any():
        raise ValueError("production_watchlist_not_allowed")
    frame["production_watchlist_enabled"] = False

    frame["production_write_enabled"] = frame["production_write_enabled"].map(
        lambda value: _parse_safety_value(value, column="production_write_enabled", default=False)
    )
    if frame["production_write_enabled"].eq(True).any():
        raise ValueError("production_write_not_allowed")
    frame["production_write_enabled"] = False


def _parse_safety_value(value: Any, *, column: str, default: bool) -> bool:
    if _is_missing(value):
        return default
    parsed = _bool_value(value)
    if parsed is None:
        raise ValueError(f"invalid_safety_field: {column}")
    return parsed


def _reject_unsafe_execution_fields(frame: pd.DataFrame) -> None:
    for column in frame.columns:
        normalized_column = str(column).strip().lower()
        if normalized_column not in UNSAFE_EXECUTION_FIELDS:
            continue
        if frame[column].map(lambda value: not _is_missing(value) and str(value).strip() != "").any():
            raise ValueError(f"unsafe_execution_field: {column}")


def _required_text(column: str):
    def normalize(value: Any) -> str:
        if _is_missing(value) or str(value).strip() == "":
            raise ValueError(f"required_field_missing: {column}")
        return str(value).strip()

    return normalize


def _normalize_horizons(horizons: list[int] | None) -> list[int]:
    return sorted(
        {int(value) for value in (horizons or DEFAULT_SHADOW_OUTCOME_ANALYTICS_HORIZONS) if int(value) > 0}
    )


def _analytics_columns(horizons: list[int]) -> list[str]:
    columns = [
        "group_key",
        "shadow_layer",
        "shadow_status",
        "sample_count",
        "complete_count",
        "insufficient_data_count",
        "source_p12_shadow_run_count",
        "source_p11_replay_run_count",
        "source_p10_proposal_run_count",
        "source_p9_analytics_run_count",
    ]
    for horizon in horizons:
        columns.extend(_metric_columns_for_horizon(horizon))
    columns.extend(
        [
            "manual_review_required",
            "auto_trade_enabled",
            "production_watchlist_enabled",
            "production_write_enabled",
        ]
    )
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


def _source_metric_columns(horizon: int) -> list[str]:
    return [
        f"forward_{horizon}d_return",
        f"max_high_return_{horizon}d",
        f"max_low_drawdown_{horizon}d",
    ]


def _base_columns() -> list[str]:
    return [
        *REQUIRED_TEXT_COLUMNS,
        "manual_review_required",
        "auto_trade_enabled",
        "production_watchlist_enabled",
        "production_write_enabled",
    ]


def _default_value(column: str) -> Any:
    if column == "manual_review_required":
        return True
    if column in {"auto_trade_enabled", "production_watchlist_enabled", "production_write_enabled"}:
        return False
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
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if value is pd.NA:
        return None
    if isinstance(value, pd.Timestamp):
        return str(value.date())
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value


def _render_shadow_outcome_analytics_markdown(analytics: dict[str, Any]) -> str:
    lines = [
        "# P14 Shadow Outcome Analytics",
        "",
        f"- run_id: {_markdown_cell(analytics.get('run_id'))}",
        f"- review_start_date: {_markdown_cell(analytics.get('review_start_date'))}",
        f"- review_end_date: {_markdown_cell(analytics.get('review_end_date'))}",
        f"- status: {_markdown_cell(analytics.get('status'))}",
        "- group_by: shadow_layer, shadow_status",
        "- manual_review_required: true",
        "- auto_trade_enabled: false",
        "- production_watchlist_enabled: false",
        "- production_write_enabled: false",
        "",
        "Review-only shadow outcome analytics. No production watchlist, broker, order, or execution state is modified.",
        "",
        "## Summary",
        "",
        f"- source_outcome_count: {int(analytics.get('source_outcome_count') or 0)}",
        f"- group_count: {int(analytics.get('group_count') or 0)}",
        "",
        "## Groups",
        "",
    ]
    groups = analytics.get("groups") or []
    if not groups:
        lines.append("No shadow outcome groups recorded.")
        return "\n".join(lines) + "\n"

    first_horizon = (analytics.get("horizons") or [None])[0]
    forward_column = f"forward_{first_horizon}d_return_mean" if first_horizon else ""
    lines.extend(
        [
            "| Group | Samples | Complete | Insufficient | Forward Mean |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in groups[:50]:
        lines.append(
            " | ".join(
                [
                    f"| {_markdown_cell(row.get('group_key'))}",
                    str(row.get("sample_count") or 0),
                    str(row.get("complete_count") or 0),
                    str(row.get("insufficient_data_count") or 0),
                    f"{_format_metric(row.get(forward_column))} |",
                ]
            )
        )
    return "\n".join(lines) + "\n"


def _format_metric(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    try:
        return f"{float(value):.6f}"
    except (TypeError, ValueError):
        return _markdown_cell(value)


def _markdown_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def _safe_path_part(value: Any) -> str:
    return str(value).replace("/", "-").replace(":", "-")


def _bool_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    return None


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
