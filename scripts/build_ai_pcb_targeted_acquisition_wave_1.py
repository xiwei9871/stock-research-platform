from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2_1.acquisition_contracts import AcquisitionContext
from stock_research.research_project_v2_1.acquisition_http import DirectHttpProvider
from stock_research.research_project_v2_1.discovery import source_candidate_id
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.normalize import normalize_artifact, write_normalized_document
from stock_research.research_project_v2_1.snapshot import _publish_bytes
from stock_research.research_project_v2_1.wave_1 import (
    build_wave_attempt_record,
    build_wave_checkpoint,
    to_provider_candidate,
    validate_gate_decision,
    validate_wave_candidate,
    validate_wave_checkpoint,
)


ROOT = Path(__file__).resolve().parents[1]
LAYOUT = LayeredResearchLayout.default()
WAVE_DIR = LAYOUT.root / "acquisition/wave_1"
GATE_PATH = LAYOUT.governance_dir / "ai_pcb_targeted_acquisition_gate_decision_v1.json"
VERSION = "research_version:ai_compute_pcb_industry_bottleneck:0.2.1"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def provenance(created_at: str) -> dict[str, Any]:
    return {
        "created_by": "Codex",
        "actor_type": "codex",
        "agent_run_id": "ai-pcb-targeted-acquisition-wave-1-20260721",
        "created_at": created_at,
        "created_in_version": VERSION,
        "review_status": "unreviewed",
    }


def candidate(
    er_id: str,
    phase: int,
    title: str,
    owner: str,
    source_class: str,
    url: str,
    role: str,
    reason: str,
    limitations: list[str],
    *,
    rank: int,
) -> dict[str, Any]:
    provider_title = f"{title} [{er_id} association]"
    candidate_id = source_candidate_id(url, provider_title)
    return {
        "candidate_id": candidate_id,
        "authorized_er_ids": [er_id],
        "source_title": title,
        "provider_source_title": provider_title,
        "source_owner": owner,
        "source_class": source_class,
        "source_url": url,
        "expected_evidence_role": role,
        "eligibility_reason": reason,
        "known_limitations": limitations,
        "publication_date": None,
        "publication_date_status": "unknown",
        "candidate_status": "eligible",
        "internal_phase": phase,
        "rank": rank,
        "out_of_scope_note": "The full immutable source may mention other topics, but formal Wave 1 coverage is restricted to the listed authorized ER only.",
    }


