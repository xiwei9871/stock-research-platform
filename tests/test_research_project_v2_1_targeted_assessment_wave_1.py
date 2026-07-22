from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest

from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.targeted_assessment import (
    AUTHORIZED_ER_IDS,
    compute_er_assessment,
    render_assessment_report,
    validate_assessment_artifact,
    validate_persisted_assessment_report,
)


TARGETED_ASSESSMENT_WAVE_1_END_COMMIT = (
    "2205bc14d59abb374fc3e3d32568f56a1030e8ae"
)


def _claim(**overrides: object) -> dict:
    claim = {
        "claim_id": "W1-A01-C01",
        "er_id": "PCB-ER-A01",
        "claim_text": "A scoped standard fact.",
        "claim_type": "fact",
        "scope": "One named OIF interface clause.",
        "product_or_standard_generation": "OIF-CEI-05.3",
        "rate": "36-58 Gsym/s",
        "frequency": "not_applicable",
        "distance": "up to 1000 mm in the cited clause",
        "topology": "point-to-point differential",
        "test_method": "normative standard definition",
        "denominator": "one named CEI interface class",
        "evidence_locators": [
            {
                "artifact_id": "evidence_artifact:test",
                "normalized_document_id": "normalized_document:test",
                "section_index": 0,
                "section_hash": "1" * 64,
                "heading": None,
                "locator_note": "Direct clause text.",
            }
        ],
        "evidence_stance": "support",
        "evidence_chain_ids": ["evidence_chain:oif-cei-05.3"],
        "source_independence_status": "single_primary_chain",
        "freshness_status": "unknown",
        "assessment_status": "sufficient",
        "evidence_strength": "high",
        "confidence": "medium",
        "assessment_reason": "The clause directly states the scoped fact.",
        "limitations": ["No industry-wide inference."],
        "counterevidence": [],
        "alternative_explanations": [],
        "missing_evidence": ["Independent engineering interpretation."],
        "maximum_supported_cognition": "standard_definition_only",
    }
    claim.update(overrides)
    return claim


def _artifact() -> dict:
    claims = [_claim()]
    er = compute_er_assessment("PCB-ER-A01", claims, independent_chain_count=1)
    artifact = {
        "schema_version": "2.7.0",
        "artifact_type": "targeted_evidence_assessment",
        "assessment_id": "targeted_evidence_assessment:ai_pcb:wave_1:v1",
        "project_id": "research_project:ai_compute_pcb_industry_bottleneck",
        "assessment_wave": "targeted_evidence_assessment_wave_1_v1",
        "execution_mode": "offline_read_only_evidence_assessment",
        "renderer_version": "targeted_evidence_assessment_markdown_v1",
        "input_bindings": {
            "checkpoint_id": "targeted_acquisition_checkpoint:b53ab0a0143b89f9914842f5",
            "checkpoint_hash": "b53ab0a0143b89f9914842f5848ed606b86de3dc1a4a7f5f08a05c6afcf81013",
            "gate_hash": "38f48163bfdc825b6f3afc12e95a9cc99c59c0fccc809fbe4e86460405d509ea",
        },
        "authorized_er_ids": list(AUTHORIZED_ER_IDS),
        "evidence_chain_register": [
            {
                "chain_id": "evidence_chain:oif-cei-05.3",
                "source_owner": "OIF",
                "artifact_ids": ["evidence_artifact:test"],
                "independence_group": "oif-cei-05.3",
            }
        ],
        "atomic_claims": claims,
        "er_assessments": [
            er,
            *[
                compute_er_assessment(er_id, [], independent_chain_count=0)
                for er_id in AUTHORIZED_ER_IDS
                if er_id != "PCB-ER-A01"
            ],
        ],
        "excluded_records": [],
        "governance": {
            "network_access": False,
            "new_acquisition": False,
            "cognition_update": False,
            "gap_review_update": False,
            "gate_update": False,
            "company_mapping_authorized": False,
            "stage_a2_authorized": False,
            "stage_b_authorized": False,
            "wave_1b_authorized": False,
        },
        "provenance": {
            "created_by": "Codex",
            "actor_type": "codex",
            "agent_run_id": "assessment-test",
            "created_at": "2026-07-22T00:00:00Z",
            "created_in_version": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
            "review_status": "unreviewed",
        },
        "content_hash": "",
    }
    artifact["content_hash"] = content_sha256(
        artifact, excluded_paths=(("content_hash",),)
    )
    return artifact


def _rehash(artifact: dict) -> dict:
    artifact["content_hash"] = content_sha256(
        artifact, excluded_paths=(("content_hash",),)
    )
    return artifact


def test_er_status_does_not_auto_promote_from_one_sufficient_claim() -> None:
    er = compute_er_assessment(
        "PCB-ER-A01",
        [_claim(), _claim(claim_id="W1-A01-C02", assessment_status="insufficient")],
        independent_chain_count=1,
    )
    assert er["sufficient_claim_ids"] == ["W1-A01-C01"]
    assert er["overall_status"] == "insufficient"


