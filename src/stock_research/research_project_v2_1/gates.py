from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re
from typing import Any

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.loader import resolve_upstream_r1_version
from stock_research.research_project_v2_1.search_plan import validate_search_plans


INDUSTRY_DESIGN_CHECKS = (
    "INDUSTRY_LAYER_CORRECT",
    "INDUSTRY_UPSTREAM_BASELINE_RESOLVED",
    "INDUSTRY_PRIMARY_QUESTION_PRESENT",
    "INDUSTRY_SCOPE_EXCLUDES_COMPANY_STOCK_RATING",
    "INDUSTRY_REQUIRED_QUESTIONS_COVERED",
    "INDUSTRY_SEARCH_PLANS_COVER_REQUIREMENTS",
    "INDUSTRY_COUNTER_SEARCH_PRESENT",
    "INDUSTRY_SOURCE_CLASS_DIVERSITY",
    "INDUSTRY_VALIDATION_PLAN_PRESENT",
    "INDUSTRY_INVALIDATION_PLAN_PRESENT",
    "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS",
    "INDUSTRY_PROVENANCE_COMPLETE",
)

_OUTPUT_KEYS = {
    "candidate_companies",
    "company_candidates",
    "company_capture_assessments",
    "company_capability_collection",
    "company_capabilities",
    "company",
    "company_list",
    "companies",
    "stock_candidates",
    "stock_outputs",
    "stock_rating",
    "stock_ratings",
}
_SCOPE_TERMS = (
    "company rating",
    "company ranking",
    "candidate companies",
    "stock rating",
    "stock recommendation",
    "公司评级",
    "公司排名",
    "候选公司",
    "股票评级",
    "股票推荐",
    "个股推荐",
    "目标价",
    "买入评级",
    "卖出评级",
)
_PROVENANCE_COLLECTIONS = {
    "questions": "question_id",
    "claims": "claim_id",
    "claim_relations": "relation_id",
    "evidence_requirements": "requirement_id",
    "references": "reference_id",
    "causal_nodes": "causal_node_id",
    "causal_edges": "causal_edge_id",
    "validation_metrics": "metric_id",
    "invalidation_conditions": "condition_id",
    "search_plans": "search_plan_id",
}
_ACTOR_TYPES = {"human", "codex", "automated_pipeline", "imported"}
_REVIEW_STATUSES = {"unreviewed", "pending_review", "reviewed", "rejected"}
_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def _result(code: str, passed: bool, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"code": code, "status": "pass" if passed else "fail", "details": details or {}}


