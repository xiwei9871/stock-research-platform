from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect
from stock_research.operator_decision.journal import validate_decision_events
from stock_research.operator_decision.snapshot_linkage import (
    merge_source_context,
    resolve_decision_snapshot_linkage,
)


def load_decision_journal_read_model_rows(
    path: str | Path,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    json_path = Path(path)
    journal = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(journal, dict):
        raise ValueError(f"operator decision journal must be a JSON object: {json_path}")

    review_session_id = str(journal.get("review_session_id") or "")
    review_date = str(journal.get("review_date") or "")
    if not review_session_id:
        raise ValueError(f"operator decision journal requires review_session_id: {json_path}")
    if not review_date:
        raise ValueError(f"operator decision journal requires review_date: {json_path}")
    if bool(journal.get("auto_trade_enabled")):
        raise ValueError("auto_trade_not_allowed")
    if bool(journal.get("manual_review_required", True)) is not True:
        raise ValueError("manual_review_required")

    items = [item for item in journal.get("items", []) if isinstance(item, dict)]
    issues = validate_decision_events(pd.DataFrame(items))
    if issues:
        issue_codes = ", ".join(sorted({str(issue["code"]) for issue in issues}))
        raise ValueError(f"invalid decision journal artifact: {issue_codes}")

    return {
        "session": {
            "review_session_id": review_session_id,
            "review_date": review_date,
            "reviewer_id": str(journal.get("reviewer_id") or ""),
            "status": str(journal.get("status") or ""),
            "decision_count": int(journal.get("decision_count") or len(items)),
            "manual_review_required": True,
            "auto_trade_enabled": False,
            "source_artifact_root": str(journal.get("source_artifact_root") or ""),
            "json_path": str(json_path),
            "csv_path": str(json_path.with_suffix(".csv")),
            "markdown_path": str(json_path.with_suffix(".md")),
            "metadata": {
                "decision_label_counts": journal.get("decision_label_counts") or {},
                "issues": journal.get("issues") or [],
            },
        },
        "events": [
            _event_row(
                item,
                index=index,
                review_session_id=review_session_id,
                review_date=review_date,
                source_artifact_path=json_path,
                service=service,
            )
            for index, item in enumerate(items)
        ],
    }


def import_decision_journal(
    path: str | Path,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    input_path = Path(path)
    paths = _journal_paths(input_path)
    session_ids: list[str] = []
    event_count = 0
    with connect(service) as conn:
        with conn.cursor() as cur:
            for journal_path in paths:
                rows = load_decision_journal_read_model_rows(journal_path, service=service)
                _upsert_session(cur, rows["session"])
                for event in rows["events"]:
                    _upsert_event(cur, event)
                    event_count += 1
                session_ids.append(str(rows["session"]["review_session_id"]))
    return {
        "imported_count": len(paths),
        "event_count": event_count,
        "session_ids": session_ids,
    }


def _journal_paths(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("operator_decision_journal_*.json"))
    return [path]


def _upsert_session(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_review_session (
        review_session_id, review_date, reviewer_id, status, decision_count,
        manual_review_required, auto_trade_enabled, source_artifact_root,
        json_path, csv_path, markdown_path, metadata
    )
    VALUES (
        %(review_session_id)s, %(review_date)s, %(reviewer_id)s, %(status)s,
        %(decision_count)s, %(manual_review_required)s, %(auto_trade_enabled)s,
        %(source_artifact_root)s, %(json_path)s, %(csv_path)s, %(markdown_path)s,
        %(metadata)s::jsonb
    )
    ON CONFLICT (review_session_id)
    DO UPDATE SET
        review_date = EXCLUDED.review_date,
        reviewer_id = EXCLUDED.reviewer_id,
        status = EXCLUDED.status,
        decision_count = EXCLUDED.decision_count,
        manual_review_required = EXCLUDED.manual_review_required,
        auto_trade_enabled = EXCLUDED.auto_trade_enabled,
        source_artifact_root = EXCLUDED.source_artifact_root,
        json_path = EXCLUDED.json_path,
        csv_path = EXCLUDED.csv_path,
        markdown_path = EXCLUDED.markdown_path,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    params = {
        **row,
        "metadata": json.dumps(row.get("metadata") or {}, sort_keys=True),
    }
    cur.execute(sql, params)


def _upsert_event(cur: Any, row: dict[str, Any]) -> None:
    sql = """
    INSERT INTO ops.operator_decision_event (
        event_id, review_session_id, review_date, event_index, asset_id,
        stock_code, stock_name, decision_label, evidence_artifact_id,
        evidence_path, source_context, requires_follow_up, follow_up_note,
        notes, manual_review_required, auto_trade_enabled, source_artifact_path
    )
    VALUES (
        %(event_id)s, %(review_session_id)s, %(review_date)s, %(event_index)s,
        %(asset_id)s, %(stock_code)s, %(stock_name)s, %(decision_label)s,
        %(evidence_artifact_id)s, %(evidence_path)s, %(source_context)s,
        %(requires_follow_up)s, %(follow_up_note)s, %(notes)s,
        %(manual_review_required)s, %(auto_trade_enabled)s,
        %(source_artifact_path)s
    )
    ON CONFLICT (event_id)
    DO UPDATE SET
        review_date = EXCLUDED.review_date,
        event_index = EXCLUDED.event_index,
        asset_id = EXCLUDED.asset_id,
        stock_code = EXCLUDED.stock_code,
        stock_name = EXCLUDED.stock_name,
        decision_label = EXCLUDED.decision_label,
        evidence_artifact_id = EXCLUDED.evidence_artifact_id,
        evidence_path = EXCLUDED.evidence_path,
        source_context = EXCLUDED.source_context,
        requires_follow_up = EXCLUDED.requires_follow_up,
        follow_up_note = EXCLUDED.follow_up_note,
        notes = EXCLUDED.notes,
        manual_review_required = EXCLUDED.manual_review_required,
        auto_trade_enabled = EXCLUDED.auto_trade_enabled,
        source_artifact_path = EXCLUDED.source_artifact_path,
        updated_at = now()
    """
    cur.execute(sql, row)


def _event_row(
    item: dict[str, Any],
    *,
    index: int,
    review_session_id: str,
    review_date: str,
    source_artifact_path: Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    asset_id = str(item.get("asset_id") or "")
    decision_label = str(item.get("decision_label") or "")
    evidence_artifact_id = str(item.get("evidence_artifact_id") or "")
    evidence_path = str(item.get("evidence_path") or "")
    source_context = str(item.get("source_context") or "")
    linkage = resolve_decision_snapshot_linkage(
        {
            **item,
            "asset_id": asset_id,
            "stock_code": str(item.get("stock_code") or ""),
            "source_context": source_context,
        },
        service=service,
    )
    return {
        "event_id": _event_id(
            review_session_id=review_session_id,
            index=index,
            asset_id=asset_id,
            decision_label=decision_label,
            evidence_artifact_id=evidence_artifact_id,
            evidence_path=evidence_path,
        ),
        "review_session_id": review_session_id,
        "review_date": review_date,
        "event_index": index,
        "asset_id": asset_id,
        "stock_code": str(item.get("stock_code") or ""),
        "stock_name": str(item.get("stock_name") or ""),
        "decision_label": decision_label,
        "evidence_artifact_id": evidence_artifact_id,
        "evidence_path": evidence_path,
        "source_context": merge_source_context(source_context, linkage),
        "requires_follow_up": bool(item.get("requires_follow_up")),
        "follow_up_note": str(item.get("follow_up_note") or ""),
        "notes": str(item.get("notes") or ""),
        "manual_review_required": True,
        "auto_trade_enabled": False,
        "source_artifact_path": str(source_artifact_path),
    }


def _event_id(
    *,
    review_session_id: str,
    index: int,
    asset_id: str,
    decision_label: str,
    evidence_artifact_id: str,
    evidence_path: str,
) -> str:
    raw = "|".join(
        [
            review_session_id,
            str(index),
            asset_id,
            decision_label,
            evidence_artifact_id,
            evidence_path,
        ]
    )
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"operator_decision:{review_session_id}:{index}:{digest}"
