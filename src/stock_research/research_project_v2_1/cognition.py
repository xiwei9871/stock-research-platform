from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.loader import (
    read_layered_bytes,
    read_layered_canonical_json,
)
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload


CONFIDENCE_ORDER = {"very_low": 0, "low": 1, "medium": 2, "high": 3}
ALLOWED_LIMITED_BOTTLENECK_DOMAINS = {
    "ai_system_architecture",
    "accelerator_interconnect",
    "network_fabric",
    "dpu",
    "optical_boundary",
}
ALLOWED_VALUE_STATUSES = {
    "open",
    "evidence_gap_linked",
    "not_eligible_for_judgment",
}


def _error(message: str, *, code: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(message, code=code, details=details)


def load_cognition_package(
    path: Path,
    *,
    layout: LayeredResearchLayout | None = None,
) -> dict[str, Any]:
    effective = LayeredResearchLayout.default() if layout is None else layout
    try:
        relative = path.relative_to(effective.root)
    except ValueError as exc:
        raise _error(
            "Cognition package is outside the managed root",
            code="RESEARCH_PROJECT_V2_1_COGNITION_INPUT_MISSING",
            path=str(path),
        ) from exc
    payload = read_layered_canonical_json(relative, layout=effective)
    validate_v2_1_schema_payload(
        "industry_cognition_baseline_v2_5", payload, layout=effective
    )
    expected = content_sha256(payload, excluded_paths={("content_hash",)})
    if payload["content_hash"] != expected:
        raise _error(
            "Cognition package content hash mismatch",
            code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
            field="content_hash",
        )
    return payload


def validate_baseline_bindings(
    package: dict[str, Any],
    *,
    layout: LayeredResearchLayout,
) -> None:
    bindings = package.get("baseline_bindings")
    if not isinstance(bindings, dict):
        raise _error(
            "Cognition baseline bindings are missing",
            code="RESEARCH_PROJECT_V2_1_COGNITION_INPUT_MISSING",
            field="baseline_bindings",
        )
    checkpoint_ref = bindings.get("acquisition_checkpoint")
    scope_ref = bindings.get("scope_correction")
    if not isinstance(checkpoint_ref, dict) or not isinstance(scope_ref, dict):
        raise _error(
            "Cognition upstream binding is missing",
            code="RESEARCH_PROJECT_V2_1_COGNITION_INPUT_MISSING",
            field="baseline_bindings",
        )
    checkpoint_id = checkpoint_ref.get("checkpoint_id")
    checkpoint = read_layered_canonical_json(
        f"acquisition/checkpoints/{checkpoint_id}.json", layout=layout
    ).get("acquisition_checkpoint")
    if not isinstance(checkpoint, dict) or checkpoint.get("content_hash") != checkpoint_ref.get(
        "content_hash"
    ):
        raise _error(
            "Acquisition checkpoint binding drifted",
            code="RESEARCH_PROJECT_V2_1_COGNITION_UPSTREAM_DRIFT",
            field="baseline_bindings.acquisition_checkpoint",
        )
    scope_path = scope_ref.get("relative_path")
    scope = read_layered_canonical_json(str(scope_path), layout=layout)
    if scope.get("content_hash") != scope_ref.get("content_hash"):
        raise _error(
            "Scope correction binding drifted",
            code="RESEARCH_PROJECT_V2_1_COGNITION_UPSTREAM_DRIFT",
            field="baseline_bindings.scope_correction",
        )


def validate_evidence_locator(
    locator: dict[str, Any],
    *,
    layout: LayeredResearchLayout,
) -> dict[str, Any]:
    copied = deepcopy(locator)
    artifact_id = copied.get("artifact_id")
    document_id = copied.get("normalized_document_id")
    section_index = copied.get("section_index")
    section_hash = copied.get("section_hash")
    if not isinstance(artifact_id, str) or not isinstance(document_id, str):
        raise _error(
            "Evidence locator identity is invalid",
            code="RESEARCH_PROJECT_V2_1_COGNITION_LOCATOR_INVALID",
            field="artifact_id",
        )
    metadata_wrapper = read_layered_canonical_json(
        f"evidence/metadata_v2_3/{artifact_id}.json", layout=layout
    )
    artifact = metadata_wrapper.get("evidence_artifact")
    if not isinstance(artifact, dict) or artifact.get("evidence_artifact_id") != artifact_id:
        raise _error(
            "Evidence artifact binding is invalid",
            code="RESEARCH_PROJECT_V2_1_COGNITION_LOCATOR_INVALID",
            field="artifact_id",
        )
    raw_path = artifact.get("raw_artifact_path")
    raw = read_layered_bytes(str(raw_path), layout=layout, max_bytes=32 * 1024 * 1024)
    if sha256(raw).hexdigest() != artifact.get("content_hash"):
        raise _error(
            "Raw evidence content hash drifted",
            code="RESEARCH_PROJECT_V2_1_COGNITION_UPSTREAM_DRIFT",
            field="raw_artifact_path",
        )
    document_wrapper = read_layered_canonical_json(
        f"evidence/normalized/{document_id}.json", layout=layout
    )
    document = document_wrapper.get("normalized_document")
    if (
        not isinstance(document, dict)
        or document.get("document_id") != document_id
        or document.get("artifact_id") != artifact_id
    ):
        raise _error(
            "Normalized evidence does not trace to the raw artifact",
            code="RESEARCH_PROJECT_V2_1_COGNITION_LOCATOR_INVALID",
            field="normalized_document_id",
        )
    sections = document.get("sections")
    if not isinstance(section_index, int) or not isinstance(sections, list):
        raise _error(
            "Evidence section index is invalid",
            code="RESEARCH_PROJECT_V2_1_COGNITION_LOCATOR_INVALID",
            field="section_index",
        )
    try:
        section = sections[section_index]
    except IndexError as exc:
        raise _error(
            "Evidence section is missing",
            code="RESEARCH_PROJECT_V2_1_COGNITION_LOCATOR_INVALID",
            field="section_index",
        ) from exc
    if not isinstance(section, dict) or section.get("section_hash") != section_hash:
        raise _error(
            "Evidence section hash drifted",
            code="RESEARCH_PROJECT_V2_1_COGNITION_LOCATOR_INVALID",
            field="section_hash",
        )
    copied["section_id"] = section.get("section_id")
    copied["section_text"] = section.get("text")
    return copied


def canonical_package_bytes(package: dict[str, Any]) -> bytes:
    return canonical_bytes(package)


def calculate_claim_grounding(
    claim: dict[str, Any],
    *,
    inventory: dict[str, Any],
    valid_locators: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    links = claim.get("evidence_links")
    if not isinstance(links, list):
        links = []
    direct_chains: set[str] = set()
    blockers: list[str] = []
    for link in links:
        if not isinstance(link, dict):
            continue
        if link.get("source_date_status") == "unknown" and link.get(
            "freshness_status"
        ) == "confirmed_current":
            raise _error(
                "Unknown-date evidence cannot be assigned definite freshness",
                code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
                field="freshness_status",
            )
        if link.get("evidence_stance") == "support" and link.get(
            "locator_id"
        ) in valid_locators:
            chain_id = link.get("source_chain_id")
            if isinstance(chain_id, str):
                direct_chains.add(chain_id)
    if not direct_chains:
        blockers.append("no_direct_support")
    if claim.get("claim_type") == "hypothesis":
        blockers.append("hypothesis_not_grounded")
    if claim.get("assessment_status") != "sufficient":
        blockers.append("assessment_not_sufficient")
    ceiling = "high"
    if len(direct_chains) < 2 or any(
        link.get("freshness_status") == "unknown"
        for link in links
        if isinstance(link, dict)
    ):
        ceiling = "medium"
    if claim.get("unresolved_contradiction"):
        ceiling = "low"
        blockers.append("unresolved_contradiction")
    declared_confidence = claim.get("assessment_confidence")
    if declared_confidence not in CONFIDENCE_ORDER:
        raise _error(
            "Claim assessment confidence is invalid",
            code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
            field="assessment_confidence",
        )
    if CONFIDENCE_ORDER[declared_confidence] > CONFIDENCE_ORDER[ceiling]:
        raise _error(
            "Claim confidence exceeds the calculated ceiling",
            code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
            field="assessment_confidence",
            ceiling=ceiling,
        )
    grounding_status = "grounded" if not blockers else "not_grounded"
    if claim.get("grounding_status") != grounding_status:
        raise _error(
            "Claim grounding status does not match calculation",
            code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
            field="grounding_status",
            calculated=grounding_status,
        )
    known_chains = {
        row.get("source_chain_id")
        for row in inventory.get("source_chains", [])
        if isinstance(row, dict)
    }
    if not direct_chains <= known_chains:
        raise _error(
            "Claim references an unknown evidence chain",
            code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
            field="source_chain_id",
        )
    return {
        "grounding_status": grounding_status,
        "independent_chain_count": len(direct_chains),
        "confidence_ceiling": ceiling,
        "blockers": blockers,
    }


def calculate_er_assessment(
    er: dict[str, Any],
    claims_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    assessed = list(er.get("assessed_claim_ids", []))
    missing = [claim_id for claim_id in assessed if claim_id not in claims_by_id]
    sufficient = [
        claim_id
        for claim_id in assessed
        if claims_by_id.get(claim_id, {}).get("assessment_status") == "sufficient"
    ]
    opened = [
        claim_id
        for claim_id in assessed
        if claims_by_id.get(claim_id, {}).get("assessment_status")
        in {"open", "insufficient", "not_assessable"}
    ]
    conflicted = [
        claim_id
        for claim_id in assessed
        if claims_by_id.get(claim_id, {}).get("assessment_status") == "conflicted"
    ]
    unresolved = list(er.get("unresolved_requirements", []))
    if conflicted:
        status = "conflicted"
    elif missing or opened or unresolved:
        status = "insufficient"
    else:
        status = "sufficient"
    if er.get("resolution_code") == "denominator_unresolved":
        status = "open"
    if er.get("overall_status") != status:
        raise _error(
            "ER overall status does not match atomic claims",
            code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
            field="overall_status",
            calculated=status,
        )
    return {
        "overall_status": status,
        "sufficient_claim_ids": sufficient,
        "open_claim_ids": opened,
        "conflicted_claim_ids": conflicted,
        "missing_claim_ids": missing,
    }


def validate_grounded_mechanisms(
    package: dict[str, Any],
    claims_by_id: dict[str, dict[str, Any]],
) -> None:
    for mechanism in package.get("evidence_grounded_mechanisms", []):
        claim_ids: set[str] = set()
        for step in mechanism.get("explanation_steps", []):
            if not step.get("statement") or not step.get("supporting_claim_ids"):
                raise _error(
                    "Grounded mechanism step lacks a statement or claims",
                    code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
                    mechanism_id=mechanism.get("mechanism_id"),
                )
            claim_ids.update(step["supporting_claim_ids"])
        for variable in mechanism.get("key_variable_grounding", []):
            claim_ids.update(variable.get("supporting_claim_ids", []))
        if not claim_ids:
            raise _error(
                "Grounded mechanism has no grounded claims",
                code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
                mechanism_id=mechanism.get("mechanism_id"),
            )
        ceilings: list[int] = []
        for claim_id in claim_ids:
            claim = claims_by_id.get(claim_id)
            if not claim or claim.get("grounding_status") != "grounded":
                raise _error(
                    "Grounded mechanism references an ungrounded claim",
                    code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
                    claim_id=claim_id,
                )
            ceilings.append(CONFIDENCE_ORDER[claim["assessment_confidence"]])
        confidence = mechanism.get("confidence")
        if confidence not in CONFIDENCE_ORDER or CONFIDENCE_ORDER[confidence] > min(
            ceilings
        ):
            raise _error(
                "Mechanism confidence exceeds its claim ceiling",
                code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
                mechanism_id=mechanism.get("mechanism_id"),
            )


def validate_causal_edges(
    package: dict[str, Any],
    claims_by_id: dict[str, dict[str, Any]],
) -> None:
    grounded_nodes = {
        row.get("node_id")
        for row in package.get("grounded_system_model", {}).get("nodes", [])
        if row.get("grounding_status") == "grounded"
    }
    grounded_mechanisms = {
        row.get("mechanism_id")
        for row in package.get("evidence_grounded_mechanisms", [])
    }
    hypothesized_ids = {
        row.get("edge_id") for row in package.get("hypothesized_causal_edges", [])
    }
    for edge in package.get("grounded_causal_edges", []):
        if edge.get("from_node") not in grounded_nodes or edge.get(
            "to_node"
        ) not in grounded_nodes:
            raise _error(
                "Grounded causal edge has an ungrounded endpoint",
                code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
                edge_id=edge.get("edge_id"),
            )
        if edge.get("mechanism_id") not in grounded_mechanisms:
            raise _error(
                "Grounded causal edge has no grounded mechanism",
                code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
                edge_id=edge.get("edge_id"),
            )
        if hypothesized_ids.intersection(edge.get("depends_on_edge_ids", [])):
            raise _error(
                "Grounded causal edge depends on a hypothesized bridge",
                code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
                edge_id=edge.get("edge_id"),
            )
        supporting = [claims_by_id.get(cid) for cid in edge.get("supporting_claim_ids", [])]
        if not any(
            claim
            and claim.get("grounding_status") == "grounded"
            and claim.get("claim_scope") == "relationship"
            for claim in supporting
        ):
            raise _error(
                "Grounded causal edge lacks relationship evidence",
                code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
                edge_id=edge.get("edge_id"),
            )
        for field in ("necessary_conditions", "alternative_explanations", "failure_conditions"):
            if not edge.get(field):
                raise _error(
                    "Grounded causal edge is missing a boundary field",
                    code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
                    edge_id=edge.get("edge_id"),
                    field=field,
                )


def validate_judgment_boundaries(package: dict[str, Any]) -> None:
    for judgment in package.get("limited_system_bottleneck_judgments", []):
        if judgment.get("domain") not in ALLOWED_LIMITED_BOTTLENECK_DOMAINS:
            raise _error(
                "PCB-domain bottleneck judgment is not authorized",
                code="RESEARCH_PROJECT_V2_1_COGNITION_SCOPE_VIOLATION",
                bottleneck_id=judgment.get("bottleneck_id"),
            )
        for field in (
            "assessment_reason",
            "counterarguments",
            "verification_metrics",
            "invalidation_conditions",
        ):
            if not judgment.get(field):
                raise _error(
                    "Limited bottleneck judgment is incomplete",
                    code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
                    bottleneck_id=judgment.get("bottleneck_id"),
                    field=field,
                )
    forbidden_terms = {"winner", "profit", "valuation", "recommendation"}
    for hypothesis in package.get("value_change_hypotheses", []):
        if hypothesis.get("status") not in ALLOWED_VALUE_STATUSES:
            raise _error(
                "Value-change hypothesis status is not allowed",
                code="RESEARCH_PROJECT_V2_1_COGNITION_SCOPE_VIOLATION",
                hypothesis_id=hypothesis.get("hypothesis_id"),
            )
        if hypothesis.get("target_scope") != "industry_segment":
            raise _error(
                "Value-change hypothesis must remain industry-segment scoped",
                code="RESEARCH_PROJECT_V2_1_COGNITION_SCOPE_VIOLATION",
                hypothesis_id=hypothesis.get("hypothesis_id"),
            )
        text = str(hypothesis.get("hypothesis_text", "")).lower()
        if forbidden_terms.intersection(text.split()):
            raise _error(
                "Value-change hypothesis contains downstream semantics",
                code="RESEARCH_PROJECT_V2_1_COGNITION_SCOPE_VIOLATION",
                hypothesis_id=hypothesis.get("hypothesis_id"),
            )


def validate_cognition_package(
    package: dict[str, Any],
    *,
    layout: LayeredResearchLayout | None = None,
) -> dict[str, Any]:
    effective = LayeredResearchLayout.default() if layout is None else layout
    validate_v2_1_schema_payload(
        "industry_cognition_baseline_v2_5", package, layout=effective
    )
    expected_hash = content_sha256(package, excluded_paths={("content_hash",)})
    if package.get("content_hash") != expected_hash:
        raise _error(
            "Cognition package content hash mismatch",
            code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
            field="content_hash",
        )
    validate_baseline_bindings(package, layout=effective)
    inventory = package.get("evidence_inventory", {})
    locators = inventory.get("locators", []) if isinstance(inventory, dict) else []
    valid_locators: dict[str, dict[str, Any]] = {}
    for locator in locators:
        locator_id = locator.get("locator_id") if isinstance(locator, dict) else None
        if not isinstance(locator_id, str) or locator_id in valid_locators:
            raise _error(
                "Cognition evidence locator IDs must be unique",
                code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
                field="locator_id",
            )
        valid_locators[locator_id] = validate_evidence_locator(
            locator, layout=effective
        )
    claims_by_id: dict[str, dict[str, Any]] = {}
    grounded_ids: list[str] = []
    for claim in package.get("claim_assessment_ledger", []):
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or claim_id in claims_by_id:
            raise _error(
                "Cognition claim IDs must be unique",
                code="RESEARCH_PROJECT_V2_1_COGNITION_VALIDATION_FAILED",
                field="claim_id",
            )
        calculation = calculate_claim_grounding(
            claim,
            inventory=inventory,
            valid_locators=valid_locators,
        )
        claims_by_id[claim_id] = claim
        if calculation["grounding_status"] == "grounded":
            grounded_ids.append(claim_id)
    for er in package.get("er_assessments", []):
        calculate_er_assessment(er, claims_by_id)
    validate_grounded_mechanisms(package, claims_by_id)
    validate_causal_edges(package, claims_by_id)
    validate_judgment_boundaries(package)
    framing = package.get("research_framing", {})
    leakage: list[str] = []
    if framing.get("model_scope") != "demand_side_and_system_interconnect":
        leakage.append("model_scope")
    for field in (
        "company_mapping_authorized",
        "stage_a2_authorized",
        "stage_b_authorized",
    ):
        if framing.get(field) is not False:
            leakage.append(field)
    if leakage:
        raise _error(
            "Cognition package exceeds the authorized research scope",
            code="RESEARCH_PROJECT_V2_1_COGNITION_SCOPE_VIOLATION",
            fields=leakage,
        )
    return {
        "status": "valid",
        "grounded_claim_ids": sorted(grounded_ids),
        "claim_count": len(claims_by_id),
        "locator_count": len(valid_locators),
        "scope_leakage": [],
    }
