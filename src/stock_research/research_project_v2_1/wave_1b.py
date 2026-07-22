from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.normalize import validate_normalized_document


AUTHORIZED_ER_IDS = ("PCB-ER-A04", "PCB-ER-B01", "PCB-ER-B02", "PCB-ER-A02")
INTERNAL_EXECUTION_ORDER = (
    ("PCB-ER-A04", "PCB-ER-B01", "PCB-ER-B02"),
    ("PCB-ER-A02",),
)
_ER_PHASE = {
    er_id: phase
    for phase, group in enumerate(INTERNAL_EXECUTION_ORDER, start=1)
    for er_id in group
}
REQUIRED_DENOMINATOR_FIELDS = {
    "PCB-ER-A04": (
        "frequency_range", "comparison_frequency", "nyquist_frequency",
        "channel_length", "unit", "differential_or_single_ended",
        "reference_plane", "fixture_configuration", "deembedding_method",
        "coupon_or_actual_channel", "temperature", "environment",
        "uncertainty_or_repeatability",
    ),
    "PCB-ER-B01": (
        "test_method", "frequency", "temperature", "humidity",
        "material_direction", "sample_geometry", "sample_thickness",
        "resin_content", "glass_style", "copper_condition",
        "nominal_typical_or_guaranteed", "design_dk_or_test_dk",
        "measurement_uncertainty",
    ),
    "PCB-ER-B02": (
        "surface_profile_metric", "treatment_type", "frequency_range",
        "trace_geometry", "copper_thickness", "dielectric_thickness",
        "material_system", "channel_length", "measurement_or_simulation_method",
        "reference_plane", "deembedding_method", "temperature_environment",
        "uncertainty_or_repeatability",
    ),
    "PCB-ER-A02": (
        "data_rate", "baud_rate", "modulation", "nyquist_frequency",
        "channel_length", "topology", "pcb_length", "connector_count",
        "cable_length", "retimer_presence", "equalization_assumption",
        "insertion_loss", "return_loss", "crosstalk",
        "ber_or_compliance_metric", "deembedding_method",
    ),
}
_TERMINAL_STATES = {
    "acquisition_complete_for_assessment",
    "acquisition_partial_with_gaps",
    "acquisition_stopped_due_to_redundancy",
    "acquisition_stopped_due_to_public_limit",
    "acquisition_blocked",
}


def _invalid(message: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        message,
        code="RESEARCH_PROJECT_V2_1_WAVE_1B_INVALID",
        details=details,
    )


def validate_wave_1b_gate(payload: dict[str, Any]) -> dict[str, Any]:
    gate = deepcopy(payload)
    if gate.get("content_hash") != content_sha256(
        gate, excluded_paths=(("content_hash",),)
    ):
        raise _invalid("Wave 1b Gate hash mismatch")
    if (
        gate.get("artifact_type") != "targeted_acquisition_wave_1b_gate_decision"
        or gate.get("decision_status") != "frozen"
        or gate.get("wave_1_assessment_accepted") is not True
    ):
        raise _invalid("Wave 1b Gate is not a frozen accepted decision")
    authorization = gate.get("authorization") or {}
    if (
        authorization.get("wave_1b_targeted_acquisition_authorized") is not True
        or authorization.get("authorization_scope") != "exact_list_only"
        or authorization.get("unlisted_er_authorized") is not False
    ):
        raise _invalid("Wave 1b Gate does not satisfy exact-list authorization")
    if tuple(gate.get("authorized_for_wave_1b") or ()) != AUTHORIZED_ER_IDS:
        raise _invalid("Wave 1b Gate authorized ER list drifted")
    order = gate.get("internal_execution_order") or {}
    if (
        tuple(order.get("phase_1") or ()) != INTERNAL_EXECUTION_ORDER[0]
        or tuple(order.get("phase_2") or ()) != INTERNAL_EXECUTION_ORDER[1]
    ):
        raise _invalid("Wave 1b Gate internal execution order drifted")
    if {row.get("er_id") for row in gate.get("no_additional_acquisition") or []} != {"PCB-ER-A01"}:
        raise _invalid("Wave 1b Gate A01 no-acquisition decision drifted")
    if {row.get("er_id") for row in gate.get("deferred") or []} != {"PCB-ER-A03"}:
        raise _invalid("Wave 1b Gate A03 deferral drifted")
    if any(
        gate.get(field) is not False
        for field in (
            "wave_1b_acquisition_started", "cognition_update_authorized",
            "company_mapping_authorized", "stage_a2_authorized", "stage_b_authorized",
        )
    ):
        raise _invalid("Wave 1b Gate authorizes a prohibited downstream action")
    return gate


