from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from stock_research.research_project_v2.canonical import canonical_bytes, content_sha256
from stock_research.research_project_v2.errors import ResearchProjectV2Error


AUTHORIZED_ERS = {"PCB-ER-A02", "PCB-ER-B01", "PCB-ER-B02"}
PROHIBITED_DOWNSTREAM_FIELDS = (
    "consolidated_assessment_authorized",
    "cognition_update_authorized",
    "company_mapping_authorized",
    "stage_a2_authorized",
    "stage_b_authorized",
)
TERMINAL_STATUSES = {
    "primary_source_confirmed_and_acquired",
    "primary_source_confirmed_but_not_acquired",
    "primary_source_candidate_found",
    "publisher_identity_confirmed_only",
    "secondary_source_only",
    "citation_present_but_unresolved",
    "unattributed_claim",
    "analyst_calculation",
    "analyst_inference",
    "investment_opinion_non_evidence",
    "identity_mismatch",
}

_A02 = re.compile(
    r"(?:112G|224G|400G|800G|1\.6T|data\s*rate|baud|SerDes|PCIe\s*[456]\.?0?|"
    r"channel\s*(?:reach|loss|measurement)|Nyquist|retimer|equalization|return\s*loss|"
    r"insertion\s*loss|通道(?:距离|损耗|测量)|速率|插损预算)",
    re.I,
)
_B01 = re.compile(
    r"(?:\bDk\b|\bDf\b|design\s*Dk|test\s*Dk|介电常数|介质损耗|损耗因子|"
    r"resin\s*content|glass\s*style|树脂含量|测试频率|测试方法)",
    re.I,
)
_B02 = re.compile(
    r"(?:HVLP|VLP|RTF|\bRz\b|\bRa\b|\bRq\b|RMS|surface\s*(?:profile|roughness|treatment)|"
    r"copper\s*foil\s*roughness|skin\s*effect|趋肤效应|铜箔粗糙度|表面粗糙度|"
    r"导体损耗|stripline|microstrip|test\s*vehicle|\bVNA\b)",
    re.I,
)
_A04 = re.compile(r"(?:de-?embedding|fixture\s*removal|reference\s*plane|去嵌|夹具移除)", re.I)
_INVESTMENT = re.compile(
    r"(?:买入|增持|目标价|投资建议|盈利预测|估值|reiterate\s+buy|target\s+price|\bBUY\b)",
    re.I,
)
_ANALYST = re.compile(r"(?:我们预计|我们认为|预计公司|测算|CMBIGM estimates|券商整理)", re.I)
_SOURCE = re.compile(r"(?:资料来源|数据来源|来源[:：]|Source[:：]|参考文献|注[:：])", re.I)
_DATE_CN = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_DATE_ISO = re.compile(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})")
_DATE_EN = re.compile(
    r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})\b",
    re.I,
)
_DATE_COMPACT_METADATA = re.compile(r"-(\d{2})(\d{2})(\d{2})(?:\.pdf)?$", re.I)
_ANALYST_NAME = re.compile(r"分析师[:：]\s*([\u4e00-\u9fff]{2,4})")
_FIGURE = re.compile(r"((?:图表|图|表)\s*\d+)")
_QUOTED_TITLE = re.compile(r"《([^》]{4,160})》")
_AUTHOR = re.compile(r"作者[:：]\s*([^），,；;]{2,60})")
_DOI = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
_STANDARD = re.compile(r"(?:IPC(?:-TM)?-[A-Z0-9.\-/]+|IEEE\s+[A-Z0-9.\-/]+|OIF-[A-Z0-9.\-/]+)", re.I)


def _invalid(message: str, **details: object) -> ResearchProjectV2Error:
    return ResearchProjectV2Error(
        message,
        code="RESEARCH_PROJECT_V2_1_PRIMARY_SOURCE_TRACEBACK_INVALID",
        details=details,
    )


def _validate_hash(payload: dict[str, Any], *, label: str) -> None:
    if payload.get("content_hash") != content_sha256(
        payload, excluded_paths={("content_hash",)}
    ):
        raise _invalid(f"{label} hash mismatch")


