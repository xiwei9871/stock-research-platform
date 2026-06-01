from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect


def load_shadow_review_decision_read_model_rows(path: str | Path) -> dict[str, Any]:
    """Load one P16 JSON artifact into run and group read-model rows."""
    json_path = Path(path)
    decisions = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(decisions, dict):
        raise ValueError(f"operator shadow review decisions must be a JSON object: {json_path}")

    _validate_safety_fields(decisions)

    run_id = _required_text(decisions, "run_id")
    decision_date = _required_text(decisions, "decision_date")
    groups = [item for item in decisions.get("groups", []) if isinstance(item, dict)]
    groups_csv_path, markdown_path = _artifact_paths(json_path)

    return {
        "run": {
            "run_id": run_id,
            "decision_date": decision_date,
            "status": _required_text(decisions, "status"),
            "operator_id": _required_text(decisions, "operator_id"),
            "source_p15_review_run_ids": decisions.get("source_p15_review_run_ids") or [],
            "group_count": int(decisions.get("group_count") or len(groups)),
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "production_watchlist_enabled": False,
            "production_write_enabled": False,
            "json_path": str(json_path),
            "groups_csv_path": str(groups_csv_path),
            "markdown_path": str(markdown_path),
            "metadata": decisions.get("metadata") or {},
        },
        "groups": [
            _group_row(
                item,
                run_id=run_id,
                decision_date=decision_date,
                decision_artifact_path=json_path,
            )
            for item in groups
        ],
    }


def import_shadow_review_decisions(
    path: str | Path,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    """Import one artifact or a directory of P16 artifacts into ops tables."""
    input_path = Path(path)
    paths = _decision_paths(input_path)
    run_ids: list[str] = []
    group_count = 0
    with connect(service) as conn:
        with conn.cursor() as cur:
            for decision_path in paths:
                rows = load_shadow_review_decision_read_model_rows(decision_path)
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


def _decision_paths(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("operator_shadow_review_decisions_*.json"))
    return [path]


def _upsert_run(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_shadow_review_decision_run (
        run_id, decision_date, status, operator_id, source_p15_review_run_ids,
        group_count, manual_review_required, auto_trade_enabled,
        production_watchlist_enabled, production_write_enabled, json_path,
        groups_csv_path, markdown_path, metadata
    )
    VALUES (
        %(run_id)s, %(decision_date)s, %(status)s, %(operator_id)s,
        %(source_p15_review_run_ids)s::jsonb, %(group_count)s,
        %(manual_review_required)s, %(auto_trade_enabled)s,
        %(production_watchlist_enabled)s, %(production_write_enabled)s,
        %(json_path)s, %(groups_csv_path)s, %(markdown_path)s,
        %(metadata)s::jsonb
    )
    ON CONFLICT (run_id)
    DO UPDATE SET
        decision_date = EXCLUDED.decision_date,
        status = EXCLUDED.status,
        operator_id = EXCLUDED.operator_id,
        source_p15_review_run_ids = EXCLUDED.source_p15_review_run_ids,
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
            "source_p15_review_run_ids": json.dumps(
                row.get("source_p15_review_run_ids") or [],
                sort_keys=True,
            ),
            "metadata": json.dumps(row.get("metadata") or {}, sort_keys=True),
        },
    )


def _upsert_group(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_shadow_review_decision_group (
        decision_group_id, run_id, decision_date, source_p15_review_group_id,
        source_p15_review_run_id, source_p14_analytics_group_id,
        source_p14_analytics_run_id, group_key, shadow_layer, shadow_status,
        sample_count, complete_count, insufficient_data_count, review_status,
        review_bucket, decision_status, decision_bucket, decision_reason,
        required_next_action, evidence_summary, risk_notes,
        next_research_question, decision_artifact_path, manual_review_required,
        auto_trade_enabled, production_watchlist_enabled, production_write_enabled,
        metadata
    )
    VALUES (
        %(decision_group_id)s, %(run_id)s, %(decision_date)s,
        %(source_p15_review_group_id)s, %(source_p15_review_run_id)s,
        %(source_p14_analytics_group_id)s, %(source_p14_analytics_run_id)s,
        %(group_key)s, %(shadow_layer)s, %(shadow_status)s, %(sample_count)s,
        %(complete_count)s, %(insufficient_data_count)s, %(review_status)s,
        %(review_bucket)s, %(decision_status)s, %(decision_bucket)s,
        %(decision_reason)s, %(required_next_action)s, %(evidence_summary)s,
        %(risk_notes)s, %(next_research_question)s, %(decision_artifact_path)s,
        %(manual_review_required)s, %(auto_trade_enabled)s,
        %(production_watchlist_enabled)s, %(production_write_enabled)s,
        %(metadata)s::jsonb
    )
    ON CONFLICT (decision_group_id)
    DO UPDATE SET
        run_id = EXCLUDED.run_id,
        decision_date = EXCLUDED.decision_date,
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
        decision_reason = EXCLUDED.decision_reason,
        required_next_action = EXCLUDED.required_next_action,
        evidence_summary = EXCLUDED.evidence_summary,
        risk_notes = EXCLUDED.risk_notes,
        next_research_question = EXCLUDED.next_research_question,
        decision_artifact_path = EXCLUDED.decision_artifact_path,
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


def _group_row(
    item: dict[str, Any],
    *,
    run_id: str,
    decision_date: str,
    decision_artifact_path: Path,
) -> dict[str, Any]:
    _validate_safety_fields(item)

    source_group_id = _required_text(item, "source_p15_review_group_id")
    decision_status = _required_text(item, "decision_status")
    return {
        "decision_group_id": _decision_group_id(
            run_id=run_id,
            source_p15_review_group_id=source_group_id,
            decision_status=decision_status,
        ),
        "run_id": run_id,
        "decision_date": decision_date,
        "source_p15_review_group_id": source_group_id,
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
        "decision_status": decision_status,
        "decision_bucket": _required_text(item, "decision_bucket"),
        "decision_reason": str(item.get("decision_reason") or ""),
        "required_next_action": str(item.get("required_next_action") or ""),
        "evidence_summary": str(item.get("evidence_summary") or ""),
        "risk_notes": str(item.get("risk_notes") or ""),
        "next_research_question": str(item.get("next_research_question") or ""),
        "decision_artifact_path": str(decision_artifact_path),
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
        json_path.with_name(f"{json_path.stem}_groups.csv"),
        json_path.with_suffix(".md"),
    )


def _decision_group_id(*, run_id: str, source_p15_review_group_id: str, decision_status: str) -> str:
    raw = "|".join([run_id, source_p15_review_group_id, decision_status])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"operator_shadow_review_decision:{run_id}:{digest}"


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
