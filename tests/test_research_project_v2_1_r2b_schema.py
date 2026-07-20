from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload
from stock_research.research_project_v2_1.loader import _industry_version_schema_name
from stock_research.research_project_v2_1.semantic import validate_industry_version_semantics
from stock_research.research_project_v2_1.evidence import validate_industry_evidence_assessment
from stock_research.research_project_v2.canonical import content_sha256


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = REPOSITORY_ROOT / "artifacts/research_projects/v2_1"
PROJECT_SLUG = "ai_compute_pcb_industry_bottleneck"
VERSION_ID = f"research_version:{PROJECT_SLUG}:0.2.0"


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _provenance() -> dict:
    return {
        "actor_type": "codex",
        "agent_run_id": "r2b-phase2-schema-test",
        "created_at": "2026-07-20T08:00:00Z",
        "created_by": "Codex",
        "created_in_version": VERSION_ID,
        "review_status": "pending_review",
    }


def _v2_2_version() -> dict:
    version = deepcopy(
        _load_json(
            ARTIFACT_ROOT
            / "projects"
            / PROJECT_SLUG
            / "versions/v0.1.0.json"
        )
    )
    version.update(
        {
            "schema_version": "2.2.0",
            "version_id": VERSION_ID,
            "semantic_version": "0.2.0",
            "parent_version_id": f"research_version:{PROJECT_SLUG}:0.1.0",
            "creation_stage": "research_design",
            "created_at": "2026-07-20T08:00:00Z",
            "created_by": "Codex",
            "change_summary": "Add R2B industry model and bottleneck design.",
            "change_reason": "Approved R2B Phase 2 industry design snapshot.",
            "incorporated_event_ids": [],
            "content_hash": "0" * 64,
        }
    )
    snapshot = version["snapshot"]
    for edge in snapshot["causal_edges"]:
        edge["counter_claim_ids"] = []
    for requirement in snapshot["evidence_requirements"]:
        requirement.update(
            {
                "geography_scope": ["global"],
                "product_scope": "Inherited R2A design scope.",
                "stop_conditions": ["approved stop condition"],
                "required_evidence_stances": ["supports", "opposes"],
                "required_evidence_functions": ["validation"],
                "lifecycle_status": "superseded",
                "supersedes_requirement_id": None,
                "open_discovery": False,
            }
        )
    snapshot["evidence_requirements"][0]["lifecycle_status"] = "active"
    snapshot["evidence_requirements"][0]["open_discovery"] = True
    for plan in snapshot["search_plans"]:
        plan["version_id"] = VERSION_ID
    snapshot["router_decision"]["secondary_methods"] = [
        "manufacturing_process",
        "constraint_analysis",
        "infrastructure_economics",
        "value_migration",
    ]
    snapshot["industry_model_nodes"] = [
        {
            "industry_model_node_id": f"industry_node:{PROJECT_SLUG}:pcb_process",
            "node_kind": "manufacturing_process",
            "title": "High-speed PCB manufacturing process",
            "scope": "AI compute PCB target process mix",
            "description": "Process node for high-layer and high-speed boards.",
            "input_ids": [],
            "output_ids": [],
            "key_parameter_names": ["yield", "layer_count"],
            "lifecycle_status": "active",
            "provenance": _provenance(),
        }
    ]
    snapshot["industry_model_edges"] = []
    snapshot["bottleneck_hypotheses"] = [
        {
            "bottleneck_hypothesis_id": f"bottleneck_hypothesis:{PROJECT_SLUG}:r2b_bh01",
            "title": "Qualified effective PCB capacity",
            "bottleneck_type": "effective_capacity",
            "target_node_or_process_id": f"industry_node:{PROJECT_SLUG}:pcb_process",
            "scope": "Shipped AI compute PCB in the defined architecture window.",
            "mechanism": "Complex process and qualification reduce effective supply.",
            "affected_system_parameter_ids": [],
            "impact_path_edge_ids": [],
            "severity_hypothesis": "high",
            "duration_hypothesis": "two to six quarters",
            "substitution_paths": ["qualified alternative source"],
            "mitigation_conditions": ["yield and qualified capacity ramp"],
            "supporting_claim_ids": [],
            "counter_claim_ids": [],
            "evidence_requirement_ids": [],
            "validation_metric_ids": [],
            "invalidation_condition_ids": [],
            "status": "proposed",
            "confidence": 0.25,
            "lifecycle_status": "active",
            "research_disposition": "unchanged",
            "related_bottleneck_ids": [],
            "scope_change_note": None,
            "created_in_version": VERSION_ID,
            "provenance": _provenance(),
        }
    ]
    snapshot["value_migration_analyses"] = []
    snapshot["bottleneck_readiness_reviews"] = []
    return version


def test_existing_v2_1_versions_remain_valid_and_unmodified() -> None:
    for path in sorted((ARTIFACT_ROOT / "projects").glob("*/versions/v0.1.0.json")):
        before = path.read_bytes()
        validate_v2_1_schema_payload(
            "industry_research_version_v2_1", _load_json(path)
        )
        assert path.read_bytes() == before


