from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Container

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2.semantic import (
    validate_version_semantics as validate_r1_version_semantics,
)


R2A_SNAPSHOT_FIELDS = {
    "research_layer",
    "upstream_research_refs",
    "search_plans",
    "source_candidates",
    "source_relationships",
    "evidence_artifacts",
    "normalized_documents",
    "industry_evidence_assessments",
    "conflict_summaries",
}

_NEW_ID_FIELDS = {
    "upstream_research_refs": "upstream_research_ref_id",
    "search_plans": "search_plan_id",
    "source_candidates": "candidate_id",
    "evidence_artifacts": "artifact_id",
    "normalized_documents": "document_id",
    "industry_evidence_assessments": "assessment_id",
    "conflict_summaries": "conflict_summary_id",
}

_COMMON_ID_FIELDS = {
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
}

_R2B_ID_FIELDS = {
    "industry_model_nodes": "industry_model_node_id",
    "industry_model_edges": "industry_model_edge_id",
    "bottleneck_hypotheses": "bottleneck_hypothesis_id",
    "value_migration_analyses": "value_migration_analysis_id",
    "bottleneck_readiness_reviews": "bottleneck_readiness_review_id",
}

_TARGET_COLLECTIONS = {
    "research_question": ("questions", "question_id"),
    "research_claim": ("claims", "claim_id"),
    "causal_edge": ("causal_edges", "causal_edge_id"),
    "industry_model_node": ("industry_model_nodes", "industry_model_node_id"),
    "bottleneck_hypothesis": ("bottleneck_hypotheses", "bottleneck_hypothesis_id"),
    "value_migration_analysis": ("value_migration_analyses", "value_migration_analysis_id"),
}

_MEDIA_EXTENSIONS = {
    "application/pdf": "pdf",
    "text/html": "html",
    "text/plain": "txt",
    "application/json": "json",
    "text/csv": "csv",
}


def _error(message: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        message,
        code="RESEARCH_PROJECT_V2_1_SEMANTIC_INVALID",
        details=details,
    )


def _structural_error(exc: KeyError | TypeError | IndexError) -> ResearchProjectV2Error:
    return _error(
        "Layered research version has an invalid semantic structure",
        reason=str(exc),
        exception_type=type(exc).__name__,
    )


def _require_reference(
    referenced_id: object,
    known_ids: Container[str],
    *,
    collection: str,
    field: str,
    source_id: object,
) -> None:
    if referenced_id not in known_ids:
        raise _error(
            f"Referenced layered research object not found: {referenced_id}",
            collection=collection,
            field=field,
            id=source_id,
            referenced_id=referenced_id,
        )


def common_r1_projection(version: dict[str, Any]) -> dict[str, Any]:
    try:
        projected = deepcopy(version)
        projected["artifact_version"] = "2.0.0"
        snapshot = projected["snapshot"]
        for field in R2A_SNAPSHOT_FIELDS:
            snapshot.pop(field, None)
        if version.get("schema_version") == "2.2.0":
            r1_target_types = {
                "research_project",
                "research_question",
                "research_claim",
                "causal_edge",
            }
            for collection in (
                "evidence_requirements",
                "evidence_assessments",
                "validation_metrics",
                "invalidation_conditions",
            ):
                snapshot[collection] = [
                    item
                    for item in snapshot[collection]
                    if item.get("target_type") in r1_target_types
                ]
            retained_metrics = {
                item["metric_id"] for item in snapshot["validation_metrics"]
            }
            retained_invalidations = {
                item["condition_id"]
                for item in snapshot["invalidation_conditions"]
            }
            for claim in snapshot["claims"]:
                claim["validation_metric_ids"] = [
                    item
                    for item in claim["validation_metric_ids"]
                    if item in retained_metrics
                ]
                claim["invalidation_condition_ids"] = [
                    item
                    for item in claim["invalidation_condition_ids"]
                    if item in retained_invalidations
                ]
            for edge in snapshot["causal_edges"]:
                edge["validation_metric_ids"] = [
                    item
                    for item in edge["validation_metric_ids"]
                    if item in retained_metrics
                ]
        snapshot["company_capture_assessments"] = []
        validate_r1_version_semantics(projected)
    except (KeyError, TypeError, IndexError) as exc:
        raise _structural_error(exc) from exc
    return projected