def test_validator_rejects_unauthorized_er_denominator_and_freshness_upgrades() -> None:
    artifact = _artifact()
    artifact["atomic_claims"][0]["er_id"] = "PCB-ER-A05"
    with pytest.raises(ResearchProjectV2Error, match="not one of|unauthorized"):
        validate_assessment_artifact(_rehash(artifact), validate_locators=False)

    artifact = _artifact()
    artifact["atomic_claims"][0]["denominator"] = "unresolved"
    with pytest.raises(ResearchProjectV2Error, match="denominator"):
        validate_assessment_artifact(_rehash(artifact), validate_locators=False)

    artifact = _artifact()
    artifact["atomic_claims"][0]["confidence"] = "high"
    with pytest.raises(ResearchProjectV2Error, match="unknown-date"):
        validate_assessment_artifact(_rehash(artifact), validate_locators=False)


def test_validator_rejects_chain_inflation_and_downstream_scope() -> None:
    artifact = _artifact()
    artifact["evidence_chain_register"] = [
        {
            "chain_id": "evidence_chain:isola-1",
            "source_owner": "Isola",
                "artifact_ids": ["evidence_artifact:a"],
            "independence_group": "isola_supplier_materials",
        },
        {
            "chain_id": "evidence_chain:isola-2",
            "source_owner": "Isola",
                "artifact_ids": ["evidence_artifact:b"],
            "independence_group": "isola_supplier_materials",
        },
    ]
    with pytest.raises(ResearchProjectV2Error, match="independence group"):
        validate_assessment_artifact(_rehash(artifact), validate_locators=False)

    artifact = _artifact()
    artifact["governance"]["stage_b_authorized"] = True
    with pytest.raises(ResearchProjectV2Error, match="False was expected|downstream"):
        validate_assessment_artifact(_rehash(artifact), validate_locators=False)


def test_report_is_deterministic_projection() -> None:
    artifact = _artifact()
    report = render_assessment_report(artifact)
    assert report.startswith(b"# AI PCB Targeted Evidence Assessment Wave 1 v1")
    validate_persisted_assessment_report(artifact, report)
    with pytest.raises(ResearchProjectV2Error):
        validate_persisted_assessment_report(artifact, report + b"extra\n")


def test_materialized_wave_1_assessment_is_strictly_bound_and_consistent() -> None:
    root = Path(__file__).resolve().parents[1]
    artifact_path = (
        root
        / "artifacts/research_projects/v2_1/analysis/ai_pcb_targeted_evidence_assessment_wave_1_v1.json"
    )
    report_path = (
        root
        / "artifacts/research_projects/v2_1/reports/ai_pcb_targeted_evidence_assessment_wave_1_v1.md"
    )
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    validated = validate_assessment_artifact(artifact)
    validate_persisted_assessment_report(validated, report_path.read_bytes())

    assert len(validated["atomic_claims"]) == 25
    assert {row["er_id"] for row in validated["er_assessments"]} == set(AUTHORIZED_ER_IDS)
    assert {row["overall_status"] for row in validated["er_assessments"]} <= {
        "insufficient",
        "open",
    }
    counts = {
        status: sum(
            claim["assessment_status"] == status
            for claim in validated["atomic_claims"]
        )
        for status in ("sufficient", "insufficient", "conflicted", "open", "not_assessable")
    }
    assert counts == {
        "sufficient": 16,
        "insufficient": 3,
        "conflicted": 0,
        "open": 4,
        "not_assessable": 2,
    }
    er_map = {row["er_id"]: row for row in validated["er_assessments"]}
    assert er_map["PCB-ER-A02"]["independent_evidence_chain_count"] == 1
    assert er_map["PCB-ER-B01"]["independent_evidence_chain_count"] == 1
    assert validated["governance"] == {
        "network_access": False,
        "new_acquisition": False,
        "cognition_update": False,
        "gap_review_update": False,
        "gate_update": False,
        "company_mapping_authorized": False,
        "stage_a2_authorized": False,
        "stage_b_authorized": False,
        "wave_1b_authorized": False,
    }


def test_targeted_assessment_exact_allowlist_blocks_upstream_and_downstream_changes() -> None:
    root = Path(__file__).resolve().parents[1]
    allowlist = json.loads(
        (
            root
            / "artifacts/research_projects/v2_1/governance/targeted_evidence_assessment_wave_1_exact_allowlist.json"
        ).read_text(encoding="utf-8")
    )
    changed = set(
        subprocess.check_output(
            [
                "git",
                "diff",
                "--name-only",
                f"{allowlist['baseline_commit']}..{TARGETED_ASSESSMENT_WAVE_1_END_COMMIT}",
            ],
            cwd=root,
            text=True,
        ).splitlines()
    )
    assert changed <= set(allowlist["paths"])
    assert not any(
        path.startswith(tuple(allowlist["forbidden_prefixes"])) for path in changed
    )
    immutable_inputs = {
        "artifacts/research_projects/v2_1/acquisition/wave_1/acquisition_checkpoint.json",
        "artifacts/research_projects/v2_1/governance/ai_pcb_targeted_acquisition_gate_decision_v1.json",
        "artifacts/research_projects/v2_1/analysis/ai_pcb_industry_cognition_package_v1.json",
        "artifacts/research_projects/v2_1/analysis/ai_pcb_evidence_gap_review_and_targeted_research_design_v1.json",
    }
    assert not changed.intersection(immutable_inputs)
