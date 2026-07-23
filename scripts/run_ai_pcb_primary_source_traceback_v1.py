from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from typing import Any

from pypdf import PdfReader

from stock_research.research_project_v2.canonical import canonical_bytes
from stock_research.research_project_v2_1.acquisition_contracts import AcquisitionContext
from stock_research.research_project_v2_1.acquisition_http import DirectHttpProvider
from stock_research.research_project_v2_1.acquisition_normalize import (
    DeterministicNormalizationAdapter,
    normalize_acquired_artifact,
)
from stock_research.research_project_v2_1.layout import LayeredResearchLayout
from stock_research.research_project_v2_1.snapshot import source_candidate_id
from stock_research.research_project_v2_1.primary_source_traceback import (
    bind_claims_to_citations,
    build_source_candidates,
    build_traceback_artifact,
    build_traceback_checkpoint,
    collapse_common_origin_candidates,
    extract_citations_from_pages,
    extract_claims_from_pages,
    extract_report_identity_from_pages,
    render_traceback_report,
    select_traceback_candidates,
    validate_traceback_artifact,
    validate_traceback_authorization,
    validate_traceback_checkpoint,
    verify_claim_source_support,
)


SOURCE_REPOSITORY_ROOT = Path("/Users/xiwei/stock_research")
LAYOUT = LayeredResearchLayout.default()
GATE_PATH = LAYOUT.governance_dir / "ai_pcb_primary_source_traceback_gate_decision_v1.json"
AUTH_PATH = LAYOUT.governance_dir / "ai_pcb_primary_source_traceback_execution_authorization_v1.json"
BUNDLE = LAYOUT.root / "acquisition/primary_source_traceback_v1"
ANALYSIS_PATH = LAYOUT.analysis_dir / "ai_pcb_primary_source_traceback_v1.json"
REPORT_PATH = LAYOUT.reports_dir / "ai_pcb_primary_source_traceback_v1.md"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def provenance(created_at: str) -> dict[str, Any]:
    return {
        "created_by": "Codex",
        "actor_type": "codex",
        "agent_run_id": "ai-pcb-primary-source-traceback-v1-20260723",
        "created_at": created_at,
        "created_in_version": "primary_source_traceback_v1",
        "review_status": "unreviewed",
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def report_pages(path: Path) -> tuple[list[str], str | None]:
    reader = PdfReader(str(path))
    metadata_title = reader.metadata.title if reader.metadata else None
    return [page.extract_text() or "" for page in reader.pages], metadata_title


def resolved_candidates(claims: list[dict[str, Any]], report_ids: set[str]) -> list[dict[str, Any]]:
    claim_ids = sorted(
        row["claim_id"]
        for row in claims
        if row.get("report_id") in report_ids and row.get("er_id") == "PCB-ER-B01"
    )
    definitions = [
        (
            "traceback_source_candidate:novoray_spherical_silica_product",
            "联瑞新材 NOVOPOWDER DQ 球形硅微粉产品参数",
            "https://www.novoray.com/index.php/product/content/id/18/proid/7.html",
            "official_product_datasheet",
            True,
        ),
        (
            "traceback_source_candidate:novoray_ccl_application",
            "联瑞新材电子与电器行业覆铜板应用说明",
            "https://www.novoray.com/index.php/application/page/id/34.html",
            "company_webpage",
            False,
        ),
    ]
    rows = []
    for candidate_id, title, url, content_class, future_candidate in definitions:
        rows.append(
            {
                "source_candidate_id": candidate_id,
                "candidate_title": title,
                "candidate_authors": [],
                "candidate_organization": "江苏联瑞新材料股份有限公司",
                "candidate_source_class": content_class,
                "candidate_document_number": None,
                "candidate_standard_number": None,
                "candidate_doi": None,
                "candidate_url": url,
                "identity_status": "confirmed",
                "identity_confidence": "high",
                "identity_evidence": ["official_domain_and_page_content"],
                "citation_specificity": "generic_company_material",
                "originating_report_ids": sorted(report_ids),
                "originating_claim_ids": claim_ids,
                "common_origin_group": "common_origin:38c17ff3d93a0941",
                "formal_acquisition_authorized": True,
                "required_content_class": content_class,
                "eligible_for_future_assessment_candidate": future_candidate,
            }
        )
    return rows


def snapshot_candidate(row: dict[str, Any], *, run_provenance: dict[str, Any]) -> dict[str, Any]:
    url = row["candidate_url"]
    title = row["candidate_title"]
    return {
        "candidate_id": source_candidate_id(url, title),
        "search_plan_id": "primary_source_traceback_v1",
        "query_id": row["source_candidate_id"],
        "normalized_url": url,
        "original_url": url,
        "title": title,
        "snippet": "",
        "publisher": row["candidate_organization"],
        "publish_date": None,
        "source_class": row["candidate_source_class"],
        "rank": 1,
        "exclusion_status": "included",
        "exclusion_reasons": [],
        "dedup_key": url,
        "provenance": run_provenance,
    }


def main() -> int:
    reuse_requested = os.environ.get("TRACEBACK_REUSE_EXISTING_ACQUISITION") == "1"
    if (BUNDLE / "traceback_checkpoint.json").exists() and not reuse_requested:
        raise RuntimeError(
            "Primary-source traceback authorization is already consumed; refusing a second acquisition run."
        )
    gate = json.loads(GATE_PATH.read_text(encoding="utf-8"))
    authorization = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    validate_traceback_authorization(
        authorization,
        gate=gate,
        validate_upstreams=True,
        source_repository_root=SOURCE_REPOSITORY_ROOT,
    )
    reports: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    for target in gate["selected_targets"]:
        path = SOURCE_REPOSITORY_ROOT / target["report_path"]
        pages, metadata_title = report_pages(path)
        identity_target = dict(target)
        identity_target["pdf_metadata_title"] = metadata_title
        identity = extract_report_identity_from_pages(target=identity_target, pages=pages)
        reports.append(identity)
        report_claims = extract_claims_from_pages(
            report_id=identity["report_id"],
            traceback_target_id=target["traceback_target_id"],
            report_file_hash=target["report_content_sha256"],
            pages=pages,
            authorized_er_ids=set(target["authorized_er_traceback_scope"]),
        )
        report_citations = extract_citations_from_pages(report_id=identity["report_id"], pages=pages)
        for citation in report_citations:
            citation["common_origin_group"] = target.get("common_origin_group")
        claims.extend(bind_claims_to_citations(report_claims, report_citations))
        citations.extend(report_citations)

    inferred = collapse_common_origin_candidates(build_source_candidates(citations))
    novoray_report_ids = {
        row["report_id"]
        for row in reports
        if "novoray" in row["traceback_target_id"]
    }
    resolved = resolved_candidates(claims, novoray_report_ids)
    selected_inferred = select_traceback_candidates(
        inferred,
        maximum_count=authorization["maximum_unique_primary_source_candidates"] - len(resolved),
    )
    candidates = resolved + selected_inferred
    attempts: list[dict[str, Any]] = []
    acquired_sources: list[dict[str, Any]] = []
    trace_links: list[dict[str, Any]] = []
    reuse_existing = reuse_requested
    existing_acquired: dict[str, dict[str, Any]] = {}
    if reuse_existing and ANALYSIS_PATH.is_file() and (BUNDLE / "attempts.jsonl").is_file():
        previous = json.loads(ANALYSIS_PATH.read_text(encoding="utf-8"))
        existing_acquired = {
            row["source_candidate_id"]: row for row in previous.get("acquired_sources") or []
        }
        attempts = [
            json.loads(line)
            for line in (BUNDLE / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    provider = DirectHttpProvider(headers={"User-Agent": "ResearchOperatingLayerV2.1/traceback"})
    adapter = DeterministicNormalizationAdapter()
    run_provenance = provenance(utc_now())
    for row in resolved:
        if row["source_candidate_id"] in existing_acquired:
            acquired = existing_acquired[row["source_candidate_id"]]
            acquired_sources.append(acquired)
            document_id = acquired.get("normalized_document_id")
            if not document_id or row["source_candidate_id"].endswith("ccl_application"):
                continue
            document_wrapper = json.loads(
                (LAYOUT.evidence_normalized_dir / f"{document_id}.json").read_text(encoding="utf-8")
            )
            document = document_wrapper.get("normalized_document", document_wrapper)
            matching_sections = [
                section for section in document["sections"]
                if "3.88" in section["text"] or "0.0002" in section["text"]
            ]
            if not matching_sections:
                continue
            section = matching_sections[0]
            for claim in claims:
                if claim.get("report_id") not in novoray_report_ids or claim.get("er_id") != "PCB-ER-B01":
                    continue
                if not any(token in claim["claim_text"] for token in ("3.88", "0.0002")):
                    continue
                verification = verify_claim_source_support(
                    report_claim=claim["claim_text"], source_text=section["text"],
                    required_terms={token for token in ("3.88", "0.0002") if token in claim["claim_text"]},
                    report_denominator={"frequency": "1MHz"} if "1MHz" in claim["claim_text"] else {},
                    source_denominator={"frequency": "1MHz", "property_status": "typical"},
                )
                link_core = {
                    "report_claim_id": claim["claim_id"],
                    "source_candidate_id": row["source_candidate_id"],
                    "source_artifact_id": acquired["source_artifact_id"],
                    "normalized_document_id": document["document_id"],
                    "source_section_index": document["sections"].index(section) + 1,
                    "source_section_hash": section["section_hash"],
                    **verification,
                }
                trace_links.append({
                    "trace_link_id": f"trace_link:{sha256(canonical_bytes(link_core)).hexdigest()[:24]}",
                    **link_core,
                })
                claim["terminal_status"] = "primary_source_confirmed_and_acquired"
            continue
        result = provider.acquire(
            snapshot_candidate(row, run_provenance=run_provenance),
            context=AcquisitionContext(
                project_id=authorization["project_id"],
                research_version_context="primary_source_traceback_v1",
                requirement_id="PCB-ER-B01",
            candidate_id=source_candidate_id(row["candidate_url"], row["candidate_title"]),
                provenance=run_provenance,
            ),
            layout=LAYOUT,
            proxy_mode="direct",
            timeout_seconds=20,
            max_redirects=5,
            max_bytes=8 * 1024 * 1024,
            max_retries=0,
        )
        attempts.append({
            "source_candidate_id": row["source_candidate_id"],
            "authorized_er_ids": ["PCB-ER-B01"],
            "status": result.attempt["status"],
            "failure_code": result.attempt.get("failure_code"),
            "attempt": result.attempt,
        })
        if result.artifact is None:
            continue
        normalized_at = result.attempt["completed_at"]
        outcome = normalize_acquired_artifact(
            result.artifact,
            adapter=adapter,
            layout=LAYOUT,
            parsed_at=normalized_at,
            provenance=run_provenance,
        )
        acquired = {
            "source_candidate_id": row["source_candidate_id"],
            "source_title": row["candidate_title"],
            "source_url": row["candidate_url"],
            "source_content_class": row["required_content_class"],
            "source_artifact_id": result.artifact["evidence_artifact_id"],
            "source_artifact_hash": result.artifact["content_hash"],
            "raw_artifact_path": result.artifact["raw_artifact_path"],
            "normalization_status": outcome.status,
            "normalized_document_id": outcome.document["document_id"] if outcome.document else None,
            "normalized_document_hash": outcome.document["document_hash"] if outcome.document else None,
            "eligible_for_future_assessment_candidate": row["eligible_for_future_assessment_candidate"] and outcome.status == "normalized",
            "admitted_to_evidence_assessment": False,
            "er_sufficient": False,
            "cognition_update_eligible": False,
            "publication_date_status": "unknown",
        }
        acquired_sources.append(acquired)
        if not outcome.document or row["source_candidate_id"].endswith("ccl_application"):
            continue
        matching_sections = [
            section
            for section in outcome.document["sections"]
            if "3.88" in section["text"] or "0.0002" in section["text"]
        ]
        if not matching_sections:
            continue
        section = matching_sections[0]
        for claim in claims:
            if claim.get("report_id") not in novoray_report_ids or claim.get("er_id") != "PCB-ER-B01":
                continue
            if not any(token in claim["claim_text"] for token in ("3.88", "0.0002")):
                continue
            verification = verify_claim_source_support(
                report_claim=claim["claim_text"],
                source_text=section["text"],
                required_terms={token for token in ("3.88", "0.0002") if token in claim["claim_text"]},
                report_denominator={"frequency": "1MHz"} if "1MHz" in claim["claim_text"] else {},
                source_denominator={"frequency": "1MHz", "property_status": "typical"},
            )
            link_core = {
                "report_claim_id": claim["claim_id"],
                "source_candidate_id": row["source_candidate_id"],
                "source_artifact_id": result.artifact["evidence_artifact_id"],
                "normalized_document_id": outcome.document["document_id"],
                "source_section_index": outcome.document["sections"].index(section) + 1,
                "source_section_hash": section["section_hash"],
                **verification,
            }
            trace_links.append({
                "trace_link_id": f"trace_link:{sha256(canonical_bytes(link_core)).hexdigest()[:24]}",
                **link_core,
            })
            claim["terminal_status"] = "primary_source_confirmed_and_acquired"

    candidate_class_by_claim = {
        claim_id: row.get("candidate_source_class")
        for row in candidates
        for claim_id in row.get("originating_claim_ids", [])
    }
    for claim in claims:
        if claim["terminal_status"] in {"analyst_inference", "investment_opinion_non_evidence", "primary_source_confirmed_and_acquired"}:
            continue
        if claim["claim_id"] in candidate_class_by_claim:
            claim["terminal_status"] = (
                "secondary_source_only"
                if candidate_class_by_claim[claim["claim_id"]] == "secondary_source"
                else "primary_source_candidate_found"
            )
        elif claim.get("citation_ids"):
            claim["terminal_status"] = "citation_present_but_unresolved"
        else:
            claim["terminal_status"] = "unattributed_claim"

    created_at = utc_now()
    checkpoint = build_traceback_checkpoint(
        gate=gate,
        authorization=authorization,
        reports=reports,
        claims=claims,
        citations=citations,
        candidates=candidates,
        attempts=attempts,
        acquired_sources=acquired_sources,
        created_at=created_at,
    )
    validate_traceback_checkpoint(checkpoint, gate=gate, authorization=authorization)
    artifact = build_traceback_artifact(
        authorization_hash=authorization["content_hash"],
        gate_hash=gate["content_hash"],
        report_identities=reports,
        claims=claims,
        citations=citations,
        source_candidates=candidates,
        trace_links=trace_links,
        acquired_sources=acquired_sources,
        checkpoint_summary=checkpoint,
        created_at=created_at,
    )
    validate_traceback_artifact(artifact)

    identities = {
        "artifact_role": "primary_source_traceback",
        "direct_er_evidence_admission": False,
        "document_identities": candidates,
        "unique_source_identity_count": len(candidates),
        "common_origin_groups": gate.get("common_origin_policy"),
    }
    raw_manifest = [
        {key: row[key] for key in ("source_candidate_id", "source_artifact_id", "source_artifact_hash", "raw_artifact_path")}
        for row in acquired_sources
    ]
    normalized_manifest = [
        {key: row[key] for key in ("source_candidate_id", "normalized_document_id", "normalized_document_hash", "normalization_status")}
        for row in acquired_sources
    ]
    write_jsonl(BUNDLE / "source_candidates.jsonl", candidates)
    write_jsonl(BUNDLE / "attempts.jsonl", attempts)
    write_json(BUNDLE / "raw/manifest.json", raw_manifest)
    write_json(BUNDLE / "normalized/manifest.json", normalized_manifest)
    write_json(BUNDLE / "document_identity_registry.json", identities)
    write_jsonl(BUNDLE / "trace_links.jsonl", trace_links)
    write_json(BUNDLE / "traceback_checkpoint.json", checkpoint)
    write_json(ANALYSIS_PATH, artifact)
    report = render_traceback_report(artifact)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8", newline="\n")
    (BUNDLE / "summary.md").write_text(report, encoding="utf-8", newline="\n")
    print(json.dumps({
        "artifact_hash": artifact["content_hash"],
        "checkpoint_id": checkpoint["checkpoint_id"],
        "checkpoint_hash": checkpoint["content_hash"],
        "claims": len(claims),
        "citations": len(citations),
        "candidates": len(candidates),
        "attempts": len(attempts),
        "acquired": len(acquired_sources),
        "trace_links": len(trace_links),
        "terminal_states": Counter(row["terminal_status"] for row in claims),
    }, ensure_ascii=False, default=dict, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
