from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from stock_research import theme_research_import as import_module
from stock_research.theme_company_mapping import load_theme_company_mapping_package
from stock_research.theme_decomposition import load_theme_package
from stock_research.theme_research_db_models import ThemeResearchDomainError
from stock_research.theme_research_import import (
    NormalizedThemeResearchPackage,
    normalize_artifact_package,
    semantic_diff,
    validate_package_integrity,
)


def test_normalize_current_artifacts_to_relational_rows() -> None:
    package = normalize_artifact_package()

    artifact_package = load_theme_package()
    assert len(package.themes) == len(artifact_package["themes"])
    assert len(package.nodes) == len(artifact_package["nodes"])
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


def test_normalize_current_artifacts_reuses_notes_only_duplicate_sources() -> None:
    artifact_package = load_theme_package()
    package = normalize_artifact_package()
    normalized_by_id = {row["source_id"]: row for row in package.sources}
    artifact_by_id = {row["source_id"]: row for row in artifact_package["sources"]}

    for source_id in ("power_688396_2025_report", "semimat_688019_2025_report"):
        normalized = normalized_by_id[source_id]
        artifact = artifact_by_id[source_id]
        assert normalized["notes"] == artifact["notes"]
        assert normalized["content_sha256"] == import_module._content_sha256(artifact)


def test_normalize_artifacts_rejects_duplicate_source_core_field_conflict(
    monkeypatch,
) -> None:
    theme_package = load_theme_package()
    mapping_package = load_theme_company_mapping_package(
        None,
        theme_package["artifact_dir"],
    )
    theme_sources = {row["source_id"]: row for row in theme_package["sources"]}
    mapping_package = copy.deepcopy(mapping_package)
    for row in mapping_package["sources"]:
        if row["source_id"] in theme_sources:
            row["notes"] = theme_sources[row["source_id"]]["notes"]
    target = next(
        row
        for row in mapping_package["sources"]
        if row["source_id"] == "power_688396_2025_report"
    )
    target["publisher"] = "conflicting publisher"
    monkeypatch.setattr(import_module, "load_theme_package", lambda _path: theme_package)
    monkeypatch.setattr(
        import_module,
        "load_theme_company_mapping_package",
        lambda _mapping_dir, _theme_dir: mapping_package,
    )

    with pytest.raises(ThemeResearchDomainError) as exc_info:
        normalize_artifact_package()

    assert exc_info.value.code == "THEME_RESEARCH_CONFLICTING_SOURCE"


def test_normalize_artifacts_rejects_duplicate_source_identity_within_theme(
    monkeypatch,
    tmp_path,
) -> None:
    theme_id = "theme-a"
    theme_source = {
        "source_id": "canonical-source",
        "url_or_ref": "HTTPS://Example.COM/reports/annual.pdf/",
    }
    mapping_source = {
        "source_id": "mapping-source",
        "url_or_ref": "https://example.com/reports/annual.pdf#page=12",
    }
    artifact = {
        "theme": {"theme_id": theme_id},
        "sources": [theme_source],
        "claims": [],
        "value_capture_assessments": [],
    }
    (tmp_path / "theme-a.json").write_text(
        import_module._canonical_json(artifact),
        encoding="utf-8",
    )
    theme_package = {
        "artifact_dir": str(tmp_path),
        "artifact_versions": ["theme_decomposition_v1_6"],
        "themes": [artifact["theme"]],
        "nodes": [{"node_id": "node-a", "theme_id": theme_id}],
        "sources": [theme_source],
        "claims": [],
    }
    mapping_package = {
        "artifacts": [
            {
                "theme_id": theme_id,
                "sources": [mapping_source],
                "company_mappings": [
                    {
                        "mapping_id": "mapping-a",
                        "theme_id": theme_id,
                        "mapped_node_id": "node-a",
                        "evidence_ids": ["evidence-a"],
                    }
                ],
            }
        ],
        "sources": [mapping_source],
        "evidence_items": [
            {
                "evidence_id": "evidence-a",
                "source_id": "mapping-source",
            }
        ],
    }
    monkeypatch.setattr(import_module, "load_theme_package", lambda _path: theme_package)
    monkeypatch.setattr(import_module, "load_theme", lambda _theme_id, _path: artifact)
    monkeypatch.setattr(
        import_module,
        "load_theme_company_mapping_package",
        lambda _mapping_dir, _theme_dir: mapping_package,
    )

    with pytest.raises(ThemeResearchDomainError) as exc_info:
        normalize_artifact_package()

    assert exc_info.value.code == "THEME_RESEARCH_DUPLICATE_SOURCE_IDENTITY"
    assert exc_info.value.details == {
        "theme_id": theme_id,
        "url": "https://example.com/reports/annual.pdf",
        "source_ids": ["canonical-source", "mapping-source"],
    }


