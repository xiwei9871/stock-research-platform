from __future__ import annotations

from copy import deepcopy
import json

import pytest

import stock_research.research_project_v2_1.search_plan as search_plan_module
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload
from stock_research.research_project_v2_1.search_plan import (
    FORBIDDEN_INDUSTRY_SEARCH_TERMS,
    compile_search_plan,
    validate_search_plans,
)


PROVENANCE = {
    "created_by": "fixture-author",
    "actor_type": "human",
    "agent_run_id": None,
    "created_at": "2026-07-18T02:00:00Z",
    "created_in_version": "research_version:pcb:0.1.0",
    "review_status": "unreviewed",
}


def requirement(
    requirement_id: str = "requirement:industry:primary",
    *,
    question: str = "What engineering constraints determine scale-up?",
    source_classes: list[str] | None = None,
) -> dict[str, object]:
    return {
        "requirement_id": requirement_id,
        "target_type": "research_claim",
        "target_id": "claim:industry:primary",
        "question_to_resolve": question,
        "requirement_type": "validation",
        "required_source_classes": source_classes
        if source_classes is not None
        else ["technical_standard", "independent_secondary"],
        "required_independence": "independent",
        "required_freshness": "within_12_months",
        "required_scope": "global",
        "minimum_coverage": 2,
        "conflict_search_required": True,
        "primary_source_required": True,
        "collection_status": "not_started",
        "satisfaction_status": "unsatisfied",
        "provenance": PROVENANCE,
    }


def compiled_plan(**requirement_overrides: object) -> dict[str, object]:
    item = requirement()
    item.update(requirement_overrides)
    return compile_search_plan(
        item,
        project_id="research_project:pcb",
        version_id="research_version:pcb:0.1.0",
        domain_terms=[" high-layer PCB ", "low-loss laminate", "high-layer PCB"],
    )


def assert_invalid(call, *, reason: str) -> None:
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        call()

    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SEARCH_PLAN_INVALID"
    assert exc_info.value.details["reason"] == reason


def test_compile_search_plan_builds_canonical_industry_queries_and_schema_payload():
    item = requirement()

    plan = compile_search_plan(
        item,
        project_id="research_project:pcb",
        version_id="research_version:pcb:0.1.0",
        domain_terms=[" high-layer PCB ", "low-loss laminate", "high-layer PCB"],
    )

    assert plan["search_plan_id"] == "search_plan:requirement:industry:primary"
    assert plan["project_id"] == "research_project:pcb"
    assert plan["version_id"] == "research_version:pcb:0.1.0"
    assert plan["evidence_channel"] == "industry"
    assert plan["requirement_ids"] == ["requirement:industry:primary"]
    assert [query["query_role"] for query in plan["queries"]] == [
        "mechanism",
        "quantification",
        "counter_evidence",
        "primary_engineering",
    ]
    assert [query["query_id"] for query in plan["queries"]] == [
        "query:requirement:industry:primary:mechanism",
        "query:requirement:industry:primary:quantification",
        "query:requirement:industry:primary:counter_evidence",
        "query:requirement:industry:primary:primary_engineering",
    ]
    assert [query["priority"] for query in plan["queries"]] == [1, 2, 3, 4]
    assert plan["queries"][0]["query_text"] == (
        "high-layer PCB low-loss laminate What engineering constraints determine "
        "scale-up? mechanism engineering"
    )
    assert plan["queries"][1]["query_text"].endswith("capacity yield price data")
    assert plan["queries"][2]["query_text"].endswith(
        "alternative substitution limitation"
    )
    assert plan["queries"][3]["query_text"] == (
        "high-layer PCB low-loss laminate standard specification technical document"
    )
    for query in plan["queries"]:
        assert query["required_terms"] == ["high-layer PCB", "low-loss laminate"]
        assert query["excluded_terms"] == sorted(FORBIDDEN_INDUSTRY_SEARCH_TERMS)
        assert query["source_classes"] == [
            "technical_standard",
            "independent_secondary",
        ]
    assert plan["languages"] == ["zh-CN", "en"]
    assert plan["geography"] == ["CN", "global"]
    assert plan["publication_window"] == "within_12_months"
    assert plan["result_limit_per_query"] == 20
    assert plan["deduplication_policy"] == "normalized_url_then_content_hash"
    assert len(plan["stop_conditions"]) == 3
    assert all(plan["stop_conditions"])
    assert plan["status"] == "planned"
    assert plan["provenance"] is PROVENANCE
    assert set(plan) == {
        "search_plan_id",
        "project_id",
        "version_id",
        "evidence_channel",
        "requirement_ids",
        "queries",
        "languages",
        "geography",
        "publication_window",
        "result_limit_per_query",
        "deduplication_policy",
        "stop_conditions",
        "status",
        "provenance",
    }
    assert not ({"candidate_companies", "company", "stock_rating"} & set(plan))
    validate_v2_1_schema_payload(
        "search_plan_v2_1",
        {
            "schema_version": "2.1.0",
            "artifact_kind": "search_plan",
            "search_plan": plan,
        },
    )


