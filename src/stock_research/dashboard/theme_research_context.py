from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timezone
import re
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.dashboard.theme_research_db import load_db_context


_COMPANY_CODE = re.compile(r"^(?P<symbol>\d{6})\.(?P<exchange>SZ|SH|BJ)$")
_PREFIXED_CODE = re.compile(r"^(?P<exchange>SZ|SH|BJ)(?P<symbol>\d{6})$")
_PLATFORM_ASSET_ID = re.compile(
    r"^(?:CN:)?(?P<exchange>SZ|SH|BJ):(?P<symbol>\d{6})$"
)


def normalize_theme_research_company_code(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if not raw:
        return ""
    match = _COMPANY_CODE.fullmatch(raw)
    if match:
        return f"{match.group('symbol')}.{match.group('exchange')}"
    match = _PREFIXED_CODE.fullmatch(raw)
    if match:
        return f"{match.group('symbol')}.{match.group('exchange')}"
    match = _PLATFORM_ASSET_ID.fullmatch(raw)
    if match:
        return f"{match.group('symbol')}.{match.group('exchange')}"
    if raw.isdigit() and len(raw) <= 6:
        symbol = raw.zfill(6)
        exchange = "SH" if symbol.startswith("6") else "BJ" if symbol.startswith(("4", "8")) else "SZ"
        return f"{symbol}.{exchange}"
    return ""


def load_asset_theme_context(
    asset_id: str,
    *,
    service: str | None = None,
) -> dict[str, Any]:
    return build_asset_theme_context(asset_id, load_db_context(service=service))


def load_asset_theme_context_for_workflow(
    asset_id: str,
    *,
    service: str | None = None,
) -> dict[str, Any]:
    try:
        return load_asset_theme_context(asset_id, service=service)
    except Exception:
        return unavailable_asset_theme_context(asset_id)


def enrich_watchlist_rows(
    rows: list[dict[str, Any]],
    *,
    service: str | None = None,
) -> list[dict[str, Any]]:
    try:
        context = load_db_context(service=service)
    except Exception:
        return [
            {
                **row,
                "theme_research_context": unavailable_asset_theme_context(
                    str(row.get("asset_id") or row.get("stock_code") or "")
                ),
            }
            for row in rows
        ]
    return [
        {
            **row,
            "theme_research_context": build_asset_theme_context(
                str(row.get("asset_id") or row.get("stock_code") or ""), context
            ),
        }
        for row in rows
    ]


def unavailable_asset_theme_context(asset_id: str) -> dict[str, Any]:
    return {
        "asset_id": str(asset_id),
        "company_code": normalize_theme_research_company_code(asset_id),
        "status": "unavailable",
        "driver_assessment": "insufficient_evidence",
        "theme_count": 0,
        "mapping_count": 0,
        "evidence_gap_count": 0,
        "themes": [],
        "mappings": [],
        "excluded_mappings": [],
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
        "source": "research.theme_research_company_mapping",
        "warnings": ["theme_research_context_unavailable"],
    }


def list_theme_research_updates(
    *,
    since: str | None = None,
    limit: int = 100,
    service: str | None = None,
) -> dict[str, Any]:
    parsed_since = _parse_since(since)
    bounded_limit = _validate_limit(limit)
    conditions = ["true"]
    params: list[Any] = []
    if parsed_since is not None:
        conditions.append("created_at >= %s")
        params.append(parsed_since)
    params.append(bounded_limit)
    selected_service = service or SETTINGS.theme_research_runtime_service
    with connect(selected_service) as conn:
        review_events = fetch_all(
            conn,
            f"""
            SELECT review_event_id, theme_id, object_type, object_id,
                   from_status, to_status, decision, comment, created_at
            FROM research.theme_research_review_event
            WHERE {' AND '.join(conditions)}
              AND (
                    (object_type = 'source' AND to_status = 'accepted')
                 OR (object_type IN ('claim', 'node') AND to_status = 'reviewed')
                 OR (object_type = 'theme' AND to_status IN ('reviewed', 'published'))
              )
            ORDER BY created_at DESC, review_event_id DESC
            LIMIT %s
            """,
            params,
        )
        revisions = fetch_all(
            conn,
            f"""
            SELECT revision_id, theme_id, object_type, object_id, operation,
                   after_payload, created_at
            FROM research.theme_research_object_revision
            WHERE {' AND '.join(conditions)}
              AND object_type = 'company_mappings'
              AND after_payload ->> 'review_status' = 'reviewed'
            ORDER BY created_at DESC, revision_id DESC
            LIMIT %s
            """,
            params,
        )
    return build_theme_research_updates(
        review_events,
        revisions,
        since=since,
        limit=bounded_limit,
    )


def build_theme_research_updates(
    review_events: list[dict[str, Any]],
    revisions: list[dict[str, Any]],
    *,
    since: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    parsed_since = _parse_since(since)
    bounded_limit = _validate_limit(limit)
    items: list[dict[str, Any]] = []
    accepted_statuses = {
        "source": {"accepted"},
        "claim": {"reviewed"},
        "node": {"reviewed"},
        "theme": {"reviewed", "published"},
    }
    for row in review_events:
        object_type = str(row.get("object_type") or "")
        if str(row.get("to_status") or "") not in accepted_statuses.get(
            object_type, set()
        ):
            continue
        if not _created_at_in_range(row.get("created_at"), parsed_since):
            continue
        items.append(
            {
                "update_id": str(row["review_event_id"]),
                "theme_id": str(row["theme_id"]),
                "object_type": object_type,
                "object_id": str(row["object_id"]),
                "from_status": str(row.get("from_status") or ""),
                "to_status": str(row.get("to_status") or ""),
                "decision": str(row.get("decision") or ""),
                "summary": str(row.get("comment") or ""),
                "created_at": _datetime_text(row.get("created_at")),
            }
        )
    for row in revisions:
        after_payload = row.get("after_payload")
        if not isinstance(after_payload, dict):
            continue
        if row.get("object_type") not in {"company_mapping", "company_mappings"}:
            continue
        if after_payload.get("review_status") != "reviewed":
            continue
        if not _created_at_in_range(row.get("created_at"), parsed_since):
            continue
        items.append(
            {
                "update_id": str(row["revision_id"]),
                "theme_id": str(row["theme_id"]),
                "object_type": "company_mapping",
                "object_id": str(row["object_id"]),
                "from_status": "",
                "to_status": "reviewed",
                "decision": str(row.get("operation") or "update"),
                "summary": str(after_payload.get("relationship_summary") or ""),
                "created_at": _datetime_text(row.get("created_at")),
            }
        )
    items.sort(key=lambda row: (row["created_at"], row["update_id"]), reverse=True)
    items = items[:bounded_limit]
    counts = Counter(row["object_type"] for row in items)
    return {
        "total": len(items),
        "items": items,
        "by_object_type": {key: counts[key] for key in sorted(counts)},
        "since": since or "",
        "limit": bounded_limit,
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
        "source": "research.theme_research_review_event",
        "warnings": [],
    }


def build_daily_theme_research_digest(
    trade_date: str,
    *,
    context: dict[str, Any] | None = None,
    updates: dict[str, Any] | None = None,
    service: str | None = None,
) -> dict[str, Any]:
    _parse_since(trade_date)
    selected_context = context or load_db_context(service=service)
    selected_updates = updates or list_theme_research_updates(
        since=trade_date,
        limit=100,
        service=service,
    )
    company_codes = sorted(
        {
            normalize_theme_research_company_code(row.get("company_code"))
            for row in selected_context["mapping_package"]["company_mappings"]
        }
        - {""}
    )
    contexts = [
        build_asset_theme_context(company_code, selected_context)
        for company_code in company_codes
    ]
    mappings = [
        mapping
        for asset_context in contexts
        for mapping in asset_context["mappings"]
    ]
    mappings.sort(
        key=lambda row: (
            -(row.get("company_research_priority_score") or 0),
            row["company_code"],
            row["mapping_id"],
        )
    )
    mapped_companies = []
    seen_companies: set[str] = set()
    themes_by_id = {
        row["theme_id"]: row for row in selected_context["theme_package"]["themes"]
    }
    for mapping in mappings:
        if mapping["company_code"] in seen_companies:
            continue
        seen_companies.add(mapping["company_code"])
        mapped_companies.append(
            {
                "company_code": mapping["company_code"],
                "company_name": mapping["company_name"],
                "theme_id": mapping["theme_id"],
                "theme_name": str(
                    themes_by_id.get(mapping["theme_id"], {}).get("theme_name") or ""
                ),
                "node_id": mapping["node"]["node_id"],
                "node_name": mapping["node"]["node_name"],
                "company_research_priority_score": mapping.get(
                    "company_research_priority_score"
                ),
                "stock_workspace_path": (
                    f"/stocks/{mapping['company_code']}?source=theme_research"
                ),
                "theme_dashboard_path": f"/theme-research/{mapping['theme_id']}",
            }
        )
    incomplete_tracks = []
    robotics_theme_id = "humanoid_robotics_head_to_toe_v1"
    if any(
        row["theme_id"] == robotics_theme_id
        for row in selected_context["theme_package"]["themes"]
    ) and not any(row["theme_id"] == robotics_theme_id for row in mappings):
        incomplete_tracks.append("humanoid_robotics_source_pack_v1")
    return {
        "trade_date": trade_date,
        "status": "ready",
        "reviewed_theme_count": len({row["theme_id"] for row in mappings}),
        "mapped_company_count": len(mapped_companies),
        "reviewed_mapping_count": len(mappings),
        "recent_reviewed_update_count": int(selected_updates.get("total") or 0),
        "evidence_gap_count": len(selected_context.get("evidence_gap_priorities", [])),
        "incomplete_evidence_tracks": incomplete_tracks,
        "mapped_companies": mapped_companies,
        "recent_updates": list(selected_updates.get("items") or []),
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
        "source": "research.theme_research_company_mapping",
        "warnings": [],
    }


def unavailable_daily_theme_research_digest(trade_date: str) -> dict[str, Any]:
    return {
        "trade_date": trade_date,
        "status": "partial",
        "reviewed_theme_count": 0,
        "mapped_company_count": 0,
        "reviewed_mapping_count": 0,
        "recent_reviewed_update_count": 0,
        "evidence_gap_count": 0,
        "incomplete_evidence_tracks": [],
        "mapped_companies": [],
        "recent_updates": [],
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
        "source": "research.theme_research_company_mapping",
        "warnings": ["theme_research_digest_unavailable"],
    }


def build_asset_theme_context(
    asset_id: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    company_code = normalize_theme_research_company_code(asset_id)
    mapping_package = context["mapping_package"]
    theme_package = context["theme_package"]

    themes_by_id = {row["theme_id"]: row for row in theme_package["themes"]}
    nodes_by_id = {row["node_id"]: row for row in theme_package["nodes"]}
    sources_by_id = {
        row["source_id"]: row
        for row in [*theme_package["sources"], *mapping_package["sources"]]
    }
    claims_by_id = {row["claim_id"]: row for row in theme_package["claims"]}
    evidence_items_by_id = {
        row["evidence_id"]: row for row in mapping_package["evidence_items"]
    }
    priorities_by_mapping = {
        row["mapping_id"]: row for row in context.get("company_priorities", [])
    }

    candidates = [
        row
        for row in mapping_package["company_mappings"]
        if normalize_theme_research_company_code(row.get("company_code")) == company_code
    ]
    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for mapping in sorted(candidates, key=lambda row: row["mapping_id"]):
        node_id = str(mapping["mapped_node_id"])
        node = nodes_by_id.get(node_id)
        reasons: list[str] = []
        if mapping.get("review_status") != "reviewed":
            reasons.append("mapping_not_reviewed")
        if node is None:
            reasons.append("mapped_node_missing")
        elif node.get("node_review_status") != "reviewed":
            reasons.append("mapped_node_not_reviewed")

        evidence_rows = [
            evidence_items_by_id[evidence_id]
            for evidence_id in mapping.get("evidence_ids", [])
            if evidence_id in evidence_items_by_id
        ]
        if not evidence_rows:
            reasons.append("mapping_evidence_missing")
        hydrated_evidence: list[dict[str, Any]] = []
        for evidence in evidence_rows:
            source = sources_by_id.get(evidence["source_id"])
            if source is None:
                reasons.append("mapping_evidence_source_missing")
                continue
            if source.get("review_status") != "accepted":
                reasons.append("mapping_evidence_source_not_accepted")
                continue
            hydrated_evidence.append(
                {
                    **evidence,
                    "source": _source_read_model(source),
                }
            )

        if reasons:
            excluded.append(
                {
                    "mapping_id": mapping["mapping_id"],
                    "theme_id": mapping["theme_id"],
                    "node_id": node_id,
                    "reasons": sorted(set(reasons)),
                }
            )
            continue

        reviewed_claims = _reviewed_claims_for_node(
            node_id,
            theme_package["claims"],
            sources_by_id,
        )
        priority = priorities_by_mapping.get(mapping["mapping_id"], {})
        eligible.append(
            {
                **mapping,
                "node": _node_read_model(node),
                "evidence_items": sorted(
                    hydrated_evidence, key=lambda row: row["evidence_id"]
                ),
                "reviewed_claims": reviewed_claims,
                "company_relevance_score": priority.get("company_relevance_score"),
                "company_research_priority_score": priority.get(
                    "company_research_priority_score"
                ),
                "priority_band": priority.get("priority_band", ""),
                "recommended_action": priority.get("recommended_action", ""),
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )

    eligible.sort(
        key=lambda row: (
            -(row.get("company_research_priority_score") or 0),
            row["theme_id"],
            row["mapping_id"],
        )
    )
    theme_ids = sorted({row["theme_id"] for row in eligible})
    themes = [
        {
            **themes_by_id[theme_id],
            "dashboard_path": f"/theme-research/{theme_id}",
            "research_only": True,
            "used_for_signal": False,
            "used_for_admission": False,
        }
        for theme_id in theme_ids
    ]
    if eligible:
        status = "reviewed_context_available"
        driver_assessment = "mixed_or_uncertain"
    elif candidates:
        status = "evidence_gap"
        driver_assessment = "insufficient_evidence"
    else:
        status = "not_mapped"
        driver_assessment = "insufficient_evidence"
    return {
        "asset_id": str(asset_id),
        "company_code": company_code,
        "status": status,
        "driver_assessment": driver_assessment,
        "theme_count": len(themes),
        "mapping_count": len(eligible),
        "evidence_gap_count": len(excluded),
        "themes": themes,
        "mappings": eligible,
        "excluded_mappings": excluded,
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
        "source": "research.theme_research_company_mapping",
        "warnings": [],
    }


def _reviewed_claims_for_node(
    node_id: str,
    claims: list[dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for claim in claims:
        if node_id not in claim.get("affected_theme_nodes", []):
            continue
        if claim.get("platform_use_status") != "reviewed":
            continue
        source_ids = {
            str(claim.get("source_id") or ""),
            *(str(source_id) for source_id in claim.get("supporting_source_ids", [])),
        }
        if not source_ids or any(
            source_id not in sources_by_id
            or sources_by_id[source_id].get("review_status") != "accepted"
            for source_id in source_ids
        ):
            continue
        result.append(
            {
                "claim_id": claim["claim_id"],
                "claim_text": claim["claim_text"],
                "claim_type": claim["claim_type"],
                "confidence": claim["confidence"],
                "evidence_status": claim["evidence_status"],
                "platform_use_status": claim["platform_use_status"],
                "supporting_source_ids": sorted(source_ids),
            }
        )
    return sorted(result, key=lambda row: row["claim_id"])


def _source_read_model(source: dict[str, Any]) -> dict[str, Any]:
    return {
        key: source.get(key)
        for key in (
            "source_id",
            "source_type",
            "title",
            "publisher",
            "publish_date",
            "url_or_ref",
            "access_level",
            "reliability_level",
            "review_status",
        )
    }


def _node_read_model(node: dict[str, Any]) -> dict[str, Any]:
    return {
        key: node.get(key)
        for key in (
            "node_id",
            "theme_id",
            "parent_node_id",
            "node_name",
            "node_type",
            "description",
            "value_capture_score",
            "bottleneck_score",
            "localization_gap_score",
            "supply_tightness_score",
            "evidence_strength",
            "node_review_status",
        )
    }


def _validate_limit(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError("theme_research_limit_invalid")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("theme_research_limit_invalid") from exc
    if normalized < 1 or normalized > 500:
        raise ValueError("theme_research_limit_invalid")
    return normalized


def _parse_since(value: str | None) -> datetime | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    try:
        if len(text) == 10:
            return datetime.combine(date.fromisoformat(text), time.min, tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("theme_research_since_invalid") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _created_at_in_range(value: Any, since: datetime | None) -> bool:
    if since is None:
        return True
    if isinstance(value, datetime):
        candidate = value
    else:
        try:
            candidate = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return False
    if candidate.tzinfo is None:
        candidate = candidate.replace(tzinfo=timezone.utc)
    return candidate >= since


def _datetime_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")