def test_source_identity_validation_allows_same_url_across_themes() -> None:
    import_module._validate_theme_source_identities(
        artifact_by_theme_id={
            "theme-a": {
                "sources": [
                    {
                        "source_id": "theme-a-source",
                        "url_or_ref": "https://example.com/report.pdf",
                    }
                ]
            },
            "theme-b": {"sources": []},
        },
        mapping_package={
            "artifacts": [
                {
                    "theme_id": "theme-b",
                    "sources": [
                        {
                            "source_id": "theme-b-source",
                            "url_or_ref": "https://example.com/report.pdf",
                        }
                    ],
                    "company_mappings": [
                        {
                            "mapping_id": "mapping-b",
                            "theme_id": "theme-b",
                            "evidence_ids": ["evidence-b"],
                        }
                    ],
                }
            ],
            "sources": [
                {
                    "source_id": "theme-b-source",
                    "url_or_ref": "https://example.com/report.pdf",
                }
            ],
            "evidence_items": [
                {"evidence_id": "evidence-b", "source_id": "theme-b-source"}
            ],
        },
    )


def test_source_identity_validation_ignores_unreferenced_mapping_sources() -> None:
    import_module._validate_theme_source_identities(
        artifact_by_theme_id={
            "theme-a": {
                "sources": [
                    {
                        "source_id": "canonical-source",
                        "url_or_ref": "https://example.com/report.pdf",
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
                            "source_id": "unused-mapping-source",
                            "url_or_ref": "https://example.com/report.pdf",
                        }
                    ],
                    "company_mappings": [
                        {
                            "mapping_id": "mapping-a",
                            "theme_id": "theme-a",
                            "evidence_ids": [],
                        }
                    ],
                }
            ],
            "sources": [
                {
                    "source_id": "unused-mapping-source",
                    "url_or_ref": "https://example.com/report.pdf",
                }
            ],
            "evidence_items": [
                {
                    "evidence_id": "unused-evidence",
                    "source_id": "unused-mapping-source",
                }
            ],
        },
    )


def test_source_identity_validation_preserves_query_strings() -> None:
    import_module._validate_theme_source_identities(
        artifact_by_theme_id={
            "theme-a": {
                "sources": [
                    {
                        "source_id": "canonical-source",
                        "url_or_ref": "https://example.com/report.pdf?version=1",
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
                            "url_or_ref": "https://example.com/report.pdf?version=2",
                        }
                    ],
                    "company_mappings": [
                        {
                            "mapping_id": "mapping-a",
                            "theme_id": "theme-a",
                            "evidence_ids": ["evidence-a"],
                        }
                    ],
                }
            ],
            "sources": [
                {
                    "source_id": "mapping-source",
                    "url_or_ref": "https://example.com/report.pdf?version=2",
                }
            ],
            "evidence_items": [
                {"evidence_id": "evidence-a", "source_id": "mapping-source"}
            ],
        },
    )


def test_source_identity_validation_preserves_url_userinfo_case() -> None:
    import_module._validate_theme_source_identities(
        artifact_by_theme_id={
            "theme-a": {
                "sources": [
                    {
                        "source_id": "canonical-source",
                        "url_or_ref": "https://User@example.com/report.pdf",
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
                            "url_or_ref": "https://user@EXAMPLE.COM/report.pdf",
                        }
                    ],
                    "company_mappings": [
                        {
                            "mapping_id": "mapping-a",
                            "theme_id": "theme-a",
                            "evidence_ids": ["evidence-a"],
                        }
                    ],
                }
            ],
            "sources": [
                {
                    "source_id": "mapping-source",
                    "url_or_ref": "https://user@EXAMPLE.COM/report.pdf",
                }
            ],
            "evidence_items": [
                {"evidence_id": "evidence-a", "source_id": "mapping-source"}
            ],
        },
    )


def test_normalized_theme_metadata_preserves_research_profiles() -> None:
    artifact_package = load_theme_package()
    package = normalize_artifact_package()
    expected = {
        row["theme_id"]: {
            key: value for key, value in row.items() if key != "theme_id"
        }
        for row in artifact_package["research_profiles"]
    }

    assert {
        row["theme_id"]: row["artifact_metadata"]["research_profile"]
        for row in package.themes
        if row["theme_id"] in expected
    } == expected


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
