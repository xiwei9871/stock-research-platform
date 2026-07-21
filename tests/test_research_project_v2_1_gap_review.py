from __future__ import annotations

from copy import deepcopy

import pytest

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.gap_review import (
    validate_gap_universe,
    validate_input_bindings,
)
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload


PROVENANCE = {
    "created_by": "Codex",
    "actor_type": "codex",
    "agent_run_id": "gap-review-test",
    "created_at": "2026-07-21T00:00:00Z",
    "created_in_version": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
    "review_status": "unreviewed",
}
EXPECTED_GROUPS = {
    "GAP-SIGNAL": "group_a_signal_transmission",
    "GAP-LOSS": "group_a_signal_transmission",
    "GAP-LAYERS": "group_a_signal_transmission",
    "GAP-LAMINATE": "group_b_material_capability",
    "GAP-BACKDRILL": "group_c_manufacturing_testing",
    "GAP-LAMINATION": "group_c_manufacturing_testing",
    "GAP-THERMAL": "group_c_manufacturing_testing",
    "GAP-TEST": "group_c_manufacturing_testing",
    "GAP-YIELD": "group_c_manufacturing_testing",
    "GAP-CAPACITY": "group_d_bottleneck_effective_capacity",
}


def minimal_gap_review() -> dict:
    return {
        "schema_version": "2.6.0",
        "artifact_type": "evidence_gap_review_and_targeted_research_design",
        "review_id": "evidence_gap_review:ai_pcb:v1",
        "project_id": "research_project:ai_compute_pcb_industry_bottleneck",
        "input_bindings": {},
        "execution_policy": {
            "execution_mode": "offline_read_only_research_design",
            "network_access": False,
            "new_acquisition": False,
            "evidence_assessment_of_new_sources": False,
            "framework_expansion": False,
        },
        "group_definitions": [],
        "gap_reviews": [],
        "evidence_requirements": [],
        "source_class_boundaries": [],
        "cross_level_inference_rules": [],
        "stopping_state_definitions": [],
        "governance": {
            "future_acquisition_authorized": False,
            "stage_a2_authorized": False,
            "stage_b_authorized": False,
            "company_mapping_authorized": False,
            "bottleneck_judgment_authorized": False,
            "value_migration_judgment_authorized": False,
        },
        "provenance": PROVENANCE,
        "content_hash": "0" * 64,
    }


def test_schema_v2_6_accepts_gap_review_artifact() -> None:
    validate_v2_1_schema_payload("evidence_gap_review_v2_6", minimal_gap_review())


def test_schema_v2_6_rejects_enabled_authorization() -> None:
    artifact = deepcopy(minimal_gap_review())
    artifact["governance"]["future_acquisition_authorized"] = True
    with pytest.raises(ResearchProjectV2Error):
        validate_v2_1_schema_payload("evidence_gap_review_v2_6", artifact)


def test_schema_v2_6_rejects_unknown_top_level_field() -> None:
    artifact = deepcopy(minimal_gap_review())
    artifact["company_candidates"] = []
    with pytest.raises(ResearchProjectV2Error):
        validate_v2_1_schema_payload("evidence_gap_review_v2_6", artifact)


def valid_gap_rows() -> list[dict]:
    return [
        {"gap_id": gap_id, "gap_group": gap_group}
        for gap_id, gap_group in EXPECTED_GROUPS.items()
    ]


def test_gap_universe_requires_exact_ten_upstream_gaps() -> None:
    assert validate_gap_universe(valid_gap_rows(), EXPECTED_GROUPS) == sorted(
        EXPECTED_GROUPS
    )


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown", "wrong_group"])
def test_gap_universe_rejects_drift(mutation: str) -> None:
    rows = valid_gap_rows()
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows[-1] = deepcopy(rows[0])
    elif mutation == "unknown":
        rows[-1]["gap_id"] = "GAP-UNKNOWN"
    else:
        rows[0]["gap_group"] = "group_d_bottleneck_effective_capacity"
    with pytest.raises(ResearchProjectV2Error):
        validate_gap_universe(rows, EXPECTED_GROUPS)


def test_input_binding_rejects_cognition_package_hash_drift() -> None:
    artifact = minimal_gap_review()
    artifact["input_bindings"] = {
        "cognition_package_path": "analysis/ai_pcb_industry_cognition_package_v1.json",
        "cognition_package_hash": "0" * 64,
        "cognition_audit_path": "analysis/ai_pcb_industry_cognition_audit_v1.json",
        "cognition_audit_hash": "b2bade2473e8016f1f06b7d8b40cbe40c5bae60b2d8f1b685312ddbf83e717c9",
        "cognition_report_path": "reports/ai_pcb_industry_cognition_report_v1.md",
        "cognition_report_hash": "8770304b84ce5815071da52a47cd8d2da7f5ab70c70d350dde7a704eb98fabad",
        "acquisition_checkpoint_id": "acquisition_checkpoint:a5f7627d8726c9405ba67a75",
        "acquisition_checkpoint_hash": "a5f7627d8726c9405ba67a7527826edb0cff26ee777287e33cb55442bace660e",
    }
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_input_bindings(artifact, layout=LayeredResearchLayout.default())
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_GAP_REVIEW_UPSTREAM_DRIFT"
