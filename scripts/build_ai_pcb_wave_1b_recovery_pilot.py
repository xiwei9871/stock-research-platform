from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2_1.acquisition_capability import (
    classify_candidate_content,
    extract_document_identity,
    match_evidence_shape,
)
from stock_research.research_project_v2_1.acquisition_contracts import (
    AcquisitionContext,
    build_acquisition_attempt,
)
from stock_research.research_project_v2_1.acquisition_http import DirectHttpProvider
from stock_research.research_project_v2_1.acquisition_storage import write_acquisition_attempt
from stock_research.research_project_v2_1.discovery import source_candidate_id
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.normalize import normalize_artifact, write_normalized_document
from stock_research.research_project_v2_1.snapshot import _publish_bytes
from stock_research.research_project_v2_1.wave_1b import REQUIRED_DENOMINATOR_FIELDS
from stock_research.research_project_v2_1.wave_1b_recovery import (
    build_recovery_checkpoint,
    recovery_identity_matches,
    validate_recovery_authorization,
    validate_recovery_checkpoint,
)


LAYOUT = LayeredResearchLayout.default()
OUT = LAYOUT.root / "acquisition/wave_1b_recovery_pilot"
GATE_PATH = LAYOUT.governance_dir / "ai_pcb_wave_1b_recovery_pilot_gate_decision_v1.json"
AUTH_PATH = LAYOUT.governance_dir / "ai_pcb_wave_1b_recovery_pilot_execution_authorization_v1.json"
WAVE_1B_CANDIDATES = LAYOUT.root / "acquisition/wave_1b/candidates.jsonl"
VERSION = "research_version:ai_compute_pcb_industry_bottleneck:0.2.1"


RESOLVED_ENTRIES: dict[str, dict[str, Any]] = {
    "recovery_target:ai_pcb:wave_1b:a04:keysight_deembedding:v1": {
        "resolved_entry_url": None,
        "resolution_status": "not_resolved",
        "resolution_note": "Official search returned HTTP 403 and the one permitted migrated-path probe returned HTTP 404.",
        "discovery_request_count": 2,
        "discovery_trace": [
            {"url": "https://www.keysight.com/us/en/search.html?q=de-embedding", "result": "http_403"},
            {"url": "https://helpfiles.keysight.com/csg/N1930xB/Content/Analyzing/De-embedding.htm", "result": "http_404"}
        ],
    },
    "recovery_target:ai_pcb:wave_1b:a04:anritsu_deembedding:v1": {
        "resolved_entry_url": None,
        "resolution_status": "not_resolved",
        "resolution_note": "Official search was security-policy blocked and the one permitted migrated-PDF probe returned HTTP 404.",
        "discovery_request_count": 2,
        "discovery_trace": [
            {"url": "https://www.anritsu.com/en-us/search?query=de-embedding", "result": "security_policy_blocked"},
            {"url": "https://dl.cdn-anritsu.com/en-us/test-measurement/files/Technical-Notes/White-Paper/De-embedding_11410-00964.pdf", "result": "http_404"}
        ],
    },
    "recovery_target:ai_pcb:wave_1b:b01:ipc_equivalent_method:v1": {
        "resolved_entry_url": None,
        "resolution_status": "not_resolved",
        "resolution_note": "The permitted legacy method path returned HTTP 404 and the current IPC path remained security-policy blocked; no qualified equivalent full text was identified.",
        "discovery_request_count": 2,
        "discovery_trace": [
            {"url": "https://www.electronics.org/sites/default/files/test_methods_docs/2-5-5-5.pdf", "result": "http_404"},
            {"url": "https://www.ipc.org/sites/default/files/test_methods_docs/2-5-5-5.pdf", "result": "security_policy_blocked"}
        ],
    },
    "recovery_target:ai_pcb:wave_1b:b01:panasonic_bounded_retry:v1": {
        "resolved_entry_url": "https://industrial.panasonic.com/ww/products/pt/megtron/megtron6",
        "resolution_status": "same_url_bounded_retry",
        "resolution_note": "Execution Authorization permits exactly one retry of the original Panasonic URL.",
        "discovery_request_count": 0,
        "discovery_trace": [],
    },
    "recovery_target:ai_pcb:wave_1b:b02:usc_repository_alternative:v1": {
        "resolved_entry_url": "https://scholarcommons.sc.edu/etd/2947/",
        "resolution_status": "derived_official_repository_entry",
        "resolution_note": "Two permitted repository landing-page probes established the repository article-to-landing pattern; the formal attempt must verify the exact title and identity.",
        "discovery_request_count": 2,
        "discovery_trace": [
            {"url": "https://scholarcommons.sc.edu/etd/2964/", "result": "acquired_identity_mismatch"},
            {"url": "https://scholarcommons.sc.edu/etd/2965/", "result": "acquired_identity_mismatch"}
        ],
    },
    "recovery_target:ai_pcb:wave_1b:a02:etc_800g_migrated_entry:v1": {
        "resolved_entry_url": None,
        "resolution_status": "not_resolved",
        "resolution_note": "The two permitted official-domain discovery entries returned HTTP 403; no migrated revision-1.0 full text was identified.",
        "discovery_request_count": 2,
        "discovery_trace": [
            {"url": "https://ethernettechnologyconsortium.org/wp-sitemap-posts-page-1.xml", "result": "http_403"},
            {"url": "https://ethernettechnologyconsortium.org/", "result": "http_403"}
        ],
    },
    "recovery_target:ai_pcb:wave_1b:a02:ieee_802_3ck_index_to_fulltext:v1": {
        "resolved_entry_url": "https://www.ieee802.org/3/ck/public/19_05/heck_3ck_01_0519.pdf",
        "resolution_status": "explicit_link_from_frozen_index",
        "resolution_note": "The single permitted May 2019 index resolution exposed this exact public PDF link.",
        "discovery_request_count": 1,
        "discovery_trace": [
            {"url": "https://www.ieee802.org/3/ck/public/19_05/index.html", "result": "acquired_explicit_pdf_link"}
        ],
    },
}


