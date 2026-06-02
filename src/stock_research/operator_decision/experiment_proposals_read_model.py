from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect


def load_experiment_proposal_read_model_rows(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)
    review = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(review, dict):
        raise ValueError(f"operator experiment proposal review must be a JSON object: {json_path}")

    if _bool_value(review.get("auto_trade_enabled")) is True:
        raise ValueError("auto_trade_not_allowed")
    if _bool_value(review.get("manual_review_required", True)) is not True:
        raise ValueError("manual_review_required")
    if _bool_value(review.get("promotion_enabled", False)) is True:
        raise ValueError("promotion_not_allowed")

    run_id = str(review.get("run_id") or "")
    review_date = str(review.get("review_date") or "")
    if not run_id:
        raise ValueError(f"operator experiment proposal review requires run_id: {json_path}")
    if not review_date:
        raise ValueError(f"operator experiment proposal review requires review_date: {json_path}")

    proposals = [item for item in review.get("proposals", []) if isinstance(item, dict)]
    proposals_csv_path, markdown_path = _artifact_paths(json_path)
    return {
        "run": {
            "run_id": run_id,
            "review_date": review_date,
            "status": str(review.get("status") or ""),
            "proposal_count": int(review.get("proposal_count") or len(proposals)),
            "status_counts": review.get("status_counts") or {},
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "promotion_enabled": False,
            "json_path": str(json_path),
            "proposals_csv_path": str(proposals_csv_path),
            "markdown_path": str(markdown_path),
            "metadata": {},
        },
        "proposals": [
            _proposal_row(item, run_id=run_id, review_date=review_date, proposal_artifact_path=json_path)
            for item in proposals
        ],
    }


