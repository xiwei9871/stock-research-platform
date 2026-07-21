from __future__ import annotations

from copy import deepcopy

import pytest

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload


PROVENANCE = {
    "created_by": "Codex",
    "actor_type": "codex",
    "agent_run_id": "gap-review-test",
    "created_at": "2026-07-21T00:00:00Z",
    "created_in_version": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
    "review_status": "unreviewed",
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