def validate_traceback_authorization(
    authorization: dict[str, Any],
    *,
    gate: dict[str, Any],
    validate_upstreams: bool = True,
    source_repository_root: Path | None = None,
) -> dict[str, Any]:
    copied = deepcopy(authorization)
    _validate_hash(copied, label="Traceback execution authorization")
    _validate_hash(gate, label="Primary-Source Traceback Gate")
    if (
        copied.get("authorization_status") != "frozen"
        or copied.get("execution_authorized") is not True
        or copied.get("authorization_scope") != "exact_report_list_only"
        or copied.get("maximum_report_count") != 5
        or copied.get("authorization_consumed") is not False
    ):
        raise _invalid("Traceback execution authorization is not executable")
    if (
        copied.get("machine_first_traceback") is not True
        or copied.get("human_assistance_required") is not False
        or copied.get("manual_source_resolution_required") is not False
        or copied.get("unresolved_is_valid_terminal_state") is not True
    ):
        raise _invalid("Traceback authorization violates machine-first requirements")
    if set(copied.get("authorized_er_ids") or []) != AUTHORIZED_ERS:
        raise _invalid("Traceback ER scope is invalid; A04 and unlisted ERs are prohibited")
    if any(copied.get(field) is not False for field in PROHIBITED_DOWNSTREAM_FIELDS):
        raise _invalid("Traceback authorization enables a prohibited downstream stage")
    gate_targets = {
        row["traceback_target_id"]: row for row in gate.get("selected_targets") or []
    }
    authorized = copied.get("authorized_targets") or []
    if (
        len(authorized) != 5
        or len(gate_targets) != 5
        or {row.get("traceback_target_id") for row in authorized} != set(gate_targets)
    ):
        raise _invalid("Traceback exact target binding drifted")
    for row in authorized:
        frozen = gate_targets[row["traceback_target_id"]]
        if row.get("report_content_sha256") != frozen.get("report_content_sha256"):
            raise _invalid("Traceback report hash binding drifted")
    bindings = copied.get("input_bindings") or {}
    if (
        bindings.get("traceback_gate_id") != gate.get("decision_id")
        or bindings.get("traceback_gate_hash") != gate.get("content_hash")
    ):
        raise _invalid("Traceback Gate binding drifted")
    if validate_upstreams:
        if source_repository_root is None:
            raise _invalid("source_repository_root is required for upstream validation")
        for target in gate_targets.values():
            path = source_repository_root / target["report_path"]
            if not path.is_file() or sha256(path.read_bytes()).hexdigest() != target["report_content_sha256"]:
                raise _invalid("Traceback report PDF hash drifted", target_id=target["traceback_target_id"])
    return copied


def _explicit_date(text: str) -> str | None:
    match = _DATE_CN.search(text) or _DATE_ISO.search(text)
    if match:
        year, month, day = (int(value) for value in match.groups())
    else:
        english = _DATE_EN.search(text)
        if not english:
            return None
        day_text, month_text, year_text = english.groups()
        month = {
            name: index
            for index, name in enumerate(
                ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
                start=1,
            )
        }[month_text[:3].casefold()]
        year, day = int(year_text), int(day_text)
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def extract_report_identity_from_pages(
    *, target: dict[str, Any], pages: list[str]
) -> dict[str, Any]:
    first = "\n".join(pages[:2])
    analysts = sorted(set(_ANALYST_NAME.findall(first)))
    explicit_date = _explicit_date(first)
    date_source = "pdf_text" if explicit_date else None
    metadata_title = target.get("pdf_metadata_title") or ""
    if explicit_date is None:
        compact = _DATE_COMPACT_METADATA.search(metadata_title)
        if compact:
            yy, month, day = (int(value) for value in compact.groups())
            try:
                explicit_date = date(2000 + yy, month, day).isoformat()
                date_source = "pdf_metadata_title"
            except ValueError:
                pass
    return {
        "report_id": f"broker_report:{target['report_content_sha256'][:24]}",
        "traceback_target_id": target["traceback_target_id"],
        "report_title": target["report_title"],
        "broker_or_research_institution": target["report_owner"],
        "analysts": analysts,
        "publication_date_explicit": explicit_date,
        "publication_date_status": "explicit_in_pdf" if explicit_date else "unresolved",
        "publication_date_source": date_source,
        "language": "zh" if re.search(r"[\u4e00-\u9fff]", first) else "en",
        "page_count": len(pages),
        "report_file_hash": target["report_content_sha256"],
        "report_identity_confidence": "high",
        "report_identity_status": "resolved",
        "human_confirmation_required": False,
    }


def _page_blocks(text: str) -> list[str]:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return [line for line in lines if line]


def _claim_er(text: str, authorized_er_ids: set[str]) -> str | None:
    if "PCB-ER-B02" in authorized_er_ids and _B02.search(text):
        return "PCB-ER-B02"
    if "PCB-ER-B01" in authorized_er_ids and _B01.search(text):
        return "PCB-ER-B01"
    if "PCB-ER-A02" in authorized_er_ids and _A02.search(text) and not _A04.search(text):
        return "PCB-ER-A02"
    return None