def _upstream(snapshot: dict[str, Any]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    references = snapshot.get("upstream_research_refs")
    if not isinstance(references, list) or not references:
        failures.append({"reason": "missing upstream R1 baseline"})
    else:
        for reference in references:
            if not isinstance(reference, dict):
                failures.append({"reason": "invalid upstream reference"})
                continue
            try:
                resolve_upstream_r1_version(reference)
            except (ResearchProjectV2Error, KeyError, TypeError, ValueError) as exc:
                failures.append(
                    {
                        "reference": reference.get("upstream_research_ref_id"),
                        "reason": getattr(exc, "code", type(exc).__name__),
                    }
                )
    return _result(INDUSTRY_DESIGN_CHECKS[1], not failures, {"failures": failures})


def _primary(snapshot: dict[str, Any]) -> dict[str, Any]:
    scope = snapshot.get("scope") if isinstance(snapshot.get("scope"), dict) else {}
    primary = scope.get("primary_question")
    matches = [
        item
        for item in snapshot.get("questions", [])
        if isinstance(item, dict)
        and item.get("question_type") == "primary"
        and item.get("required_for_gate") is True
        and isinstance(item.get("question_text"), str)
        and isinstance(primary, str)
        and item["question_text"].strip() == primary.strip()
    ]
    return _result(INDUSTRY_DESIGN_CHECKS[2], bool(primary and primary.strip() and matches))


def _scope(snapshot: dict[str, Any]) -> dict[str, Any]:
    scope = snapshot.get("scope") if isinstance(snapshot.get("scope"), dict) else {}
    excluded = " ".join(str(item).casefold() for item in scope.get("excluded_scope", []))
    included_payload = {
        key: scope.get(key)
        for key in ("included_scope", "primary_question", "research_object", "industry_boundary")
    }
    included = str(included_payload).casefold()
    company_exclusion_groups = (
        ("company", "rating"),
        ("company", "ranking"),
        ("公司", "评级"),
        ("公司", "排名"),
    )
    stock_exclusion_groups = (
        ("stock", "rating"),
        ("股票", "评级"),
        ("个股", "推荐"),
    )
    explicitly_excluded = (
        any(all(term in excluded for term in group) for group in company_exclusion_groups)
        and any(all(term in excluded for term in group) for group in stock_exclusion_groups)
    )
    offending = sorted(term for term in _SCOPE_TERMS if term.casefold() in included)
    return _result(
        INDUSTRY_DESIGN_CHECKS[3],
        explicitly_excluded and not offending,
        {"offending_terms": offending},
    )


def _required_questions(snapshot: dict[str, Any]) -> dict[str, Any]:
    required = {
        item.get("question_id")
        for item in snapshot.get("questions", [])
        if isinstance(item, dict) and item.get("required_for_gate") is True
    }
    covered = {
        item.get("target_id")
        for item in snapshot.get("evidence_requirements", [])
        if isinstance(item, dict)
        and item.get("target_type") == "research_question"
        and item.get("collection_status") not in {"invalid", "cancelled", "rejected"}
    }
    missing = sorted(item for item in required - covered if isinstance(item, str))
    return _result(INDUSTRY_DESIGN_CHECKS[4], bool(required) and not missing, {"missing": missing})


def _search_plans(snapshot: dict[str, Any]) -> dict[str, Any]:
    requirements = snapshot.get("evidence_requirements", [])
    plans = snapshot.get("search_plans", [])
    try:
        validate_search_plans(requirements, plans)
    except (ResearchProjectV2Error, KeyError, TypeError, ValueError) as exc:
        reason = exc.details.get("reason") if isinstance(exc, ResearchProjectV2Error) else None
        if reason in {
            "missing counter_evidence query",
            "insufficient source classes",
            "source class contract mismatch",
        }:
            return _result(INDUSTRY_DESIGN_CHECKS[5], True)
        return _result(
            INDUSTRY_DESIGN_CHECKS[5],
            False,
            {"reason": getattr(exc, "code", type(exc).__name__), "message": str(exc)},
        )
    return _result(INDUSTRY_DESIGN_CHECKS[5], True)


def _counter(snapshot: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    plans = snapshot.get("search_plans", [])
    for plan in plans if isinstance(plans, list) else []:
        roles = {
            query.get("query_role")
            for query in plan.get("queries", [])
            if isinstance(query, dict)
        } if isinstance(plan, dict) else set()
        if "counter_evidence" not in roles:
            missing.append(str(plan.get("search_plan_id", "<unknown>")))
    return _result(INDUSTRY_DESIGN_CHECKS[6], bool(plans) and not missing, {"missing": missing})


def _source_diversity(snapshot: dict[str, Any]) -> dict[str, Any]:
    insufficient: list[str] = []
    requirement_classes: dict[str, set[str]] = {}
    for requirement in snapshot.get("evidence_requirements", []):
        if not isinstance(requirement, dict):
            insufficient.append("<unknown>")
            continue
        classes = requirement.get("required_source_classes")
        distinct = set(classes) if isinstance(classes, list) else set()
        requirement_id = str(requirement.get("requirement_id", "<unknown>"))
        requirement_classes[requirement_id] = distinct
        if len(distinct) < 2 and distinct not in ({"technical_standard"}, {"primary_standard"}):
            insufficient.append(requirement_id)
    mismatched_queries: list[str] = []
    for plan in snapshot.get("search_plans", []):
        if not isinstance(plan, dict):
            continue
        expected: set[str] = set()
        for requirement_id in plan.get("requirement_ids", []):
            if isinstance(requirement_id, str):
                expected.update(requirement_classes.get(requirement_id, set()))
        for query in plan.get("queries", []):
            actual = set(query.get("source_classes", [])) if isinstance(query, dict) else set()
            if actual != expected:
                mismatched_queries.append(
                    str(query.get("query_id", "<unknown>")) if isinstance(query, dict) else "<unknown>"
                )
    return _result(
        INDUSTRY_DESIGN_CHECKS[7],
        bool(snapshot.get("evidence_requirements")) and not insufficient and not mismatched_queries,
        {"insufficient": insufficient, "mismatched_queries": mismatched_queries},
    )


def _critical_claim_ids(snapshot: dict[str, Any]) -> set[str]:
    return {
        item.get("claim_id")
        for item in snapshot.get("claims", [])
        if isinstance(item, dict)
        and item.get("claim_kind") == "primary"
        and isinstance(item.get("importance"), (int, float))
        and not isinstance(item.get("importance"), bool)
        and item["importance"] >= 0.8
        and isinstance(item.get("claim_id"), str)
    }


def _claim_plan(snapshot: dict[str, Any], collection: str, code: str) -> dict[str, Any]:
    critical = _critical_claim_ids(snapshot)
    covered = {
        item.get("target_id")
        for item in snapshot.get(collection, [])
        if isinstance(item, dict)
        and item.get("target_type") == "research_claim"
        and item.get("status") == "planned"
    }
    missing = sorted(critical - covered)
    return _result(code, bool(critical) and not missing, {"missing": missing})


def _output_paths(value: object, path: tuple[object, ...] = ()) -> list[list[object]]:
    found: list[list[object]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (*path, key)
            normalized_key = str(key).casefold()
            key_tokens = set(re.split(r"[^a-z0-9]+", normalized_key))
            downstream_subject = bool(key_tokens & {"company", "companies", "stock", "stocks"})
            output_marker = bool(
                key_tokens
                & {
                    "assessment", "assessments", "candidate", "candidates",
                    "capability", "capabilities", "capture", "collection",
                    "list", "output", "outputs", "ranking", "rankings", "rating",
                    "ratings", "recommendation", "recommendations",
                }
            )
            if normalized_key in _OUTPUT_KEYS or (downstream_subject and output_marker):
                found.append(list(child_path))
            found.extend(_output_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_output_paths(child, (*path, index)))
    return found


def _valid_timestamp(value: object) -> bool:
    if not isinstance(value, str) or _RFC3339.fullmatch(value) is None:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _provenance(snapshot: dict[str, Any]) -> dict[str, Any]:
    invalid: list[str] = []
    for collection, id_field in _PROVENANCE_COLLECTIONS.items():
        for item in snapshot.get(collection, []):
            object_id = item.get(id_field, f"<{collection}>") if isinstance(item, dict) else f"<{collection}>"
            provenance = item.get("provenance") if isinstance(item, dict) else None
            if not isinstance(provenance, dict) or not (
                isinstance(provenance.get("created_by"), str)
                and provenance["created_by"].strip()
                and provenance.get("actor_type") in _ACTOR_TYPES
                and (provenance.get("agent_run_id") is None or isinstance(provenance.get("agent_run_id"), str))
                and _valid_timestamp(provenance.get("created_at"))
                and isinstance(provenance.get("created_in_version"), str)
                and provenance["created_in_version"].strip()
                and provenance.get("review_status") in _REVIEW_STATUSES
            ):
                invalid.append(str(object_id))
    return _result(INDUSTRY_DESIGN_CHECKS[11], not invalid, {"invalid": sorted(invalid)})


def evaluate_industry_design_gate(
    identity: dict[str, Any], version: dict[str, Any]
) -> dict[str, Any]:
    """Evaluate the immutable R2A industry design contract without mutation."""
    safe_identity, safe_version = deepcopy(identity), deepcopy(version)
    snapshot = safe_version.get("snapshot") if isinstance(safe_version.get("snapshot"), dict) else {}
    checks = [
        _result(
            INDUSTRY_DESIGN_CHECKS[0],
            safe_identity.get("research_layer") == "industry_research"
            and snapshot.get("research_layer") == "industry_research",
            {
                "identity_layer": safe_identity.get("research_layer"),
                "snapshot_layer": snapshot.get("research_layer"),
            },
        ),
        _upstream(snapshot),
        _primary(snapshot),
        _scope(snapshot),
        _required_questions(snapshot),
        _search_plans(snapshot),
        _counter(snapshot),
        _source_diversity(snapshot),
        _claim_plan(snapshot, "validation_metrics", INDUSTRY_DESIGN_CHECKS[8]),
        _claim_plan(snapshot, "invalidation_conditions", INDUSTRY_DESIGN_CHECKS[9]),
        _result(
            INDUSTRY_DESIGN_CHECKS[10],
            not _output_paths(safe_version),
            {"paths": _output_paths(safe_version)},
        ),
        _provenance(snapshot),
    ]
    status = "fail" if any(check["status"] == "fail" for check in checks) else "pass"
    return {
        "gate": "industry_design",
        "status": status,
        "overall": status,
        "checks": checks,
    }


def list_industry_design_checks() -> list[str]:
    return list(INDUSTRY_DESIGN_CHECKS)


__all__ = [
    "INDUSTRY_DESIGN_CHECKS",
    "evaluate_industry_design_gate",
    "list_industry_design_checks",
]
