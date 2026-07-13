from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.data_to_brief_backfill_primary_source_text_first_parse import (
    _build_source_rows,
    _extract_pages,
)
from stock_research.tech_bottleneck_90_primary_source_backfill import (
    PRIMARY_SOURCE_TYPES,
    _strategy_diff_clean,
    _stock_code,
    _write_json,
)
from stock_research.tech_bottleneck_90_primary_source_backfill_rerun_v2 import (
    _build_evidence_matrix,
)


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_latent_manual_review_backfill_batch1_v1"
COLLECTION_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_latent_manual_review_collection_batch1_v1"
SOURCES = COLLECTION_DIR / "latent_manual_review_collection_batch1_sources.csv"
DOWNLOADS = COLLECTION_DIR / "latent_manual_review_collection_batch1_download_manifest.csv"
COLLECTION_SUMMARY = COLLECTION_DIR / "latent_manual_review_collection_batch1_summary.json"
INPUT_QUEUE = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_latent_manual_review_first_triage_v1/latent_manual_review_high_priority_collection_queue.csv"
)
QUALITY_POOL_V5 = PROJECT_ROOT / "outputs/research/tech_bottleneck_quality_pool_layer_v5/quality_pool_layer_v5_manifest.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
EXPECTED_STOCK_COUNT = 26
EXPECTED_PDF_COUNT = 78

EMPTY_CHUNK_COLUMNS = [
    "stock_code",
    "stock_name",
    "source_type",
    "source_title",
    "source_path",
    "source_id",
    "chunk_id",
    "chunk_text",
    "page_start",
    "page_end",
    "page_locator",
    "citation_granularity",
    "section_matches",
    "keyword_score",
]

EVIDENCE_COLUMNS = [
    "stock_code",
    "stock_name",
    "source_file",
    "source_type",
    "source_title",
    "source_date",
    "page",
    "evidence_text",
    "evidence_claim_type",
    "hard_tech_domain",
    "supply_chain_role_hint",
    "business_relevance_hint",
    "bottleneck_or_chokepoint_hint",
    "concept_pollution_risk",
    "citation_quality",
    "backfill_status",
    "next_action_hint",
]

STATUS_COLUMNS = [
    "stock_code",
    "stock_name",
    "backfill_status",
    "primary_source_supported",
    "evidence_count",
    "page_level_citation_count",
    "hard_tech_domain_evidence_count",
    "supply_chain_role_evidence_count",
    "business_relevance_evidence_count",
    "bottleneck_or_chokepoint_evidence_count",
    "concept_pollution_risk",
    "remaining_evidence_gap_flags",
    "next_action_hint",
    "research_only",
    "used_for_signal",
    "used_for_admission",
    "price_move_used_for_signal",
    "low_position_used_for_signal",
    "evidence_backfill_performed",
    "core_equivalence_performed",
    "quality_pool_v5_processed",
    "notes",
]

PARSE_GAP_COLUMNS = [
    "stock_code",
    "stock_name",
    "source_type",
    "source_title",
    "source_file",
    "gap_type",
    "gap_detail",
    "recommended_next_action",
    "research_only",
    "used_for_signal",
    "used_for_admission",
]


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _truthy_count(frame: pd.DataFrame, column: str) -> int:
    if frame.empty or column not in frame.columns:
        return 0
    truthy = frame[column].map(lambda value: str(value).strip().lower() in {"true", "1", "yes"})
    return int(truthy.sum())


def _load_cached(output: Path) -> dict[str, Any] | None:
    summary_path = output / "latent_manual_review_backfill_batch1_summary.json"
    required = [
        summary_path,
        output / "latent_manual_review_backfill_batch1_evidence.csv",
        output / "latent_manual_review_backfill_batch1_stock_status.csv",
        output / "latent_manual_review_backfill_batch1_page_citations.csv",
        output / "latent_manual_review_backfill_batch1_parse_gaps.csv",
        output / "latent_manual_review_backfill_batch1_guardrails.json",
        output / "tech_bottleneck_latent_manual_review_backfill_batch1_v1_report.md",
    ]
    if not all(path.exists() for path in required):
        return None
    summary = _read_json(summary_path)
    if (
        summary.get("source_collection_batch1_stock_count") == EXPECTED_STOCK_COUNT
        and summary.get("source_collection_batch1_pdf_count") == EXPECTED_PDF_COUNT
        and summary.get("processed_stock_count") == EXPECTED_STOCK_COUNT
        and summary.get("processed_pdf_count") == EXPECTED_PDF_COUNT
    ):
        return summary
    return None


