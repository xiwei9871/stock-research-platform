from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.dashboard.research_queue_gaps import list_research_queue_gaps
from stock_research.research_review_actions import review_action_read_model


DEFAULT_REFRESH_ROOT = Path("outputs/research/research_queue_refresh_v1")


def load_research_queue_health(
    *,
    trade_date: str | None = None,
    output_root: str | Path = DEFAULT_REFRESH_ROOT,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    counts = load_research_queue_counts(trade_date=trade_date, service=service)
    manifest = load_latest_refresh_manifest(trade_date=trade_date, output_root=output_root)
    unmatched_digest_count = _int((manifest or {}).get("counts", {}).get("unmatched_digest"))
    error_count = _int((manifest or {}).get("counts", {}).get("errors"))
    warnings = _health_warnings(counts=counts, unmatched_digest_count=unmatched_digest_count, error_count=error_count)
    gap_payload = list_research_queue_gaps(trade_date=trade_date, limit=5, service=service)
    gap_summary = gap_payload.get("summary") or {}
    status = _health_status(
        counts=counts,
        unmatched_digest_count=unmatched_digest_count,
        error_count=error_count,
        manifest_status=str((manifest or {}).get("status") or ""),
    )
    summary = {
        "case_count": _int(counts.get("cases")),
        "open_case_count": _int(counts.get("open_cases")),
        "claim_count": _int(counts.get("claims")),
        "evidence_artifact_count": _int(counts.get("evidence_artifacts")),
        "evidence_link_count": _int(counts.get("evidence_links")),
        "evidence_gap_count": _int(counts.get("evidence_gap_count")),
        "unmatched_digest_count": unmatched_digest_count,
        "error_count": error_count,
        "no_evidence_count": _int(gap_summary.get("no_evidence_count")),
        "missing_evidence_count": _int(gap_summary.get("missing_evidence_count")),
        "partial_evidence_count": _int(gap_summary.get("partial_evidence_count")),
        "incomplete_evidence_status_count": _int(gap_summary.get("incomplete_evidence_status_count")),
        "unknown_gap_count": _int(gap_summary.get("unknown_gap_count")),
        "reviewed_gap_count": _int(gap_summary.get("reviewed_gap_count")),
        "pending_gap_count": _int(gap_summary.get("pending_gap_count")),
        "deferred_gap_count": _int(gap_summary.get("deferred_gap_count")),
        "request_more_evidence_count": _int(gap_summary.get("request_more_evidence_count")),
    }
    publish_gate_status = _publish_gate_status(summary=summary, health_status=status)
    return research_queue_health_read_model(
        {
            "trade_date": trade_date or "",
            "status": status,
            "can_review": _int(counts.get("open_cases")) > 0,
            "can_publish_research_queue": False,
            "publish_gate_status": publish_gate_status,
            "research_ready_for_publication": publish_gate_status == "research_ready",
            "actual_publish_enabled": False,
            "internal_snapshot_enabled": publish_gate_status == "research_ready",
            "external_delivery_enabled": False,
            "summary": summary,
            "last_refresh": _last_refresh_read_model(manifest),
            "top_gap_cases": gap_payload.get("items") or [],
            "warnings": warnings,
        }
    )


def load_research_queue_counts(
    *,
    trade_date: str | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, int]:
    case_filter = "WHERE trade_date = %s" if trade_date else ""
    params = [trade_date] if trade_date else []
    sql = f"""
    WITH queue_cases AS (
        SELECT
            case_id,
            status,
            metadata->>'evidence_status' AS evidence_status,
            COALESCE((metadata->>'missing_evidence_count')::int, 0) AS missing_evidence_count,
            COALESCE((metadata->>'partial_evidence_count')::int, 0) AS partial_evidence_count
        FROM research.research_case
        {case_filter}
    ),
    case_evidence AS (
        SELECT target_id AS case_id, count(DISTINCT evidence_id) AS evidence_count
        FROM research.evidence_link
        WHERE target_type = 'research_case'
        GROUP BY target_id
    ),
    queue_claims AS (
        SELECT claim_id
        FROM research.research_claim
        WHERE case_id IN (SELECT case_id FROM queue_cases)
    ),
    queue_evidence_links AS (
        SELECT l.link_id, l.evidence_id
        FROM research.evidence_link l
        WHERE
            (l.target_type = 'research_case' AND l.target_id IN (SELECT case_id FROM queue_cases))
            OR (l.target_type = 'research_claim' AND l.target_id IN (SELECT claim_id FROM queue_claims))
    )
    SELECT
        (SELECT count(*) FROM queue_cases) AS cases,
        (SELECT count(*) FROM queue_cases WHERE status = 'open') AS open_cases,
        (SELECT count(*) FROM queue_claims) AS claims,
        (SELECT count(DISTINCT evidence_id) FROM queue_evidence_links) AS evidence_artifacts,
        (SELECT count(*) FROM queue_evidence_links) AS evidence_links,
        (
            SELECT count(*)
            FROM queue_cases c
            LEFT JOIN case_evidence e USING (case_id)
            WHERE
                COALESCE(e.evidence_count, 0) <= 0
                OR c.missing_evidence_count > 0
                OR c.partial_evidence_count > 0
                OR (COALESCE(c.evidence_status, '') <> '' AND lower(c.evidence_status) <> 'complete')
        ) AS evidence_gap_count
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    row = dict(rows[0]) if rows else {}
    return {
        "cases": _int(row.get("cases")),
        "open_cases": _int(row.get("open_cases")),
        "claims": _int(row.get("claims")),
        "evidence_artifacts": _int(row.get("evidence_artifacts")),
        "evidence_links": _int(row.get("evidence_links")),
        "evidence_gap_count": _int(row.get("evidence_gap_count")),
    }


def load_latest_refresh_manifest(
    *,
    trade_date: str | None = None,
    output_root: str | Path = DEFAULT_REFRESH_ROOT,
) -> dict[str, Any] | None:
    root = Path(output_root)
    if trade_date:
        for exact in (
            root / trade_date / "research_queue_refresh_manifest.json",
            root / "research_queue_refresh_manifest.json",
        ):
            if exact.exists():
                return _load_manifest_file(exact)
    candidates = list(root.glob("*/research_queue_refresh_manifest.json") if root.exists() else [])
    existing = [path for path in candidates if path.exists()]
    if not existing:
        return None
    latest = max(existing, key=lambda path: path.stat().st_mtime)
    return _load_manifest_file(latest)


def _load_manifest_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    payload.setdefault("artifact_paths", {})
    payload["artifact_paths"].setdefault("manifest_json", str(path))
    return payload


def research_queue_health_read_model(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "trade_date": str(payload.get("trade_date") or ""),
        "status": str(payload.get("status") or "empty"),
        "can_review": bool(payload.get("can_review")),
        "can_publish_research_queue": False,
        "publish_gate_status": str(payload.get("publish_gate_status") or "empty"),
        "research_ready_for_publication": bool(payload.get("research_ready_for_publication")),
        "actual_publish_enabled": False,
        "internal_snapshot_enabled": bool(payload.get("internal_snapshot_enabled")),
        "external_delivery_enabled": False,
        "summary": {
            "case_count": _int(summary.get("case_count")),
            "open_case_count": _int(summary.get("open_case_count")),
            "claim_count": _int(summary.get("claim_count")),
            "evidence_artifact_count": _int(summary.get("evidence_artifact_count")),
            "evidence_link_count": _int(summary.get("evidence_link_count")),
            "evidence_gap_count": _int(summary.get("evidence_gap_count")),
            "unmatched_digest_count": _int(summary.get("unmatched_digest_count")),
            "error_count": _int(summary.get("error_count")),
            "no_evidence_count": _int(summary.get("no_evidence_count")),
            "missing_evidence_count": _int(summary.get("missing_evidence_count")),
            "partial_evidence_count": _int(summary.get("partial_evidence_count")),
            "incomplete_evidence_status_count": _int(summary.get("incomplete_evidence_status_count")),
            "unknown_gap_count": _int(summary.get("unknown_gap_count")),
            "reviewed_gap_count": _int(summary.get("reviewed_gap_count")),
            "pending_gap_count": _int(summary.get("pending_gap_count")),
            "deferred_gap_count": _int(summary.get("deferred_gap_count")),
            "request_more_evidence_count": _int(summary.get("request_more_evidence_count")),
        },
        "last_refresh": _last_refresh_read_model(payload.get("last_refresh")),
        "top_gap_cases": [_clean_top_gap_case(item) for item in (payload.get("top_gap_cases") or [])[:5]],
        "warnings": [str(item) for item in payload.get("warnings") or []],
    }


def _clean_top_gap_case(item: dict[str, Any]) -> dict[str, Any]:
    latest_review_action = review_action_read_model(item.get("latest_review_action"))
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
        "gap_reasons": [str(reason) for reason in item.get("gap_reasons") or []],
        "gap_summary": str(item.get("gap_summary") or ""),
        "review_status": str(item.get("review_status") or "pending"),
        "latest_review_action": latest_review_action,
        "source_type": str(item.get("source_type") or ""),
        "source_id": str(item.get("source_id") or ""),
    }


def _last_refresh_read_model(manifest: dict[str, Any] | None) -> dict[str, str] | None:
    if not isinstance(manifest, dict):
        return None
    artifact_paths = manifest.get("artifact_paths") if isinstance(manifest.get("artifact_paths"), dict) else {}
    manifest_path = artifact_paths.get("manifest_json") or manifest.get("manifest_path") or ""
    return {
        "run_id": str(manifest.get("run_id") or ""),
        "finished_at": str(manifest.get("finished_at") or ""),
        "manifest_path": str(manifest_path),
    }


def _health_status(
    *,
    counts: dict[str, Any],
    unmatched_digest_count: int,
    error_count: int,
    manifest_status: str,
) -> str:
    if error_count > 0 or manifest_status == "failed":
        return "failed"
    if _int(counts.get("cases")) <= 0:
        return "empty"
    if (
        unmatched_digest_count > 0
        or _int(counts.get("evidence_gap_count")) > 0
        or _int(counts.get("claims")) <= 0
        or _int(counts.get("evidence_artifacts")) <= 0
        or _int(counts.get("evidence_links")) <= 0
    ):
        return "partial"
    return "healthy"


def _health_warnings(*, counts: dict[str, Any], unmatched_digest_count: int, error_count: int) -> list[str]:
    warnings: list[str] = []
    if _int(counts.get("evidence_gap_count")) > 0:
        warnings.append(f"evidence_gap_count={_int(counts.get('evidence_gap_count'))}")
    if unmatched_digest_count > 0:
        warnings.append(f"unmatched_digest_count={unmatched_digest_count}")
    if error_count > 0:
        warnings.append(f"error_count={error_count}")
    if _int(counts.get("cases")) > 0 and _int(counts.get("claims")) <= 0:
        warnings.append("claim_count=0")
    if _int(counts.get("cases")) > 0 and _int(counts.get("evidence_links")) <= 0:
        warnings.append("evidence_link_count=0")
    return warnings


def _publish_gate_status(*, summary: dict[str, Any], health_status: str) -> str:
    if _int(summary.get("error_count")) > 0 or health_status == "failed":
        return "failed"
    if _int(summary.get("case_count")) <= 0:
        return "empty"
    reviewed = _int(summary.get("reviewed_gap_count"))
    pending = _int(summary.get("pending_gap_count"))
    request_more = _int(summary.get("request_more_evidence_count"))
    deferred = _int(summary.get("deferred_gap_count"))
    unexplained_gaps = max(0, _int(summary.get("evidence_gap_count")) - reviewed - pending - request_more - deferred)
    if (
        _int(summary.get("unmatched_digest_count")) > 0
        or pending > 0
        or request_more > 0
        or deferred > 0
        or unexplained_gaps > 0
        or _int(summary.get("claim_count")) <= 0
        or _int(summary.get("evidence_link_count")) <= 0
    ):
        return "blocked"
    return "research_ready"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
