from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect


def load_experiment_replay_read_model_rows(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)
    review = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(review, dict):
        raise ValueError(f"operator experiment replay review must be a JSON object: {json_path}")

    if _bool_value(review.get("auto_trade_enabled")) is True:
        raise ValueError("auto_trade_not_allowed")
    if _bool_value(review.get("manual_review_required", True)) is not True:
        raise ValueError("manual_review_required")
    if _bool_value(review.get("production_write_enabled", False)) is True:
        raise ValueError("production_write_not_allowed")

    run_id = str(review.get("run_id") or "")
    replay_start_date = str(review.get("replay_start_date") or "")
    replay_end_date = str(review.get("replay_end_date") or "")
    if not run_id:
        raise ValueError(f"operator experiment replay review requires run_id: {json_path}")
    if not replay_start_date:
        raise ValueError(f"operator experiment replay review requires replay_start_date: {json_path}")
    if not replay_end_date:
        raise ValueError(f"operator experiment replay review requires replay_end_date: {json_path}")

    results = [item for item in review.get("results", []) if isinstance(item, dict)]
    results_csv_path, markdown_path = _artifact_paths(json_path)
    return {
        "run": {
            "run_id": run_id,
            "replay_start_date": replay_start_date,
            "replay_end_date": replay_end_date,
            "status": str(review.get("status") or ""),
            "result_count": int(review.get("result_count") or len(results)),
            "status_counts": review.get("status_counts") or {},
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "production_write_enabled": False,
            "json_path": str(json_path),
            "results_csv_path": str(results_csv_path),
            "markdown_path": str(markdown_path),
            "metadata": {},
        },
        "results": [
            _result_row(item, run_id=run_id, replay_artifact_path=json_path)
            for item in results
        ],
    }