def candidates() -> list[dict[str, Any]]:
    cei = "https://www.oiforum.com/wp-content/uploads/OIF-CEI-05.3.pdf"
    cei448 = "https://www.oiforum.com/wp-content/uploads/OIF-FD-CEI-448G-01.0.pdf"
    nist = "https://doi.org/10.6028/NIST.TN.1520"
    return [
        candidate("PCB-ER-A01", 1, "OIF Common Electrical I/O CEI 5.3", "OIF", "technical_standard", cei, "definition", "Defines named electrical interface classes, endpoints, reaches and operating conditions.", ["Does not establish PCB manufacturing capability or industry capacity."], rank=1),
        candidate("PCB-ER-A01", 1, "OIF Next Generation CEI-448G Framework", "OIF", "technical_standard", cei448, "boundary_context", "Provides an official next-generation framework for channel classes and reach assumptions.", ["Framework status and future-oriented scope must be separated from a released implementation agreement."], rank=2),
        candidate("PCB-ER-A04", 1, "NIST Technical Note 1520: Dielectric and conductor-loss characterization", "NIST", "engineering_measurement", nist, "measurement_method", "Provides public metrology definitions and measurement treatment for dielectric and conductor loss.", ["Older publication; applicability to modern interface generations requires later assessment."], rank=1),
        candidate("PCB-ER-A04", 1, "OIF Common Electrical I/O CEI 5.3", "OIF", "technical_standard", cei, "normative_measurement_context", "Contains normative channel-loss and compliance definitions tied to interface classes.", ["Normative limits do not by themselves establish production-channel performance."], rank=2),
        candidate("PCB-ER-B01", 1, "Isola I-Tera MT40 Dk/Df Tables", "Isola", "material_datasheet", "https://www.isola-group.com/wp-content/uploads/data-sheets/i-tera-mt40__Dk_Df_Tables.pdf?t=710359572", "parameter_declaration", "Records supplier-declared Dk/Df values with stated test conditions and constructions.", ["Supplier declaration is not independent verification and does not establish whole-channel performance."], rank=1),
        candidate("PCB-ER-B01", 1, "Making Sense of Laminate Dielectric Properties", "Isola", "supplier_technical_paper", "https://www.isola-group.com/wp-content/uploads/Making-Sense-of-Laminate-Dielectric-Properties.pdf", "method_context", "Explains why dielectric-property values depend on method and conditions.", ["Supplier-authored interpretation requires independent corroboration."], rank=2),
        candidate("PCB-ER-B01", 1, "RT/duroid 5880 laminate product page", "Rogers Corporation", "material_datasheet", "https://www.rogerscorp.com/advanced-electronics-solutions/rt-duroid-laminates/rt-duroid-5880-laminates", "parameter_declaration", "Provides a second supplier's declared dielectric parameters and test-method context.", ["Product-specific marketing page cannot establish cross-material comparability or board performance."], rank=3),
        candidate("PCB-ER-A02", 2, "OIF Common Electrical I/O CEI 5.3", "OIF", "technical_standard", cei, "quantitative_comparison", "Provides rate- and reach-specific channel definitions with comparable loss constraints.", ["Multiple interface classes must not be mixed without matching denominator and topology."], rank=1),
        candidate("PCB-ER-A02", 2, "OIF Next Generation CEI-448G Framework", "OIF", "technical_standard", cei448, "generation_boundary", "Provides next-generation rate and channel-framework context for comparison.", ["Framework assumptions are not measured production results."], rank=2),
        candidate("PCB-ER-A03", 2, "OIF 112G Retimed Transmitter Linear Receiver Agreement", "OIF", "technical_standard", "https://www.oiforum.com/wp-content/uploads/OIF-EEI-112G-RTLR-01.0.pdf", "alternative_architecture", "Provides an official retimed/linear-receiver architecture that can bound simple rate-to-material narratives.", ["Optical-module electrical-interface scope is a boundary case, not a universal PCB architecture."], rank=1),
        candidate("PCB-ER-A03", 2, "OIF Next Generation CEI-448G Framework", "OIF", "technical_standard", cei448, "counter_and_boundary", "Documents alternative reach classes and architectural assumptions at higher rates.", ["Future framework does not prove deployment prevalence."], rank=2),
        candidate("PCB-ER-A03", 2, "NIST Technical Note 1520: Dielectric and conductor-loss characterization", "NIST", "engineering_measurement", nist, "alternative_explanation", "Separates dielectric and conductor loss so a measured change is not automatically attributed to one material variable.", ["Older test structures may not match current high-speed product geometry."], rank=3),
        candidate("PCB-ER-B02", 3, "PCB Material Selection for High-speed Digital Designs", "Isola", "supplier_technical_paper", "https://www.isola-group.com/wp-content/uploads/PCB-Material-Selection-for-High-speed-Digital-Designs-1.pdf", "variable_context", "Provides supplier technical discussion of conductor profile and high-speed material selection.", ["Supplier-authored material guidance cannot establish an industry-wide effect alone."], rank=1),
        candidate("PCB-ER-B02", 3, "Signal transmission loss due to copper surface roughness in high-frequency region", "SMTnet technical library", "engineering_research", "https://www.smtnet.com/library/files/upload/Copper-Surface-Roughness-in-High-Frequency-Region.pdf", "engineering_measurement", "Provides an engineering paper with explicit high-frequency copper-surface-roughness measurements.", ["Repository hosting is not the original publisher; authorship and method must be checked during assessment."], rank=2),
        candidate("PCB-ER-B02", 3, "Characterization of electrodeposited copper foil surface roughness for accurate conductor power loss modeling", "University of South Carolina Scholar Commons", "academic_research", "https://scholarcommons.sc.edu/cgi/viewcontent.cgi?article=3964&context=etd", "independent_measurement", "Provides an academic measurement and modeling study independent of a laminate supplier.", ["Thesis scope and test structures may not generalize to current production boards."], rank=3),
        candidate("PCB-ER-B02", 3, "NIST Technical Note 1520: Dielectric and conductor-loss characterization", "NIST", "engineering_measurement", nist, "loss_separation_context", "Provides public metrology context for separating conductor and dielectric contributions.", ["Does not alone quantify modern copper-foil treatment effects."], rank=4),
    ]


