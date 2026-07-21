from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.governance import (
    validate_stage_a_scope_correction,
)
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload


GLOBAL_ENTITIES = (
    "NVIDIA",
    "Intel / Habana",
    "Cisco",
    "Broadcom",
    "Lightmatter",
    "Supermicro",
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_NAME = "acquisition_checkpoint:a5f7627d8726c9405ba67a75.json"
CHECKPOINT_CANONICAL_HASH = (
    "a5f7627d8726c9405ba67a7527826edb0cff26ee777287e33cb55442bace660e"
)
CHECKPOINT_FILE_SHA256 = (
    "e2b91137df1c01a7fa7b30c8ed9cdd8b052e30ad3a57a274519fab20cb2f07ae"
)


def scope_correction_payload() -> dict:
    return {
        "schema_version": "2.4.0",
        "artifact_kind": "stage_a_scope_correction",
        "decision": {
            "decision_id": "scope_correction:ai_compute_pcb_stage_a_v1",
            "decision_type": "stage_a_scope_correction",
            "project_id": "research_project:ai_compute_pcb_industry_bottleneck",
            "investment_market_scope": "A_share",
            "original_stage": "stage_a_acquisition",
            "original_checkpoint": {
                "checkpoint_id": "acquisition_checkpoint:a5f7627d8726c9405ba67a75",
                "canonical_content_hash": "a5f7627d8726c9405ba67a7527826edb0cff26ee777287e33cb55442bace660e",
                "file_sha256": "e2b91137df1c01a7fa7b30c8ed9cdd8b052e30ad3a57a274519fab20cb2f07ae",
            },
            "corrected_stage_role": "global_industry_reference_acquisition",
            "corrected_status": "global_industry_reference_acquisition_complete",
            "global_entities_role": "industry_reference_only",
            "global_equity_assessment_allowed": False,
            "a_share_candidate_coverage_claimed": False,
            "evidence_assessment_allowed": "industry_claim_level_only",
            "company_level_assessment_allowed": False,
            "stage_b_authorized": False,
            "next_stage": "stage_a2_a_share_supply_chain_mapping",
            "entity_classifications": [
                {
                    "entity_name": name,
                    "entity_role": "global_industry_reference",
                    "investment_candidate": False,
                    "eligible_for_a_share_review_universe": False,
                    "eligible_for_company_scoring": False,
                    "eligible_for_signal": False,
                    "eligible_for_admission": False,
                }
                for name in GLOBAL_ENTITIES
            ],
            "evidence_use_invariants": [
                "global_reference_coverage != a_share_candidate_coverage",
                "primary_source_count != evidence_sufficiency",
                "industry_claim_support != company_exposure_support",
            ],
            "preserved_acquisition_rules": [
                "blocked_attempts_do_not_count_as_acquired_evidence",
                "exact_duplicates_count_as_one_evidence_chain",
                "suspected_common_origin_is_one_provisional_chain",
                "unknown_publication_dates_remain_unknown",
                "er05_denominator_remains_open",
                "widen_redirects_remain_fail_closed",
                "network_mode_remains_direct_http_trust_env_false",
            ],
            "stage_a2_plan": {
                "stage_name": "Stage A2 — A-share Supply-chain Mapping",
                "plan_status": "planned",
                "research_only": True,
                "acquisition_started": False,
                "company_universe_generated": False,
                "object_flow": [
                    "global_technology_claim",
                    "component_or_process_requirement",
                    "value_chain_segment",
                    "a_share_candidate_hypothesis",
                    "company_specific_evidence_requirement",
                ],
                "candidate_mapping_dimensions": ["high_speed_pcb"],
                "acceptance_criteria": [
                    "industry-evidence traceability precedes candidate hypotheses"
                ],
                "forbidden_outputs": [
                    "company_score",
                    "stock_recommendation",
                    "signal",
                    "admission",
                    "portfolio",
                    "strategy",
                    "trade",
                ],
            },
            "provenance": {
                "created_by": "Codex",
                "actor_type": "codex",
                "agent_run_id": "r2b-stage-a-scope-correction-20260721",
                "created_at": "2026-07-21T00:00:00Z",
                "created_in_version": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
                "review_status": "reviewed",
            },
        },
        "content_hash": "0" * 64,
    }


def test_schema_v2_4_accepts_stage_a_scope_correction() -> None:
    validate_v2_1_schema_payload(
        "stage_a_scope_correction_v2_4", scope_correction_payload()
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload["decision"].update(investment_market_scope="US"),
        lambda payload: payload["decision"].update(
            global_equity_assessment_allowed=True
        ),
        lambda payload: payload["decision"].update(
            company_level_assessment_allowed=True
        ),
        lambda payload: payload["decision"].update(stage_b_authorized=True),
        lambda payload: payload["decision"].update(next_stage="stage_b"),
        lambda payload: payload["decision"]["stage_a2_plan"].update(
            acquisition_started=True
        ),
        lambda payload: payload["decision"]["entity_classifications"][0].update(
            investment_candidate=True
        ),
    ],
)
def test_schema_v2_4_rejects_scope_leakage(mutation) -> None:
    payload = scope_correction_payload()
    mutation(payload)
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_v2_1_schema_payload("stage_a_scope_correction_v2_4", payload)
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCHEMA_INVALID"