def _require_unique_ids(snapshot: dict[str, Any]) -> None:
    seen: dict[str, str] = {}
    for collection, id_field in {**_COMMON_ID_FIELDS, **_R2B_ID_FIELDS}.items():
        for item in snapshot.get(collection, []):
            seen[item[id_field]] = collection
    for collection, id_field in _NEW_ID_FIELDS.items():
        for item in snapshot[collection]:
            object_id = item[id_field]
            if object_id in seen:
                raise _error(
                    f"Duplicate layered research object ID: {object_id}",
                    collection=collection,
                    first_collection=seen[object_id],
                    id=object_id,
                    reason="duplicate object id",
                )
            seen[object_id] = collection

    query_seen: dict[str, str] = {}
    for plan in snapshot["search_plans"]:
        for query in plan["queries"]:
            query_id = query["query_id"]
            if query_id in query_seen:
                raise _error(
                    f"Duplicate search query ID: {query_id}",
                    collection="search_plans",
                    id=query_id,
                    first_search_plan_id=query_seen[query_id],
                    reason="duplicate query id",
                )
            query_seen[query_id] = plan["search_plan_id"]


def _require_industry_boundaries(value: object, path: tuple[object, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (*path, key)
            if key == "research_layer" and child != "industry_research":
                raise _error(
                    "Layered industry research contains a downstream research layer",
                    field="research_layer",
                    value=child,
                    path=list(child_path),
                    reason="research_layer must be industry_research",
                )
            if key == "evidence_channel" and child != "industry":
                raise _error(
                    "Layered industry research contains a downstream evidence channel",
                    field="evidence_channel",
                    value=child,
                    path=list(child_path),
                    reason="evidence_channel must be industry",
                )
            if key == "upstream_research_layer" and child is not None:
                raise _error(
                    "R1 upstream reference must have a null research layer",
                    field="upstream_research_layer",
                    value=child,
                    path=list(child_path),
                    reason="upstream_research_layer must be null",
                )
            _require_industry_boundaries(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _require_industry_boundaries(child, (*path, index))


def _validate_upstream_references(snapshot: dict[str, Any]) -> None:
    seen: set[tuple[object, ...]] = set()
    for reference in snapshot["upstream_research_refs"]:
        key = (
            reference.get("upstream_project_id"),
            reference.get("upstream_version_id"),
            reference.get("upstream_object_type"),
            reference.get("upstream_object_id"),
            reference.get("upstream_gate_result_id"),
        )
        if key in seen:
            raise _error(
                "Duplicate upstream research reference",
                id=reference.get("upstream_research_ref_id"),
                duplicate_key=list(key),
                reason="duplicate upstream reference",
            )
        seen.add(key)
    if snapshot["upstream_research_refs"]:
        from stock_research.research_project_v2_1.loader import resolve_upstream_r1_version

        for reference in snapshot["upstream_research_refs"]:
            resolve_upstream_r1_version(reference)


@dataclass(frozen=True)
class _ValidationContext:
    requirement_by_id: dict[str, dict[str, Any]]
    target_ids_by_type: dict[str, set[str]]
    plan_by_id: dict[str, dict[str, Any]]
    query_ids_by_plan: dict[str, set[str]]
    candidate_by_id: dict[str, dict[str, Any]]
    artifact_by_id: dict[str, dict[str, Any]]
    document_by_id: dict[str, dict[str, Any]]
    locators_by_document: dict[str, dict[str, dict[str, Any]]]
    assessment_by_id: dict[str, dict[str, Any]]


def _build_validation_context(
    version: dict[str, Any], snapshot: dict[str, Any]
) -> _ValidationContext:
    requirement_by_id = {
        item["requirement_id"]: item for item in snapshot["evidence_requirements"]
    }
    plan_by_id = {
        item["search_plan_id"]: item for item in snapshot["search_plans"]
    }
    query_ids_by_plan = {
        plan_id: {query["query_id"] for query in plan["queries"]}
        for plan_id, plan in plan_by_id.items()
    }
    candidate_by_id = {
        item["candidate_id"]: item for item in snapshot["source_candidates"]
    }
    artifact_by_id = {
        item["artifact_id"]: item for item in snapshot["evidence_artifacts"]
    }
    document_by_id = {
        item["document_id"]: item for item in snapshot["normalized_documents"]
    }
    assessment_by_id = {
        item["assessment_id"]: item
        for item in snapshot["industry_evidence_assessments"]
    }
    target_ids_by_type = {"research_project": {version["project_id"]}}
    for target_type, (collection, id_field) in _TARGET_COLLECTIONS.items():
        target_ids_by_type[target_type] = {
            item[id_field] for item in snapshot.get(collection, [])
        }

    locators_by_document: dict[str, dict[str, dict[str, Any]]] = {}
    for document_id, document in document_by_id.items():
        section_ids: set[str] = set()
        locators: dict[str, dict[str, Any]] = {}
        for section in document["sections"]:
            section_id = section["section_id"]
            if section_id in section_ids:
                raise _error(
                    "Normalized document contains a duplicate section_id",
                    collection="normalized_documents",
                    id=document_id,
                    field="section_id",
                    value=section_id,
                    reason="duplicate document section_id",
                )
            section_ids.add(section_id)
            locator = section["locator"]
            if locator in locators:
                raise _error(
                    "Normalized document contains a duplicate locator",
                    collection="normalized_documents",
                    id=document_id,
                    field="locator",
                    value=locator,
                    reason="duplicate document locator",
                )
            locators[locator] = section
        locators_by_document[document_id] = locators

    return _ValidationContext(
        requirement_by_id=requirement_by_id,
        target_ids_by_type=target_ids_by_type,
        plan_by_id=plan_by_id,
        query_ids_by_plan=query_ids_by_plan,
        candidate_by_id=candidate_by_id,
        artifact_by_id=artifact_by_id,
        document_by_id=document_by_id,
        locators_by_document=locators_by_document,
        assessment_by_id=assessment_by_id,
    )


def _validate_artifact_path(artifact: dict[str, Any]) -> None:
    digest = artifact["content_sha256"]
    raw_path = PurePosixPath(artifact["raw_path"])
    expected_extension = _MEDIA_EXTENSIONS.get(artifact["media_type"])
    valid = (
        len(raw_path.parts) == 4
        and raw_path.parts[:2] == ("evidence", "raw")
        and raw_path.parts[2] == digest[:2]
        and raw_path.stem == digest
        and raw_path.suffix == f".{expected_extension}"
    )
    if not valid:
        raise _error(
            "Evidence artifact raw_path is not content-addressed for its media type",
            collection="evidence_artifacts",
            id=artifact.get("artifact_id"),
            field="raw_path",
            reason="raw_path hash directory, filename, or extension mismatch",
        )


def _validate_plans_and_candidates(
    version: dict[str, Any],
    snapshot: dict[str, Any],
    context: _ValidationContext,
) -> None:
    for plan in snapshot["search_plans"]:
        if plan["project_id"] != version["project_id"]:
            raise _error(
                "Search plan project_id does not match its version",
                collection="search_plans",
                id=plan["search_plan_id"],
                field="project_id",
                referenced_id=plan["project_id"],
            )
        allowed_version_ids = {version["version_id"]}
        if (
            version.get("schema_version") == "2.2.0"
            and version.get("creation_stage") == "evidence_snapshot"
            and isinstance(version.get("parent_version_id"), str)
        ):
            allowed_version_ids.add(version["parent_version_id"])
        if plan["version_id"] not in allowed_version_ids:
            raise _error(
                "Search plan version_id does not match its version",
                collection="search_plans",
                id=plan["search_plan_id"],
                field="version_id",
                referenced_id=plan["version_id"],
            )
        for requirement_id in plan["requirement_ids"]:
            _require_reference(
                requirement_id,
                context.requirement_by_id,
                collection="search_plans",
                field="requirement_ids",
                source_id=plan["search_plan_id"],
            )

    for candidate in snapshot["source_candidates"]:
        plan_id = candidate["search_plan_id"]
        _require_reference(
            plan_id,
            context.plan_by_id,
            collection="source_candidates",
            field="search_plan_id",
            source_id=candidate["candidate_id"],
        )
        _require_reference(
            candidate["query_id"],
            context.query_ids_by_plan[plan_id],
            collection="source_candidates",
            field="query_id",
            source_id=candidate["candidate_id"],
        )



def _validate_artifacts_and_documents(context: _ValidationContext) -> None:
    for artifact in context.artifact_by_id.values():
        _require_reference(
            artifact["candidate_id"],
            context.candidate_by_id,
            collection="evidence_artifacts",
            field="candidate_id",
            source_id=artifact["artifact_id"],
        )
        _validate_artifact_path(artifact)

    for document in context.document_by_id.values():
        _require_reference(
            document["artifact_id"],
            context.artifact_by_id,
            collection="normalized_documents",
            field="artifact_id",
            source_id=document["document_id"],
        )
        artifact = context.artifact_by_id[document["artifact_id"]]
        if document["media_type"] != artifact["media_type"]:
            raise _error(
                "Normalized document media_type does not match its artifact",
                collection="normalized_documents",
                id=document["document_id"],
                field="media_type",
                expected=artifact["media_type"],
                actual=document["media_type"],
                reason="document media_type mismatch",
            )


def _validate_assessments_relationships_and_conflicts(
    snapshot: dict[str, Any],
    context: _ValidationContext,
) -> None:
    for assessment in snapshot["industry_evidence_assessments"]:
        source_id = assessment["assessment_id"]
        _require_reference(
            assessment["requirement_id"],
            context.requirement_by_id,
            collection="industry_evidence_assessments",
            field="requirement_id",
            source_id=source_id,
        )
        _require_reference(
            assessment["artifact_id"],
            context.artifact_by_id,
            collection="industry_evidence_assessments",
            field="artifact_id",
            source_id=source_id,
        )
        _require_reference(
            assessment["normalized_document_id"],
            context.document_by_id,
            collection="industry_evidence_assessments",
            field="normalized_document_id",
            source_id=source_id,
        )
        _require_reference(
            assessment["target_id"],
            context.target_ids_by_type[assessment["target_type"]],
            collection="industry_evidence_assessments",
            field="target_id",
            source_id=source_id,
        )
        requirement = context.requirement_by_id[assessment["requirement_id"]]
        if (
            assessment["target_type"],
            assessment["target_id"],
        ) != (
            requirement["target_type"],
            requirement["target_id"],
        ):
            raise _error(
                "Industry assessment target does not match its evidence requirement",
                collection="industry_evidence_assessments",
                id=source_id,
                requirement_id=assessment["requirement_id"],
                reason="assessment target does not match requirement target",
            )
        document = context.document_by_id[assessment["normalized_document_id"]]
        if document["artifact_id"] != assessment["artifact_id"]:
            raise _error(
                "Assessment document does not belong to its evidence artifact",
                collection="industry_evidence_assessments",
                field="artifact_id",
                id=source_id,
                referenced_id=assessment["artifact_id"],
            )
        locator = assessment["locator"]
        locator_id = (
            locator.get("locator_value") if isinstance(locator, dict) else locator
        )
        _require_reference(
            locator_id,
            context.locators_by_document[assessment["normalized_document_id"]],
            collection="industry_evidence_assessments",
            field="locator",
            source_id=source_id,
        )

    for relationship in snapshot["source_relationships"]:
        for field in ("left_artifact_id", "right_artifact_id"):
            _require_reference(
                relationship[field],
                context.artifact_by_id,
                collection="source_relationships",
                field=field,
                source_id=f"{relationship['left_artifact_id']}:{relationship['right_artifact_id']}",
            )

    for conflict in snapshot["conflict_summaries"]:
        for assessment_id in conflict["assessment_ids"]:
            _require_reference(
                assessment_id,
                context.assessment_by_id,
                collection="conflict_summaries",
                field="assessment_ids",
                source_id=conflict["conflict_summary_id"],
            )
        _require_reference(
            conflict["target_id"],
            context.target_ids_by_type[conflict["target_type"]],
            collection="conflict_summaries",
            field="target_id",
            source_id=conflict["conflict_summary_id"],
        )
        conflict_target = (conflict["target_type"], conflict["target_id"])
        for assessment_id in conflict["assessment_ids"]:
            assessment = context.assessment_by_id[assessment_id]
            if conflict_target != (
                assessment["target_type"],
                assessment["target_id"],
            ):
                raise _error(
                    "Conflict summary target does not match a referenced assessment",
                    collection="conflict_summaries",
                    id=conflict["conflict_summary_id"],
                    assessment_id=assessment_id,
                    reason="conflict target does not match assessment target",
                )


def _validate_r2b_semantics(
    version: dict[str, Any],
    snapshot: dict[str, Any],
    context: _ValidationContext,
) -> None:
    if version.get("schema_version") != "2.2.0":
        return

    nodes = {
        item["industry_model_node_id"]: item
        for item in snapshot["industry_model_nodes"]
    }
    edges = {
        item["industry_model_edge_id"]: item
        for item in snapshot["industry_model_edges"]
    }
    causal_nodes = {
        item["causal_node_id"]: item for item in snapshot["causal_nodes"]
    }
    causal_edges = {
        item["causal_edge_id"]: item for item in snapshot["causal_edges"]
    }
    claims = {item["claim_id"] for item in snapshot["claims"]}
    requirements = {
        item["requirement_id"] for item in snapshot["evidence_requirements"]
    }
    metrics = {item["metric_id"] for item in snapshot["validation_metrics"]}
    invalidations = {
        item["condition_id"] for item in snapshot["invalidation_conditions"]
    }
    bottlenecks = {
        item["bottleneck_hypothesis_id"]: item
        for item in snapshot["bottleneck_hypotheses"]
    }

    for node_id, node in nodes.items():
        for field in ("input_ids", "output_ids"):
            for referenced_id in node[field]:
                _require_reference(
                    referenced_id,
                    nodes,
                    collection="industry_model_nodes",
                    field=field,
                    source_id=node_id,
                )
    for edge_id, edge in edges.items():
        for field in (
            "from_industry_model_node_id",
            "to_industry_model_node_id",
        ):
            _require_reference(
                edge[field],
                nodes,
                collection="industry_model_edges",
                field=field,
                source_id=edge_id,
            )
        for field, known in (
            ("supporting_claim_ids", claims),
            ("counter_claim_ids", claims),
        ):
            for referenced_id in edge[field]:
                _require_reference(
                    referenced_id,
                    known,
                    collection="industry_model_edges",
                    field=field,
                    source_id=edge_id,
                )

    for bottleneck_id, bottleneck in bottlenecks.items():
        _require_reference(
            bottleneck["target_node_or_process_id"],
            nodes,
            collection="bottleneck_hypotheses",
            field="target_node_or_process_id",
            source_id=bottleneck_id,
        )
        for parameter_id in bottleneck["affected_system_parameter_ids"]:
            _require_reference(
                parameter_id,
                causal_nodes,
                collection="bottleneck_hypotheses",
                field="affected_system_parameter_ids",
                source_id=bottleneck_id,
            )
            if causal_nodes[parameter_id]["node_kind"] != "system_parameter":
                raise _error(
                    "Bottleneck affected parameter must reference a system_parameter causal node",
                    collection="bottleneck_hypotheses",
                    field="affected_system_parameter_ids",
                    id=bottleneck_id,
                    referenced_id=parameter_id,
                )
        for field, known in (
            ("impact_path_edge_ids", causal_edges),
            ("supporting_claim_ids", claims),
            ("counter_claim_ids", claims),
            ("evidence_requirement_ids", requirements),
            ("validation_metric_ids", metrics),
            ("invalidation_condition_ids", invalidations),
            ("related_bottleneck_ids", bottlenecks),
        ):
            for referenced_id in bottleneck[field]:
                _require_reference(
                    referenced_id,
                    known,
                    collection="bottleneck_hypotheses",
                    field=field,
                    source_id=bottleneck_id,
                )

    for analysis in snapshot["value_migration_analyses"]:
        source_id = analysis["value_migration_analysis_id"]
        _require_reference(
            analysis["bottleneck_hypothesis_id"],
            bottlenecks,
            collection="value_migration_analyses",
            field="bottleneck_hypothesis_id",
            source_id=source_id,
        )
        for field in (
            "affected_node_ids",
            "beneficiary_node_ids",
            "disadvantaged_node_ids",
        ):
            for referenced_id in analysis[field]:
                _require_reference(
                    referenced_id,
                    nodes,
                    collection="value_migration_analyses",
                    field=field,
                    source_id=source_id,
                )

    active_open = [
        item
        for item in snapshot["evidence_requirements"]
        if item["lifecycle_status"] == "active" and item["open_discovery"]
    ]
    if not active_open:
        raise _error(
            "R2B industry research requires an active open-discovery evidence requirement",
            collection="evidence_requirements",
            reason="open discovery requirement missing",
        )

    for requirement in snapshot["evidence_requirements"]:
        target_type = requirement["target_type"]
        _require_reference(
            requirement["target_id"],
            context.target_ids_by_type[target_type],
            collection="evidence_requirements",
            field="target_id",
            source_id=requirement["requirement_id"],
        )
        for field, known in (
            ("attempted_candidate_ids", context.candidate_by_id),
            ("impact_on_claim_ids", claims),
            ("impact_on_bottleneck_ids", bottlenecks),
        ):
            for referenced_id in requirement.get(field, []):
                _require_reference(
                    referenced_id,
                    known,
                    collection="evidence_requirements",
                    field=field,
                    source_id=requirement["requirement_id"],
                )

    for collection, id_field in (
        ("validation_metrics", "metric_id"),
        ("invalidation_conditions", "condition_id"),
    ):
        for item in snapshot[collection]:
            _require_reference(
                item["target_id"],
                context.target_ids_by_type[item["target_type"]],
                collection=collection,
                field="target_id",
                source_id=item[id_field],
            )

    if version["creation_stage"] in {"research_design", "evidence_snapshot"}:
        forbidden = [
            item["bottleneck_hypothesis_id"]
            for item in snapshot["bottleneck_hypotheses"]
            if item["status"] == "confirmed_for_current_scope"
        ]
        if forbidden:
            raise _error(
                "R2B design/evidence snapshots cannot confirm bottlenecks",
                collection="bottleneck_hypotheses",
                ids=forbidden,
            )


def validate_industry_version_semantics(version: dict[str, Any]) -> None:
    try:
        common_r1_projection(version)
        snapshot = version["snapshot"]
        _require_industry_boundaries(snapshot)
        _require_unique_ids(snapshot)
        _validate_upstream_references(snapshot)
        context = _build_validation_context(version, snapshot)
        _validate_plans_and_candidates(version, snapshot, context)
        _validate_artifacts_and_documents(context)
        _validate_assessments_relationships_and_conflicts(
            snapshot, context
        )
        _validate_r2b_semantics(version, snapshot, context)
    except ResearchProjectV2Error:
        raise
    except (KeyError, TypeError, IndexError) as exc:
        raise _structural_error(exc) from exc
