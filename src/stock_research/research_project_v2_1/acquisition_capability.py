from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error
from stock_research.research_project_v2_1.layout import LayeredResearchLayout


CAPABILITY_ROLE = "acquisition_capability_validation_only"
CAPABILITY_DIRNAME = "acquisition/capability_hardening_v1"
AUTHORIZED_DISCOVERY_ERS = ("PCB-ER-A04", "PCB-ER-B01", "PCB-ER-B02", "PCB-ER-A02")
CONTENT_CLASSES = {
    "full_text_pdf", "full_text_html", "official_technical_document",
    "formal_standard_text", "standard_landing_page", "working_group_index",
    "overview", "abstract_only", "metadata_record", "dataset_or_measurement_record",
    "datasheet", "marketing_page", "purchase_page", "broken_url", "unknown",
}
ROOT_CAUSES = {
    "success_full_text", "success_partial_text", "landing_page_only", "overview_only",
    "index_only", "abstract_only", "metadata_only", "paywall_or_purchase_page",
    "broken_or_moved_url", "http_403", "http_404", "timeout_or_transient_network",
    "security_policy_blocked", "encrypted_or_unparseable", "identity_unresolved",
    "source_type_mismatch", "denominator_insufficient", "duplicate_or_common_origin",
    "public_fulltext_unavailable", "unknown",
}
EVIDENCE_MATCHES = {
    "answers_er_directly", "answers_er_partially", "context_only",
    "source_discovery_only", "does_not_answer_er",
}


def _invalid(message: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        message,
        code="RESEARCH_PROJECT_V2_1_ACQUISITION_CAPABILITY_INVALID",
        details=details,
    )


def _document_text(document: dict[str, Any] | None) -> str:
    if not document:
        return ""
    return "\n".join(
        str(section.get("text") or "") for section in document.get("sections") or []
    )


def classify_root_cause(
    candidate: dict[str, Any], attempt: dict[str, Any],
    *, content_class: str | None = None, evidence_match: str | None = None,
) -> dict[str, Any]:
    status = attempt.get("status")
    failure = attempt.get("failure_class") or attempt.get("failure_code")
    http = attempt.get("http_status")
    normalization = attempt.get("normalization_status")
    if failure == "security_policy_blocked" or status == "blocked":
        root = "security_policy_blocked"
    elif http == 404:
        root = "http_404"
    elif http == 403:
        root = "http_403"
    elif failure in {"connection_timeout", "connection_refused", "rate_limited"}:
        root = "timeout_or_transient_network"
    elif normalization == "failed":
        error = str(attempt.get("normalization_error") or "").lower()
        root = "encrypted_or_unparseable" if "encrypt" in error or "parse" in error else "encrypted_or_unparseable"
    elif status != "acquired":
        root = "broken_or_moved_url" if failure == "http_error" else "unknown"
    elif content_class == "standard_landing_page":
        root = "landing_page_only"
    elif content_class == "working_group_index":
        root = "index_only"
    elif content_class == "overview":
        root = "overview_only"
    elif content_class == "abstract_only":
        root = "abstract_only"
    elif content_class == "metadata_record":
        root = "metadata_only"
    elif content_class in {"purchase_page", "marketing_page"}:
        root = "paywall_or_purchase_page" if content_class == "purchase_page" else "source_type_mismatch"
    elif evidence_match == "does_not_answer_er" or evidence_match == "context_only":
        root = "source_type_mismatch"
    elif evidence_match == "answers_er_partially":
        root = "denominator_insufficient"
    elif status == "acquired":
        root = "success_full_text"
    else:
        root = "unknown"
    return {
        "root_cause_class": root,
        "retry_value": (
            "bounded_retry_once"
            if root == "timeout_or_transient_network"
            else "no_same_url_retry"
        ),
    }