def test_schema_v2_4_rejects_unknown_fields() -> None:
    payload = deepcopy(scope_correction_payload())
    payload["decision"]["stock_recommendation"] = "forbidden"
    with pytest.raises(ResearchProjectV2Error):
        validate_v2_1_schema_payload("stage_a_scope_correction_v2_4", payload)


def _layout_with_checkpoint(tmp_path: Path) -> LayeredResearchLayout:
    root = tmp_path / "v2_1"
    checkpoint_dir = root / "acquisition/checkpoints"
    checkpoint_dir.mkdir(parents=True)
    source = (
        REPOSITORY_ROOT
        / "artifacts/research_projects/v2_1/acquisition/checkpoints"
        / CHECKPOINT_NAME
    )
    shutil.copyfile(source, checkpoint_dir / CHECKPOINT_NAME)
    schema_source = REPOSITORY_ROOT / "artifacts/research_projects/v2_1/schema"
    shutil.copytree(schema_source, root / "schema")
    return LayeredResearchLayout(root)


def _semantic_payload() -> dict:
    payload = scope_correction_payload()
    payload["content_hash"] = content_sha256(
        payload, excluded_paths={("content_hash",)}
    )
    return payload


def test_validate_scope_correction_binds_checkpoint_id_and_both_hashes(
    tmp_path: Path,
) -> None:
    layout = _layout_with_checkpoint(tmp_path)
    validated = validate_stage_a_scope_correction(
        _semantic_payload(), layout=layout
    )
    assert validated["decision"]["original_checkpoint"] == {
        "checkpoint_id": CHECKPOINT_NAME.removesuffix(".json"),
        "canonical_content_hash": CHECKPOINT_CANONICAL_HASH,
        "file_sha256": CHECKPOINT_FILE_SHA256,
    }


def test_validate_scope_correction_rejects_embedded_checkpoint_hash_drift(
    tmp_path: Path,
) -> None:
    layout = _layout_with_checkpoint(tmp_path)
    checkpoint_path = layout.acquisition_checkpoints_dir / CHECKPOINT_NAME
    wrapper = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    wrapper["acquisition_checkpoint"]["content_hash"] = "f" * 64
    checkpoint_path.write_bytes(canonical_bytes(wrapper))

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_stage_a_scope_correction(_semantic_payload(), layout=layout)
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCOPE_CORRECTION_INVALID"
    assert exc_info.value.details["field"] == (
        "original_checkpoint.canonical_content_hash"
    )


def test_validate_scope_correction_rejects_checkpoint_file_drift(
    tmp_path: Path,
) -> None:
    layout = _layout_with_checkpoint(tmp_path)
    checkpoint_path = layout.acquisition_checkpoints_dir / CHECKPOINT_NAME
    wrapper = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    wrapper["acquisition_checkpoint"]["unresolved_issues"].append(
        "unauthorized mutation"
    )
    checkpoint_path.write_bytes(canonical_bytes(wrapper))

    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_stage_a_scope_correction(_semantic_payload(), layout=layout)
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_SCOPE_CORRECTION_INVALID"
    assert exc_info.value.details["field"] == "original_checkpoint.file_sha256"


