from __future__ import annotations

import copy
from typing import Any

from stock_research.config import SETTINGS
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
