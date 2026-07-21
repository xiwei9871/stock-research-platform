from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.discovery import source_candidate_id
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.normalize import validate_normalized_document


AUTHORIZED_ER_IDS = (
    "PCB-ER-A01",
    "PCB-ER-A02",
    "PCB-ER-A03",
    "PCB-ER-A04",
    "PCB-ER-B01",
    "PCB-ER-B02",
)
INTERNAL_EXECUTION_ORDER = (
    ("PCB-ER-A01", "PCB-ER-A04", "PCB-ER-B01"),
    ("PCB-ER-A02", "PCB-ER-A03"),
    ("PCB-ER-B02",),
)
_ER_PHASE = {
    er_id: phase
    for phase, group in enumerate(INTERNAL_EXECUTION_ORDER, start=1)
    for er_id in group
}
_PUBLICATION_DATE_STATES = {"known", "unknown"}
_TERMINAL_STATES = {
    "acquisition_complete_for_assessment",
    "acquisition_partial_with_gaps",
    "acquisition_stopped_due_to_redundancy",
    "acquisition_stopped_due_to_public_limit",
    "acquisition_blocked",
}


def _invalid(message: str, *, details: dict[str, Any] | None = None) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        message,
        code="RESEARCH_PROJECT_V2_1_WAVE_1_INVALID",
        details={} if details is None else details,
    )


def validate_gate_decision(payload: dict[str, Any]) -> dict[str, Any]:
    gate = deepcopy(payload)
    expected_hash = content_sha256(gate, excluded_paths=(("content_hash",),))
    if gate.get("content_hash") != expected_hash:
        raise _invalid("Gate artifact hash mismatch")
    if gate.get("artifact_type") != "targeted_acquisition_gate_decision" or gate.get("decision_status") != "frozen":
        raise _invalid("Gate artifact is not a frozen targeted-acquisition decision")
    authorization = gate.get("authorization") or {}
    if (
        authorization.get("targeted_acquisition_authorized") is not True
        or authorization.get("authorization_scope") != "exact_list_only"
        or authorization.get("unlisted_er_authorized") is not False
    ):
        raise _invalid("Gate does not satisfy the fail-closed exact-list policy")
    if tuple(gate.get("authorized_for_targeted_acquisition") or ()) != AUTHORIZED_ER_IDS:
        raise _invalid("Gate authorized ER list does not match Wave 1")
    if tuple(tuple(group) for group in gate.get("execution_order") or ()) != INTERNAL_EXECUTION_ORDER:
        raise _invalid("Gate internal execution order does not match Wave 1")
    if any(
        gate.get(field) is not False
        for field in ("company_mapping_authorized", "stage_a2_authorized", "stage_b_authorized")
    ):
        raise _invalid("Gate authorizes a prohibited downstream stage")
    return gate


def validate_wave_candidate(candidate: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any]:
    validate_gate_decision(gate)
    copied = deepcopy(candidate)
    er_ids = copied.get("authorized_er_ids")
    if not isinstance(er_ids, list) or not er_ids or len(set(er_ids)) != len(er_ids):
        raise _invalid("Candidate authorized_er_ids must be a non-empty unique list")
    unauthorized = sorted(set(er_ids) - set(AUTHORIZED_ER_IDS))
    if unauthorized:
        raise _invalid("Candidate contains an ER that is not authorized", details={"er_ids": unauthorized})
    phases = {_ER_PHASE[er_id] for er_id in er_ids}
    if len(phases) != 1 or copied.get("internal_phase") not in phases:
        raise _invalid("Candidate internal phase does not match its authorized ER phase")
    required = (
        "candidate_id",
        "source_title",
        "provider_source_title",
        "source_owner",
        "source_class",
        "source_url",
        "expected_evidence_role",
        "eligibility_reason",
        "known_limitations",
        "publication_date_status",
        "candidate_status",
    )
    missing = [field for field in required if field not in copied]
    if missing:
        raise _invalid("Candidate is missing required fields", details={"fields": missing})
    if copied["publication_date_status"] not in _PUBLICATION_DATE_STATES:
        raise _invalid("Candidate publication date status is invalid")
    if copied["candidate_status"] not in {"eligible", "ineligible", "blocked_lead"}:
        raise _invalid("Candidate status is invalid")
    normalized_url = _normalized_url(copied["source_url"])
    if copied["candidate_id"] != source_candidate_id(normalized_url, copied["provider_source_title"]):
        raise _invalid("Candidate identity does not match the provider candidate contract")
    return copied


