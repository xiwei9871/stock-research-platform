from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json

import pytest

from stock_research.research_project_v2_1.gates import (
    INDUSTRY_DESIGN_CHECKS,
    evaluate_industry_design_gate,
)


EXPECTED_CHECKS = (
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

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "artifacts/research_projects/v2_1/projects/ai_compute_pcb_industry_bottleneck"


def _pilot() -> tuple[dict, dict]:
    return (
        json.loads((PROJECT / "project.json").read_text()),
        json.loads((PROJECT / "versions/v0.1.0.json").read_text()),
    )


def _failed_checks(identity: dict, version: dict) -> set[str]:
    result = evaluate_industry_design_gate(identity, version)
    return {check["code"] for check in result["checks"] if check["status"] == "fail"}


def test_industry_gate_exports_fixed_check_order() -> None:
    assert INDUSTRY_DESIGN_CHECKS == EXPECTED_CHECKS


def test_industry_gate_does_not_mutate_input(monkeypatch) -> None:
    version = {"snapshot": {}}
    identity = {}
    before = deepcopy((identity, version))
    monkeypatch.setattr(
        "stock_research.research_project_v2_1.gates.resolve_upstream_r1_version",
        lambda reference: {},
    )
    evaluate_industry_design_gate(identity, version)
    assert (identity, version) == before


def test_pilot_passes_all_twelve_checks() -> None:
    identity, version = _pilot()
    result = evaluate_industry_design_gate(identity, version)
    assert result["status"] == "pass"
    assert [check["code"] for check in result["checks"]] == list(EXPECTED_CHECKS)
    assert {check["status"] for check in result["checks"]} == {"pass"}


@pytest.mark.parametrize(
    ("mutation", "expected_check"),
    [
        (lambda identity, version: identity.update(research_layer="company_capture"), "INDUSTRY_LAYER_CORRECT"),
        (lambda identity, version: version["snapshot"].update(upstream_research_refs=[]), "INDUSTRY_UPSTREAM_BASELINE_RESOLVED"),
        (lambda identity, version: version["snapshot"]["search_plans"][0]["queries"].pop(2), "INDUSTRY_COUNTER_SEARCH_PRESENT"),
        (lambda identity, version: version["snapshot"]["search_plans"][0]["queries"][0].update(query_text="industry target price"), "INDUSTRY_SEARCH_PLANS_COVER_REQUIREMENTS"),
        (lambda identity, version: version["snapshot"].update(company_capability_collection=[]), "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS"),
    ],
)
def test_industry_gate_reports_the_targeted_failure(mutation, expected_check) -> None:
    identity, version = _pilot()
    mutation(identity, version)
    result = evaluate_industry_design_gate(identity, version)
    failed = {check["code"] for check in result["checks"] if check["status"] == "fail"}
    assert expected_check in failed


def test_missing_counter_does_not_cascade_into_plan_coverage() -> None:
    identity, version = _pilot()
    version["snapshot"]["search_plans"][0]["queries"] = [
        query for query in version["snapshot"]["search_plans"][0]["queries"]
        if query["query_role"] != "counter_evidence"
    ]
    result = evaluate_industry_design_gate(identity, version)
    failed = {check["code"] for check in result["checks"] if check["status"] == "fail"}
    assert failed == {"INDUSTRY_COUNTER_SEARCH_PRESENT"}


@pytest.mark.parametrize(
    "forbidden_key",
    ["stock_recommendations", "company_rankings", "company_output_collection", "listed_company_candidates"],
)
def test_output_gate_rejects_downstream_key_variants(forbidden_key: str) -> None:
    identity, version = _pilot()
    version["snapshot"][forbidden_key] = []
    result = evaluate_industry_design_gate(identity, version)
    failed = {check["code"] for check in result["checks"] if check["status"] == "fail"}
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in failed


def test_output_gate_allows_company_background_reference_metadata() -> None:
    identity, version = _pilot()
    version["snapshot"]["listed_company_reference"] = {"role": "background"}
    result = evaluate_industry_design_gate(identity, version)
    failed = {check["code"] for check in result["checks"] if check["status"] == "fail"}
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" not in failed


def test_source_diversity_checks_each_query_source_contract() -> None:
    identity, version = _pilot()
    version["snapshot"]["search_plans"][0]["queries"][0]["source_classes"].pop()
    result = evaluate_industry_design_gate(identity, version)
    failed = {check["code"] for check in result["checks"] if check["status"] == "fail"}
    assert failed == {"INDUSTRY_SOURCE_CLASS_DIVERSITY"}


def test_initial_design_provenance_must_bind_to_current_version() -> None:
    identity, version = _pilot()
    question = version["snapshot"]["questions"][0]
    question["provenance"]["created_in_version"] = "research_version:other:0.1.0"

    result = evaluate_industry_design_gate(identity, version)
    failed = [check for check in result["checks"] if check["status"] == "fail"]

    assert [check["code"] for check in failed] == ["INDUSTRY_PROVENANCE_COMPLETE"]
    assert question["question_id"] in failed[0]["details"]["mismatched_object_ids"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda snapshot, claim: claim.update(validation_metric_ids=[]),
        lambda snapshot, claim: claim.update(validation_metric_ids=claim["validation_metric_ids"] * 2),
        lambda snapshot, claim: claim.update(validation_metric_ids=["metric:missing"]),
        lambda snapshot, claim: snapshot["validation_metrics"][0].update(target_id="claim:other"),
        lambda snapshot, claim: snapshot["validation_metrics"][0].update(status="complete"),
        lambda snapshot, claim: (
            claim.update(validation_metric_ids=[]),
            snapshot["validation_metrics"].append(
                {
                    **deepcopy(snapshot["validation_metrics"][0]),
                    "metric_id": "metric:unlinked:stray",
                    "target_id": claim["claim_id"],
                }
            ),
        ),
    ],
)
def test_validation_plan_follows_critical_claim_metric_links(mutation) -> None:
    identity, version = _pilot()
    snapshot = version["snapshot"]
    critical = next(claim for claim in snapshot["claims"] if claim["claim_kind"] == "primary")
    mutation(snapshot, critical)
    assert _failed_checks(identity, version) == {"INDUSTRY_VALIDATION_PLAN_PRESENT"}