def classify_candidate_content(
    candidate: dict[str, Any],
    attempt: dict[str, Any],
    normalized_document: dict[str, Any] | None,
) -> dict[str, Any]:
    if attempt.get("http_status") == 404:
        return {"candidate_content_class": "broken_url", "classification_signals": ["http_status:404"]}
    if attempt.get("status") != "acquired" or normalized_document is None:
        return {"candidate_content_class": "unknown", "classification_signals": [f"attempt_status:{attempt.get('status')}"]}
    title = " ".join(
        str(value or "")
        for value in (candidate.get("source_title"), normalized_document.get("title"))
    ).lower()
    text = _document_text(normalized_document)
    lowered = text.lower()
    signals: list[str] = []
    media = normalized_document.get("media_type") or attempt.get("content_type")
    if "purchase" in lowered or "buy this standard" in lowered:
        signals.append("purchase_marker")
    if "landing page" in title or (
        re.search(r"\bstandard\b", title)
        and any(term in lowered for term in ("purchase this standard", "buy this standard", "standard overview"))
    ):
        return {"candidate_content_class": "standard_landing_page", "classification_signals": signals + ["standard_metadata_without_normative_sections"]}
    if "overview" in title or re.search(r"\boverview\b", lowered[:3000]):
        return {"candidate_content_class": "overview", "classification_signals": signals + ["overview_marker"]}
    if "index" in title or (
        "public area" in title and any(term in lowered for term in ("meeting materials", "presentations", "documents"))
    ):
        return {"candidate_content_class": "working_group_index", "classification_signals": signals + ["resource_index_marker"]}
    if "abstract" in title and len(lowered) < 8000:
        return {"candidate_content_class": "abstract_only", "classification_signals": ["abstract_marker", "short_body"]}
    if candidate.get("source_class") == "publication_registry" or media == "application/json":
        return {"candidate_content_class": "metadata_record", "classification_signals": ["registry_or_json"]}
    if candidate.get("source_class") in {"material_datasheet", "second_supplier_datasheet"}:
        return {"candidate_content_class": "datasheet", "classification_signals": ["datasheet_source_class"]}
    section_count = len(normalized_document.get("sections") or [])
    body_length = len(lowered)
    if media == "application/pdf" and section_count > 0 and body_length >= 50:
        return {"candidate_content_class": "full_text_pdf", "classification_signals": ["pdf", "normalized_sections", f"body_chars:{body_length}"]}
    if media == "text/html" and body_length >= 3000:
        return {"candidate_content_class": "full_text_html", "classification_signals": ["html", "substantive_body", f"body_chars:{body_length}"]}
    return {"candidate_content_class": "unknown", "classification_signals": [f"media:{media}", f"body_chars:{body_length}"]}


def extract_document_identity(
    candidate: dict[str, Any], normalized_document: dict[str, Any] | None
) -> dict[str, Any]:
    text = _document_text(normalized_document)
    immutable_identity_source = normalized_document is not None
    title = (
        (normalized_document or {}).get("title")
        or candidate.get("source_title")
        or None
    )
    doi_match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", text, re.I)
    nist_match = re.search(r"NIST\s*Technical\s*Note\s*(\d+)", text, re.I)
    ieee_match = re.search(
        r"\bIEEE\s+(?:Std\s+)?P?((?:802\.3[a-z]+|\d{3,4}(?:\.\d+)?)(?:[-–]\d{4})?)",
        f"{title or ''}\n{text}",
        re.I,
    )
    pci_match = re.search(r"PCI(?:\s+Express|e)\s*(\d+(?:\.\d+)?)", f"{title or ''}\n{text}", re.I)
    revision_match = re.search(r"\b(?:Revision|Rev\.?|Version)\b\s*([A-Z0-9.-]+)", text, re.I)
    author_match = re.search(r"Authors?\s*:\s*([^\n]{3,300})", text, re.I)
    explicit_date = None
    explicit_date_match = re.search(
        r"(?:Published|Publication date|Issued|Date)\s*[:\-]\s*((?:19|20)\d{2}-\d{2}-\d{2})",
        text,
        re.I,
    )
    if explicit_date_match:
        explicit_date = explicit_date_match.group(1)
    standard_number = None
    document_number = None
    identifier_evidence: list[str] = []
    if nist_match:
        document_number = f"NIST Technical Note {nist_match.group(1)}"
        identifier_evidence.append("body:nist_technical_note_number")
    elif ieee_match:
        standard_number = f"IEEE {ieee_match.group(1)}"
        identifier_evidence.append(
            "normalized_title_or_body:ieee_standard_number"
            if immutable_identity_source
            else "candidate_title:ieee_standard_number"
        )
    elif pci_match:
        standard_number = f"PCI Express {pci_match.group(1)}"
        identifier_evidence.append(
            "normalized_title_or_body:pci_specification_number"
            if immutable_identity_source
            else "candidate_title:pci_specification_number"
        )
    doi = doi_match.group(0).rstrip(".,;)") if doi_match else None
    if doi:
        identifier_evidence.append("body:doi")
    authors = []
    if author_match:
        authors = [item.strip() for item in re.split(r",|\band\b", author_match.group(1)) if item.strip()]
    elif title and text.lower().startswith(str(title).lower()):
        # A number of conference PDFs put ``title + author + organization`` on
        # the first page without an ``Authors:`` label.  Accept only a compact
        # proper-name immediately following the exact title; this creates a
        # provisional identity candidate, never a resolved publication record.
        remainder = text[len(str(title)):].strip()
        inline_author = re.match(
            r"([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,4})(?:,|\n|$)",
            remainder,
        )
        if inline_author:
            authors = [inline_author.group(1).strip()]
    organizations = [candidate["source_owner"]] if candidate.get("source_owner") else []
    if immutable_identity_source and (doi or standard_number or document_number):
        confidence = "resolved"
    elif title and (authors or doi or standard_number or document_number):
        confidence = "provisional"
    else:
        confidence = "unresolved"
    return {
        "formal_title": title,
        "authors": authors,
        "organizations": organizations,
        "publisher": candidate.get("source_owner"),
        "journal": None,
        "conference": None,
        "standard_number": standard_number,
        "document_number": document_number,
        "revision": revision_match.group(1) if revision_match else None,
        "doi": doi,
        "isbn_or_issn": None,
        "publication_date_explicit": explicit_date,
        "publication_date_status": "known" if explicit_date else "unknown",
        "canonical_source_url": candidate.get("source_url"),
        "document_identity_confidence": confidence,
        "identity_evidence": identifier_evidence + (["body:explicit_publication_date"] if explicit_date else []),
    }


