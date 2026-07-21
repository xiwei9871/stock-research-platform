from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import unicodedata
from typing import Any

from stock_research.research_project_v2.canonical import content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.normalize import validate_normalized_document
from stock_research.research_project_v2_1.schema import validate_v2_1_schema_payload


AUTHORIZED_ER_IDS = (
    "PCB-ER-A01", "PCB-ER-A02", "PCB-ER-A03",
    "PCB-ER-A04", "PCB-ER-B01", "PCB-ER-B02",
)
ASSESSMENT_STATUSES = {"sufficient", "insufficient", "conflicted", "open", "not_assessable"}
CLAIM_TYPES = {"fact", "inference", "hypothesis", "judgment"}
EVIDENCE_STANCES = {"support", "oppose", "mixed", "contextual", "non_evidence"}
CONFIDENCE_ORDER = {"very_low": 0, "low": 1, "medium": 2, "high": 3}
RENDERER_VERSION = "targeted_evidence_assessment_markdown_v1"


def _error(message: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        message,
        code="RESEARCH_PROJECT_V2_1_TARGETED_ASSESSMENT_INVALID",
        details=details,
    )


def compute_er_assessment(
    er_id: str,
    claims: list[dict[str, Any]],
    *,
    independent_chain_count: int,
    remaining_evidence_gaps: list[str] | None = None,
    recommended_next_action: str = "targeted_gap_review",
) -> dict[str, Any]:
    selected = sorted(
        (claim for claim in claims if claim.get("er_id") == er_id),
        key=lambda claim: claim["claim_id"],
    )
    by_status = {
        status: [claim["claim_id"] for claim in selected if claim.get("assessment_status") == status]
        for status in ASSESSMENT_STATUSES
    }
    if by_status["conflicted"]:
        overall = "conflicted"
    elif by_status["not_assessable"] or by_status["insufficient"]:
        overall = "insufficient"
    elif by_status["open"]:
        overall = "open"
    elif selected and all(claim.get("assessment_status") == "sufficient" for claim in selected) and independent_chain_count >= 2:
        overall = "sufficient"
    else:
        overall = "insufficient"
    return {
        "er_id": er_id,
        "assessed_claim_ids": [claim["claim_id"] for claim in selected],
        "sufficient_claim_ids": by_status["sufficient"],
        "insufficient_claim_ids": by_status["insufficient"],
        "conflicted_claim_ids": by_status["conflicted"],
        "open_claim_ids": by_status["open"],
        "not_assessable_claim_ids": by_status["not_assessable"],
        "independent_evidence_chain_count": independent_chain_count,
        "overall_status": overall,
        "overall_status_reason": "ER status is computed from all atomic claims, independence, denominator and unresolved gaps; one sufficient claim cannot promote the ER.",
        "remaining_evidence_gaps": list(remaining_evidence_gaps or []),
        "recommended_next_action": recommended_next_action,
    }


def _wave_inventory(layout: LayeredResearchLayout) -> dict[str, Any]:
    return json.loads(
        (layout.root / "acquisition/wave_1/evidence_inventory.json").read_text(encoding="utf-8")
    )


def validate_assessment_locator(
    locator: dict[str, Any], *, layout: LayeredResearchLayout, er_id: str | None = None
) -> dict[str, Any]:
    inventory = _wave_inventory(layout)
    items = {item["artifact_id"]: item for item in inventory["items"]}
    item = items.get(locator.get("artifact_id"))
    if item is None or item.get("normalization_status") != "normalized":
        raise _error("Evidence locator references blocked, failed or non-normalized evidence")
    if er_id is not None and er_id not in set(item.get("authorized_er_ids") or []):
        raise _error(
            "Evidence locator crosses the Wave 1 authorized ER association",
            artifact_id=locator.get("artifact_id"),
            er_id=er_id,
        )
    if item.get("normalized_document_id") != locator.get("normalized_document_id"):
        raise _error("Evidence locator normalized-document binding mismatch")
    document_path = layout.evidence_normalized_dir / f"{locator['normalized_document_id']}.json"
    wrapper = json.loads(document_path.read_text(encoding="utf-8"))
    document = validate_normalized_document(wrapper["normalized_document"])
    legacy_path = layout.evidence_metadata_dir / f"{document['artifact_id']}.json"
    legacy = json.loads(legacy_path.read_text(encoding="utf-8"))["evidence_artifact"]
    if legacy["content_sha256"] != item["content_hash"] or legacy["raw_path"] != item["raw_artifact_path"]:
        raise _error("Evidence locator raw lineage drifted")
    index = locator.get("section_index")
    if not isinstance(index, int) or index < 0 or index >= len(document["sections"]):
        raise _error("Evidence locator section index is invalid")
    section = document["sections"][index]
    if section["section_hash"] != locator.get("section_hash"):
        raise _error("Evidence locator section hash drifted")
    return {**deepcopy(locator), "section_text": section["text"]}


