from __future__ import annotations

from typing import Any

from stock_research.research_project_v2.errors import ResearchProjectV2Error


FORBIDDEN_INDUSTRY_SEARCH_TERMS = {
    "目标价",
    "买入",
    "卖出",
    "股票推荐",
    "估值最低",
    "最强龙头",
    "target price",
    "buy rating",
    "sell rating",
    "top stock",
    "candidate companies",
    "company ranking",
    "上市公司排名",
    "受益标的",
}

# R1 evidence requirements have no separate single-source exception flag. A
# plan may therefore use one source class only when that class explicitly names
# a primary engineering standard.
SINGLE_PRIMARY_STANDARD_SOURCE_CLASSES = {
    "technical_standard",
    "primary_standard",
}

_ALLOWED_STATUSES = {
    "planned",
    "active",
    "complete",
    "superseded",
    "cancelled",
}
_DOWNSTREAM_FIELDS = {"candidate_companies", "company", "stock_rating"}
_QUERY_SPECS = (
    ("mechanism", "mechanism engineering"),
    ("quantification", "capacity yield price data"),
    ("counter_evidence", "alternative substitution limitation"),
    ("primary_engineering", "standard specification technical document"),
)


def _invalid(reason: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        f"Invalid industry evidence search plan: {reason}",
        code="RESEARCH_PROJECT_V2_1_SEARCH_PLAN_INVALID",
        details={"reason": reason, **details},
    )


def _trimmed(
    value: object, *, field: str, owner: str, **details: object
) -> str:
    if not isinstance(value, str):
        raise _invalid(
            f"missing {field}",
            field=field,
            owner=owner,
            value_type=type(value).__name__,
            **details,
        )
    trimmed = value.strip()
    if not trimmed:
        raise _invalid(f"blank {field}", field=field, owner=owner, **details)
    return trimmed


def _trimmed_unique_strings(
    values: object,
    *,
    field: str,
    owner: str,
    **details: object,
) -> list[str]:
    if not isinstance(values, list) or not values:
        raise _invalid(
            f"empty {field}", field=field, owner=owner, **details
        )
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise _invalid(
                f"blank {field}", field=field, owner=owner, **details
            )
        trimmed = value.strip()
        if trimmed not in seen:
            seen.add(trimmed)
            normalized.append(trimmed)
    return normalized


def _find_forbidden_term(text: str) -> str | None:
    normalized = text.casefold()
    for term in sorted(FORBIDDEN_INDUSTRY_SEARCH_TERMS, key=str.casefold):
        if term.casefold() in normalized:
            return term
    return None


def _reject_forbidden(text: str, *, field: str, **details: object) -> None:
    term = _find_forbidden_term(text)
    if term is not None:
        raise _invalid(
            "forbidden industry search term",
            field=field,
            forbidden_term=term,
            **details,
        )


def _single_standard_exception(source_classes: list[str]) -> bool:
    return (
        len(source_classes) == 1
        and source_classes[0] in SINGLE_PRIMARY_STANDARD_SOURCE_CLASSES
    )


