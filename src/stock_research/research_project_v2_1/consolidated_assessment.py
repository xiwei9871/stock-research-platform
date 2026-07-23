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
from stock_research.research_project_v2_1.targeted_assessment import (
    ASSESSMENT_STATUSES,
    CLAIM_TYPES,
    EVIDENCE_STANCES,
    compute_er_assessment,
)


CONSOLIDATED_AUTHORIZED_ER_IDS = (
    "PCB-ER-A04",
    "PCB-ER-B01",
    "PCB-ER-B02",
    "PCB-ER-A02",
)
ELIGIBLE_RECOVERY_ARTIFACT_IDS = (
    "evidence_artifact:5cf8a72e4f4c6a9043a474c5",
)
UNRESOLVED_CLASSIFICATIONS = {
    "machine_public_acquisition_resolved",
    "manual_source_resolution_candidate",
    "expert_technical_review_candidate",
    "bounded_by_public_evidence",
    "stop_investment_recommended",
}
CLAIM_REQUIRED_FIELDS = {
    "claim_id",
    "er_id",
    "claim_text",
    "claim_type",
    "scope",
    "product_or_standard_generation",
    "rate",
    "frequency",
    "distance",
    "topology",
    "test_method",
    "denominator",
    "evidence_locators",
    "evidence_stance",
    "evidence_chain_ids",
    "source_independence_status",
    "freshness_status",
    "assessment_status",
    "evidence_strength",
    "confidence",
    "assessment_reason",
    "limitations",
    "counterevidence",
    "alternative_explanations",
    "missing_evidence",
    "maximum_supported_cognition",
}
ER_ASSESSMENT_REQUIRED_FIELDS = {
    "er_id",
    "assessed_claim_ids",
    "sufficient_claim_ids",
    "insufficient_claim_ids",
    "conflicted_claim_ids",
    "open_claim_ids",
    "not_assessable_claim_ids",
    "independent_evidence_chain_count",
    "overall_status",
    "overall_status_reason",
    "remaining_evidence_gaps",
    "recommended_next_action",
}
AUTHORIZATION_NAME = (
    "ai_pcb_targeted_evidence_assessment_wave_1b_"
    "consolidated_execution_authorization_v1.json"
)


def _error(message: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        message,
        code="RESEARCH_PROJECT_V2_1_CONSOLIDATED_ASSESSMENT_INVALID",
        details=details,
    )


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_content_hash(payload: dict[str, Any], label: str) -> None:
    expected = content_sha256(payload, excluded_paths={("content_hash",)})
    if payload.get("content_hash") != expected:
        raise _error(f"{label} content hash mismatch")


def _bound_payloads(layout: LayeredResearchLayout) -> dict[str, tuple[Path, str]]:
    return {
        "recovery_pilot_review_decision_hash": (
            layout.governance_dir
            / "ai_pcb_wave_1b_recovery_pilot_review_decision_v1.json",
            "content_hash",
        ),
        "recovery_pilot_checkpoint_hash": (
            layout.root
            / "acquisition/wave_1b_recovery_pilot/acquisition_checkpoint.json",
            "content_hash",
        ),
        "wave_1b_checkpoint_hash": (
            layout.root / "acquisition/wave_1b/acquisition_checkpoint.json",
            "content_hash",
        ),
        "wave_1_assessment_hash": (
            layout.analysis_dir / "ai_pcb_targeted_evidence_assessment_wave_1_v1.json",
            "content_hash",
        ),
        "wave_1_checkpoint_hash": (
            layout.root / "acquisition/wave_1/acquisition_checkpoint.json",
            "content_hash",
        ),
    }


