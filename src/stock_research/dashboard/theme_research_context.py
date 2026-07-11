from __future__ import annotations

import re
from typing import Any

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
