from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess

import pytest

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.wave_1b_recovery import (
    build_recovery_checkpoint,
    recovery_identity_matches,
    validate_recovery_authorization,
    validate_recovery_checkpoint,
    validate_recovery_repository_bundle,
)


def _gate() -> dict:
    targets = []
    for index, er_id in enumerate(("PCB-ER-A04", "PCB-ER-A04", "PCB-ER-B01", "PCB-ER-B01", "PCB-ER-B02", "PCB-ER-A02", "PCB-ER-A02"), 1):
        targets.append({
            "recovery_target_id": f"recovery_target:test:{index}",
            "original_candidate_id": f"source_candidate:test{index}",
            "authorized_er_id": er_id,
            "authorized_recovery_action": f"action_{index}",
            "same_failed_url_retry_allowed": index == 4,
            "maximum_attempts": 1,
        })
    payload = {
        "decision_id": "wave_1b_recovery_pilot_gate_decision:ai_pcb:v1",
        "decision_status": "frozen",
        "selected_target_count": 7,
        "selected_targets": targets,
        "content_hash": "",
    }
    payload["content_hash"] = content_sha256(payload, excluded_paths={("content_hash",)})
    return payload


def _authorization(gate: dict) -> dict:
    targets = [{
        "recovery_target_id": row["recovery_target_id"],
        "original_candidate_id": row["original_candidate_id"],
        "authorized_er_id": row["authorized_er_id"],
        "authorized_recovery_action": row["authorized_recovery_action"],
        "formal_acquisition_authorized": True,
        "same_failed_url_retry_allowed": row["same_failed_url_retry_allowed"],
        "maximum_formal_attempts": 1,
    } for row in gate["selected_targets"]]
    payload = {
        "authorization_id": "wave_1b_recovery_pilot_execution_authorization:ai_pcb:v1",
        "authorization_status": "frozen",
        "project_id": "research_project:ai_compute_pcb_industry_bottleneck",
        "input_bindings": {"recovery_pilot_gate_id": gate["decision_id"], "recovery_pilot_gate_hash": gate["content_hash"]},
        "execution_authorized": True,
        "authorization_scope": "exact_candidate_and_action_list_only",
        "authorized_target_count": 7,
        "maximum_total_formal_attempts": 7,
        "authorization_consumed": False,
        "authorized_targets": targets,
        "unlisted_target_authorized": False,
        "target_substitution_authorized": False,
        "automatic_scope_expansion_authorized": False,
        "automatic_assessment_authorized": False,
        "cognition_update_authorized": False,
        "wave_2_authorized": False,
        "company_mapping_authorized": False,
        "stage_a2_authorized": False,
        "stage_b_authorized": False,
        "content_hash": "",
    }
    payload["content_hash"] = content_sha256(payload, excluded_paths={("content_hash",)})
    return payload


def test_recovery_authorization_requires_exact_seven_target_binding() -> None:
    gate = _gate()
    authorization = _authorization(gate)
    validated = validate_recovery_authorization(authorization, gate=gate, validate_upstreams=False)
    assert len(validated["authorized_targets"]) == 7

    invalid = deepcopy(authorization)
    invalid["authorized_targets"][0]["authorized_recovery_action"] = "substituted"
    invalid["content_hash"] = content_sha256(invalid, excluded_paths={("content_hash",)})
    with pytest.raises(ResearchProjectV2Error, match="target binding"):
        validate_recovery_authorization(invalid, gate=gate, validate_upstreams=False)


def test_recovery_checkpoint_consumes_authorization_and_caps_attempts() -> None:
    gate = _gate()
    authorization = _authorization(gate)
    attempts = [{
        "recovery_target_id": row["recovery_target_id"],
        "authorized_er_id": row["authorized_er_id"],
        "status": "failed",
        "failure_code": "manually_unavailable",
        "raw_artifact_id": None,
        "normalized_document_id": None,
    } for row in authorization["authorized_targets"]]
    checkpoint = build_recovery_checkpoint(
        gate=gate,
        authorization=authorization,
        attempts=attempts,
        inventory=[],
        created_at="2026-07-22T00:00:00Z",
    )
    validated = validate_recovery_checkpoint(checkpoint, gate=gate, authorization=authorization)
    assert validated["authorization_consumed"] is True
    assert validated["formal_attempt_count"] == 7
    assert validated["assessment_started"] is False

    too_many = deepcopy(checkpoint)
    too_many["formal_attempt_count"] = 8
    too_many["checkpoint_id"] = f"wave_1b_recovery_checkpoint:{sha256(canonical_bytes({key: value for key, value in too_many.items() if key not in {'checkpoint_id', 'content_hash'}})).hexdigest()[:24]}"
    too_many["content_hash"] = content_sha256(too_many, excluded_paths={("content_hash",)})
    with pytest.raises(ResearchProjectV2Error, match="attempt"):
        validate_recovery_checkpoint(too_many, gate=gate, authorization=authorization)


def test_recovery_identity_match_is_fail_closed_for_wrong_landing_page() -> None:
    assert recovery_identity_matches(
        target_id="recovery_target:ai_pcb:wave_1b:b02:usc_repository_alternative:v1",
        expected_title="Characterization of electrodeposited copper foil surface roughness for accurate conductor power loss modeling",
        document_title="Methods for Identifying Regions of Brain Activation",
        document_text="Unrelated dissertation text.",
        resolved_url="https://scholarcommons.sc.edu/etd/2965/",
    ) is False
    assert recovery_identity_matches(
        target_id="recovery_target:ai_pcb:wave_1b:b01:panasonic_bounded_retry:v1",
        expected_title="Panasonic MEGTRON 6 product information",
        document_title="MEGTRON 6 | Panasonic Industry",
        document_text="High-speed circuit board materials.",
        resolved_url="https://industrial.panasonic.com/ww/products/pt/megtron/megtron6",
    ) is True


def test_materialized_recovery_bundle_is_exact_and_downstream_closed() -> None:
    result = validate_recovery_repository_bundle()
    assert result == {
        "status": "pass",
        "checkpoint_id": "wave_1b_recovery_checkpoint:eb5ac1cd5e37481dcd2df2dc",
        "checkpoint_hash": "96949222f5697c1074e4ac60ee230fd814e9f8cc95cecbb112c0e14982290f54",
        "formal_attempt_count": 7,
        "raw_artifact_count": 2,
        "normalized_representation_count": 4,
        "eligible_for_assessment_count": 1,
    }


def test_recovery_pilot_exact_allowlist_contains_all_changes() -> None:
    root = Path(__file__).resolve().parents[1]
    allowlist = json.loads(
        (root / "artifacts/research_projects/v2_1/acquisition/wave_1b_recovery_pilot_exact_allowlist.json").read_text(encoding="utf-8")
    )
    changed = set(
        subprocess.check_output(
            ["git", "diff", "--name-only", f"{allowlist['baseline_commit']}..HEAD"],
            cwd=root,
            text=True,
        ).splitlines()
    )
    for line in subprocess.check_output(
        ["git", "status", "--porcelain=v1", "-uall"], cwd=root, text=True
    ).splitlines():
        changed.add(line[3:].split(" -> ", 1)[-1])
    assert changed <= set(allowlist["paths"])
    assert not any(path.startswith(tuple(allowlist["forbidden_prefixes"])) for path in changed)
