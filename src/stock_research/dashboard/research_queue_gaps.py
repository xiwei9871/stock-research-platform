from __future__ import annotations

from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.research_review_actions import review_action_read_model, review_status_from_action


GAP_REASON_LABELS = {
    "no_evidence": "no linked evidence",
    "missing_evidence": "missing evidence signal found",
    "partial_evidence": "partial evidence signal found",
    "incomplete_evidence_status": "evidence status is incomplete",
    "unknown_gap": "gap could not be explained from whitelisted fields",
}


def list_research_queue_gaps(
    *,
    trade_date: str | None = None,
    limit: int = 50,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    clauses = ["1=1"]
    params: list[Any] = []
    if trade_date:
        clauses.append("c.trade_date = %s")
        params.append(trade_date)
    base_sql = f"""
    WITH latest_review_action AS (
        SELECT DISTINCT ON (case_id)
            review_action_id,
            case_id,
            trade_date::text AS review_trade_date,
            asset_id AS review_asset_id,
            action_type AS latest_action_type,
            gap_reasons AS latest_review_gap_reasons,
            reviewer AS latest_reviewer,
            comment AS latest_review_comment,
            created_at::text AS latest_review_created_at,
            source_context AS latest_review_source_context
        FROM research.review_action
        ORDER BY case_id, created_at DESC, review_action_id DESC
    ),
    gap_rows AS (
    SELECT
        c.case_id,
        c.trade_date::text AS trade_date,
        c.asset_id,
        c.theme,
        c.title,
        c.status,
        c.priority,
        c.source_type,
        c.source_id,
        c.updated_at,
        c.metadata->>'evidence_status' AS evidence_status,
        COALESCE((c.metadata->>'missing_evidence_count')::int, 0) AS missing_evidence_count,
        COALESCE((c.metadata->>'partial_evidence_count')::int, 0) AS partial_evidence_count,
        COALESCE(claims.claim_count, 0) AS claim_count,
        COALESCE(evidence.evidence_count, 0) AS evidence_count,
        latest.review_action_id AS latest_review_action_id,
        latest.latest_action_type,
        latest.latest_review_gap_reasons,
        latest.latest_reviewer,
        latest.latest_review_comment,
        latest.latest_review_created_at,
        latest.latest_review_source_context
    FROM research.research_case c
    LEFT JOIN (
        SELECT case_id, count(*) AS claim_count
        FROM research.research_claim
        GROUP BY case_id
    ) claims USING (case_id)
    LEFT JOIN (
        SELECT target_id AS case_id, count(DISTINCT evidence_id) AS evidence_count
        FROM research.evidence_link
        WHERE target_type = 'research_case'
        GROUP BY target_id
    ) evidence ON evidence.case_id = c.case_id
    LEFT JOIN latest_review_action latest ON latest.case_id = c.case_id
    WHERE {" AND ".join(clauses)}
    )
    """
    gap_predicate = """
      (
        evidence_count <= 0
        OR missing_evidence_count > 0
        OR partial_evidence_count > 0
        OR (
          COALESCE(evidence_status, '') <> ''
          AND lower(evidence_status) <> 'complete'
        )
      )
    """
    rows_sql = f"""
    {base_sql}
    SELECT
        case_id,
        trade_date,
        asset_id,
        theme,
        title,
        status,
        priority,
        source_type,
        source_id,
        evidence_status,
        missing_evidence_count,
        partial_evidence_count,
        claim_count,
        evidence_count,
        latest_review_action_id,
        latest_action_type,
        latest_review_gap_reasons,
        latest_reviewer,
        latest_review_comment,
        latest_review_created_at,
        latest_review_source_context
    FROM gap_rows
    WHERE {gap_predicate}
    ORDER BY priority ASC, updated_at DESC
    LIMIT %s
    """
    summary_sql = f"""
    {base_sql}
    SELECT
        count(*) AS gap_case_count,
        count(*) FILTER (WHERE evidence_count <= 0) AS no_evidence_count,
        count(*) FILTER (WHERE missing_evidence_count > 0) AS missing_evidence_count,
        count(*) FILTER (WHERE partial_evidence_count > 0) AS partial_evidence_count,
        count(*) FILTER (
            WHERE COALESCE(evidence_status, '') <> ''
              AND lower(evidence_status) <> 'complete'
        ) AS incomplete_evidence_status_count,
        0 AS unknown_gap_count,
        count(*) FILTER (WHERE latest_action_type IN ('acknowledge_gap', 'mark_reviewed')) AS reviewed_gap_count,
        count(*) FILTER (WHERE latest_action_type = 'request_more_evidence') AS request_more_evidence_count,
        count(*) FILTER (WHERE latest_action_type = 'defer') AS deferred_gap_count,
        count(*) FILTER (WHERE COALESCE(latest_action_type, '') = '') AS pending_gap_count
    FROM gap_rows
    WHERE {gap_predicate}
    """
    with connect(service) as conn:
        rows = fetch_all(conn, rows_sql, [*params, _clamp_limit(limit)])
        summary_rows = fetch_all(conn, summary_sql, params)
    items = [gap_case_read_model(row) for row in rows]
    summary = _clean_gap_summary(summary_rows[0] if summary_rows else {})
    return {"trade_date": trade_date or "", "items": items, "summary": summary}


def gap_case_read_model(row: dict[str, Any]) -> dict[str, Any]:
    item = {
        "case_id": str(row.get("case_id") or ""),
        "trade_date": str(row.get("trade_date") or ""),
        "asset_id": str(row.get("asset_id") or ""),
        "theme": str(row.get("theme") or ""),
        "title": str(row.get("title") or ""),
        "status": str(row.get("status") or ""),
        "priority": _int(row.get("priority")),
        "evidence_count": _int(row.get("evidence_count")),
        "claim_count": _int(row.get("claim_count")),
        "source_type": str(row.get("source_type") or ""),
        "source_id": str(row.get("source_id") or ""),
        "evidence_status": str(row.get("evidence_status") or ""),
        "missing_evidence_count": _int(row.get("missing_evidence_count")),
        "partial_evidence_count": _int(row.get("partial_evidence_count")),
    }
    reasons = gap_reasons_for_case(item)
    latest_review_action = latest_review_action_from_row(row)
    return {
        "case_id": item["case_id"],
        "trade_date": item["trade_date"],
        "asset_id": item["asset_id"],
        "theme": item["theme"],
        "title": item["title"],
        "status": item["status"],
        "priority": item["priority"],
        "evidence_count": item["evidence_count"],
        "claim_count": item["claim_count"],
        "gap_reasons": reasons,
        "gap_summary": gap_summary_text(reasons, item),
        "review_status": review_status_from_action(row.get("latest_action_type")),
        "latest_review_action": latest_review_action,
        "source_type": item["source_type"],
        "source_id": item["source_id"],
    }


def latest_review_action_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    if not row.get("latest_review_action_id"):
        return None
    return review_action_read_model(
        {
            "review_action_id": row.get("latest_review_action_id"),
            "case_id": row.get("case_id"),
            "trade_date": row.get("trade_date"),
            "asset_id": row.get("asset_id"),
            "action_type": row.get("latest_action_type"),
            "gap_reasons": row.get("latest_review_gap_reasons"),
            "reviewer": row.get("latest_reviewer"),
            "comment": row.get("latest_review_comment"),
            "created_at": row.get("latest_review_created_at"),
            "source_context": row.get("latest_review_source_context"),
        }
    )


def gap_reasons_for_case(row: dict[str, Any], *, force_gap: bool = False) -> list[str]:
    reasons: list[str] = []
    if _int(row.get("evidence_count")) <= 0:
        reasons.append("no_evidence")
    if _int(row.get("missing_evidence_count")) > 0:
        reasons.append("missing_evidence")
    if _int(row.get("partial_evidence_count")) > 0:
        reasons.append("partial_evidence")
    status = str(row.get("evidence_status") or "").strip().lower()
    if status and status != "complete":
        reasons.append("incomplete_evidence_status")
    if force_gap and not reasons:
        reasons.append("unknown_gap")
    return reasons


def gap_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "gap_case_count": len(items),
        "no_evidence_count": 0,
        "missing_evidence_count": 0,
        "partial_evidence_count": 0,
        "incomplete_evidence_status_count": 0,
        "unknown_gap_count": 0,
        "reviewed_gap_count": 0,
        "pending_gap_count": 0,
        "deferred_gap_count": 0,
        "request_more_evidence_count": 0,
    }
    for item in items:
        for reason in item.get("gap_reasons") or []:
            key = f"{reason}_count"
            if key in summary:
                summary[key] += 1
        status = str(item.get("review_status") or "pending")
        if status == "reviewed":
            summary["reviewed_gap_count"] += 1
        elif status == "request_more_evidence":
            summary["request_more_evidence_count"] += 1
        elif status == "deferred":
            summary["deferred_gap_count"] += 1
        else:
            summary["pending_gap_count"] += 1
    return summary


