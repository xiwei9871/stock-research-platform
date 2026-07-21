from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.cognition import (
    calculate_claim_grounding,
    calculate_er_assessment,
    validate_baseline_bindings,
    validate_causal_edges,
    validate_evidence_locator,
    validate_grounded_mechanisms,
    validate_judgment_boundaries,
    validate_cognition_package,
)
from stock_research.research_project_v2_1.cognition_audit import (
    compute_audit,
    compute_capability,
    compute_domain_coverage,
    validate_persisted_audit,
)
from stock_research.research_project_v2_1.cognition_render import (
    canonical_render_hash,
    render_cognition_report,
    validate_persisted_report,
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


def grounded_claim_fixture() -> dict:
    return {
        "claim_id": "CLM-001",
        "claim_type": "fact",
        "claim_scope": "product_fact",
        "assessment_status": "sufficient",
        "assessment_confidence": "medium",
        "unresolved_contradiction": False,
        "evidence_links": [
            {
                "link_id": "EL-001",
                "evidence_stance": "support",
                "source_chain_id": "CHAIN-001",
                "freshness_status": "unknown",
                "locator_id": "LOC-001",
            }
        ],
        "grounding_status": "grounded",
    }


def test_calculate_claim_grounding_uses_direct_support_and_chain_count() -> None:
    result = calculate_claim_grounding(
        grounded_claim_fixture(),
        inventory={"source_chains": [{"source_chain_id": "CHAIN-001"}]},
        valid_locators={"LOC-001": real_locator()},
    )
    assert result == {
        "grounding_status": "grounded",
        "independent_chain_count": 1,
        "confidence_ceiling": "medium",
        "blockers": [],
    }


def test_contextual_only_evidence_does_not_ground_claim() -> None:
    claim = grounded_claim_fixture()
    claim["evidence_links"][0]["evidence_stance"] = "contextual"
    claim["grounding_status"] = "not_grounded"
    result = calculate_claim_grounding(
        claim,
        inventory={"source_chains": [{"source_chain_id": "CHAIN-001"}]},
        valid_locators={"LOC-001": real_locator()},
    )
    assert result["grounding_status"] == "not_grounded"
    assert "no_direct_support" in result["blockers"]


def test_unknown_date_cannot_receive_definite_freshness() -> None:
    claim = grounded_claim_fixture()
    claim["evidence_links"][0]["freshness_status"] = "confirmed_current"
    claim["evidence_links"][0]["source_date_status"] = "unknown"
    with pytest.raises(ResearchProjectV2Error) as exc_info:
        calculate_claim_grounding(
            claim,
            inventory={"source_chains": [{"source_chain_id": "CHAIN-001"}]},
            valid_locators={"LOC-001": real_locator()},
        )
    assert exc_info.value.code == "RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED"


def test_claim_confidence_cannot_exceed_calculated_ceiling() -> None:
    claim = grounded_claim_fixture()
    claim["assessment_confidence"] = "high"
    with pytest.raises(ResearchProjectV2Error):
        calculate_claim_grounding(
            claim,
            inventory={"source_chains": [{"source_chain_id": "CHAIN-001"}]},
            valid_locators={"LOC-001": real_locator()},
        )


def test_exact_duplicate_links_count_as_one_chain() -> None:
    claim = grounded_claim_fixture()
    claim["evidence_links"].append(
        {
            **claim["evidence_links"][0],
            "link_id": "EL-002",
            "locator_id": "LOC-002",
        }
    )
    result = calculate_claim_grounding(
        claim,
        inventory={"source_chains": [{"source_chain_id": "CHAIN-001"}]},
        valid_locators={"LOC-001": real_locator(), "LOC-002": real_locator()},
    )
    assert result["independent_chain_count"] == 1


def test_er_assessment_is_recomputed_from_atomic_claims() -> None:
    er = {
        "requirement_id": "ER01",
        "assessed_claim_ids": ["CLM-001", "CLM-002"],
        "sufficient_claim_ids": ["CLM-001"],
        "open_claim_ids": ["CLM-002"],
        "conflicted_claim_ids": [],
        "missing_claim_ids": [],
        "governance_requirements": {"independent_secondary_required": True},
        "unresolved_requirements": ["independent_secondary_missing"],
        "overall_status": "insufficient",
    }
    claims = {
        "CLM-001": {"assessment_status": "sufficient"},
        "CLM-002": {"assessment_status": "open"},
    }
    result = calculate_er_assessment(er, claims)
    assert result["overall_status"] == "insufficient"
    assert result["open_claim_ids"] == ["CLM-002"]


def semantic_package_fixture() -> dict:
    package = minimal_package()
    package["claim_assessment_ledger"] = [
        {
            "claim_id": "CLM-REL",
            "claim_scope": "relationship",
            "grounding_status": "grounded",
            "assessment_confidence": "medium",
        },
        {
            "claim_id": "CLM-CTX",
            "claim_scope": "context",
            "grounding_status": "not_grounded",
            "assessment_confidence": "low",
        },
    ]
    package["evidence_grounded_mechanisms"] = [
        {
            "mechanism_id": "MECH-001",
            "confidence": "medium",
            "explanation_steps": [
                {"statement": "Relationship step", "supporting_claim_ids": ["CLM-REL"]}
            ],
            "key_variable_grounding": [
                {"variable": "bandwidth", "supporting_claim_ids": ["CLM-REL"]}
            ],
        }
    ]
    package["grounded_system_model"] = {
        "nodes": [
            {"node_id": "NODE-A", "grounding_status": "grounded"},
            {"node_id": "NODE-B", "grounding_status": "grounded"},
        ],
        "edges": [],
    }
    package["grounded_causal_edges"] = [
        {
            "edge_id": "EDGE-001",
            "from_node": "NODE-A",
            "to_node": "NODE-B",
            "mechanism_id": "MECH-001",
            "supporting_claim_ids": ["CLM-REL"],
            "necessary_conditions": ["condition"],
            "alternative_explanations": ["alternative"],
            "failure_conditions": ["failure"],
            "confidence": "medium",
        }
    ]
    return package


def test_grounded_mechanism_rejects_skeleton_or_contextual_claims() -> None:
    package = semantic_package_fixture()
    package["evidence_grounded_mechanisms"][0]["explanation_steps"][0][
        "supporting_claim_ids"
    ] = ["CLM-CTX"]
    claims = {row["claim_id"]: row for row in package["claim_assessment_ledger"]}
    with pytest.raises(ResearchProjectV2Error):
        validate_grounded_mechanisms(package, claims)


def test_grounded_edge_requires_relationship_claim_not_endpoint_facts_only() -> None:
    package = semantic_package_fixture()
    package["claim_assessment_ledger"][0]["claim_scope"] = "product_fact"
    claims = {row["claim_id"]: row for row in package["claim_assessment_ledger"]}
    validate_grounded_mechanisms(package, claims)
    with pytest.raises(ResearchProjectV2Error):
        validate_causal_edges(package, claims)


def test_hypothesized_edges_cannot_compose_into_grounded_chain() -> None:
    package = semantic_package_fixture()
    package["grounded_causal_edges"][0]["depends_on_edge_ids"] = ["HEDGE-001"]
    package["hypothesized_causal_edges"] = [
        {"edge_id": "HEDGE-001", "status": "unverified_hypothesis", "evidence_gap_ids": ["GAP-001"]}
    ]
    claims = {row["claim_id"]: row for row in package["claim_assessment_ledger"]}
    with pytest.raises(ResearchProjectV2Error):
        validate_causal_edges(package, claims)


def test_pcb_domains_are_forbidden_in_limited_bottleneck_judgments() -> None:
    package = semantic_package_fixture()
    package["limited_system_bottleneck_judgments"] = [
        {"bottleneck_id": "BOT-001", "domain": "pcb_manufacturing", "assessment_reason": "unsupported"}
    ]
    with pytest.raises(ResearchProjectV2Error):
        validate_judgment_boundaries(package)


def test_value_hypotheses_have_only_open_gap_linked_or_ineligible_status() -> None:
    package = semantic_package_fixture()
    package["value_change_hypotheses"] = [
        {"hypothesis_id": "VAL-001", "status": "supported", "target_scope": "industry_segment"}
    ]
    with pytest.raises(ResearchProjectV2Error):
        validate_judgment_boundaries(package)


def capability_package_fixture() -> dict:
    package = minimal_package()
    package["content_hash"] = "a" * 64
    package["evidence_grounded_mechanisms"] = [
        {"mechanism_id": "MECH-A", "domain": "ai_system_architecture"},
        {"mechanism_id": "MECH-B", "domain": "accelerator_interconnect"},
        {"mechanism_id": "MECH-C", "domain": "network_fabric"},
        {"mechanism_id": "MECH-D", "domain": "dpu"},
        {"mechanism_id": "MECH-E", "domain": "optical_boundary"},
    ]
    package["unverified_mechanism_skeletons"] = [
        {"skeleton_id": "SKEL-001", "domain": "signal_integrity"}
    ]
    package["evidence_gap_referrals"] = [
        {"gap_id": "GAP-MAT", "domain": "pcb_materials", "status": "not_assessable"},
        {"gap_id": "GAP-MFG", "domain": "pcb_manufacturing", "status": "not_assessable"},
        {"gap_id": "GAP-TST", "domain": "pcb_testing", "status": "not_assessable"},
        {"gap_id": "GAP-YLD", "domain": "yield", "status": "not_assessable"},
        {"gap_id": "GAP-CAP", "domain": "effective_capacity", "status": "not_assessable"},
    ]
    return package


def test_domain_matrix_distinguishes_grounded_skeleton_and_not_assessable() -> None:
    coverage = {row["domain"]: row["status"] for row in compute_domain_coverage(capability_package_fixture())}
    assert coverage["accelerator_interconnect"] == "evidence_grounded"
    assert coverage["signal_integrity"] == "unverified_skeleton_only"
    assert coverage["pcb_manufacturing"] == "not_assessable"


def test_skeletons_never_raise_domain_coverage() -> None:
    package = capability_package_fixture()
    package["evidence_grounded_mechanisms"] = []
    package["unverified_mechanism_skeletons"].append(
        {"skeleton_id": "SKEL-A", "domain": "ai_system_architecture"}
    )
    coverage = {row["domain"]: row["status"] for row in compute_domain_coverage(package)}
    assert coverage["ai_system_architecture"] == "unverified_skeleton_only"


def test_missing_pcb_domains_caps_full_cognition_and_mapping_readiness() -> None:
    package = capability_package_fixture()
    capability = compute_capability(package, compute_domain_coverage(package))
    assert capability == {
        "overall_capability": "partial_industry_cognition_demand_side_only",
        "ai_system_interconnect_cognition": "evidence_grounded",
        "signal_integrity_and_pcb_mechanism_cognition": "unverified_skeleton_only",
        "pcb_material_and_manufacturing_cognition": "not_assessable",
        "pcb_industry_bottleneck_judgment": "not_available",
        "full_ai_pcb_industry_cognition": "not_achieved",
        "company_mapping_readiness": False,
        "next_required_action": "evidence_gap_review",
        "automatic_gap_acquisition_authorized": False,
    }


def test_persisted_audit_must_equal_recomputed_audit() -> None:
    package = capability_package_fixture()
    expected = compute_audit(package, b"report\n")
    validate_persisted_audit(deepcopy(expected), expected)
    drifted = deepcopy(expected)
    drifted["computed_capability"]["company_mapping_readiness"] = True
    with pytest.raises(ResearchProjectV2Error):
        validate_persisted_audit(drifted, expected)


def test_eight_audit_answers_include_supporting_and_blocking_ids() -> None:
    audit = compute_audit(capability_package_fixture(), b"report\n")
    assert len(audit["audit_answers"]) == 8
    assert all(row["calculation_rule"] for row in audit["audit_answers"])
    assert all(
        "supporting_object_ids" in row and "blocking_object_ids" in row
        for row in audit["audit_answers"]
    )


def render_package_fixture() -> dict:
    package = capability_package_fixture()
    package["research_framing"] = {
        "topic": "AI compute interconnect and PCB cognition baseline",
        "objective": "Bound existing cognition without filling evidence gaps.",
        "model_scope": "demand_side_and_system_interconnect",
        "included_scope": ["AI system interconnect"],
        "excluded_scope": ["company mapping"],
        "limitations": ["PCB manufacturing evidence is unavailable."],
    }
    package["claim_assessment_ledger"] = [
        {
            "claim_id": "CLM-002",
            "claim_text": "Second claim.",
            "claim_type": "inference",
            "assessment_status": "insufficient",
            "assessment_confidence": "low",
            "grounding_status": "not_grounded",
            "evidence_links": [],
            "limitations": ["Limited evidence."],
        },
        {
            "claim_id": "CLM-001",
            "claim_text": "First grounded claim.",
            "claim_type": "fact",
            "assessment_status": "sufficient",
            "assessment_confidence": "medium",
            "grounding_status": "grounded",
            "evidence_links": [
                {
                    "artifact_id": ARTIFACT_ID,
                    "normalized_document_id": DOCUMENT_ID,
                    "section_index": 43,
                    "section_hash": SECTION_HASH,
                }
            ],
            "limitations": ["Product-specific evidence."],
        },
    ]
    package["unverified_mechanism_skeletons"] = [
        {
            "skeleton_id": "SKEL-001",
            "domain": "signal_integrity",
            "research_question": "How does rate affect signal integrity?",
            "status": "unverified_hypothesis",
            "evidence_gap_ids": ["GAP-001"],
        }
    ]
    package["evidence_gap_referrals"] = [
        {
            "gap_id": "GAP-001",
            "domain": "signal_integrity",
            "blocked_question": "Signal integrity mechanism",
            "why_insufficient": "No engineering evidence was acquired.",
            "required_evidence_types": ["signal integrity standard"],
            "automatic_acquisition_authorized": False,
        }
    ]
    package["contradictions_and_uncertainties"] = [
        {
            "uncertainty_id": "UNC-001",
            "domain": "network_fabric",
            "uncertainty_type": "unknown_date",
            "summary": "Publication date remains unknown.",
        }
    ]
    return package


def test_render_report_is_canonical_and_order_independent() -> None:
    first = render_package_fixture()
    second = deepcopy(first)
    second["claim_assessment_ledger"].reverse()
    rendered = render_cognition_report(first)
    assert rendered == render_cognition_report(second)
    assert rendered.endswith(b"\n") and not rendered.endswith(b"\n\n")
    assert b"\r" not in rendered
    assert canonical_render_hash(first) == canonical_render_hash(second)


def test_render_report_contains_clear_grounded_skeleton_gap_labels() -> None:
    text = render_cognition_report(render_package_fixture()).decode("utf-8")
    assert "[GROUNDED]" in text
    assert "[SKELETON — NOT VERIFIED]" in text
    assert "[EVIDENCE GAP]" in text
    assert "[UNCERTAINTY]" in text
    assert "Evidence: evidence_artifact:" in text


def test_validate_report_rejects_added_claim_or_hash_drift() -> None:
    package = render_package_fixture()
    report = render_cognition_report(package)
    validate_persisted_report(package, report)
    with pytest.raises(ResearchProjectV2Error):
        validate_persisted_report(package, report + b"Unregistered conclusion.\n")


def test_validate_cognition_package_recomputes_grounding_and_scope(tmp_path: Path) -> None:
    layout = temporary_real_layout(tmp_path)
    package = package_with_real_bindings()
    locator = {"locator_id": "LOC-001", **real_locator()}
    package["evidence_inventory"] = {
        "locators": [locator],
        "source_chains": [{"source_chain_id": "CHAIN-001"}],
    }
    claim = grounded_claim_fixture()
    claim["evidence_links"][0].update(
        {
            "artifact_id": ARTIFACT_ID,
            "normalized_document_id": DOCUMENT_ID,
            "section_index": 43,
            "section_hash": SECTION_HASH,
            "source_date_status": "unknown",
        }
    )
    package["claim_assessment_ledger"] = [claim]
    package["research_framing"] = {
        "model_scope": "demand_side_and_system_interconnect",
        "company_mapping_authorized": False,
        "stage_a2_authorized": False,
        "stage_b_authorized": False,
    }
    package["content_hash"] = content_sha256(
        package, excluded_paths={("content_hash",)}
    )
    result = validate_cognition_package(package, layout=layout)
    assert result["grounded_claim_ids"] == ["CLM-001"]
    assert result["scope_leakage"] == []


def test_repository_ai_pcb_cognition_package_is_valid_and_strictly_bounded() -> None:
    layout = LayeredResearchLayout.default()
    path = layout.analysis_dir / "ai_pcb_industry_cognition_package_v1.json"
    package = json.loads(path.read_text(encoding="utf-8"))
    result = validate_cognition_package(package, layout=layout)
    assert result["scope_leakage"] == []
    assert len(package["er_assessments"]) == 5
    assert package["research_framing"]["model_scope"] == (
        "demand_side_and_system_interconnect"
    )
    assert package["research_framing"]["company_mapping_authorized"] is False
    assert package["research_framing"]["stage_a2_authorized"] is False
    assert package["research_framing"]["stage_b_authorized"] is False
