from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest

from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2.canonical import canonical_bytes
from hashlib import sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.wave_1b import (
    AUTHORIZED_ER_IDS,
    INTERNAL_EXECUTION_ORDER,
    REQUIRED_DENOMINATOR_FIELDS,
    build_wave_1b_checkpoint,
    to_wave_1b_provider_candidate,
    validate_wave_1b_candidate,
    validate_wave_1b_checkpoint,
    validate_wave_1b_gate,
    validate_wave_1b_repository_bundle,
)


def _gate() -> dict:
    gate = {
        "schema_version": "1.0.0",
        "artifact_type": "targeted_acquisition_wave_1b_gate_decision",
        "decision_id": "targeted_acquisition_wave_1b_gate_decision:ai_pcb:v1",
        "decision_status": "frozen",
        "project_id": "research_project:ai_compute_pcb_industry_bottleneck",
        "gate_decision": "approved_with_revisions",
        "wave_1_assessment_accepted": True,
        "input_bindings": {
            "wave_1_assessment_id": "targeted_evidence_assessment:ai_pcb:wave_1:v1",
            "wave_1_assessment_hash": "8e80bc8994f6f1fd20ae7c46fe5d3669be13a08b86162f7c5d7f2729788367cd",
            "wave_1_checkpoint_id": "targeted_acquisition_checkpoint:b53ab0a0143b89f9914842f5",
            "wave_1_checkpoint_hash": "b53ab0a0143b89f9914842f5848ed606b86de3dc1a4a7f5f08a05c6afcf81013",
            "prior_gate_decision_id": "targeted_acquisition_gate_decision:ai_pcb:v1",
            "prior_gate_hash": "38f48163bfdc825b6f3afc12e95a9cc99c59c0fccc809fbe4e86460405d509ea",
        },
        "no_additional_acquisition": [{"er_id": "PCB-ER-A01"}],
        "deferred": [{"er_id": "PCB-ER-A03"}],
        "authorized_for_wave_1b": list(AUTHORIZED_ER_IDS),
        "internal_execution_order": {
            "phase_1": list(INTERNAL_EXECUTION_ORDER[0]),
            "phase_2": list(INTERNAL_EXECUTION_ORDER[1]),
        },
        "research_objectives": [],
        "authorization": {
            "wave_1b_targeted_acquisition_authorized": True,
            "authorization_scope": "exact_list_only",
            "unlisted_er_authorized": False,
            "fail_closed_conditions": [],
            "failure_result": "acquisition_allowed = false",
        },
        "prohibited_inferences": [],
        "wave_1b_acquisition_started": False,
        "cognition_update_authorized": False,
        "company_mapping_authorized": False,
        "stage_a2_authorized": False,
        "stage_b_authorized": False,
        "decided_at": "2026-07-22T01:19:53Z",
        "decision_actor": "human_reviewer",
        "content_hash": "",
    }
    gate["content_hash"] = content_sha256(gate, excluded_paths=(("content_hash",),))
    return gate


def _candidate(er_id: str, *, phase: int | None = None) -> dict:
    expected_phase = 1 if er_id in INTERNAL_EXECUTION_ORDER[0] else 2
    return {
        "candidate_id": f"source_candidate:{er_id.lower()}",
        "wave_id": "targeted_evidence_acquisition_wave_1b",
        "internal_phase": expected_phase if phase is None else phase,
        "authorized_er_ids": [er_id],
        "source_title": "Test source",
        "provider_source_title": f"Test source [{er_id}]",
        "source_owner": "Standards body",
        "source_class": "technical_standard",
        "source_url": "https://example.com/test.pdf",
        "expected_evidence_role": "measurement_method",
        "expected_denominator_fields": list(REQUIRED_DENOMINATOR_FIELDS.get(er_id, ())),
        "eligibility_reason": "Matches the exact authorized research requirement.",
        "known_limitations": ["Does not establish manufacturing capacity."],
        "publication_date": None,
        "publication_date_status": "unknown",
        "candidate_status": "eligible",
        "rank": 1,
    }


