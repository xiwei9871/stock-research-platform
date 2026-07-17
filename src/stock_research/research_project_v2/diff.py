from __future__ import annotations

from copy import deepcopy
from typing import Any

from stock_research.research_project_v2.errors import ResearchProjectV2Error


OBJECT_FAMILIES = {
    "questions": "question_id",
    "question_tree_nodes": "tree_node_id",
    "claims": "claim_id",
    "claim_relations": "relation_id",
    "evidence_requirements": "requirement_id",
    "evidence_assessments": "assessment_id",
    "causal_nodes": "causal_node_id",
    "causal_edges": "causal_edge_id",
    "validation_metrics": "metric_id",
    "invalidation_conditions": "condition_id",
    "references": "reference_id",
    "company_capture_assessments": "assessment_id",
}

_CATEGORIES = (
    "added",
    "removed_from_current_scope",
    "modified",
    "status_changed",
    "superseded",
    "unchanged",
)

_FAMILY_STATUS_PATHS = {
    "questions": (("answer_status",),),
    "question_tree_nodes": (),
    "claims": (("claim_status",),),
    "claim_relations": (),
    "evidence_requirements": (
        ("collection_status",),
        ("satisfaction_status",),
    ),
    "evidence_assessments": (("review_status",), ("conflict_status",)),
    "causal_nodes": (),
    "causal_edges": (),
    "validation_metrics": (("status",),),
    "invalidation_conditions": (("status",),),
    "references": (("resolution_status",),),
    "company_capture_assessments": (
        ("assessment_status",),
        ("product_evidence_status",),
        ("qualification_status",),
        ("capacity_status",),
        ("order_status",),
        ("revenue_conversion_status",),
        ("profit_conversion_status",),
        ("market_pricing_status",),
    ),
}

_COMMON_STATUS_PATHS = (("lifecycle_status",), ("provenance", "review_status"))


def _error(code: str, message: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(message, code=code, details=details)


def _validate_pair(before: dict[str, Any], after: dict[str, Any]) -> None:
    if before["project_id"] != after["project_id"]:
        raise _error(
            "RESEARCH_PROJECT_DIFF_PROJECT_MISMATCH",
            "Research project versions belong to different projects",
            before=before["project_id"],
            after=after["project_id"],
        )

    expected_parent = before["version_id"]
    actual_parent = after["parent_version_id"]
    if after["version_id"] == before["version_id"] or actual_parent != expected_parent:
        raise _error(
            "RESEARCH_PROJECT_DIFF_ANCESTRY_INVALID",
            "Research project versions are not a direct parent-child pair",
            expected=expected_parent,
            actual=actual_parent,
        )


def _index_family(
    version: dict[str, Any],
    family: str,
    id_field: str,
    side: str,
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in version["snapshot"][family]:
        object_id = item[id_field]
        if object_id in indexed:
            raise _error(
                "RESEARCH_PROJECT_DIFF_DUPLICATE_OBJECT_ID",
                f"Duplicate object ID in {side} {family}: {object_id}",
                side=side,
                family=family,
                id=object_id,
            )
        indexed[object_id] = item
    return indexed


def _without_status_fields(item: dict[str, Any], family: str) -> dict[str, Any]:
    normalized = deepcopy(item)
    for path in _COMMON_STATUS_PATHS + _FAMILY_STATUS_PATHS[family]:
        parent: Any = normalized
        for component in path[:-1]:
            if not isinstance(parent, dict) or component not in parent:
                parent = None
                break
            parent = parent[component]
        if isinstance(parent, dict):
            parent.pop(path[-1], None)
    return normalized


def _explicitly_superseded_ids(
    family: str,
    after_items: dict[str, dict[str, Any]],
) -> set[str]:
    supersedes_fields = ("supersedes_object_id",)
    if family == "claims":
        supersedes_fields = ("supersedes_claim_id",) + supersedes_fields

    superseded_ids: set[str] = set()
    for item in after_items.values():
        for field in supersedes_fields:
            superseded_id = item.get(field)
            if isinstance(superseded_id, str):
                superseded_ids.add(superseded_id)
    return superseded_ids


def _classify_same_id(
    family: str,
    before_item: dict[str, Any],
    after_item: dict[str, Any],
) -> str:
    if before_item == after_item:
        return "unchanged"

    before_lifecycle = before_item.get("lifecycle_status")
    after_lifecycle = after_item.get("lifecycle_status")
    if after_lifecycle == "removed_from_scope" and before_lifecycle != after_lifecycle:
        return "removed_from_current_scope"
    if after_lifecycle == "superseded" and before_lifecycle != after_lifecycle:
        return "superseded"

    if _without_status_fields(before_item, family) == _without_status_fields(
        after_item, family
    ):
        return "status_changed"
    return "modified"


def _diff_family(
    family: str,
    id_field: str,
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, list[str]]:
    before_items = _index_family(before, family, id_field, "before")
    after_items = _index_family(after, family, id_field, "after")
    changes = {category: [] for category in _CATEGORIES}

    before_ids = set(before_items)
    after_ids = set(after_items)
    superseded_ids = _explicitly_superseded_ids(family, after_items) & before_ids
    changes["added"].extend(after_ids - before_ids)

    for object_id in before_ids - after_ids:
        category = (
            "superseded"
            if object_id in superseded_ids
            else "removed_from_current_scope"
        )
        changes[category].append(object_id)

    for object_id in before_ids & after_ids:
        category = (
            "superseded"
            if object_id in superseded_ids
            else _classify_same_id(
                family,
                before_items[object_id],
                after_items[object_id],
            )
        )
        changes[category].append(object_id)

    for ids in changes.values():
        ids.sort()
    return changes


def diff_versions(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    _validate_pair(before, after)
    changes = {
        family: _diff_family(family, id_field, before, after)
        for family, id_field in OBJECT_FAMILIES.items()
    }
    return {
        "project_id": before["project_id"],
        "from_version": before["semantic_version"],
        "to_version": after["semantic_version"],
        "from_content_hash": before["content_hash"],
        "to_content_hash": after["content_hash"],
        "changes": changes,
    }