def validate_upstream_bindings(
    artifact: dict[str, Any], *, layout: LayeredResearchLayout
) -> None:
    bindings = artifact["input_bindings"]
    checkpoint = json.loads(
        (layout.root / "acquisition/wave_1/acquisition_checkpoint.json").read_text(encoding="utf-8")
    )
    gate = json.loads(
        (layout.governance_dir / "ai_pcb_targeted_acquisition_gate_decision_v1.json").read_text(encoding="utf-8")
    )
    if checkpoint.get("checkpoint_id") != bindings.get("checkpoint_id") or checkpoint.get("content_hash") != bindings.get("checkpoint_hash"):
        raise _error("Wave 1 checkpoint/hash drifted")
    if gate.get("content_hash") != bindings.get("gate_hash"):
        raise _error("Gate/hash drifted")


def validate_assessment_artifact(
    artifact: dict[str, Any],
    *,
    layout: LayeredResearchLayout | None = None,
    validate_locators: bool = True,
) -> dict[str, Any]:
    copied = deepcopy(artifact)
    validate_v2_1_schema_payload("targeted_evidence_assessment_v2_7", copied, layout=layout)
    expected_hash = content_sha256(copied, excluded_paths=(("content_hash",),))
    if copied.get("content_hash") != expected_hash:
        raise _error("Assessment content hash mismatch")
    if tuple(copied.get("authorized_er_ids") or ()) != AUTHORIZED_ER_IDS:
        raise _error("Assessment authorized ER universe drifted")
    governance = copied.get("governance") or {}
    if any(
        governance.get(field) is not False
        for field in (
            "network_access", "new_acquisition", "cognition_update", "gap_review_update",
            "gate_update", "company_mapping_authorized", "stage_a2_authorized",
            "stage_b_authorized", "wave_1b_authorized",
        )
    ):
        raise _error("Assessment enables a prohibited downstream or mutation path")
    chain_groups: set[str] = set()
    known_chains: set[str] = set()
    for chain in copied.get("evidence_chain_register", []):
        chain_id = chain.get("chain_id")
        group = chain.get("independence_group")
        if not isinstance(chain_id, str) or not isinstance(group, str):
            raise _error("Evidence chain identity is invalid")
        if group in chain_groups:
            raise _error("Multiple evidence chains claim the same independence group")
        chain_groups.add(group)
        known_chains.add(chain_id)
    seen_claims: set[str] = set()
    effective_layout = LayeredResearchLayout.default() if layout is None else layout
    for claim in copied.get("atomic_claims", []):
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or claim_id in seen_claims:
            raise _error("Atomic claim identity is invalid or duplicated")
        seen_claims.add(claim_id)
        if claim.get("er_id") not in AUTHORIZED_ER_IDS:
            raise _error("Atomic claim references an unauthorized ER")
        if claim.get("claim_type") not in CLAIM_TYPES or claim.get("evidence_stance") not in EVIDENCE_STANCES or claim.get("assessment_status") not in ASSESSMENT_STATUSES:
            raise _error("Atomic claim enum is invalid", claim_id=claim_id)
        if claim.get("assessment_status") == "sufficient" and claim.get("denominator") in {None, "", "unresolved", "not_defined"}:
            raise _error("A sufficient claim has an unresolved denominator", claim_id=claim_id)
        if claim.get("freshness_status") == "unknown" and claim.get("confidence") == "high":
            raise _error("An unknown-date claim cannot receive high confidence", claim_id=claim_id)
        if claim.get("evidence_stance") in {"contextual", "non_evidence"} and claim.get("assessment_status") == "sufficient":
            raise _error("Contextual/non-evidence cannot be sufficient direct support", claim_id=claim_id)
        unknown_chains = sorted(set(claim.get("evidence_chain_ids") or []) - known_chains)
        if unknown_chains:
            raise _error("Atomic claim references an unknown evidence chain", claim_id=claim_id)
        locators = claim.get("evidence_locators") or []
        if claim.get("assessment_status") == "sufficient" and not locators:
            raise _error("A sufficient claim has no evidence locator", claim_id=claim_id)
        if validate_locators:
            for locator in locators:
                validate_assessment_locator(
                    locator, layout=effective_layout, er_id=claim.get("er_id")
                )
    er_ids = [row.get("er_id") for row in copied.get("er_assessments", [])]
    if tuple(sorted(er_ids)) != tuple(sorted(AUTHORIZED_ER_IDS)):
        raise _error("ER assessment must cover exactly the six authorized ERs")
    er_map = {row["er_id"]: row for row in copied.get("er_assessments", [])}
    for er_id, persisted in er_map.items():
        recomputed = compute_er_assessment(
            er_id,
            copied.get("atomic_claims", []),
            independent_chain_count=persisted["independent_evidence_chain_count"],
            remaining_evidence_gaps=persisted.get("remaining_evidence_gaps") or [],
            recommended_next_action=persisted.get("recommended_next_action")
            or "targeted_gap_review",
        )
        for field in (
            "assessed_claim_ids",
            "sufficient_claim_ids",
            "insufficient_claim_ids",
            "conflicted_claim_ids",
            "open_claim_ids",
            "not_assessable_claim_ids",
            "overall_status",
        ):
            if persisted.get(field) != recomputed.get(field):
                raise _error(
                    "Persisted ER assessment differs from atomic-claim computation",
                    er_id=er_id,
                    field=field,
                )
    if "PCB-ER-A02" in er_map and er_map["PCB-ER-A02"].get("independent_evidence_chain_count", 0) > 1:
        raise _error("A02 OIF materials were incorrectly treated as independent evidence chains")
    if "PCB-ER-B01" in er_map and er_map["PCB-ER-B01"].get("independent_evidence_chain_count", 0) > 1:
        raise _error("B01 Isola materials were incorrectly treated as independent evidence chains")
    excluded_artifacts = {
        row.get("artifact_id") for row in copied.get("excluded_records", []) if row.get("artifact_id")
    }
    for claim in copied.get("atomic_claims", []):
        used = {locator.get("artifact_id") for locator in claim.get("evidence_locators", [])}
        if used & excluded_artifacts:
            raise _error("Excluded or normalization-failed evidence was used by a claim")
    return copied


