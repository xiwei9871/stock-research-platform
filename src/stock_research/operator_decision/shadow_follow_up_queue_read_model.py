from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect


def load_shadow_follow_up_queue_read_model_rows(path: str | Path) -> dict[str, Any]:
    """Load one P17 JSON artifact into run and item read-model rows."""
    json_path = Path(path)
    queue = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(queue, dict):
        raise ValueError(f"operator shadow follow-up queue must be a JSON object: {json_path}")

    _validate_safety_fields(queue)

    run_id = _required_text(queue, "run_id")
    follow_up_date = _required_text(queue, "follow_up_date")
    items = [item for item in queue.get("items", []) if isinstance(item, dict)]
    items_csv_path, markdown_path = _artifact_paths(json_path)

    return {
        "run": {
            "run_id": run_id,
            "follow_up_date": follow_up_date,
            "status": _required_text(queue, "status"),
            "operator_id": _required_text(queue, "operator_id"),
            "source_p16_decision_run_ids": queue.get("source_p16_decision_run_ids") or [],
            "item_count": int(queue.get("item_count") or len(items)),
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "production_watchlist_enabled": False,
            "production_write_enabled": False,
            "json_path": str(json_path),
            "items_csv_path": str(items_csv_path),
            "markdown_path": str(markdown_path),
            "metadata": queue.get("metadata") or {},
        },
        "items": [
            _item_row(
                item,
                run_id=run_id,
                follow_up_date=follow_up_date,
                follow_up_artifact_path=json_path,
            )
            for item in items
        ],
    }