def _rehash_checkpoint(checkpoint: dict) -> dict:
    core = {
        key: value
        for key, value in checkpoint.items()
        if key not in {"checkpoint_id", "content_hash"}
    }
    checkpoint["checkpoint_id"] = (
        f"targeted_acquisition_checkpoint:{sha256(canonical_bytes(core)).hexdigest()[:24]}"
    )
    checkpoint["content_hash"] = content_sha256(core)
    return checkpoint


def test_gate_is_exact_list_fail_closed_and_hash_bound() -> None:
    gate = validate_wave_1b_gate(_gate())
    assert tuple(gate["authorized_for_wave_1b"]) == AUTHORIZED_ER_IDS
    assert tuple(gate["internal_execution_order"]["phase_1"]) == INTERNAL_EXECUTION_ORDER[0]

    drifted = deepcopy(_gate())
    drifted["authorized_for_wave_1b"].append("PCB-ER-A01")
    with pytest.raises(ResearchProjectV2Error, match="hash|authorized"):
        validate_wave_1b_gate(drifted)


def test_candidate_rejects_a01_a03_unlisted_er_and_wrong_phase() -> None:
    gate = validate_wave_1b_gate(_gate())
    assert validate_wave_1b_candidate(_candidate("PCB-ER-A04"), gate)["internal_phase"] == 1
    assert validate_wave_1b_candidate(_candidate("PCB-ER-A02"), gate)["internal_phase"] == 2

    for er_id in ("PCB-ER-A01", "PCB-ER-A03", "PCB-ER-A05"):
        with pytest.raises(ResearchProjectV2Error, match="not authorized"):
            validate_wave_1b_candidate(_candidate(er_id), gate)

    with pytest.raises(ResearchProjectV2Error, match="phase"):
        validate_wave_1b_candidate(_candidate("PCB-ER-A02", phase=1), gate)


def test_candidate_requires_er_specific_denominator_fields() -> None:
    gate = validate_wave_1b_gate(_gate())
    candidate = _candidate("PCB-ER-B01")
    candidate["expected_denominator_fields"].remove("test_method")
    with pytest.raises(ResearchProjectV2Error, match="denominator"):
        validate_wave_1b_candidate(candidate, gate)


def test_provider_candidate_preserves_wave_1b_discovery_identity() -> None:
    candidate = _candidate("PCB-ER-A04")
    provider = to_wave_1b_provider_candidate(
        candidate,
        discovered_at="2026-07-22T02:00:00Z",
        provenance={"created_by": "Codex"},
    )
    assert provider["search_plan_id"] == "search_plan:ai_pcb_targeted_wave_1b"
    assert provider["query_id"] == "wave_1b_phase_1"
    assert provider["snippet"] == ""


def test_checkpoint_counts_only_formal_authorized_coverage() -> None:
    gate = validate_wave_1b_gate(_gate())
    candidates = [_candidate(er_id) for er_id in AUTHORIZED_ER_IDS]
    attempts = [
        {
            "attempt_id": f"attempt:{er_id}",
            "candidate_id": f"source_candidate:{er_id.lower()}",
            "authorized_er_ids": [er_id],
            "internal_phase": 1 if er_id in INTERNAL_EXECUTION_ORDER[0] else 2,
            "status": "acquired",
            "raw_artifact_id": f"artifact:{er_id}",
            "content_hash": er_id.encode().hex().ljust(64, "0")[:64],
            "content_type": "application/pdf",
            "normalization_status": "normalized",
        }
        for er_id in AUTHORIZED_ER_IDS
    ]
    inventory = [
        {
            "artifact_id": row["raw_artifact_id"],
            "authorized_er_ids": row["authorized_er_ids"],
            "content_hash": row["content_hash"],
            "content_type": row["content_type"],
            "publication_date_status": "unknown",
            "normalized_document_id": f"normalized:{row['authorized_er_ids'][0]}",
            "normalization_status": "normalized",
            "source_class": "technical_standard",
            "denominator_fields_present": list(
                REQUIRED_DENOMINATOR_FIELDS[row["authorized_er_ids"][0]]
            ),
        }
        for row in attempts
    ]
    checkpoint = build_wave_1b_checkpoint(
        gate=gate,
        candidates=candidates,
        attempts=attempts,
        inventory=inventory,
        created_at="2026-07-22T02:00:00Z",
        preflight_attempt_ids=["preflight:1"],
    )
    validated = validate_wave_1b_checkpoint(checkpoint, gate=gate)
    assert validated["formal_attempt_count"] == 4
    assert validated["preflight_attempt_count"] == 1
    assert validated["per_er_attempt_coverage"] == {er_id: 1 for er_id in AUTHORIZED_ER_IDS}
    assert validated["out_of_scope_coverage"] == 0
    assert validated["assessment_started"] is False
    assert validated["cognition_update_started"] is False
    assert set(validated["per_er_terminal_state"].values()) == {
        "acquisition_complete_for_assessment"
    }


