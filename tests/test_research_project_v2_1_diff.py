from __future__ import annotations

from copy import deepcopy

import pytest

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.diff import diff_industry_versions


BASE_FAMILIES = {
    "questions": [],
    "question_tree_nodes": [],
    "claims": [],
    "claim_relations": [],
    "evidence_requirements": [],
    "references": [],
    "evidence_assessments": [],
    "causal_nodes": [],
    "causal_edges": [],
    "validation_metrics": [],
    "invalidation_conditions": [],
    "search_plans": [],
    "source_candidates": [],
    "source_relationships": [],
    "evidence_artifacts": [],
    "normalized_documents": [],
    "industry_evidence_assessments": [],
    "conflict_summaries": [],
}


def _version(version: str, parent: str | None) -> dict:
    return {
        "project_id": "research_project:fixture",
        "version_id": f"research_version:fixture:{version}",
        "semantic_version": version,
        "parent_version_id": parent,
        "content_hash": version.replace(".", "") * 21 + "0",
        "snapshot": deepcopy(BASE_FAMILIES),
    }


def test_diff_adds_all_r2b_object_families_from_v2_1_parent() -> None:
    before = _version("0.1.0", None)
    after = _version("0.2.0", before["version_id"])
    after["snapshot"].update(
        {
            "industry_model_nodes": [
                {"industry_model_node_id": "industry_node:fixture:one"}
            ],
            "industry_model_edges": [
                {"industry_model_edge_id": "industry_edge:fixture:one"}
            ],
            "bottleneck_hypotheses": [
                {
                    "bottleneck_hypothesis_id": "bottleneck_hypothesis:fixture:one",
                    "status": "proposed",
                    "research_disposition": "unchanged",
                    "lifecycle_status": "active",
                }
            ],
            "value_migration_analyses": [
                {
                    "value_migration_analysis_id": "value_migration:fixture:one",
                    "status": "proposed",
                    "lifecycle_status": "active",
                }
            ],
            "bottleneck_readiness_reviews": [],
        }
    )

    result = diff_industry_versions(before, after)

    assert result["changes"]["industry_model_nodes"]["added"] == [
        "industry_node:fixture:one"
    ]
    assert result["changes"]["bottleneck_hypotheses"]["added"] == [
        "bottleneck_hypothesis:fixture:one"
    ]


def test_diff_classifies_bottleneck_status_and_disposition_changes() -> None:
    before = _version("0.2.0", "research_version:fixture:0.1.0")
    before["snapshot"]["bottleneck_hypotheses"] = [
        {
            "bottleneck_hypothesis_id": "bottleneck_hypothesis:fixture:one",
            "status": "proposed",
            "research_disposition": "unchanged",
            "lifecycle_status": "active",
        }
    ]
    after = deepcopy(before)
    after.update(
        {
            "version_id": "research_version:fixture:0.2.1",
            "semantic_version": "0.2.1",
            "parent_version_id": before["version_id"],
        }
    )
    after["snapshot"]["bottleneck_hypotheses"][0]["status"] = "under_investigation"

    result = diff_industry_versions(before, after)

    assert result["changes"]["bottleneck_hypotheses"]["status_changed"] == [
        "bottleneck_hypothesis:fixture:one"
    ]


def test_diff_requires_direct_ancestry_and_does_not_mutate_inputs() -> None:
    before = _version("0.1.0", None)
    after = _version("0.2.0", "research_version:fixture:other")
    original_before = deepcopy(before)
    original_after = deepcopy(after)

    with pytest.raises(ResearchProjectV2Error):
        diff_industry_versions(before, after)

    assert before == original_before
    assert after == original_after