def gap_summary_text(reasons: list[str], row: dict[str, Any] | None = None) -> str:
    if not reasons:
        return ""
    parts: list[str] = []
    for reason in reasons:
        if reason == "incomplete_evidence_status":
            status = str((row or {}).get("evidence_status") or "").strip()
            parts.append(f"evidence status is {status or 'not complete'}")
        else:
            parts.append(GAP_REASON_LABELS.get(reason, reason))
    return "; ".join(parts)


def research_queue_gaps_read_model(payload: dict[str, Any]) -> dict[str, Any]:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    clean_items = [gap_case_read_model(item) if "gap_reasons" not in item else _clean_gap_item(item) for item in items]
    return {
        "trade_date": str(payload.get("trade_date") or ""),
        "items": clean_items,
        "summary": gap_summary(clean_items) if "summary" not in payload else _clean_gap_summary(payload.get("summary")),
    }


def _clean_gap_item(item: dict[str, Any]) -> dict[str, Any]:
    reasons = [str(reason) for reason in item.get("gap_reasons") or []]
    latest_review_action = review_action_read_model(item.get("latest_review_action"))
    review_status = str(item.get("review_status") or review_status_from_action((latest_review_action or {}).get("action_type")))
    return {
        "case_id": str(item.get("case_id") or ""),
        "trade_date": str(item.get("trade_date") or ""),
        "asset_id": str(item.get("asset_id") or ""),
        "theme": str(item.get("theme") or ""),
        "title": str(item.get("title") or ""),
        "status": str(item.get("status") or ""),
        "priority": _int(item.get("priority")),
        "evidence_count": _int(item.get("evidence_count")),
        "claim_count": _int(item.get("claim_count")),
        "gap_reasons": reasons,
        "gap_summary": str(item.get("gap_summary") or gap_summary_text(reasons, item)),
        "review_status": review_status,
        "latest_review_action": latest_review_action,
        "source_type": str(item.get("source_type") or ""),
        "source_id": str(item.get("source_id") or ""),
    }


def _clean_gap_summary(value: Any) -> dict[str, int]:
    summary = value if isinstance(value, dict) else {}
    return {
        "gap_case_count": _int(summary.get("gap_case_count")),
        "no_evidence_count": _int(summary.get("no_evidence_count")),
        "missing_evidence_count": _int(summary.get("missing_evidence_count")),
        "partial_evidence_count": _int(summary.get("partial_evidence_count")),
        "incomplete_evidence_status_count": _int(summary.get("incomplete_evidence_status_count")),
        "unknown_gap_count": _int(summary.get("unknown_gap_count")),
        "reviewed_gap_count": _int(summary.get("reviewed_gap_count")),
        "pending_gap_count": _int(summary.get("pending_gap_count")),
        "deferred_gap_count": _int(summary.get("deferred_gap_count")),
        "request_more_evidence_count": _int(summary.get("request_more_evidence_count")),
    }


def _clamp_limit(value: int) -> int:
    return max(1, min(100, int(value or 50)))


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