def validate_upstream_bindings(
    gate: dict[str, Any], *, layout: LayeredResearchLayout | None = None
) -> None:
    effective = LayeredResearchLayout.default() if layout is None else layout
    bindings = gate["input_bindings"]
    assessment = json.loads(
        (effective.analysis_dir / "ai_pcb_targeted_evidence_assessment_wave_1_v1.json").read_text(encoding="utf-8")
    )
    checkpoint = json.loads(
        (effective.root / "acquisition/wave_1/acquisition_checkpoint.json").read_text(encoding="utf-8")
    )
    prior_gate = json.loads(
        (effective.governance_dir / "ai_pcb_targeted_acquisition_gate_decision_v1.json").read_text(encoding="utf-8")
    )
    expected = {
        "wave_1_assessment_id": assessment["assessment_id"],
        "wave_1_assessment_hash": assessment["content_hash"],
        "wave_1_checkpoint_id": checkpoint["checkpoint_id"],
        "wave_1_checkpoint_hash": checkpoint["content_hash"],
        "prior_gate_decision_id": prior_gate["decision_id"],
        "prior_gate_hash": prior_gate["content_hash"],
    }
    if bindings != expected:
        raise _invalid("Wave 1b upstream binding drifted", expected=expected, actual=bindings)


def validate_wave_1b_candidate(
    candidate: dict[str, Any], gate: dict[str, Any]
) -> dict[str, Any]:
    validate_wave_1b_gate(gate)
    copied = deepcopy(candidate)
    er_ids = copied.get("authorized_er_ids")
    if not isinstance(er_ids, list) or len(er_ids) != 1:
        raise _invalid("Wave 1b candidate must bind exactly one authorized ER")
    er_id = er_ids[0]
    if er_id not in AUTHORIZED_ER_IDS:
        raise _invalid("Wave 1b candidate ER is not authorized", er_id=er_id)
    if copied.get("wave_id") != "targeted_evidence_acquisition_wave_1b":
        raise _invalid("Wave 1b candidate wave identity is invalid")
    if copied.get("internal_phase") != _ER_PHASE[er_id]:
        raise _invalid("Wave 1b candidate internal phase is invalid", er_id=er_id)
    required = {
        "candidate_id", "source_title", "provider_source_title", "source_owner",
        "source_class", "source_url", "expected_evidence_role",
        "expected_denominator_fields", "eligibility_reason", "known_limitations",
        "publication_date_status", "candidate_status",
    }
    missing = sorted(required - set(copied))
    if missing:
        raise _invalid("Wave 1b candidate fields are missing", fields=missing)
    denominator_fields = set(copied.get("expected_denominator_fields") or [])
    required_denominators = set(REQUIRED_DENOMINATOR_FIELDS[er_id])
    if not required_denominators <= denominator_fields:
        raise _invalid(
            "Wave 1b candidate denominator plan is incomplete",
            er_id=er_id,
            missing=sorted(required_denominators - denominator_fields),
        )
    if copied.get("publication_date_status") not in {"known", "unknown"}:
        raise _invalid("Wave 1b publication date status is invalid")
    if copied.get("candidate_status") not in {"eligible", "ineligible", "blocked_lead"}:
        raise _invalid("Wave 1b candidate status is invalid")
    return copied


def build_wave_1b_attempt_record(
    *,
    candidate: dict[str, Any],
    provider_attempt: dict[str, Any],
    artifact: dict[str, Any] | None,
    normalization_status: str,
    normalized_document_id: str | None,
    normalization_error: str | None = None,
) -> dict[str, Any]:
    return {
        "attempt_id": provider_attempt["attempt_id"],
        "provider_attempt_id": provider_attempt["attempt_id"],
        "candidate_id": candidate["candidate_id"],
        "wave_id": "targeted_evidence_acquisition_wave_1b",
        "authorized_er_ids": list(candidate["authorized_er_ids"]),
        "internal_phase": candidate["internal_phase"],
        "network_mode": "direct_http",
        "proxy_mode": "direct",
        "trust_env": False,
        "started_at": provider_attempt["attempted_at"],
        "finished_at": provider_attempt["completed_at"],
        "elapsed_ms": provider_attempt["elapsed_ms"],
        "status": provider_attempt["status"],
        "result": provider_attempt["status"],
        "http_status": provider_attempt.get("http_status"),
        "failure_class": provider_attempt.get("failure_code"),
        "security_status": (
            "blocked"
            if provider_attempt.get("failure_code") == "security_policy_blocked"
            else "passed"
        ),
        "raw_artifact_created": artifact is not None,
        "raw_artifact_id": None if artifact is None else artifact["evidence_artifact_id"],
        "content_hash": None if artifact is None else artifact["content_hash"],
        "content_type": provider_attempt.get("content_type"),
        "bytes_received": provider_attempt.get("bytes_received", 0),
        "resolved_url": provider_attempt.get("resolved_url"),
        "retry_count": provider_attempt.get("retry_count", 0),
        "normalization_status": normalization_status,
        "normalized_document_id": normalized_document_id,
        "normalization_error": normalization_error,
        "assessment_started": False,
        "cognition_update_started": False,
        "diagnostic_summary": provider_attempt.get("diagnostic_summary"),
    }


