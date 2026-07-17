from collections import defaultdict, deque
from typing import Any

from stock_research.research_project_v2.errors import ResearchProjectV2Error


TARGET_COLLECTIONS = {
    "research_project": None,
    "research_question": "questions",
    "research_claim": "claims",
    "causal_edge": "causal_edges",
    "company_capture": "company_capture_assessments",
}

_ID_FIELDS = {
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
    "company_capture_assessments": "assessment_id",
}

_CONTEXT_REFERENCE_ROLES = {"definition", "background", "scope_context"}


def _error(code: str, message: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(message, code=code, details=details)


def _ids(snapshot: dict[str, Any], collection: str) -> set[str]:
    id_field = _ID_FIELDS[collection]
    return {item[id_field] for item in snapshot[collection]}


def _require_unique_ids(snapshot: dict[str, Any]) -> None:
    object_collections: dict[str, str] = {}
    for collection, id_field in _ID_FIELDS.items():
        for item in snapshot[collection]:
            object_id = item[id_field]
            if object_id in object_collections:
                raise _error(
                    "RESEARCH_PROJECT_DUPLICATE_OBJECT_ID",
                    f"Duplicate object ID: {object_id}",
                    first_collection=object_collections[object_id],
                    current_collection=collection,
                    id=object_id,
                )
            object_collections[object_id] = collection


def _require_reference(
    referenced_id: str,
    known_ids: set[str],
    *,
    code: str,
    collection: str,
    field: str,
    source_id: str,
) -> None:
    if referenced_id not in known_ids:
        raise _error(
            code,
            f"Referenced object not found: {referenced_id}",
            collection=collection,
            field=field,
            id=source_id,
            referenced_id=referenced_id,
        )


def _validate_parent_tree(nodes: list[dict[str, Any]]) -> None:
    nodes_by_id = {node["tree_node_id"]: node for node in nodes}
    for node in nodes:
        parent_id = node["parent_tree_node_id"]
        if parent_id is None:
            continue
        if parent_id not in nodes_by_id:
            raise _error(
                "RESEARCH_PROJECT_TREE_PARENT_NOT_FOUND",
                f"Question tree parent not found: {parent_id}",
                collection="question_tree_nodes",
                id=node["tree_node_id"],
                parent_tree_node_id=parent_id,
            )
        if nodes_by_id[parent_id]["tree_id"] != node["tree_id"]:
            raise _error(
                "RESEARCH_PROJECT_TREE_PARENT_INVALID",
                f"Question tree parent belongs to another tree: {parent_id}",
                collection="question_tree_nodes",
                id=node["tree_node_id"],
                parent_tree_node_id=parent_id,
            )

    state = {node_id: 0 for node_id in nodes_by_id}
    for node in nodes:
        start_id = node["tree_node_id"]
        if state[start_id] != 0:
            continue
        path: list[str] = []
        current_id: str | None = start_id
        while current_id is not None and state[current_id] == 0:
            state[current_id] = 1
            path.append(current_id)
            current_id = nodes_by_id[current_id]["parent_tree_node_id"]
        if current_id is not None and state[current_id] == 1:
            raise _error(
                "RESEARCH_PROJECT_TREE_PARENT_CYCLE",
                f"Question tree parent cycle contains: {current_id}",
                collection="question_tree_nodes",
                id=current_id,
            )
        for path_node_id in path:
            state[path_node_id] = 2


def _validate_question_dependency_dag(
    nodes: list[dict[str, Any]],
    question_ids: set[str],
) -> None:
    adjacency: dict[str, set[str]] = {question_id: set() for question_id in question_ids}
    indegree = {question_id: 0 for question_id in question_ids}
    for node in nodes:
        question_id = node["question_id"]
        for dependency_id in node["dependency_question_ids"]:
            _require_reference(
                dependency_id,
                question_ids,
                code="RESEARCH_PROJECT_QUESTION_DEPENDENCY_NOT_FOUND",
                collection="question_tree_nodes",
                field="dependency_question_ids",
                source_id=node["tree_node_id"],
            )
            if question_id not in adjacency[dependency_id]:
                adjacency[dependency_id].add(question_id)
                indegree[question_id] += 1

    queue = deque(question_id for question_id, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        question_id = queue.popleft()
        visited += 1
        for dependent_id in adjacency[question_id]:
            indegree[dependent_id] -= 1
            if indegree[dependent_id] == 0:
                queue.append(dependent_id)
    if visited != len(question_ids):
        raise _error(
            "RESEARCH_PROJECT_QUESTION_DEPENDENCY_CYCLE",
            "Question dependency graph contains a cycle",
            collection="question_tree_nodes",
        )


def _validate_question_trees(snapshot: dict[str, Any]) -> None:
    question_ids = _ids(snapshot, "questions")
    nodes = snapshot["question_tree_nodes"]
    for node in nodes:
        _require_reference(
            node["question_id"],
            question_ids,
            code="RESEARCH_PROJECT_TREE_QUESTION_NOT_FOUND",
            collection="question_tree_nodes",
            field="question_id",
            source_id=node["tree_node_id"],
        )
    _validate_parent_tree(nodes)
    _validate_question_dependency_dag(nodes, question_ids)


def _validate_questions(snapshot: dict[str, Any]) -> None:
    claim_ids = _ids(snapshot, "claims")
    requirement_ids = _ids(snapshot, "evidence_requirements")
    for question in snapshot["questions"]:
        for claim_id in question["linked_claim_ids"]:
            _require_reference(
                claim_id,
                claim_ids,
                code="RESEARCH_PROJECT_QUESTION_CLAIM_NOT_FOUND",
                collection="questions",
                field="linked_claim_ids",
                source_id=question["question_id"],
            )
        for requirement_id in question["linked_requirement_ids"]:
            _require_reference(
                requirement_id,
                requirement_ids,
                code="RESEARCH_PROJECT_QUESTION_REQUIREMENT_NOT_FOUND",
                collection="questions",
                field="linked_requirement_ids",
                source_id=question["question_id"],
            )


def _validate_claims(snapshot: dict[str, Any]) -> None:
    _validate_questions(snapshot)
    claim_ids = _ids(snapshot, "claims")
    question_ids = _ids(snapshot, "questions")
    metric_ids = _ids(snapshot, "validation_metrics")
    condition_ids = _ids(snapshot, "invalidation_conditions")
    for claim in snapshot["claims"]:
        claim_id = claim["claim_id"]
        for question_id in claim["linked_question_ids"]:
            _require_reference(
                question_id,
                question_ids,
                code="RESEARCH_PROJECT_CLAIM_QUESTION_NOT_FOUND",
                collection="claims",
                field="linked_question_ids",
                source_id=claim_id,
            )
        for metric_id in claim["validation_metric_ids"]:
            _require_reference(
                metric_id,
                metric_ids,
                code="RESEARCH_PROJECT_CLAIM_METRIC_NOT_FOUND",
                collection="claims",
                field="validation_metric_ids",
                source_id=claim_id,
            )
        for condition_id in claim["invalidation_condition_ids"]:
            _require_reference(
                condition_id,
                condition_ids,
                code="RESEARCH_PROJECT_CLAIM_INVALIDATION_CONDITION_NOT_FOUND",
                collection="claims",
                field="invalidation_condition_ids",
                source_id=claim_id,
            )
        supersedes_id = claim["supersedes_claim_id"]
        if supersedes_id is not None and (
            supersedes_id == claim_id or supersedes_id not in claim_ids
        ):
            raise _error(
                "RESEARCH_PROJECT_SUPERSEDES_CLAIM_INVALID",
                f"Invalid superseded claim: {supersedes_id}",
                collection="claims",
                id=claim_id,
                supersedes_claim_id=supersedes_id,
            )

    for relation in snapshot["claim_relations"]:
        for field in ("from_claim_id", "to_claim_id"):
            _require_reference(
                relation[field],
                claim_ids,
                code="RESEARCH_PROJECT_CLAIM_RELATION_TARGET_NOT_FOUND",
                collection="claim_relations",
                field=field,
                source_id=relation["relation_id"],
            )


def _target_ids(version: dict[str, Any], target_type: str) -> set[str]:
    collection = TARGET_COLLECTIONS[target_type]
    if collection is None:
        return {version["project_id"]}
    return _ids(version["snapshot"], collection)


def _validate_target(
    version: dict[str, Any],
    item: dict[str, Any],
    *,
    code: str,
    collection: str,
    id_field: str,
) -> None:
    target_type = item["target_type"]
    target_id = item["target_id"]
    if target_id not in _target_ids(version, target_type):
        raise _error(
            code,
            f"Target not found: {target_type} {target_id}",
            collection=collection,
            id=item[id_field],
            target_type=target_type,
            target_id=target_id,
        )


def _validate_evidence_targets(version: dict[str, Any]) -> None:
    snapshot = version["snapshot"]
    requirements = {
        requirement["requirement_id"]: requirement
        for requirement in snapshot["evidence_requirements"]
    }
    requirement_ids = set(requirements)
    reference_ids = _ids(snapshot, "references")
    for requirement in snapshot["evidence_requirements"]:
        _validate_target(
            version,
            requirement,
            code="RESEARCH_PROJECT_EVIDENCE_TARGET_NOT_FOUND",
            collection="evidence_requirements",
            id_field="requirement_id",
        )
    for assessment in snapshot["evidence_assessments"]:
        _validate_target(
            version,
            assessment,
            code="RESEARCH_PROJECT_EVIDENCE_TARGET_NOT_FOUND",
            collection="evidence_assessments",
            id_field="assessment_id",
        )
        _require_reference(
            assessment["requirement_id"],
            requirement_ids,
            code="RESEARCH_PROJECT_EVIDENCE_REQUIREMENT_NOT_FOUND",
            collection="evidence_assessments",
            field="requirement_id",
            source_id=assessment["assessment_id"],
        )
        requirement = requirements[assessment["requirement_id"]]
        assessment_target = (assessment["target_type"], assessment["target_id"])
        requirement_target = (requirement["target_type"], requirement["target_id"])
        if assessment_target != requirement_target:
            raise _error(
                "RESEARCH_PROJECT_EVIDENCE_REQUIREMENT_TARGET_MISMATCH",
                "Evidence assessment target does not match its requirement target",
                assessment_id=assessment["assessment_id"],
                requirement_id=requirement["requirement_id"],
                assessment_target_type=assessment["target_type"],
                assessment_target_id=assessment["target_id"],
                requirement_target_type=requirement["target_type"],
                requirement_target_id=requirement["target_id"],
            )
        _require_reference(
            assessment["reference_id"],
            reference_ids,
            code="RESEARCH_PROJECT_EVIDENCE_REFERENCE_NOT_FOUND",
            collection="evidence_assessments",
            field="reference_id",
            source_id=assessment["assessment_id"],
        )


def _validate_context_references(snapshot: dict[str, Any]) -> None:
    references = {reference["reference_id"]: reference for reference in snapshot["references"]}
    for claim in snapshot["claims"]:
        for reference_id in claim["context_reference_ids"]:
            if reference_id not in references:
                raise _error(
                    "RESEARCH_PROJECT_CONTEXT_REFERENCE_NOT_FOUND",
                    f"Context reference not found: {reference_id}",
                    collection="claims",
                    id=claim["claim_id"],
                    reference_id=reference_id,
                )
            role = references[reference_id]["reference_role"]
            if role not in _CONTEXT_REFERENCE_ROLES:
                raise _error(
                    "RESEARCH_PROJECT_CONTEXT_REFERENCE_ROLE_INVALID",
                    f"Reference role is not valid for claim context: {role}",
                    collection="claims",
                    id=claim["claim_id"],
                    reference_id=reference_id,
                    reference_role=role,
                )


def _strongly_connected_components(
    node_ids: set[str],
    adjacency: dict[str, list[str]],
) -> list[set[str]]:
    visited: set[str] = set()
    finish_order: list[str] = []

    for start_id in sorted(node_ids):
        if start_id in visited:
            continue
        stack = [(start_id, False)]
        while stack:
            node_id, expanded = stack.pop()
            if expanded:
                finish_order.append(node_id)
                continue
            if node_id in visited:
                continue
            visited.add(node_id)
            stack.append((node_id, True))
            for target_id in reversed(sorted(adjacency[node_id])):
                if target_id not in visited:
                    stack.append((target_id, False))

    reverse_adjacency: dict[str, list[str]] = defaultdict(list)
    for node_id in node_ids:
        reverse_adjacency[node_id]
    for source_id, target_ids in adjacency.items():
        for target_id in target_ids:
            reverse_adjacency[target_id].append(source_id)

    assigned: set[str] = set()
    components: list[set[str]] = []
    for start_id in reversed(finish_order):
        if start_id in assigned:
            continue
        component: set[str] = set()
        stack = [start_id]
        assigned.add(start_id)
        while stack:
            node_id = stack.pop()
            component.add(node_id)
            for source_id in reversed(sorted(reverse_adjacency[node_id])):
                if source_id not in assigned:
                    assigned.add(source_id)
                    stack.append(source_id)
        components.append(component)
    return sorted(components, key=lambda component: tuple(sorted(component)))


def _validate_causal_cycles(
    node_ids: set[str],
    edges: list[dict[str, Any]],
) -> None:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for node_id in node_ids:
        adjacency[node_id]
    for edge in edges:
        adjacency[edge["from_causal_node_id"]].append(edge["to_causal_node_id"])

    components = _strongly_connected_components(node_ids, adjacency)
    component_index = {
        node_id: index
        for index, component in enumerate(components)
        for node_id in component
    }
    internal_edges_by_component: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        source_component = component_index[edge["from_causal_node_id"]]
        if source_component == component_index[edge["to_causal_node_id"]]:
            internal_edges_by_component[source_component].append(edge)

    for index, component in enumerate(components):
        internal_edges = internal_edges_by_component[index]
        is_cycle = len(component) > 1 or any(
            edge["from_causal_node_id"] == edge["to_causal_node_id"]
            for edge in internal_edges
        )
        if not is_cycle:
            continue
        feedback_ids = {edge["feedback_loop_id"] for edge in internal_edges}
        if len(feedback_ids) != 1 or None in feedback_ids or "" in feedback_ids:
            raise _error(
                "RESEARCH_PROJECT_UNMARKED_CAUSAL_CYCLE",
                "Causal cycle edges must share one explicit feedback loop ID",
                collection="causal_edges",
                causal_node_ids=sorted(component),
            )


def _validate_causal_graph(snapshot: dict[str, Any]) -> None:
    node_ids = _ids(snapshot, "causal_nodes")
    claim_ids = _ids(snapshot, "claims")
    metric_ids = _ids(snapshot, "validation_metrics")
    edges = snapshot["causal_edges"]
    for edge in edges:
        edge_id = edge["causal_edge_id"]
        for field in ("from_causal_node_id", "to_causal_node_id"):
            _require_reference(
                edge[field],
                node_ids,
                code="RESEARCH_PROJECT_CAUSAL_NODE_NOT_FOUND",
                collection="causal_edges",
                field=field,
                source_id=edge_id,
            )
        for claim_id in edge["supporting_claim_ids"]:
            _require_reference(
                claim_id,
                claim_ids,
                code="RESEARCH_PROJECT_CAUSAL_CLAIM_NOT_FOUND",
                collection="causal_edges",
                field="supporting_claim_ids",
                source_id=edge_id,
            )
        for metric_id in edge["validation_metric_ids"]:
            _require_reference(
                metric_id,
                metric_ids,
                code="RESEARCH_PROJECT_CAUSAL_METRIC_NOT_FOUND",
                collection="causal_edges",
                field="validation_metric_ids",
                source_id=edge_id,
            )
    _validate_causal_cycles(node_ids, edges)


def _validate_company_capture_references(snapshot: dict[str, Any]) -> None:
    claim_ids = _ids(snapshot, "claims")
    requirement_ids = _ids(snapshot, "evidence_requirements")
    reference_ids = _ids(snapshot, "references")
    for assessment in snapshot["company_capture_assessments"]:
        assessment_id = assessment["assessment_id"]
        for field in ("company_reference_id", "node_reference_ids"):
            values = assessment[field] if isinstance(assessment[field], list) else [assessment[field]]
            for reference_id in values:
                _require_reference(
                    reference_id,
                    reference_ids,
                    code="RESEARCH_PROJECT_COMPANY_CAPTURE_REFERENCE_NOT_FOUND",
                    collection="company_capture_assessments",
                    field=field,
                    source_id=assessment_id,
                )
        for claim_id in assessment["linked_claim_ids"]:
            _require_reference(
                claim_id,
                claim_ids,
                code="RESEARCH_PROJECT_COMPANY_CAPTURE_CLAIM_NOT_FOUND",
                collection="company_capture_assessments",
                field="linked_claim_ids",
                source_id=assessment_id,
            )
        for requirement_id in assessment["linked_requirement_ids"]:
            _require_reference(
                requirement_id,
                requirement_ids,
                code="RESEARCH_PROJECT_COMPANY_CAPTURE_REQUIREMENT_NOT_FOUND",
                collection="company_capture_assessments",
                field="linked_requirement_ids",
                source_id=assessment_id,
            )


def _validate_metric_targets(version: dict[str, Any]) -> None:
    snapshot = version["snapshot"]
    for collection, id_field in (
        ("validation_metrics", "metric_id"),
        ("invalidation_conditions", "condition_id"),
    ):
        for item in snapshot[collection]:
            _validate_target(
                version,
                item,
                code="RESEARCH_PROJECT_VALIDATION_TARGET_NOT_FOUND",
                collection=collection,
                id_field=id_field,
            )
    _validate_company_capture_references(snapshot)


def _validate_first_design_snapshot(version: dict[str, Any]) -> None:
    if version["creation_stage"] != "research_design":
        return
    snapshot = version["snapshot"]
    invalid = (
        snapshot["project_lifecycle_state"] != "research_ready"
        or snapshot["evidence_stage"] != "requirements_defined"
        or snapshot["conclusion_status"] != "unavailable"
        or snapshot["investment_status"] != "not_assessed"
        or bool(snapshot["evidence_assessments"])
        or bool(snapshot["company_capture_assessments"])
        or any(
            claim["epistemic_type"] != "hypothesis"
            or claim["claim_status"] not in {"hypothesis", "under_test"}
            for claim in snapshot["claims"]
        )
    )
    if invalid:
        raise _error(
            "RESEARCH_PROJECT_DESIGN_SNAPSHOT_INVALID",
            "Research design snapshot contains post-design state",
            creation_stage=version["creation_stage"],
        )


def validate_version_semantics(version: dict[str, Any]) -> None:
    snapshot = version["snapshot"]
    _require_unique_ids(snapshot)
    _validate_question_trees(snapshot)
    _validate_claims(snapshot)
    _validate_evidence_targets(version)
    _validate_context_references(snapshot)
    _validate_causal_graph(snapshot)
    _validate_metric_targets(version)
    _validate_first_design_snapshot(version)
