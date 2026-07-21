from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.cognition import (
    validate_baseline_bindings,
    validate_evidence_locator,
)
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload


PROVENANCE = {
    "created_by": "Codex",
    "actor_type": "codex",
    "agent_run_id": "cognition-test",
    "created_at": "2026-07-21T00:00:00Z",
    "created_in_version": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
    "review_status": "reviewed",
}
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_ID = "acquisition_checkpoint:a5f7627d8726c9405ba67a75"
CHECKPOINT_HASH = "a5f7627d8726c9405ba67a7527826edb0cff26ee777287e33cb55442bace660e"
SCOPE_PATH = "governance/stage_a_scope_correction_v1.json"
SCOPE_HASH = "d4feb7bce9b6598a2106e0de9d3d7afd1de60e22146efa25ba251e99bab71b07"
ARTIFACT_ID = "evidence_artifact:222da3eb56146c9604f09fca"
DOCUMENT_ID = "normalized_document:aa0d4f097afc3db709bcfad1"
SECTION_HASH = "f768be3cedce308a34d2b4f31407dd1108d83a026c9e6abd2b9c10ec76b756d0"


def minimal_package() -> dict:
    return {
        "schema_version": "2.5.0",
        "artifact_type": "industry_cognition_package",
        "package_id": "industry_cognition_package:ai_pcb:v1",
        "project_id": "research_project:ai_compute_pcb_industry_bottleneck",
        "renderer_version": "industry_cognition_markdown_v1",
        "baseline_bindings": {},
        "research_framing": {},
        "research_question_tree": [],
        "evidence_inventory": {},
        "er_assessments": [],
        "claim_assessment_ledger": [],
        "grounded_system_model": {"nodes": [], "edges": []},
        "unverified_system_extensions": [],
        "evidence_grounded_mechanisms": [],
        "unverified_mechanism_skeletons": [],
        "grounded_causal_edges": [],
        "hypothesized_causal_edges": [],
        "technology_route_comparisons": [],
        "limited_system_bottleneck_judgments": [],
        "value_change_hypotheses": [],
        "contradictions_and_uncertainties": [],
        "evidence_gap_referrals": [],
        "verification_and_falsification": [],
        "provenance": PROVENANCE,
        "content_hash": "0" * 64,
    }


def minimal_audit() -> dict:
    return {
        "schema_version": "2.5.0",
        "artifact_type": "industry_cognition_audit",
        "audit_id": "industry_cognition_audit:ai_pcb:v1",
        "package_id": "industry_cognition_package:ai_pcb:v1",
        "package_content_hash": "a" * 64,
        "report_content_hash": "b" * 64,
        "renderer_version": "industry_cognition_markdown_v1",
        "capability_rule_version": "industry_cognition_capability_v1",
        "domain_matrix_version": "industry_cognition_domains_v1",
        "audit_question_set_version": "industry_cognition_audit_questions_v1",
        "domain_coverage": [],
        "computed_capability": {},
        "coverage_metrics": {},
        "audit_answers": [],
        "violations": [],
        "warnings": [],
        "content_hash": "0" * 64,
    }


def test_schema_v2_5_accepts_package_and_rejects_capability_fields() -> None:
    package = minimal_package()
    validate_v2_1_schema_payload("industry_cognition_baseline_v2_5", package)
    package["overall_capability"] = "complete"
    with pytest.raises(ResearchProjectV2Error):
        validate_v2_1_schema_payload("industry_cognition_baseline_v2_5", package)


def test_schema_v2_5_accepts_audit_and_rejects_cognition_objects() -> None:
    audit = minimal_audit()
    validate_v2_1_schema_payload("industry_cognition_baseline_v2_5", audit)
    audit["claim_assessment_ledger"] = []
    with pytest.raises(ResearchProjectV2Error):
        validate_v2_1_schema_payload("industry_cognition_baseline_v2_5", audit)


@pytest.mark.parametrize("artifact_type", ["package", "audit", "report"])
def test_schema_v2_5_rejects_unknown_discriminator(artifact_type: str) -> None:
    payload = deepcopy(minimal_package())
    payload["artifact_type"] = artifact_type
    with pytest.raises(ResearchProjectV2Error):
        validate_v2_1_schema_payload("industry_cognition_baseline_v2_5", payload)


def package_with_real_bindings() -> dict:
    package = minimal_package()
    package["baseline_bindings"] = {
        "acquisition_checkpoint": {
            "checkpoint_id": CHECKPOINT_ID,
            "content_hash": CHECKPOINT_HASH,
        },
        "scope_correction": {"relative_path": SCOPE_PATH, "content_hash": SCOPE_HASH},
    }
    return package


def real_locator() -> dict:
    return {
        "artifact_id": ARTIFACT_ID,
        "normalized_document_id": DOCUMENT_ID,
        "section_index": 43,
        "section_hash": SECTION_HASH,
        "heading": "DGX H100/H200 Component Descriptions#",
        "locator_note": "Direct product specification for NVLink bandwidth.",
    }


def _copy_managed_file(source_root: Path, target_root: Path, relative: Path) -> None:
    target = target_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_root / relative, target)


def temporary_real_layout(tmp_path: Path) -> LayeredResearchLayout:
    source = REPOSITORY_ROOT / "artifacts/research_projects/v2_1"
    target = tmp_path / "v2_1"
    shutil.copytree(source / "schema", target / "schema")
    _copy_managed_file(
        source,
        target,
        Path("acquisition/checkpoints") / f"{CHECKPOINT_ID}.json",
    )
    _copy_managed_file(source, target, Path(SCOPE_PATH))
    metadata_relative = Path("evidence/metadata_v2_3") / f"{ARTIFACT_ID}.json"
    _copy_managed_file(source, target, metadata_relative)
    metadata = json.loads((source / metadata_relative).read_text())["evidence_artifact"]
    _copy_managed_file(source, target, Path(metadata["raw_artifact_path"]))
    _copy_managed_file(
        source,
        target,
        Path("evidence/normalized") / f"{DOCUMENT_ID}.json",
    )
    return LayeredResearchLayout(target)


def test_validate_package_rejects_checkpoint_or_scope_hash_drift(tmp_path: Path) -> None:
    layout = temporary_real_layout(tmp_path)
    package = package_with_real_bindings()
    validate_baseline_bindings(package, layout=layout)

    package["baseline_bindings"]["scope_correction"]["content_hash"] = "f" * 64
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_baseline_bindings(package, layout=layout)
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_COGNITION_UPSTREAM_DRIFT"


def test_validate_locator_requires_raw_normalized_traceability(tmp_path: Path) -> None:
    layout = temporary_real_layout(tmp_path)
    validated = validate_evidence_locator(real_locator(), layout=layout)
    assert validated["section_hash"] == SECTION_HASH

    metadata_path = layout.evidence_metadata_v2_3_dir / f"{ARTIFACT_ID}.json"
    wrapper = json.loads(metadata_path.read_text())
    wrapper["evidence_artifact"]["content_hash"] = "e" * 64
    metadata_path.write_bytes(canonical_bytes(wrapper))
    with pytest.raises(ResearchProjectV2Error):
        validate_evidence_locator(real_locator(), layout=layout)


def test_validate_locator_rejects_section_hash_drift(tmp_path: Path) -> None:
    layout = temporary_real_layout(tmp_path)
    locator = real_locator()
    locator["section_hash"] = "f" * 64
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        validate_evidence_locator(locator, layout=layout)
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_COGNITION_LOCATOR_INVALID"