def validate_consolidated_assessment_authorization(
    authorization: dict[str, Any],
    *,
    layout: LayeredResearchLayout | None = None,
) -> dict[str, Any]:
    copied = deepcopy(authorization)
    _verify_content_hash(copied, "Consolidated assessment authorization")
    if copied.get("artifact_type") != "consolidated_assessment_execution_authorization":
        raise _error("Consolidated assessment authorization type is invalid")
    if copied.get("execution_authorized") is not True:
        raise _error("Consolidated assessment execution is not authorized")
    if copied.get("authorization_scope") != "exact_er_and_evidence_list_only":
        raise _error("Consolidated assessment authorization scope is not exact")
    if tuple(copied.get("authorized_er_ids") or ()) != CONSOLIDATED_AUTHORIZED_ER_IDS:
        raise _error("Consolidated assessment authorized ER universe drifted")
    eligible = tuple(
        row.get("artifact_id") for row in copied.get("eligible_recovery_evidence", [])
    )
    if eligible != ELIGIBLE_RECOVERY_ARTIFACT_IDS:
        raise _error("Consolidated assessment eligible recovery evidence drifted")
    if copied.get("network_access") is not False or copied.get(
        "new_acquisition_authorized"
    ) is not False:
        raise _error("Consolidated assessment authorization enables acquisition")
    for field in (
        "recovery_acquisition_authorized",
        "cognition_update_authorized",
        "wave_2_authorized",
        "company_mapping_authorized",
        "stage_a2_authorized",
        "stage_b_authorized",
    ):
        if copied.get(field) is not False:
            raise _error("Consolidated assessment authorization enables downstream work", field=field)

    effective_layout = LayeredResearchLayout.default() if layout is None else layout
    bindings = copied.get("input_bindings") or {}
    for field, (path, hash_field) in _bound_payloads(effective_layout).items():
        upstream = _load_json(path)
        if bindings.get(field) != upstream.get(hash_field):
            raise _error("Consolidated assessment upstream hash drifted", field=field)
    return copied


def canonicalize_recovery_representations(
    authorization: dict[str, Any],
) -> dict[str, str]:
    rule = authorization.get("normalization_duplicate_rule") or {}
    canonical_by_hash = rule.get("canonical_representations") or {}
    duplicates = list(rule.get("resume_duplicates") or [])
    expected = {
        "normalized_document:c3ff111a56925e8c6836494f": canonical_by_hash.get(
            "50983b38c26460255f89668f3fe76eb9759b879c3ea6cce31483f468e61c97e2"
        ),
        "normalized_document:500ae7dcaae88360df0e9c72": canonical_by_hash.get(
            "701d2fbd43167f5f40a02e51c6ad58bef346dcc49c5fb502d5a268dc195cdad4"
        ),
    }
    if set(duplicates) != set(expected) or any(value is None for value in expected.values()):
        raise _error("Recovery normalized representation policy drifted")
    return expected


def _inventories(layout: LayeredResearchLayout) -> list[dict[str, Any]]:
    return [
        _load_json(layout.root / "acquisition/wave_1/evidence_inventory.json"),
        _load_json(layout.root / "acquisition/wave_1b/evidence_inventory.json"),
        _load_json(
            layout.root
            / "acquisition/wave_1b_recovery_pilot/evidence_inventory.json"
        ),
    ]


def _inventory_items(layout: LayeredResearchLayout) -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for inventory in _inventories(layout):
        for item in inventory.get("items", []):
            items[item["artifact_id"]] = item
    return items


def validate_consolidated_locator(
    locator: dict[str, Any],
    *,
    layout: LayeredResearchLayout,
    er_id: str,
    eligible_recovery_artifact_ids: set[str],
    duplicate_representation_map: dict[str, str],
) -> dict[str, Any]:
    items = _inventory_items(layout)
    artifact_id = locator.get("artifact_id")
    item = items.get(artifact_id)
    if item is None or item.get("normalization_status") != "normalized":
        raise _error("Evidence locator references blocked, failed or non-normalized evidence")
    if er_id not in set(item.get("authorized_er_ids") or []):
        raise _error("Evidence locator crosses an authorized ER association")
    if item.get("recovery_target_id") and artifact_id not in eligible_recovery_artifact_ids:
        raise _error("Evidence locator uses ineligible recovery evidence")
    document_id = locator.get("normalized_document_id")
    if document_id in duplicate_representation_map:
        raise _error("Evidence locator uses a resume-duplicate normalized representation")
    if item.get("normalized_document_id") != document_id:
        raise _error("Evidence locator normalized-document binding mismatch")

    wrapper = _load_json(layout.evidence_normalized_dir / f"{document_id}.json")
    document = validate_normalized_document(wrapper["normalized_document"])
    legacy = _load_json(
        layout.evidence_metadata_dir / f"{document['artifact_id']}.json"
    )["evidence_artifact"]
    if legacy["content_sha256"] != item["content_hash"]:
        raise _error("Evidence locator raw hash lineage drifted")
    if legacy["raw_path"] != item["raw_artifact_path"]:
        raise _error("Evidence locator raw path lineage drifted")
    index = locator.get("section_index")
    if not isinstance(index, int) or index < 0 or index >= len(document["sections"]):
        raise _error("Evidence locator section index is invalid")
    section = document["sections"][index]
    if section["section_hash"] != locator.get("section_hash"):
        raise _error("Evidence locator section hash drifted")
    return {**deepcopy(locator), "section_text": section["text"]}


