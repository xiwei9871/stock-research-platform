from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2.references import audit_references


@dataclass(frozen=True)
class GateCheck:
    code: str
    status: str
    message: str
    object_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class GateResult:
    gate: str
    status: str
    checks: tuple[GateCheck, ...]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["checks"] = [asdict(check) for check in self.checks]
        return payload


_OBJECT_COLLECTION_IDS = {
    "questions": "question_id",
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
_ACTOR_TYPES = {"human", "codex", "automated_pipeline", "imported"}
_REVIEW_STATUSES = {"unreviewed", "pending_review", "reviewed", "rejected"}
_COUNTER_RELATIONS = {
    "challenges",
    "contradicts",
    "qualifies",
    "alternative_to",
}
_INVALID_COLLECTION_STATUSES = {
    "invalid",
    "cancelled",
    "canceled",
    "not_applicable",
    "rejected",
}
_SATISFIED_STATUSES = {
    "satisfied",
    "complete",
    "completed",
    "fully_satisfied",
    "partially_satisfied",
}


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _non_empty_strings(value: object) -> bool:
    return isinstance(value, list) and any(_non_empty(item) for item in value)


def _check(code: str, passed: bool, message: str, ids: tuple[str, ...] = ()) -> GateCheck:
    return GateCheck(code, "pass" if passed else "fail", message, ids if not passed else ())


def _primary_question(snapshot: dict[str, Any]) -> GateCheck:
    scope = snapshot.get("scope", {})
    questions = snapshot.get("questions", [])
    passed = _non_empty(scope.get("primary_question")) and any(
        isinstance(question, dict) and question.get("required_for_gate") is True
        for question in questions
    )
    return _check(
        "DESIGN_PRIMARY_QUESTION_PRESENT",
        passed,
        "Primary question and a required gate question are present.",
    )


def _scope_check(snapshot: dict[str, Any], field: str, code: str) -> GateCheck:
    passed = _non_empty_strings(snapshot.get("scope", {}).get(field))
    return _check(code, passed, f"Scope field {field} contains a non-empty entry.")


def _router(snapshot: dict[str, Any]) -> GateCheck:
    router = snapshot.get("router_decision", {})
    confidence = router.get("confidence")
    confidence_valid = (
        isinstance(confidence, (int, float))
        and not isinstance(confidence, bool)
        and 0 <= confidence <= 1
    )
    passed = (
        _non_empty(router.get("primary_method"))
        and _non_empty_strings(router.get("routing_reasons"))
        and _non_empty_strings(router.get("required_research_modules"))
        and confidence_valid
        and (
            router.get("manual_override") is not True
            or _non_empty(router.get("override_reason"))
        )
    )
    return _check("DESIGN_ROUTER_COMPLETE", passed, "Router decision is complete.")


def _cyclic_ids(edges: dict[str, list[str]]) -> set[str]:
    indegree = {node_id: 0 for node_id in edges}
    reverse: dict[str, list[str]] = {node_id: [] for node_id in edges}
    for node_id, dependencies in edges.items():
        for dependency in dependencies:
            if dependency in indegree:
                indegree[node_id] += 1
                reverse[dependency].append(node_id)
    ready = [node_id for node_id, degree in indegree.items() if degree == 0]
    visited: set[str] = set()
    while ready:
        node_id = ready.pop()
        visited.add(node_id)
        for dependent in reverse[node_id]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)
    return set(edges) - visited


def _question_tree(snapshot: dict[str, Any]) -> GateCheck:
    questions = {
        question.get("question_id")
        for question in snapshot.get("questions", [])
        if isinstance(question, dict) and _non_empty(question.get("question_id"))
    }
    nodes = snapshot.get("question_tree_nodes", [])
    node_by_id: dict[str, dict[str, Any]] = {}
    invalid: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            invalid.add("<unknown-tree-node>")
            continue
        node_id = node.get("tree_node_id")
        if not _non_empty(node_id):
            invalid.add("<unknown-tree-node>")
            continue
        if node_id in node_by_id:
            invalid.add(node_id)
        node_by_id[node_id] = node
        if not _non_empty(node.get("tree_id")) or node.get("question_id") not in questions:
            invalid.add(node_id)
        dependencies = node.get("dependency_question_ids")
        if not isinstance(dependencies, list) or any(item not in questions for item in dependencies):
            invalid.add(node_id)

    parent_edges: dict[str, list[str]] = {node_id: [] for node_id in node_by_id}
    question_edges: dict[str, list[str]] = {question_id: [] for question_id in questions}
    for node_id, node in node_by_id.items():
        parent_id = node.get("parent_tree_node_id")
        if parent_id is not None:
            parent = node_by_id.get(parent_id)
            if parent is None or parent.get("tree_id") != node.get("tree_id"):
                invalid.add(node_id)
            else:
                parent_edges[node_id].append(parent_id)
        question_id = node.get("question_id")
        if question_id in question_edges and isinstance(node.get("dependency_question_ids"), list):
            question_edges[question_id].extend(
                dependency
                for dependency in node["dependency_question_ids"]
                if dependency in questions
            )
    invalid.update(_cyclic_ids(parent_edges))
    cyclic_questions = _cyclic_ids(question_edges)
    invalid.update(
        node_id
        for node_id, node in node_by_id.items()
        if node.get("question_id") in cyclic_questions
    )
    return _check(
        "DESIGN_QUESTION_TREE_VALID",
        not invalid and bool(nodes),
        "Question tree references and dependencies form valid acyclic trees.",
        tuple(sorted(invalid)),
    )