def extract_claims_from_pages(
    *,
    report_id: str,
    traceback_target_id: str,
    report_file_hash: str,
    pages: list[str],
    authorized_er_ids: set[str],
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for page_number, page in enumerate(pages, start=1):
        blocks = _page_blocks(page)
        current_heading: str | None = None
        for block_index, block in enumerate(blocks, start=1):
            if len(block) < 8 or _SOURCE.search(block):
                continue
            if len(block) < 80 and re.match(r"^\d+(?:\.\d+)*\s+", block):
                current_heading = block
            claim_class: str | None = None
            er_id = _claim_er(block, authorized_er_ids)
            if _INVESTMENT.search(block):
                claim_class = "investment_opinion"
                er_id = None
            elif _ANALYST.search(block) and er_id is None:
                claim_class = "analyst_inference"
            elif er_id is not None:
                if re.search(r"(?:公司公告|公司官网|公司资料|年报|招股书)", block):
                    claim_class = "company_disclosure_reference"
                else:
                    claim_class = "technical_fact_with_ambiguous_source"
            if claim_class is None:
                continue
            claim_text_hash = sha256(block.encode("utf-8")).hexdigest()
            claim_identity_hash = sha256(f"{report_id}\n{block}".encode("utf-8")).hexdigest()
            figure = _FIGURE.search(block)
            claims.append(
                {
                    "claim_id": f"broker_claim:{claim_identity_hash[:24]}",
                    "report_id": report_id,
                    "traceback_target_id": traceback_target_id,
                    "er_id": er_id,
                    "claim_text": block,
                    "claim_class": claim_class,
                    "report_file_hash": report_file_hash,
                    "page_number": page_number,
                    "section_heading": current_heading,
                    "paragraph_or_block_index": block_index,
                    "figure_or_table_id": figure.group(1).replace(" ", "") if figure else None,
                    "source_note_text": None,
                    "claim_text_hash": claim_text_hash,
                    "locator_note": "Page-local text block extracted deterministically from the broker PDF.",
                    "citation_ids": [],
                    "terminal_status": (
                        "investment_opinion_non_evidence"
                        if claim_class == "investment_opinion"
                        else "analyst_inference"
                        if claim_class == "analyst_inference"
                        else "unattributed_claim"
                    ),
                    "admitted_to_evidence_assessment": False,
                }
            )
    return claims


def _citation_specificity(text: str) -> str:
    if _QUOTED_TITLE.search(text) or _DOI.search(text) or _STANDARD.search(text):
        return "exact_document"
    if re.search(r"(?:公司官网|公司资料|公司公告)", text) and not re.search(
        r"(?:20\d{2}|《|编号|证券代码)", text
    ):
        return "generic_company_material"
    if re.search(r"(?:招股书|招股说明书|年报|公告|公开转让说明书)", text):
        return "partial_identity"
    if re.search(r"(?:Wind|Prismark|QY\s*Research|CNKI|研究院|情报网)", text, re.I):
        return "secondary_source"
    return "unattributed"


def extract_citations_from_pages(
    *, report_id: str, pages: list[str]
) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for page_number, page in enumerate(pages, start=1):
        for block_index, block in enumerate(_page_blocks(page), start=1):
            if not _SOURCE.search(block):
                continue
            digest = sha256(f"{report_id}\n{page_number}\n{block_index}\n{block}".encode()).hexdigest()
            title = _QUOTED_TITLE.search(block)
            author = _AUTHOR.search(block)
            doi = _DOI.search(block)
            standard = _STANDARD.search(block)
            citations.append(
                {
                    "citation_id": f"broker_citation:{digest[:24]}",
                    "report_id": report_id,
                    "report_claim_ids": [],
                    "page_number": page_number,
                    "block_index": block_index,
                    "citation_raw_text": block,
                    "citation_type": "source_note",
                    "named_source_entities": sorted(
                        set(
                            re.findall(
                                r"(?:公司官网|公司公告|公司年报|公司招股书|Wind|Prismark(?: Partners)?|QY\s*Research|CNKI|[\u4e00-\u9fff]{2,12}研究院)",
                                block,
                                flags=re.I,
                            )
                        )
                    ),
                    "document_title_candidate": title.group(1).strip() if title else None,
                    "authors_candidate": [re.sub(r"等$", "", author.group(1).strip())] if author else [],
                    "publisher_candidate": None,
                    "standard_or_document_number": standard.group(0) if standard else None,
                    "doi_candidate": doi.group(0).rstrip(".,;。；") if doi else None,
                    "publication_date_candidate": None,
                    "citation_specificity": _citation_specificity(block),
                }
            )
    return citations


def bind_claims_to_citations(
    claims: list[dict[str, Any]], citations: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    copied = deepcopy(claims)
    for claim in copied:
        if claim.get("claim_class") in {"investment_opinion", "analyst_inference"}:
            continue
        same_page = [
            citation
            for citation in citations
            if citation["report_id"] == claim["report_id"]
            and citation["page_number"] == claim["page_number"]
        ]
        if not same_page:
            continue
        nearest = min(
            same_page,
            key=lambda row: abs(row["block_index"] - claim["paragraph_or_block_index"]),
        )
        if abs(nearest["block_index"] - claim["paragraph_or_block_index"]) > 8:
            continue
        claim["citation_ids"] = [nearest["citation_id"]]
        claim["source_note_text"] = nearest["citation_raw_text"]
        claim["claim_class"] = (
            "technical_fact_with_explicit_source"
            if nearest["citation_specificity"] == "exact_document"
            else "technical_fact_with_ambiguous_source"
        )
        claim["terminal_status"] = "citation_present_but_unresolved"
        nearest["report_claim_ids"].append(claim["claim_id"])
    return copied


def build_source_candidates(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for citation in citations:
        raw = citation["citation_raw_text"]
        specificity = citation.get("citation_specificity") or _citation_specificity(raw)
        quoted_title = _QUOTED_TITLE.search(raw)
        author_match = _AUTHOR.search(raw)
        title = citation.get("document_title_candidate") or (
            quoted_title.group(1).strip() if quoted_title else None
        )
        if not title:
            if re.search(r"(?:公司公告|公司年报|公司招股书|公司官网)", raw):
                title = next(
                    label
                    for label in ("公司年报", "公司招股书", "公司公告", "公司官网")
                    if label in raw
                )
            elif citation.get("named_source_entities"):
                title = " / ".join(citation["named_source_entities"])
            else:
                continue
        core = {
                "candidate_title": title,
            "candidate_authors": citation.get("authors_candidate") or (
                [re.sub(r"等$", "", author_match.group(1).strip())]
                if author_match
                else []
            ),
            "candidate_organization": (
                citation.get("named_source_entities") or [None]
            )[0],
            "candidate_source_class": (
                "formal_document"
                if specificity == "exact_document"
                else "company_material"
                if specificity in {"partial_identity", "generic_company_material"}
                else "secondary_source"
            ),
            "candidate_document_number": citation.get("standard_or_document_number"),
            "candidate_standard_number": citation.get("standard_or_document_number"),
            "candidate_doi": citation.get("doi_candidate"),
            "candidate_url": None,
            "identity_status": (
                "provisional"
                if specificity in {"exact_document", "partial_identity"}
                else "unresolved"
            ),
            "identity_confidence": (
                "medium" if specificity == "exact_document" else "low"
            ),
            "identity_evidence": [citation["citation_id"]],
            "citation_specificity": specificity,
            "originating_report_ids": [citation["report_id"]],
            "originating_claim_ids": list(citation.get("report_claim_ids") or []),
            "common_origin_group": citation.get("common_origin_group"),
            "formal_acquisition_authorized": False,
        }
        identity = sha256(canonical_bytes(core)).hexdigest()[:24]
        candidates.append({"source_candidate_id": f"traceback_source_candidate:{identity}", **core})
    return candidates


def classify_candidate_content(
    *, content_type: str, title: str, text: str, has_full_text: bool
) -> str:
    lower = f"{title}\n{text}".casefold()
    if not has_full_text:
        if "abstract" in lower or "doi" in lower or "journal" in lower:
            return "publisher_record"
        return "metadata_record"
    if content_type == "application/pdf" and re.search(r"\b(methods?|results?|experiment|measurement)\b", lower):
        return "peer_reviewed_paper"
    if re.search(r"(?:年度报告|公司公告|证券代码|招股说明书)", text):
        return "official_company_disclosure"
    if re.search(r"(?:datasheet|data sheet|technical data|产品规格|典型值)", lower):
        return "official_product_datasheet"
    if _STANDARD.search(text):
        return "formal_standard_text"
    return "full_text_primary_source"


def collapse_common_origin_candidates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    for row in candidates:
        key = (re.sub(r"\s+", "", row["candidate_title"]).casefold(), row.get("common_origin_group"))
        grouped.setdefault(key, []).append(row)
    collapsed: list[dict[str, Any]] = []
    for rows in grouped.values():
        canonical = deepcopy(rows[0])
        canonical["originating_candidate_ids"] = sorted(
            row["source_candidate_id"] for row in rows
        )
        canonical["originating_report_ids"] = sorted(
            {report_id for row in rows for report_id in row.get("originating_report_ids", [])}
        )
        canonical["originating_claim_ids"] = sorted(
            {claim_id for row in rows for claim_id in row.get("originating_claim_ids", [])}
        )
        canonical["provisional_source_chain_count"] = 1
        collapsed.append(canonical)
    return collapsed


def select_traceback_candidates(
    candidates: list[dict[str, Any]], *, maximum_count: int
) -> list[dict[str, Any]]:
    if maximum_count < 1 or maximum_count > 25:
        raise _invalid("Traceback candidate limit must be between one and 25")
    priority = {
        "exact_document": 0,
        "partial_identity": 1,
        "generic_company_material": 2,
        "secondary_source": 3,
        "unattributed": 4,
    }
    ordered = sorted(
        (deepcopy(row) for row in candidates),
        key=lambda row: (
            priority.get(row.get("citation_specificity"), 5),
            row.get("candidate_title") or "",
            row.get("source_candidate_id") or "",
        ),
    )
    return ordered[:maximum_count]


def build_traceback_artifact(
    *,
    authorization_hash: str,
    gate_hash: str,
    report_identities: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    citations: list[dict[str, Any]],
    source_candidates: list[dict[str, Any]],
    trace_links: list[dict[str, Any]],
    acquired_sources: list[dict[str, Any]],
    checkpoint_summary: dict[str, Any],
    created_at: str,
) -> dict[str, Any]:
    core = {
        "schema_version": "1.0.0",
        "artifact_type": "ai_pcb_primary_source_traceback",
        "artifact_role": "primary_source_traceback",
        "direct_er_evidence_admission": False,
        "execution_authorization_hash": authorization_hash,
        "traceback_gate_hash": gate_hash,
        "report_identities": deepcopy(report_identities),
        "claims": deepcopy(claims),
        "citations": deepcopy(citations),
        "source_candidates": deepcopy(source_candidates),
        "trace_links": deepcopy(trace_links),
        "acquired_sources": deepcopy(acquired_sources),
        "checkpoint_summary": deepcopy(checkpoint_summary),
        "created_at": created_at,
        "created_by": "Codex",
    }
    identity = sha256(canonical_bytes(core)).hexdigest()[:24]
    payload = {
        "artifact_id": f"primary_source_traceback:ai_pcb:{identity}",
        **core,
        "content_hash": "",
    }
    payload["content_hash"] = content_sha256(
        payload, excluded_paths={("content_hash",)}
    )
    return payload


def validate_traceback_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    copied = deepcopy(payload)
    _validate_hash(copied, label="Primary-source traceback artifact")
    if (
        copied.get("artifact_role") != "primary_source_traceback"
        or copied.get("direct_er_evidence_admission") is not False
    ):
        raise _invalid("Traceback artifact role or admission boundary is invalid")
    if any(
        row.get("admitted_to_evidence_assessment") is not False
        or row.get("er_sufficient") is not False
        or row.get("cognition_update_eligible") is not False
        for row in copied.get("acquired_sources") or []
    ):
        raise _invalid("Traceback source was automatically admitted downstream")
    if any(row.get("er_id") not in AUTHORIZED_ERS | {None} for row in copied.get("claims") or []):
        raise _invalid("Traceback artifact contains an unauthorized ER")
    if any(row.get("terminal_status") not in TERMINAL_STATUSES for row in copied.get("claims") or []):
        raise _invalid("Traceback artifact contains an invalid terminal status")
    return copied


def validate_traceback_repository_bundle(
    *,
    layout_root: Path,
    source_repository_root: Path,
) -> dict[str, Any]:
    governance = layout_root / "governance"
    bundle = layout_root / "acquisition/primary_source_traceback_v1"
    gate = json.loads(
        (governance / "ai_pcb_primary_source_traceback_gate_decision_v1.json").read_text(encoding="utf-8")
    )
    authorization = json.loads(
        (governance / "ai_pcb_primary_source_traceback_execution_authorization_v1.json").read_text(encoding="utf-8")
    )
    validate_traceback_authorization(
        authorization,
        gate=gate,
        validate_upstreams=True,
        source_repository_root=source_repository_root,
    )
    triage_bindings = {
        "triage_csv_hash": gate["input_bindings"]["triage_csv_path"],
        "triage_audit_hash": gate["input_bindings"]["triage_audit_path"],
        "triage_summary_hash": gate["input_bindings"]["triage_summary_path"],
    }
    for field, relative in triage_bindings.items():
        path = source_repository_root / relative
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != authorization["input_bindings"][field]:
            raise _invalid("Traceback triage upstream hash drifted", field=field)
    artifact = json.loads(
        (layout_root / "analysis/ai_pcb_primary_source_traceback_v1.json").read_text(encoding="utf-8")
    )
    validate_traceback_artifact(artifact)
    checkpoint = json.loads((bundle / "traceback_checkpoint.json").read_text(encoding="utf-8"))
    validate_traceback_checkpoint(checkpoint, gate=gate, authorization=authorization)
    candidates = [
        json.loads(line)
        for line in (bundle / "source_candidates.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    attempts = [
        json.loads(line)
        for line in (bundle / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    trace_links = [
        json.loads(line)
        for line in (bundle / "trace_links.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(candidates) > 25 or len(attempts) > 30:
        raise _invalid("Traceback candidate or acquisition limit exceeded")
    if any(set(row.get("authorized_er_ids") or []) - AUTHORIZED_ERS for row in attempts):
        raise _invalid("Traceback attempt contains an unauthorized ER")
    if any(row.get("status") == "acquired" and row.get("attempt", {}).get("proxy_mode") != "direct" for row in attempts):
        raise _invalid("Traceback acquisition did not use direct proxy mode")
    raw_manifest = json.loads((bundle / "raw/manifest.json").read_text(encoding="utf-8"))
    normalized_manifest = json.loads((bundle / "normalized/manifest.json").read_text(encoding="utf-8"))
    for row in raw_manifest:
        path = layout_root / row["raw_artifact_path"]
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != row["source_artifact_hash"]:
            raise _invalid("Traceback raw artifact hash drifted", source_candidate_id=row["source_candidate_id"])
    normalized_by_id: dict[str, dict[str, Any]] = {}
    for row in normalized_manifest:
        if row["normalization_status"] != "normalized":
            continue
        wrapper = json.loads(
            (layout_root / f"evidence/normalized/{row['normalized_document_id']}.json").read_text(encoding="utf-8")
        )
        document = wrapper.get("normalized_document", wrapper)
        if document.get("document_hash") != row["normalized_document_hash"]:
            raise _invalid("Traceback normalized document hash drifted")
        normalized_by_id[row["normalized_document_id"]] = document
    claim_ids = {row["claim_id"] for row in artifact.get("claims") or []}
    for link in trace_links:
        if link["report_claim_id"] not in claim_ids:
            raise _invalid("Trace link references an unknown report claim")
        document = normalized_by_id.get(link["normalized_document_id"])
        if document is None:
            raise _invalid("Trace link references a missing normalized document")
        index = link["source_section_index"] - 1
        if index < 0 or index >= len(document["sections"]):
            raise _invalid("Trace link section index is invalid")
        if document["sections"][index]["section_hash"] != link["source_section_hash"]:
            raise _invalid("Trace link section hash drifted")
    expected_report = render_traceback_report(artifact)
    if (layout_root / "reports/ai_pcb_primary_source_traceback_v1.md").read_text(encoding="utf-8") != expected_report:
        raise _invalid("Traceback report is not the deterministic artifact projection")
    if checkpoint.get("source_candidate_count") != len(candidates) or checkpoint.get("formal_attempt_count") != len(attempts):
        raise _invalid("Traceback checkpoint counts drifted from bundle")
    return {
        "valid": True,
        "processed_report_count": checkpoint["processed_report_count"],
        "candidate_count": len(candidates),
        "attempt_count": len(attempts),
        "trace_link_count": len(trace_links),
        "raw_artifact_count": len(raw_manifest),
        "normalized_artifact_count": len(normalized_by_id),
        "human_assistance_requested": checkpoint["human_assistance_requested"],
        "consolidated_assessment_started": checkpoint["consolidated_assessment_started"],
    }


def verify_claim_source_support(
    *,
    report_claim: str,
    source_text: str,
    required_terms: set[str],
    report_denominator: dict[str, Any],
    source_denominator: dict[str, Any],
) -> dict[str, Any]:
    matched = {
        term for term in required_terms if term.casefold() in source_text.casefold()
    }
    support = "direct_support" if matched == required_terms else "partial_support" if matched else "does_not_support"
    broad_language = bool(
        re.search(
            r"(?:所有|必然|行业标准|普遍|越.{0,24}越|保证传输|all|always|industry-wide)",
            report_claim,
            re.I,
        )
    )
    if broad_language and support == "direct_support":
        support = "partial_support"
    denominator_gap = bool(source_denominator) and not report_denominator
    transformation = (
        "scope_broadened"
        if broad_language or denominator_gap
        else "faithful_transcription"
        if support == "direct_support"
        else "bounded_summary"
        if support == "partial_support"
        else "cannot_determine"
    )
    return {
        "support_relationship": support,
        "scope_alignment": "misaligned" if transformation == "scope_broadened" else "aligned",
        "denominator_alignment": "missing_in_report" if denominator_gap else "aligned_or_not_applicable",
        "broker_report_transformation": transformation,
        "verification_reason": f"matched {len(matched)} of {len(required_terms)} required terms",
    }


def build_traceback_checkpoint(
    *,
    gate: dict[str, Any],
    authorization: dict[str, Any],
    reports: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    citations: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    acquired_sources: list[dict[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    terminal = Counter(row.get("terminal_status") for row in claims)
    er_counts = Counter(row.get("er_id") for row in claims if row.get("er_id"))
    specificity = Counter(row.get("citation_specificity") for row in citations)
    statuses = Counter(row.get("status") for row in attempts)
    core = {
        "execution_authorization_id": authorization["authorization_id"],
        "execution_authorization_hash": authorization["content_hash"],
        "traceback_gate_id": gate["decision_id"],
        "traceback_gate_hash": gate["content_hash"],
        "authorization_consumed": True,
        "authorized_target_ids": [row["traceback_target_id"] for row in authorization["authorized_targets"]],
        "processed_report_count": len(reports),
        "report_identity_resolved_count": sum(row.get("report_identity_status") == "resolved" for row in reports),
        "extracted_claim_count": len(claims),
        "a02_claim_count": er_counts.get("PCB-ER-A02", 0),
        "b01_claim_count": er_counts.get("PCB-ER-B01", 0),
        "b02_claim_count": er_counts.get("PCB-ER-B02", 0),
        "non_evidence_claim_count": sum(row.get("claim_class") in {"analyst_calculation", "analyst_inference", "industry_opinion", "investment_opinion"} for row in claims),
        "citation_count": len(citations),
        "exact_document_citation_count": specificity.get("exact_document", 0),
        "partial_identity_citation_count": specificity.get("partial_identity", 0),
        "generic_source_citation_count": specificity.get("generic_company_material", 0),
        "unattributed_claim_count": terminal.get("unattributed_claim", 0),
        "source_candidate_count": len(candidates),
        "unique_source_identity_count": len(candidates),
        "formal_attempt_count": len(attempts),
        "acquired_source_count": statuses.get("acquired", 0),
        "failed_source_count": statuses.get("failed", 0),
        "blocked_source_count": statuses.get("blocked", 0),
        "normalized_source_count": sum(row.get("normalization_status") == "normalized" for row in acquired_sources),
        "normalization_failure_count": sum(row.get("normalization_status") == "failed" for row in acquired_sources),
        "primary_source_confirmed_and_acquired_count": terminal.get("primary_source_confirmed_and_acquired", 0),
        "primary_source_confirmed_but_not_acquired_count": terminal.get("primary_source_confirmed_but_not_acquired", 0),
        "primary_source_candidate_found_count": terminal.get("primary_source_candidate_found", 0),
        "publisher_identity_confirmed_only_count": terminal.get("publisher_identity_confirmed_only", 0),
        "secondary_source_only_count": terminal.get("secondary_source_only", 0),
        "citation_unresolved_count": terminal.get("citation_present_but_unresolved", 0),
        "analyst_inference_count": terminal.get("analyst_inference", 0),
        "investment_opinion_count": terminal.get("investment_opinion_non_evidence", 0),
        "identity_mismatch_count": terminal.get("identity_mismatch", 0),
        "common_origin_groups": gate.get("common_origin_policy") or gate.get("common_origin_constraints") or [],
        "per_er_traceback_summary": dict(sorted(er_counts.items())),
        "future_assessment_candidate_count": sum(row.get("eligible_for_future_assessment_candidate") is True for row in acquired_sources),
        "security_policy_blocked_count": sum(row.get("failure_code") == "security_policy_blocked" for row in attempts),
        "security_violations": [],
        "scope_violations": [],
        "human_assistance_requested": False,
        "consolidated_assessment_started": False,
        "cognition_update_started": False,
        "company_mapping_started": False,
        "stage_a2_started": False,
        "stage_b_started": False,
        "created_at": created_at,
        "created_by": "Codex",
    }
    checkpoint_id = f"primary_source_traceback_checkpoint:{sha256(canonical_bytes(core)).hexdigest()[:24]}"
    payload = {"checkpoint_id": checkpoint_id, **core, "content_hash": ""}
    payload["content_hash"] = content_sha256(payload, excluded_paths={("content_hash",)})
    return payload


def validate_traceback_checkpoint(
    checkpoint: dict[str, Any], *, gate: dict[str, Any], authorization: dict[str, Any]
) -> dict[str, Any]:
    copied = deepcopy(checkpoint)
    _validate_hash(copied, label="Traceback checkpoint")
    if copied.get("traceback_gate_hash") != gate.get("content_hash"):
        raise _invalid("Traceback checkpoint Gate binding drifted")
    if copied.get("execution_authorization_hash") != authorization.get("content_hash"):
        raise _invalid("Traceback checkpoint authorization binding drifted")
    if copied.get("authorization_consumed") is not True:
        raise _invalid("Traceback authorization was not consumed")
    if copied.get("processed_report_count") != 5:
        raise _invalid("Traceback did not process exactly five reports")
    if copied.get("formal_attempt_count", 0) > 30:
        raise _invalid("Traceback acquisition attempt cap exceeded")
    if copied.get("human_assistance_requested") is not False:
        raise _invalid("Traceback requested prohibited human assistance")
    if any(
        copied.get(field) is not False
        for field in (
            "consolidated_assessment_started",
            "cognition_update_started",
            "company_mapping_started",
            "stage_a2_started",
            "stage_b_started",
        )
    ):
        raise _invalid("Traceback started a prohibited downstream stage")
    if copied.get("security_violations") or copied.get("scope_violations"):
        raise _invalid("Traceback checkpoint contains violations")
    return copied


def render_traceback_report(artifact: dict[str, Any]) -> str:
    summary = artifact.get("checkpoint_summary") or {}
    terminal_counts = Counter(row.get("terminal_status") for row in artifact.get("claims") or [])
    er_counts = Counter(row.get("er_id") for row in artifact.get("claims") or [] if row.get("er_id"))
    lines = [
        "# AI PCB 研报技术陈述—原始来源自动追溯 v1",
        "",
        f"- Processed reports: {summary.get('processed_report_count', 0)}",
        f"- Extracted claims: {summary.get('extracted_claim_count', len(artifact.get('claims') or []))}",
        f"- Source candidates: {summary.get('source_candidate_count', len(artifact.get('source_candidates') or []))}",
        "- Direct ER evidence admission: no",
        "- Consolidated Assessment started: no",
        "- Human assistance requested: no",
        "",
        "## Scope",
        "",
        "The broker reports remain source-discovery artifacts. Traceback results identify and qualify possible original sources without changing any ER status.",
        "",
        "## Report identities",
        "",
    ]
    for row in sorted(artifact.get("report_identities") or [], key=lambda item: item["traceback_target_id"]):
        lines.append(
            f"- `{row['traceback_target_id']}` — {row['report_title']} / "
            f"{row['broker_or_research_institution']} / {row['publication_date_status']}"
        )
    lines.extend(["", "## Claim distribution", ""])
    for er_id in sorted(er_counts):
        lines.append(f"- {er_id}: {er_counts[er_id]}")
    lines.append(f"- non-evidence: {summary.get('non_evidence_claim_count', 0)}")
    lines.extend(["", "## Traceback terminal states", ""])
    for status in sorted(status for status in terminal_counts if status):
        lines.append(f"- {status}: {terminal_counts[status]}")
    lines.extend(["", "## Acquired primary-source candidates", ""])
    for row in sorted(artifact.get("acquired_sources") or [], key=lambda item: item["source_candidate_id"]):
        lines.append(
            f"- `{row['source_candidate_id']}` — {row.get('source_title')} — "
            f"future assessment candidate: {'yes' if row.get('eligible_for_future_assessment_candidate') else 'no'}"
        )
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            "- Broker opinions, analyst calculations, and investment recommendations remain non-evidence.",
            "- Publisher or metadata identity alone does not provide technical support.",
            "- Newly acquired sources are not admitted to Evidence Assessment and do not change ER status.",
            "- Unresolved citations are valid terminal states; no human assistance was requested.",
            "",
        ]
    )
    return "\n".join(lines)
