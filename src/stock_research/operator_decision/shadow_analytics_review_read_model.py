from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect


def load_shadow_analytics_review_read_model_rows(path: str | Path) -> dict[str, Any]:
    """Load one P15 JSON artifact into run and group read-model rows."""
    json_path = Path(path)
    review = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(review, dict):
        raise ValueError(f"operator shadow analytics review must be a JSON object: {json_path}")

    _validate_safety_fields(review)

    run_id = _required_text(review, "run_id")
    review_start_date = _required_text(review, "review_start_date")
    review_end_date = _required_text(review, "review_end_date")
    groups = [item for item in review.get("groups", []) if isinstance(item, dict)]
    groups_csv_path, markdown_path = _artifact_paths(json_path)
    primary_horizon = str(review.get("primary_horizon") or (review.get("thresholds") or {}).get("primary_horizon") or "")

    return {
        "run": {
            "run_id": run_id,
            "review_start_date": review_start_date,
            "review_end_date": review_end_date,
            "status": _required_text(review, "status"),
            "reviewer_id": _required_text(review, "reviewer_id"),
            "source_p14_analytics_run_ids": review.get("source_p14_analytics_run_ids") or [],
            "thresholds": review.get("thresholds") or {},
            "group_count": int(review.get("group_count") or len(groups)),
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "production_watchlist_enabled": False,
            "production_write_enabled": False,
            "json_path": str(json_path),
            "groups_csv_path": str(groups_csv_path),
            "markdown_path": str(markdown_path),
            "metadata": {
                "primary_horizon": primary_horizon,
                "artifact_metadata": review.get("metadata") or {},
            },
        },
        "groups": [
            _group_row(
                item,
                run_id=run_id,
                review_start_date=review_start_date,
                review_end_date=review_end_date,
                payload_primary_horizon=primary_horizon,
                review_artifact_path=json_path,
            )
            for item in groups
        ],
    }


def import_shadow_analytics_review(
    path: str | Path,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    """Import one artifact or a directory of P15 artifacts into ops tables."""
    input_path = Path(path)
    paths = _review_paths(input_path)
    run_ids: list[str] = []
    group_count = 0
    with connect(service) as conn:
        with conn.cursor() as cur:
            for review_path in paths:
                rows = load_shadow_analytics_review_read_model_rows(review_path)
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


def _review_paths(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("operator_shadow_analytics_review_*.json"))
    return [path]


def _upsert_run(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_shadow_analytics_review_run (
        run_id, review_start_date, review_end_date, status, reviewer_id,
        source_p14_analytics_run_ids, thresholds, group_count,
        manual_review_required, auto_trade_enabled, production_watchlist_enabled,
        production_write_enabled, json_path, groups_csv_path, markdown_path,
        metadata
    )
    VALUES (
        %(run_id)s, %(review_start_date)s, %(review_end_date)s, %(status)s,
        %(reviewer_id)s, %(source_p14_analytics_run_ids)s::jsonb,
        %(thresholds)s::jsonb, %(group_count)s, %(manual_review_required)s,
        %(auto_trade_enabled)s, %(production_watchlist_enabled)s,
        %(production_write_enabled)s, %(json_path)s, %(groups_csv_path)s,
        %(markdown_path)s, %(metadata)s::jsonb
    )
    ON CONFLICT (run_id)
    DO UPDATE SET
        review_start_date = EXCLUDED.review_start_date,
        review_end_date = EXCLUDED.review_end_date,
        status = EXCLUDED.status,
        reviewer_id = EXCLUDED.reviewer_id,
        source_p14_analytics_run_ids = EXCLUDED.source_p14_analytics_run_ids,
        thresholds = EXCLUDED.thresholds,
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
            "source_p14_analytics_run_ids": json.dumps(
                row.get("source_p14_analytics_run_ids") or [],
                sort_keys=True,
            ),
            "thresholds": json.dumps(row.get("thresholds") or {}, sort_keys=True),
            "metadata": json.dumps(row.get("metadata") or {}, sort_keys=True),
        },
    )