_DISCOVERY_PLANS: dict[str, dict[str, Any]] = {
    "PCB-ER-A04": {
        "research_question": "How are high-speed interconnect insertion loss, fixtures, reference planes, de-embedding and coupons measured and compared?",
        "required_evidence_shape": "formal measurement method with calibration, fixture, reference-plane, uncertainty and channel/coupon denominator",
        "preferred_source_classes": ["national_metrology", "test_standard", "peer_reviewed_metrology", "instrument_method"],
        "query_concepts": ["high-speed channel measurement", "S-parameter calibration", "fixture removal", "de-embedding", "test coupon"],
        "exact_phrases": ["S-parameter", "fixture removal", "de-embedding", "reference plane", "test coupon"],
        "document_identifiers": ["IEEE 370", "IPC-TM-650", "NIST Technical Note"],
        "expected_document_types": ["full_text_pdf", "formal_standard_text", "official_technical_document"],
        "required_denominator_terms": ["measurement uncertainty", "frequency range", "channel length", "differential", "reference plane"],
        "exclusion_terms": ["overview only", "purchase page", "marketing summary"],
        "qualification_rules": ["must expose method text or a measurable procedure", "must identify reference plane or fixture scope"],
        "stop_rules": ["method classes covered", "new results are common-origin", "only purchase/landing pages remain"],
    },
    "PCB-ER-B01": {
        "research_question": "When are laminate Dk and Df values comparable across methods, suppliers and sample conditions?",
        "required_evidence_shape": "formal test method plus supplier declaration and independent material measurement with matched conditions",
        "preferred_source_classes": ["test_standard", "peer_reviewed_material_measurement", "independent_laboratory", "second_supplier_datasheet"],
        "query_concepts": ["dielectric constant test method", "dissipation factor comparison", "design Dk", "clamped stripline", "split post resonator"],
        "exact_phrases": ["Dk test method", "Df test method", "design Dk", "nominal Dk", "typical Df"],
        "document_identifiers": ["IPC-TM-650 2.5.5.5", "IEC 61189", "ASTM D2520"],
        "expected_document_types": ["formal_standard_text", "datasheet", "full_text_pdf"],
        "required_denominator_terms": ["frequency", "temperature", "humidity", "direction", "sample thickness", "resin content", "glass style"],
        "exclusion_terms": ["best material", "marketing comparison", "no test method"],
        "qualification_rules": ["must name test method", "supplier comparison requires matched or convertible method"],
        "stop_rules": ["formal method and independent comparison acquired", "public method text unavailable", "only unmatched supplier tables remain"],
    },
    "PCB-ER-B02": {
        "research_question": "How do copper surface profile metrics and treatment affect measured conductor loss under controlled geometry and frequency?",
        "required_evidence_shape": "identified full-text experiment with roughness metric, geometry, material, frequency, measurement method and uncertainty",
        "preferred_source_classes": ["peer_reviewed_paper", "conference_paper", "independent_engineering_measurement", "supplier_technical_research"],
        "query_concepts": ["copper foil roughness conductor loss", "surface profile insertion loss", "stripline roughness VNA", "test vehicle"],
        "exact_phrases": ["Rz", "Ra", "Rq", "RMS", "measured insertion loss", "stripline", "VNA", "test vehicle", "surface treatment"],
        "document_identifiers": ["DOI", "conference proceedings", "journal article"],
        "expected_document_types": ["full_text_pdf", "dataset_or_measurement_record", "metadata_record"],
        "required_denominator_terms": ["frequency", "line width", "copper thickness", "dielectric thickness", "channel length", "reference plane", "de-embedding"],
        "exclusion_terms": ["roughness marketing claim", "no geometry", "no measurement method"],
        "qualification_rules": ["publication identity must be resolved or provisional", "experiment must expose matched conditions"],
        "stop_rules": ["identity and independent experiment found", "only same original data recurs", "public full text structurally unavailable"],
    },
    "PCB-ER-A02": {
        "research_question": "How do rate, baud, modulation, reach and topology relate to measured channel metrics under a common denominator?",
        "required_evidence_shape": "independent channel measurement with explicit rate, frequency, length, composition, equalization and de-embedding",
        "preferred_source_classes": ["technical_standard", "peer_reviewed_link_measurement", "independent_laboratory", "engineering_measurement"],
        "query_concepts": ["channel insertion loss versus baud rate", "PAM4 reach measurement", "SerDes channel compliance", "connector PCB cable budget"],
        "exact_phrases": ["baud rate", "Nyquist frequency", "channel length", "connector count", "de-embedding", "insertion loss", "return loss"],
        "document_identifiers": ["IEEE 802.3ck", "PCI Express 6.0", "Ethernet channel compliance"],
        "expected_document_types": ["formal_standard_text", "full_text_pdf", "dataset_or_measurement_record"],
        "required_denominator_terms": ["data rate", "baud", "modulation", "Nyquist", "PCB length", "connector count", "equalization", "BER"],
        "exclusion_terms": ["overview only", "working group index", "no measured channel"],
        "qualification_rules": ["overview and index are discovery only", "measurement requires channel composition and reference plane"],
        "stop_rules": ["independent measured denominator acquired", "only standard summaries remain", "measurements cannot be harmonized"],
    },
}