def _normalized_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))


def to_provider_candidate(
    candidate: dict[str, Any],
    *,
    discovered_at: str,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    publish_date = candidate.get("publication_date") if candidate.get("publication_date_status") == "known" else None
    normalized_url = _normalized_url(candidate["source_url"])
    return {
        "candidate_id": candidate["candidate_id"],
        "search_plan_id": "search_plan:ai_pcb_targeted_wave_1",
        "query_id": f"wave_1_phase_{candidate['internal_phase']}",
        "normalized_url": normalized_url,
        "original_url": candidate["source_url"],
        "title": candidate["provider_source_title"],
        "snippet": "",
        "publisher": candidate["source_owner"],
        "publish_date": publish_date,
        "source_class": candidate["source_class"],
        "rank": int(candidate.get("rank", 1)),
        "exclusion_status": "included",
        "exclusion_reasons": [],
        "dedup_key": normalized_url,
        "provenance": deepcopy(provenance),
        "discovered_at": discovered_at,
    }


def build_wave_attempt_record(
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
        "security_status": "blocked" if provider_attempt.get("failure_code") == "security_policy_blocked" else "passed",
        "diagnostic_summary": provider_attempt.get("diagnostic_summary"),
        "assessment_started": False,
    }


def _coverage(records: Iterable[dict[str, Any]], *, acquired_only: bool) -> dict[str, int]:
    coverage = {er_id: 0 for er_id in AUTHORIZED_ER_IDS}
    for record in records:
        if acquired_only and record.get("status") != "acquired":
            continue
        for er_id in record.get("authorized_er_ids") or ():
            coverage[er_id] = coverage.get(er_id, 0) + 1
    return coverage


def _terminal_state(attempts: list[dict[str, Any]], er_id: str) -> str:
    relevant = [row for row in attempts if er_id in (row.get("authorized_er_ids") or ())]
    if not relevant or all(row.get("status") == "blocked" for row in relevant):
        return "acquisition_blocked"
    if any(row.get("status") == "acquired" for row in relevant):
        return "acquisition_complete_for_assessment"
    return "acquisition_partial_with_gaps"


def build_wave_checkpoint(
    *,
    gate: dict[str, Any],
    candidates: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    created_at: str,
    suspected_common_origin_groups: list[list[str]] | None = None,
    out_of_scope_candidate_count: int = 0,
    engineering_preflight_attempt_ids: list[str] | None = None,
) -> dict[str, Any]:
    frozen_gate = validate_gate_decision(gate)
    candidate_map = {row["candidate_id"]: validate_wave_candidate(row, frozen_gate) for row in candidates}
    if len(candidate_map) != len(candidates):
        raise _invalid("Duplicate Wave 1 candidate ID")
    for attempt in attempts:
        er_ids = attempt.get("authorized_er_ids") or []
        unauthorized = sorted(set(er_ids) - set(AUTHORIZED_ER_IDS))
        if unauthorized:
            # Preserve construction for negative validator tests; validator remains fail-closed.
            continue
        if attempt.get("candidate_id") not in candidate_map:
            raise _invalid("Attempt references an unknown Wave 1 candidate")
    status_counts = Counter(row.get("status") for row in attempts)
    hash_groups: dict[str, list[str]] = defaultdict(list)
    for row in inventory:
        if row.get("content_hash"):
            hash_groups[row["content_hash"]].append(row["artifact_id"])
    duplicates = sorted(sorted(group) for group in hash_groups.values() if len(group) > 1)
    common_origin_groups = sorted(suspected_common_origin_groups or [])
    common_origin_reductions = sum(max(0, len(set(group)) - 1) for group in common_origin_groups)
    media_counts = Counter(row.get("content_type") for row in inventory)
    normalized_count = sum(bool(row.get("normalized_document_id")) for row in inventory)
    normalization_failures = sum(row.get("normalization_status") == "failed" for row in inventory)
    core = {
        "acquisition_wave": "targeted_evidence_acquisition_wave_1",
        "project_id": frozen_gate["project_id"],
        "research_version_context": "research_version:ai_compute_pcb_industry_bottleneck:0.2.1",
        "gate_artifact_id": frozen_gate["decision_id"],
        "gate_artifact_hash": frozen_gate["content_hash"],
        "authorized_er_ids": list(AUTHORIZED_ER_IDS),
        "authorization_scope": "exact_list_only",
        "internal_execution_order": [list(group) for group in INTERNAL_EXECUTION_ORDER],
        "candidate_count": len(candidates),
        "attempt_count": len(attempts),
        "acquired_count": status_counts["acquired"],
        "blocked_count": status_counts["blocked"],
        "failed_count": status_counts["failed"],
        "html_count": media_counts["text/html"],
        "pdf_count": media_counts["application/pdf"],
        "other_content_count": sum(
            count for media, count in media_counts.items() if media not in {"text/html", "application/pdf"}
        ),
        "raw_artifact_count": len(inventory),
        "unique_raw_hash_count": len(hash_groups),
        "normalized_artifact_count": normalized_count,
        "normalization_failure_count": normalization_failures,
        "duplicate_groups": duplicates,
        "suspected_common_origin_groups": common_origin_groups,
        "evidence_chain_count": max(0, len(hash_groups) - common_origin_reductions),
        "unknown_publication_date_count": sum(row.get("publication_date_status") == "unknown" for row in inventory),
        "per_er_attempt_coverage": _coverage(attempts, acquired_only=False),
        "per_er_acquired_coverage": _coverage(attempts, acquired_only=True),
        "per_er_terminal_state": {er_id: _terminal_state(attempts, er_id) for er_id in AUTHORIZED_ER_IDS},
        "out_of_scope_candidate_count": out_of_scope_candidate_count,
        "out_of_scope_coverage_count": 0,
        "engineering_preflight_attempt_count": len(engineering_preflight_attempt_ids or []),
        "engineering_preflight_attempt_ids": sorted(engineering_preflight_attempt_ids or []),
        "engineering_preflight_coverage_count": 0,
        "security_violations": 0,
        "scope_violations": 0,
        "assessment_started": False,
        "stage_a2_authorized": False,
        "stage_b_authorized": False,
        "company_mapping_authorized": False,
        "created_at": created_at,
        "created_by": "Codex",
    }
    digest = content_sha256(core)
    return {
        "checkpoint_id": f"targeted_acquisition_checkpoint:{sha256(canonical_bytes(core)).hexdigest()[:24]}",
        **core,
        "content_hash": digest,
    }


def validate_wave_checkpoint(checkpoint: dict[str, Any], *, gate: dict[str, Any]) -> dict[str, Any]:
    frozen_gate = validate_gate_decision(gate)
    copied = deepcopy(checkpoint)
    if any(copied.get(field) is not False for field in ("assessment_started", "stage_a2_authorized", "stage_b_authorized", "company_mapping_authorized")):
        raise _invalid("Wave checkpoint enables a prohibited downstream activity")
    all_coverage_ids = set((copied.get("per_er_attempt_coverage") or {})) | set((copied.get("per_er_acquired_coverage") or {}))
    unauthorized = sorted(all_coverage_ids - set(AUTHORIZED_ER_IDS))
    if unauthorized:
        raise _invalid("Wave checkpoint contains unauthorized ER coverage", details={"er_ids": unauthorized})
    expected_hash = content_sha256(
        {key: value for key, value in copied.items() if key not in {"checkpoint_id", "content_hash"}}
    )
    expected_id = f"targeted_acquisition_checkpoint:{sha256(canonical_bytes({key: value for key, value in copied.items() if key not in {'checkpoint_id', 'content_hash'}})).hexdigest()[:24]}"
    if copied.get("content_hash") != expected_hash or copied.get("checkpoint_id") != expected_id:
        raise _invalid("Wave checkpoint hash or identity mismatch")
    if copied.get("gate_artifact_hash") != frozen_gate["content_hash"]:
        raise _invalid("Wave checkpoint Gate binding mismatch")
    if tuple(copied.get("authorized_er_ids") or ()) != AUTHORIZED_ER_IDS:
        raise _invalid("Wave checkpoint authorized ER list mismatch")
    if any(state not in _TERMINAL_STATES for state in (copied.get("per_er_terminal_state") or {}).values()):
        raise _invalid("Wave checkpoint contains an invalid terminal state")
    return copied


def validate_wave_repository_bundle(
    *,
    layout: LayeredResearchLayout | None = None,
    wave_dir: Path | None = None,
) -> dict[str, Any]:
    effective = LayeredResearchLayout.default() if layout is None else layout
    directory = effective.root / "acquisition/wave_1" if wave_dir is None else wave_dir
    gate = validate_gate_decision(
        json.loads(
            (effective.governance_dir / "ai_pcb_targeted_acquisition_gate_decision_v1.json").read_text(encoding="utf-8")
        )
    )
    candidates = [json.loads(line) for line in (directory / "candidates.jsonl").read_text(encoding="utf-8").splitlines() if line]
    attempts = [json.loads(line) for line in (directory / "attempts.jsonl").read_text(encoding="utf-8").splitlines() if line]
    inventory_wrapper = json.loads((directory / "evidence_inventory.json").read_text(encoding="utf-8"))
    inventory = inventory_wrapper["items"]
    checkpoint = validate_wave_checkpoint(
        json.loads((directory / "acquisition_checkpoint.json").read_text(encoding="utf-8")),
        gate=gate,
    )
    if inventory_wrapper.get("content_hash") != content_sha256(inventory):
        raise _invalid("Wave inventory hash mismatch")
    candidate_map = {row["candidate_id"]: validate_wave_candidate(row, gate) for row in candidates}
    if len(candidate_map) != len(candidates):
        raise _invalid("Wave bundle contains duplicate candidate IDs")
    phases = [row.get("internal_phase") for row in attempts]
    if phases != sorted(phases):
        raise _invalid("Wave attempts violate the frozen internal phase order")
    attempted_ers: set[str] = set()
    for attempt in attempts:
        candidate = candidate_map.get(attempt.get("candidate_id"))
        if candidate is None:
            raise _invalid("Wave attempt references an unknown candidate")
        if attempt.get("authorized_er_ids") != candidate["authorized_er_ids"]:
            raise _invalid("Wave attempt ER scope differs from its candidate")
        attempted_ers.update(attempt["authorized_er_ids"])
        if attempt.get("proxy_mode") != "direct" or attempt.get("trust_env") is not False:
            raise _invalid("Wave attempt did not use the frozen direct network mode")
        if attempt.get("assessment_started") is not False:
            raise _invalid("Wave attempt started Evidence Assessment")
        if attempt.get("status") != "acquired" and attempt.get("raw_artifact_created") is not False:
            raise _invalid("Non-acquired attempt claims a raw artifact")
    if attempted_ers != set(AUTHORIZED_ER_IDS):
        raise _invalid("Not every authorized ER has a Wave attempt")
    for item in inventory:
        raw_path = effective.root / item["raw_artifact_path"]
        data = raw_path.read_bytes()
        if sha256(data).hexdigest() != item["content_hash"] or len(data) != item["byte_size"]:
            raise _invalid("Wave raw artifact hash or size mismatch", details={"artifact_id": item["artifact_id"]})
        if item["published_at"] is not None and item["publication_date_status"] != "known":
            raise _invalid("Unknown-date artifact was assigned a publication date")
        document_id = item.get("normalized_document_id")
        if document_id is None:
            continue
        wrapper = json.loads((effective.evidence_normalized_dir / f"{document_id}.json").read_text(encoding="utf-8"))
        document = validate_normalized_document(wrapper["normalized_document"])
        legacy_wrapper = json.loads((effective.evidence_metadata_dir / f"{document['artifact_id']}.json").read_text(encoding="utf-8"))
        legacy = legacy_wrapper["evidence_artifact"]
        if legacy["content_sha256"] != item["content_hash"] or legacy["raw_path"] != item["raw_artifact_path"]:
            raise _invalid("Normalized document does not trace to the Wave raw artifact")
    if checkpoint["attempt_count"] != len(attempts) or checkpoint["raw_artifact_count"] != len(inventory):
        raise _invalid("Wave checkpoint counts do not match its bundle")
    return {
        "valid": True,
        "checkpoint_id": checkpoint["checkpoint_id"],
        "checkpoint_hash": checkpoint["content_hash"],
        "candidate_count": len(candidates),
        "attempt_count": len(attempts),
        "raw_artifact_count": len(inventory),
    }