def _upsert_group(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_shadow_analytics_review_group (
        review_group_id, run_id, review_start_date, review_end_date,
        source_p14_analytics_group_id, source_p14_analytics_run_id,
        group_key, shadow_layer, shadow_status, sample_count, complete_count,
        insufficient_data_count, horizon_metrics, review_status, review_bucket,
        evidence_summary, risk_notes, next_research_question, review_artifact_path,
        manual_review_required, auto_trade_enabled, production_watchlist_enabled,
        production_write_enabled, metadata
    )
    VALUES (
        %(review_group_id)s, %(run_id)s, %(review_start_date)s,
        %(review_end_date)s, %(source_p14_analytics_group_id)s,
        %(source_p14_analytics_run_id)s, %(group_key)s, %(shadow_layer)s,
        %(shadow_status)s, %(sample_count)s, %(complete_count)s,
        %(insufficient_data_count)s, %(horizon_metrics)s::jsonb,
        %(review_status)s, %(review_bucket)s, %(evidence_summary)s,
        %(risk_notes)s, %(next_research_question)s, %(review_artifact_path)s,
        %(manual_review_required)s, %(auto_trade_enabled)s,
        %(production_watchlist_enabled)s, %(production_write_enabled)s,
        %(metadata)s::jsonb
    )
    ON CONFLICT (review_group_id)
    DO UPDATE SET
        run_id = EXCLUDED.run_id,
        review_start_date = EXCLUDED.review_start_date,
        review_end_date = EXCLUDED.review_end_date,
        source_p14_analytics_group_id = EXCLUDED.source_p14_analytics_group_id,
        source_p14_analytics_run_id = EXCLUDED.source_p14_analytics_run_id,
        group_key = EXCLUDED.group_key,
        shadow_layer = EXCLUDED.shadow_layer,
        shadow_status = EXCLUDED.shadow_status,
        sample_count = EXCLUDED.sample_count,
        complete_count = EXCLUDED.complete_count,
        insufficient_data_count = EXCLUDED.insufficient_data_count,
        horizon_metrics = EXCLUDED.horizon_metrics,
        review_status = EXCLUDED.review_status,
        review_bucket = EXCLUDED.review_bucket,
        evidence_summary = EXCLUDED.evidence_summary,
        risk_notes = EXCLUDED.risk_notes,
        next_research_question = EXCLUDED.next_research_question,
        review_artifact_path = EXCLUDED.review_artifact_path,
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
    payload_primary_horizon: str,
    review_artifact_path: Path,
) -> dict[str, Any]:
    _validate_safety_fields(item)

    source_group_id = _required_text(item, "source_p14_analytics_group_id")
    review_status = _required_text(item, "review_status")
    return {
        "review_group_id": _review_group_id(
            run_id=run_id,
            source_p14_analytics_group_id=source_group_id,
            review_status=review_status,
        ),
        "run_id": run_id,
        "review_start_date": review_start_date,
        "review_end_date": review_end_date,
        "source_p14_analytics_group_id": source_group_id,
        "source_p14_analytics_run_id": _required_text(item, "source_p14_analytics_run_id"),
        "group_key": _required_text(item, "group_key"),
        "shadow_layer": _required_text(item, "shadow_layer"),
        "shadow_status": _required_text(item, "shadow_status"),
        "sample_count": int(item.get("sample_count") or 0),
        "complete_count": int(item.get("complete_count") or 0),
        "insufficient_data_count": int(item.get("insufficient_data_count") or 0),
        "horizon_metrics": _horizon_metrics(item, payload_primary_horizon),
        "review_status": review_status,
        "review_bucket": _required_text(item, "review_bucket"),
        "evidence_summary": str(item.get("evidence_summary") or ""),
        "risk_notes": str(item.get("risk_notes") or ""),
        "next_research_question": str(item.get("next_research_question") or ""),
        "review_artifact_path": str(review_artifact_path),
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
        "metadata": item.get("metadata") or {},
    }


def _horizon_metrics(item: dict[str, Any], payload_primary_horizon: str) -> dict[str, Any]:
    horizon_metrics = item.get("horizon_metrics")
    if isinstance(horizon_metrics, dict):
        return horizon_metrics

    primary_metrics = item.get("primary_horizon_metrics")
    if not isinstance(primary_metrics, dict):
        return {}

    primary_horizon = str(item.get("primary_horizon") or payload_primary_horizon or "")
    if not primary_horizon:
        return {}
    return {primary_horizon: primary_metrics}


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


def _review_group_id(*, run_id: str, source_p14_analytics_group_id: str, review_status: str) -> str:
    raw = "|".join([run_id, source_p14_analytics_group_id, review_status])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"operator_shadow_analytics_review:{run_id}:{digest}"


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
