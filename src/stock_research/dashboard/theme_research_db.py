from __future__ import annotations

import copy
from functools import lru_cache
import json
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.theme_research_store import (
    build_theme_artifact_from_package,
    load_database_package,
)
from stock_research import theme_research_priority as priority


def load_db_context(
    service: str | None = None,
) -> dict[str, Any]:
    normalized = load_database_package(
        service=service or SETTINGS.theme_research_runtime_service
    )
    artifact_context = priority.load_theme_research_priority_package()
    theme_package = _theme_package(normalized)
    mapping_package = _mapping_package(normalized, theme_package)
    node_priorities = priority._build_node_priorities(  # noqa: SLF001
        theme_package["nodes"], artifact_context["policy"]
    )
    integration_by_mapping = priority._integration_by_mapping(  # noqa: SLF001
        artifact_context["crosswalk_package"]
    )
    company_priorities = priority._build_company_priorities(  # noqa: SLF001
        mapping_package["company_mappings"],
        node_priorities,
        integration_by_mapping,
        artifact_context["policy"],
    )
    evidence_gaps = priority._build_evidence_gap_priorities(  # noqa: SLF001
        node_priorities, company_priorities
    )
    review_queue = priority._build_review_queue(  # noqa: SLF001
        node_priorities, company_priorities, artifact_context["policy"]
    )
    return {
        **artifact_context,
        "theme_package": theme_package,
        "mapping_package": mapping_package,
        "node_priorities": node_priorities,
        "company_priorities": company_priorities,
        "evidence_gap_priorities": evidence_gaps,
        "review_queue": review_queue,
    }


