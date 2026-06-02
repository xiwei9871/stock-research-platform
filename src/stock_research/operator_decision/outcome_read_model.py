from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect


def load_decision_outcome_read_model_rows(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)
    review = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(review, dict):
        raise ValueError(f"operator decision outcome review must be a JSON object: {json_path}")

    if _bool_value(review.get("auto_trade_enabled")) is True:
        raise ValueError("auto_trade_not_allowed")
    if _bool_value(review.get("manual_review_required", True)) is not True:
        raise ValueError("manual_review_required")

    run_id = str(review.get("run_id") or "")
    start_date = str(review.get("review_start_date") or "")
    end_date = str(review.get("review_end_date") or "")
    if not run_id:
        raise ValueError(f"operator decision outcome review requires run_id: {json_path}")
    if not start_date or not end_date:
        raise ValueError(f"operator decision outcome review requires review date range: {json_path}")

    details_csv_path, summary_csv_path, markdown_path = _artifact_paths(json_path)
    outcomes = [item for item in review.get("outcomes", []) if isinstance(item, dict)]
    return {
        "run": {
            "run_id": run_id,
            "review_start_date": start_date,
            "review_end_date": end_date,
            "status": str(review.get("status") or ""),
            "outcome_count": int(review.get("outcome_count") or len(outcomes)),
            "summary_count": int(review.get("summary_count") or len(review.get("summary", []) or [])),
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "json_path": str(json_path),
            "details_csv_path": str(details_csv_path),
            "summary_csv_path": str(summary_csv_path),
            "markdown_path": str(markdown_path),
            "metadata": {
                "horizons": review.get("horizons") or [],
                "summary": review.get("summary") or [],
            },
        },
        "events": [
            _event_row(item, run_id=run_id, outcome_artifact_path=json_path)
            for item in outcomes
        ],
    }


