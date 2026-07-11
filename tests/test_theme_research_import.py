from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from stock_research.theme_research_db_models import ThemeResearchDomainError
from stock_research.theme_research_import import (
    NormalizedThemeResearchPackage,
    normalize_artifact_package,
    semantic_diff,
)


def test_normalize_current_artifacts_to_relational_rows() -> None:
    package = normalize_artifact_package()

    assert len(package.themes) == 2
    assert len(package.nodes) == 34
    assert package.sources
    assert package.claims
    assert package.assessments
    assert package.company_mappings
    assert package.mapping_evidence_items
    assert package.package_sha256
    assert all(row["theme_id"] for row in package.theme_sources)
    assert all(row["claim_id"] and row["node_id"] for row in package.claim_nodes)
    assert all(row["assessment_id"] for row in package.assessment_evidence)
    assert all(row["mapping_id"] for row in package.company_mapping_evidence)


def test_normalization_is_deterministic() -> None:
    first = normalize_artifact_package()
    second = normalize_artifact_package()

    assert first == second
    assert first.package_sha256 == second.package_sha256


def test_semantic_diff_is_order_independent() -> None:
    left = normalize_artifact_package()
    right = replace(
        left,
        nodes=tuple(reversed(left.nodes)),
        sources=tuple(reversed(left.sources)),
        claim_nodes=tuple(reversed(left.claim_nodes)),
    )

    diff = semantic_diff(left, right)

    assert diff["has_changes"] is False
    assert diff["summary"]["insert"] == 0
    assert diff["summary"]["update"] == 0
    assert diff["summary"]["deactivate"] == 0


def test_semantic_diff_reports_insert_update_and_deactivate() -> None:
    left = normalize_artifact_package()
    changed_node = copy.deepcopy(left.nodes[0])
    changed_node["description"] = "changed"
    inserted_node = copy.deepcopy(left.nodes[0])
    inserted_node["node_id"] = "new-node"
    right = replace(
        left,
        nodes=tuple([changed_node, *left.nodes[1:-1], inserted_node]),
    )

    diff = semantic_diff(left, right)

    assert diff["has_changes"] is True
    assert diff["families"]["nodes"]["update"] == [left.nodes[0]["node_id"]]
    assert diff["families"]["nodes"]["insert"] == ["new-node"]
    assert diff["families"]["nodes"]["deactivate"] == [left.nodes[-1]["node_id"]]


def test_package_rejects_duplicate_ids() -> None:
    package = normalize_artifact_package()

    with pytest.raises(ThemeResearchDomainError) as exc_info:
        NormalizedThemeResearchPackage.build(
            artifact_version=package.artifact_version,
            themes=package.themes,
            nodes=(*package.nodes, package.nodes[0]),
            sources=package.sources,
            theme_sources=package.theme_sources,
            claims=package.claims,
            claim_sources=package.claim_sources,
            claim_nodes=package.claim_nodes,
            assessments=package.assessments,
            assessment_evidence=package.assessment_evidence,
            company_mappings=package.company_mappings,
            mapping_evidence_items=package.mapping_evidence_items,
            company_mapping_evidence=package.company_mapping_evidence,
        )

    assert exc_info.value.code == "THEME_RESEARCH_DUPLICATE_ID"


def test_package_rejects_orphan_relationships() -> None:
    package = normalize_artifact_package()
    orphan = {"claim_id": package.claims[0]["claim_id"], "node_id": "missing-node"}

    with pytest.raises(ThemeResearchDomainError) as exc_info:
        NormalizedThemeResearchPackage.build(
            artifact_version=package.artifact_version,
            themes=package.themes,
            nodes=package.nodes,
            sources=package.sources,
            theme_sources=package.theme_sources,
            claims=package.claims,
            claim_sources=package.claim_sources,
            claim_nodes=(*package.claim_nodes, orphan),
            assessments=package.assessments,
            assessment_evidence=package.assessment_evidence,
            company_mappings=package.company_mappings,
            mapping_evidence_items=package.mapping_evidence_items,
            company_mapping_evidence=package.company_mapping_evidence,
        )

    assert exc_info.value.code == "THEME_RESEARCH_ORPHAN_RELATIONSHIP"