def load_asset_db_context(
    company_code: str,
    *,
    service: str | None = None,
) -> dict[str, Any]:
    selected_service = service or SETTINGS.theme_research_runtime_service
    with connect(selected_service) as conn:
        mapping_rows = fetch_all(
            conn,
            """
            SELECT m.mapping_id, m.theme_id, m.node_id AS mapped_node_id,
                   m.company_code, m.company_name, m.market, m.mapping_type,
                   m.confidence, m.revenue_relevance, m.bottleneck_relevance,
                   m.business_materiality, m.business_stage, m.product_or_service,
                   m.relationship_summary, m.review_status, m.notes,
                   t.theme_name, t.theme_type, t.summary AS theme_summary,
                   t.status AS theme_status, t.created_from, t.last_updated,
                   n.parent_node_id, n.node_name, n.node_type,
                   n.description AS node_description, n.value_capture_score,
                   n.bottleneck_score, n.localization_gap_score,
                   n.supply_tightness_score, n.evidence_strength,
                   n.node_review_status
            FROM research.theme_research_company_mapping m
            JOIN research.theme_research_theme t
              ON t.theme_id = m.theme_id AND t.is_active = true
            JOIN research.theme_research_node n
              ON n.node_id = m.node_id AND n.is_active = true
            WHERE m.company_code = %s AND m.is_active = true
            ORDER BY m.mapping_id
            """,
            [company_code],
        )
        evidence_rows = fetch_all(
            conn,
            """
            SELECT me.mapping_id, e.evidence_id, e.source_id, e.evidence_type,
                   e.excerpt_locator, e.evidence_summary,
                   e.related_company_codes, e.related_node_ids
            FROM research.theme_research_company_mapping m
            JOIN research.theme_research_company_mapping_evidence me
              ON me.mapping_id = m.mapping_id
             AND me.evidence_type = 'mapping_evidence_item'
            JOIN research.theme_research_mapping_evidence_item e
              ON e.evidence_id = me.evidence_id AND e.is_active = true
            WHERE m.company_code = %s AND m.is_active = true
            ORDER BY me.mapping_id, e.evidence_id
            """,
            [company_code],
        )
        claim_rows = fetch_all(
            conn,
            """
            SELECT c.claim_id, c.theme_id, c.source_id, c.claim_text,
                   c.claim_type, c.confidence, c.evidence_status,
                   c.platform_use_status, cn.node_id,
                   COALESCE(array_agg(DISTINCT cs.source_id)
                       FILTER (WHERE cs.source_id IS NOT NULL), ARRAY[]::text[])
                       AS supporting_source_ids
            FROM research.theme_research_company_mapping m
            JOIN research.theme_research_claim_node cn ON cn.node_id = m.node_id
            JOIN research.theme_research_content_claim c
              ON c.claim_id = cn.claim_id AND c.is_active = true
            LEFT JOIN research.theme_research_claim_source cs
              ON cs.claim_id = c.claim_id
            WHERE m.company_code = %s AND m.is_active = true
            GROUP BY c.claim_id, c.theme_id, c.source_id, c.claim_text,
                     c.claim_type, c.confidence, c.evidence_status,
                     c.platform_use_status, cn.node_id
            ORDER BY c.claim_id
            """,
            [company_code],
        )
        source_ids = sorted(
            {
                str(row["source_id"])
                for row in evidence_rows
            }
            | {
                str(row["source_id"])
                for row in claim_rows
            }
            | {
                str(source_id)
                for row in claim_rows
                for source_id in row.get("supporting_source_ids", [])
            }
        )
        source_rows = (
            fetch_all(
                conn,
                """
                SELECT source_id, source_type, title, publisher, author,
                       publish_date, url_or_ref, access_level,
                       reliability_level, review_status, notes
                FROM research.theme_research_source_item
                WHERE source_id = ANY(%s) AND is_active = true
                ORDER BY source_id
                """,
                [source_ids],
            )
            if source_ids
            else []
        )

    mappings = []
    themes_by_id: dict[str, dict[str, Any]] = {}
    nodes_by_id: dict[str, dict[str, Any]] = {}
    evidence_by_mapping: dict[str, list[str]] = {}
    for row in evidence_rows:
        evidence_by_mapping.setdefault(str(row["mapping_id"]), []).append(
            str(row["evidence_id"])
        )
    for row in mapping_rows:
        theme_id = str(row["theme_id"])
        node_id = str(row["mapped_node_id"])
        themes_by_id.setdefault(
            theme_id,
            {
                "theme_id": theme_id,
                "theme_name": str(row["theme_name"]),
                "theme_type": str(row["theme_type"]),
                "summary": str(row["theme_summary"]),
                "status": str(row["theme_status"]),
                "created_from": str(row["created_from"]),
                "last_updated": str(row["last_updated"]),
            },
        )
        nodes_by_id.setdefault(
            node_id,
            {
                "node_id": node_id,
                "theme_id": theme_id,
                "parent_node_id": row.get("parent_node_id"),
                "node_name": str(row["node_name"]),
                "node_type": str(row["node_type"]),
                "description": str(row["node_description"]),
                "value_capture_score": int(row["value_capture_score"]),
                "bottleneck_score": int(row["bottleneck_score"]),
                "localization_gap_score": int(row["localization_gap_score"]),
                "supply_tightness_score": int(row["supply_tightness_score"]),
                "evidence_strength": int(row["evidence_strength"]),
                "node_review_status": str(row["node_review_status"]),
            },
        )
        mapping = {
            key: row.get(key)
            for key in (
                "mapping_id",
                "theme_id",
                "mapped_node_id",
                "company_code",
                "company_name",
                "market",
                "mapping_type",
                "confidence",
                "revenue_relevance",
                "bottleneck_relevance",
                "business_materiality",
                "business_stage",
                "product_or_service",
                "relationship_summary",
                "review_status",
                "notes",
            )
        }
        mapping["confidence"] = float(mapping["confidence"])
        mapping["evidence_ids"] = sorted(
            evidence_by_mapping.get(str(row["mapping_id"]), [])
        )
        mappings.append(mapping)

    claims = [
        {
            "claim_id": str(row["claim_id"]),
            "theme_id": str(row["theme_id"]),
            "source_id": str(row["source_id"]),
            "claim_text": str(row["claim_text"]),
            "claim_type": str(row["claim_type"]),
            "confidence": float(row["confidence"]),
            "evidence_status": str(row["evidence_status"]),
            "platform_use_status": str(row["platform_use_status"]),
            "supporting_source_ids": sorted(
                str(value) for value in row.get("supporting_source_ids", [])
            ),
            "affected_theme_nodes": [str(row["node_id"])],
        }
        for row in claim_rows
    ]
    priority_context = _build_scoped_priority_context(
        list(nodes_by_id.values()),
        mappings,
    )
    return {
        "policy": priority_context["policy"],
        "priority_status": priority_context["priority_status"],
        "theme_package": {
            "themes": list(themes_by_id.values()),
            "nodes": list(nodes_by_id.values()),
            "sources": [copy.deepcopy(row) for row in source_rows],
            "claims": claims,
            "value_capture_assessments": [],
            "decomposition_templates": [],
        },
        "mapping_package": {
            "themes": list(themes_by_id.values()),
            "theme_nodes": list(nodes_by_id.values()),
            "sources": [copy.deepcopy(row) for row in source_rows],
            "evidence_items": [
                {
                    key: row.get(key)
                    for key in (
                        "evidence_id",
                        "source_id",
                        "evidence_type",
                        "excerpt_locator",
                        "evidence_summary",
                        "related_company_codes",
                        "related_node_ids",
                    )
                }
                for row in evidence_rows
            ],
            "company_mappings": mappings,
        },
        "node_priorities": priority_context["node_priorities"],
        "company_priorities": priority_context["company_priorities"],
        "evidence_gap_priorities": priority_context["evidence_gap_priorities"],
        "review_queue": priority_context["review_queue"],
    }