@pytest.mark.parametrize(
    "mutation",
    [
        lambda snapshot, claim: claim.update(invalidation_condition_ids=[]),
        lambda snapshot, claim: claim.update(
            invalidation_condition_ids=claim["invalidation_condition_ids"] * 2
        ),
        lambda snapshot, claim: claim.update(invalidation_condition_ids=["condition:missing"]),
        lambda snapshot, claim: snapshot["invalidation_conditions"][0].update(
            target_type="research_question"
        ),
        lambda snapshot, claim: snapshot["invalidation_conditions"][0].update(status="triggered"),
    ],
)
def test_invalidation_plan_follows_critical_claim_condition_links(mutation) -> None:
    identity, version = _pilot()
    snapshot = version["snapshot"]
    critical = next(claim for claim in snapshot["claims"] if claim["claim_kind"] == "primary")
    mutation(snapshot, critical)
    assert _failed_checks(identity, version) == {"INDUSTRY_INVALIDATION_PLAN_PRESENT"}


def test_critical_claim_requires_a_direct_evidence_requirement() -> None:
    identity, version = _pilot()
    snapshot = version["snapshot"]
    critical_id = next(
        claim["claim_id"] for claim in snapshot["claims"] if claim["claim_kind"] == "primary"
    )
    removed_ids = {
        requirement["requirement_id"]
        for requirement in snapshot["evidence_requirements"]
        if requirement["target_type"] == "research_claim" and requirement["target_id"] == critical_id
    }
    snapshot["evidence_requirements"] = [
        requirement for requirement in snapshot["evidence_requirements"]
        if requirement["requirement_id"] not in removed_ids
    ]
    snapshot["search_plans"] = [
        plan for plan in snapshot["search_plans"]
        if not removed_ids.intersection(plan["requirement_ids"])
    ]
    assert _failed_checks(identity, version) == {"INDUSTRY_REQUIRED_QUESTIONS_COVERED"}


def test_critical_claim_requirement_must_be_covered_by_a_search_plan() -> None:
    identity, version = _pilot()
    snapshot = version["snapshot"]
    claim_requirement_ids = {
        requirement["requirement_id"]
        for requirement in snapshot["evidence_requirements"]
        if requirement["target_type"] == "research_claim"
    }
    snapshot["search_plans"] = [
        plan for plan in snapshot["search_plans"]
        if not claim_requirement_ids.intersection(plan["requirement_ids"])
    ]
    assert _failed_checks(identity, version) == {"INDUSTRY_SEARCH_PLANS_COVER_REQUIREMENTS"}