DENOMINATOR_TERMS = {
    "frequency_range": ("ghz", "frequency range"),
    "comparison_frequency": ("at 10 ghz", "at 20 ghz", "frequency"),
    "nyquist_frequency": ("nyquist",),
    "channel_length": ("channel length", "mm", "inch"),
    "unit": ("db", "db/in", "db/cm"),
    "differential_or_single_ended": ("differential", "single-ended"),
    "reference_plane": ("reference plane",),
    "fixture_configuration": ("fixture", "launch", "probe"),
    "deembedding_method": ("de-embedding", "deembedding"),
    "coupon_or_actual_channel": ("coupon", "channel"),
    "temperature": ("temperature",),
    "environment": ("humidity", "environment"),
    "uncertainty_or_repeatability": ("uncertainty", "repeatability", "tolerance"),
    "test_method": ("test method", "ipc-tm", "clamped stripline"),
    "frequency": ("mhz", "ghz", "frequency"),
    "humidity": ("humidity",),
    "material_direction": ("x direction", "y direction", "z direction", "direction"),
    "sample_geometry": ("sample", "specimen", "stripline"),
    "sample_thickness": ("thickness",),
    "resin_content": ("resin content",),
    "glass_style": ("glass style", "glass cloth"),
    "copper_condition": ("copper", "foil"),
    "nominal_typical_or_guaranteed": ("nominal", "typical", "guaranteed"),
    "design_dk_or_test_dk": ("design dk", "dielectric constant", "permittivity"),
    "measurement_uncertainty": ("uncertainty", "tolerance"),
    "surface_profile_metric": ("rz", "ra", "rq", "rms", "roughness"),
    "treatment_type": ("treatment", "rtf", "vlp"),
    "trace_geometry": ("trace", "stripline", "microstrip"),
    "copper_thickness": ("copper thickness",),
    "dielectric_thickness": ("dielectric thickness",),
    "material_system": ("laminate", "dielectric", "resin"),
    "measurement_or_simulation_method": ("vna", "measured", "simulation", "s21"),
    "temperature_environment": ("temperature", "humidity", "environment"),
    "data_rate": ("gb/s", "gbps", "data rate"),
    "baud_rate": ("gbaud", "gbd", "baud"),
    "modulation": ("pam4", "nrz", "modulation"),
    "topology": ("topology", "link", "point-to-point"),
    "pcb_length": ("pcb length", "host pcb", "board trace"),
    "connector_count": ("connector",),
    "cable_length": ("cable length",),
    "retimer_presence": ("retimer", "retimed"),
    "equalization_assumption": ("equalization", "ffe", "dfe", "ctle"),
    "insertion_loss": ("insertion loss", "s21", "sdd21"),
    "return_loss": ("return loss", "s11", "sdd11"),
    "crosstalk": ("crosstalk", "next", "fext"),
    "ber_or_compliance_metric": ("ber", "bit error", "compliance", "com"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def provenance(created_at: str) -> dict[str, Any]:
    return {
        "created_by": "Codex",
        "actor_type": "codex",
        "agent_run_id": "ai-pcb-wave-1b-recovery-pilot-20260722",
        "created_at": created_at,
        "created_in_version": VERSION,
        "review_status": "unreviewed",
    }


def load_original_candidates() -> dict[str, dict[str, Any]]:
    return {
        row["candidate_id"]: row
        for row in (
            json.loads(line)
            for line in WAVE_1B_CANDIDATES.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }


def provider_candidate(
    *, target: dict[str, Any], original: dict[str, Any], url: str,
    discovered_at: str, prov: dict[str, Any],
) -> dict[str, Any]:
    parts = urlsplit(url)
    normalized_url = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))
    title = f"{original['source_title']} [{target['recovery_target_id']}]"
    return {
        "candidate_id": source_candidate_id(normalized_url, title),
        "search_plan_id": "search_plan:ai_pcb_wave_1b_recovery_pilot",
        "query_id": target["recovery_target_id"],
        "normalized_url": normalized_url,
        "original_url": normalized_url,
        "title": title,
        "snippet": "",
        "publisher": original["source_owner"],
        "publish_date": None,
        "source_class": original["source_class"],
        "rank": 1,
        "exclusion_status": "included",
        "exclusion_reasons": [],
        "dedup_key": normalized_url,
        "provenance": prov,
        "discovered_at": discovered_at,
    }


def resolver_failure(
    *, target: dict[str, Any], resolution: dict[str, Any], prov: dict[str, Any],
) -> dict[str, Any]:
    now = utc_now()
    built = build_acquisition_attempt(
        context=AcquisitionContext(
            project_id="research_project:ai_compute_pcb_industry_bottleneck",
            research_version_context=VERSION,
            requirement_id=target["authorized_er_id"],
            candidate_id=target["original_candidate_id"],
            provenance=prov,
        ),
        provider="search_discovery",
        request_mode="discovery",
        proxy_mode="direct",
        requested_url=None,
        resolved_url=None,
        attempted_at=now,
        completed_at=now,
        elapsed_ms=0,
        status="failed",
        failure_code="manually_unavailable",
        http_status=None,
        redirect_chain=[],
        content_type=None,
        bytes_received=0,
        retry_count=0,
        raw_artifact_id=None,
        diagnostic_summary=resolution["resolution_note"],
        failure_details=None,
    )
    write_acquisition_attempt(built.payload, layout=LAYOUT)
    return built.payload


def find_legacy_artifact(candidate_id: str, content_hash: str) -> dict[str, Any]:
    matches = []
    for path in LAYOUT.evidence_metadata_dir.glob("*.json"):
        item = json.loads(path.read_text(encoding="utf-8")).get("evidence_artifact", {})
        if item.get("candidate_id") == candidate_id and item.get("content_sha256") == content_hash:
            matches.append(item)
    if len(matches) != 1:
        raise RuntimeError(f"Expected one legacy artifact for {candidate_id}, found {len(matches)}")
    return matches[0]


def find_existing_attempt(target: dict[str, Any], resolved_url: str | None) -> dict[str, Any] | None:
    matches = []
    for path in LAYOUT.acquisition_attempts_dir.glob("*.json"):
        item = json.loads(path.read_text(encoding="utf-8")).get("acquisition_attempt", {})
        if item.get("provenance", {}).get("agent_run_id") != "ai-pcb-wave-1b-recovery-pilot-20260722":
            continue
        if item.get("requirement_id") != target["authorized_er_id"]:
            continue
        if resolved_url is None:
            if item.get("candidate_id") == target["original_candidate_id"] and item.get("provider") == "search_discovery":
                matches.append(item)
        elif item.get("requested_url") == resolved_url:
            matches.append(item)
    if len(matches) > 1:
        raise RuntimeError(f"Multiple formal attempts exist for {target['recovery_target_id']}")
    return None if not matches else matches[0]


def load_v2_3_artifact(artifact_id: str | None) -> dict[str, Any] | None:
    if artifact_id is None:
        return None
    path = LAYOUT.evidence_metadata_v2_3_dir / f"{artifact_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))["evidence_artifact"]


def find_existing_normalized(candidate_id: str, content_hash: str) -> dict[str, Any] | None:
    legacy = find_legacy_artifact(candidate_id, content_hash)
    for path in sorted(LAYOUT.evidence_normalized_dir.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8")).get("normalized_document", {})
        if document.get("artifact_id") == legacy.get("artifact_id"):
            return document
    return None


def normalized_representation_ids(candidate_id: str, content_hash: str) -> list[str]:
    legacy = find_legacy_artifact(candidate_id, content_hash)
    result = []
    for path in sorted(LAYOUT.evidence_normalized_dir.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8")).get("normalized_document", {})
        if document.get("artifact_id") == legacy.get("artifact_id"):
            result.append(document["document_id"])
    return result


def observed_denominators(document: dict[str, Any], er_id: str) -> list[str]:
    text = "\n".join(section.get("text", "") for section in document.get("sections", [])).lower()
    return [
        field for field in REQUIRED_DENOMINATOR_FIELDS[er_id]
        if any(term in text for term in DENOMINATOR_TERMS.get(field, ()))
    ]


def write_json(name: str, payload: dict[str, Any]) -> None:
    _publish_bytes(OUT, name, canonical_bytes(payload))


def write_jsonl(name: str, rows: list[dict[str, Any]]) -> None:
    _publish_bytes(OUT, name, b"".join(canonical_bytes(row) + b"\n" for row in rows))


def main() -> None:
    gate = json.loads(GATE_PATH.read_text(encoding="utf-8"))
    authorization = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    validate_recovery_authorization(authorization, gate=gate, layout=LAYOUT)
    originals = load_original_candidates()
    started_at = utc_now()
    prov = provenance(started_at)
    provider = DirectHttpProvider(headers={"User-Agent": "StockResearchRecoveryPilot/1.0"})
    target_records: list[dict[str, Any]] = []
    attempt_records: list[dict[str, Any]] = []
    inventory: list[dict[str, Any]] = []
    normalized_associations: list[dict[str, Any]] = []

    gate_targets = {row["recovery_target_id"]: row for row in gate["selected_targets"]}
    for authorized in authorization["authorized_targets"]:
        target = gate_targets[authorized["recovery_target_id"]]
        resolution = RESOLVED_ENTRIES[target["recovery_target_id"]]
        original = originals[target["original_candidate_id"]]
        resolved_url = resolution["resolved_entry_url"]
        artifact = None
        provider_id = None
        normalized_document = None
        normalization_status = "not_applicable"
        normalization_error = None
        denominator_fields: list[str] = []
        content_class = "unknown"
        identity_status = "unresolved"
        target_evidence_match = "does_not_answer_er"
        identity_match = False

        provider_attempt = find_existing_attempt(target, resolved_url)
        if provider_attempt is not None:
            provider_id = provider_attempt.get("candidate_id") if resolved_url is not None else None
            artifact = load_v2_3_artifact(provider_attempt.get("raw_artifact_id"))
        elif resolved_url is None:
            provider_attempt = resolver_failure(target=target, resolution=resolution, prov=prov)
        else:
            candidate = provider_candidate(
                target=target, original=original, url=resolved_url,
                discovered_at=started_at, prov=prov,
            )
            provider_id = candidate["candidate_id"]
            provider_result = provider.acquire(
                candidate,
                context=AcquisitionContext(
                    project_id=authorization["project_id"],
                    research_version_context=VERSION,
                    requirement_id=target["authorized_er_id"],
                    candidate_id=provider_id,
                    provenance=prov,
                ),
                layout=LAYOUT,
                proxy_mode="direct",
                timeout_seconds=20.0,
                max_redirects=target["redirect_limit"],
                max_bytes=30 * 1024 * 1024,
                max_retries=0,
            )
            provider_attempt = provider_result.attempt
            artifact = provider_result.artifact
        if artifact is not None:
            try:
                normalized_document = find_existing_normalized(provider_id, artifact["content_hash"])
                if normalized_document is None:
                    legacy = find_legacy_artifact(provider_id, artifact["content_hash"])
                    normalized_document = normalize_artifact(
                        legacy,
                        layout=LAYOUT,
                        parsed_at=provider_attempt["completed_at"],
                        provenance=prov,
                    )
                    write_normalized_document(normalized_document, layout=LAYOUT)
                normalization_status = "normalized"
                denominator_fields = observed_denominators(normalized_document, target["authorized_er_id"])
                resolved_source_class = (
                    "standards_working_group_measurement"
                    if ":a02:ieee_802_3ck_index_to_fulltext:" in target["recovery_target_id"]
                    else original["source_class"]
                )
                qualified_candidate = {
                    "source_title": normalized_document.get("title") or original["source_title"],
                    "source_owner": original["source_owner"],
                    "source_class": resolved_source_class,
                    "source_url": resolved_url,
                }
                content_class = classify_candidate_content(
                    qualified_candidate,
                    {"status": "acquired", "content_type": provider_attempt.get("content_type"), "http_status": provider_attempt.get("http_status")},
                    normalized_document,
                )["candidate_content_class"]
                identity = extract_document_identity(qualified_candidate, normalized_document)
                identity_status = identity["document_identity_confidence"]
                document_text = "\n".join(
                    section.get("text", "")
                    for section in normalized_document.get("sections", [])
                )
                identity_match = recovery_identity_matches(
                    target_id=target["recovery_target_id"],
                    expected_title=target["target_document_identity"],
                    document_title=normalized_document.get("title"),
                    document_text=document_text,
                    resolved_url=provider_attempt.get("resolved_url") or resolved_url,
                )
                target_evidence_match = match_evidence_shape(
                    target["authorized_er_id"], content_class,
                    denominator_fields, resolved_source_class,
                )["target_evidence_match"]
            except Exception as exc:
                normalization_status = "failed"
                normalization_error = f"{type(exc).__name__}: {exc}"

        wrapper = {
            "recovery_target_id": target["recovery_target_id"],
            "original_candidate_id": target["original_candidate_id"],
            "resolved_entry_candidate_id": provider_id,
            "authorized_er_id": target["authorized_er_id"],
            "authorized_recovery_action": target["authorized_recovery_action"],
            "resolved_entry_url": resolved_url,
            "discovery_request_count": resolution["discovery_request_count"],
            "discovery_trace": resolution["discovery_trace"],
            "attempt_id": provider_attempt["attempt_id"],
            "provider": provider_attempt["provider"],
            "request_mode": provider_attempt["request_mode"],
            "status": provider_attempt["status"],
            "failure_code": provider_attempt.get("failure_code"),
            "http_status": provider_attempt.get("http_status"),
            "raw_artifact_id": provider_attempt.get("raw_artifact_id"),
            "content_hash": None if artifact is None else artifact["content_hash"],
            "normalized_document_id": None if normalized_document is None else normalized_document["document_id"],
            "normalization_status": normalization_status,
            "normalization_error": normalization_error,
            "candidate_content_class": content_class,
            "document_identity_status": identity_status,
            "identity_match": identity_match,
            "target_evidence_match": target_evidence_match,
            "denominator_fields_present": denominator_fields,
            "assessment_started": False,
            "cognition_update_started": False,
        }
        attempt_records.append(wrapper)
        target_records.append({
            "recovery_target_id": target["recovery_target_id"],
            "original_candidate_id": target["original_candidate_id"],
            "authorized_er_id": target["authorized_er_id"],
            "authorized_recovery_action": target["authorized_recovery_action"],
            "resolution_status": resolution["resolution_status"],
            "resolved_entry_url": resolved_url,
            "resolution_note": resolution["resolution_note"],
            "discovery_request_count": resolution["discovery_request_count"],
            "formal_attempt_id": provider_attempt["attempt_id"],
        })
        if artifact is not None:
            resolved_source_class = (
                "standards_working_group_measurement"
                if ":a02:ieee_802_3ck_index_to_fulltext:" in target["recovery_target_id"]
                else original["source_class"]
            )
            item = {
                "recovery_target_id": target["recovery_target_id"],
                "original_candidate_id": target["original_candidate_id"],
                "resolved_entry_candidate_id": provider_id,
                "authorized_er_ids": [target["authorized_er_id"]],
                "artifact_id": artifact["evidence_artifact_id"],
                "content_hash": artifact["content_hash"],
                "content_type": artifact["content_type"],
                "byte_size": artifact["byte_size"],
                "raw_artifact_path": artifact["raw_artifact_path"],
                "source_url": resolved_url,
                "resolved_url": artifact["resolved_url"],
                "source_owner": original["source_owner"],
                "source_class": resolved_source_class,
                "published_at": artifact["published_at"],
                "publication_date_status": "unknown" if artifact["published_at"] is None else "known",
                "accessed_at": artifact["accessed_at"],
                "normalized_document_id": None if normalized_document is None else normalized_document["document_id"],
                "normalized_representation_ids": normalized_representation_ids(provider_id, artifact["content_hash"]),
                "normalization_status": normalization_status,
                "normalization_error": normalization_error,
                "candidate_content_class": content_class,
                "document_identity_status": identity_status,
                "identity_match": identity_match,
                "target_evidence_match": target_evidence_match,
                "denominator_fields_present": denominator_fields,
                "eligible_for_assessment": normalization_status == "normalized" and identity_match and target_evidence_match in {"answers_er_directly", "answers_er_partially"},
                "pending_assessment": True,
            }
            inventory.append(item)
            if normalized_document is not None:
                normalized_associations.append({
                    "recovery_target_id": target["recovery_target_id"],
                    "evidence_artifact_id": item["artifact_id"],
                    "raw_content_hash": item["content_hash"],
                    "normalized_document_id": normalized_document["document_id"],
                    "normalized_document_hash": normalized_document["document_hash"],
                    "section_count": len(normalized_document["sections"]),
                    "denominator_fields_present": denominator_fields,
                    "assessment_started": False,
                    "cognition_update_started": False,
                })

    checkpoint = build_recovery_checkpoint(
        gate=gate,
        authorization=authorization,
        attempts=attempt_records,
        inventory=inventory,
        created_at=utc_now(),
        preflight_discovery_request_count=sum(
            row["discovery_request_count"] for row in RESOLVED_ENTRIES.values()
        ),
    )
    validate_recovery_checkpoint(checkpoint, gate=gate, authorization=authorization)
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl("target_execution_records.jsonl", target_records)
    write_jsonl("attempts.jsonl", attempt_records)
    write_jsonl("normalized_associations.jsonl", normalized_associations)
    inventory_payload = {
        "artifact_type": "wave_1b_recovery_evidence_inventory",
        "acquisition_wave": "wave_1b_recovery_pilot_acquisition",
        "items": inventory,
        "artifact_count": len(inventory),
        "unique_raw_hash_count": len({row["content_hash"] for row in inventory}),
        "eligible_for_assessment_count": sum(row["eligible_for_assessment"] for row in inventory),
        "assessment_started": False,
        "content_hash": content_sha256(inventory),
    }
    write_json("evidence_inventory.json", inventory_payload)
    write_json("acquisition_checkpoint.json", checkpoint)
    summary = "\n".join([
        "# AI PCB Wave 1b Recovery Pilot Acquisition",
        "",
        "This bundle consumes the one-time execution authorization for exactly seven frozen recovery targets. It contains acquisition and normalization facts only.",
        "",
        f"- Checkpoint: `{checkpoint['checkpoint_id']}`",
        f"- Formal attempts: {checkpoint['formal_attempt_count']}",
        f"- Acquired / blocked / failed: {checkpoint['acquired_count']} / {checkpoint['blocked_count']} / {checkpoint['failed_count']}",
        f"- Raw / unique hashes: {checkpoint['raw_artifact_count']} / {checkpoint['unique_raw_hash_count']}",
        f"- Normalized / failures: {checkpoint['normalized_artifact_count']} / {checkpoint['normalization_failure_count']}",
        "- `authorization_consumed = true`",
        "- `assessment_started = false`",
        "- `cognition_update_started = false`",
        "- No Wave 2, company mapping, Stage A2 or Stage B authorization was created.",
        "",
    ])
    _publish_bytes(OUT, "summary.md", summary.encode("utf-8"))
    print(json.dumps({
        "checkpoint_id": checkpoint["checkpoint_id"],
        "content_hash": checkpoint["content_hash"],
        "formal_attempt_count": checkpoint["formal_attempt_count"],
        "acquired": checkpoint["acquired_count"],
        "blocked": checkpoint["blocked_count"],
        "failed": checkpoint["failed_count"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
