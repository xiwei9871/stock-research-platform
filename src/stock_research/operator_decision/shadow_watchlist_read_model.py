from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect


def load_shadow_watchlist_read_model_rows(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)
    review = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(review, dict):
        raise ValueError(f"operator shadow watchlist review must be a JSON object: {json_path}")

    if _bool_value(review.get("auto_trade_enabled")) is True:
        raise ValueError("auto_trade_not_allowed")
    if _bool_value(review.get("manual_review_required", True)) is not True:
        raise ValueError("manual_review_required")
    if _bool_value(review.get("production_watchlist_enabled", False)) is True:
        raise ValueError("production_watchlist_not_allowed")
    if _bool_value(review.get("production_write_enabled", False)) is True:
        raise ValueError("production_write_not_allowed")

    run_id = str(review.get("run_id") or "")
    review_date = str(review.get("review_date") or "")
    if not run_id:
        raise ValueError(f"operator shadow watchlist review requires run_id: {json_path}")
    if not review_date:
        raise ValueError(f"operator shadow watchlist review requires review_date: {json_path}")

    candidates = [item for item in review.get("candidates", []) if isinstance(item, dict)]
    candidates_csv_path, markdown_path = _artifact_paths(json_path)
    return {
        "run": {
            "run_id": run_id,
            "review_date": review_date,
            "status": str(review.get("status") or ""),
            "candidate_count": int(review.get("candidate_count") or len(candidates)),
            "status_counts": review.get("status_counts") or {},
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "production_watchlist_enabled": False,
            "production_write_enabled": False,
            "json_path": str(json_path),
            "candidates_csv_path": str(candidates_csv_path),
            "markdown_path": str(markdown_path),
            "metadata": {},
        },
        "candidates": [
            _candidate_row(item, run_id=run_id, shadow_artifact_path=json_path)
            for item in candidates
        ],
    }


