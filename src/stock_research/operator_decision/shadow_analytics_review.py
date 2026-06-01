from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


REVIEW_STATUSES = [
    "continue_observing",
    "needs_more_data",
    "investigate_data_quality",
    "deprioritize_review",
    "research_follow_up_candidate",
]

DEFAULT_SHADOW_ANALYTICS_REVIEW_THRESHOLDS = {
    "min_sample_count": 10,
    "max_insufficient_data_rate": 0.40,
    "follow_up_forward_return_mean": 0.03,
    "deprioritize_forward_return_mean": -0.02,
    "max_controlled_drawdown_worst": -0.15,
    "deprioritize_drawdown_worst": -0.20,
    "primary_horizon": "20",
}

UNSAFE_EXECUTION_FIELDS = {
    "account_id",
    "broker",
    "broker_id",
    "cash",
    "execution_id",
    "fill_id",
    "limit_price",
    "order_id",
    "order_side",
    "position_id",
    "price",
    "quantity",
    "shares",
    "side",
    "stop_price",
    "trade_id",
    "notional",
}

REVIEW_BUCKETS = {
    "continue_observing": "observe",
    "needs_more_data": "data_needed",
    "investigate_data_quality": "data_quality",
    "deprioritize_review": "deprioritize",
    "research_follow_up_candidate": "follow_up",
}

SAFETY_FIELDS = [
    "manual_review_required",
    "auto_trade_enabled",
    "production_watchlist_enabled",
    "production_write_enabled",
]


