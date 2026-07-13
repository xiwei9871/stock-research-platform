from __future__ import annotations

from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.research_queue_gaps import list_research_queue_gaps
from stock_research.dashboard.research_queue_health import load_research_queue_health


PUBLICATION_ENTRYPOINT_STATUS = "scaffolded"


def get_research_publish_gate(
    *,
    trade_date: str,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    health = load_research_queue_health(trade_date=trade_date, service=service)
    summary = _clean_summary(health.get("summary"))
    gap_payload = list_research_queue_gaps(trade_date=trade_date, limit=5, service=service)
    status, blockers = _gate_status_and_blockers(summary=summary, health_status=str(health.get("status") or ""))
    research_ready = status == "research_ready"
    warnings: list[dict[str, Any]] = []
    if research_ready:
        warnings.append(
            _notice(
                "external_delivery_not_connected",
                "External research delivery is not connected",
                1,
            )
        )
    elif status == "blocked":
        blockers.append(
            _notice(
                "external_delivery_not_connected",
                "External research delivery is not connected",
                1,
            )
        )

    return research_publish_gate_read_model(
        {
            "trade_date": trade_date,
            "status": status,
            "research_ready_for_publication": research_ready,
            "actual_publish_enabled": False,
            "internal_snapshot_enabled": research_ready,
            "external_delivery_enabled": False,
            "publication_entrypoint_status": PUBLICATION_ENTRYPOINT_STATUS,
            "summary": summary,
            "blockers": blockers,
            "warnings": warnings,
            "top_blocked_cases": _top_blocked_cases(gap_payload.get("items") or [], status=status),
        }
    )


def research_publish_gate_read_model(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "trade_date": str(payload.get("trade_date") or ""),
        "status": _status(payload.get("status")),
        "research_ready_for_publication": bool(payload.get("research_ready_for_publication")),
        "actual_publish_enabled": False,
        "internal_snapshot_enabled": bool(payload.get("internal_snapshot_enabled")),
        "external_delivery_enabled": False,
        "publication_entrypoint_status": PUBLICATION_ENTRYPOINT_STATUS,
        "summary": _clean_summary(payload.get("summary")),
        "blockers": [_clean_notice(item) for item in payload.get("blockers") or []],
        "warnings": [_clean_notice(item) for item in payload.get("warnings") or []],
        "top_blocked_cases": [_clean_blocked_case(item) for item in (payload.get("top_blocked_cases") or [])[:5]],
    }


def publish_gate_status_from_summary(summary: dict[str, Any], *, health_status: str = "") -> tuple[str, bool]:
    clean = _clean_summary(summary)
    status, blockers = _gate_status_and_blockers(summary=clean, health_status=health_status)
    return status, status == "research_ready" and not blockers


def _gate_status_and_blockers(*, summary: dict[str, int], health_status: str) -> tuple[str, list[dict[str, Any]]]:
    if _int(summary.get("error_count")) > 0 or health_status == "failed":
        return (
            "failed",
            [_notice("refresh_errors", f"{_int(summary.get('error_count'))} refresh errors were recorded", _int(summary.get("error_count")))],
        )
    if _int(summary.get("case_count")) <= 0:
        return "empty", []

    blockers: list[dict[str, Any]] = []
    if _int(summary.get("unmatched_digest_count")) > 0:
        count = _int(summary.get("unmatched_digest_count"))
        blockers.append(_notice("unmatched_digest", f"{count} digest snapshots did not match a case", count))
    if _int(summary.get("pending_gap_count")) > 0:
        count = _int(summary.get("pending_gap_count"))
        blockers.append(_notice("pending_gap", f"{count} gap cases have not been reviewed", count))
    if _int(summary.get("request_more_evidence_count")) > 0:
        count = _int(summary.get("request_more_evidence_count"))
        blockers.append(_notice("request_more_evidence", f"{count} gap cases require more evidence", count))
    if _int(summary.get("deferred_gap_count")) > 0:
        count = _int(summary.get("deferred_gap_count"))
        blockers.append(_notice("deferred_gap", f"{count} gap cases were deferred", count))
    explained_gap_count = (
        _int(summary.get("reviewed_gap_count"))
        + _int(summary.get("pending_gap_count"))
        + _int(summary.get("request_more_evidence_count"))
        + _int(summary.get("deferred_gap_count"))
    )
    unexplained_gap_count = max(0, _int(summary.get("evidence_gap_count")) - explained_gap_count)
    if unexplained_gap_count > 0:
        blockers.append(
            _notice("unexplained_evidence_gap", f"{unexplained_gap_count} evidence gaps have no review state", unexplained_gap_count)
        )
    if _int(summary.get("case_count")) > 0 and _int(summary.get("claim_count")) <= 0:
        blockers.append(_notice("missing_claims", "Research queue has cases but no claims", 1))
    if _int(summary.get("case_count")) > 0 and _int(summary.get("evidence_link_count")) <= 0:
        blockers.append(_notice("missing_evidence_links", "Research queue has cases but no evidence links", 1))

    if blockers:
        return "blocked", blockers
    return "research_ready", []


def _top_blocked_cases(items: list[dict[str, Any]], *, status: str) -> list[dict[str, Any]]:
    if status not in {"blocked", "failed"}:
        return []
    return [_clean_blocked_case(item) for item in items[:5]]


def _clean_blocked_case(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": str(item.get("case_id") or ""),
        "trade_date": str(item.get("trade_date") or ""),
        "asset_id": str(item.get("asset_id") or ""),
        "theme": str(item.get("theme") or ""),
        "title": str(item.get("title") or ""),
        "review_status": str(item.get("review_status") or "pending"),
        "gap_reasons": [str(reason) for reason in item.get("gap_reasons") or []],
        "gap_summary": str(item.get("gap_summary") or ""),
    }


def _clean_summary(value: Any) -> dict[str, int]:
    summary = value if isinstance(value, dict) else {}
    return {
        "case_count": _int(summary.get("case_count")),
        "open_case_count": _int(summary.get("open_case_count")),
        "claim_count": _int(summary.get("claim_count")),
        "evidence_artifact_count": _int(summary.get("evidence_artifact_count")),
        "evidence_link_count": _int(summary.get("evidence_link_count")),
        "evidence_gap_count": _int(summary.get("evidence_gap_count")),
        "pending_gap_count": _int(summary.get("pending_gap_count")),
        "reviewed_gap_count": _int(summary.get("reviewed_gap_count")),
        "request_more_evidence_count": _int(summary.get("request_more_evidence_count")),
        "deferred_gap_count": _int(summary.get("deferred_gap_count")),
        "unmatched_digest_count": _int(summary.get("unmatched_digest_count")),
        "error_count": _int(summary.get("error_count")),
    }


def _notice(code: str, message: str, count: int) -> dict[str, Any]:
    return {"code": code, "message": message, "count": _int(count)}


def _clean_notice(value: Any) -> dict[str, Any]:
    notice = value if isinstance(value, dict) else {}
    return {
        "code": str(notice.get("code") or ""),
        "message": str(notice.get("message") or ""),
        "count": _int(notice.get("count")),
    }


def _status(value: Any) -> str:
    status = str(value or "empty")
    if status not in {"blocked", "research_ready", "empty", "failed", "entrypoint_missing"}:
        return "blocked"
    return status


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
