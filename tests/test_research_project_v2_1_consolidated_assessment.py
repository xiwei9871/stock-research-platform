from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest

from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.consolidated_assessment import (
    CONSOLIDATED_AUTHORIZED_ER_IDS,
    canonicalize_recovery_representations,
    render_consolidated_assessment_report,
    validate_consolidated_assessment_artifact,
    validate_consolidated_assessment_authorization,
    validate_persisted_consolidated_assessment_report,
)


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION_PATH = ROOT / (
    "artifacts/research_projects/v2_1/governance/"
    "ai_pcb_targeted_evidence_assessment_wave_1b_consolidated_execution_authorization_v1.json"
)
ARTIFACT_PATH = ROOT / (
    "artifacts/research_projects/v2_1/analysis/"
    "ai_pcb_targeted_evidence_assessment_wave_1b_consolidated_v1.json"
)
REPORT_PATH = ROOT / (
    "artifacts/research_projects/v2_1/reports/"
    "ai_pcb_targeted_evidence_assessment_wave_1b_consolidated_v1.md"
)


def _rehash(payload: dict) -> dict:
    payload["content_hash"] = content_sha256(
        payload, excluded_paths={("content_hash",)}
    )
    return payload


def test_frozen_authorization_is_exact_offline_and_bound() -> None:
    authorization = json.loads(AUTHORIZATION_PATH.read_text(encoding="utf-8"))
    validated = validate_consolidated_assessment_authorization(authorization)

    assert tuple(validated["authorized_er_ids"]) == CONSOLIDATED_AUTHORIZED_ER_IDS
    assert validated["authorization_scope"] == "exact_er_and_evidence_list_only"
    assert validated["network_access"] is False
    assert validated["new_acquisition_authorized"] is False
    assert [
        row["artifact_id"] for row in validated["eligible_recovery_evidence"]
    ] == ["evidence_artifact:5cf8a72e4f4c6a9043a474c5"]


def test_recovery_resume_representations_collapse_to_canonical_documents() -> None:
    authorization = json.loads(AUTHORIZATION_PATH.read_text(encoding="utf-8"))
    result = canonicalize_recovery_representations(authorization)

    assert result == {
        "normalized_document:c3ff111a56925e8c6836494f": "normalized_document:22497cde16ab00ae7b720c87",
        "normalized_document:500ae7dcaae88360df0e9c72": "normalized_document:019803185d3da18b4d1f2486",
    }


def test_materialized_consolidated_assessment_is_strict_and_deterministic() -> None:
    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    validated = validate_consolidated_assessment_artifact(artifact)
    validate_persisted_consolidated_assessment_report(
        validated, REPORT_PATH.read_bytes()
    )

    assert tuple(validated["authorized_er_ids"]) == CONSOLIDATED_AUTHORIZED_ER_IDS
    assert validated["authorization_consumed"] is True
    assert validated["eligible_recovery_artifact_ids"] == [
        "evidence_artifact:5cf8a72e4f4c6a9043a474c5"
    ]
    assert validated["canonical_representation_register"][1][
        "resume_duplicate_ids"
    ] == ["normalized_document:500ae7dcaae88360df0e9c72"]
    assert len(validated["er_assessments"]) == 4
    assert {row["overall_status"] for row in validated["er_assessments"]} == {
        "insufficient"
    }
    assert 3 <= len(validated["unresolved_evidence_targets"]) <= 5
    assert validated["governance"]["network_access"] is False
    assert validated["governance"]["new_acquisition"] is False
    assert validated["governance"]["cognition_update"] is False
    assert validated["governance"]["automatic_manual_task_authorization"] is False


def test_validator_rejects_recovery_identity_mismatch_and_duplicate_chain_inflation() -> None:
    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    invalid = deepcopy(artifact)
    invalid["eligible_recovery_artifact_ids"].append(
        "evidence_artifact:a906a111c3b689ac19c58f3a"
    )
    with pytest.raises(ResearchProjectV2Error, match="eligible recovery"):
        validate_consolidated_assessment_artifact(_rehash(invalid))

    invalid = deepcopy(artifact)
    invalid["evidence_chain_register"].append(
        {
            "chain_id": "evidence_chain:ieee-802-3ck-resume-duplicate",
            "source_owner": "IEEE 802.3",
            "artifact_ids": ["evidence_artifact:5cf8a72e4f4c6a9043a474c5"],
            "independence_group": "ieee_802_3ck_backplane_com_2019",
        }
    )
    with pytest.raises(ResearchProjectV2Error, match="independence group"):
        validate_consolidated_assessment_artifact(_rehash(invalid))


def test_validator_rejects_scope_or_downstream_authorization() -> None:
    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    invalid = deepcopy(artifact)
    invalid["authorized_er_ids"].append("PCB-ER-A03")
    with pytest.raises(ResearchProjectV2Error, match="authorized ER"):
        validate_consolidated_assessment_artifact(_rehash(invalid))

    invalid = deepcopy(artifact)
    invalid["governance"]["cognition_update"] = True
    with pytest.raises(ResearchProjectV2Error, match="prohibited downstream"):
        validate_consolidated_assessment_artifact(_rehash(invalid))


def test_report_renderer_is_byte_deterministic() -> None:
    artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    expected = render_consolidated_assessment_report(artifact)
    assert expected == REPORT_PATH.read_bytes()
    with pytest.raises(ResearchProjectV2Error, match="deterministic projection"):
        validate_persisted_consolidated_assessment_report(
            artifact, expected + b"unexpected\n"
        )


def test_consolidated_assessment_exact_allowlist_contains_current_changes() -> None:
    allowlist_path = ROOT / (
        "artifacts/research_projects/v2_1/governance/"
        "targeted_evidence_assessment_wave_1b_consolidated_exact_allowlist.json"
    )
    allowlist = json.loads(allowlist_path.read_text(encoding="utf-8"))
    changed = set(
        subprocess.check_output(
            ["git", "diff", "--name-only", allowlist["baseline_commit"]],
            cwd=ROOT,
            text=True,
        ).splitlines()
    )
    for line in subprocess.check_output(
        ["git", "status", "--porcelain=v1", "-uall"],
        cwd=ROOT,
        text=True,
    ).splitlines():
        changed.add(line[3:].split(" -> ", 1)[-1])
    assert changed <= set(allowlist["paths"])
    assert not any(
        path.startswith(tuple(allowlist["forbidden_prefixes"])) for path in changed
    )