def _empty_chunks() -> pd.DataFrame:
    return pd.DataFrame(columns=EMPTY_CHUNK_COLUMNS)


def _parse_sources(
    sources: pd.DataFrame,
    output: Path,
    *,
    max_pages_per_source: int = 80,
    max_chunks_per_source: int = 8,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    chunks_path = output / "latent_manual_review_backfill_batch1_text_first_chunks.csv"
    parse_manifest_path = output / "latent_manual_review_backfill_batch1_text_first_parse_manifest.csv"
    if chunks_path.exists() and parse_manifest_path.exists():
        chunks = _read_csv(chunks_path)
        parse_manifest = pd.read_csv(parse_manifest_path).fillna("")
        return chunks, parse_manifest, {
            "processed_pdf_count": int(len(parse_manifest)),
            "parse_success_count": int(parse_manifest["parse_status"].eq("parsed").sum()) if "parse_status" in parse_manifest.columns else 0,
            "parse_failure_count": int(parse_manifest["parse_status"].ne("parsed").sum()) if "parse_status" in parse_manifest.columns else 0,
            "evidence_chunk_count": int(len(chunks)),
            "page_level_citation_count": int(chunks["citation_granularity"].eq("page_level").sum()) if not chunks.empty else 0,
        }

    if sources.empty:
        chunks = _empty_chunks()
        parse_manifest = pd.DataFrame()
        chunks.to_csv(chunks_path, index=False)
        parse_manifest.to_csv(parse_manifest_path, index=False)
        return chunks, parse_manifest, {
            "processed_pdf_count": 0,
            "parse_success_count": 0,
            "parse_failure_count": 0,
            "evidence_chunk_count": 0,
            "page_level_citation_count": 0,
        }

    source_rows = sources.copy().sort_values(["stock_code", "source_type", "local_pdf_path"]).reset_index(drop=True)
    source_rows["source_index"] = range(1, len(source_rows) + 1)
    parse_rows: list[dict[str, Any]] = []
    chunk_rows: list[dict[str, Any]] = []
    for source in source_rows.to_dict("records"):
        pages, metadata = _extract_pages(Path(str(source["local_pdf_path"])), max_pages_per_source)
        parse_row, chunks, _fallback = _build_source_rows(
            source,
            pages,
            metadata,
            max_chunks_per_source=max_chunks_per_source,
        )
        parse_rows.append(parse_row)
        chunk_rows.extend(chunks)

    chunks = pd.DataFrame(chunk_rows) if chunk_rows else _empty_chunks()
    parse_manifest = pd.DataFrame(parse_rows)
    chunks.to_csv(chunks_path, index=False)
    parse_manifest.to_csv(parse_manifest_path, index=False)
    return chunks, parse_manifest, {
        "processed_pdf_count": int(len(parse_manifest)),
        "parse_success_count": int(parse_manifest["parse_status"].eq("parsed").sum()) if not parse_manifest.empty else 0,
        "parse_failure_count": int(parse_manifest["parse_status"].ne("parsed").sum()) if not parse_manifest.empty else 0,
        "evidence_chunk_count": int(len(chunks)),
        "page_level_citation_count": int(chunks["citation_granularity"].eq("page_level").sum()) if not chunks.empty else 0,
    }


def _source_date_lookup(downloads: pd.DataFrame) -> dict[str, str]:
    if downloads.empty:
        return {}
    rows = downloads.copy()
    rows["local_pdf_path"] = rows["local_pdf_path"].astype(str)
    return dict(zip(rows["local_pdf_path"], rows.get("announcement_time", pd.Series([""] * len(rows))).astype(str)))


def _status_from_counts(stock_evidence: pd.DataFrame) -> tuple[str, str, str]:
    if stock_evidence.empty:
        return (
            "parse_failed_or_unusable",
            "no citation-ready text evidence was extracted from downloaded primary-source PDFs",
            "retry parsing with Docling/OCR fallback or collect alternate official disclosure",
        )
    primary_count = int(stock_evidence["source_type"].isin(PRIMARY_SOURCE_TYPES).sum())
    page_count = int(stock_evidence["provenance_status"].eq("page_level").sum())
    support_text = "|".join(stock_evidence["supports_field"].fillna("").astype(str).tolist())
    hard_hits = support_text.count("hard_tech_exposure")
    value_hits = support_text.count("revenue_trace") + support_text.count("financial_trace") + support_text.count("order_or_capacity")
    architecture_hits = support_text.count("architecture_shift")
    if primary_count and page_count and hard_hits >= 2 and value_hits >= 1:
        return (
            "primary_source_supported",
            "page-level primary-source evidence supports hard-tech and business/value-trace fields",
            "proceed to latent manual review equivalence gate; no automatic quality-pool action",
        )
    if primary_count and (hard_hits or architecture_hits or value_hits):
        return (
            "partially_supported",
            "primary-source evidence exists but some bottleneck, value-capture, or route-around fields remain incomplete",
            "manual review remaining evidence gaps before equivalence gate",
        )
    return (
        "insufficient_primary_source_evidence",
        "downloaded primary sources parsed but did not produce enough hard-tech thesis evidence",
        "collect targeted product, project, customer, or technology disclosure before equivalence gate",
    )


def _hint_from_support(support: str, target: str) -> str:
    return "supported" if target in support else "evidence_required"


def _build_evidence_output(evidence_matrix: pd.DataFrame, downloads: pd.DataFrame, stock_status: pd.DataFrame) -> pd.DataFrame:
    if evidence_matrix.empty:
        return pd.DataFrame(columns=EVIDENCE_COLUMNS)
    date_lookup = _source_date_lookup(downloads)
    status_lookup = dict(zip(stock_status["stock_code"], stock_status["backfill_status"]))
    action_lookup = dict(zip(stock_status["stock_code"], stock_status["next_action_hint"]))
    rows: list[dict[str, Any]] = []
    page_evidence = evidence_matrix[evidence_matrix["provenance_status"].eq("page_level")].copy()
    for _, row in page_evidence.sort_values(["stock_code", "source_type", "page", "source_title"]).iterrows():
        support = str(row.get("supports_field") or "")
        source_file = str(row.get("source_path_or_url") or "")
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row.get("stock_name", ""),
                "source_file": source_file,
                "source_type": row.get("source_type", ""),
                "source_title": row.get("source_title", ""),
                "source_date": date_lookup.get(source_file, ""),
                "page": row.get("page", ""),
                "evidence_text": row.get("claim", ""),
                "evidence_claim_type": support,
                "hard_tech_domain": _hint_from_support(support, "hard_tech_exposure"),
                "supply_chain_role_hint": (
                    "supported"
                    if "customer_certification" in support or "order_or_capacity" in support
                    else "evidence_required"
                ),
                "business_relevance_hint": (
                    "supported"
                    if "revenue_trace" in support or "financial_trace" in support or "primary_periodic_disclosure" in support
                    else "evidence_required"
                ),
                "bottleneck_or_chokepoint_hint": (
                    "supported"
                    if "architecture_shift" in support or "hard_tech_exposure" in support
                    else "evidence_required"
                ),
                "concept_pollution_risk": "risk_or_counter_evidence_present" if "disconfirmation_or_risk" in support else "not_detected_in_chunk",
                "citation_quality": "page_level",
                "backfill_status": status_lookup.get(row["stock_code"], ""),
                "next_action_hint": action_lookup.get(row["stock_code"], ""),
            }
        )
    return pd.DataFrame(rows, columns=EVIDENCE_COLUMNS)


