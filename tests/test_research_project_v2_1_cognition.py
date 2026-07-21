from __future__ import annotations

from copy import deepcopy

import pytest

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload


PROVENANCE = {
    "created_by": "Codex",
    "actor_type": "codex",
    "agent_run_id": "cognition-test",
    "created_at": "2026-07-21T00:00:00Z",
    "created_in_version": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
    "review_status": "reviewed",
}


def minimal_package() -> dict:
    return {
        "schema_version": "2.5.0",
        "artifact_type": "industry_cognition_package",
        "package_id": "industry_cognition_package:ai_pcb:v1",
        "project_id": "research_project:ai_compute_pcb_industry_bottleneck",
        "renderer_version": "industry_cognition_markdown_v1",
        "baseline_bindings": {},
        "research_framing": {},
        "research_question_tree": [],
        "evidence_inventory": {},
        "er_assessments": [],
        "claim_assessment_ledger": [],
        "grounded_system_model": {"nodes": [], "edges": []},
        "unverified_system_extensions": [],
        "evidence_grounded_mechanisms": [],
        "unverified_mechanism_skeletons": [],
        "grounded_causal_edges": [],
        "hypothesized_causal_edges": [],
        "technology_route_comparisons": [],
        "limited_system_bottleneck_judgments": [],
        "value_change_hypotheses": [],
        "contradictions_and_uncertainties": [],
        "evidence_gap_referrals": [],
        "verification_and_falsification": [],
        "provenance": PROVENANCE,
        "content_hash": "0" * 64,
    }


def minimal_audit() -> dict:
    return {
        "schema_version": "2.5.0",
        "artifact_type": "industry_cognition_audit",
        "audit_id": "industry_cognition_audit:ai_pcb:v1",
        "package_id": "industry_cognition_package:ai_pcb:v1",
        "package_content_hash": "a" * 64,
        "report_content_hash": "b" * 64,
        "renderer_version": "industry_cognition_markdown_v1",
        "capability_rule_version": "industry_cognition_capability_v1",
        "domain_matrix_version": "industry_cognition_domains_v1",
        "audit_question_set_version": "industry_cognition_audit_questions_v1",
        "domain_coverage": [],
        "computed_capability": {},
        "coverage_metrics": {},
        "audit_answers": [],
        "violations": [],
        "warnings": [],
        "content_hash": "0" * 64,
    }


def test_schema_v2_5_accepts_package_and_rejects_capability_fields() -> None:
    package = minimal_package()
    validate_v2_1_schema_payload("industry_cognition_baseline_v2_5", package)
    package["overall_capability"] = "complete"
    with pytest.raises(ResearchProjectV2Error):
        validate_v2_1_schema_payload("industry_cognition_baseline_v2_5", package)


def test_schema_v2_5_accepts_audit_and_rejects_cognition_objects() -> None:
    audit = minimal_audit()
    validate_v2_1_schema_payload("industry_cognition_baseline_v2_5", audit)
    audit["claim_assessment_ledger"] = []
    with pytest.raises(ResearchProjectV2Error):
        validate_v2_1_schema_payload("industry_cognition_baseline_v2_5", audit)


@pytest.mark.parametrize("artifact_type", ["package", "audit", "report"])
def test_schema_v2_5_rejects_unknown_discriminator(artifact_type: str) -> None:
    payload = deepcopy(minimal_package())
    payload["artifact_type"] = artifact_type
    with pytest.raises(ResearchProjectV2Error):
        validate_v2_1_schema_payload("industry_cognition_baseline_v2_5", payload)