def import_decision_outcome_review(
    path: str | Path,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    input_path = Path(path)
    paths = _review_paths(input_path)
    run_ids: list[str] = []
    event_count = 0
    with connect(service) as conn:
        with conn.cursor() as cur:
            for review_path in paths:
                rows = load_decision_outcome_read_model_rows(review_path)
                _upsert_run(cur, rows["run"])
                for event in rows["events"]:
                    _upsert_event(cur, event)
                    event_count += 1
                run_ids.append(str(rows["run"]["run_id"]))
    return {
        "imported_count": len(paths),
        "event_count": event_count,
        "run_ids": run_ids,
    }


def _review_paths(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("operator_decision_outcome_review_*.json"))
    return [path]


def _upsert_run(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_decision_outcome_run (
        run_id, review_start_date, review_end_date, status, outcome_count,
        summary_count, manual_review_required, auto_trade_enabled, json_path,
        details_csv_path, summary_csv_path, markdown_path, metadata
    )
    VALUES (
        %(run_id)s, %(review_start_date)s, %(review_end_date)s, %(status)s,
        %(outcome_count)s, %(summary_count)s, %(manual_review_required)s,
        %(auto_trade_enabled)s, %(json_path)s, %(details_csv_path)s,
        %(summary_csv_path)s, %(markdown_path)s, %(metadata)s::jsonb
    )
    ON CONFLICT (run_id)
    DO UPDATE SET
        review_start_date = EXCLUDED.review_start_date,
        review_end_date = EXCLUDED.review_end_date,
        status = EXCLUDED.status,
        outcome_count = EXCLUDED.outcome_count,
        summary_count = EXCLUDED.summary_count,
        manual_review_required = EXCLUDED.manual_review_required,
        auto_trade_enabled = EXCLUDED.auto_trade_enabled,
        json_path = EXCLUDED.json_path,
        details_csv_path = EXCLUDED.details_csv_path,
        summary_csv_path = EXCLUDED.summary_csv_path,
        markdown_path = EXCLUDED.markdown_path,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    cur.execute(sql, {**row, "metadata": json.dumps(row.get("metadata") or {}, sort_keys=True)})


def _upsert_event(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_decision_outcome_event (
        outcome_event_id, run_id, decision_event_id, review_session_id,
        review_date, asset_id, stock_code, stock_name, decision_label,
        source_context, outcome_status, available_future_bars,
        base_trade_date, base_close, forward_returns, max_high_returns,
        max_low_drawdowns, manual_review_required, auto_trade_enabled,
        source_artifact_path, outcome_artifact_path, metadata
    )
    VALUES (
        %(outcome_event_id)s, %(run_id)s, %(decision_event_id)s,
        %(review_session_id)s, %(review_date)s, %(asset_id)s, %(stock_code)s,
        %(stock_name)s, %(decision_label)s, %(source_context)s,
        %(outcome_status)s, %(available_future_bars)s, %(base_trade_date)s,
        %(base_close)s, %(forward_returns)s::jsonb, %(max_high_returns)s::jsonb,
        %(max_low_drawdowns)s::jsonb, %(manual_review_required)s,
        %(auto_trade_enabled)s, %(source_artifact_path)s,
        %(outcome_artifact_path)s, %(metadata)s::jsonb
    )
    ON CONFLICT (outcome_event_id)
    DO UPDATE SET
        run_id = EXCLUDED.run_id,
        decision_event_id = EXCLUDED.decision_event_id,
        review_session_id = EXCLUDED.review_session_id,
        review_date = EXCLUDED.review_date,
        asset_id = EXCLUDED.asset_id,
        stock_code = EXCLUDED.stock_code,
        stock_name = EXCLUDED.stock_name,
        decision_label = EXCLUDED.decision_label,
        source_context = EXCLUDED.source_context,
        outcome_status = EXCLUDED.outcome_status,
        available_future_bars = EXCLUDED.available_future_bars,
        base_trade_date = EXCLUDED.base_trade_date,
        base_close = EXCLUDED.base_close,
        forward_returns = EXCLUDED.forward_returns,
        max_high_returns = EXCLUDED.max_high_returns,
        max_low_drawdowns = EXCLUDED.max_low_drawdowns,
        manual_review_required = EXCLUDED.manual_review_required,
        auto_trade_enabled = EXCLUDED.auto_trade_enabled,
        source_artifact_path = EXCLUDED.source_artifact_path,
        outcome_artifact_path = EXCLUDED.outcome_artifact_path,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    params = {
        **row,
        "forward_returns": json.dumps(row.get("forward_returns") or {}, sort_keys=True),
        "max_high_returns": json.dumps(row.get("max_high_returns") or {}, sort_keys=True),
        "max_low_drawdowns": json.dumps(row.get("max_low_drawdowns") or {}, sort_keys=True),
        "metadata": json.dumps(row.get("metadata") or {}, sort_keys=True),
    }
    cur.execute(sql, params)


def _event_row(item: dict[str, Any], *, run_id: str, outcome_artifact_path: Path) -> dict[str, Any]:
    if _bool_value(item.get("auto_trade_enabled")) is True:
        raise ValueError("auto_trade_not_allowed")
    if _bool_value(item.get("manual_review_required", True)) is not True:
        raise ValueError("manual_review_required")

    decision_event_id = str(item.get("event_id") or "")
    source_artifact_path = str(item.get("source_artifact_path") or outcome_artifact_path)
    if not decision_event_id and not source_artifact_path:
        raise ValueError("missing_decision_event_or_source_artifact")
    return {
        "outcome_event_id": _outcome_event_id(
            run_id=run_id,
            decision_event_id=decision_event_id,
            source_artifact_path=source_artifact_path,
        ),
        "run_id": run_id,
        "decision_event_id": decision_event_id,
        "review_session_id": str(item.get("review_session_id") or ""),
        "review_date": str(item.get("review_date") or ""),
        "asset_id": str(item.get("asset_id") or ""),
        "stock_code": str(item.get("stock_code") or ""),
        "stock_name": str(item.get("stock_name") or ""),
        "decision_label": str(item.get("decision_label") or ""),
        "source_context": str(item.get("source_context") or ""),
        "outcome_status": str(item.get("outcome_status") or ""),
        "available_future_bars": int(item.get("available_future_bars") or 0),
        "base_trade_date": str(item.get("base_trade_date") or ""),
        "base_close": item.get("base_close"),
        "forward_returns": _metric_map(item, "forward_", "d_return"),
        "max_high_returns": _metric_map(item, "max_high_return_", "d"),
        "max_low_drawdowns": _metric_map(item, "max_low_drawdown_", "d"),
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "source_artifact_path": source_artifact_path,
        "outcome_artifact_path": str(outcome_artifact_path),
        "metadata": {
            "evidence_artifact_id": item.get("evidence_artifact_id") or "",
            "evidence_path": item.get("evidence_path") or "",
            "requires_follow_up": bool(item.get("requires_follow_up")),
            "follow_up_note": item.get("follow_up_note") or "",
            "notes": item.get("notes") or "",
        },
    }


def _artifact_paths(json_path: Path) -> tuple[Path, Path, Path]:
    return (
        json_path.with_name(f"{json_path.stem}_details.csv"),
        json_path.with_name(f"{json_path.stem}_summary.csv"),
        json_path.with_suffix(".md"),
    )


def _metric_map(item: dict[str, Any], prefix: str, suffix: str) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for key, value in item.items():
        text = str(key)
        if not text.startswith(prefix) or not text.endswith(suffix):
            continue
        horizon = text.removeprefix(prefix).removesuffix(suffix)
        if value is not None:
            metrics[horizon] = value
    return metrics


def _outcome_event_id(*, run_id: str, decision_event_id: str, source_artifact_path: str) -> str:
    raw = "|".join([run_id, decision_event_id, source_artifact_path])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"operator_decision_outcome:{run_id}:{digest}"


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
