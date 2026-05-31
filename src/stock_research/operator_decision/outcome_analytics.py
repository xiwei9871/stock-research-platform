from __future__ import annotations

import json
from pathlib import Path
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
    group_records = _records(groups)
    diagnostics = _diagnostic_rows(group_records, selected_horizons)
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
        "diagnostic_count": len(diagnostics),
        "groups": group_records,
        "diagnostics": diagnostics,
    }


def write_decision_outcome_analytics(analytics: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    start_date = _safe_path_part(analytics.get("review_start_date", "unknown-start"))
    end_date = _safe_path_part(analytics.get("review_end_date", "unknown-end"))
    stem = f"operator_decision_outcome_analytics_{start_date}_{end_date}"

    json_path = output_path / f"{stem}.json"
    groups_csv_path = output_path / f"{stem}_groups.csv"
    diagnostics_csv_path = output_path / f"{stem}_diagnostics.csv"
    markdown_path = output_path / f"{stem}.md"

    payload = _json_safe(analytics)
    horizons = [int(value) for value in payload.get("horizons", [])]
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    pd.DataFrame(payload.get("groups", []), columns=_analytics_columns(horizons)).to_csv(
        groups_csv_path,
        index=False,
    )
    pd.DataFrame(payload.get("diagnostics", []), columns=_diagnostic_columns()).to_csv(
        diagnostics_csv_path,
        index=False,
    )
    markdown_path.write_text(_render_analytics_markdown(payload), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "groups_csv_path": str(groups_csv_path),
        "diagnostics_csv_path": str(diagnostics_csv_path),
        "markdown_path": str(markdown_path),
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
        parsed = _bool_value(row.get("requires_follow_up"))
        if parsed is not None:
            return parsed
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


def _diagnostic_rows(groups: list[dict[str, Any]], horizons: list[int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for horizon in horizons:
        forward_column = f"forward_{horizon}d_return_mean"
        drawdown_column = f"max_low_drawdown_{horizon}d_worst"
        complete_groups = [
            group
            for group in groups
            if int(group.get("complete_count") or 0) > 0 and group.get(forward_column) is not None
        ]
        if complete_groups:
            top = max(complete_groups, key=lambda group: float(group[forward_column]))
            bottom = min(complete_groups, key=lambda group: float(group[forward_column]))
            rows.append(_diagnostic_row("top_forward_return", horizon, top, forward_column))
            rows.append(_diagnostic_row("bottom_forward_return", horizon, bottom, forward_column))

        drawdown_groups = [
            group
            for group in groups
            if int(group.get("complete_count") or 0) > 0 and group.get(drawdown_column) is not None
        ]
        if drawdown_groups:
            worst_drawdown = min(drawdown_groups, key=lambda group: float(group[drawdown_column]))
            rows.append(_diagnostic_row("worst_drawdown", horizon, worst_drawdown, drawdown_column))
    return rows


def _diagnostic_row(
    diagnostic_type: str,
    horizon: int,
    group: dict[str, Any],
    metric_column: str,
) -> dict[str, Any]:
    analytics_level = str(group.get("analytics_level") or "")
    return {
        "diagnostic_type": diagnostic_type,
        "horizon": horizon,
        "analytics_level": analytics_level,
        "group_value": str(group.get(analytics_level) or ""),
        "metric_column": metric_column,
        "metric_value": group.get(metric_column),
        "sample_count": group.get("sample_count"),
        "complete_count": group.get("complete_count"),
        "insufficient_data_count": group.get("insufficient_data_count"),
        "follow_up_required_rate": group.get("follow_up_required_rate"),
    }


def _diagnostic_columns() -> list[str]:
    return [
        "diagnostic_type",
        "horizon",
        "analytics_level",
        "group_value",
        "metric_column",
        "metric_value",
        "sample_count",
        "complete_count",
        "insufficient_data_count",
        "follow_up_required_rate",
    ]


def _render_analytics_markdown(analytics: dict[str, Any]) -> str:
    lines = [
        "# P9 Outcome Analytics",
        "",
        f"- run_id: {_markdown_cell(analytics.get('run_id'))}",
        f"- review_start_date: {_markdown_cell(analytics.get('review_start_date'))}",
        f"- review_end_date: {_markdown_cell(analytics.get('review_end_date'))}",
        f"- status: {_markdown_cell(analytics.get('status'))}",
        "- manual_review_required: true",
        "- auto_trade_enabled: false",
        "",
        "Review-only grouped outcome analytics. No broker, order, or execution state is modified.",
        "",
        "## Summary",
        "",
        f"- source_outcome_count: {int(analytics.get('source_outcome_count') or 0)}",
        f"- group_count: {int(analytics.get('group_count') or 0)}",
        f"- diagnostic_count: {int(analytics.get('diagnostic_count') or 0)}",
        "",
        "## Diagnostics",
        "",
    ]
    diagnostics = analytics.get("diagnostics") or []
    if diagnostics:
        lines.extend(
            [
                "| Type | Horizon | Level | Group | Metric | Value |",
                "| --- | ---: | --- | --- | --- | ---: |",
            ]
        )
        for row in diagnostics[:20]:
            lines.append(
                " | ".join(
                    [
                        f"| {_markdown_cell(row.get('diagnostic_type'))}",
                        str(row.get("horizon") or ""),
                        _markdown_cell(row.get("analytics_level")),
                        _markdown_cell(row.get("group_value")),
                        _markdown_cell(row.get("metric_column")),
                        f"{_format_metric(row.get('metric_value'))} |",
                    ]
                )
            )
    else:
        lines.append("No diagnostic rows recorded.")

    lines.extend(["", "## Groups", ""])
    groups = analytics.get("groups") or []
    if not groups:
        lines.append("No outcome groups recorded.")
        return "\n".join(lines) + "\n"

    first_horizon = (analytics.get("horizons") or [None])[0]
    forward_column = f"forward_{first_horizon}d_return_mean" if first_horizon else ""
    lines.extend(
        [
            "| Level | Group | Samples | Complete | Insufficient | Follow-up Rate | Forward Mean |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in groups[:50]:
        analytics_level = str(row.get("analytics_level") or "")
        lines.append(
            " | ".join(
                [
                    f"| {_markdown_cell(analytics_level)}",
                    _markdown_cell(row.get(analytics_level)),
                    str(row.get("sample_count") or 0),
                    str(row.get("complete_count") or 0),
                    str(row.get("insufficient_data_count") or 0),
                    _format_metric(row.get("follow_up_required_rate")),
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
    text = str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def _safe_path_part(value: Any) -> str:
    text = str(value or "")
    return "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in text)


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