def _required_questions(snapshot: dict[str, Any]) -> GateCheck:
    required_ids = {
        question.get("question_id")
        for question in snapshot.get("questions", [])
        if isinstance(question, dict)
        and question.get("required_for_gate") is True
        and _non_empty(question.get("question_id"))
    }
    covered = {
        requirement.get("target_id")
        for requirement in snapshot.get("evidence_requirements", [])
        if isinstance(requirement, dict)
        and requirement.get("target_type") == "research_question"
        and str(requirement.get("collection_status", "")).lower()
        not in _INVALID_COLLECTION_STATUSES
    }
    missing = tuple(sorted(required_ids - covered))
    return _check(
        "DESIGN_REQUIRED_QUESTIONS_COVERED",
        not missing,
        "Every required question has a directly targeted evidence requirement.",
        missing,
    )


def _critical_claims(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        claim
        for claim in snapshot.get("claims", [])
        if isinstance(claim, dict)
        and claim.get("claim_kind") == "primary"
        and isinstance(claim.get("importance"), (int, float))
        and not isinstance(claim.get("importance"), bool)
        and claim["importance"] >= 0.8
    ]


def _counter_claims(snapshot: dict[str, Any]) -> GateCheck:
    claims = {
        claim.get("claim_id"): claim
        for claim in snapshot.get("claims", [])
        if isinstance(claim, dict) and _non_empty(claim.get("claim_id"))
    }
    counter_ids = {
        claim_id
        for claim_id, claim in claims.items()
        if claim.get("claim_kind") in {"counter", "alternative"}
    }
    connected: set[str] = set()
    for relation in snapshot.get("claim_relations", []):
        if not isinstance(relation, dict) or relation.get("relation_type") not in _COUNTER_RELATIONS:
            continue
        from_id, to_id = relation.get("from_claim_id"), relation.get("to_claim_id")
        if from_id in counter_ids:
            connected.add(to_id)
        if to_id in counter_ids:
            connected.add(from_id)
    missing = tuple(
        sorted(
            claim["claim_id"]
            for claim in _critical_claims(snapshot)
            if claim.get("claim_id") not in connected
        )
    )
    return _check(
        "DESIGN_CRITICAL_CLAIMS_HAVE_COUNTER",
        not missing,
        "Every critical primary claim is linked to a counter or alternative claim.",
        missing,
    )


def _plan(snapshot: dict[str, Any], collection: str, field: str, code: str, id_field: str) -> GateCheck:
    object_ids = {
        item.get(id_field)
        for item in snapshot.get(collection, [])
        if isinstance(item, dict) and _non_empty(item.get(id_field))
    }
    missing: set[str] = set()
    for claim in _critical_claims(snapshot):
        linked = claim.get(field)
        if not isinstance(linked, list) or not linked or any(item not in object_ids for item in linked):
            missing.add(claim.get("claim_id", "<unknown-claim>"))
    passed = bool(object_ids) and not missing
    return _check(code, passed, f"Critical claims have a valid {collection} plan.", tuple(sorted(missing)))


def _references(snapshot: dict[str, Any], version: dict[str, Any]) -> GateCheck:
    result = audit_references(version)
    ids: list[str] = []
    seen: set[str] = set()
    for issue in result.get("issues", []):
        reference_id = issue.get("reference_id")
        if isinstance(reference_id, str) and reference_id not in seen:
            seen.add(reference_id)
            ids.append(reference_id)
    return _check(
        "DESIGN_REFERENCES_AUDITABLE",
        result.get("status") == "pass",
        "References are auditable.",
        tuple(ids),
    )


