import json
from pathlib import Path

import pytest

from stock_research.theme_decomposition import (
    ThemeDecompositionValidationError,
    cli,
    load_theme,
    load_theme_package,
    summarize_theme_package,
)


def test_sample_artifacts_load_and_summarize():
    package = load_theme_package()

    summary = summarize_theme_package(package)

    assert summary["theme_count"] == 6
    assert summary["node_count"] == 77
    assert summary["source_count"] >= 50
    assert summary["claim_count"] >= 50
    assert summary["sources_by_reliability_level"]["S4"] >= 2
    assert summary["claims_by_evidence_status"]["verified"] >= 40
    assert summary["sources_by_review_status"]["lead_only"] >= 2
    assert summary["claims_by_platform_use_status"]["reviewed"] >= 47
    assert summary["nodes_by_review_status"]["needs_evidence"] >= 1
    assert summary["high_priority_evidence_gap_count"] >= 1
    assert "transformer" in summary["high_priority_evidence_gap"]
    assert "transformer" in summary["nodes_by_value_capture_score"]["5"]
    assert "planetary_roller_screw" in summary["nodes_by_bottleneck_score"]["5"]


def test_theme_detail_includes_current_assessment_sources():
    detail = load_theme("ai_power_value_capture_v1")

    source_ids = {source["source_id"] for source in detail["sources"]}

    assert "ai_power_doe_data_center_demand_2024" in source_ids
    assert "ai_power_nvidia_800v_ecosystem_blog_2025" in source_ids


def test_missing_required_field_raises(tmp_path):
    artifact_dir = tmp_path / "theme_decomposition"
    artifact_dir.mkdir()
    _write_artifact(
        artifact_dir / "bad.json",
        {
            "artifact_version": "theme_decomposition_v1_5",
            "theme": {
                "theme_name": "Missing ID",
                "theme_type": "other",
                "summary": "invalid",
                "status": "draft",
                "created_from": "manual",
                "last_updated": "2026-07-10",
            },
            "sources": [],
            "claims": [],
            "nodes": [],
            "value_capture_assessments": [],
            "decomposition_templates": [],
        },
    )

    with pytest.raises(ThemeDecompositionValidationError, match="theme.theme_id"):
        load_theme_package(artifact_dir)


def test_score_out_of_range_raises(tmp_path):
    artifact_dir = tmp_path / "theme_decomposition"
    artifact_dir.mkdir()
    artifact = _minimal_valid_artifact()
    artifact["nodes"][0]["bottleneck_score"] = 6
    _write_artifact(artifact_dir / "bad_score.json", artifact)

    with pytest.raises(ThemeDecompositionValidationError, match="bottleneck_score"):
        load_theme_package(artifact_dir)


def test_invalid_reliability_level_raises(tmp_path):
    artifact_dir = tmp_path / "theme_decomposition"
    artifact_dir.mkdir()
    artifact = _minimal_valid_artifact()
    artifact["sources"][0]["reliability_level"] = "S9"
    _write_artifact(artifact_dir / "bad_reliability.json", artifact)

    with pytest.raises(ThemeDecompositionValidationError, match="reliability_level"):
        load_theme_package(artifact_dir)


def test_summary_evidence_status_aggregation_is_stable(tmp_path):
    artifact_dir = tmp_path / "theme_decomposition"
    artifact_dir.mkdir()
    artifact = _minimal_valid_artifact()
    artifact["claims"].append(
        {
            "claim_id": "claim_2",
            "theme_id": "theme_minimal",
            "source_id": "source_s4",
            "claim_text": "A second unverified clue.",
            "claim_type": "bottleneck",
            "confidence": 0.2,
            "evidence_status": "unverified",
            "platform_use_status": "research_lead",
            "supporting_source_ids": ["source_s4"],
            "affected_theme_nodes": ["root_node"],
        }
    )
    _write_artifact(artifact_dir / "minimal.json", artifact)

    summary = summarize_theme_package(load_theme_package(artifact_dir))

    assert summary["claims_by_evidence_status"] == {
        "partially_verified": 1,
        "unverified": 1,
    }