def build_discovery_plan(er_id: str) -> dict[str, Any]:
    try:
        plan = deepcopy(_DISCOVERY_PLANS[er_id])
    except KeyError as exc:
        raise _invalid("No capability discovery plan exists for ER", er_id=er_id) from exc
    return {"er_id": er_id, **plan, "formal_acquisition_authorized": False}


def plan_alternative_entry(
    *, original_candidate_id: str, original_failure_class: str,
    source_owner: str, title: str,
) -> dict[str, Any]:
    mapping = {
        "http_404": ("same_official_domain_document_search", "title_or_document_identifier", "high"),
        "broken_or_moved_url": ("official_document_library", "title_or_document_identifier", "high"),
        "http_403": ("publisher_landing_page", "title_and_author", "medium"),
        "timeout_or_transient_network": ("official_document_library", "stable_official_entry", "medium"),
        "security_policy_blocked": ("independent_equivalent_source", "standard_number_or_equivalent_method", "medium"),
        "encrypted_or_unparseable": ("official_mirror_or_archive", "same_document_title_or_number", "high"),
        "landing_page_only": ("official_document_library", "standard_number", "high"),
        "index_only": ("same_official_domain_document_search", "linked_document_identifier", "high"),
        "metadata_only": ("publisher_landing_page", "doi_or_title_author", "high"),
        "denominator_insufficient": ("independent_equivalent_source", "missing_denominator_terms", "medium"),
        "duplicate_or_common_origin": ("independent_equivalent_source", "new_source_class", "high"),
    }
    entry_type, identifier, gain = mapping.get(
        original_failure_class,
        ("independent_equivalent_source", "title_and_organization", "low"),
    )
    return {
        "original_candidate_id": original_candidate_id,
        "original_failure_class": original_failure_class,
        "alternative_entry_type": entry_type,
        "alternative_identifier": identifier,
        "same_document_or_equivalent_source": (
            "same_document_preferred" if original_failure_class in {"http_404", "broken_or_moved_url", "encrypted_or_unparseable"} else "equivalent_source_allowed"
        ),
        "expected_information_gain": gain,
        "security_eligibility": "safe_plan_only",
        "source_owner": source_owner,
        "title": title,
        "formal_acquisition_authorized": False,
    }