def _provenance(snapshot: dict[str, Any]) -> GateCheck:
    invalid: set[str] = set()
    required_fields = {
        "created_by",
        "actor_type",
        "agent_run_id",
        "created_at",
        "created_in_version",
        "review_status",
    }
    for collection, id_field in _OBJECT_COLLECTION_IDS.items():
        for item in snapshot.get(collection, []):
            if not isinstance(item, dict):
                invalid.add(f"<{collection}-object>")
                continue
            object_id = item.get(id_field)
            stable_id = object_id if isinstance(object_id, str) else f"<{collection}-object>"
            provenance = item.get("provenance")
            if (
                not isinstance(provenance, dict)
                or not required_fields.issubset(provenance)
                or not _non_empty(provenance.get("created_by"))
                or not _non_empty(provenance.get("created_in_version"))
                or provenance.get("actor_type") not in _ACTOR_TYPES
                or provenance.get("review_status") not in _REVIEW_STATUSES
            ):
                invalid.add(stable_id)
    return _check(
        "DESIGN_PROVENANCE_COMPLETE",
        not invalid,
        "All gate-relevant objects have complete provenance.",
        tuple(sorted(invalid)),
    )


def _no_premature(version: dict[str, Any], snapshot: dict[str, Any]) -> GateCheck:
    passed = (
        version.get("creation_stage") == "research_design"
        and snapshot.get("project_lifecycle_state") == "research_ready"
        and snapshot.get("evidence_stage") == "requirements_defined"
        and snapshot.get("conclusion_status") == "unavailable"
        and snapshot.get("investment_status") == "not_assessed"
        and not snapshot.get("evidence_assessments")
        and not snapshot.get("company_capture_assessments")
        and all(
            isinstance(claim, dict)
            and claim.get("epistemic_type") == "hypothesis"
            and claim.get("claim_status") in {"hypothesis", "under_test"}
            for claim in snapshot.get("claims", [])
        )
        and all(
            str(requirement.get("satisfaction_status", "")).lower()
            not in _SATISFIED_STATUSES
            for requirement in snapshot.get("evidence_requirements", [])
            if isinstance(requirement, dict)
        )
    )
    return _check(
        "DESIGN_NO_PREMATURE_CONCLUSIONS",
        passed,
        "Research design contains no premature evidence or conclusions.",
    )


def _aggregate(checks: tuple[GateCheck, ...]) -> str:
    if any(check.status == "fail" for check in checks):
        return "fail"
    if any(check.status == "warning" for check in checks):
        return "pass_with_warnings"
    if checks and all(check.status == "not_applicable" for check in checks):
        return "not_applicable"
    return "pass"


def _design_gate(version: dict[str, Any]) -> GateResult:
    snapshot = version.get("snapshot", {})
    checks = (
        _primary_question(snapshot),
        _scope_check(snapshot, "included_scope", "DESIGN_SCOPE_INCLUDED_PRESENT"),
        _scope_check(snapshot, "excluded_scope", "DESIGN_SCOPE_EXCLUDED_PRESENT"),
        _router(snapshot),
        _question_tree(snapshot),
        _required_questions(snapshot),
        _counter_claims(snapshot),
        _plan(snapshot, "validation_metrics", "validation_metric_ids", "DESIGN_VALIDATION_PLAN_PRESENT", "metric_id"),
        _plan(snapshot, "invalidation_conditions", "invalidation_condition_ids", "DESIGN_INVALIDATION_PLAN_PRESENT", "condition_id"),
        _references(snapshot, version),
        _provenance(snapshot),
        _no_premature(version, snapshot),
    )
    return GateResult("design", _aggregate(checks), checks)


def _later_gate(version: dict[str, Any], gate: str) -> GateResult:
    if version.get("creation_stage") == "research_design":
        checks = (
            GateCheck(
                "GATE_CREATION_STAGE_NOT_APPLICABLE",
                "not_applicable",
                f"The {gate} gate does not apply to a research_design snapshot.",
            ),
        )
        return GateResult(gate, "not_applicable", checks)
    checks = (
        GateCheck(
            "GATE_R1_NOT_IMPLEMENTED",
            "fail",
            f"The {gate} gate is not implemented in R1.",
        ),
    )
    return GateResult(gate, "fail", checks)


def evaluate_gate(version: dict[str, Any], gate: str) -> GateResult:
    evaluators: dict[str, Callable[[], GateResult]] = {
        "design": lambda: _design_gate(version),
        "evidence": lambda: _later_gate(version, "evidence"),
        "publication": lambda: _later_gate(version, "publication"),
    }
    try:
        evaluator = evaluators[gate]
    except (KeyError, TypeError) as exc:
        raise ResearchProjectV2Error(
            f"Unknown research project gate: {gate}",
            code="RESEARCH_PROJECT_GATE_UNKNOWN",
            details={"gate": gate},
        ) from exc
    return evaluator()


__all__ = ["GateCheck", "GateResult", "evaluate_gate"]
