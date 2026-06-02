from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect


def load_shadow_outcome_analytics_read_model_rows(path: str | Path) -> dict[str, Any]:
    """Load one P14 JSON artifact into run and group read-model rows."""
    json_path = Path(path)
    analytics = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(analytics, dict):
        raise ValueError(f"operator shadow outcome analytics must be a JSON object: {json_path}")

    _validate_safety_fields(analytics)

    run_id = str(analytics.get("run_id") or "")
    review_start_date = str(analytics.get("review_start_date") or "")
    review_end_date = str(analytics.get("review_end_date") or "")
    if not run_id:
        raise ValueError(f"operator shadow outcome analytics requires run_id: {json_path}")
    if not review_start_date or not review_end_date:
        raise ValueError(f"operator shadow outcome analytics requires review date range: {json_path}")

    groups = [item for item in analytics.get("groups", []) if isinstance(item, dict)]
    horizons = [int(value) for value in analytics.get("horizons", [])]
    groups_csv_path, markdown_path = _artifact_paths(json_path)
    return {
        "run": {
            "run_id": run_id,
            "review_start_date": review_start_date,
            "review_end_date": review_end_date,
            "status": str(analytics.get("status") or ""),
            "group_by": analytics.get("group_by") or [],
            "source_outcome_count": int(analytics.get("source_outcome_count") or 0),
            "group_count": int(analytics.get("group_count") or len(groups)),
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "production_watchlist_enabled": False,
            "production_write_enabled": False,
            "json_path": str(json_path),
            "groups_csv_path": str(groups_csv_path),
            "markdown_path": str(markdown_path),
            "metadata": {
                "horizons": horizons,
                "artifact_metadata": analytics.get("metadata") or {},
            },
        },
        "groups": [
            _group_row(
                item,
                run_id=run_id,
                review_start_date=review_start_date,
                review_end_date=review_end_date,
                horizons=horizons,
                analytics_artifact_path=json_path,
            )
            for item in groups
        ],
    }