def test_orphan_parent_node_raises(tmp_path):
    artifact_dir = tmp_path / "theme_decomposition"
    artifact_dir.mkdir()
    artifact = _minimal_valid_artifact()
    artifact["nodes"][0]["parent_node_id"] = "missing_parent"
    _write_artifact(artifact_dir / "orphan.json", artifact)

    with pytest.raises(ThemeDecompositionValidationError, match="parent_node_id"):
        load_theme_package(artifact_dir)


def test_s4_source_cannot_be_accepted(tmp_path):
    artifact = _minimal_valid_artifact()
    artifact["sources"][1]["review_status"] = "accepted"

    error = _load_invalid_artifact(tmp_path, artifact)

    assert error.code == "S4_SOURCE_CANNOT_BE_ACCEPTED"


def test_reviewed_claim_cannot_be_supported_only_by_s4_sources(tmp_path):
    artifact = _minimal_valid_artifact()
    artifact["claims"][0].update(
        {
            "source_id": "source_s4",
            "supporting_source_ids": ["source_s4"],
            "platform_use_status": "reviewed",
        }
    )

    error = _load_invalid_artifact(tmp_path, artifact)

    assert error.code == "REVIEWED_CLAIM_S4_ONLY"


def test_reviewed_claim_requires_accepted_source(tmp_path):
    artifact = _minimal_valid_artifact()
    artifact["sources"][0]["review_status"] = "needs_full_text"
    artifact["claims"][0]["platform_use_status"] = "reviewed"

    error = _load_invalid_artifact(tmp_path, artifact)

    assert error.code == "REVIEWED_CLAIM_REQUIRES_ACCEPTED_SOURCE"


def test_reviewed_claim_cannot_use_rejected_source(tmp_path):
    artifact = _minimal_valid_artifact()
    artifact["sources"][0]["review_status"] = "rejected"
    artifact["claims"][0]["platform_use_status"] = "reviewed"

    error = _load_invalid_artifact(tmp_path, artifact)

    assert error.code == "REVIEWED_CLAIM_USES_REJECTED_SOURCE"


def test_reviewed_node_requires_evidence_strength_at_least_three(tmp_path):
    artifact = _minimal_valid_artifact()
    artifact["nodes"][0]["node_review_status"] = "reviewed"

    error = _load_invalid_artifact(tmp_path, artifact)

    assert error.code == "REVIEWED_NODE_REQUIRES_STRONG_EVIDENCE"


def test_reviewed_node_cannot_use_rejected_assessment_source(tmp_path):
    artifact = _minimal_valid_artifact()
    artifact["sources"][0]["review_status"] = "rejected"
    artifact["nodes"][0].update({"node_review_status": "reviewed", "evidence_strength": 3})

    error = _load_invalid_artifact(tmp_path, artifact)

    assert error.code == "REVIEWED_NODE_USES_REJECTED_SOURCE"


def test_invalid_review_status_has_stable_error_code(tmp_path):
    artifact = _minimal_valid_artifact()
    artifact["sources"][0]["review_status"] = "approved"

    error = _load_invalid_artifact(tmp_path, artifact)

    assert error.code == "INVALID_SOURCE_REVIEW_STATUS"


def test_unsupported_artifact_version_has_stable_error_code(tmp_path):
    artifact = _minimal_valid_artifact()
    artifact["artifact_version"] = "theme_decomposition_v1"

    error = _load_invalid_artifact(tmp_path, artifact)

    assert error.code == "UNSUPPORTED_ARTIFACT_VERSION"


