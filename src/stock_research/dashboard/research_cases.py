from __future__ import annotations

from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.dashboard.research_queue_gaps import gap_reasons_for_case, gap_summary_text
from stock_research.research_review_actions import review_action_read_model, review_status_from_action


def list_research_cases(
    *,
    trade_date: str | None = None,
    status: str | None = None,
    asset_id: str | None = None,
    limit: int = 50,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if trade_date:
        clauses.append("c.trade_date = %s")
        params.append(trade_date)
    if status:
        clauses.append("c.status = %s")
        params.append(status)
    if asset_id:
        clauses.append("c.asset_id = %s")
        params.append(asset_id)
    params.append(_clamp_limit(limit))
    sql = f"""
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
        c.metadata->>'evidence_status' AS evidence_status,
        c.metadata->>'missing_evidence_count' AS missing_evidence_count,
        c.metadata->>'partial_evidence_count' AS partial_evidence_count,
        COALESCE(claims.claim_count, 0) AS claim_count,
        COALESCE(evidence.evidence_count, 0) AS evidence_count
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
    WHERE {" AND ".join(clauses)}
    ORDER BY c.priority ASC, c.updated_at DESC
    LIMIT %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return [research_case_read_model(row) for row in rows]


def research_case_read_model(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": str(row.get("case_id") or ""),
        "trade_date": str(row.get("trade_date") or ""),
        "asset_id": str(row.get("asset_id") or ""),
        "theme": str(row.get("theme") or ""),
        "title": str(row.get("title") or ""),
        "status": str(row.get("status") or ""),
        "priority": int(row.get("priority") or 0),
        "source_type": str(row.get("source_type") or ""),
        "source_id": str(row.get("source_id") or ""),
        "evidence_status": str(row.get("evidence_status") or ""),
        "missing_evidence_count": int(row.get("missing_evidence_count") or 0),
        "partial_evidence_count": int(row.get("partial_evidence_count") or 0),
        "claim_count": int(row.get("claim_count") or 0),
        "evidence_count": int(row.get("evidence_count") or 0),
    }


def load_research_case_detail(
    case_id: str,
    *,
    limit: int = 100,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    child_limit = _clamp_limit(limit)
    case_sql = """
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
        c.metadata->>'evidence_status' AS evidence_status,
        c.metadata->>'missing_evidence_count' AS missing_evidence_count,
        c.metadata->>'partial_evidence_count' AS partial_evidence_count,
        COALESCE(claims.claim_count, 0) AS claim_count,
        COALESCE(evidence.evidence_count, 0) AS evidence_count
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
    WHERE c.case_id = %s
    LIMIT 1
    """
    claims_sql = """
    SELECT
        claim_id,
        claim_type,
        claim_text,
        confidence,
        status,
        metadata
    FROM research.research_claim
    WHERE case_id = %s
    ORDER BY created_at ASC, claim_id ASC
    LIMIT %s
    """
    evidence_sql = """
    SELECT DISTINCT ON (e.evidence_id, l.target_type, l.target_id, l.relation)
        e.evidence_id,
        e.source_type,
        e.source_id,
        e.asset_id,
        e.trade_date::text AS trade_date,
        e.title,
        e.uri,
        e.content_hash,
        e.metadata AS evidence_metadata,
        l.relation,
        l.target_type,
        l.target_id,
        l.metadata AS link_metadata
    FROM research.evidence_link l
    JOIN research.evidence_artifact e ON e.evidence_id = l.evidence_id
    WHERE
        (l.target_type = 'research_case' AND l.target_id = %s)
        OR (
            l.target_type = 'research_claim'
            AND l.target_id IN (
                SELECT claim_id FROM research.research_claim WHERE case_id = %s
            )
        )
    ORDER BY e.evidence_id, l.target_type, l.target_id, l.relation, e.trade_date DESC NULLS LAST
    LIMIT %s
    """
    review_actions_sql = """
    SELECT
        review_action_id,
        case_id,
        trade_date::text AS trade_date,
        asset_id,
        action_type,
        gap_reasons,
        reviewer,
        comment,
        created_at::text AS created_at,
        source_context
    FROM research.review_action
    WHERE case_id = %s
    ORDER BY created_at DESC, review_action_id DESC
    LIMIT 5
    """
    with connect(service) as conn:
        case_rows = fetch_all(conn, case_sql, [case_id])
        if not case_rows:
            return None
        claims = [research_claim_read_model(row) for row in fetch_all(conn, claims_sql, [case_id, child_limit])]
        evidence = [
            linked_evidence_read_model(row)
            for row in fetch_all(conn, evidence_sql, [case_id, case_id, child_limit])
        ]
        review_actions = [
            item
            for item in (
                review_action_read_model(row)
                for row in fetch_all(conn, review_actions_sql, [case_id])
            )
            if item is not None
        ]

    case = research_case_read_model(case_rows[0])
    gap_reasons = gap_reasons_for_case(case)
    latest_review_action = review_actions[0] if review_actions else None
    return {
        "case": {
            "case_id": case["case_id"],
            "trade_date": case["trade_date"],
            "asset_id": case["asset_id"],
            "theme": case["theme"],
            "title": case["title"],
            "status": case["status"],
            "priority": case["priority"],
            "source_type": case["source_type"],
            "source_id": case["source_id"],
        },
        "claims": claims,
        "evidence": evidence,
        "summary": {
            "claim_count": len(claims),
            "evidence_count": len({item["evidence_id"] for item in evidence}),
            "missing_or_partial_evidence_count": case["missing_evidence_count"] + case["partial_evidence_count"],
            "evidence_status": case["evidence_status"],
            "missing_evidence_count": case["missing_evidence_count"],
            "partial_evidence_count": case["partial_evidence_count"],
        },
        "gap_reasons": gap_reasons,
        "gap_summary": gap_summary_text(gap_reasons, case),
        "review_actions": review_actions,
        "latest_review_action": latest_review_action,
        "review_status": review_status_from_action((latest_review_action or {}).get("action_type")),
    }


def research_case_detail_read_model(detail: dict[str, Any]) -> dict[str, Any]:
    case = detail.get("case") if isinstance(detail.get("case"), dict) else {}
    claims = detail.get("claims") if isinstance(detail.get("claims"), list) else []
    evidence = detail.get("evidence") if isinstance(detail.get("evidence"), list) else []
    summary = detail.get("summary") if isinstance(detail.get("summary"), dict) else {}
    return {
        "case": {
            "case_id": str(case.get("case_id") or ""),
            "trade_date": str(case.get("trade_date") or ""),
            "asset_id": str(case.get("asset_id") or ""),
            "theme": str(case.get("theme") or ""),
            "title": str(case.get("title") or ""),
            "status": str(case.get("status") or ""),
            "priority": int(case.get("priority") or 0),
            "source_type": str(case.get("source_type") or ""),
            "source_id": str(case.get("source_id") or ""),
        },
        "claims": [research_claim_read_model(item) for item in claims],
        "evidence": [linked_evidence_read_model(item) for item in evidence],
        "summary": {
            "claim_count": int(summary.get("claim_count") or 0),
            "evidence_count": int(summary.get("evidence_count") or 0),
            "missing_or_partial_evidence_count": int(summary.get("missing_or_partial_evidence_count") or 0),
            "evidence_status": str(summary.get("evidence_status") or ""),
            "missing_evidence_count": int(summary.get("missing_evidence_count") or 0),
            "partial_evidence_count": int(summary.get("partial_evidence_count") or 0),
        },
        "gap_reasons": [str(reason) for reason in detail.get("gap_reasons") or []],
        "gap_summary": str(detail.get("gap_summary") or ""),
        "review_actions": [
            item
            for item in (
                review_action_read_model(action)
                for action in (detail.get("review_actions") or [])[:5]
            )
            if item is not None
        ],
        "latest_review_action": review_action_read_model(detail.get("latest_review_action")),
        "review_status": str(detail.get("review_status") or review_status_from_action((detail.get("latest_review_action") or {}).get("action_type"))),
    }


def research_claim_read_model(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    confidence = row.get("confidence")
    return {
        "claim_id": str(row.get("claim_id") or ""),
        "claim_type": str(row.get("claim_type") or ""),
        "claim_text": str(row.get("claim_text") or ""),
        "confidence": float(confidence) if confidence is not None else None,
        "status": str(row.get("status") or ""),
        "source_type": str(row.get("source_type") or metadata.get("source_type") or ""),
        "source_id": str(row.get("source_id") or metadata.get("source_id") or ""),
    }


def linked_evidence_read_model(row: dict[str, Any]) -> dict[str, Any]:
    evidence_metadata = row.get("evidence_metadata") if isinstance(row.get("evidence_metadata"), dict) else {}
    link_metadata = row.get("link_metadata") if isinstance(row.get("link_metadata"), dict) else {}
    allowed_metadata = row.get("allowed_metadata") if isinstance(row.get("allowed_metadata"), dict) else {}
    return {
        "evidence_id": str(row.get("evidence_id") or ""),
        "source_type": str(row.get("source_type") or ""),
        "source_id": str(row.get("source_id") or ""),
        "asset_id": str(row.get("asset_id") or ""),
        "trade_date": str(row.get("trade_date") or ""),
        "title": str(row.get("title") or ""),
        "uri": str(row.get("uri") or ""),
        "content_hash": str(row.get("content_hash") or ""),
        "relation": str(row.get("relation") or ""),
        "target_type": str(row.get("target_type") or ""),
        "target_id": str(row.get("target_id") or ""),
        "allowed_metadata": _allowed_metadata(evidence_metadata, link_metadata, allowed_metadata),
    }


def _allowed_metadata(*metadata_items: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "digest_key",
        "source_type",
        "source_id",
        "seed_version",
        "evidence_status",
        "overall_status",
        "missing",
        "partial",
        "missing_evidence",
        "partial_evidence",
        "missing_evidence_count",
        "partial_evidence_count",
    }
    allowed: dict[str, Any] = {}
    for metadata in metadata_items:
        for key in allowed_keys:
            if key in metadata:
                allowed[key] = metadata[key]
    return allowed


def _clamp_limit(value: int) -> int:
    return max(1, min(100, int(value or 50)))
