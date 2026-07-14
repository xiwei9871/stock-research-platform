from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from typing import Any
from urllib.parse import quote

from stock_research.industry_chain_theme_research import (
    build_theme_catalog_context,
    classify_beneficiary,
)
from stock_research.technology_industry_catalog import load_industry_catalog
from stock_research.theme_research_priority import (
    load_theme_research_priority_package,
)
from stock_research.theme_research_db_models import ThemeResearchDomainError


class ThemeResearchNotFoundError(LookupError):
    pass


READ_SOURCES = {"artifact", "compare", "db"}


def configured_theme_research_read_source() -> str:
    value = os.getenv("THEME_RESEARCH_READ_SOURCE", "artifact").strip().lower()
    if value not in READ_SOURCES:
        raise ThemeResearchDomainError(
            f"unsupported read source: {value}",
            code="THEME_RESEARCH_READ_SOURCE_INVALID",
        )
    return value


def list_theme_research_themes(
    *, read_source: str | None = None
) -> dict[str, Any]:
    return _serve(_list_theme_research_themes, read_source=read_source)


def _list_theme_research_themes(context: dict[str, Any]) -> dict[str, Any]:
    items = [
        _theme_index_row(theme, context)
        for theme in context["theme_package"]["themes"]
    ]
    return {
        "total": len(items),
        "items": sorted(items, key=lambda row: (row["theme_name"], row["theme_id"])),
    }


def get_theme_research_theme(
    theme_id: str, *, read_source: str | None = None
) -> dict[str, Any]:
    return _serve(
        lambda context: _get_theme_research_theme(context, theme_id),
        read_source=read_source,
    )


def _get_theme_research_theme(
    context: dict[str, Any], theme_id: str
) -> dict[str, Any]:
    theme = _require_theme(context, theme_id)
    nodes = _theme_node_rows(context, theme_id)
    sources = _theme_source_rows(context, theme_id)
    claims = _theme_claim_rows(context, theme_id)
    companies = _theme_company_rows(context, theme_id)
    evidence_gaps = [
        row
        for row in context["evidence_gap_priorities"]
        if row["theme_id"] == theme_id
    ]
    queue = [
        row for row in context["review_queue"] if row["theme_id"] == theme_id
    ]
    beneficiary_counts = _count_by(companies, "beneficiary_tier")
    catalog_context = build_theme_catalog_context(
        theme_id,
        catalog=load_industry_catalog(),
    )
    research_profile = next(
        (
            {key: value for key, value in row.items() if key != "theme_id"}
            for row in context["theme_package"].get("research_profiles", [])
            if row["theme_id"] == theme_id
        ),
        None,
    )
    return {
        "theme": _with_guardrails(theme),
        "node_summary": {
            "total": len(nodes),
            "by_priority_class": _count_by(nodes, "priority_class"),
            "by_review_status": _count_by(nodes, "node_review_status"),
        },
        "source_summary": {
            "total": len(sources),
            "by_review_status": _count_by(sources, "review_status"),
        },
        "claim_summary": {
            "total": len(claims),
            "by_platform_use_status": _count_by(claims, "platform_use_status"),
        },
        "company_summary": {
            "total": len(companies),
            "by_priority_band": _count_by(companies, "priority_band"),
            "by_integration_status": _count_by(companies, "integration_status"),
        },
        "evidence_gap_summary": {
            "total": len(evidence_gaps),
            "by_priority_band": _count_by(evidence_gaps, "priority_band"),
        },
        "source_reliability_distribution": _count_by(
            sources, "reliability_level"
        ),
        "claim_evidence_status_distribution": _count_by(
            claims, "evidence_status"
        ),
        "review_queue_action_distribution": _count_by(
            queue, "recommended_action"
        ),
        "top_node_priorities": nodes[:5],
        "evidence_gaps": evidence_gaps[:5],
        "top_company_priorities": companies[:5],
        "catalog_context": catalog_context,
        "research_profile": research_profile,
        "beneficiary_summary": {
            "total": len(companies),
            "by_tier": beneficiary_counts,
            "reviewed_beneficiary_count": sum(
                row["beneficiary_tier"] != "concept_association"
                for row in companies
            ),
        },
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
    }


def list_theme_research_nodes(
    theme_id: str, *, read_source: str | None = None
) -> dict[str, Any]:
    return _serve(
        lambda context: _list_theme_research_nodes(context, theme_id),
        read_source=read_source,
    )


def _list_theme_research_nodes(
    context: dict[str, Any], theme_id: str
) -> dict[str, Any]:
    _require_theme(context, theme_id)
    items = _theme_node_rows(context, theme_id)
    return {"total": len(items), "items": items}


def list_theme_research_sources(
    theme_id: str, *, read_source: str | None = None
) -> dict[str, Any]:
    return _serve(
        lambda context: _list_theme_research_sources(context, theme_id),
        read_source=read_source,
    )


def _list_theme_research_sources(
    context: dict[str, Any], theme_id: str
) -> dict[str, Any]:
    _require_theme(context, theme_id)
    items = _theme_source_rows(context, theme_id)
    return {"total": len(items), "items": items}


