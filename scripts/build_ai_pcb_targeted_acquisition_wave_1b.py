from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2_1.acquisition_contracts import AcquisitionContext
from stock_research.research_project_v2_1.acquisition_http import DirectHttpProvider
from stock_research.research_project_v2_1.discovery import source_candidate_id
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.normalize import normalize_artifact, write_normalized_document
from stock_research.research_project_v2_1.snapshot import _publish_bytes
from stock_research.research_project_v2_1.wave_1b import (
    AUTHORIZED_ER_IDS,
    INTERNAL_EXECUTION_ORDER,
    REQUIRED_DENOMINATOR_FIELDS,
    build_wave_1b_attempt_record,
    build_wave_1b_checkpoint,
    to_wave_1b_provider_candidate,
    validate_upstream_bindings,
    validate_wave_1b_candidate,
    validate_wave_1b_checkpoint,
    validate_wave_1b_gate,
)


LAYOUT = LayeredResearchLayout.default()
WAVE_DIR = LAYOUT.root / "acquisition/wave_1b"
GATE_PATH = LAYOUT.governance_dir / "ai_pcb_targeted_acquisition_wave_1b_gate_decision_v1.json"
VERSION = "research_version:ai_compute_pcb_industry_bottleneck:0.2.1"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def provenance(created_at: str) -> dict[str, Any]:
    return {
        "created_by": "Codex",
        "actor_type": "codex",
        "agent_run_id": "ai-pcb-targeted-acquisition-wave-1b-20260722",
        "created_at": created_at,
        "created_in_version": VERSION,
        "review_status": "unreviewed",
    }


