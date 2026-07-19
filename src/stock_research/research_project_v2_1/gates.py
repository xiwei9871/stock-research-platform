from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re
from typing import Any
import unicodedata

from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.lineage import (
    LineageError,
    collect_lineage_version_ids,
)
from stock_research.research_project_v2_1.loader import (
    list_layered_versions,
    load_industry_version,
    resolve_upstream_r1_version,
)
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
    "company_list",
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
_CHINESE_DOWNSTREAM_SUBJECTS = (
    "公司",
    "企业",
    "发行人",
    "个股",
    "股票",
    "证券",
    "股权",
)
_CHINESE_DOWNSTREAM_ACTIONS = (
    "推荐",
    "评级",
    "排名",
    "筛选",
    "画像",
    "能力",
    "观察名单",
    "策略",
    "估值",
    "候选",
    "映射",
    "评估",
    "输出",
    "清单",
    "名单",
    "集合",
    "收集",
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
    missing_questions = sorted(item for item in required - covered if isinstance(item, str))
    critical_claim_ids = _critical_claim_ids(snapshot)
    covered_claims = {
        item.get("target_id")
        for item in snapshot.get("evidence_requirements", [])
        if isinstance(item, dict)
        and item.get("target_type") == "research_claim"
        and item.get("collection_status") not in {"invalid", "cancelled", "rejected"}
    }
    missing_claims = sorted(critical_claim_ids - covered_claims)
    return _result(
        INDUSTRY_DESIGN_CHECKS[4],
        bool(required) and not missing_questions and bool(critical_claim_ids) and not missing_claims,
        {
            "missing": missing_questions,
            "missing_required_question_ids": missing_questions,
            "missing_critical_claim_ids": missing_claims,
        },
    )


def _search_plans(snapshot: dict[str, Any]) -> dict[str, Any]:
    requirements = snapshot.get("evidence_requirements", [])
    plans = snapshot.get("search_plans", [])
    failures: list[dict[str, Any]] = []
    requirement_ids: list[str] = []
    if isinstance(requirements, list):
        requirement_ids = [
            item["requirement_id"]
            for item in requirements
            if isinstance(item, dict)
            and isinstance(item.get("requirement_id"), str)
            and item["requirement_id"]
        ]
    if len(requirement_ids) != len(requirements) or len(set(requirement_ids)) != len(
        requirement_ids
    ):
        failures.append({"reason": "invalid or duplicate requirement_id"})
    known_requirements = set(requirement_ids)
    covered: set[str] = set()
    seen_plan_ids: set[str] = set()
    seen_query_ids: set[str] = set()
    if not isinstance(plans, list):
        failures.append({"reason": "search_plans must be a list"})
    else:
        for plan in plans:
            if not isinstance(plan, dict):
                failures.append({"reason": "search plan must be an object"})
                continue
            plan_id = plan.get("search_plan_id")
            if not isinstance(plan_id, str) or not plan_id or plan_id in seen_plan_ids:
                failures.append({"reason": "invalid or duplicate search_plan_id", "plan_id": plan_id})
            else:
                seen_plan_ids.add(plan_id)
            plan_requirement_ids = plan.get("requirement_ids")
            if not isinstance(plan_requirement_ids, list) or not plan_requirement_ids:
                failures.append({"reason": "empty requirement_ids", "plan_id": plan_id})
            else:
                for requirement_id in plan_requirement_ids:
                    if not isinstance(requirement_id, str) or requirement_id not in known_requirements:
                        failures.append(
                            {
                                "reason": "unknown requirement_id",
                                "plan_id": plan_id,
                                "requirement_id": requirement_id,
                            }
                        )
                    else:
                        covered.add(requirement_id)
            queries = plan.get("queries")
            if not isinstance(queries, list) or not queries:
                failures.append({"reason": "empty queries", "plan_id": plan_id})
            else:
                for query in queries:
                    query_id = query.get("query_id") if isinstance(query, dict) else None
                    if not isinstance(query_id, str) or not query_id or query_id in seen_query_ids:
                        failures.append(
                            {"reason": "invalid or duplicate query_id", "query_id": query_id}
                        )
                    else:
                        seen_query_ids.add(query_id)
    uncovered = sorted(known_requirements - covered)
    if uncovered:
        failures.append({"reason": "uncovered requirement_id", "requirement_ids": uncovered})
    try:
        validate_search_plans(requirements, plans)
    except (ResearchProjectV2Error, KeyError, TypeError, ValueError) as exc:
        reason = exc.details.get("reason") if isinstance(exc, ResearchProjectV2Error) else None
        if reason not in {
            "missing counter_evidence query",
            "insufficient source classes",
            "source class contract mismatch",
        }:
            failures.append(
                {
                    "reason": getattr(exc, "code", type(exc).__name__),
                    "validator_reason": reason,
                    "message": str(exc),
                }
            )
    return _result(INDUSTRY_DESIGN_CHECKS[5], not failures, {"failures": failures})


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


def _claim_plan(
    snapshot: dict[str, Any],
    collection: str,
    code: str,
    *,
    object_id_field: str,
    claim_link_field: str,
) -> dict[str, Any]:
    objects_by_id: dict[str, list[dict[str, Any]]] = {}
    for item in snapshot.get(collection, []):
        if isinstance(item, dict) and isinstance(item.get(object_id_field), str):
            objects_by_id.setdefault(item[object_id_field], []).append(item)

    claim_issues: list[dict[str, Any]] = []
    critical_claims = [
        claim
        for claim in snapshot.get("claims", [])
        if isinstance(claim, dict) and claim.get("claim_id") in _critical_claim_ids(snapshot)
    ]
    for claim in critical_claims:
        claim_id = claim["claim_id"]
        raw_links = claim.get(claim_link_field)
        links = [item for item in raw_links if isinstance(item, str)] if isinstance(raw_links, list) else []
        duplicate_ids = sorted({item for item in links if links.count(item) > 1})
        missing_ids: list[str] = []
        mismatched_ids: list[str] = []
        if not links:
            missing_ids.append(f"<{claim_link_field}>")
        for object_id in dict.fromkeys(links):
            matches = objects_by_id.get(object_id, [])
            if not matches:
                missing_ids.append(object_id)
                continue
            if len(matches) != 1 or any(
                item.get("target_type") != "research_claim"
                or item.get("target_id") != claim_id
                or item.get("status") != "planned"
                for item in matches
            ):
                mismatched_ids.append(object_id)
        if duplicate_ids or missing_ids or mismatched_ids:
            claim_issues.append(
                {
                    "claim_id": claim_id,
                    "missing_ids": sorted(missing_ids),
                    "duplicate_ids": duplicate_ids,
                    "mismatched_ids": sorted(mismatched_ids),
                }
            )
    return _result(
        code,
        bool(critical_claims) and not claim_issues,
        {
            "claims": claim_issues,
            "missing_claim_ids": sorted(
                issue["claim_id"] for issue in claim_issues if issue["missing_ids"]
            ),
            "mismatched_claim_ids": sorted(
                issue["claim_id"]
                for issue in claim_issues
                if issue["duplicate_ids"] or issue["mismatched_ids"]
            ),
        },
    )


def _key_tokens(key: object) -> set[str]:
    text = unicodedata.normalize("NFKC", str(key))
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", text)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    raw_tokens = re.findall(r"[a-z0-9]+", text.casefold())
    canonical = {
        "companies": "company",
        "corporations": "corporate",
        "entities": "entity",
        "equities": "equity",
        "securities": "security",
        "stocks": "stock",
        "assessments": "assessment",
        "boundaries": "boundary",
        "candidates": "candidate",
        "capabilities": "capability",
        "cases": "case",
        "collections": "collection",
        "contexts": "context",
        "examples": "example",
        "lists": "list",
        "mappings": "mapping",
        "maps": "map",
        "outputs": "output",
        "profiles": "profile",
        "rankings": "ranking",
        "ratings": "rating",
        "recommendations": "recommendation",
        "references": "reference",
        "screens": "screen",
        "scopes": "scope",
        "strategies": "strategy",
        "valuations": "valuation",
        "watchlists": "watchlist",
    }
    return {canonical.get(token, token) for token in raw_tokens}


def _background_tokens() -> set[str]:
    return {
        "background", "boundary", "case", "context", "engineering", "example",
        "reference", "scope", "universe",
    }


def _subject_groups(tokens: set[str]) -> set[str]:
    subjects: set[str] = set()
    if tokens & {"company", "corporate", "entity", "issuer"}:
        subjects.add("company")
    if tokens & {"stock", "equity", "security", "share"}:
        subjects.add("stock")
    return subjects


def _chinese_subject_groups(compact_key: str) -> set[str]:
    subjects: set[str] = set()
    if any(subject in compact_key for subject in ("公司", "企业", "发行人")):
        subjects.add("company")
    if any(subject in compact_key for subject in ("个股", "股票", "证券", "股权")):
        subjects.add("stock")
    return subjects


def _has_background_marker(tokens: set[str], compact_key: str) -> bool:
    return bool(tokens & _background_tokens()) or any(
        marker in compact_key
        for marker in ("背景", "参考", "上下文", "范围", "边界", "案例", "示例", "工程", "资料")
    )


def _is_downstream_output_key(
    key: object,
    *,
    path_subjects: frozenset[str] = frozenset(),
    background_context: bool = False,
) -> bool:
    normalized_key = unicodedata.normalize("NFKC", str(key)).casefold()
    compact_key = re.sub(r"[\W_]+", "", normalized_key)
    if (
        any(subject in compact_key for subject in _CHINESE_DOWNSTREAM_SUBJECTS)
        and any(action in compact_key for action in _CHINESE_DOWNSTREAM_ACTIONS)
    ):
        return True
    if normalized_key in _OUTPUT_KEYS:
        return True
    tokens = _key_tokens(key)
    local_subjects = _subject_groups(tokens) | _chinese_subject_groups(compact_key)
    effective_subjects = local_subjects | set(path_subjects)
    if effective_subjects and any(
        action in compact_key for action in _CHINESE_DOWNSTREAM_ACTIONS
    ):
        return True
    company_outputs = {
        "assessment", "candidate", "capability", "capture", "collection", "list", "map",
        "mapping", "output", "profile", "ranking", "rating", "recommendation",
        "screen", "strategy", "valuation", "watchlist",
    }
    stock_outputs = {
        "candidate", "list", "map", "output", "ranking", "rating",
        "recommendation", "screen", "strategy", "valuation", "watchlist",
    }
    has_output = ("company" in effective_subjects and bool(tokens & company_outputs)) or (
        "stock" in effective_subjects and bool(tokens & stock_outputs)
    )
    if has_output:
        return True
    if (
        effective_subjects
        and "notes" in tokens
        and not background_context
        and not _has_background_marker(tokens, compact_key)
    ):
        return True
    return False


def _output_paths(
    value: object,
    path: tuple[object, ...] = (),
    *,
    path_subjects: frozenset[str] = frozenset(),
    background_context: bool = False,
) -> list[list[object]]:
    found: list[list[object]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = (*path, key)
            if _is_downstream_output_key(
                key,
                path_subjects=path_subjects,
                background_context=background_context,
            ):
                found.append(list(child_path))
            key_tokens = _key_tokens(key)
            compact_key = re.sub(
                r"[\W_]+",
                "",
                unicodedata.normalize("NFKC", str(key)).casefold(),
            )
            child_path_subjects = frozenset(
                set(path_subjects)
                | _subject_groups(key_tokens)
                | _chinese_subject_groups(compact_key)
            )
            child_background_context = background_context or _has_background_marker(
                key_tokens,
                compact_key,
            )
            found.extend(
                _output_paths(
                    child,
                    child_path,
                    path_subjects=child_path_subjects,
                    background_context=child_background_context,
                )
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(
                _output_paths(
                    child,
                    (*path, index),
                    path_subjects=path_subjects,
                    background_context=background_context,
                )
            )
    return found


def _valid_timestamp(value: object) -> bool:
    if not isinstance(value, str) or _RFC3339.fullmatch(value) is None:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _provenance(
    snapshot: dict[str, Any],
    *,
    allowed_versions: set[str],
    lineage_error: str | None,
) -> dict[str, Any]:
    invalid: list[str] = []
    mismatched: list[str] = []
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
            elif provenance.get("created_in_version") not in allowed_versions:
                mismatched.append(str(object_id))
    return _result(
        INDUSTRY_DESIGN_CHECKS[11],
        not invalid and not mismatched and lineage_error is None,
        {
            "invalid": sorted(invalid),
            "mismatched_object_ids": sorted(mismatched),
            "lineage_error": lineage_error,
        },
    )


def _verified_gate_lineage(
    identity: dict[str, Any],
    version: dict[str, Any],
    layout: LayeredResearchLayout | None,
) -> tuple[set[str], str | None]:
    version_id = version.get("version_id")
    slug = identity.get("project_slug")
    semantic_version = version.get("semantic_version")
    if not isinstance(slug, str) or not isinstance(semantic_version, str):
        return set(), "lineage version identity mismatch"
    if version_id != f"research_version:{slug}:{semantic_version}":
        return set(), "lineage version identity mismatch"
    if layout is None:
        if version.get("parent_version_id") is None and semantic_version == "0.1.0":
            return {version_id}, None
        return set(), "verified lineage storage is required"
    if content_sha256(version, excluded_paths={("content_hash",)}) != version.get(
        "content_hash"
    ):
        return set(), "gate version does not match verified storage"
    try:
        stored_current = load_industry_version(slug, semantic_version, layout=layout)
        if (
            stored_current.get("version_id") != version_id
            or stored_current.get("content_hash") != version.get("content_hash")
        ):
            return set(), "gate version does not match verified storage"
        known_versions = list_layered_versions(slug, layout=layout)
        lineage_ids = collect_lineage_version_ids(
            stored_current,
            project_slug=slug,
            known_semantic_versions=known_versions,
            load_version=lambda parent_semver: load_industry_version(
                slug,
                parent_semver,
                layout=layout,
            ),
        )
        return set(lineage_ids), None
    except LineageError as exc:
        return set(), exc.reason
    except ResearchProjectV2Error as exc:
        return set(), exc.code


def evaluate_industry_design_gate(
    identity: dict[str, Any],
    version: dict[str, Any],
    *,
    layout: LayeredResearchLayout | None = None,
) -> dict[str, Any]:
    """Evaluate the immutable R2A industry design contract without mutation."""
    safe_identity, safe_version = deepcopy(identity), deepcopy(version)
    snapshot = safe_version.get("snapshot") if isinstance(safe_version.get("snapshot"), dict) else {}
    allowed_provenance_versions, lineage_error = _verified_gate_lineage(
        safe_identity,
        safe_version,
        layout,
    )
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
        _claim_plan(
            snapshot,
            "validation_metrics",
            INDUSTRY_DESIGN_CHECKS[8],
            object_id_field="metric_id",
            claim_link_field="validation_metric_ids",
        ),
        _claim_plan(
            snapshot,
            "invalidation_conditions",
            INDUSTRY_DESIGN_CHECKS[9],
            object_id_field="condition_id",
            claim_link_field="invalidation_condition_ids",
        ),
        _result(
            INDUSTRY_DESIGN_CHECKS[10],
            not _output_paths(safe_version),
            {"paths": _output_paths(safe_version)},
        ),
        _provenance(
            snapshot,
            allowed_versions=allowed_provenance_versions,
            lineage_error=lineage_error,
        ),
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