def find_legacy_artifact(candidate_id: str, content_hash: str) -> dict[str, Any]:
    matches = []
    for path in LAYOUT.evidence_metadata_dir.glob("*.json"):
        wrapper = json.loads(path.read_text(encoding="utf-8"))
        item = wrapper.get("evidence_artifact", {})
        if item.get("candidate_id") == candidate_id and item.get("content_sha256") == content_hash:
            matches.append(item)
    if len(matches) != 1:
        raise RuntimeError(f"Expected one legacy artifact for {candidate_id}, found {len(matches)}")
    return matches[0]


def write_jsonl(name: str, rows: list[dict[str, Any]]) -> Path:
    data = b"".join(canonical_bytes(row) + b"\n" for row in rows)
    return _publish_bytes(WAVE_DIR, name, data)


def write_json(name: str, payload: dict[str, Any]) -> Path:
    return _publish_bytes(WAVE_DIR, name, canonical_bytes(payload))


def render_summary(checkpoint: dict[str, Any]) -> str:
    lines = [
        "# AI PCB Targeted Evidence Acquisition Wave 1",
        "",
        "This is an acquisition and normalization checkpoint only. It does not contain Evidence Assessment or ER sufficiency conclusions.",
        "",
        f"- Checkpoint: `{checkpoint['checkpoint_id']}`",
        f"- Authorized ERs: {', '.join(checkpoint['authorized_er_ids'])}",
        f"- Candidates / attempts: {checkpoint['candidate_count']} / {checkpoint['attempt_count']}",
        f"- Acquired / blocked / failed: {checkpoint['acquired_count']} / {checkpoint['blocked_count']} / {checkpoint['failed_count']}",
        f"- Unique raw hashes: {checkpoint['unique_raw_hash_count']}",
        f"- Normalized artifacts / failures: {checkpoint['normalized_artifact_count']} / {checkpoint['normalization_failure_count']}",
        f"- Engineering preflight attempts excluded from formal coverage: {checkpoint['engineering_preflight_attempt_count']}",
        "",
        "## Per-ER acquisition coverage",
        "",
    ]
    for er_id in checkpoint["authorized_er_ids"]:
        lines.append(
            f"- `{er_id}`: attempts={checkpoint['per_er_attempt_coverage'][er_id]}, acquired={checkpoint['per_er_acquired_coverage'][er_id]}, terminal={checkpoint['per_er_terminal_state'][er_id]}"
        )
    lines.extend([
        "",
        "## Governance",
        "",
        "- `assessment_started = false`",
        "- `company_mapping_authorized = false`",
        "- `stage_a2_authorized = false`",
        "- `stage_b_authorized = false`",
        "- Acquired evidence coverage is not evidence sufficiency.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    gate = validate_gate_decision(json.loads(GATE_PATH.read_text(encoding="utf-8")))
    started_at = utc_now()
    prov = provenance(started_at)
    provider = DirectHttpProvider(headers={"User-Agent": "StockResearchEvidenceAcquisition/1.0"})
    candidate_rows = [validate_wave_candidate(item, gate) for item in candidates()]
    attempt_rows: list[dict[str, Any]] = []
    inventory: list[dict[str, Any]] = []
    normalized_associations: list[dict[str, Any]] = []
    for phase in (1, 2, 3):
        for row in [item for item in candidate_rows if item["internal_phase"] == phase]:
            provider_candidate = to_provider_candidate(row, discovered_at=started_at, provenance=prov)
            context = AcquisitionContext(
                project_id=gate["project_id"],
                research_version_context=VERSION,
                requirement_id=row["authorized_er_ids"][0],
                candidate_id=row["candidate_id"],
                provenance=prov,
            )
            result = provider.acquire(
                provider_candidate,
                context=context,
                layout=LAYOUT,
                proxy_mode="direct",
                timeout_seconds=30.0,
                max_redirects=5,
                max_bytes=25 * 1024 * 1024,
                max_retries=1,
            )
            normalized_document = None
            normalization_status = "not_applicable"
            normalization_error = None
            if result.artifact is not None:
                try:
                    legacy = find_legacy_artifact(row["candidate_id"], result.artifact["content_hash"])
                    normalized_document = normalize_artifact(
                        legacy,
                        layout=LAYOUT,
                        parsed_at=result.attempt["completed_at"],
                        provenance=prov,
                    )
                    write_normalized_document(normalized_document, layout=LAYOUT)
                    normalization_status = "normalized"
                except Exception as exc:  # raw acquisition remains authoritative
                    normalization_status = "failed"
                    normalization_error = f"{type(exc).__name__}: {exc}"
            wave_attempt = build_wave_attempt_record(
                candidate=row,
                provider_attempt=result.attempt,
                artifact=result.artifact,
                normalization_status=normalization_status,
                normalized_document_id=None if normalized_document is None else normalized_document["document_id"],
                normalization_error=normalization_error,
            )
            attempt_rows.append(wave_attempt)
            if result.artifact is not None:
                item = {
                    "artifact_id": result.artifact["evidence_artifact_id"],
                    "legacy_artifact_id": None if normalized_document is None else normalized_document["artifact_id"],
                    "candidate_id": row["candidate_id"],
                    "authorized_er_ids": list(row["authorized_er_ids"]),
                    "content_hash": result.artifact["content_hash"],
                    "content_type": result.artifact["content_type"],
                    "byte_size": result.artifact["byte_size"],
                    "raw_artifact_path": result.artifact["raw_artifact_path"],
                    "publication_date_status": row["publication_date_status"],
                    "published_at": result.artifact["published_at"],
                    "accessed_at": result.artifact["accessed_at"],
                    "normalized_document_id": None if normalized_document is None else normalized_document["document_id"],
                    "normalization_status": normalization_status,
                    "normalization_error": normalization_error,
                    "pending_assessment": True,
                    "non_derivable_conclusions": row["known_limitations"],
                }
                inventory.append(item)
                if normalized_document is not None:
                    normalized_associations.append({
                        "candidate_id": row["candidate_id"],
                        "authorized_er_ids": list(row["authorized_er_ids"]),
                        "evidence_artifact_id": result.artifact["evidence_artifact_id"],
                        "raw_content_hash": result.artifact["content_hash"],
                        "normalized_document_id": normalized_document["document_id"],
                        "normalized_document_hash": normalized_document["document_hash"],
                        "section_count": len(normalized_document["sections"]),
                        "assessment_started": False,
                    })
    isola_b01_artifacts = [
        item["artifact_id"]
        for item in inventory
        if item["authorized_er_ids"] == ["PCB-ER-B01"]
        and next(row for row in candidate_rows if row["candidate_id"] == item["candidate_id"])["source_owner"] == "Isola"
    ]
    suspected_common_origin_groups = [isola_b01_artifacts] if len(isola_b01_artifacts) > 1 else []
    checkpoint = build_wave_checkpoint(
        gate=gate,
        candidates=candidate_rows,
        attempts=attempt_rows,
        inventory=inventory,
        created_at=utc_now(),
        suspected_common_origin_groups=suspected_common_origin_groups,
        engineering_preflight_attempt_ids=[],
    )
    validate_wave_checkpoint(checkpoint, gate=gate)
    write_jsonl("candidates.jsonl", candidate_rows)
    write_jsonl("attempts.jsonl", attempt_rows)
    write_jsonl("normalized_associations.jsonl", normalized_associations)
    write_json("evidence_inventory.json", {
        "artifact_type": "targeted_acquisition_evidence_inventory",
        "acquisition_wave": "targeted_evidence_acquisition_wave_1",
        "authorized_er_ids": checkpoint["authorized_er_ids"],
        "items": inventory,
        "artifact_count": len(inventory),
        "unique_raw_hash_count": checkpoint["unique_raw_hash_count"],
        "evidence_chain_count": checkpoint["evidence_chain_count"],
        "duplicate_groups": checkpoint["duplicate_groups"],
        "suspected_common_origin_groups": checkpoint["suspected_common_origin_groups"],
        "content_hash": content_sha256(inventory),
    })
    write_json("acquisition_checkpoint.json", checkpoint)
    _publish_bytes(WAVE_DIR, "summary.md", render_summary(checkpoint).encode("utf-8"))
    print(json.dumps({"checkpoint_id": checkpoint["checkpoint_id"], "content_hash": checkpoint["content_hash"], "attempts": len(attempt_rows), "acquired": checkpoint["acquired_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
