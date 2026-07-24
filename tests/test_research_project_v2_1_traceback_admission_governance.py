from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
import subprocess

from stock_research.research_project_v2.canonical import content_sha256


ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE = ROOT / "artifacts/research_projects/v2_1/governance"
ANALYSIS = ROOT / "artifacts/research_projects/v2_1/analysis"
ACQUISITION = ROOT / "artifacts/research_projects/v2_1/acquisition"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_canonical_hash(payload: dict) -> None:
    assert payload["content_hash"] == content_sha256(
        payload, excluded_paths={("content_hash",)}
    )


def test_traceback_review_admits_only_the_supplier_specific_b01_source() -> None:
    review = _read(
        GOVERNANCE
        / "ai_pcb_primary_source_traceback_review_and_admission_decision_v1.json"
    )
    traceback = _read(ANALYSIS / "ai_pcb_primary_source_traceback_v1.json")
    checkpoint = _read(
        ACQUISITION / "primary_source_traceback_v1/traceback_checkpoint.json"
    )
    _assert_canonical_hash(review)
    assert review["input_bindings"]["traceback_artifact_hash"] == traceback["content_hash"]
    assert review["input_bindings"]["traceback_checkpoint_hash"] == checkpoint["content_hash"]
    assert review["traceback_accepted"] is True
    assert review["future_assessment_candidate_count"] == 1
    assert review["direct_er_status_change"] is False
    admitted = review["admitted_sources"]
    assert len(admitted) == 1
    source = admitted[0]
    assert source["source_candidate_id"] == "traceback_source_candidate:novoray_spherical_silica_product"
    assert source["source_artifact_id"] == "evidence_artifact:408fa4886206c8463510a812"
    assert source["raw_content_hash"] == "ab2ccbf1587f9d9a31a0482fce64e53e84af129e1c0b283488e9eca6ae6ad2a7"
    assert source["normalized_document_id"] == "normalized_document:ddb90d268b7abd4114702aae"
    assert source["locator"]["section_index"] == 111
    assert source["locator"]["section_hash"] == "e8ad5cef300fa3cfaf6301b594a0199efd559c2d04353cb8a0b4197f15192a8e"
    assert source["authorized_er_id"] == "PCB-ER-B01"
    assert source["evidence_role"] == "supplier_specific_parameter_statement"
    assert source["admitted_to_consolidated_assessment"] is True
    assert source["claim_sufficient"] is False
    assert source["er_sufficient"] is False
    assert source["cognition_update_eligible"] is False
    assert source["evidence_chain_count"] == 1
    assert len(source["originating_broker_claim_ids"]) == 4
    raw_path = ROOT / "artifacts/research_projects/v2_1" / source["raw_artifact_path"]
    assert sha256(raw_path.read_bytes()).hexdigest() == source["raw_content_hash"]
    normalized = _read(
        ROOT
        / "artifacts/research_projects/v2_1/evidence/normalized"
        / f"{source['normalized_document_id']}.json"
    )["normalized_document"]
    assert normalized["document_hash"] == source["normalized_document_hash"]
    section = normalized["sections"][source["locator"]["section_index"] - 1]
    assert section["section_id"] == source["locator"]["section_id"]
    assert section["section_hash"] == source["locator"]["section_hash"]
    assert "3.88(1MHz)" in section["text"]
    assert "0.0002(1MHz)" in section["text"]
    assert review["additional_traceback_authorized"] is False
    assert review["human_assistance_required"] is False


def test_consolidated_assessment_authorization_v2_is_exact_offline_and_unconsumed() -> None:
    review = _read(
        GOVERNANCE
        / "ai_pcb_primary_source_traceback_review_and_admission_decision_v1.json"
    )
    authorization = _read(
        GOVERNANCE
        / "ai_pcb_consolidated_evidence_assessment_execution_authorization_v2.json"
    )
    old_authorization = _read(
        GOVERNANCE
        / "ai_pcb_targeted_evidence_assessment_wave_1b_consolidated_execution_authorization_v1.json"
    )
    _assert_canonical_hash(authorization)
    assert authorization["input_bindings"]["traceback_review_decision_hash"] == review["content_hash"]
    assert authorization["authorization_scope"] == "exact_evidence_bundle_only"
    assert authorization["execution_mode"] == "offline_read_only_consolidated_assessment"
    assert authorization["network_access"] is False
    assert authorization["new_acquisition"] is False
    assert authorization["fallback_acquisition"] is False
    assert authorization["consolidated_assessment_authorized"] is True
    assert authorization["authorization_consumed"] is False
    assert set(authorization["authorized_er_ids"]) == {
        "PCB-ER-A02",
        "PCB-ER-A04",
        "PCB-ER-B01",
        "PCB-ER-B02",
    }
    assert len(authorization["admitted_traceback_evidence"]) == 1
    assert authorization["admitted_traceback_evidence"][0]["source_artifact_id"] == "evidence_artifact:408fa4886206c8463510a812"
    assert old_authorization["authorization_consumed"] is False
    assert authorization["input_bindings"]["prior_authorization_consumed"] is False
    for field in (
        "cognition_update_authorized",
        "additional_recovery_authorized",
        "additional_traceback_authorized",
        "company_mapping_authorized",
        "stage_a2_authorized",
        "stage_b_authorized",
    ):
        assert authorization[field] is False


def test_traceback_admission_governance_exact_allowlist_contains_only_task_changes() -> None:
    allowlist = _read(
        GOVERNANCE
        / "ai_pcb_traceback_review_and_consolidated_assessment_authorization_v2_exact_allowlist.json"
    )
    changed = set(
        subprocess.check_output(
            ["git", "diff", "--name-only", allowlist["baseline_commit"]],
            cwd=ROOT,
            text=True,
        ).splitlines()
    )
    for line in subprocess.check_output(
        ["git", "status", "--porcelain=v1", "-uall"], cwd=ROOT, text=True
    ).splitlines():
        changed.add(line[3:].split(" -> ", 1)[-1])
    assert changed <= set(allowlist["allowed_paths"])