def match_evidence_shape(
    er_id: str, candidate_content_class: str,
    denominator_fields: Iterable[str], source_class: str,
) -> dict[str, Any]:
    fields = set(denominator_fields)
    if candidate_content_class == "working_group_index":
        match = "source_discovery_only"
    elif candidate_content_class in {"standard_landing_page", "overview", "abstract_only", "metadata_record", "purchase_page", "marketing_page"}:
        match = "context_only" if candidate_content_class in {"overview", "abstract_only"} else "source_discovery_only"
    elif candidate_content_class in {"broken_url", "unknown"}:
        match = "does_not_answer_er"
    elif er_id == "PCB-ER-A04" and source_class in {"national_metrology", "test_standard", "instrument_method", "technical_standard"}:
        match = "answers_er_directly" if {"reference_plane", "deembedding_method", "uncertainty_or_repeatability"} <= fields else "answers_er_partially"
    elif er_id == "PCB-ER-B01":
        if source_class == "national_metrology":
            match = "context_only"
        elif source_class in {"test_standard", "peer_reviewed_material_measurement", "independent_laboratory", "second_supplier_datasheet"}:
            match = "answers_er_directly" if {"test_method", "frequency", "sample_geometry"} <= fields else "answers_er_partially"
        else:
            match = "context_only"
    elif er_id == "PCB-ER-B02":
        if source_class == "national_metrology":
            match = "context_only"
        elif source_class in {"academic_research", "peer_reviewed_paper", "conference_paper", "independent_engineering_measurement"}:
            match = "answers_er_directly" if {"surface_profile_metric", "frequency_range", "trace_geometry", "measurement_or_simulation_method"} <= fields else "answers_er_partially"
        else:
            match = "context_only"
    elif er_id == "PCB-ER-A02":
        if source_class in {"engineering_measurement", "peer_reviewed_link_measurement", "independent_laboratory"}:
            match = "answers_er_directly" if {"data_rate", "channel_length", "insertion_loss", "deembedding_method"} <= fields else "answers_er_partially"
        else:
            match = "context_only"
    else:
        match = "does_not_answer_er"
    return {
        "target_evidence_match": match,
        "match_basis": {
            "er_id": er_id,
            "candidate_content_class": candidate_content_class,
            "source_class": source_class,
            "denominator_fields": sorted(fields),
        },
    }