@pytest.mark.parametrize("entity_name", GLOBAL_ENTITIES)
def test_validate_scope_correction_requires_every_global_reference_entity(
    tmp_path: Path, entity_name: str
) -> None:
    layout = _layout_with_checkpoint(tmp_path)
    payload = _semantic_payload()
    payload["decision"]["entity_classifications"] = [
        entity
        for entity in payload["decision"]["entity_classifications"]
        if entity["entity_name"] != entity_name
    ]
    payload["decision"]["entity_classifications"].append(
        deepcopy(payload["decision"]["entity_classifications"][0])
    )
    payload["content_hash"] = content_sha256(
        payload, excluded_paths={("content_hash",)}
    )
    with pytest.raises(ResearchProjectV2Error):
        validate_stage_a_scope_correction(payload, layout=layout)


@pytest.mark.parametrize(
    "forbidden",
    [
        "company_score",
        "stock_recommendation",
        "signal",
        "admission",
        "portfolio",
        "strategy",
        "trade",
    ],
)
def test_validate_scope_correction_requires_every_downstream_prohibition(
    tmp_path: Path, forbidden: str
) -> None:
    layout = _layout_with_checkpoint(tmp_path)
    payload = _semantic_payload()
    payload["decision"]["stage_a2_plan"]["forbidden_outputs"].remove(forbidden)
    payload["content_hash"] = content_sha256(
        payload, excluded_paths={("content_hash",)}
    )
    with pytest.raises(ResearchProjectV2Error):
        validate_stage_a_scope_correction(payload, layout=layout)


def test_validate_scope_correction_rejects_content_hash_mismatch(
    tmp_path: Path,
) -> None:
    layout = _layout_with_checkpoint(tmp_path)
    payload = _semantic_payload()
    payload["content_hash"] = "f" * 64
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_stage_a_scope_correction(payload, layout=layout)
    assert exc_info.value.details["field"] == "content_hash"


def test_checkpoint_fixture_hashes_match_the_immutable_baseline() -> None:
    checkpoint = (
        REPOSITORY_ROOT
        / "artifacts/research_projects/v2_1/acquisition/checkpoints"
        / CHECKPOINT_NAME
    )
    wrapper = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert wrapper["acquisition_checkpoint"]["content_hash"] == CHECKPOINT_CANONICAL_HASH
    assert sha256(checkpoint.read_bytes()).hexdigest() == CHECKPOINT_FILE_SHA256


def test_repository_scope_correction_artifact_is_valid_and_checkpoint_is_unchanged() -> None:
    layout = LayeredResearchLayout.default()
    path = layout.governance_dir / "stage_a_scope_correction_v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    validated = validate_stage_a_scope_correction(payload, layout=layout)
    assert canonical_bytes(validated) == path.read_bytes()

    checkpoint = layout.acquisition_checkpoints_dir / CHECKPOINT_NAME
    wrapper = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert wrapper["acquisition_checkpoint"]["content_hash"] == CHECKPOINT_CANONICAL_HASH
    assert sha256(checkpoint.read_bytes()).hexdigest() == CHECKPOINT_FILE_SHA256


def test_scope_correction_documents_preserve_history_and_state_boundaries() -> None:
    stage_a = (
        REPOSITORY_ROOT
        / "docs/research_operating_layer_v2_r2b_ai_pcb_stage_a_acquisition.md"
    ).read_text(encoding="utf-8")
    plan = (
        REPOSITORY_ROOT
        / "docs/research_operating_layer_v2_r2b_ai_pcb_scope_correction_and_stage_a2_plan.md"
    ).read_text(encoding="utf-8")
    for phrase in (
        "global_industry_reference_acquisition",
        "investment_market_scope = A_share",
        "industry_claim_level_only",
        "company_level_assessment_allowed = false",
        "stage_b_authorized = false",
        "Stage A2 — A-share Supply-chain Mapping",
    ):
        assert phrase in stage_a
        assert phrase in plan
    assert "Stage A2 acquisition has not started" in plan
    assert "global_reference_coverage != a_share_candidate_coverage" in plan
    assert "industry_claim_support != company_exposure_support" in plan