def test_missing_counter_and_uncovered_requirement_fail_independent_checks() -> None:
    identity, version = _pilot()
    plans = version["snapshot"]["search_plans"]
    plans[0]["queries"] = [
        query for query in plans[0]["queries"] if query["query_role"] != "counter_evidence"
    ]
    plans.pop(1)
    assert _failed_checks(identity, version) == {
        "INDUSTRY_SEARCH_PLANS_COVER_REQUIREMENTS",
        "INDUSTRY_COUNTER_SEARCH_PRESENT",
    }


def test_source_mismatch_and_uncovered_requirement_fail_independent_checks() -> None:
    identity, version = _pilot()
    plans = version["snapshot"]["search_plans"]
    for query in plans[0]["queries"]:
        query["source_classes"].pop()
    plans.pop(1)
    assert _failed_checks(identity, version) == {
        "INDUSTRY_SEARCH_PLANS_COVER_REQUIREMENTS",
        "INDUSTRY_SOURCE_CLASS_DIVERSITY",
    }


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "companyCapabilityCollection",
        "company_profiles",
        "stock_screen",
        "background_company_ratings",
    ],
)
def test_downstream_taxonomy_rejects_company_and_stock_output_keys(forbidden_key: str) -> None:
    identity, version = _pilot()
    version["snapshot"][forbidden_key] = []
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in _failed_checks(identity, version)


def test_downstream_taxonomy_rejects_nested_camel_case_stock_recommendations() -> None:
    identity, version = _pilot()
    version["snapshot"]["nested"] = [{"stockRecommendations": []}]
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in _failed_checks(identity, version)


def test_downstream_taxonomy_rejects_non_background_company_metadata() -> None:
    identity, version = _pilot()
    version["snapshot"]["company_notes"] = []
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in _failed_checks(identity, version)


@pytest.mark.parametrize(
    "background_key",
    ["background_company_references", "engineering_company_case_reference"],
)
def test_downstream_taxonomy_allows_background_company_reference_keys(background_key: str) -> None:
    identity, version = _pilot()
    version["snapshot"][background_key] = {"role": "background"}
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" not in _failed_checks(identity, version)


def test_downstream_taxonomy_propagates_background_context_to_non_output_metadata() -> None:
    identity, version = _pilot()
    version["snapshot"]["background_company_references"] = [
        {"company_name": "Example Co", "source_url": "https://example.com"}
    ]
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" not in _failed_checks(identity, version)


def test_downstream_taxonomy_does_not_hide_outputs_inside_background_context() -> None:
    identity, version = _pilot()
    version["snapshot"]["background_company_references"] = [
        {"company_profile": {"rating": "A"}}
    ]
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in _failed_checks(identity, version)


@pytest.mark.parametrize("output_key", ["rating", "profile"])
def test_downstream_taxonomy_applies_background_company_subject_to_direct_outputs(
    output_key: str,
) -> None:
    identity, version = _pilot()
    version["snapshot"]["background_company_references"] = [{output_key: {}}]
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in _failed_checks(identity, version)


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "公司评级",
        "个股推荐",
        "股票推荐",
        "股票评级",
        "发行人排名",
        "证券推荐",
        "issuer_rankings",
        "share_recommendations",
        "ｃｏｍｐａｎｙ＿ｒａｔｉｎｇ",
    ],
)
def test_downstream_taxonomy_rejects_nfkc_alias_and_chinese_outputs(
    forbidden_key: str,
) -> None:
    identity, version = _pilot()
    version["snapshot"][forbidden_key] = []
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in _failed_checks(identity, version)


@pytest.mark.parametrize(
    "allowed_key",
    [
        "listed_company_count",
        "company_policy",
        "company_employment_total",
        "stock_exchange_code",
        "background_company_notes",
    ],
)
def test_downstream_taxonomy_allows_statistics_policy_and_background_notes(
    allowed_key: str,
) -> None:
    identity, version = _pilot()
    version["snapshot"][allowed_key] = 1
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" not in _failed_checks(identity, version)


def test_downstream_taxonomy_rejects_stock_notes_only_outside_background() -> None:
    identity, version = _pilot()
    version["snapshot"]["stock_notes"] = []
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" in _failed_checks(identity, version)

    identity, version = _pilot()
    version["snapshot"]["background_stock_notes"] = []
    assert "INDUSTRY_NO_COMPANY_OR_STOCK_OUTPUTS" not in _failed_checks(identity, version)