def import_experiment_proposal_review(
    path: str | Path,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    input_path = Path(path)
    paths = _proposal_paths(input_path)
    run_ids: list[str] = []
    proposal_count = 0
    with connect(service) as conn:
        with conn.cursor() as cur:
            for proposal_path in paths:
                rows = load_experiment_proposal_read_model_rows(proposal_path)
                _upsert_run(cur, rows["run"])
                for proposal in rows["proposals"]:
                    _upsert_proposal(cur, proposal)
                    proposal_count += 1
                run_ids.append(str(rows["run"]["run_id"]))
    return {
        "imported_count": len(paths),
        "proposal_count": proposal_count,
        "run_ids": run_ids,
    }


def _proposal_paths(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("operator_experiment_proposals_*.json"))
    return [path]


def _upsert_run(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_experiment_proposal_run (
        run_id, review_date, status, proposal_count, status_counts,
        manual_review_required, auto_trade_enabled, promotion_enabled,
        json_path, proposals_csv_path, markdown_path, metadata
    )
    VALUES (
        %(run_id)s, %(review_date)s, %(status)s, %(proposal_count)s,
        %(status_counts)s::jsonb, %(manual_review_required)s,
        %(auto_trade_enabled)s, %(promotion_enabled)s, %(json_path)s,
        %(proposals_csv_path)s, %(markdown_path)s, %(metadata)s::jsonb
    )
    ON CONFLICT (run_id)
    DO UPDATE SET
        review_date = EXCLUDED.review_date,
        status = EXCLUDED.status,
        proposal_count = EXCLUDED.proposal_count,
        status_counts = EXCLUDED.status_counts,
        manual_review_required = EXCLUDED.manual_review_required,
        auto_trade_enabled = EXCLUDED.auto_trade_enabled,
        promotion_enabled = EXCLUDED.promotion_enabled,
        json_path = EXCLUDED.json_path,
        proposals_csv_path = EXCLUDED.proposals_csv_path,
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


def _upsert_proposal(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_experiment_proposal (
        proposal_id, run_id, review_date, proposal_title, hypothesis,
        source_p9_analytics_run_id, source_analytics_group_ids,
        source_diagnostic_refs, source_artifact_paths,
        expected_validation_method, risk_notes, reviewer_id, status,
        manual_review_required, auto_trade_enabled, promotion_enabled,
        proposal_artifact_path, metadata
    )
    VALUES (
        %(proposal_id)s, %(run_id)s, %(review_date)s, %(proposal_title)s,
        %(hypothesis)s, %(source_p9_analytics_run_id)s,
        %(source_analytics_group_ids)s::jsonb, %(source_diagnostic_refs)s::jsonb,
        %(source_artifact_paths)s::jsonb, %(expected_validation_method)s,
        %(risk_notes)s, %(reviewer_id)s, %(status)s, %(manual_review_required)s,
        %(auto_trade_enabled)s, %(promotion_enabled)s, %(proposal_artifact_path)s,
        %(metadata)s::jsonb
    )
    ON CONFLICT (proposal_id)
    DO UPDATE SET
        run_id = EXCLUDED.run_id,
        review_date = EXCLUDED.review_date,
        proposal_title = EXCLUDED.proposal_title,
        hypothesis = EXCLUDED.hypothesis,
        source_p9_analytics_run_id = EXCLUDED.source_p9_analytics_run_id,
        source_analytics_group_ids = EXCLUDED.source_analytics_group_ids,
        source_diagnostic_refs = EXCLUDED.source_diagnostic_refs,
        source_artifact_paths = EXCLUDED.source_artifact_paths,
        expected_validation_method = EXCLUDED.expected_validation_method,
        risk_notes = EXCLUDED.risk_notes,
        reviewer_id = EXCLUDED.reviewer_id,
        status = EXCLUDED.status,
        manual_review_required = EXCLUDED.manual_review_required,
        auto_trade_enabled = EXCLUDED.auto_trade_enabled,
        promotion_enabled = EXCLUDED.promotion_enabled,
        proposal_artifact_path = EXCLUDED.proposal_artifact_path,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    cur.execute(
        sql,
        {
            **row,
            "source_analytics_group_ids": json.dumps(row.get("source_analytics_group_ids") or [], sort_keys=True),
            "source_diagnostic_refs": json.dumps(row.get("source_diagnostic_refs") or [], sort_keys=True),
            "source_artifact_paths": json.dumps(row.get("source_artifact_paths") or [], sort_keys=True),
            "metadata": json.dumps(row.get("metadata") or {}, sort_keys=True),
        },
    )


def _proposal_row(
    item: dict[str, Any],
    *,
    run_id: str,
    review_date: str,
    proposal_artifact_path: Path,
) -> dict[str, Any]:
    if _bool_value(item.get("auto_trade_enabled")) is True:
        raise ValueError("auto_trade_not_allowed")
    if _bool_value(item.get("manual_review_required", True)) is not True:
        raise ValueError("manual_review_required")
    proposal_id = str(item.get("proposal_id") or "")
    if not proposal_id:
        raise ValueError("required_field_missing: proposal_id")
    return {
        "proposal_id": proposal_id,
        "run_id": run_id,
        "review_date": review_date,
        "proposal_title": str(item.get("proposal_title") or ""),
        "hypothesis": str(item.get("hypothesis") or ""),
        "source_p9_analytics_run_id": str(item.get("source_p9_analytics_run_id") or ""),
        "source_analytics_group_ids": _list_value(item.get("source_analytics_group_ids")),
        "source_diagnostic_refs": _list_value(item.get("source_diagnostic_refs")),
        "source_artifact_paths": _list_value(item.get("source_artifact_paths")),
        "expected_validation_method": str(item.get("expected_validation_method") or ""),
        "risk_notes": str(item.get("risk_notes") or ""),
        "reviewer_id": str(item.get("reviewer_id") or ""),
        "status": str(item.get("status") or ""),
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "promotion_enabled": False,
        "proposal_artifact_path": str(proposal_artifact_path),
        "metadata": {},
    }


def _artifact_paths(json_path: Path) -> tuple[Path, Path]:
    return (
        json_path.with_name(f"{json_path.stem}_proposals.csv"),
        json_path.with_suffix(".md"),
    )


def _list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


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
