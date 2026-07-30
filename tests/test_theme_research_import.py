from __future__ import annotations

import copy
from dataclasses import replace
import json
from pathlib import Path
import shutil

import pytest

from stock_research import theme_research_import as import_module
from stock_research.theme_research_db_models import ThemeResearchDomainError
from stock_research.theme_research_import import (
    NormalizedThemeResearchPackage,
    normalize_artifact_package,
    semantic_diff,
    validate_package_integrity,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


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


def test_normalized_theme_metadata_preserves_v1_6_research_profile(tmp_path) -> None:
    artifact_dir = tmp_path / "theme_decomposition"
    mapping_dir = artifact_dir / "company_mappings"
    artifact_dir.mkdir()
    shutil.copytree(
        REPO_ROOT / "artifacts" / "theme_decomposition" / "company_mappings",
        mapping_dir,
    )
    source_dir = REPO_ROOT / "artifacts" / "theme_decomposition"
    expected_profile = None
    for source_path in source_dir.glob("*.json"):
        artifact = json.loads(source_path.read_text(encoding="utf-8"))
        artifact["artifact_version"] = "theme_decomposition_v1_6"
        if artifact["theme"]["theme_id"] == "ai_power_value_capture_v1":
            claim_ids = [row["claim_id"] for row in artifact["claims"]]
            expected_profile = {
                "catalog_chain_id": "ai_power",
                "research_kind": "industry_chain_deep_research",
                "industry_stage": "commercial_scaling",
                "central_conflict": "Power density and grid capacity constrain AI deployment.",
                "investment_summary": "Value capture spans equipment and integration.",
                "value_flow_summary": "grid -> transformer -> UPS -> server power -> compute",
                "profit_pool_summary": "Qualification and integration drive durable economics.",
                "catalyst_claim_ids": [claim_ids[0]],
                "risk_claim_ids": [claim_ids[1]],
                "validation_signals": ["power density", "delivery lead time"],
                "evidence_gap_summary": "Company revenue attribution remains incomplete.",
            }
            artifact["research_profile"] = expected_profile
        (artifact_dir / source_path.name).write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    package = normalize_artifact_package(
        theme_artifact_dir=artifact_dir,
        company_mapping_dir=mapping_dir,
    )
    normalized = next(
        row for row in package.themes if row["theme_id"] == "ai_power_value_capture_v1"
    )

    assert expected_profile is not None
    assert normalized["artifact_metadata"]["research_profile"] == expected_profile


def test_source_url_identity_normalizes_case_fragment_and_trailing_slash() -> None:
    assert import_module._normalize_source_url(
        "HTTPS://Example.COM/reports/annual.pdf/#page=12"
    ) == "https://example.com/reports/annual.pdf"


def test_source_identity_validation_rejects_duplicate_url_within_theme() -> None:
    with pytest.raises(ThemeResearchDomainError) as exc_info:
        import_module._validate_theme_source_identities(
            artifact_by_theme_id={
                "theme-a": {
                    "sources": [
                        {
                            "source_id": "canonical-source",
                            "url_or_ref": "HTTPS://Example.COM/report.pdf/",
                        }
                    ]
                }
            },
            mapping_package={
                "artifacts": [
                    {
                        "theme_id": "theme-a",
                        "sources": [
                            {
                                "source_id": "mapping-source",
                                "url_or_ref": "https://example.com/report.pdf#page=2",
                            }
                        ],
                        "company_mappings": [],
                    }
                ]
            },
        )

    assert exc_info.value.code == "THEME_RESEARCH_DUPLICATE_SOURCE_IDENTITY"
    assert exc_info.value.details == {
        "theme_id": "theme-a",
        "url": "https://example.com/report.pdf",
        "source_ids": ["canonical-source", "mapping-source"],
    }


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


def test_package_integrity_detects_mutation_after_hashing() -> None:
    package = normalize_artifact_package()
    package.nodes[0]["description"] = "mutated after hashing"

    with pytest.raises(ThemeResearchDomainError) as exc_info:
        validate_package_integrity(package)

    assert exc_info.value.code == "THEME_RESEARCH_PACKAGE_HASH_MISMATCH"