def test_v1_6_deep_industry_research_profile_loads(tmp_path):
    artifact_dir = tmp_path / "theme_decomposition"
    artifact_dir.mkdir()
    artifact = _minimal_valid_artifact()
    artifact["artifact_version"] = "theme_decomposition_v1_6"
    artifact["theme"]["theme_type"] = "new_energy_storage"
    artifact["claims"].extend(
        [
            {
                "claim_id": "storage_catalyst_1",
                "theme_id": "theme_minimal",
                "source_id": "source_s0",
                "claim_text": "Utilization and market participation are observable demand validators.",
                "claim_type": "catalyst",
                "confidence": 0.7,
                "evidence_status": "partially_verified",
                "platform_use_status": "draft",
                "supporting_source_ids": ["source_s0"],
                "affected_theme_nodes": ["root_node"],
            },
            {
                "claim_id": "storage_risk_1",
                "theme_id": "theme_minimal",
                "source_id": "source_s0",
                "claim_text": "Low utilization can prevent installed capacity from producing durable economics.",
                "claim_type": "risk",
                "confidence": 0.7,
                "evidence_status": "partially_verified",
                "platform_use_status": "draft",
                "supporting_source_ids": ["source_s0"],
                "affected_theme_nodes": ["root_node"],
            },
        ]
    )
    artifact["research_profile"] = {
        "catalog_chain_id": "new_energy_storage",
        "research_kind": "industry_chain_deep_research",
        "industry_stage": "commercial_scaling",
        "central_conflict": "System economics depend on cells, conversion, safety, and utilization together.",
        "investment_summary": "Storage value is captured across equipment and operating layers.",
        "value_flow_summary": "cells -> packs -> PCS/BMS/EMS -> integration -> grid service",
        "profit_pool_summary": "Qualification, control, integration, and operation are assessed separately.",
        "catalyst_claim_ids": ["storage_catalyst_1"],
        "risk_claim_ids": ["storage_risk_1"],
        "validation_signals": ["system tender prices", "utilization hours"],
        "evidence_gap_summary": "Revenue exposure requires company-level filings.",
    }
    _write_artifact(artifact_dir / "deep_theme.json", artifact)

    package = load_theme_package(artifact_dir)
    detail = load_theme("theme_minimal", artifact_dir)

    assert package["research_profiles"] == [artifact["research_profile"] | {"theme_id": "theme_minimal"}]
    assert detail["research_profile"] == artifact["research_profile"]


def test_v1_6_deep_research_profile_requires_all_fields(tmp_path):
    artifact = _minimal_valid_artifact()
    artifact["artifact_version"] = "theme_decomposition_v1_6"
    artifact["research_profile"] = _minimal_research_profile()
    del artifact["research_profile"]["central_conflict"]

    error = _load_invalid_artifact(tmp_path, artifact)

    assert error.code == "MISSING_RESEARCH_PROFILE_FIELD"


def test_v1_6_profile_claim_references_must_exist(tmp_path):
    artifact = _minimal_valid_artifact()
    artifact["artifact_version"] = "theme_decomposition_v1_6"
    artifact["research_profile"] = _minimal_research_profile()

    error = _load_invalid_artifact(tmp_path, artifact)

    assert error.code == "RESEARCH_PROFILE_CLAIM_NOT_FOUND"


def test_cli_validate_returns_structured_gate_error(tmp_path, capsys):
    artifact_dir = tmp_path / "theme_decomposition"
    artifact_dir.mkdir()
    artifact = _minimal_valid_artifact()
    artifact["sources"][1]["review_status"] = "accepted"
    _write_artifact(artifact_dir / "invalid.json", artifact)

    exit_code = cli(["--artifact-dir", str(artifact_dir), "validate"])
    payload = json.loads(capsys.readouterr().err)

    assert exit_code == 2
    assert payload == {
        "error_code": "S4_SOURCE_CANNOT_BE_ACCEPTED",
        "message": "sources[1] S4 source cannot be accepted",
        "status": "error",
    }


