from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.research_evidence_registry import (
    evidence_from_digest_snapshot,
    evidence_from_review_item_snapshot,
    upsert_evidence_artifact,
)


SOURCE_TYPES = {"evidence_digest_snapshot", "review_item_snapshot", "all"}


def run_research_evidence_backfill(
    *,
    trade_date: str | None = None,
    source_type: str = "all",
    dry_run: bool = False,
    limit: int = 100,
    output_dir: str | Path = "outputs/research",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    source_type = source_type or "all"
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"invalid_source_type:{source_type}")

    limit_value = _clamp_limit(limit)
    summary = {
        "trade_date": trade_date or "",
        "source_type": source_type,
        "scanned": 0,
        "inserted_or_updated": 0,
        "skipped": 0,
        "errors": [],
        "dry_run": bool(dry_run),
    }

    for source in _selected_sources(source_type):
        for evidence in _load_source_evidence(source, trade_date=trade_date, limit=limit_value, service=service):
            summary["scanned"] += 1
            if dry_run:
                continue
            try:
                upsert_evidence_artifact(evidence, service=service)
                summary["inserted_or_updated"] += 1
            except Exception as exc:  # pragma: no cover - defensive around DB upsert errors.
                summary["skipped"] += 1
                summary["errors"].append(
                    {
                        "source_type": source,
                        "evidence_id": str(evidence.get("evidence_id") or ""),
                        "error": str(exc),
                    }
                )

    paths = write_research_evidence_backfill_summary(summary, output_dir=output_dir)
    summary.update(paths)
    return summary


def write_research_evidence_backfill_summary(
    summary: dict[str, Any],
    *,
    output_dir: str | Path,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    json_path = output_path / "research_evidence_backfill_summary.json"
    markdown_path = output_path / "research_evidence_backfill_summary.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_summary_markdown(summary), encoding="utf-8")
    return {"json_path": str(json_path), "markdown_path": str(markdown_path)}


def _load_source_evidence(
    source_type: str,
    *,
    trade_date: str | None,
    limit: int,
    service: str,
) -> list[dict[str, Any]]:
    if source_type == "evidence_digest_snapshot":
        rows = _load_digest_rows(trade_date=trade_date, limit=limit, service=service)
        return [evidence_from_digest_snapshot(dict(row)) for row in rows]
    if source_type == "review_item_snapshot":
        rows = _load_review_rows(trade_date=trade_date, limit=limit, service=service)
        return [evidence_from_review_item_snapshot(dict(row)) for row in rows]
    raise ValueError(f"invalid_source_type:{source_type}")


def _load_digest_rows(*, trade_date: str | None, limit: int, service: str) -> list[dict[str, Any]]:
    clauses, params = _trade_date_filter(trade_date)
    params.append(limit)
    sql = f"""
    SELECT
        snapshot_id,
        asset_id,
        trade_date::text AS trade_date,
        digest_key,
        payload_hash,
        digest_payload
    FROM ops.evidence_digest_snapshot
    WHERE {" AND ".join(clauses)}
    ORDER BY trade_date DESC, updated_at DESC
    LIMIT %s
    """
    with connect(service) as conn:
        return fetch_all(conn, sql, params)


def _load_review_rows(*, trade_date: str | None, limit: int, service: str) -> list[dict[str, Any]]:
    clauses, params = _trade_date_filter(trade_date)
    params.append(limit)
    sql = f"""
    SELECT
        snapshot_id,
        asset_id,
        stock_name,
        trade_date::text AS trade_date,
        digest_key,
        payload_hash,
        review_item_payload
    FROM ops.review_item_snapshot
    WHERE {" AND ".join(clauses)}
    ORDER BY trade_date DESC, updated_at DESC
    LIMIT %s
    """
    with connect(service) as conn:
        return fetch_all(conn, sql, params)


def _trade_date_filter(trade_date: str | None) -> tuple[list[str], list[Any]]:
    if not trade_date:
        return ["1=1"], []
    return ["trade_date = %s"], [trade_date]


def _selected_sources(source_type: str) -> list[str]:
    if source_type == "all":
        return ["evidence_digest_snapshot", "review_item_snapshot"]
    return [source_type]


def _clamp_limit(value: int) -> int:
    return max(1, min(1000, int(value or 100)))


def _summary_markdown(summary: dict[str, Any]) -> str:
    errors = summary.get("errors") or []
    lines = [
        "# Research Evidence Backfill Summary",
        "",
        f"- trade_date: {summary.get('trade_date') or ''}",
        f"- source_type: {summary.get('source_type') or ''}",
        f"- scanned: {summary.get('scanned')}",
        f"- inserted_or_updated: {summary.get('inserted_or_updated')}",
        f"- skipped: {summary.get('skipped')}",
        f"- dry_run: {summary.get('dry_run')}",
        f"- errors: {len(errors)}",
    ]
    if errors:
        lines.append("")
        lines.append("## Errors")
        for error in errors:
            lines.append(f"- {error}")
    lines.append("")
    return "\n".join(lines)