def candidate(
    er_id: str,
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
    phase = 1 if er_id in INTERNAL_EXECUTION_ORDER[0] else 2
    provider_title = f"{title} [{er_id} Wave 1b association]"
    return {
        "candidate_id": source_candidate_id(url, provider_title),
        "wave_id": "targeted_evidence_acquisition_wave_1b",
        "internal_phase": phase,
        "authorized_er_ids": [er_id],
        "source_title": title,
        "provider_source_title": provider_title,
        "source_owner": owner,
        "source_class": source_class,
        "source_url": url,
        "expected_evidence_role": role,
        "expected_denominator_fields": list(REQUIRED_DENOMINATOR_FIELDS[er_id]),
        "eligibility_reason": reason,
        "known_limitations": limitations,
        "publication_date": None,
        "publication_date_status": "unknown",
        "candidate_status": "eligible",
        "rank": rank,
        "out_of_scope_note": "The immutable source may mention unapproved ERs, but Wave 1b formal coverage is restricted to the listed ER only.",
    }


def candidates() -> list[dict[str, Any]]:
    nist_tn_1520 = "https://nvlpubs.nist.gov/nistpubs/Legacy/TN/nbstechnicalnote1520.pdf"
    return [
        candidate(
            "PCB-ER-A04",
            "NIST Technical Note 1520: dielectric and conductor-loss characterization",
            "NIST",
            "national_metrology",
            nist_tn_1520,
            "measurement_method",
            "Provides public metrology treatment of dielectric/conductor loss and calibrated high-frequency measurements.",
            ["Older structures and frequency ranges require later scope assessment."],
            rank=1,
        ),
        candidate(
            "PCB-ER-A04",
            "IEEE 370 standard landing page",
            "IEEE Standards Association",
            "technical_standard",
            "https://standards.ieee.org/ieee/370/7337/",
            "deembedding_standard_context",
            "Provides the official identity and scope of an electrical-characterization and de-embedding standard.",
            ["A landing page may not expose the full normative method."],
            rank=2,
        ),
        candidate(
            "PCB-ER-A04",
            "Keysight de-embedding help: De-embedding",
            "Keysight Technologies",
            "instrument_method",
            "https://helpfiles.keysight.com/csg/N1930xB/Analyzing/De-embedding.htm",
            "fixture_and_deembedding_method",
            "Describes instrument-side de-embedding concepts, reference planes and fixture treatment.",
            ["Instrument documentation does not establish factory capability or industry practice."],
            rank=3,
        ),
        candidate(
            "PCB-ER-A04",
            "Anritsu de-embedding technical paper",
            "Anritsu",
            "instrument_method",
            "https://dl.cdn-anritsu.com/en-us/test-measurement/files/Technical-Notes/White-Paper/De-embedding_11410-00964A.pdf",
            "fixture_and_deembedding_method",
            "Provides a second instrument-vendor method candidate independent of OIF.",
            ["URL stability and applicability must be verified from the acquired document."],
            rank=4,
        ),
        candidate(
            "PCB-ER-B01",
            "IPC-TM-650 2.5.5.5 stripline permittivity and loss-tangent method",
            "IPC",
            "test_standard",
            "https://www.ipc.org/TOC/IPC-TM-650-2-5-5-5.pdf",
            "formal_test_method",
            "Defines a formal laminate permittivity/loss-tangent test method and specimen denominator.",
            ["Method scope must not be treated as directly comparable to other methods without assessment."],
            rank=1,
        ),
        candidate(
            "PCB-ER-B01",
            "RT/duroid 5870 and 5880 data sheet",
            "Rogers Corporation",
            "second_supplier_datasheet",
            "https://rogerscorp.com/-/media/project/rogerscorp/documents/advanced-electronics-solutions/english/data-sheets/rt-duroid-5870---5880-data-sheet.pdf",
            "supplier_parameter_declaration",
            "Provides a second supplier's Dk/Df declarations and stated test-method conditions.",
            ["Supplier data is not independent validation and cannot rank materials without matched methods."],
            rank=2,
        ),
        candidate(
            "PCB-ER-B01",
            "RO3000 laminate family data sheet",
            "Rogers Corporation",
            "second_supplier_datasheet",
            "https://rogerscorp.com/-/media/project/rogerscorp/documents/advanced-electronics-solutions/english/data-sheets/ro3000-laminate-data-sheet-ro3003-ro3006-ro3010-and-ro3035.pdf",
            "supplier_parameter_declaration",
            "Adds a second Rogers product-family declaration with explicit parameter conditions.",
            ["Same-supplier documents form a suspected common-origin cluster for independence counting."],
            rank=3,
        ),
        candidate(
            "PCB-ER-B01",
            "Panasonic MEGTRON 6 product information",
            "Panasonic Industry",
            "second_supplier_datasheet",
            "https://industrial.panasonic.com/ww/products/pt/megtron/megtron6",
            "supplier_parameter_declaration",
            "Provides a non-Isola, non-Rogers supplier candidate for method and parameter declarations.",
            ["Product-page values may omit complete sample and uncertainty metadata."],
            rank=4,
        ),
        candidate(
            "PCB-ER-B01",
            "NIST Technical Note 1520: dielectric and conductor-loss characterization",
            "NIST",
            "national_metrology",
            nist_tn_1520,
            "independent_measurement_method",
            "Provides an independent metrology source for dielectric-property measurement limitations.",
            ["The method may not match supplier datasheet methods or modern product constructions."],
            rank=5,
        ),
        candidate(
            "PCB-ER-B02",
            "Crossref registry query for the existing copper-surface-roughness paper",
            "Crossref",
            "publication_registry",
            "https://api.crossref.org/works?query.title=Signal%20transmission%20loss%20due%20to%20copper%20surface%20roughness%20in%20high-frequency%20region&rows=5",
            "publication_provenance",
            "Attempts to verify a formal title, publisher, date and stable identifier without relying on the repository filename.",
            ["Registry search results require later title/author matching and are not experiment evidence."],
            rank=1,
        ),
        candidate(
            "PCB-ER-B02",
            "Characterization of electrodeposited copper foil surface roughness for accurate conductor power loss modeling",
            "University of South Carolina Scholar Commons",
            "academic_research",
            "https://scholarcommons.sc.edu/cgi/viewcontent.cgi?article=3964&context=etd",
            "independent_measurement",
            "Provides an academic roughness measurement/modeling candidate independent of a laminate supplier.",
            ["Thesis geometry and modeling scope may not match production high-speed boards."],
            rank=2,
        ),
        candidate(
            "PCB-ER-B02",
            "Copper foil roughness and conductor loss",
            "Signal Integrity Journal",
            "professional_engineering",
            "https://www.signalintegrityjournal.com/articles/2109-copper-foil-roughness-and-conductor-loss",
            "engineering_context",
            "Provides an engineering source for roughness metrics, modeling and comparison boundaries.",
            ["Professional technical article is not an independent replication by itself."],
            rank=3,
        ),
        candidate(
            "PCB-ER-B02",
            "NIST Technical Note 1520: dielectric and conductor-loss characterization",
            "NIST",
            "national_metrology",
            nist_tn_1520,
            "loss_separation_method",
            "Provides an independent method context for separating conductor and dielectric loss.",
            ["Does not directly replicate a modern copper-profile experiment."],
            rank=4,
        ),
        candidate(
            "PCB-ER-A02",
            "800G Ethernet Technology Consortium specification version 1.0",
            "Ethernet Technology Consortium",
            "technical_standard",
            "https://ethernettechnologyconsortium.org/wp-content/uploads/2020/04/800G-ETC-Specification_r1.0.pdf",
            "independent_channel_definition",
            "Provides a non-OIF system/specification context with explicit rates, lanes and link assumptions.",
            ["System specification may not expose a complete PCB/connector measurement denominator."],
            rank=1,
        ),
        candidate(
            "PCB-ER-A02",
            "PCI Express 6.0 specification overview",
            "PCI-SIG",
            "technical_standard_context",
            "https://pcisig.com/pci-express-6.0-specification",
            "independent_rate_and_modulation_context",
            "Provides a distinct standards ecosystem for rate, modulation and compliance context.",
            ["Public overview may not include the normative channel-loss tables."],
            rank=2,
        ),
        candidate(
            "PCB-ER-A02",
            "IEEE 802.3ck public task-force material index",
            "IEEE 802.3",
            "standards_working_group",
            "https://www.ieee802.org/3/ck/public/index.html",
            "independent_channel_measurement_discovery",
            "Provides the official public record for 100/200/400 Gb/s electrical-interface engineering material.",
            ["Index content is contextual unless a specific measurement presentation is acquired."],
            rank=3,
        ),
        candidate(
            "PCB-ER-A02",
            "IEEE 802.3ck May 2019 channel presentation",
            "IEEE 802.3",
            "engineering_measurement",
            "https://www.ieee802.org/3/ck/public/19_05/heck_mellitz_3ck_01_0519.pdf",
            "independent_channel_measurement",
            "Provides a candidate engineering presentation with channel frequency/loss conditions outside OIF.",
            ["Title, setup and denominator must be verified from the acquired PDF before assessment."],
            rank=4,
        ),
    ]


_DENOMINATOR_TERMS = {
    "frequency_range": ("ghz", "mhz", "frequency range"),
    "comparison_frequency": ("comparison frequency", "at 10 ghz", "at 20 ghz", "frequency"),
    "nyquist_frequency": ("nyquist",),
    "channel_length": ("channel length", " mm", " inch", " meter"),
    "unit": ("db/in", "db/cm", " db", "decibel"),
    "differential_or_single_ended": ("differential", "single-ended", "single ended"),
    "reference_plane": ("reference plane", "test point"),
    "fixture_configuration": ("fixture", "launch", "probe"),
    "deembedding_method": ("de-embedding", "deembedding", "de embed"),
    "coupon_or_actual_channel": ("coupon", "actual channel", "production channel"),
    "temperature": ("temperature", "°c", "deg c"),
    "environment": ("humidity", "environment"),
    "uncertainty_or_repeatability": ("uncertainty", "repeatability", "reproducibility"),
    "test_method": ("test method", "ipc-tm", "clamped stripline", "split post resonator"),
    "frequency": ("ghz", "mhz", "frequency"),
    "humidity": ("humidity", "%rh"),
    "material_direction": ("x-y", "z-axis", "direction", "anisotrop"),
    "sample_geometry": ("specimen", "sample", "stripline", "microstrip"),
    "sample_thickness": ("thickness", "mil", " mm"),
    "resin_content": ("resin content",),
    "glass_style": ("glass style", "glass cloth", "construction"),
    "copper_condition": ("copper", "cladding", "foil"),
    "nominal_typical_or_guaranteed": ("nominal", "typical", "guaranteed"),
    "design_dk_or_test_dk": ("design dk", "process dk", "dielectric constant", "permittivity"),
    "measurement_uncertainty": ("uncertainty", "tolerance"),
    "surface_profile_metric": ("rz", "ra", "rq", "rms", "roughness"),
    "treatment_type": ("rtf", "vlp", "treatment", "reverse treated"),
    "trace_geometry": ("line width", "trace width", "microstrip", "stripline"),
    "copper_thickness": ("copper thickness", "oz copper"),
    "dielectric_thickness": ("dielectric thickness", "substrate thickness"),
    "material_system": ("dielectric", "laminate", "fr-4", "resin"),
    "measurement_or_simulation_method": ("vna", "simulation", "measured", "s21", "sdd21"),
    "temperature_environment": ("temperature", "humidity", "environment"),
    "data_rate": ("gb/s", "gbps", "data rate"),
    "baud_rate": ("gbaud", "gbd", "baud"),
    "modulation": ("pam4", "nrz", "modulation"),
    "topology": ("topology", "point-to-point", "point to point", "link"),
    "pcb_length": ("pcb length", "board trace", "host pcb"),
    "connector_count": ("connector",),
    "cable_length": ("cable length", "cable"),
    "retimer_presence": ("retimer", "retimed"),
    "equalization_assumption": ("equalization", "ffe", "dfe", "ctle"),
    "insertion_loss": ("insertion loss", "s21", "sdd21"),
    "return_loss": ("return loss", "s11", "sdd11"),
    "crosstalk": ("crosstalk", "next", "fext"),
    "ber_or_compliance_metric": ("ber", "bit error", "compliance", "com"),
}


def observed_denominator_fields(document: dict[str, Any], er_id: str) -> list[str]:
    text = "\n".join(section.get("text", "") for section in document.get("sections", [])).lower()
    observed = []
    for field in REQUIRED_DENOMINATOR_FIELDS[er_id]:
        terms = _DENOMINATOR_TERMS.get(field, ())
        if any(term in text for term in terms):
            observed.append(field)
    return observed


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
    return _publish_bytes(WAVE_DIR, name, b"".join(canonical_bytes(row) + b"\n" for row in rows))


def write_json(name: str, payload: dict[str, Any]) -> Path:
    return _publish_bytes(WAVE_DIR, name, canonical_bytes(payload))


def render_summary(checkpoint: dict[str, Any]) -> str:
    lines = [
        "# AI PCB Targeted Evidence Acquisition Wave 1b",
        "",
        "This checkpoint records acquisition and normalization only. It contains no Evidence Assessment, cognition update, bottleneck judgment, value migration or company conclusion.",
        "",
        f"- Checkpoint: `{checkpoint['checkpoint_id']}`",
        f"- Authorized ERs: {', '.join(checkpoint['authorized_er_ids'])}",
        f"- Candidates / formal attempts: {checkpoint['candidate_count']} / {checkpoint['formal_attempt_count']}",
        f"- Acquired / blocked / failed: {checkpoint['acquired_count']} / {checkpoint['blocked_count']} / {checkpoint['failed_count']}",
        f"- Raw / unique hashes: {checkpoint['raw_artifact_count']} / {checkpoint['unique_raw_hash_count']}",
        f"- Normalized / failures: {checkpoint['normalized_artifact_count']} / {checkpoint['normalization_failure_count']}",
        "",
        "## Per-ER acquisition state",
        "",
    ]
    for er_id in checkpoint["authorized_er_ids"]:
        denominator = checkpoint["per_er_denominator_completeness"][er_id]
        lines.append(
            f"- `{er_id}`: attempts={checkpoint['per_er_attempt_coverage'][er_id]}, acquired={checkpoint['per_er_acquired_coverage'][er_id]}, source_classes={checkpoint['per_er_source_class_coverage'][er_id]}, denominator_ratio={denominator['completeness_ratio']}, terminal={checkpoint['per_er_terminal_state'][er_id]}"
        )
    lines.extend([
        "",
        "## Governance",
        "",
        "- `assessment_started = false`",
        "- `cognition_update_started = false`",
        "- `wave_2_authorized = false`",
        "- `company_mapping_authorized = false`",
        "- `stage_a2_authorized = false`",
        "- `stage_b_authorized = false`",
        "- Acquired evidence coverage is not evidence sufficiency.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    gate = validate_wave_1b_gate(json.loads(GATE_PATH.read_text(encoding="utf-8")))
    validate_upstream_bindings(gate, layout=LAYOUT)
    started_at = utc_now()
    prov = provenance(started_at)
    provider = DirectHttpProvider(headers={"User-Agent": "StockResearchEvidenceAcquisition/1.0"})
    candidate_rows = [validate_wave_1b_candidate(row, gate) for row in candidates()]
    attempt_rows: list[dict[str, Any]] = []
    inventory: list[dict[str, Any]] = []
    normalized_associations: list[dict[str, Any]] = []
    phase_1_ready = False
    for phase in (1, 2):
        if phase == 2 and not phase_1_ready:
            break
        for row in [item for item in candidate_rows if item["internal_phase"] == phase]:
            provider_candidate = to_wave_1b_provider_candidate(
                row, discovered_at=started_at, provenance=prov
            )
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
                timeout_seconds=25.0,
                max_redirects=5,
                max_bytes=30 * 1024 * 1024,
                max_retries=0,
            )
            normalized_document = None
            normalization_status = "not_applicable"
            normalization_error = None
            denominator_fields: list[str] = []
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
                    denominator_fields = observed_denominator_fields(
                        normalized_document, row["authorized_er_ids"][0]
                    )
                except Exception as exc:
                    normalization_status = "failed"
                    normalization_error = f"{type(exc).__name__}: {exc}"
            attempt_rows.append(
                build_wave_1b_attempt_record(
                    candidate=row,
                    provider_attempt=result.attempt,
                    artifact=result.artifact,
                    normalization_status=normalization_status,
                    normalized_document_id=(
                        None if normalized_document is None else normalized_document["document_id"]
                    ),
                    normalization_error=normalization_error,
                )
            )
            if result.artifact is not None:
                item = {
                    "artifact_id": result.artifact["evidence_artifact_id"],
                    "legacy_artifact_id": None if normalized_document is None else normalized_document["artifact_id"],
                    "candidate_id": row["candidate_id"],
                    "authorized_er_ids": list(row["authorized_er_ids"]),
                    "source_owner": row["source_owner"],
                    "source_class": row["source_class"],
                    "expected_evidence_role": row["expected_evidence_role"],
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
                    "denominator_fields_present": denominator_fields,
                    "denominator_detection_note": "Conservative term-presence scan for acquisition triage only; does not establish denominator validity or Evidence Assessment sufficiency.",
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
                        "denominator_fields_present": denominator_fields,
                        "assessment_started": False,
                        "cognition_update_started": False,
                    })
        if phase == 1:
            a04_items = [
                item for item in inventory
                if item["authorized_er_ids"] == ["PCB-ER-A04"]
                and item["normalization_status"] == "normalized"
            ]
            a04_observed = {
                field for item in a04_items for field in item["denominator_fields_present"]
            }
            phase_1_ready = bool(a04_items) and "frequency_range" in a04_observed and bool(
                {"reference_plane", "fixture_configuration", "deembedding_method"}
                & a04_observed
            )
    acquired_by_owner: dict[tuple[str, str], list[str]] = {}
    for item in inventory:
        er_id = item["authorized_er_ids"][0]
        acquired_by_owner.setdefault((er_id, item["source_owner"]), []).append(item["artifact_id"])
    suspected_common_origins = sorted(
        sorted(ids)
        for (er_id, owner), ids in acquired_by_owner.items()
        if len(ids) > 1 and owner in {"Rogers Corporation", "IEEE 802.3"}
    )
    checkpoint = build_wave_1b_checkpoint(
        gate=gate,
        candidates=candidate_rows,
        attempts=attempt_rows,
        inventory=inventory,
        created_at=utc_now(),
        preflight_attempt_ids=[],
        suspected_common_origin_groups=suspected_common_origins,
        out_of_scope_candidate_count=0,
        security_violations=[],
        scope_violations=[],
    )
    validate_wave_1b_checkpoint(checkpoint, gate=gate)
    WAVE_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl("candidates.jsonl", candidate_rows)
    write_jsonl("attempts.jsonl", attempt_rows)
    write_jsonl("normalized_associations.jsonl", normalized_associations)
    write_json("evidence_inventory.json", {
        "artifact_type": "targeted_acquisition_evidence_inventory",
        "acquisition_wave": "targeted_evidence_acquisition_wave_1b",
        "authorized_er_ids": list(AUTHORIZED_ER_IDS),
        "items": inventory,
        "artifact_count": len(inventory),
        "unique_raw_hash_count": checkpoint["unique_raw_hash_count"],
        "provisional_evidence_chain_count": checkpoint["provisional_evidence_chain_count"],
        "exact_duplicate_groups": checkpoint["exact_duplicate_groups"],
        "suspected_common_origin_groups": checkpoint["suspected_common_origin_groups"],
        "content_hash": content_sha256(inventory),
    })
    write_json("acquisition_checkpoint.json", checkpoint)
    _publish_bytes(WAVE_DIR, "summary.md", render_summary(checkpoint).encode("utf-8"))
    print(json.dumps({
        "checkpoint_id": checkpoint["checkpoint_id"],
        "content_hash": checkpoint["content_hash"],
        "formal_attempts": checkpoint["formal_attempt_count"],
        "acquired": checkpoint["acquired_count"],
        "blocked": checkpoint["blocked_count"],
        "failed": checkpoint["failed_count"],
        "phase_1_ready": phase_1_ready,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