def test_compile_is_deterministic_and_does_not_mutate_inputs():
    item = requirement()
    terms = [" high-layer PCB ", "low-loss laminate", "high-layer PCB"]
    original_item = deepcopy(item)
    original_terms = deepcopy(terms)

    first = compile_search_plan(
        item,
        project_id="research_project:pcb",
        version_id="research_version:pcb:0.1.0",
        domain_terms=terms,
    )
    second = compile_search_plan(
        item,
        project_id="research_project:pcb",
        version_id="research_version:pcb:0.1.0",
        domain_terms=terms,
    )

    assert first == second
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
        second, ensure_ascii=False, sort_keys=True
    )
    assert item == original_item
    assert terms == original_terms


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda item: item.pop("question_to_resolve"), "missing question_to_resolve"),
        (lambda item: item.update(question_to_resolve="  "), "blank question_to_resolve"),
        (
            lambda item: item.update(required_source_classes=[]),
            "empty required_source_classes",
        ),
        (
            lambda item: item.update(required_source_classes=["primary", " "]),
            "blank required_source_classes",
        ),
    ],
)
def test_compile_rejects_invalid_requirement_fields(mutation, reason):
    item = requirement()
    mutation(item)

    assert_invalid(
        lambda: compile_search_plan(
            item,
            project_id="research_project:pcb",
            version_id="research_version:pcb:0.1.0",
            domain_terms=["high-layer PCB"],
        ),
        reason=reason,
    )


@pytest.mark.parametrize(
    ("terms", "reason"),
    [([], "empty domain_terms"), (["  "], "blank domain_terms")],
)
def test_compile_rejects_empty_or_blank_domain_terms(terms, reason):
    assert_invalid(
        lambda: compile_search_plan(
            requirement(),
            project_id="research_project:pcb",
            version_id="research_version:pcb:0.1.0",
            domain_terms=terms,
        ),
        reason=reason,
    )


@pytest.mark.parametrize(
    "forbidden",
    [
        "目标价",
        "买入",
        "卖出",
        "股票推荐",
        "估值最低",
        "最强龙头",
        "TARGET PRICE",
        "Buy Rating",
        "sell rating",
        "top stock",
        "candidate companies",
        "company ranking",
        "上市公司排名",
        "受益标的",
    ],
)
@pytest.mark.parametrize("location", ["question", "domain_term"])
def test_compile_rejects_investment_and_company_ranking_terms(forbidden, location):
    item = requirement()
    terms = ["low-loss laminate"]
    if location == "question":
        item["question_to_resolve"] = f"Engineering review of {forbidden} candidates"
    else:
        terms.append(f"prefix-{forbidden}-suffix")

    assert_invalid(
        lambda: compile_search_plan(
            item,
            project_id="research_project:pcb",
            version_id="research_version:pcb:0.1.0",
            domain_terms=terms,
        ),
        reason="forbidden industry search term",
    )


def test_compile_does_not_false_positive_on_ordinary_engineering_terms():
    plan = compile_search_plan(
        requirement(question="How does sell-side copper roughness affect insertion loss?"),
        project_id="research_project:pcb",
        version_id="research_version:pcb:0.1.0",
        domain_terms=["buy-off engineering test", "target impedance"],
    )

    assert plan["status"] == "planned"