def test_checkpoint_marks_acquired_but_denominator_incomplete_er_partial() -> None:
    gate = validate_wave_1b_gate(_gate())
    candidate = _candidate("PCB-ER-A04")
    attempt = {
        "attempt_id": "attempt:a04",
        "candidate_id": candidate["candidate_id"],
        "authorized_er_ids": ["PCB-ER-A04"],
        "internal_phase": 1,
        "status": "acquired",
        "raw_artifact_id": "artifact:a04",
        "content_hash": "1" * 64,
        "content_type": "application/pdf",
        "normalization_status": "normalized",
    }
    inventory = [{
        "artifact_id": "artifact:a04",
        "authorized_er_ids": ["PCB-ER-A04"],
        "content_hash": "1" * 64,
        "content_type": "application/pdf",
        "publication_date_status": "unknown",
        "normalized_document_id": "normalized:a04",
        "normalization_status": "normalized",
        "source_class": "national_metrology",
        "denominator_fields_present": ["frequency_range"],
    }]
    checkpoint = build_wave_1b_checkpoint(
        gate=gate,
        candidates=[candidate],
        attempts=[attempt],
        inventory=inventory,
        created_at="2026-07-22T02:00:00Z",
    )
    assert checkpoint["per_er_terminal_state"]["PCB-ER-A04"] == (
        "acquisition_partial_with_gaps"
    )


def test_checkpoint_rejects_unauthorized_coverage_and_downstream_flags() -> None:
    gate = validate_wave_1b_gate(_gate())
    checkpoint = build_wave_1b_checkpoint(
        gate=gate,
        candidates=[_candidate("PCB-ER-A04")],
        attempts=[],
        inventory=[],
        created_at="2026-07-22T02:00:00Z",
    )
    checkpoint["per_er_acquired_coverage"]["PCB-ER-A01"] = 1
    with pytest.raises(ResearchProjectV2Error, match="unauthorized|scope"):
        validate_wave_1b_checkpoint(_rehash_checkpoint(checkpoint), gate=gate)

    checkpoint = build_wave_1b_checkpoint(
        gate=gate,
        candidates=[_candidate("PCB-ER-A04")],
        attempts=[],
        inventory=[],
        created_at="2026-07-22T02:00:00Z",
    )
    checkpoint["assessment_started"] = True
    with pytest.raises(ResearchProjectV2Error, match="downstream"):
        validate_wave_1b_checkpoint(_rehash_checkpoint(checkpoint), gate=gate)


def test_materialized_wave_1b_bundle_is_fail_closed_and_traceable() -> None:
    result = validate_wave_1b_repository_bundle()
    assert result == {
        "valid": True,
        "checkpoint_id": "targeted_acquisition_checkpoint:a4690962e23c07e238dd2f4d",
        "checkpoint_hash": "a4690962e23c07e238dd2f4dfeb5d081fd1c93a0b95a89a2509e23ae4f9ceec2",
        "candidate_count": 17,
        "formal_attempt_count": 17,
        "raw_artifact_count": 6,
    }


def test_wave_1b_exact_allowlist_covers_only_the_authorized_phase() -> None:
    root = Path(__file__).resolve().parents[1]
    allowlist = json.loads(
        (
            root
            / "artifacts/research_projects/v2_1/acquisition/wave_1b_exact_allowlist.json"
        ).read_text(encoding="utf-8")
    )
    changed = set(
        subprocess.check_output(
            ["git", "diff", "--name-only", f"{allowlist['baseline_commit']}..061471c"],
            cwd=root,
            text=True,
        ).splitlines()
    )
    assert changed <= set(allowlist["paths"])
    assert not any(
        path.startswith(tuple(allowlist["forbidden_prefixes"])) for path in changed
    )