def _coverage(
    records: list[dict[str, Any]], *, acquired_only: bool
) -> dict[str, int]:
    result = {er_id: 0 for er_id in AUTHORIZED_ER_IDS}
    for record in records:
        if acquired_only and record.get("status") != "acquired":
            continue
        for er_id in record.get("authorized_er_ids") or []:
            if er_id in result:
                result[er_id] += 1
    return result


def _terminal_state(attempts: list[dict[str, Any]], er_id: str) -> str:
    rows = [row for row in attempts if er_id in (row.get("authorized_er_ids") or [])]
    if not rows or all(row.get("status") == "blocked" for row in rows):
        return "acquisition_blocked"
    if any(row.get("status") == "acquired" for row in rows):
        return "acquisition_complete_for_assessment"
    return "acquisition_partial_with_gaps"


def build_wave_1b_checkpoint(
    *,
    gate: dict[str, Any],
    candidates: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    created_at: str,
    preflight_attempt_ids: list[str] | None = None,
    exact_duplicate_groups: list[list[str]] | None = None,
    suspected_common_origin_groups: list[list[str]] | None = None,
    out_of_scope_candidate_count: int = 0,
    security_violations: list[str] | None = None,
    scope_violations: list[str] | None = None,
) -> dict[str, Any]:
    frozen = validate_wave_1b_gate(gate)
    status_counts = Counter(row.get("status") for row in attempts)
    media_counts = Counter(row.get("content_type") for row in inventory)
    hash_groups: dict[str, list[str]] = defaultdict(list)
    for item in inventory:
        if item.get("content_hash"):
            hash_groups[item["content_hash"]].append(item["artifact_id"])
    duplicates = exact_duplicate_groups
    if duplicates is None:
        duplicates = sorted(sorted(group) for group in hash_groups.values() if len(group) > 1)
    common_origins = sorted(suspected_common_origin_groups or [])
    common_origin_reductions = sum(max(0, len(set(group)) - 1) for group in common_origins)
    source_coverage = {er_id: [] for er_id in AUTHORIZED_ER_IDS}
    denominator_coverage: dict[str, dict[str, Any]] = {}
    for er_id in AUTHORIZED_ER_IDS:
        relevant = [item for item in inventory if er_id in (item.get("authorized_er_ids") or [])]
        source_coverage[er_id] = sorted({item.get("source_class") for item in relevant if item.get("source_class")})
        present = sorted({field for item in relevant for field in item.get("denominator_fields_present") or []})
        required = list(REQUIRED_DENOMINATOR_FIELDS[er_id])
        missing = sorted(set(required) - set(present))
        denominator_coverage[er_id] = {
            "required_fields": required,
            "observed_fields": present,
            "missing_fields": missing,
            "completeness_ratio": 0.0 if not required else round((len(required) - len(missing)) / len(required), 4),
        }
    bindings = frozen["input_bindings"]
    core = {
        "acquisition_wave": "targeted_evidence_acquisition_wave_1b",
        "project_id": frozen["project_id"],
        "research_version_context": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
        "wave_1b_gate_artifact_id": frozen["decision_id"],
        "wave_1b_gate_hash": frozen["content_hash"],
        "upstream_assessment_hash": bindings["wave_1_assessment_hash"],
        "upstream_wave_1_checkpoint_hash": bindings["wave_1_checkpoint_hash"],
        "authorized_er_ids": list(AUTHORIZED_ER_IDS),
        "authorization_scope": "exact_list_only",
        "internal_execution_order": [list(group) for group in INTERNAL_EXECUTION_ORDER],
        "internal_phase_status": {
            "phase_1": "completed" if all(any(er in (a.get("authorized_er_ids") or []) for a in attempts) for er in INTERNAL_EXECUTION_ORDER[0]) else "incomplete",
            "phase_2": "completed" if any("PCB-ER-A02" in (a.get("authorized_er_ids") or []) for a in attempts) else "not_started",
        },
        "candidate_count": len(candidates),
        "formal_attempt_count": len(attempts),
        "preflight_attempt_count": len(preflight_attempt_ids or []),
        "preflight_attempt_ids": sorted(preflight_attempt_ids or []),
        "acquired_count": status_counts["acquired"],
        "blocked_count": status_counts["blocked"],
        "failed_count": status_counts["failed"],
        "html_count": media_counts["text/html"],
        "pdf_count": media_counts["application/pdf"],
        "other_content_count": sum(count for media, count in media_counts.items() if media not in {"text/html", "application/pdf"}),
        "raw_artifact_count": len(inventory),
        "unique_raw_hash_count": len(hash_groups),
        "normalized_artifact_count": sum(item.get("normalization_status") == "normalized" for item in inventory),
        "normalization_failure_count": sum(item.get("normalization_status") == "failed" for item in inventory),
        "exact_duplicate_groups": duplicates,
        "suspected_common_origin_groups": common_origins,
        "provisional_evidence_chain_count": max(0, len(hash_groups) - common_origin_reductions),
        "unknown_publication_date_count": sum(item.get("publication_date_status") == "unknown" for item in inventory),
        "confirmed_publication_date_count": sum(item.get("publication_date_status") == "known" for item in inventory),
        "per_er_attempt_coverage": _coverage(attempts, acquired_only=False),
        "per_er_acquired_coverage": _coverage(attempts, acquired_only=True),
        "per_er_source_class_coverage": source_coverage,
        "per_er_denominator_completeness": denominator_coverage,
        "per_er_terminal_state": {er_id: _terminal_state(attempts, er_id) for er_id in AUTHORIZED_ER_IDS},
        "out_of_scope_candidate_count": out_of_scope_candidate_count,
        "out_of_scope_coverage": 0,
        "security_policy_blocked_count": sum(row.get("failure_class") == "security_policy_blocked" for row in attempts),
        "security_violations": list(security_violations or []),
        "scope_violations": list(scope_violations or []),
        "assessment_started": False,
        "cognition_update_started": False,
        "wave_2_authorized": False,
        "company_mapping_authorized": False,
        "stage_a2_authorized": False,
        "stage_b_authorized": False,
        "created_at": created_at,
        "created_by": "Codex",
    }
    digest = content_sha256(core)
    return {
        "checkpoint_id": f"targeted_acquisition_checkpoint:{sha256(canonical_bytes(core)).hexdigest()[:24]}",
        **core,
        "content_hash": digest,
    }