@lru_cache(maxsize=1)
def _load_workflow_priority_support() -> dict[str, Any]:
    policy = priority._load_policy(priority.THEME_RESEARCH_PRIORITY_POLICY_DIR)  # noqa: SLF001
    integration_by_mapping: dict[str, dict[str, Any]] = {}
    for path in sorted(priority.TECH_BOTTLENECK_CROSSWALK_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("crosswalks", []):
            integration_by_mapping[str(row["mapping_id"])] = {
                "integration_status": "linked_existing_universe",
                "integration_ref": str(row["crosswalk_id"]),
                "existing_review_context": {
                    "status": "pending_review",
                    "reviewer_decision": "",
                },
            }
        for row in payload.get("coverage_gaps", []):
            integration_by_mapping[str(row["mapping_id"])] = {
                "integration_status": "coverage_gap",
                "integration_ref": str(row["gap_id"]),
                "existing_review_context": {
                    "status": "not_in_existing_universe",
                    "reviewer_decision": "",
                },
            }
    return {"policy": policy, "integration_by_mapping": integration_by_mapping}


def _build_scoped_priority_context(
    nodes: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
) -> dict[str, Any]:
    unavailable = {
        "policy": None,
        "node_priorities": [],
        "company_priorities": [],
        "evidence_gap_priorities": [],
        "review_queue": [],
        "priority_status": "unavailable",
    }
    try:
        support = _load_workflow_priority_support()
        policy = support["policy"]
        integration_by_mapping = copy.deepcopy(support["integration_by_mapping"])
        for mapping in mappings:
            integration_by_mapping.setdefault(
                str(mapping["mapping_id"]),
                {
                    "integration_status": "coverage_gap",
                    "integration_ref": f"unmapped:{mapping['mapping_id']}",
                    "existing_review_context": {
                        "status": "not_in_existing_universe",
                        "reviewer_decision": "",
                    },
                },
            )
        node_priorities = priority._build_node_priorities(nodes, policy)  # noqa: SLF001
        company_priorities = priority._build_company_priorities(  # noqa: SLF001
            mappings,
            node_priorities,
            integration_by_mapping,
            policy,
        )
        evidence_gaps = priority._build_evidence_gap_priorities(  # noqa: SLF001
            node_priorities,
            company_priorities,
        )
        review_queue = priority._build_review_queue(  # noqa: SLF001
            node_priorities,
            company_priorities,
            policy,
        )
    except Exception:
        return unavailable
    return {
        "policy": policy,
        "node_priorities": node_priorities,
        "company_priorities": company_priorities,
        "evidence_gap_priorities": evidence_gaps,
        "review_queue": review_queue,
        "priority_status": "available",
    }


def _theme_package(normalized) -> dict[str, Any]:
    artifacts = [
        build_theme_artifact_from_package(normalized, row["theme_id"])
        for row in normalized.themes
    ]
    return {
        "artifact_dir": "database",
        "artifact_versions": sorted({row["artifact_version"] for row in artifacts}),
        "themes": [row["theme"] for row in artifacts],
        "nodes": [node for row in artifacts for node in row["nodes"]],
        "sources": [source for row in artifacts for source in row["sources"]],
        "claims": [claim for row in artifacts for claim in row["claims"]],
        "value_capture_assessments": [
            assessment
            for row in artifacts
            for assessment in row["value_capture_assessments"]
        ],
        "decomposition_templates": [
            template
            for row in artifacts
            for template in row["decomposition_templates"]
        ],
        "research_profiles": [
            {
                **copy.deepcopy(row["research_profile"]),
                "theme_id": row["theme"]["theme_id"],
            }
            for row in artifacts
            if row.get("research_profile") is not None
        ],
    }


def _mapping_package(normalized, theme_package: dict[str, Any]) -> dict[str, Any]:
    evidence_by_mapping: dict[str, list[str]] = {}
    for link in normalized.company_mapping_evidence:
        evidence_by_mapping.setdefault(link["mapping_id"], []).append(link["evidence_id"])
    mappings = []
    for mapping in normalized.company_mappings:
        row = copy.deepcopy(mapping)
        row["mapped_node_id"] = row.pop("node_id")
        row["evidence_ids"] = sorted(evidence_by_mapping.get(row["mapping_id"], []))
        row.pop("metadata", None)
        mappings.append(row)
    mapping_source_ids = {row["source_id"] for row in normalized.mapping_evidence_items}
    return {
        "artifact_dir": "database",
        "theme_artifact_dir": "database",
        "artifacts": [],
        "themes": theme_package["themes"],
        "theme_nodes": theme_package["nodes"],
        "sources": [
            _artifact_source(row)
            for row in normalized.sources
            if row["source_id"] in mapping_source_ids
        ],
        "evidence_items": [copy.deepcopy(row) for row in normalized.mapping_evidence_items],
        "company_mappings": mappings,
    }


def _artifact_source(source: dict[str, Any]) -> dict[str, Any]:
    row = copy.deepcopy(source)
    row.pop("content_sha256", None)
    row.pop("provenance", None)
    row["publish_date"] = row.get("publish_date") or ""
    return row