def test_validate_search_plans_allows_duplicate_coverage_and_single_primary_standard():
    item = requirement(source_classes=["primary_standard"])
    first = compile_search_plan(
        item,
        project_id="research_project:pcb",
        version_id="research_version:pcb:0.1.0",
        domain_terms=["low-loss laminate"],
    )
    second = deepcopy(first)
    second["search_plan_id"] += ":followup"
    for query in second["queries"]:
        query["query_id"] += ":followup"

    validate_search_plans([item], [first, second])


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (
            lambda requirements, plans: plans[0]["queries"].__setitem__(
                slice(None),
                [
                    query
                    for query in plans[0]["queries"]
                    if query["query_role"] != "counter_evidence"
                ],
            ),
            "missing counter_evidence query",
        ),
        (
            lambda requirements, plans: plans.append(deepcopy(plans[0])),
            "duplicate search_plan_id",
        ),
        (
            lambda requirements, plans: plans[0]["queries"][1].update(
                query_id=plans[0]["queries"][0]["query_id"]
            ),
            "duplicate query_id",
        ),
        (
            lambda requirements, plans: plans[0].update(
                requirement_ids=["requirement:unknown"]
            ),
            "unknown requirement_id",
        ),
        (
            lambda requirements, plans: plans.clear(),
            "uncovered requirement_id",
        ),
        (
            lambda requirements, plans: plans[0].update(status="draft"),
            "invalid status",
        ),
        (
            lambda requirements, plans: plans[0].update(evidence_channel="company"),
            "invalid evidence_channel",
        ),
        (
            lambda requirements, plans: plans[0]["queries"][0].update(query_text=" "),
            "blank query_text",
        ),
        (
            lambda requirements, plans: plans[0].update(candidate_companies=[]),
            "downstream field",
        ),
    ],
)
def test_validate_search_plans_rejects_invalid_semantics(mutate, reason):
    requirements = [requirement()]
    plans = [compiled_plan()]
    mutate(requirements, plans)

    assert_invalid(
        lambda: validate_search_plans(requirements, plans),
        reason=reason,
    )


def test_validate_search_plans_rejects_duplicate_requirement_ids():
    item = requirement()

    assert_invalid(
        lambda: validate_search_plans([item, deepcopy(item)], [compiled_plan()]),
        reason="duplicate requirement_id",
    )


def test_compile_and_validate_reject_nonstandard_single_source_class():
    item = requirement(source_classes=["primary"])

    assert_invalid(
        lambda: compile_search_plan(
            item,
            project_id="research_project:pcb",
            version_id="research_version:pcb:0.1.0",
            domain_terms=["low-loss laminate"],
        ),
        reason="insufficient source classes",
    )

    plan = compiled_plan()
    for query in plan["queries"]:
        query["source_classes"] = ["primary"]
    assert_invalid(
        lambda: validate_search_plans([item], [plan]),
        reason="insufficient source classes",
    )


def test_validate_search_plans_rejects_forbidden_generated_query_substrings():
    plan = compiled_plan()
    plan["queries"][0]["query_text"] = "engineering TARGET PRICE sensitivity"

    assert_invalid(
        lambda: validate_search_plans([requirement()], [plan]),
        reason="forbidden industry search term",
    )


def test_validate_search_plans_wraps_structural_errors_stably():
    plan = compiled_plan()
    del plan["queries"]

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_search_plans([requirement()], [plan])
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SEARCH_PLAN_INVALID"
    assert exc_info.value.details["reason"] == "invalid search plan structure"
    assert exc_info.value.details["plan_id"] == plan["search_plan_id"]


def test_compile_structural_error_locates_requirement():
    item = requirement()
    del item["provenance"]

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        compile_search_plan(
            item,
            project_id="research_project:pcb",
            version_id="research_version:pcb:0.1.0",
            domain_terms=["low-loss laminate"],
        )
    assert exc_info.value.details["reason"] == "invalid requirement structure"
    assert exc_info.value.details["requirement_id"] == item["requirement_id"]