def compile_search_plan(
    requirement: dict[str, Any],
    *,
    project_id: str,
    version_id: str,
    domain_terms: list[str],
) -> dict[str, Any]:
    """Compile one industry evidence requirement into a deterministic plan."""
    requirement_id: str | None = None
    try:
        requirement_id = _trimmed(
            requirement.get("requirement_id"),
            field="requirement_id",
            owner="requirement",
        )
        question = _trimmed(
            requirement.get("question_to_resolve"),
            field="question_to_resolve",
            owner=requirement_id,
            requirement_id=requirement_id,
        )
        source_classes = _trimmed_unique_strings(
            requirement.get("required_source_classes"),
            field="required_source_classes",
            owner=requirement_id,
            requirement_id=requirement_id,
        )
        terms = _trimmed_unique_strings(
            domain_terms,
            field="domain_terms",
            owner=requirement_id,
            requirement_id=requirement_id,
        )
        normalized_project_id = _trimmed(
            project_id, field="project_id", owner=requirement_id
        )
        normalized_version_id = _trimmed(
            version_id, field="version_id", owner=requirement_id
        )
        publication_window = _trimmed(
            requirement.get("required_freshness"),
            field="required_freshness",
            owner=requirement_id,
        )
        provenance = requirement["provenance"]
    except (KeyError, TypeError, AttributeError) as exc:
        raise _invalid(
            "invalid requirement structure",
            exception_type=type(exc).__name__,
            **(
                {"requirement_id": requirement_id}
                if requirement_id is not None
                else {}
            ),
        ) from exc

    _reject_forbidden(
        question, field="question_to_resolve", requirement_id=requirement_id
    )
    for index, term in enumerate(terms):
        _reject_forbidden(
            term,
            field="domain_terms",
            requirement_id=requirement_id,
            index=index,
        )
    if len(source_classes) < 2 and not _single_standard_exception(source_classes):
        raise _invalid(
            "insufficient source classes",
            requirement_id=requirement_id,
            field="required_source_classes",
        )

    term_text = " ".join(terms)
    excluded_terms = sorted(FORBIDDEN_INDUSTRY_SEARCH_TERMS)
    queries: list[dict[str, Any]] = []
    for priority, (role, suffix) in enumerate(_QUERY_SPECS, start=1):
        if role == "primary_engineering":
            query_text = f"{term_text} {suffix}"
        else:
            query_text = f"{term_text} {question} {suffix}"
        _reject_forbidden(
            query_text,
            field="query_text",
            requirement_id=requirement_id,
            query_role=role,
        )
        queries.append(
            {
                "query_id": f"query:{requirement_id}:{role}",
                "query_role": role,
                "query_text": query_text,
                "required_terms": list(terms),
                "excluded_terms": list(excluded_terms),
                "source_classes": list(source_classes),
                "priority": priority,
            }
        )

    return {
        "search_plan_id": f"search_plan:{requirement_id}",
        "project_id": normalized_project_id,
        "version_id": normalized_version_id,
        "evidence_channel": "industry",
        "requirement_ids": [requirement_id],
        "queries": queries,
        "languages": ["zh-CN", "en"],
        "geography": ["CN", "global"],
        "publication_window": publication_window,
        "result_limit_per_query": 20,
        "deduplication_policy": "normalized_url_then_content_hash",
        "stop_conditions": [
            "all four industry query roles executed",
            "counter-evidence query executed and reviewed",
            "required source-class coverage reached",
        ],
        "status": "planned",
        "provenance": provenance,
    }


