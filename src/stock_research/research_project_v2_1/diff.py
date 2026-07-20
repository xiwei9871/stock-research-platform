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
    "references": "reference_id",
    "evidence_assessments": "assessment_id",
    "causal_nodes": "causal_node_id",
    "causal_edges": "causal_edge_id",
    "validation_metrics": "metric_id",
    "invalidation_conditions": "condition_id",
    "search_plans": "search_plan_id",
    "source_candidates": "candidate_id",
    "evidence_artifacts": "artifact_id",
    "normalized_documents": "document_id",
    "industry_evidence_assessments": "assessment_id",
    "conflict_summaries": "conflict_summary_id",
    "industry_model_nodes": "industry_model_node_id",
    "industry_model_edges": "industry_model_edge_id",
    "bottleneck_hypotheses": "bottleneck_hypothesis_id",
    "value_migration_analyses": "value_migration_analysis_id",
    "bottleneck_readiness_reviews": "bottleneck_readiness_review_id",
}

CATEGORIES = (
    "added",
    "removed_from_current_scope",
    "modified",
    "status_changed",
    "superseded",
    "unchanged",
)

STATUS_FIELDS = {
    "evidence_requirements": {"collection_status", "satisfaction_status"},
    "evidence_assessments": {"review_status", "conflict_status"},
    "validation_metrics": {"status"},
    "invalidation_conditions": {"status"},
    "references": {"resolution_status"},
    "search_plans": {"status"},
    "source_candidates": {"acquisition_status", "exclusion_status"},
    "industry_evidence_assessments": {"review_status", "conflict_status"},
    "conflict_summaries": {"conflict_status"},
    "bottleneck_hypotheses": {"status", "research_disposition"},
    "value_migration_analyses": {"status"},
    "bottleneck_readiness_reviews": {"status", "reviewer_decision"},
    "claims": {"claim_status"},
    "questions": {"answer_status"},
}


def _error(code: str, message: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(message, code=code, details=details)


def _validate_pair(before: dict[str, Any], after: dict[str, Any]) -> None:
    if before["project_id"] != after["project_id"]:
        raise _error(
            "RESEARCH_PROJECT_V2_1_DIFF_PROJECT_MISMATCH",
            "Layered versions belong to different projects",
        )
    if (
        before["version_id"] == after["version_id"]
        or after["parent_version_id"] != before["version_id"]
    ):
        raise _error(
            "RESEARCH_PROJECT_V2_1_DIFF_ANCESTRY_INVALID",
            "Layered versions are not a direct parent-child pair",
            expected=before["version_id"],
            actual=after["parent_version_id"],
        )


def _index(version: dict[str, Any], family: str, id_field: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in version["snapshot"].get(family, []):
        object_id = item[id_field]
        if object_id in indexed:
            raise _error(
                "RESEARCH_PROJECT_V2_1_DIFF_DUPLICATE_OBJECT_ID",
                "Duplicate layered diff object ID",
                family=family,
                id=object_id,
            )
        indexed[object_id] = item
    return indexed


def _without_status(item: dict[str, Any], family: str) -> dict[str, Any]:
    normalized = deepcopy(item)
    normalized.pop("lifecycle_status", None)
    for field in STATUS_FIELDS.get(family, set()):
        normalized.pop(field, None)
    provenance = normalized.get("provenance")
    if isinstance(provenance, dict):
        provenance.pop("review_status", None)
    return normalized


def _classify(family: str, before: dict[str, Any], after: dict[str, Any]) -> str:
    if before == after:
        return "unchanged"
    if after.get("lifecycle_status") == "removed_from_scope":
        return "removed_from_current_scope"
    if after.get("lifecycle_status") == "superseded":
        return "superseded"
    if _without_status(before, family) == _without_status(after, family):
        return "status_changed"
    return "modified"


def _superseded_ids(after: dict[str, dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    for item in after.values():
        for field in (
            "supersedes_object_id",
            "supersedes_claim_id",
            "supersedes_requirement_id",
        ):
            value = item.get(field)
            if isinstance(value, str):
                result.add(value)
    return result


def _diff_family(
    family: str,
    id_field: str,
    before_version: dict[str, Any],
    after_version: dict[str, Any],
) -> dict[str, list[str]]:
    before = _index(before_version, family, id_field)
    after = _index(after_version, family, id_field)
    changes = {category: [] for category in CATEGORIES}
    superseded = _superseded_ids(after)

    for object_id in set(after) - set(before):
        changes["added"].append(object_id)
    for object_id in set(before) - set(after):
        changes[
            "superseded" if object_id in superseded else "removed_from_current_scope"
        ].append(object_id)
    for object_id in set(before) & set(after):
        category = (
            "superseded"
            if object_id in superseded
            else _classify(family, before[object_id], after[object_id])
        )
        changes[category].append(object_id)
    for values in changes.values():
        values.sort()
    return changes


def diff_industry_versions(
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