def test_loader_dispatches_industry_schema_by_embedded_version() -> None:
    assert _industry_version_schema_name({"schema_version": "2.1.0"}) == "industry_research_version_v2_1"
    assert _industry_version_schema_name({"schema_version": "2.2.0"}) == "industry_research_version_v2_2"
    with pytest.raises(ResearchProjectV2Error):
        _industry_version_schema_name({"schema_version": "9.9.9"})


def test_v2_2_industry_profile_accepts_required_r2b_collections() -> None:
    validate_v2_1_schema_payload("industry_research_version_v2_2", _v2_2_version())


def test_v2_2_semantics_resolve_new_object_references() -> None:
    validate_industry_version_semantics(_v2_2_version())


def test_v2_2_semantics_reject_missing_bottleneck_target_node() -> None:
    version = _v2_2_version()
    version["snapshot"]["bottleneck_hypotheses"][0][
        "target_node_or_process_id"
    ] = "industry_node:missing"
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_industry_version_semantics(version)
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SEMANTIC_INVALID"


def test_v2_2_semantics_require_active_open_discovery_requirement() -> None:
    version = _v2_2_version()
    for requirement in version["snapshot"]["evidence_requirements"]:
        requirement["open_discovery"] = False
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_industry_version_semantics(version)
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SEMANTIC_INVALID"


def test_v2_2_industry_profile_requires_all_new_collections() -> None:
    version = _v2_2_version()
    del version["snapshot"]["bottleneck_hypotheses"]
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload("industry_research_version_v2_2", version)
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"


def test_v2_2_metrics_and_invalidations_can_target_bottlenecks() -> None:
    version = _v2_2_version()
    bottleneck_id = version["snapshot"]["bottleneck_hypotheses"][0][
        "bottleneck_hypothesis_id"
    ]
    version["snapshot"]["validation_metrics"][0].update(
        {"target_type": "bottleneck_hypothesis", "target_id": bottleneck_id}
    )
    version["snapshot"]["invalidation_conditions"][0].update(
        {"target_type": "bottleneck_hypothesis", "target_id": bottleneck_id}
    )
    validate_v2_1_schema_payload("industry_research_version_v2_2", version)
    validate_industry_version_semantics(version)


def test_v2_2_assessment_separates_one_stance_from_multiple_functions() -> None:
    payload = {
        "schema_version": "2.2.0",
        "artifact_kind": "industry_evidence_assessment",
        "industry_evidence_assessment": {
            "assessment_id": "assessment:r2b:test:001",
            "evidence_channel": "industry",
            "target_type": "bottleneck_hypothesis",
            "target_id": f"bottleneck_hypothesis:{PROJECT_SLUG}:r2b_bh01",
            "requirement_id": f"requirement:{PROJECT_SLUG}:r2b_er08",
            "artifact_id": "evidence_artifact:0123456789abcdef01234567",
            "normalized_document_id": "normalized_document:0123456789abcdef01234567",
            "evidence_stance": "mixed",
            "evidence_functions": ["mechanism", "feasibility"],
            "locator": {
                "locator_type": "page",
                "locator_value": "12",
                "quoted_text": "Defined engineering observation.",
            },
            "assessment_summary": "Supports the mechanism but not market quantification.",
            "applicable_scope": "Specified board generation and process mix.",
            "directness": "direct",
            "strength": "medium",
            "independence": "primary_source",
            "freshness": "current",
            "scope_match": "exact",
            "conflict_status": "material_conflict",
            "review_status": "pending_review",
            "assessed_by": "Codex",
            "assessed_at": "2026-07-20T08:00:00Z",
            "provenance": _provenance(),
        },
        "content_hash": "0" * 64,
    }
    validate_v2_1_schema_payload("industry_evidence_assessment_v2_2", payload)

    assessment = payload["industry_evidence_assessment"]
    import hashlib

    locator_key = json.dumps(assessment["locator"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    identity = hashlib.sha256(
        f"{assessment['requirement_id']}\n{assessment['artifact_id']}\n{locator_key}".encode()
    ).hexdigest()[:24]
    assessment["assessment_id"] = f"industry_evidence_assessment:{identity}"
    payload["content_hash"] = content_sha256(payload, excluded_paths={("content_hash",)})
    assert validate_industry_evidence_assessment(payload)["evidence_stance"] == "mixed"


def test_v2_2_assessment_rejects_legacy_single_role() -> None:
    payload = {
        "schema_version": "2.2.0",
        "artifact_kind": "industry_evidence_assessment",
        "industry_evidence_assessment": {
            "assessment_id": "assessment:r2b:test:001",
            "evidence_role": "supports",
        },
        "content_hash": "0" * 64,
    }
    with pytest.raises(ResearchProjectV2Error):
        validate_v2_1_schema_payload("industry_evidence_assessment_v2_2", payload)