def collapse_document_identities(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[item["content_hash"]].append(item)
    return [
        {
            "document_identity_id": f"document_identity:{digest[:24]}",
            "content_hash": digest,
            "artifact_ids": sorted(row["artifact_id"] for row in rows),
            "authorized_er_ids": sorted({er for row in rows for er in row.get("authorized_er_ids") or []}),
        }
        for digest, rows in sorted(grouped.items())
    ]


def load_normalized_document(
    document_id: str | None, *, layout: LayeredResearchLayout
) -> dict[str, Any] | None:
    if not document_id:
        return None
    path = layout.evidence_normalized_dir / f"{document_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))["normalized_document"]


def diagnose_attempt(
    candidate: dict[str, Any], attempt: dict[str, Any],
    inventory_item: dict[str, Any] | None,
    *, layout: LayeredResearchLayout,
) -> dict[str, Any]:
    document = load_normalized_document(
        None if inventory_item is None else inventory_item.get("normalized_document_id"),
        layout=layout,
    )
    qualification = classify_candidate_content(candidate, attempt, document)
    er_id = (attempt.get("authorized_er_ids") or candidate.get("authorized_er_ids") or [None])[0]
    denominator_fields = [] if inventory_item is None else inventory_item.get("denominator_fields_present") or []
    shape = match_evidence_shape(
        er_id,
        qualification["candidate_content_class"],
        denominator_fields,
        candidate.get("source_class") or "unknown",
    )
    cause = classify_root_cause(
        candidate,
        attempt,
        content_class=qualification["candidate_content_class"],
        evidence_match=shape["target_evidence_match"],
    )
    identity = extract_document_identity(candidate, document)
    alternative = plan_alternative_entry(
        original_candidate_id=candidate["candidate_id"],
        original_failure_class=cause["root_cause_class"],
        source_owner=candidate.get("source_owner") or "unknown",
        title=candidate.get("source_title") or "unknown",
    )
    return {
        "attempt_id": attempt["attempt_id"],
        "candidate_id": candidate["candidate_id"],
        "authorized_er_ids": list(attempt.get("authorized_er_ids") or []),
        "source_class": candidate.get("source_class"),
        "requested_url": candidate.get("source_url"),
        "result": attempt.get("status"),
        "root_cause_class": cause["root_cause_class"],
        "candidate_content_class": qualification["candidate_content_class"],
        "classification_signals": qualification["classification_signals"],
        "target_evidence_match": shape["target_evidence_match"],
        "identity_resolution_status": identity["document_identity_confidence"],
        "document_identity": identity,
        "alternative_entry_status": alternative["alternative_entry_type"],
        "alternative_entry_plan": alternative,
        "retry_value": cause["retry_value"],
        "recommended_next_action": _recommended_action(cause["root_cause_class"], shape["target_evidence_match"]),
    }


def _recommended_action(root_cause: str, evidence_match: str) -> str:
    if root_cause in {"http_404", "broken_or_moved_url"}:
        return "resolve_title_or_document_number_in_official_library"
    if root_cause == "http_403":
        return "use_publisher_record_or_author_repository_without_bypass"
    if root_cause == "timeout_or_transient_network":
        return "bounded_retry_then_stable_official_or_equivalent_entry"
    if root_cause == "security_policy_blocked":
        return "retain_fail_closed_and_use_legal_alternative_source"
    if root_cause == "encrypted_or_unparseable":
        return "find_same_public_parseable_document_or_equivalent_source"
    if root_cause in {"landing_page_only", "index_only", "overview_only", "metadata_only"}:
        return "resolve_full_text_identifier_before_formal_acquisition"
    if evidence_match == "context_only":
        return "retain_as_context_and_redirect_discovery_to_required_evidence_shape"
    if evidence_match == "answers_er_partially":
        return "target_missing_denominator_fields"
    return "human_review"


def validate_capability_checkpoint(
    checkpoint: dict[str, Any], *, validate_schema: bool = True
) -> dict[str, Any]:
    copied = deepcopy(checkpoint)
    if copied.get("content_hash") != content_sha256(
        copied, excluded_paths=(("content_hash",),)
    ):
        raise _invalid("Capability checkpoint hash mismatch")
    if copied.get("formal_research_coverage_change") != 0:
        raise _invalid("Capability hardening changed formal research coverage")
    if copied.get("landing_or_index_false_positive_count") != 0:
        raise _invalid("Capability benchmark promoted landing/index content")
    if copied.get("security_policy_violations") != 0:
        raise _invalid("Capability benchmark contains a security-policy violation")
    if any(
        copied.get(field) is not False
        for field in (
            "recovery_acquisition_authorized", "wave_1b_assessment_authorized",
            "cognition_update_authorized", "company_mapping_authorized",
            "stage_a2_authorized", "stage_b_authorized",
        )
    ):
        raise _invalid("Capability checkpoint authorizes a prohibited downstream action")
    return copied


def validate_non_evidence_artifact(payload: dict[str, Any]) -> None:
    if (
        payload.get("artifact_role") != CAPABILITY_ROLE
        or payload.get("eligible_for_evidence") is not False
        or payload.get("eligible_for_er_coverage") is not False
        or payload.get("eligible_for_assessment") is not False
    ):
        raise _invalid("Capability artifact is eligible for formal research use")
    if payload.get("content_hash") != content_sha256(payload, excluded_paths=(("content_hash",),)):
        raise _invalid("Capability artifact hash mismatch")


def capability_artifact_envelope(
    artifact_type: str, body: dict[str, Any]
) -> dict[str, Any]:
    payload = {
        "schema_version": "1.0.0",
        "artifact_type": artifact_type,
        "artifact_role": CAPABILITY_ROLE,
        "eligible_for_evidence": False,
        "eligible_for_er_coverage": False,
        "eligible_for_assessment": False,
        **deepcopy(body),
        "content_hash": "",
    }
    payload["content_hash"] = content_sha256(payload, excluded_paths=(("content_hash",),))
    return payload


def checkpoint_identity(core: dict[str, Any]) -> str:
    return f"acquisition_capability_checkpoint:{sha256(canonical_bytes(core)).hexdigest()[:24]}"


def load_capability_artifact(name: str, *, layout: LayeredResearchLayout) -> dict[str, Any]:
    path = layout.root / CAPABILITY_DIRNAME / name
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _invalid("Capability artifact is missing or invalid", path=str(path)) from exc
    validate_non_evidence_artifact(payload)
    return payload


def validate_capability_repository_bundle(
    *, layout: LayeredResearchLayout | None = None,
) -> dict[str, Any]:
    effective = layout or LayeredResearchLayout.default()
    diagnosis = load_capability_artifact("diagnosis.json", layout=effective)
    manifest = load_capability_artifact("benchmark_manifest.json", layout=effective)
    results = load_capability_artifact("benchmark_results.json", layout=effective)
    checkpoint = load_capability_artifact("capability_checkpoint.json", layout=effective)
    validate_capability_checkpoint(checkpoint)

    upstream = {
        "wave_1b_checkpoint_hash": (
            effective.root / "acquisition/wave_1b/acquisition_checkpoint.json"
        ),
        "wave_1b_gate_hash": (
            effective.governance_dir / "ai_pcb_targeted_acquisition_wave_1b_gate_decision_v1.json"
        ),
        "wave_1_assessment_hash": (
            effective.analysis_dir / "ai_pcb_targeted_evidence_assessment_wave_1_v1.json"
        ),
        "wave_1_checkpoint_hash": (
            effective.root / "acquisition/wave_1/acquisition_checkpoint.json"
        ),
    }
    for field, path in upstream.items():
        try:
            actual = json.loads(path.read_text(encoding="utf-8"))["content_hash"]
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError) as exc:
            raise _invalid("Upstream capability binding is unavailable", field=field, path=str(path)) from exc
        if checkpoint.get(field) != actual or diagnosis.get("bindings", {}).get(field) != actual:
            raise _invalid("Upstream capability binding drift", field=field, expected=checkpoint.get(field), actual=actual)

    if results.get("benchmark_manifest_hash") != manifest.get("content_hash"):
        raise _invalid("Benchmark manifest binding drift")
    manifest_ids = [row.get("case_id") for row in manifest.get("cases") or []]
    result_ids = [row.get("case_id") for row in results.get("cases") or []]
    if manifest_ids != result_ids or len(set(result_ids)) != len(result_ids):
        raise _invalid("Benchmark case universe drift")
    recomputed_passes = sum(
        bool(row.get("passed"))
        and all(row.get("actual", {}).get(key) == value for key, value in (row.get("expected") or {}).items())
        for row in results.get("cases") or []
    )
    if (
        recomputed_passes != results.get("passed_case_count")
        or results.get("failed_case_count") != len(result_ids) - recomputed_passes
        or checkpoint.get("offline_fixture_pass_count") != recomputed_passes
        or checkpoint.get("benchmark_case_count") != len(result_ids)
    ):
        raise _invalid("Benchmark result is not deterministically reproducible")
    for field in (
        "landing_or_index_false_positive_count", "formal_research_coverage_change",
        "security_policy_violation_count",
    ):
        if checkpoint.get(field) != results.get("metrics", {}).get(field):
            raise _invalid("Benchmark metric drift", field=field)
    if checkpoint.get("diagnosis_hash") != diagnosis.get("content_hash"):
        raise _invalid("Diagnosis binding drift")
    if checkpoint.get("benchmark_results_hash") != results.get("content_hash"):
        raise _invalid("Benchmark results binding drift")
    return {
        "status": "pass",
        "checkpoint_id": checkpoint["checkpoint_id"],
        "checkpoint_hash": checkpoint["content_hash"],
        "benchmark_case_count": len(result_ids),
        "passed_case_count": recomputed_passes,
        "formal_research_coverage_change": checkpoint["formal_research_coverage_change"],
        "security_policy_violations": checkpoint["security_policy_violations"],
    }