def _write_artifact(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_invalid_artifact(tmp_path: Path, artifact: dict) -> ThemeDecompositionValidationError:
    artifact_dir = tmp_path / "theme_decomposition"
    artifact_dir.mkdir()
    _write_artifact(artifact_dir / "invalid.json", artifact)
    with pytest.raises(ThemeDecompositionValidationError) as exc_info:
        load_theme_package(artifact_dir)
    return exc_info.value


def _minimal_valid_artifact() -> dict:
    return {
        "artifact_version": "theme_decomposition_v1_5",
        "theme": {
            "theme_id": "theme_minimal",
            "theme_name": "Minimal Theme",
            "theme_type": "other",
            "summary": "Minimal valid artifact.",
            "status": "draft",
            "created_from": "manual",
            "last_updated": "2026-07-10",
        },
        "sources": [
            {
                "source_id": "source_s0",
                "source_type": "official_report",
                "title": "Primary source",
                "publisher": "Issuer",
                "author": "",
                "publish_date": "2026-01-01",
                "url_or_ref": "internal:test",
                "access_level": "public",
                "reliability_level": "S0",
                "review_status": "accepted",
                "notes": "test",
            },
            {
                "source_id": "source_s4",
                "source_type": "video_claim",
                "title": "Video clue",
                "publisher": "Social account",
                "author": "",
                "publish_date": "",
                "url_or_ref": "manual:video",
                "access_level": "private_claimed",
                "reliability_level": "S4",
                "review_status": "lead_only",
                "notes": "unverified clue only",
            },
        ],
        "claims": [
            {
                "claim_id": "claim_1",
                "theme_id": "theme_minimal",
                "source_id": "source_s0",
                "claim_text": "A partially verified claim.",
                "claim_type": "value_capture",
                "confidence": 0.6,
                "evidence_status": "partially_verified",
                "platform_use_status": "draft",
                "supporting_source_ids": ["source_s0"],
                "affected_theme_nodes": ["root_node"],
            }
        ],
        "nodes": [
            {
                "node_id": "root_node",
                "theme_id": "theme_minimal",
                "parent_node_id": "",
                "node_name": "Root",
                "node_type": "infrastructure",
                "description": "Root node.",
                "value_capture_score": 1,
                "bottleneck_score": 1,
                "localization_gap_score": 1,
                "supply_tightness_score": 1,
                "evidence_strength": 1,
                "node_review_status": "draft",
                "key_metrics": [],
                "overseas_leaders": [],
                "domestic_players": [],
                "related_stock_codes": [],
            }
        ],
        "value_capture_assessments": [
            {
                "node_id": "root_node",
                "value_basis": "scarcity",
                "assessment_text": "Minimal assessment.",
                "rank": 1,
                "evidence_ids": ["source_s0"],
                "uncertainty": "medium",
            }
        ],
        "decomposition_templates": [
            {
                "template_id": "minimal_template",
                "theme_type": "other",
                "steps": ["define theme", "map nodes"],
                "required_dimensions": ["evidence"],
                "optional_dimensions": [],
                "output_schema": "theme_decomposition_v1_5",
            }
        ],
    }


def _minimal_research_profile() -> dict:
    return {
        "catalog_chain_id": "new_energy_storage",
        "research_kind": "industry_chain_deep_research",
        "industry_stage": "commercial_scaling",
        "central_conflict": "System economics depend on cells, conversion, safety, and utilization together.",
        "investment_summary": "Storage value is captured across equipment and operating layers.",
        "value_flow_summary": "cells -> packs -> PCS/BMS/EMS -> integration -> grid service",
        "profit_pool_summary": "Qualification, control, integration, and operation are assessed separately.",
        "catalyst_claim_ids": ["missing_catalyst"],
        "risk_claim_ids": ["missing_risk"],
        "validation_signals": ["system tender prices", "utilization hours"],
        "evidence_gap_summary": "Revenue exposure requires company-level filings.",
    }