def _values(value: object) -> str:
    return "; ".join(str(item) for item in value) if isinstance(value, list) else str(value or "")


def render_assessment_report(artifact: dict[str, Any]) -> bytes:
    lines = [
        "# AI PCB Targeted Evidence Assessment Wave 1 v1",
        "",
        "This report is a deterministic projection of the assessment artifact. Acquired evidence coverage is not ER sufficiency.",
        "",
        "## ER status",
        "",
    ]
    for er in sorted(artifact.get("er_assessments", []), key=lambda row: row["er_id"]):
        lines.extend([
            f"### {er['er_id']}: {er['overall_status']}", "",
            f"- Independent evidence chains: {er['independent_evidence_chain_count']}",
            f"- Reason: {er['overall_status_reason']}",
            f"- Remaining gaps: {_values(er['remaining_evidence_gaps'])}",
            f"- Next action: {er['recommended_next_action']}", "",
        ])
    lines.extend(["## Atomic claims", ""])
    for claim in sorted(artifact.get("atomic_claims", []), key=lambda row: row["claim_id"]):
        lines.extend([
            f"### [{claim['assessment_status'].upper()}] {claim['claim_id']}", "",
            claim["claim_text"], "",
            f"- ER / type: {claim['er_id']} / {claim['claim_type']}",
            f"- Scope: {claim['scope']}",
            f"- Generation: {claim['product_or_standard_generation']}",
            f"- Rate / frequency: {claim['rate']} / {claim['frequency']}",
            f"- Distance / topology: {claim['distance']} / {claim['topology']}",
            f"- Test method: {claim['test_method']}",
            f"- Denominator: {claim['denominator']}",
            f"- Stance: {claim['evidence_stance']}",
            f"- Evidence chains: {_values(claim['evidence_chain_ids'])}",
            f"- Independence: {claim['source_independence_status']}",
            f"- Freshness / confidence: {claim['freshness_status']} / {claim['confidence']}",
            f"- Assessment reason: {claim['assessment_reason']}",
            f"- Limitations: {_values(claim['limitations'])}",
            f"- Counterevidence: {_values(claim['counterevidence'])}",
            f"- Alternative explanations: {_values(claim['alternative_explanations'])}",
            f"- Missing evidence: {_values(claim['missing_evidence'])}",
            f"- Maximum cognition: {claim['maximum_supported_cognition']}",
        ])
        for locator in sorted(claim.get("evidence_locators", []), key=lambda row: (row["artifact_id"], row["section_index"])):
            lines.append(
                f"- Evidence: {locator['artifact_id']} / {locator['normalized_document_id']} / section {locator['section_index']} / hash {locator['section_hash'][:12]}..."
            )
        lines.append("")
    lines.extend(["## Excluded records", ""])
    for row in sorted(artifact.get("excluded_records", []), key=lambda item: str(item.get("record_id", ""))):
        lines.append(f"- {row.get('record_id')}: {row.get('reason')}")
    normalized = unicodedata.normalize("NFC", "\n".join(lines).replace("\r\n", "\n"))
    return (normalized.rstrip("\n") + "\n").encode("utf-8")


def validate_persisted_assessment_report(
    artifact: dict[str, Any], report_bytes: bytes
) -> None:
    expected = render_assessment_report(artifact)
    if report_bytes != expected:
        raise _error(
            "Persisted assessment report differs from deterministic projection",
            expected_hash=sha256(expected).hexdigest(),
            actual_hash=sha256(report_bytes).hexdigest(),
        )