def import_shadow_watchlist_review(
    path: str | Path,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    input_path = Path(path)
    paths = _shadow_paths(input_path)
    run_ids: list[str] = []
    candidate_count = 0
    with connect(service) as conn:
        with conn.cursor() as cur:
            for shadow_path in paths:
                rows = load_shadow_watchlist_read_model_rows(shadow_path)
                _upsert_run(cur, rows["run"])
                for candidate in rows["candidates"]:
                    _upsert_candidate(cur, candidate)
                    candidate_count += 1
                run_ids.append(str(rows["run"]["run_id"]))
    return {
        "imported_count": len(paths),
        "candidate_count": candidate_count,
        "run_ids": run_ids,
    }


def _shadow_paths(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("operator_shadow_watchlist_*.json"))
    return [path]


def _upsert_run(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_shadow_watchlist_run (
        run_id, review_date, status, candidate_count, status_counts,
        manual_review_required, auto_trade_enabled,
        production_watchlist_enabled, production_write_enabled,
        json_path, candidates_csv_path, markdown_path, metadata
    )
    VALUES (
        %(run_id)s, %(review_date)s, %(status)s, %(candidate_count)s,
        %(status_counts)s::jsonb, %(manual_review_required)s,
        %(auto_trade_enabled)s, %(production_watchlist_enabled)s,
        %(production_write_enabled)s, %(json_path)s, %(candidates_csv_path)s,
        %(markdown_path)s, %(metadata)s::jsonb
    )
    ON CONFLICT (run_id)
    DO UPDATE SET
        review_date = EXCLUDED.review_date,
        status = EXCLUDED.status,
        candidate_count = EXCLUDED.candidate_count,
        status_counts = EXCLUDED.status_counts,
        manual_review_required = EXCLUDED.manual_review_required,
        auto_trade_enabled = EXCLUDED.auto_trade_enabled,
        production_watchlist_enabled = EXCLUDED.production_watchlist_enabled,
        production_write_enabled = EXCLUDED.production_write_enabled,
        json_path = EXCLUDED.json_path,
        candidates_csv_path = EXCLUDED.candidates_csv_path,
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


def _upsert_candidate(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_shadow_watchlist_candidate (
        shadow_candidate_id, run_id, replay_result_id, source_p11_replay_run_id,
        source_p10_proposal_run_id, source_p9_analytics_run_id,
        candidate_date, asset_id, stock_code, stock_name, shadow_layer,
        candidate_reason, evidence_artifact_paths, metric_summary,
        reviewer_id, status, review_notes, manual_review_required,
        auto_trade_enabled, production_watchlist_enabled,
        production_write_enabled, shadow_artifact_path, metadata
    )
    VALUES (
        %(shadow_candidate_id)s, %(run_id)s, %(replay_result_id)s,
        %(source_p11_replay_run_id)s, %(source_p10_proposal_run_id)s,
        %(source_p9_analytics_run_id)s, %(candidate_date)s, %(asset_id)s,
        %(stock_code)s, %(stock_name)s, %(shadow_layer)s,
        %(candidate_reason)s, %(evidence_artifact_paths)s::jsonb,
        %(metric_summary)s::jsonb, %(reviewer_id)s, %(status)s,
        %(review_notes)s, %(manual_review_required)s,
        %(auto_trade_enabled)s, %(production_watchlist_enabled)s,
        %(production_write_enabled)s, %(shadow_artifact_path)s,
        %(metadata)s::jsonb
    )
    ON CONFLICT (shadow_candidate_id)
    DO UPDATE SET
        run_id = EXCLUDED.run_id,
        replay_result_id = EXCLUDED.replay_result_id,
        source_p11_replay_run_id = EXCLUDED.source_p11_replay_run_id,
        source_p10_proposal_run_id = EXCLUDED.source_p10_proposal_run_id,
        source_p9_analytics_run_id = EXCLUDED.source_p9_analytics_run_id,
        candidate_date = EXCLUDED.candidate_date,
        asset_id = EXCLUDED.asset_id,
        stock_code = EXCLUDED.stock_code,
        stock_name = EXCLUDED.stock_name,
        shadow_layer = EXCLUDED.shadow_layer,
        candidate_reason = EXCLUDED.candidate_reason,
        evidence_artifact_paths = EXCLUDED.evidence_artifact_paths,
        metric_summary = EXCLUDED.metric_summary,
        reviewer_id = EXCLUDED.reviewer_id,
        status = EXCLUDED.status,
        review_notes = EXCLUDED.review_notes,
        manual_review_required = EXCLUDED.manual_review_required,
        auto_trade_enabled = EXCLUDED.auto_trade_enabled,
        production_watchlist_enabled = EXCLUDED.production_watchlist_enabled,
        production_write_enabled = EXCLUDED.production_write_enabled,
        shadow_artifact_path = EXCLUDED.shadow_artifact_path,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    cur.execute(
        sql,
        {
            **row,
            "evidence_artifact_paths": json.dumps(row.get("evidence_artifact_paths") or [], sort_keys=True),
            "metric_summary": json.dumps(row.get("metric_summary") or {}, sort_keys=True),
            "metadata": json.dumps(row.get("metadata") or {}, sort_keys=True),
        },
    )


def _candidate_row(
    item: dict[str, Any],
    *,
    run_id: str,
    shadow_artifact_path: Path,
) -> dict[str, Any]:
    if _bool_value(item.get("auto_trade_enabled")) is True:
        raise ValueError("auto_trade_not_allowed")
    if _bool_value(item.get("manual_review_required", True)) is not True:
        raise ValueError("manual_review_required")
    if _bool_value(item.get("production_watchlist_enabled", False)) is True:
        raise ValueError("production_watchlist_not_allowed")
    if _bool_value(item.get("production_write_enabled", False)) is True:
        raise ValueError("production_write_not_allowed")

    shadow_candidate_id = str(item.get("shadow_candidate_id") or "")
    if not shadow_candidate_id:
        raise ValueError("required_field_missing: shadow_candidate_id")
    return {
        "shadow_candidate_id": shadow_candidate_id,
        "run_id": run_id,
        "replay_result_id": _required_text(item, "replay_result_id"),
        "source_p11_replay_run_id": _required_text(item, "source_p11_replay_run_id"),
        "source_p10_proposal_run_id": _required_text(item, "source_p10_proposal_run_id"),
        "source_p9_analytics_run_id": _required_text(item, "source_p9_analytics_run_id"),
        "candidate_date": _required_text(item, "candidate_date"),
        "asset_id": _required_text(item, "asset_id"),
        "stock_code": str(item.get("stock_code") or ""),
        "stock_name": str(item.get("stock_name") or ""),
        "shadow_layer": _required_text(item, "shadow_layer"),
        "candidate_reason": _required_text(item, "candidate_reason"),
        "evidence_artifact_paths": _list_value(item.get("evidence_artifact_paths")),
        "metric_summary": _dict_value(item.get("metric_summary")),
        "reviewer_id": _required_text(item, "reviewer_id"),
        "status": _required_text(item, "status"),
        "review_notes": str(item.get("review_notes") or ""),
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "production_watchlist_enabled": False,
        "production_write_enabled": False,
        "shadow_artifact_path": str(shadow_artifact_path),
        "metadata": {},
    }


def _artifact_paths(json_path: Path) -> tuple[Path, Path]:
    return (
        json_path.with_name(f"{json_path.stem}_candidates.csv"),
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
    if isinstance(value, (list, tuple, set)):
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
