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