def build_shadow_analytics_review_from_rows(
    rows: list[dict[str, Any]],
    *,
    run_id: str,
    review_start_date: str,
    review_end_date: str,
    reviewer_id: str,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the JSON-serializable P15 shadow analytics review artifact payload."""
    selected_thresholds = _normalize_thresholds(thresholds)
    normalized_rows = [_normalize_group_row(row) for row in rows]
    primary_horizon = str(selected_thresholds["primary_horizon"])
    groups = [
        _review_group(row, run_id=run_id, thresholds=selected_thresholds, primary_horizon=primary_horizon)
        for row in normalized_rows
    ]
    return {
        "run_id": str(run_id),
        "review_start_date": str(review_start_date),
        "review_end_date": str(review_end_date),
        "reviewer_id": str(reviewer_id),
        "status": "shadow_analytics_review_ready" if groups else "no_shadow_analytics_groups_recorded",
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
        "thresholds": _json_safe(selected_thresholds),
        "primary_horizon": primary_horizon,
        "source_p14_analytics_run_ids": sorted(
            {
                str(row["run_id"])
                for row in normalized_rows
                if not _is_missing(row.get("run_id")) and str(row.get("run_id")).strip()
            }
        ),
        "group_count": int(len(groups)),
        "groups": groups,
    }


def build_shadow_analytics_review(
    *,
    p14_analytics: dict[str, Any],
    run_id: str,
    review_start_date: str,
    review_end_date: str,
    reviewer_id: str,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a P15 review artifact from the P14 analytics groups."""
    _reject_unsafe_execution_fields(p14_analytics)
    _validate_safety_fields(p14_analytics)
    rows = _p14_artifact_rows(p14_analytics)
    return build_shadow_analytics_review_from_rows(
        rows,
        run_id=run_id,
        review_start_date=review_start_date,
        review_end_date=review_end_date,
        reviewer_id=reviewer_id,
        thresholds=thresholds,
    )


def write_shadow_analytics_review(review: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    """Write JSON, groups CSV, and Markdown artifacts."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    start_date = _safe_path_part(review.get("review_start_date") or "unknown-start")
    end_date = _safe_path_part(review.get("review_end_date") or "unknown-end")
    stem = f"operator_shadow_analytics_review_{start_date}_{end_date}"

    json_path = output_path / f"{stem}.json"
    groups_csv_path = output_path / f"{stem}_groups.csv"
    markdown_path = output_path / f"{stem}.md"

    payload = _json_safe(review)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    pd.DataFrame(_csv_safe_rows(payload.get("groups", [])), columns=_group_columns()).to_csv(
        groups_csv_path,
        index=False,
    )
    markdown_path.write_text(_render_shadow_analytics_review_markdown(payload), encoding="utf-8")
    return {
        "json_path": str(json_path),
        "groups_csv_path": str(groups_csv_path),
        "markdown_path": str(markdown_path),
    }


def _p14_artifact_rows(p14_analytics: dict[str, Any]) -> list[dict[str, Any]]:
    p14_run_id = _text_or_empty(p14_analytics.get("run_id"))
    artifact_path = _text_or_empty(
        p14_analytics.get("analytics_artifact_path")
        or p14_analytics.get("artifact_path")
        or p14_analytics.get("json_path")
    )
    rows = []
    for item in p14_analytics.get("groups") or []:
        if not isinstance(item, dict):
            raise ValueError("invalid_p14_analytics_group")
        row = dict(item)
        row_run_id = _text_or_empty(row.get("run_id")) or p14_run_id
        if row_run_id:
            row["run_id"] = row_run_id
        if _is_missing(row.get("analytics_group_id")) or str(row.get("analytics_group_id")).strip() == "":
            group_key = _required_text(row, "group_key")
            if not row_run_id:
                raise ValueError("required_field_missing: run_id")
            row["analytics_group_id"] = _p14_analytics_group_id(run_id=row_run_id, group_key=group_key)
        if artifact_path and (_is_missing(row.get("analytics_artifact_path")) or str(row.get("analytics_artifact_path")).strip() == ""):
            row["analytics_artifact_path"] = artifact_path
        rows.append(row)
    return rows


def _normalize_group_row(row: dict[str, Any]) -> dict[str, Any]:
    _reject_unsafe_execution_fields(row)
    _validate_safety_fields(row)
    normalized = dict(row)
    normalized["manual_review_required"] = True
    normalized["auto_trade_enabled"] = False
    normalized["production_watchlist_enabled"] = False
    normalized["production_write_enabled"] = False
    return normalized


def _review_group(
    row: dict[str, Any],
    *,
    run_id: str,
    thresholds: dict[str, Any],
    primary_horizon: str,
) -> dict[str, Any]:
    review_status = _review_status(row, thresholds=thresholds, primary_horizon=primary_horizon)
    source_group_id = _required_text(row, "analytics_group_id")
    digest = hashlib.sha256(f"{source_group_id}|{review_status}".encode("utf-8")).hexdigest()[:16]
    metrics = _primary_horizon_metrics(row, primary_horizon)
    insufficient_rate = _insufficient_data_rate(row)
    group = {
        "review_group_id": f"operator_shadow_analytics_review:{run_id}:{digest}",
        "source_p14_analytics_group_id": source_group_id,
        "source_p14_analytics_run_id": _required_text(row, "run_id"),
        "review_status": review_status,
        "review_bucket": REVIEW_BUCKETS[review_status],
        "group_key": _text_or_empty(row.get("group_key")),
        "shadow_layer": _text_or_empty(row.get("shadow_layer")),
        "shadow_status": _text_or_empty(row.get("shadow_status")),
        "sample_count": _int_value(row.get("sample_count")),
        "complete_count": _int_value(row.get("complete_count")),
        "insufficient_data_count": _int_value(row.get("insufficient_data_count")),
        "insufficient_data_rate": insufficient_rate,
        "source_p12_shadow_run_count": _int_value(row.get("source_p12_shadow_run_count")),
        "source_p11_replay_run_count": _int_value(row.get("source_p11_replay_run_count")),
        "source_p10_proposal_run_count": _int_value(row.get("source_p10_proposal_run_count")),
        "source_p9_analytics_run_count": _int_value(row.get("source_p9_analytics_run_count")),
        "primary_horizon": primary_horizon,
        "primary_horizon_metrics": metrics,
        "analytics_artifact_path": _text_or_empty(row.get("analytics_artifact_path")),
        "evidence_summary": _evidence_summary(row, review_status, metrics, insufficient_rate),
        "risk_notes": _risk_notes(review_status),
        "next_research_question": _next_research_question(review_status),
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
    }
    return _json_safe(group)


def _review_status(row: dict[str, Any], *, thresholds: dict[str, Any], primary_horizon: str) -> str:
    sample_count = _int_value(row.get("sample_count"))
    insufficient_rate = _insufficient_data_rate(row)
    metrics = _primary_horizon_metrics(row, primary_horizon)
    forward_mean = _float_or_none(metrics.get("forward_return_mean"))
    drawdown_worst = _float_or_none(metrics.get("max_low_drawdown_worst"))

    if sample_count < int(thresholds["min_sample_count"]):
        return "needs_more_data"
    if insufficient_rate > float(thresholds["max_insufficient_data_rate"]):
        return "investigate_data_quality"
    if _at_or_below(forward_mean, thresholds["deprioritize_forward_return_mean"]) or _at_or_below(
        drawdown_worst, thresholds["deprioritize_drawdown_worst"]
    ):
        return "deprioritize_review"
    if _at_or_above(forward_mean, thresholds["follow_up_forward_return_mean"]) and _at_or_above(
        drawdown_worst, thresholds["max_controlled_drawdown_worst"]
    ):
        return "research_follow_up_candidate"
    return "continue_observing"


def _primary_horizon_metrics(row: dict[str, Any], primary_horizon: str) -> dict[str, Any]:
    horizon_metrics = row.get("horizon_metrics")
    if isinstance(horizon_metrics, dict):
        metrics = horizon_metrics.get(primary_horizon, {})
        if isinstance(metrics, dict):
            return {
                "forward_return_mean": _float_or_none(
                    metrics.get("forward_return_mean", metrics.get(f"forward_{primary_horizon}d_return_mean"))
                ),
                "forward_return_median": _float_or_none(
                    metrics.get("forward_return_median", metrics.get(f"forward_{primary_horizon}d_return_median"))
                ),
                "forward_win_rate": _float_or_none(
                    metrics.get("forward_win_rate", metrics.get(f"forward_{primary_horizon}d_win_rate"))
                ),
                "max_high_return_mean": _float_or_none(
                    metrics.get("max_high_return_mean", metrics.get(f"max_high_return_{primary_horizon}d_mean"))
                ),
                "max_low_drawdown_mean": _float_or_none(
                    metrics.get(
                        "max_low_drawdown_mean",
                        metrics.get(f"max_low_drawdown_{primary_horizon}d_mean"),
                    )
                ),
                "max_low_drawdown_worst": _float_or_none(
                    metrics.get(
                        "max_low_drawdown_worst",
                        metrics.get(f"max_low_drawdown_{primary_horizon}d_worst"),
                    )
                ),
            }

    return {
        "forward_return_mean": _float_or_none(row.get(f"forward_{primary_horizon}d_return_mean")),
        "forward_return_median": _float_or_none(row.get(f"forward_{primary_horizon}d_return_median")),
        "forward_win_rate": _float_or_none(row.get(f"forward_{primary_horizon}d_win_rate")),
        "max_high_return_mean": _float_or_none(row.get(f"max_high_return_{primary_horizon}d_mean")),
        "max_low_drawdown_mean": _float_or_none(row.get(f"max_low_drawdown_{primary_horizon}d_mean")),
        "max_low_drawdown_worst": _float_or_none(row.get(f"max_low_drawdown_{primary_horizon}d_worst")),
    }


def _insufficient_data_rate(row: dict[str, Any]) -> float:
    sample_count = _int_value(row.get("sample_count"))
    if sample_count <= 0:
        return 0.0
    return _int_value(row.get("insufficient_data_count")) / sample_count


def _normalize_thresholds(thresholds: dict[str, Any] | None) -> dict[str, Any]:
    selected = dict(DEFAULT_SHADOW_ANALYTICS_REVIEW_THRESHOLDS)
    if thresholds:
        selected.update(thresholds)
    selected["primary_horizon"] = str(selected["primary_horizon"])
    return selected


def _validate_safety_fields(payload: dict[str, Any]) -> None:
    if "manual_review_required" in payload:
        manual_review_required = _parse_safety_value(
            payload.get("manual_review_required"),
            column="manual_review_required",
            default=True,
        )
        if manual_review_required is not True:
            raise ValueError("manual_review_required")
    if "auto_trade_enabled" in payload:
        auto_trade_enabled = _parse_safety_value(
            payload.get("auto_trade_enabled"),
            column="auto_trade_enabled",
            default=False,
        )
        if auto_trade_enabled is True:
            raise ValueError("auto_trade_not_allowed")
    if "production_watchlist_enabled" in payload:
        production_watchlist_enabled = _parse_safety_value(
            payload.get("production_watchlist_enabled"),
            column="production_watchlist_enabled",
            default=False,
        )
        if production_watchlist_enabled is True:
            raise ValueError("production_watchlist_not_allowed")
    if "production_write_enabled" in payload:
        production_write_enabled = _parse_safety_value(
            payload.get("production_write_enabled"),
            column="production_write_enabled",
            default=False,
        )
        if production_write_enabled is True:
            raise ValueError("production_write_not_allowed")


def _parse_safety_value(value: Any, *, column: str, default: bool) -> bool:
    if _is_missing(value):
        return default
    parsed = _bool_value(value)
    if parsed is None:
        raise ValueError(f"invalid_safety_field: {column}")
    return parsed


def _reject_unsafe_execution_fields(payload: dict[str, Any]) -> None:
    for key, value in payload.items():
        normalized_key = str(key).strip().lower()
        if normalized_key in UNSAFE_EXECUTION_FIELDS and not _is_missing(value) and str(value).strip() != "":
            raise ValueError(f"unsafe_execution_field: {key}")


def _p14_analytics_group_id(*, run_id: str, group_key: str) -> str:
    raw = "|".join([run_id, group_key])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"operator_shadow_outcome_analytics:{run_id}:{digest}"


def _evidence_summary(
    row: dict[str, Any],
    review_status: str,
    metrics: dict[str, Any],
    insufficient_rate: float,
) -> str:
    return (
        f"{review_status} for {_text_or_empty(row.get('group_key')) or _text_or_empty(row.get('analytics_group_id'))}: "
        f"samples={_int_value(row.get('sample_count'))}, insufficient_rate={insufficient_rate:.2f}, "
        f"forward_mean={_format_metric(metrics.get('forward_return_mean'))}, "
        f"drawdown_worst={_format_metric(metrics.get('max_low_drawdown_worst'))}."
    )


def _risk_notes(review_status: str) -> str:
    notes = {
        "continue_observing": "Review-only observation should continue until stronger evidence accumulates.",
        "needs_more_data": "Sample size is below the conservative review threshold.",
        "investigate_data_quality": "Insufficient data rate is elevated and should be checked before interpretation.",
        "deprioritize_review": "Forward return or drawdown evidence is unfavorable for follow-up research.",
        "research_follow_up_candidate": "Positive evidence remains review-only and must not enable production writes.",
    }
    return notes[review_status]


def _next_research_question(review_status: str) -> str:
    questions = {
        "continue_observing": "Does the group remain stable after the next shadow analytics refresh?",
        "needs_more_data": "How many more complete samples are needed before review status can change?",
        "investigate_data_quality": "Which source runs or horizons explain the insufficient data concentration?",
        "deprioritize_review": "Is the weak evidence structural or tied to a temporary market regime?",
        "research_follow_up_candidate": "Which non-production research checks would validate this group next?",
    }
    return questions[review_status]


def _group_columns() -> list[str]:
    return [
        "review_group_id",
        "source_p14_analytics_group_id",
        "source_p14_analytics_run_id",
        "review_status",
        "review_bucket",
        "group_key",
        "shadow_layer",
        "shadow_status",
        "sample_count",
        "complete_count",
        "insufficient_data_count",
        "insufficient_data_rate",
        "source_p12_shadow_run_count",
        "source_p11_replay_run_count",
        "source_p10_proposal_run_count",
        "source_p9_analytics_run_count",
        "primary_horizon",
        "primary_horizon_metrics",
        "analytics_artifact_path",
        "evidence_summary",
        "risk_notes",
        "next_research_question",
        *SAFETY_FIELDS,
    ]


def _render_shadow_analytics_review_markdown(review: dict[str, Any]) -> str:
    lines = [
        "# P15 Shadow Analytics Review",
        "",
        f"- run_id: {_markdown_cell(review.get('run_id'))}",
        f"- review_start_date: {_markdown_cell(review.get('review_start_date'))}",
        f"- review_end_date: {_markdown_cell(review.get('review_end_date'))}",
        f"- reviewer_id: {_markdown_cell(review.get('reviewer_id'))}",
        f"- status: {_markdown_cell(review.get('status'))}",
        "- manual_review_required: true",
        "- auto_trade_enabled: false",
        "- production_watchlist_enabled: false",
        "- production_write_enabled: false",
        "",
        "Review-only shadow analytics triage. No production watchlist, broker, order, or execution state is modified.",
        "",
        "## Summary",
        "",
        f"- group_count: {int(review.get('group_count') or 0)}",
        f"- primary_horizon: {_markdown_cell(review.get('primary_horizon'))}",
        "",
        "## Groups",
        "",
    ]
    groups = review.get("groups") or []
    if not groups:
        lines.append("No shadow analytics groups recorded.")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| Group | Review Status | Bucket | Samples | Evidence |",
            "| --- | --- | --- | ---: | --- |",
        ]
    )
    for row in groups[:50]:
        lines.append(
            " | ".join(
                [
                    f"| {_markdown_cell(row.get('group_key'))}",
                    _markdown_cell(row.get("review_status")),
                    _markdown_cell(row.get("review_bucket")),
                    str(row.get("sample_count") or 0),
                    f"{_markdown_cell(row.get('evidence_summary'))} |",
                ]
            )
        )
    return "\n".join(lines) + "\n"


def _required_text(row: dict[str, Any], column: str) -> str:
    value = row.get(column)
    if _is_missing(value) or str(value).strip() == "":
        raise ValueError(f"required_field_missing: {column}")
    return str(value).strip()


def _text_or_empty(value: Any) -> str:
    if _is_missing(value):
        return ""
    return str(value).strip()


def _int_value(value: Any) -> int:
    if _is_missing(value):
        return 0
    return int(value)


def _float_or_none(value: Any) -> float | None:
    if _is_missing(value):
        return None
    return float(value)


def _at_or_below(value: float | None, threshold: Any) -> bool:
    return value is not None and value <= float(threshold)


def _at_or_above(value: float | None, threshold: Any) -> bool:
    return value is not None and value >= float(threshold)


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


def _csv_safe_rows(rows: Any) -> list[dict[str, Any]]:
    csv_rows = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        csv_rows.append(
            {
                key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, (dict, list))
                else value
                for key, value in row.items()
            }
        )
    return csv_rows


def _format_metric(value: Any) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.6f}"
    except (TypeError, ValueError):
        return str(value)


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