def list_theme_research_claims(
    theme_id: str, *, read_source: str | None = None
) -> dict[str, Any]:
    return _serve(
        lambda context: _list_theme_research_claims(context, theme_id),
        read_source=read_source,
    )


def _list_theme_research_claims(
    context: dict[str, Any], theme_id: str
) -> dict[str, Any]:
    _require_theme(context, theme_id)
    items = _theme_claim_rows(context, theme_id)
    return {"total": len(items), "items": items}


def list_theme_research_companies(
    theme_id: str, *, read_source: str | None = None
) -> dict[str, Any]:
    return _serve(
        lambda context: _list_theme_research_companies(context, theme_id),
        read_source=read_source,
    )


def _list_theme_research_companies(
    context: dict[str, Any], theme_id: str
) -> dict[str, Any]:
    _require_theme(context, theme_id)
    items = _theme_company_rows(context, theme_id)
    return {"total": len(items), "items": items}


def _load_artifact_context() -> dict[str, Any]:
    return load_theme_research_priority_package()


def _serve(builder, *, read_source: str | None) -> dict[str, Any]:
    source = (read_source or configured_theme_research_read_source()).strip().lower()
    if source not in READ_SOURCES:
        raise ThemeResearchDomainError(
            f"unsupported read source: {source}",
            code="THEME_RESEARCH_READ_SOURCE_INVALID",
        )
    if source == "artifact":
        return builder(_load_artifact_context())
    from stock_research.dashboard.theme_research_db import load_db_context

    if source == "db":
        return builder(load_db_context())
    artifact_payload = builder(_load_artifact_context())
    database_payload = builder(load_db_context())
    artifact_payload["comparison"] = _compare_payloads(
        artifact_payload,
        database_payload,
    )
    return artifact_payload