def validate_consolidated_assessment_artifact(
    artifact: dict[str, Any],
    *,
    layout: LayeredResearchLayout | None = None,
    validate_locators: bool = True,
) -> dict[str, Any]:
    copied = deepcopy(artifact)
    _verify_content_hash(copied, "Consolidated assessment")
    if copied.get("artifact_type") != "targeted_evidence_assessment_consolidated":
        raise _error("Consolidated assessment artifact type is invalid")
    if copied.get("execution_mode") != "offline_read_only_consolidated_evidence_assessment":
        raise _error("Consolidated assessment execution mode drifted")
    if tuple(copied.get("authorized_er_ids") or ()) != CONSOLIDATED_AUTHORIZED_ER_IDS:
        raise _error("Consolidated assessment authorized ER universe drifted")
    if tuple(copied.get("eligible_recovery_artifact_ids") or ()) != ELIGIBLE_RECOVERY_ARTIFACT_IDS:
        raise _error("Consolidated assessment eligible recovery artifact list drifted")
    if copied.get("authorization_consumed") is not True:
        raise _error("Consolidated assessment authorization was not consumed")

    effective_layout = LayeredResearchLayout.default() if layout is None else layout
    authorization = validate_consolidated_assessment_authorization(
        _load_json(effective_layout.governance_dir / AUTHORIZATION_NAME),
        layout=effective_layout,
    )
    if copied.get("input_bindings", {}).get("execution_authorization_hash") != authorization.get("content_hash"):
        raise _error("Consolidated assessment authorization binding drifted")
    for field, (path, hash_field) in _bound_payloads(effective_layout).items():
        if copied.get("input_bindings", {}).get(field) != _load_json(path).get(hash_field):
            raise _error("Consolidated assessment upstream hash drifted", field=field)

    governance = copied.get("governance") or {}
    for field in (
        "network_access",
        "new_acquisition",
        "recovery_acquisition",
        "cognition_update",
        "gap_review_update",
        "gate_update",
        "automatic_manual_task_authorization",
        "company_mapping_authorized",
        "stage_a2_authorized",
        "stage_b_authorized",
        "wave_2_authorized",
    ):
        if governance.get(field) is not False:
            raise _error("Consolidated assessment enables a prohibited downstream path", field=field)

    validate_v2_1_schema_payload(
        "targeted_evidence_assessment_consolidated_v2_8",
        copied,
        layout=layout,
    )

    duplicate_map = canonicalize_recovery_representations(authorization)
    canonical_register = copied.get("canonical_representation_register") or []
    registered_duplicates = {
        duplicate: row.get("canonical_normalized_document_id")
        for row in canonical_register
        for duplicate in row.get("resume_duplicate_ids", [])
    }
    if registered_duplicates != duplicate_map:
        raise _error("Consolidated assessment canonical representation register drifted")

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

    eligible_recovery = set(ELIGIBLE_RECOVERY_ARTIFACT_IDS)
    excluded_artifacts = {
        row.get("artifact_id")
        for row in copied.get("excluded_records", [])
        if row.get("artifact_id")
    }
    seen_claims: set[str] = set()
    for claim in copied.get("atomic_claims", []):
        if set(claim) != CLAIM_REQUIRED_FIELDS:
            raise _error("Atomic claim fields are incomplete or contain undeclared data")
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or claim_id in seen_claims:
            raise _error("Atomic claim identity is invalid or duplicated")
        seen_claims.add(claim_id)
        if claim.get("er_id") not in CONSOLIDATED_AUTHORIZED_ER_IDS:
            raise _error("Atomic claim references an unauthorized ER")
        if claim.get("claim_type") not in CLAIM_TYPES:
            raise _error("Atomic claim type is invalid", claim_id=claim_id)
        if claim.get("evidence_stance") not in EVIDENCE_STANCES:
            raise _error("Atomic claim stance is invalid", claim_id=claim_id)
        if claim.get("assessment_status") not in ASSESSMENT_STATUSES:
            raise _error("Atomic claim assessment status is invalid", claim_id=claim_id)
        if claim.get("assessment_status") == "sufficient" and claim.get("denominator") in {
            None,
            "",
            "unresolved",
            "not_defined",
        }:
            raise _error("A sufficient claim has an unresolved denominator", claim_id=claim_id)
        if claim.get("freshness_status") == "unknown" and claim.get("confidence") == "high":
            raise _error("An unknown-date claim cannot receive high confidence", claim_id=claim_id)
        if claim.get("evidence_stance") in {"contextual", "non_evidence"} and claim.get("assessment_status") == "sufficient":
            raise _error("Contextual/non-evidence cannot be sufficient direct support", claim_id=claim_id)
        if set(claim.get("evidence_chain_ids") or []) - known_chains:
            raise _error("Atomic claim references an unknown evidence chain", claim_id=claim_id)
        locators = claim.get("evidence_locators") or []
        if claim.get("assessment_status") == "sufficient" and not locators:
            raise _error("A sufficient claim has no evidence locator", claim_id=claim_id)
        if {locator.get("artifact_id") for locator in locators} & excluded_artifacts:
            raise _error("Excluded evidence was used by a claim", claim_id=claim_id)
        if validate_locators:
            for locator in locators:
                validate_consolidated_locator(
                    locator,
                    layout=effective_layout,
                    er_id=claim["er_id"],
                    eligible_recovery_artifact_ids=eligible_recovery,
                    duplicate_representation_map=duplicate_map,
                )

    er_rows = copied.get("er_assessments") or []
    if tuple(row.get("er_id") for row in er_rows) != CONSOLIDATED_AUTHORIZED_ER_IDS:
        raise _error("Consolidated assessment must cover exactly four authorized ERs")
    for persisted in er_rows:
        if set(persisted) != ER_ASSESSMENT_REQUIRED_FIELDS:
            raise _error("ER assessment fields are incomplete or contain undeclared data")
        recomputed = compute_er_assessment(
            persisted["er_id"],
            copied.get("atomic_claims", []),
            independent_chain_count=persisted["independent_evidence_chain_count"],
            remaining_evidence_gaps=persisted.get("remaining_evidence_gaps") or [],
            recommended_next_action=persisted.get("recommended_next_action") or "manual_gate_review",
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
                raise _error("Persisted ER assessment differs from claim computation", er_id=persisted["er_id"], field=field)

    unresolved = copied.get("unresolved_evidence_targets") or []
    if not 3 <= len(unresolved) <= 5:
        raise _error("Consolidated assessment must produce three to five unresolved targets")
    unresolved_ids: set[str] = set()
    for row in unresolved:
        target_id = row.get("target_id")
        if not isinstance(target_id, str) or target_id in unresolved_ids:
            raise _error("Unresolved evidence target identity is invalid")
        unresolved_ids.add(target_id)
        if row.get("classification") not in UNRESOLVED_CLASSIFICATIONS:
            raise _error("Unresolved evidence target classification is invalid", target_id=target_id)
        if row.get("future_action_authorized") is not False:
            raise _error("Unresolved evidence target self-authorizes future work", target_id=target_id)
    return copied


def _values(value: object) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value or "")