def validate_wave_1b_checkpoint(
    checkpoint: dict[str, Any], *, gate: dict[str, Any]
) -> dict[str, Any]:
    frozen = validate_wave_1b_gate(gate)
    copied = deepcopy(checkpoint)
    if any(
        copied.get(field) is not False
        for field in (
            "assessment_started", "cognition_update_started", "wave_2_authorized",
            "company_mapping_authorized", "stage_a2_authorized", "stage_b_authorized",
        )
    ):
        raise _invalid("Wave 1b checkpoint enables prohibited downstream activity")
    expected_hash = content_sha256(
        {key: value for key, value in copied.items() if key not in {"checkpoint_id", "content_hash"}}
    )
    expected_id = f"targeted_acquisition_checkpoint:{sha256(canonical_bytes({key: value for key, value in copied.items() if key not in {'checkpoint_id', 'content_hash'}})).hexdigest()[:24]}"
    if copied.get("content_hash") != expected_hash or copied.get("checkpoint_id") != expected_id:
        raise _invalid("Wave 1b checkpoint hash or identity mismatch")
    if copied.get("wave_1b_gate_hash") != frozen["content_hash"]:
        raise _invalid("Wave 1b checkpoint Gate binding mismatch")
    if tuple(copied.get("authorized_er_ids") or ()) != AUTHORIZED_ER_IDS:
        raise _invalid("Wave 1b checkpoint authorized ER list mismatch")
    for field in ("per_er_attempt_coverage", "per_er_acquired_coverage"):
        coverage = copied.get(field) or {}
        if set(coverage) != set(AUTHORIZED_ER_IDS):
            raise _invalid("Wave 1b checkpoint has unauthorized scope coverage", field=field)
    if copied.get("out_of_scope_coverage") != 0 or copied.get("scope_violations"):
        raise _invalid("Wave 1b checkpoint contains scope violations")
    if copied.get("security_violations"):
        raise _invalid("Wave 1b checkpoint contains security violations")
    if any(state not in _TERMINAL_STATES for state in (copied.get("per_er_terminal_state") or {}).values()):
        raise _invalid("Wave 1b checkpoint terminal state is invalid")
    return copied