def _compare_payloads(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_json = json.dumps(left, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    right_json = json.dumps(right, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    differences = _difference_paths(left, right)
    return {
        "status": "match" if not differences else "mismatch",
        "artifact_sha256": hashlib.sha256(left_json.encode("utf-8")).hexdigest(),
        "database_sha256": hashlib.sha256(right_json.encode("utf-8")).hexdigest(),
        "differences": differences,
    }


def _difference_paths(left: Any, right: Any, path: str = "$") -> list[str]:
    if type(left) is not type(right):
        return [path]
    if isinstance(left, dict):
        differences: list[str] = []
        for key in sorted(left.keys() | right.keys()):
            if key not in left or key not in right:
                differences.append(f"{path}.{key}")
            else:
                differences.extend(_difference_paths(left[key], right[key], f"{path}.{key}"))
        return differences[:100]
    if isinstance(left, list):
        if len(left) != len(right):
            return [f"{path}.length"]
        differences = []
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
            differences.extend(
                _difference_paths(left_item, right_item, f"{path}[{index}]")
            )
        return differences[:100]
    return [] if left == right else [path]


def _require_theme(context: dict[str, Any], theme_id: str) -> dict[str, Any]:
    candidate = str(theme_id or "")
    normalized = candidate.strip()
    if candidate != normalized:
        raise ThemeResearchNotFoundError(f"theme not found: {candidate}")
    for theme in context["theme_package"]["themes"]:
        if theme["theme_id"] == normalized:
            return theme
    raise ThemeResearchNotFoundError(f"theme not found: {normalized}")


def _theme_index_row(
    theme: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    theme_id = theme["theme_id"]
    nodes = _theme_node_rows(context, theme_id)
    sources = _theme_source_rows(context, theme_id)
    claims = _theme_claim_rows(context, theme_id)
    companies = _theme_company_rows(context, theme_id)
    queue = [
        row for row in context["review_queue"] if row["theme_id"] == theme_id
    ]
    catalog_context = build_theme_catalog_context(
        theme_id,
        catalog=load_industry_catalog(),
    )
    return {
        **theme,
        "research_kind": (
            "industry_chain_deep_research" if catalog_context is not None else "theme_research"
        ),
        "catalog_context": catalog_context,
        "node_count": len(nodes),
        "source_count": len(sources),
        "claim_count": len(claims),
        "company_count": len(companies),
        "evidence_gap_count": sum(
            row["priority_class"] == "evidence_collection_priority"
            for row in nodes
        ),
        "deep_research_node_count": sum(
            row["priority_class"] == "deep_research_priority" for row in nodes
        ),
        "review_queue_count": len(queue),
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
    }


def _theme_node_rows(
    context: dict[str, Any], theme_id: str
) -> list[dict[str, Any]]:
    node_by_id = {
        row["node_id"]: row
        for row in context["theme_package"]["nodes"]
        if row["theme_id"] == theme_id
    }
    items = [
        {**node_by_id[row["node_id"]], **row}
        for row in context["node_priorities"]
        if row["theme_id"] == theme_id
    ]
    return sorted(items, key=lambda row: (-row["priority_score"], row["node_id"]))


def _theme_source_rows(
    context: dict[str, Any], theme_id: str
) -> list[dict[str, Any]]:
    source_ids = _theme_source_ids(context["theme_package"], theme_id)
    claims = [
        row for row in context["theme_package"]["claims"] if row["theme_id"] == theme_id
    ]
    related_claims: dict[str, list[str]] = {source_id: [] for source_id in source_ids}
    for claim in claims:
        for source_id in {claim["source_id"], *claim["supporting_source_ids"]}:
            if source_id in related_claims:
                related_claims[source_id].append(claim["claim_id"])
    items = []
    for source in context["theme_package"]["sources"]:
        if source["source_id"] not in source_ids:
            continue
        claim_ids = sorted(set(related_claims.get(source["source_id"], [])))
        items.append(
            {
                **source,
                "theme_id": theme_id,
                "claim_count": len(claim_ids),
                "claim_ids": claim_ids,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return sorted(
        items,
        key=lambda row: (
            row["reliability_level"],
            _descending_date_key(row["publish_date"]),
            row["source_id"],
        ),
    )


def _theme_claim_rows(
    context: dict[str, Any], theme_id: str
) -> list[dict[str, Any]]:
    source_by_id = {
        row["source_id"]: row for row in context["theme_package"]["sources"]
    }
    items = []
    for claim in context["theme_package"]["claims"]:
        if claim["theme_id"] != theme_id:
            continue
        source = source_by_id[claim["source_id"]]
        supporting_sources = [
            {
                "source_id": source_id,
                "title": source_by_id[source_id]["title"],
                "reliability_level": source_by_id[source_id]["reliability_level"],
                "review_status": source_by_id[source_id]["review_status"],
            }
            for source_id in sorted(claim["supporting_source_ids"])
        ]
        items.append(
            {
                **claim,
                "supporting_source_ids": sorted(claim["supporting_source_ids"]),
                "affected_theme_nodes": sorted(claim["affected_theme_nodes"]),
                "source_title": source["title"],
                "source_reliability_level": source["reliability_level"],
                "source_review_status": source["review_status"],
                "supporting_sources": supporting_sources,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return sorted(
        items, key=lambda row: (row["evidence_status"], row["claim_id"])
    )


def _theme_company_rows(
    context: dict[str, Any], theme_id: str
) -> list[dict[str, Any]]:
    mapping_by_id = {
        row["mapping_id"]: row
        for row in context["mapping_package"]["company_mappings"]
        if row["theme_id"] == theme_id
    }
    node_by_id = {
        row["node_id"]: row
        for row in context["theme_package"]["nodes"]
        if row["theme_id"] == theme_id
    }
    source_by_id = {
        row["source_id"]: row for row in context["mapping_package"]["sources"]
    }
    evidence_by_id = {
        row["evidence_id"]: {
            **row,
            "source": source_by_id[row["source_id"]],
        }
        for row in context["mapping_package"]["evidence_items"]
    }
    items = []
    for priority in context["company_priorities"]:
        if priority["theme_id"] != theme_id:
            continue
        mapping = mapping_by_id[priority["mapping_id"]]
        mapping_evidence = [
            evidence_by_id[evidence_id]
            for evidence_id in mapping["evidence_ids"]
        ]
        stock_code = quote(priority["company_code"], safe="")
        items.append(
            {
                **mapping,
                **priority,
                "beneficiary_tier": classify_beneficiary(
                    mapping,
                    mapping_evidence,
                ),
                "mapping_evidence": mapping_evidence,
                "mapped_node": node_by_id[priority["theme_node_id"]],
                "tech_bottleneck_stock_path": (
                    f"/tech-bottleneck/stock/{stock_code}?source=theme_research"
                ),
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return sorted(
        items,
        key=lambda row: (
            -row["company_research_priority_score"],
            row["company_code"],
            row["mapping_id"],
        ),
    )


def _theme_source_ids(package: dict[str, Any], theme_id: str) -> set[str]:
    node_ids = {
        row["node_id"] for row in package["nodes"] if row["theme_id"] == theme_id
    }
    source_ids: set[str] = set()
    claim_ids: set[str] = set()
    for claim in package["claims"]:
        if claim["theme_id"] != theme_id:
            continue
        claim_ids.add(claim["claim_id"])
        source_ids.add(claim["source_id"])
        source_ids.update(claim["supporting_source_ids"])
    for assessment in package["value_capture_assessments"]:
        if assessment["node_id"] not in node_ids:
            continue
        for evidence_id in assessment["evidence_ids"]:
            if evidence_id not in claim_ids:
                source_ids.add(evidence_id)
    return source_ids


def _count_by(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(str(row[field]) for row in rows)
    return {key: counts[key] for key in sorted(counts)}


def _with_guardrails(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
    }


def _descending_date_key(value: str) -> tuple[int, ...]:
    text = str(value or "").strip()
    if not text:
        return (0, 0, 0)
    parts = text.split("-")
    try:
        return tuple(-int(part) for part in parts)
    except ValueError:
        return (0, 0, 0)