def _reject_downstream_fields(value: object, *, plan_id: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _DOWNSTREAM_FIELDS:
                raise _invalid(
                    "downstream field", plan_id=plan_id, field=key
                )
            _reject_downstream_fields(child, plan_id=plan_id)
    elif isinstance(value, list):
        for child in value:
            _reject_downstream_fields(child, plan_id=plan_id)


def validate_search_plans(
    requirements: list[dict[str, Any]], plans: list[dict[str, Any]]
) -> None:
    """Validate cross-plan semantics independently of JSON Schema validation.

    A requirement may be covered by more than one plan. All referenced
    requirements must exist, every requirement must be covered, and plan/query
    identifiers remain globally unique.
    """
    location: dict[str, object] = {}
    try:
        if not isinstance(requirements, list) or not isinstance(plans, list):
            raise TypeError("requirements and plans must be lists")

        requirement_by_id: dict[str, dict[str, Any]] = {}
        for requirement in requirements:
            location = {}
            requirement_id = _trimmed(
                requirement["requirement_id"],
                field="requirement_id",
                owner="requirement",
            )
            location = {"requirement_id": requirement_id}
            if requirement_id in requirement_by_id:
                raise _invalid(
                    "duplicate requirement_id", requirement_id=requirement_id
                )
            question = _trimmed(
                requirement["question_to_resolve"],
                field="question_to_resolve",
                owner=requirement_id,
                requirement_id=requirement_id,
            )
            _reject_forbidden(
                question,
                field="question_to_resolve",
                requirement_id=requirement_id,
            )
            _trimmed_unique_strings(
                requirement["required_source_classes"],
                field="required_source_classes",
                owner=requirement_id,
                requirement_id=requirement_id,
            )
            requirement_by_id[requirement_id] = requirement

        seen_plan_ids: set[str] = set()
        seen_query_ids: set[str] = set()
        covered_requirement_ids: set[str] = set()
        for plan in plans:
            location = {}
            plan_id = _trimmed(
                plan["search_plan_id"],
                field="search_plan_id",
                owner="plan",
            )
            location = {"plan_id": plan_id}
            if plan_id in seen_plan_ids:
                raise _invalid("duplicate search_plan_id", plan_id=plan_id)
            seen_plan_ids.add(plan_id)
            _reject_downstream_fields(plan, plan_id=plan_id)

            if plan["evidence_channel"] != "industry":
                raise _invalid(
                    "invalid evidence_channel",
                    plan_id=plan_id,
                    field="evidence_channel",
                )
            if plan["status"] not in _ALLOWED_STATUSES:
                raise _invalid(
                    "invalid status", plan_id=plan_id, field="status"
                )

            requirement_ids = _trimmed_unique_strings(
                plan["requirement_ids"],
                field="requirement_ids",
                owner=plan_id,
                plan_id=plan_id,
            )
            referenced_requirements: list[dict[str, Any]] = []
            for requirement_id in requirement_ids:
                if requirement_id not in requirement_by_id:
                    raise _invalid(
                        "unknown requirement_id",
                        plan_id=plan_id,
                        requirement_id=requirement_id,
                    )
                referenced_requirements.append(requirement_by_id[requirement_id])
                covered_requirement_ids.add(requirement_id)

            queries = plan["queries"]
            if not isinstance(queries, list) or not queries:
                raise _invalid("empty queries", plan_id=plan_id)
            roles: set[str] = set()
            for query in queries:
                location = {"plan_id": plan_id}
                query_id = _trimmed(
                    query["query_id"],
                    field="query_id",
                    owner=plan_id,
                    plan_id=plan_id,
                )
                location["query_id"] = query_id
                if query_id in seen_query_ids:
                    raise _invalid(
                        "duplicate query_id", plan_id=plan_id, query_id=query_id
                    )
                seen_query_ids.add(query_id)
                query_role = _trimmed(
                    query["query_role"],
                    field="query_role",
                    owner=query_id,
                    plan_id=plan_id,
                    query_id=query_id,
                )
                roles.add(query_role)
                query_text = _trimmed(
                    query["query_text"],
                    field="query_text",
                    owner=query_id,
                    plan_id=plan_id,
                    query_id=query_id,
                )
                _reject_forbidden(
                    query_text,
                    field="query_text",
                    plan_id=plan_id,
                    query_id=query_id,
                )
                required_terms = _trimmed_unique_strings(
                    query["required_terms"],
                    field="required_terms",
                    owner=query_id,
                    plan_id=plan_id,
                    query_id=query_id,
                )
                for term in required_terms:
                    _reject_forbidden(
                        term,
                        field="required_terms",
                        plan_id=plan_id,
                        query_id=query_id,
                    )
                source_classes = _trimmed_unique_strings(
                    query["source_classes"],
                    field="source_classes",
                    owner=query_id,
                    plan_id=plan_id,
                    query_id=query_id,
                )
                single_standard_allowed = _single_standard_exception(source_classes)
                if single_standard_allowed:
                    single_standard_allowed = all(
                        _trimmed_unique_strings(
                            requirement["required_source_classes"],
                            field="required_source_classes",
                            owner=requirement["requirement_id"],
                        )
                        == source_classes
                        for requirement in referenced_requirements
                    )
                if len(source_classes) < 2 and not single_standard_allowed:
                    raise _invalid(
                        "insufficient source classes",
                        plan_id=plan_id,
                        query_id=query_id,
                    )

            if "counter_evidence" not in roles:
                raise _invalid("missing counter_evidence query", plan_id=plan_id)

        uncovered = sorted(set(requirement_by_id) - covered_requirement_ids)
        if uncovered:
            raise _invalid(
                "uncovered requirement_id", requirement_id=uncovered[0]
            )
    except ResearchProjectV2Error:
        raise
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise _invalid(
            "invalid search plan structure",
            exception_type=type(exc).__name__,
            detail=str(exc),
            **location,
        ) from exc