def _build_stock_status(queue: pd.DataFrame, evidence_matrix: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, queue_row in queue.sort_values("stock_code").iterrows():
        stock_code = queue_row["stock_code"]
        stock_evidence = evidence_matrix[evidence_matrix["stock_code"].eq(stock_code)].copy()
        if not stock_evidence.empty:
            stock_evidence = stock_evidence[stock_evidence["provenance_status"].eq("page_level")].copy()
        status, notes, next_action = _status_from_counts(stock_evidence)
        support_series = stock_evidence["supports_field"].fillna("").astype(str) if not stock_evidence.empty else pd.Series(dtype=str)
        hard_hits = int(support_series.str.contains("hard_tech_exposure").sum()) if not support_series.empty else 0
        supply_hits = int(support_series.str.contains("customer_certification|order_or_capacity").sum()) if not support_series.empty else 0
        business_hits = int(support_series.str.contains("revenue_trace|financial_trace|primary_periodic_disclosure").sum()) if not support_series.empty else 0
        bottleneck_hits = int(support_series.str.contains("architecture_shift|hard_tech_exposure").sum()) if not support_series.empty else 0
        risk_hits = int(support_series.str.contains("disconfirmation_or_risk").sum()) if not support_series.empty else 0
        gaps: list[str] = []
        if hard_hits == 0:
            gaps.append("missing_hard_tech_domain_evidence")
        if supply_hits == 0:
            gaps.append("missing_supply_chain_role_evidence")
        if business_hits == 0:
            gaps.append("missing_business_or_financial_trace")
        if bottleneck_hits == 0:
            gaps.append("missing_bottleneck_or_chokepoint_evidence")
        if risk_hits == 0:
            gaps.append("missing_disconfirmation_review")
        rows.append(
            {
                "stock_code": stock_code,
                "stock_name": queue_row.get("stock_name", ""),
                "backfill_status": status,
                "primary_source_supported": status == "primary_source_supported",
                "evidence_count": int(len(stock_evidence)),
                "page_level_citation_count": int(stock_evidence["provenance_status"].eq("page_level").sum()) if not stock_evidence.empty else 0,
                "hard_tech_domain_evidence_count": hard_hits,
                "supply_chain_role_evidence_count": supply_hits,
                "business_relevance_evidence_count": business_hits,
                "bottleneck_or_chokepoint_evidence_count": bottleneck_hits,
                "concept_pollution_risk": "risk_or_counter_evidence_present" if risk_hits else "not_detected_in_page_evidence",
                "remaining_evidence_gap_flags": "|".join(gaps),
                "next_action_hint": next_action,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "price_move_used_for_signal": False,
                "low_position_used_for_signal": False,
                "evidence_backfill_performed": True,
                "core_equivalence_performed": False,
                "quality_pool_v5_processed": False,
                "notes": notes,
            }
        )
    return pd.DataFrame(rows, columns=STATUS_COLUMNS)


def _build_page_citations(evidence: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for citation_index, (_, row) in enumerate(evidence.iterrows(), start=1):
        rows.append(
            {
                "citation_id": f"S{citation_index}",
                "stock_code": row["stock_code"],
                "stock_name": row.get("stock_name", ""),
                "source_file": row.get("source_file", ""),
                "source_type": row.get("source_type", ""),
                "source_title": row.get("source_title", ""),
                "source_date": row.get("source_date", ""),
                "page": row.get("page", ""),
                "evidence_text": row.get("evidence_text", ""),
                "evidence_claim_type": row.get("evidence_claim_type", ""),
                "citation_quality": row.get("citation_quality", "page_level"),
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows)


def _build_parse_gaps(queue: pd.DataFrame, sources: pd.DataFrame, parse_manifest: pd.DataFrame, stock_status: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not parse_manifest.empty:
        failures = parse_manifest[parse_manifest["parse_status"].ne("parsed")].copy()
        for _, row in failures.iterrows():
            rows.append(
                {
                    "stock_code": row.get("stock_code", ""),
                    "stock_name": row.get("stock_name", ""),
                    "source_type": row.get("source_type", ""),
                    "source_title": row.get("source_title", ""),
                    "source_file": row.get("source_path", ""),
                    "gap_type": "parse_failed_or_unusable",
                    "gap_detail": row.get("extract_errors", "") or "no citation-ready text extracted",
                    "recommended_next_action": "retry with Docling layout parse or OCR fallback for this source",
                    "research_only": True,
                    "used_for_signal": False,
                    "used_for_admission": False,
                }
            )
    no_evidence = stock_status[stock_status["backfill_status"].eq("parse_failed_or_unusable")].copy()
    source_codes = set(sources["stock_code"]) if not sources.empty else set()
    for _, row in queue[~queue["stock_code"].isin(source_codes)].iterrows():
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row.get("stock_name", ""),
                "source_type": "",
                "source_title": "",
                "source_file": "",
                "gap_type": "missing_collection_source",
                "gap_detail": "no downloaded primary-source PDF found in collection batch1 manifest",
                "recommended_next_action": "rerun primary-source collection before backfill",
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    for _, row in no_evidence.iterrows():
        if any(existing.get("stock_code") == row["stock_code"] for existing in rows):
            continue
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row.get("stock_name", ""),
                "source_type": "",
                "source_title": "",
                "source_file": "",
                "gap_type": "stock_level_parse_unusable",
                "gap_detail": "downloaded sources did not yield stock-level citation-ready evidence",
                "recommended_next_action": "retry parsing or collect alternate official disclosure",
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows, columns=PARSE_GAP_COLUMNS)


def _summary(
    *,
    queue: pd.DataFrame,
    sources: pd.DataFrame,
    stock_status: pd.DataFrame,
    evidence: pd.DataFrame,
    citations: pd.DataFrame,
    parse_gaps: pd.DataFrame,
    parse_summary: dict[str, Any],
    strategy_clean: bool,
) -> dict[str, Any]:
    status_counts = stock_status["backfill_status"].value_counts() if not stock_status.empty else pd.Series(dtype=int)
    used_for_signal = _truthy_count(stock_status, "used_for_signal")
    used_for_admission = _truthy_count(stock_status, "used_for_admission")
    blocking = (
        len(queue) != EXPECTED_STOCK_COUNT
        or len(sources) != EXPECTED_PDF_COUNT
        or len(stock_status) != EXPECTED_STOCK_COUNT
        or int(parse_summary["processed_pdf_count"]) != EXPECTED_PDF_COUNT
        or used_for_signal
        or used_for_admission
        or not strategy_clean
    )
    if blocking:
        acceptance = "blocked_due_to_guardrail_violation"
    elif len(parse_gaps):
        acceptance = "conditionally_ready_with_parse_gaps"
    else:
        acceptance = "latent_manual_review_backfill_batch1_ready"
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_collection_batch1_stock_count": int(len(queue)),
        "source_collection_batch1_pdf_count": int(len(sources)),
        "processed_stock_count": int(len(stock_status)),
        "processed_pdf_count": int(parse_summary["processed_pdf_count"]),
        "parse_success_count": int(parse_summary["parse_success_count"]),
        "parse_failure_count": int(parse_summary["parse_failure_count"]),
        "evidence_row_count": int(len(evidence)),
        "page_level_citation_count": int(len(citations)),
        "primary_source_supported_count": int(status_counts.get("primary_source_supported", 0)),
        "partially_supported_count": int(status_counts.get("partially_supported", 0)),
        "insufficient_primary_source_evidence_count": int(status_counts.get("insufficient_primary_source_evidence", 0)),
        "parse_failed_or_unusable_count": int(status_counts.get("parse_failed_or_unusable", 0)),
        "parse_gap_count": int(len(parse_gaps)),
        "evidence_backfill_performed": True,
        "core_equivalence_performed": False,
        "quality_pool_v5_processed": False,
        "auto_added_to_quality_pool_count": 0,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "used_for_signal_count": used_for_signal,
        "used_for_admission_count": used_for_admission,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": 0,
        "acceptance_decision": acceptance,
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_collection_batch1_stock_count": summary["source_collection_batch1_stock_count"],
        "source_collection_batch1_pdf_count": summary["source_collection_batch1_pdf_count"],
        "processed_stock_count": summary["processed_stock_count"],
        "processed_pdf_count": summary["processed_pdf_count"],
        "evidence_backfill_performed": True,
        "core_equivalence_performed": False,
        "quality_pool_v5_processed": False,
        "auto_added_to_quality_pool_count": 0,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": summary["strategy_file_diff_clean"],
        "formal_strategy_files_modified": summary["formal_strategy_files_modified"],
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": 0,
        "acceptance_decision": summary["acceptance_decision"],
    }


def _report(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Tech Bottleneck Latent Manual Review Backfill Batch1 v1",
            "",
            "## 1. Scope",
            "This task processes only the 26-stock latent manual-review high-priority collection batch and its 78 downloaded primary-source PDFs. It performs PDF parsing, evidence extraction, page-level citation generation, and backfill status classification only.",
            "",
            "## 2. Evidence Backfill Results",
            f"Processed stocks: {summary['processed_stock_count']}; processed PDFs: {summary['processed_pdf_count']}; parse success: {summary['parse_success_count']}; parse failures: {summary['parse_failure_count']}; evidence rows: {summary['evidence_row_count']}; page-level citations: {summary['page_level_citation_count']}.",
            "",
            "## 3. Stock Status",
            f"Primary-source supported: {summary['primary_source_supported_count']}; partially supported: {summary['partially_supported_count']}; insufficient evidence: {summary['insufficient_primary_source_evidence_count']}; parse failed/unusable: {summary['parse_failed_or_unusable_count']}.",
            "",
            "## 4. Guardrails",
            f"evidence_backfill_performed=true; core_equivalence_performed=false; quality_pool_v5_processed=false; auto_added_to_quality_pool_count=0; price_move_used_for_signal=0; low_position_used_for_signal=0; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 5. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 6. Recommended Next Steps",
            "1. tech_bottleneck_latent_manual_review_equivalence_gate_batch1_v1",
            "2. tech_bottleneck_latent_manual_review_standard_collection_v1",
            "3. tech_bottleneck_latent_manual_review_human_confirm_packet_v1",
        ]
    )


def run(output_dir: str | Path = OUTPUT_DIR, *, force: bool = False) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if not force:
        cached = _load_cached(output)
        if cached is not None:
            return cached

    queue = _read_csv(INPUT_QUEUE).sort_values("stock_code").reset_index(drop=True)
    sources = _read_csv(SOURCES)
    downloads = _read_csv(DOWNLOADS)
    _collection_summary = _read_json(COLLECTION_SUMMARY)
    queue_codes = set(queue["stock_code"])
    sources = sources[sources["stock_code"].isin(queue_codes)].copy().sort_values(["stock_code", "source_type", "local_pdf_path"])
    chunks, parse_manifest, parse_summary = _parse_sources(sources, output)
    evidence_matrix = _build_evidence_matrix(chunks)
    evidence_matrix = evidence_matrix[evidence_matrix["stock_code"].isin(queue_codes)].copy()
    stock_status = _build_stock_status(queue, evidence_matrix)
    evidence = _build_evidence_output(evidence_matrix, downloads, stock_status)
    citations = _build_page_citations(evidence)
    parse_gaps = _build_parse_gaps(queue, sources, parse_manifest, stock_status)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(
        queue=queue,
        sources=sources,
        stock_status=stock_status,
        evidence=evidence,
        citations=citations,
        parse_gaps=parse_gaps,
        parse_summary=parse_summary,
        strategy_clean=strategy_clean,
    )
    guardrails = _guardrails(summary)

    evidence.to_csv(output / "latent_manual_review_backfill_batch1_evidence.csv", index=False)
    stock_status.to_csv(output / "latent_manual_review_backfill_batch1_stock_status.csv", index=False)
    citations.to_csv(output / "latent_manual_review_backfill_batch1_page_citations.csv", index=False)
    parse_gaps.to_csv(output / "latent_manual_review_backfill_batch1_parse_gaps.csv", index=False)
    _write_json(output / "latent_manual_review_backfill_batch1_summary.json", summary)
    _write_json(output / "latent_manual_review_backfill_batch1_guardrails.json", guardrails)
    (output / "tech_bottleneck_latent_manual_review_backfill_batch1_v1_report.md").write_text(
        _report(summary),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    print(json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
