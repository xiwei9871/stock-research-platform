from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect


def load_p2_aggregate_review_rows(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)
    review = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(review, dict):
        raise ValueError(f"P2 aggregate review must be a JSON object: {json_path}")

    trade_date = str(review.get("trade_date") or "")
    if not trade_date:
        raise ValueError(f"P2 aggregate review requires trade_date: {json_path}")
    run_id = str(review.get("run_id") or _fallback_run_id(trade_date, json_path))
    sections = [
        _section_row(run_id, section)
        for section in review.get("sections", [])
        if isinstance(section, dict)
    ]
    return {
        "run": {
            "run_id": run_id,
            "trade_date": trade_date,
            "status": str(review.get("status") or ""),
            "source_rollup_status": review.get("source_rollup_status"),
            "artifact_count": len(sections),
            "blocker_count": int(review.get("blocker_count") or 0),
            "warning_count": int(review.get("warning_count") or 0),
            "json_path": str(json_path),
            "markdown_path": str(_markdown_path(json_path)),
            "metadata": {
                "auto_trade_enabled": bool(review.get("auto_trade_enabled")),
                "human_confirmation_required": bool(
                    review.get("human_confirmation_required")
                ),
            },
        },
        "sections": sections,
    }


def import_p2_aggregate_review(
    path: str | Path,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    input_path = Path(path)
    paths = _review_paths(input_path)
    run_ids: list[str] = []
    with connect(service) as conn:
        with conn.cursor() as cur:
            for review_path in paths:
                rows = load_p2_aggregate_review_rows(review_path)
                _upsert_run(cur, rows["run"])
                for section in rows["sections"]:
                    _upsert_section(cur, section)
                run_ids.append(str(rows["run"]["run_id"]))
    return {"imported_count": len(run_ids), "run_ids": run_ids}


def _review_paths(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("p2_aggregate_review_*.json"))
    return [path]


def _upsert_run(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.p2_review_run (
        run_id, trade_date, status, source_rollup_status, artifact_count,
        blocker_count, warning_count, json_path, markdown_path, metadata
    )
    VALUES (
        %(run_id)s, %(trade_date)s, %(status)s, %(source_rollup_status)s,
        %(artifact_count)s, %(blocker_count)s, %(warning_count)s,
        %(json_path)s, %(markdown_path)s, %(metadata)s::jsonb
    )
    ON CONFLICT (run_id)
    DO UPDATE SET
        trade_date = EXCLUDED.trade_date,
        status = EXCLUDED.status,
        source_rollup_status = EXCLUDED.source_rollup_status,
        artifact_count = EXCLUDED.artifact_count,
        blocker_count = EXCLUDED.blocker_count,
        warning_count = EXCLUDED.warning_count,
        json_path = EXCLUDED.json_path,
        markdown_path = EXCLUDED.markdown_path,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    params = {
        **row,
        "metadata": json.dumps(row.get("metadata") or {}, sort_keys=True),
    }
    cur.execute(sql, params)


def _upsert_section(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.p2_review_section (
        run_id, section_group, section_name, status, required, exists,
        source_artifact_path, summary
    )
    VALUES (
        %(run_id)s, %(section_group)s, %(section_name)s, %(status)s,
        %(required)s, %(exists)s, %(source_artifact_path)s, %(summary)s::jsonb
    )
    ON CONFLICT (run_id, section_group, section_name)
    DO UPDATE SET
        status = EXCLUDED.status,
        required = EXCLUDED.required,
        exists = EXCLUDED.exists,
        source_artifact_path = EXCLUDED.source_artifact_path,
        summary = EXCLUDED.summary
    """
    params = {
        **row,
        "summary": json.dumps(row.get("summary") or {}, sort_keys=True),
    }
    cur.execute(sql, params)


def _section_row(run_id: str, section: dict[str, Any]) -> dict[str, Any]:
    summary = section.get("summary")
    return {
        "run_id": run_id,
        "section_group": str(section.get("group") or ""),
        "section_name": str(section.get("name") or section.get("group") or ""),
        "status": str(section.get("status") or ""),
        "required": bool(section.get("required")),
        "exists": bool(section.get("exists")),
        "source_artifact_path": str(section.get("path") or ""),
        "summary": summary if isinstance(summary, dict) else {},
    }


def _markdown_path(json_path: Path) -> Path:
    candidate = json_path.with_suffix(".md")
    return candidate


def _fallback_run_id(trade_date: str, json_path: Path) -> str:
    digest = hashlib.sha1(str(json_path).encode("utf-8")).hexdigest()[:12]
    return f"p2_review:{trade_date}:{digest}"