def import_shadow_follow_up_queue(
    path: str | Path,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    """Import one artifact or a directory of P17 artifacts into ops tables."""
    input_path = Path(path)
    paths = _queue_paths(input_path)
    run_ids: list[str] = []
    item_count = 0
    with connect(service) as conn:
        with conn.cursor() as cur:
            for queue_path in paths:
                rows = load_shadow_follow_up_queue_read_model_rows(queue_path)
                _upsert_run(cur, rows["run"])
                for item in rows["items"]:
                    _upsert_item(cur, item)
                    item_count += 1
                run_ids.append(str(rows["run"]["run_id"]))
    return {
        "imported_count": len(paths),
        "item_count": item_count,
        "run_ids": run_ids,
    }


def _queue_paths(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("operator_shadow_follow_up_queue_*.json"))
    return [path]


def _upsert_run(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_shadow_follow_up_run (
        run_id, follow_up_date, status, operator_id, source_p16_decision_run_ids,
        item_count, manual_review_required, auto_trade_enabled,
        production_watchlist_enabled, production_write_enabled, json_path,
        items_csv_path, markdown_path, metadata
    )
    VALUES (
        %(run_id)s, %(follow_up_date)s, %(status)s, %(operator_id)s,
        %(source_p16_decision_run_ids)s::jsonb, %(item_count)s,
        %(manual_review_required)s, %(auto_trade_enabled)s,
        %(production_watchlist_enabled)s, %(production_write_enabled)s,
        %(json_path)s, %(items_csv_path)s, %(markdown_path)s,
        %(metadata)s::jsonb
    )
    ON CONFLICT (run_id)
    DO UPDATE SET
        follow_up_date = EXCLUDED.follow_up_date,
        status = EXCLUDED.status,
        operator_id = EXCLUDED.operator_id,
        source_p16_decision_run_ids = EXCLUDED.source_p16_decision_run_ids,
        item_count = EXCLUDED.item_count,
        manual_review_required = EXCLUDED.manual_review_required,
        auto_trade_enabled = EXCLUDED.auto_trade_enabled,
        production_watchlist_enabled = EXCLUDED.production_watchlist_enabled,
        production_write_enabled = EXCLUDED.production_write_enabled,
        json_path = EXCLUDED.json_path,
        items_csv_path = EXCLUDED.items_csv_path,
        markdown_path = EXCLUDED.markdown_path,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    cur.execute(
        sql,
        {
            **row,
            "source_p16_decision_run_ids": json.dumps(
                row.get("source_p16_decision_run_ids") or [],
                sort_keys=True,
            ),
            "metadata": json.dumps(row.get("metadata") or {}, sort_keys=True),
        },
    )


def _upsert_item(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_shadow_follow_up_item (
        follow_up_item_id, run_id, follow_up_date, source_p16_decision_group_id,
        source_p16_decision_run_id, source_p15_review_group_id,
        source_p15_review_run_id, source_p14_analytics_group_id,
        source_p14_analytics_run_id, group_key, shadow_layer, shadow_status,
        sample_count, complete_count, insufficient_data_count, review_status,
        review_bucket, decision_status, decision_bucket, follow_up_status,
        priority_bucket, required_input, follow_up_reason, decision_reason,
        required_next_action, evidence_summary, risk_notes,
        next_research_question, follow_up_artifact_path, manual_review_required,
        auto_trade_enabled, production_watchlist_enabled, production_write_enabled,
        metadata
    )
    VALUES (
        %(follow_up_item_id)s, %(run_id)s, %(follow_up_date)s,
        %(source_p16_decision_group_id)s, %(source_p16_decision_run_id)s,
        %(source_p15_review_group_id)s, %(source_p15_review_run_id)s,
        %(source_p14_analytics_group_id)s, %(source_p14_analytics_run_id)s,
        %(group_key)s, %(shadow_layer)s, %(shadow_status)s, %(sample_count)s,
        %(complete_count)s, %(insufficient_data_count)s, %(review_status)s,
        %(review_bucket)s, %(decision_status)s, %(decision_bucket)s,
        %(follow_up_status)s, %(priority_bucket)s, %(required_input)s,
        %(follow_up_reason)s, %(decision_reason)s, %(required_next_action)s,
        %(evidence_summary)s, %(risk_notes)s, %(next_research_question)s,
        %(follow_up_artifact_path)s, %(manual_review_required)s,
        %(auto_trade_enabled)s, %(production_watchlist_enabled)s,
        %(production_write_enabled)s, %(metadata)s::jsonb
    )
    ON CONFLICT (follow_up_item_id)
    DO UPDATE SET
        run_id = EXCLUDED.run_id,
        follow_up_date = EXCLUDED.follow_up_date,
        source_p16_decision_group_id = EXCLUDED.source_p16_decision_group_id,
        source_p16_decision_run_id = EXCLUDED.source_p16_decision_run_id,
        source_p15_review_group_id = EXCLUDED.source_p15_review_group_id,
        source_p15_review_run_id = EXCLUDED.source_p15_review_run_id,
        source_p14_analytics_group_id = EXCLUDED.source_p14_analytics_group_id,
        source_p14_analytics_run_id = EXCLUDED.source_p14_analytics_run_id,
        group_key = EXCLUDED.group_key,
        shadow_layer = EXCLUDED.shadow_layer,
        shadow_status = EXCLUDED.shadow_status,
        sample_count = EXCLUDED.sample_count,
        complete_count = EXCLUDED.complete_count,
        insufficient_data_count = EXCLUDED.insufficient_data_count,
        review_status = EXCLUDED.review_status,
        review_bucket = EXCLUDED.review_bucket,
        decision_status = EXCLUDED.decision_status,
        decision_bucket = EXCLUDED.decision_bucket,
        follow_up_status = EXCLUDED.follow_up_status,
        priority_bucket = EXCLUDED.priority_bucket,
        required_input = EXCLUDED.required_input,
        follow_up_reason = EXCLUDED.follow_up_reason,
        decision_reason = EXCLUDED.decision_reason,
        required_next_action = EXCLUDED.required_next_action,
        evidence_summary = EXCLUDED.evidence_summary,
        risk_notes = EXCLUDED.risk_notes,
        next_research_question = EXCLUDED.next_research_question,
        follow_up_artifact_path = EXCLUDED.follow_up_artifact_path,
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
            "metadata": json.dumps(row.get("metadata") or {}, sort_keys=True),
        },
    )


def _item_row(
    item: dict[str, Any],
    *,
    run_id: str,
    follow_up_date: str,
    follow_up_artifact_path: Path,
) -> dict[str, Any]:
    _validate_safety_fields(item)

    source_group_id = _required_text(item, "source_p16_decision_group_id")
    follow_up_status = _required_text(item, "follow_up_status")
    return {
        "follow_up_item_id": _follow_up_item_id(
            run_id=run_id,
            source_p16_decision_group_id=source_group_id,
            follow_up_status=follow_up_status,
        ),
        "run_id": run_id,
        "follow_up_date": follow_up_date,
        "source_p16_decision_group_id": source_group_id,
        "source_p16_decision_run_id": _required_text(item, "source_p16_decision_run_id"),
        "source_p15_review_group_id": _required_text(item, "source_p15_review_group_id"),
        "source_p15_review_run_id": _required_text(item, "source_p15_review_run_id"),
        "source_p14_analytics_group_id": _required_text(item, "source_p14_analytics_group_id"),
        "source_p14_analytics_run_id": _required_text(item, "source_p14_analytics_run_id"),
        "group_key": _required_text(item, "group_key"),
        "shadow_layer": _required_text(item, "shadow_layer"),
        "shadow_status": _required_text(item, "shadow_status"),
        "sample_count": int(item.get("sample_count") or 0),
        "complete_count": int(item.get("complete_count") or 0),
        "insufficient_data_count": int(item.get("insufficient_data_count") or 0),
        "review_status": _required_text(item, "review_status"),
        "review_bucket": _required_text(item, "review_bucket"),
        "decision_status": _required_text(item, "decision_status"),
        "decision_bucket": _required_text(item, "decision_bucket"),
        "follow_up_status": follow_up_status,
        "priority_bucket": _required_text(item, "priority_bucket"),
        "required_input": _required_text(item, "required_input"),
        "follow_up_reason": str(item.get("follow_up_reason") or ""),
        "decision_reason": str(item.get("decision_reason") or ""),
        "required_next_action": str(item.get("required_next_action") or ""),
        "evidence_summary": str(item.get("evidence_summary") or ""),
        "risk_notes": str(item.get("risk_notes") or ""),
        "next_research_question": str(item.get("next_research_question") or ""),
        "follow_up_artifact_path": str(follow_up_artifact_path),
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
        "metadata": item.get("metadata") or {},
    }


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
        json_path.with_name(f"{json_path.stem}_items.csv"),
        json_path.with_suffix(".md"),
    )


def _follow_up_item_id(*, run_id: str, source_p16_decision_group_id: str, follow_up_status: str) -> str:
    raw = "|".join([run_id, source_p16_decision_group_id, follow_up_status])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"operator_shadow_follow_up:{run_id}:{digest}"


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