def import_shadow_outcome_analytics(
    path: str | Path,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    """Import one artifact or a directory of P14 artifacts into ops tables."""
    input_path = Path(path)
    paths = _analytics_paths(input_path)
    run_ids: list[str] = []
    group_count = 0
    with connect(service) as conn:
        with conn.cursor() as cur:
            for analytics_path in paths:
                rows = load_shadow_outcome_analytics_read_model_rows(analytics_path)
                _upsert_run(cur, rows["run"])
                for group in rows["groups"]:
                    _upsert_group(cur, group)
                    group_count += 1
                run_ids.append(str(rows["run"]["run_id"]))
    return {
        "imported_count": len(paths),
        "group_count": group_count,
        "run_ids": run_ids,
    }


def _analytics_paths(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("operator_shadow_outcome_analytics_*.json"))
    return [path]


def _upsert_run(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_shadow_watchlist_outcome_analytics_run (
        run_id, review_start_date, review_end_date, status, group_by,
        source_outcome_count, group_count, manual_review_required,
        auto_trade_enabled, production_watchlist_enabled, production_write_enabled,
        json_path, groups_csv_path, markdown_path, metadata
    )
    VALUES (
        %(run_id)s, %(review_start_date)s, %(review_end_date)s, %(status)s,
        %(group_by)s::jsonb, %(source_outcome_count)s, %(group_count)s,
        %(manual_review_required)s, %(auto_trade_enabled)s,
        %(production_watchlist_enabled)s, %(production_write_enabled)s,
        %(json_path)s, %(groups_csv_path)s, %(markdown_path)s, %(metadata)s::jsonb
    )
    ON CONFLICT (run_id)
    DO UPDATE SET
        review_start_date = EXCLUDED.review_start_date,
        review_end_date = EXCLUDED.review_end_date,
        status = EXCLUDED.status,
        group_by = EXCLUDED.group_by,
        source_outcome_count = EXCLUDED.source_outcome_count,
        group_count = EXCLUDED.group_count,
        manual_review_required = EXCLUDED.manual_review_required,
        auto_trade_enabled = EXCLUDED.auto_trade_enabled,
        production_watchlist_enabled = EXCLUDED.production_watchlist_enabled,
        production_write_enabled = EXCLUDED.production_write_enabled,
        json_path = EXCLUDED.json_path,
        groups_csv_path = EXCLUDED.groups_csv_path,
        markdown_path = EXCLUDED.markdown_path,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    cur.execute(
        sql,
        {
            **row,
            "group_by": json.dumps(row.get("group_by") or [], sort_keys=True),
            "metadata": json.dumps(row.get("metadata") or {}, sort_keys=True),
        },
    )


def _upsert_group(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_shadow_watchlist_outcome_analytics_group (
        analytics_group_id, run_id, review_start_date, review_end_date,
        group_key, shadow_layer, shadow_status, sample_count, complete_count,
        insufficient_data_count, source_p12_shadow_run_count,
        source_p11_replay_run_count, source_p10_proposal_run_count,
        source_p9_analytics_run_count, horizon_metrics, analytics_artifact_path,
        manual_review_required, auto_trade_enabled, production_watchlist_enabled,
        production_write_enabled, metadata
    )
    VALUES (
        %(analytics_group_id)s, %(run_id)s, %(review_start_date)s,
        %(review_end_date)s, %(group_key)s, %(shadow_layer)s, %(shadow_status)s,
        %(sample_count)s, %(complete_count)s, %(insufficient_data_count)s,
        %(source_p12_shadow_run_count)s, %(source_p11_replay_run_count)s,
        %(source_p10_proposal_run_count)s, %(source_p9_analytics_run_count)s,
        %(horizon_metrics)s::jsonb, %(analytics_artifact_path)s,
        %(manual_review_required)s, %(auto_trade_enabled)s,
        %(production_watchlist_enabled)s, %(production_write_enabled)s,
        %(metadata)s::jsonb
    )
    ON CONFLICT (analytics_group_id)
    DO UPDATE SET
        run_id = EXCLUDED.run_id,
        review_start_date = EXCLUDED.review_start_date,
        review_end_date = EXCLUDED.review_end_date,
        group_key = EXCLUDED.group_key,
        shadow_layer = EXCLUDED.shadow_layer,
        shadow_status = EXCLUDED.shadow_status,
        sample_count = EXCLUDED.sample_count,
        complete_count = EXCLUDED.complete_count,
        insufficient_data_count = EXCLUDED.insufficient_data_count,
        source_p12_shadow_run_count = EXCLUDED.source_p12_shadow_run_count,
        source_p11_replay_run_count = EXCLUDED.source_p11_replay_run_count,
        source_p10_proposal_run_count = EXCLUDED.source_p10_proposal_run_count,
        source_p9_analytics_run_count = EXCLUDED.source_p9_analytics_run_count,
        horizon_metrics = EXCLUDED.horizon_metrics,
        analytics_artifact_path = EXCLUDED.analytics_artifact_path,
        manual_review_required = EXCLUDED.manual_review_required,
        auto_trade_enabled = EXCLUDED.auto_trade_enabled,
        production_watchlist_enabled = EXCLUDED.production_watchlist_enabled,
        production_write_enabled = EXCLUDED.production_write_enabled,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    cur.execute(
        sql,
        {
            **row,
            "horizon_metrics": json.dumps(row.get("horizon_metrics") or {}, sort_keys=True),
            "metadata": json.dumps(row.get("metadata") or {}, sort_keys=True),
        },
    )


def _group_row(
    item: dict[str, Any],
    *,
    run_id: str,
    review_start_date: str,
    review_end_date: str,
    horizons: list[int],
    analytics_artifact_path: Path,
) -> dict[str, Any]:
    _validate_safety_fields(item)

    group_key = _required_text(item, "group_key")
    return {
        "analytics_group_id": _analytics_group_id(run_id=run_id, group_key=group_key),
        "run_id": run_id,
        "review_start_date": review_start_date,
        "review_end_date": review_end_date,
        "group_key": group_key,
        "shadow_layer": _required_text(item, "shadow_layer"),
        "shadow_status": _required_text(item, "shadow_status"),
        "sample_count": int(item.get("sample_count") or 0),
        "complete_count": int(item.get("complete_count") or 0),
        "insufficient_data_count": int(item.get("insufficient_data_count") or 0),
        "source_p12_shadow_run_count": int(item.get("source_p12_shadow_run_count") or 0),
        "source_p11_replay_run_count": int(item.get("source_p11_replay_run_count") or 0),
        "source_p10_proposal_run_count": int(item.get("source_p10_proposal_run_count") or 0),
        "source_p9_analytics_run_count": int(item.get("source_p9_analytics_run_count") or 0),
        "horizon_metrics": _horizon_metrics(item, horizons),
        "analytics_artifact_path": str(analytics_artifact_path),
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
        "metadata": item.get("metadata") or {},
    }


def _horizon_metrics(item: dict[str, Any], horizons: list[int]) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    for horizon in horizons:
        horizon_metrics: dict[str, Any] = {}
        for source_suffix, target_name in [
            ("return_mean", "forward_return_mean"),
            ("return_median", "forward_return_median"),
            ("win_rate", "forward_win_rate"),
        ]:
            _add_metric(horizon_metrics, item, f"forward_{horizon}d_{source_suffix}", target_name)
        _add_metric(horizon_metrics, item, f"max_high_return_{horizon}d_mean", "max_high_return_mean")
        _add_metric(horizon_metrics, item, f"max_low_drawdown_{horizon}d_mean", "max_low_drawdown_mean")
        _add_metric(horizon_metrics, item, f"max_low_drawdown_{horizon}d_worst", "max_low_drawdown_worst")
        if horizon_metrics:
            metrics[str(horizon)] = horizon_metrics
    return metrics


def _add_metric(
    horizon_metrics: dict[str, Any],
    item: dict[str, Any],
    source_column: str,
    target_name: str,
) -> None:
    value = item.get(source_column)
    if _is_metric_value(value):
        horizon_metrics[target_name] = value


def _is_metric_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    return True


def _validate_safety_fields(item: dict[str, Any]) -> None:
    manual_review_required = _parse_safety_value(
        item.get("manual_review_required"),
        column="manual_review_required",
        default=True,
    )
    auto_trade_enabled = _parse_safety_value(
        item.get("auto_trade_enabled"),
        column="auto_trade_enabled",
        default=False,
    )
    production_watchlist_enabled = _parse_safety_value(
        item.get("production_watchlist_enabled"),
        column="production_watchlist_enabled",
        default=False,
    )
    production_write_enabled = _parse_safety_value(
        item.get("production_write_enabled"),
        column="production_write_enabled",
        default=False,
    )

    if auto_trade_enabled is True:
        raise ValueError("auto_trade_not_allowed")
    if manual_review_required is not True:
        raise ValueError("manual_review_required")
    if production_watchlist_enabled is True:
        raise ValueError("production_watchlist_not_allowed")
    if production_write_enabled is True:
        raise ValueError("production_write_not_allowed")


def _parse_safety_value(value: Any, *, column: str, default: bool) -> bool:
    if value is None:
        return default
    parsed = _bool_value(value)
    if parsed is None:
        raise ValueError(f"invalid_safety_field: {column}")
    return parsed


def _required_text(item: dict[str, Any], column: str) -> str:
    value = item.get(column)
    if value is None or str(value).strip() == "":
        raise ValueError(f"required_field_missing: {column}")
    return str(value).strip()


def _artifact_paths(json_path: Path) -> tuple[Path, Path]:
    return (
        json_path.with_name(f"{json_path.stem}_groups.csv"),
        json_path.with_suffix(".md"),
    )


def _analytics_group_id(*, run_id: str, group_key: str) -> str:
    raw = "|".join([run_id, group_key])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"operator_shadow_outcome_analytics:{run_id}:{digest}"


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