def test_errors_locate_requirement_plan_and_query_objects():
    item = requirement(question=" ")
    with pytest.raises(ResearchProjectV2Error) as compile_exc:
        compile_search_plan(
            item,
            project_id="research_project:pcb",
            version_id="research_version:pcb:0.1.0",
            domain_terms=["low-loss laminate"],
        )
    assert compile_exc.value.details["requirement_id"] == item["requirement_id"]

    plan = compiled_plan()
    plan["queries"][0]["query_text"] = " "
    with pytest.raises(ResearchProjectV2Error) as validate_exc:
        validate_search_plans([requirement()], [plan])
    assert validate_exc.value.details["plan_id"] == plan["search_plan_id"]
    assert validate_exc.value.details["query_id"] == plan["queries"][0]["query_id"]


@pytest.mark.parametrize(
    "field",
    [
        "project_id",
        "version_id",
        "languages",
        "geography",
        "publication_window",
        "result_limit_per_query",
        "deduplication_policy",
        "stop_conditions",
        "provenance",
    ],
)
def test_validate_search_plans_reuses_schema_for_missing_plan_fields(field):
    plan = compiled_plan()
    del plan[field]

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_search_plans([requirement()], [plan])

    error = exc_info.value
    assert error.code == "RESEARCH_PROJECT_V2_1_SEARCH_PLAN_INVALID"
    assert error.details["reason"] == "invalid search plan structure"
    assert error.details["plan_id"] == plan["search_plan_id"]
    assert error.details["query_id"] is None
    assert error.details["field_path"] == [field]
    assert error.details["original_message"]
    assert error.__cause__.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"


@pytest.mark.parametrize("field", ["excluded_terms", "priority"])
def test_validate_search_plans_reuses_schema_for_missing_query_fields(field):
    plan = compiled_plan()
    query = plan["queries"][0]
    del query[field]

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_search_plans([requirement()], [plan])

    error = exc_info.value
    assert error.code == "RESEARCH_PROJECT_V2_1_SEARCH_PLAN_INVALID"
    assert error.details["plan_id"] == plan["search_plan_id"]
    assert error.details["query_id"] == query["query_id"]
    assert error.details["field_path"] == ["queries", 0, field]
    assert error.__cause__.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"


@pytest.mark.parametrize(
    ("mutation", "field_path", "query_index"),
    [
        (lambda plan: plan.update(languages="zh-CN"), ["languages"], None),
        (lambda plan: plan.update(unexpected="value"), ["unexpected"], None),
        (
            lambda plan: plan["queries"][0].update(priority="1"),
            ["queries", 0, "priority"],
            0,
        ),
        (
            lambda plan: plan["queries"][0].update(unexpected="value"),
            ["queries", 0, "unexpected"],
            0,
        ),
    ],
)
def test_validate_search_plans_reuses_schema_for_types_and_extra_fields(
    mutation, field_path, query_index
):
    plan = compiled_plan()
    mutation(plan)

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_search_plans([requirement()], [plan])

    error = exc_info.value
    assert error.code == "RESEARCH_PROJECT_V2_1_SEARCH_PLAN_INVALID"
    assert error.details["plan_id"] == plan["search_plan_id"]
    expected_query_id = (
        plan["queries"][query_index]["query_id"]
        if query_index is not None
        else None
    )
    assert error.details["query_id"] == expected_query_id
    assert error.details["field_path"] == field_path
    assert error.__cause__.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"


def test_validate_search_plans_does_not_mask_schema_registry_errors(monkeypatch):
    registry_error = ResearchProjectV2Error(
        "registry unavailable",
        code="RESEARCH_PROJECT_V2_1_SCHEMA_NOT_FOUND",
        details={"schema": "search_plan_v2_1"},
    )

    def fail_registry(schema_name, payload):
        raise registry_error

    monkeypatch.setattr(
        search_plan_module,
        "validate_v2_1_schema_payload",
        fail_registry,
        raising=False,
    )

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_search_plans([requirement()], [compiled_plan()])

    assert exc_info.value is registry_error