def validate_wave_1b_repository_bundle(
    *, layout: LayeredResearchLayout | None = None
) -> dict[str, Any]:
    effective = LayeredResearchLayout.default() if layout is None else layout
    directory = effective.root / "acquisition/wave_1b"
    gate = validate_wave_1b_gate(
        json.loads((effective.governance_dir / "ai_pcb_targeted_acquisition_wave_1b_gate_decision_v1.json").read_text(encoding="utf-8"))
    )
    validate_upstream_bindings(gate, layout=effective)
    candidates = [json.loads(line) for line in (directory / "candidates.jsonl").read_text(encoding="utf-8").splitlines() if line]
    attempts = [json.loads(line) for line in (directory / "attempts.jsonl").read_text(encoding="utf-8").splitlines() if line]
    inventory_wrapper = json.loads((directory / "evidence_inventory.json").read_text(encoding="utf-8"))
    inventory = inventory_wrapper["items"]
    checkpoint = validate_wave_1b_checkpoint(
        json.loads((directory / "acquisition_checkpoint.json").read_text(encoding="utf-8")),
        gate=gate,
    )
    candidate_map = {row["candidate_id"]: validate_wave_1b_candidate(row, gate) for row in candidates}
    if len(candidate_map) != len(candidates):
        raise _invalid("Wave 1b bundle has duplicate candidate IDs")
    phases = [row.get("internal_phase") for row in attempts]
    if phases != sorted(phases):
        raise _invalid("Wave 1b attempts violate phase order")
    attempted_ers: set[str] = set()
    for attempt in attempts:
        candidate = candidate_map.get(attempt.get("candidate_id"))
        if candidate is None or attempt.get("authorized_er_ids") != candidate["authorized_er_ids"]:
            raise _invalid("Wave 1b attempt candidate scope mismatch")
        attempted_ers.update(attempt["authorized_er_ids"])
        if attempt.get("proxy_mode") != "direct" or attempt.get("trust_env") is not False:
            raise _invalid("Wave 1b attempt did not use direct fail-closed mode")
        if attempt.get("assessment_started") is not False or attempt.get("cognition_update_started") is not False:
            raise _invalid("Wave 1b attempt started a prohibited downstream action")
        if attempt.get("status") != "acquired" and attempt.get("raw_artifact_created") is not False:
            raise _invalid("Non-acquired Wave 1b attempt claims a raw artifact")
    if attempted_ers != set(AUTHORIZED_ER_IDS):
        raise _invalid("Not every Wave 1b ER has a formal attempt")
    for item in inventory:
        raw_path = effective.root / item["raw_artifact_path"]
        data = raw_path.read_bytes()
        if sha256(data).hexdigest() != item["content_hash"] or len(data) != item["byte_size"]:
            raise _invalid("Wave 1b raw hash or size mismatch", artifact_id=item["artifact_id"])
        if item.get("published_at") is not None and item.get("publication_date_status") != "known":
            raise _invalid("Unknown Wave 1b publication date was inferred")
        document_id = item.get("normalized_document_id")
        if document_id is None:
            continue
        wrapper = json.loads((effective.evidence_normalized_dir / f"{document_id}.json").read_text(encoding="utf-8"))
        document = validate_normalized_document(wrapper["normalized_document"])
        legacy = json.loads((effective.evidence_metadata_dir / f"{document['artifact_id']}.json").read_text(encoding="utf-8"))["evidence_artifact"]
        if legacy["content_sha256"] != item["content_hash"] or legacy["raw_path"] != item["raw_artifact_path"]:
            raise _invalid("Wave 1b normalized lineage mismatch")
    if inventory_wrapper.get("content_hash") != content_sha256(inventory):
        raise _invalid("Wave 1b inventory hash mismatch")
    if checkpoint["formal_attempt_count"] != len(attempts) or checkpoint["raw_artifact_count"] != len(inventory):
        raise _invalid("Wave 1b checkpoint counts differ from bundle")
    return {
        "valid": True,
        "checkpoint_id": checkpoint["checkpoint_id"],
        "checkpoint_hash": checkpoint["content_hash"],
        "candidate_count": len(candidates),
        "formal_attempt_count": len(attempts),
        "raw_artifact_count": len(inventory),
    }