def render_consolidated_assessment_report(artifact: dict[str, Any]) -> bytes:
    lines = [
        "# AI PCB Targeted Evidence Assessment Wave 1b Consolidated v1",
        "",
        "This report is a deterministic projection of the consolidated assessment artifact. Evidence acquisition volume is not evidence sufficiency.",
        "",
        "## Consolidated answer",
        "",
    ]
    answer = artifact.get("consolidated_answer") or {}
    for label, field in (
        ("Understood", "understood"),
        ("Scope-limited understanding", "scope_limited_understanding"),
        ("Machine public-acquisition ceiling", "machine_public_acquisition_ceiling"),
        ("Manual evidence candidates", "manual_evidence_candidates"),
        ("Stop-investment items", "stop_investment_items"),
    ):
        lines.append(f"- {label}: {_values(answer.get(field))}")
    lines.extend(["", "## ER status", ""])
    for er in artifact.get("er_assessments", []):
        lines.extend(
            [
                f"### {er['er_id']}: {er['overall_status']}",
                "",
                f"- Independent evidence chains: {er['independent_evidence_chain_count']}",
                f"- Reason: {er['overall_status_reason']}",
                f"- Remaining gaps: {_values(er['remaining_evidence_gaps'])}",
                f"- Next action: {er['recommended_next_action']}",
                "",
            ]
        )
    lines.extend(["## Atomic claims", ""])
    for claim in sorted(artifact.get("atomic_claims", []), key=lambda row: row["claim_id"]):
        lines.extend(
            [
                f"### [{claim['assessment_status'].upper()}] {claim['claim_id']}",
                "",
                claim["claim_text"],
                "",
                f"- ER / type: {claim['er_id']} / {claim['claim_type']}",
                f"- Scope: {claim['scope']}",
                f"- Denominator: {claim['denominator']}",
                f"- Evidence chains: {_values(claim['evidence_chain_ids'])}",
                f"- Freshness / confidence: {claim['freshness_status']} / {claim['confidence']}",
                f"- Assessment reason: {claim['assessment_reason']}",
                f"- Limitations: {_values(claim['limitations'])}",
                f"- Missing evidence: {_values(claim['missing_evidence'])}",
                f"- Maximum cognition: {claim['maximum_supported_cognition']}",
            ]
        )
        for locator in sorted(
            claim.get("evidence_locators", []),
            key=lambda row: (row["artifact_id"], row["section_index"]),
        ):
            lines.append(
                f"- Evidence: {locator['artifact_id']} / {locator['normalized_document_id']} / section {locator['section_index']} / hash {locator['section_hash'][:12]}..."
            )
        lines.append("")
    lines.extend(["## Unresolved evidence targets", ""])
    for row in sorted(artifact.get("unresolved_evidence_targets", []), key=lambda item: item["priority"]):
        lines.extend(
            [
                f"### {row['priority']} {row['target_id']}",
                "",
                f"- ER: {row['er_id']}",
                f"- Classification: {row['classification']}",
                f"- Why unresolved: {row['why_unresolved']}",
                f"- Required human action: {row['required_human_action']}",
                f"- Stop condition: {row['stop_condition']}",
                f"- Future action authorized: {str(row['future_action_authorized']).lower()}",
                "",
            ]
        )
    lines.extend(["## Excluded records", ""])
    for row in sorted(artifact.get("excluded_records", []), key=lambda item: str(item.get("record_id", ""))):
        lines.append(f"- {row.get('record_id')}: {row.get('reason')}")
    normalized = unicodedata.normalize("NFC", "\n".join(lines).replace("\r\n", "\n"))
    return (normalized.rstrip("\n") + "\n").encode("utf-8")


def validate_persisted_consolidated_assessment_report(
    artifact: dict[str, Any], report_bytes: bytes
) -> None:
    expected = render_consolidated_assessment_report(artifact)
    if expected != report_bytes:
        raise _error(
            "Persisted consolidated assessment report differs from deterministic projection",
            expected_hash=sha256(expected).hexdigest(),
            actual_hash=sha256(report_bytes).hexdigest(),
        )