def import_experiment_replay_review(
    path: str | Path,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    input_path = Path(path)
    paths = _replay_paths(input_path)
    run_ids: list[str] = []
    result_count = 0
    with connect(service) as conn:
        with conn.cursor() as cur:
            for replay_path in paths:
                rows = load_experiment_replay_read_model_rows(replay_path)
                _upsert_run(cur, rows["run"])
                for result in rows["results"]:
                    _upsert_result(cur, result)
                    result_count += 1
                run_ids.append(str(rows["run"]["run_id"]))
    return {
        "imported_count": len(paths),
        "result_count": result_count,
        "run_ids": run_ids,
    }


def _replay_paths(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("operator_experiment_replay_*.json"))
    return [path]


def _upsert_run(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_experiment_replay_run (
        run_id, replay_start_date, replay_end_date, status, result_count,
        status_counts, manual_review_required, auto_trade_enabled,
        production_write_enabled, json_path, results_csv_path, markdown_path,
        metadata
    )
    VALUES (
        %(run_id)s, %(replay_start_date)s, %(replay_end_date)s, %(status)s,
        %(result_count)s, %(status_counts)s::jsonb,
        %(manual_review_required)s, %(auto_trade_enabled)s,
        %(production_write_enabled)s, %(json_path)s, %(results_csv_path)s,
        %(markdown_path)s, %(metadata)s::jsonb
    )
    ON CONFLICT (run_id)
    DO UPDATE SET
        replay_start_date = EXCLUDED.replay_start_date,
        replay_end_date = EXCLUDED.replay_end_date,
        status = EXCLUDED.status,
        result_count = EXCLUDED.result_count,
        status_counts = EXCLUDED.status_counts,
        manual_review_required = EXCLUDED.manual_review_required,
        auto_trade_enabled = EXCLUDED.auto_trade_enabled,
        production_write_enabled = EXCLUDED.production_write_enabled,
        json_path = EXCLUDED.json_path,
        results_csv_path = EXCLUDED.results_csv_path,
        markdown_path = EXCLUDED.markdown_path,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    cur.execute(
        sql,
        {
            **row,
            "status_counts": json.dumps(row.get("status_counts") or {}, sort_keys=True),
            "metadata": json.dumps(row.get("metadata") or {}, sort_keys=True),
        },
    )


def _upsert_result(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_experiment_replay_result (
        replay_result_id, run_id, proposal_id, source_p10_proposal_run_id,
        source_p9_analytics_run_id, replay_start_date, replay_end_date,
        replay_input_artifact_paths, validation_method, replay_status,
        sample_count, passed_count, failed_count, metric_summary,
        failure_reason, defer_reason, manual_review_required,
        auto_trade_enabled, production_write_enabled, replay_artifact_path,
        metadata
    )
    VALUES (
        %(replay_result_id)s, %(run_id)s, %(proposal_id)s,
        %(source_p10_proposal_run_id)s, %(source_p9_analytics_run_id)s,
        %(replay_start_date)s, %(replay_end_date)s,
        %(replay_input_artifact_paths)s::jsonb, %(validation_method)s,
        %(replay_status)s, %(sample_count)s, %(passed_count)s,
        %(failed_count)s, %(metric_summary)s::jsonb, %(failure_reason)s,
        %(defer_reason)s, %(manual_review_required)s,
        %(auto_trade_enabled)s, %(production_write_enabled)s,
        %(replay_artifact_path)s, %(metadata)s::jsonb
    )
    ON CONFLICT (replay_result_id)
    DO UPDATE SET
        run_id = EXCLUDED.run_id,
        proposal_id = EXCLUDED.proposal_id,
        source_p10_proposal_run_id = EXCLUDED.source_p10_proposal_run_id,
        source_p9_analytics_run_id = EXCLUDED.source_p9_analytics_run_id,
        replay_start_date = EXCLUDED.replay_start_date,
        replay_end_date = EXCLUDED.replay_end_date,
        replay_input_artifact_paths = EXCLUDED.replay_input_artifact_paths,
        validation_method = EXCLUDED.validation_method,
        replay_status = EXCLUDED.replay_status,
        sample_count = EXCLUDED.sample_count,
        passed_count = EXCLUDED.passed_count,
        failed_count = EXCLUDED.failed_count,
        metric_summary = EXCLUDED.metric_summary,
        failure_reason = EXCLUDED.failure_reason,
        defer_reason = EXCLUDED.defer_reason,
        manual_review_required = EXCLUDED.manual_review_required,
        auto_trade_enabled = EXCLUDED.auto_trade_enabled,
        production_write_enabled = EXCLUDED.production_write_enabled,
        replay_artifact_path = EXCLUDED.replay_artifact_path,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    cur.execute(
        sql,
        {
            **row,
            "replay_input_artifact_paths": json.dumps(
                row.get("replay_input_artifact_paths") or [],
                sort_keys=True,
            ),
            "metric_summary": json.dumps(row.get("metric_summary") or {}, sort_keys=True),
            "metadata": json.dumps(row.get("metadata") or {}, sort_keys=True),
        },
    )


def _result_row(
    item: dict[str, Any],
    *,
    run_id: str,
    replay_artifact_path: Path,
) -> dict[str, Any]:
    if _bool_value(item.get("auto_trade_enabled")) is True:
        raise ValueError("auto_trade_not_allowed")
    if _bool_value(item.get("manual_review_required", True)) is not True:
        raise ValueError("manual_review_required")
    if _bool_value(item.get("production_write_enabled", False)) is True:
        raise ValueError("production_write_not_allowed")

    replay_result_id = str(item.get("replay_result_id") or "")
    if not replay_result_id:
        raise ValueError("required_field_missing: replay_result_id")
    return {
        "replay_result_id": replay_result_id,
        "run_id": run_id,
        "proposal_id": _required_text(item, "proposal_id"),
        "source_p10_proposal_run_id": _required_text(item, "source_p10_proposal_run_id"),
        "source_p9_analytics_run_id": _required_text(item, "source_p9_analytics_run_id"),
        "replay_start_date": _required_text(item, "replay_start_date"),
        "replay_end_date": _required_text(item, "replay_end_date"),
        "replay_input_artifact_paths": _list_value(item.get("replay_input_artifact_paths")),
        "validation_method": _required_text(item, "validation_method"),
        "replay_status": _required_text(item, "replay_status"),
        "sample_count": int(item.get("sample_count") or 0),
        "passed_count": int(item.get("passed_count") or 0),
        "failed_count": int(item.get("failed_count") or 0),
        "metric_summary": _dict_value(item.get("metric_summary")),
        "failure_reason": str(item.get("failure_reason") or ""),
        "defer_reason": str(item.get("defer_reason") or ""),
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_write_enabled": False,
        "replay_artifact_path": str(replay_artifact_path),
        "metadata": {},
    }


def _artifact_paths(json_path: Path) -> tuple[Path, Path]:
    return (
        json_path.with_name(f"{json_path.stem}_results.csv"),
        json_path.with_suffix(".md"),
    )


def _required_text(item: dict[str, Any], column: str) -> str:
    value = item.get(column)
    if value is None or str(value).strip() == "":
        raise ValueError(f"required_field_missing: {column}")
    return str(value).strip()


def _list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value]
    return [str(value)]


def _dict_value(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    parsed = json.loads(str(value))
    if not isinstance(parsed, dict):
        raise ValueError("metric_summary_must_be_object")
    return parsed


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
