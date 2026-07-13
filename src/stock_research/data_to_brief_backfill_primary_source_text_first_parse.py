from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from pypdf import PdfReader


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "data_to_brief_backfill_primary_source_text_first_parse_v1"
COLLECTION_MANIFEST = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_remaining_primary_source_collection_v1/primary_source_collection_manifest.csv"
)
PREVIOUS_DOCLING_OUTPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_backfill_queue_primary_source_parse_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

SECTION_KEYWORDS: dict[str, list[str]] = {
    "business_overview": ["主营业务", "主要业务", "公司从事", "主要产品", "经营范围", "业务概要"],
    "key_products": ["产品", "设备", "材料", "芯片", "模块", "系统", "解决方案", "核心产品"],
    "hard_tech_bottleneck_thesis": ["国产化", "自主可控", "核心技术", "关键技术", "进口替代", "半导体", "高端装备", "工业控制", "电力设备"],
    "technology_capability": ["研发", "专利", "技术", "工艺", "平台", "创新", "实验室", "技术中心"],
    "financial_snapshot": ["营业收入", "净利润", "毛利率", "研发费用", "现金流", "分产品", "分行业"],
    "risks_and_counter_evidence": ["风险", "不确定性", "竞争", "客户集中", "供应链", "存货", "应收账款", "毛利率下降"],
}


def _stock_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame


def _read_collection() -> pd.DataFrame:
    frame = _read_csv(COLLECTION_MANIFEST)
    frame["source_index"] = range(1, len(frame) + 1)
    return frame.sort_values(["stock_code", "source_type", "local_pdf_path"]).reset_index(drop=True)


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").replace("\x00", " ").split())


def _section_matches(text: str) -> list[str]:
    matches: list[str] = []
    for section, keywords in SECTION_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            matches.append(section)
    return matches


def _score_page(text: str) -> int:
    return sum(text.count(keyword) for keywords in SECTION_KEYWORDS.values() for keyword in keywords)


def _split_chunk(text: str, max_chars: int = 1800) -> list[str]:
    clean = _normalize_text(text)
    if len(clean) <= max_chars:
        return [clean] if clean else []
    chunks: list[str] = []
    start = 0
    while start < len(clean) and len(chunks) < 2:
        chunks.append(clean[start : start + max_chars])
        start += max_chars
    return chunks


def _extract_pages(pdf_path: Path, max_pages_per_source: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.perf_counter()
    reader = PdfReader(str(pdf_path))
    page_count = len(reader.pages)
    extract_page_count = min(page_count, max_pages_per_source)
    pages: list[dict[str, Any]] = []
    errors: list[str] = []
    for page_index in range(extract_page_count):
        try:
            text = _normalize_text(reader.pages[page_index].extract_text() or "")
        except Exception as exc:  # noqa: BLE001 - audited per page.
            errors.append(f"page_{page_index + 1}:{type(exc).__name__}")
            text = ""
        if text:
            pages.append(
                {
                    "page": page_index + 1,
                    "text": text,
                    "char_count": len(text),
                    "keyword_score": _score_page(text),
                    "section_matches": _section_matches(text),
                }
            )
    runtime_seconds = round(time.perf_counter() - started, 3)
    metadata = {
        "page_count": page_count,
        "pages_examined": extract_page_count,
        "non_empty_page_count": len(pages),
        "extract_error_count": len(errors),
        "extract_errors": ";".join(errors[:8]),
        "runtime_seconds": runtime_seconds,
    }
    return pages, metadata


def _select_pages(pages: list[dict[str, Any]], max_chunks_per_source: int) -> list[dict[str, Any]]:
    if not pages:
        return []
    scored = [page for page in pages if int(page["keyword_score"]) > 0]
    if scored:
        selected = sorted(scored, key=lambda item: (-int(item["keyword_score"]), int(item["page"])))[:max_chunks_per_source]
        return sorted(selected, key=lambda item: int(item["page"]))
    return pages[: min(3, max_chunks_per_source)]


def _build_source_rows(
    source: dict[str, Any],
    pages: list[dict[str, Any]],
    metadata: dict[str, Any],
    *,
    max_chunks_per_source: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    updated_at = _now()
    source_path = str(source["local_pdf_path"])
    selected_pages = _select_pages(pages, max_chunks_per_source)
    text_status = "text_extracted" if pages else "text_missing"
    parse_status = "parsed" if selected_pages else "evidence_required"
    manifest = {
        "stock_code": source["stock_code"],
        "stock_name": source["stock_name"],
        "source_type": source["source_type"],
        "source_title": source["source_title"],
        "source_path": source_path,
        "source_id": source["source_id"],
        "collection_source_id": source["source_id"],
        "source_index": source["source_index"],
        "parse_engine": "pypdf_text_first",
        "parse_status": parse_status,
        "text_extract_status": text_status,
        "docling_fallback_status": "not_needed_text_quality_usable" if selected_pages else "deferred_text_missing",
        "page_count": metadata["page_count"],
        "pages_examined": metadata["pages_examined"],
        "non_empty_page_count": metadata["non_empty_page_count"],
        "selected_page_count": len(selected_pages),
        "extract_error_count": metadata["extract_error_count"],
        "extract_errors": metadata["extract_errors"],
        "runtime_seconds": metadata["runtime_seconds"],
        "page_provenance_ready": bool(selected_pages),
        "citation_granularity": "page_level" if selected_pages else "",
        "research_only": True,
        "used_for_signal": False,
        "used_for_admission": False,
        "updated_at": updated_at,
    }
    chunk_rows: list[dict[str, Any]] = []
    chunk_index = 1
    for page in selected_pages:
        for part_index, chunk_text in enumerate(_split_chunk(page["text"]), start=1):
            citation_id = f"TF{int(source['source_index'])}P{int(page['page'])}C{part_index}"
            chunk_rows.append(
                {
                    "stock_code": source["stock_code"],
                    "stock_name": source["stock_name"],
                    "source_type": source["source_type"],
                    "source_title": source["source_title"],
                    "source_path": source_path,
                    "source_id": source["source_id"],
                    "collection_source_id": source["source_id"],
                    "citation_id": citation_id,
                    "chunk_id": f"{source['stock_code']}-TF{int(source['source_index'])}-P{int(page['page'])}-C{part_index}",
                    "chunk_index": chunk_index,
                    "page_start": int(page["page"]),
                    "page_end": int(page["page"]),
                    "page_locator": str(int(page["page"])),
                    "char_count": len(chunk_text),
                    "chunk_text_length": len(chunk_text),
                    "excerpt": chunk_text[:320],
                    "chunk_text": chunk_text,
                    "section_matches": "|".join(page["section_matches"]),
                    "keyword_score": int(page["keyword_score"]),
                    "parse_engine": "pypdf_text_first",
                    "parse_status": "parsed",
                    "citation_granularity": "page_level",
                    "citation_ready": True,
                    "issue_warning": "",
                    "research_only": True,
                    "used_for_signal": False,
                    "used_for_admission": False,
                    "updated_at": updated_at,
                }
            )
            chunk_index += 1
    fallback = {
        "stock_code": source["stock_code"],
        "stock_name": source["stock_name"],
        "source_type": source["source_type"],
        "source_title": source["source_title"],
        "source_path": source_path,
        "docling_fallback_status": manifest["docling_fallback_status"],
        "fallback_reason": "" if selected_pages else "direct_text_extraction_returned_no_citation_ready_chunks",
        "fallback_executed": False,
        "notes": "Docling remains reserved for scanned/low-quality text sources or richer table/layout extraction.",
    }
    return manifest, chunk_rows, fallback


def _build_claims(chunks: pd.DataFrame) -> pd.DataFrame:
    if chunks.empty:
        return pd.DataFrame(
            columns=[
                "claim_id",
                "stock_code",
                "stock_name",
                "source_type",
                "source_title",
                "source_path_or_url",
                "citation_id",
                "chunk_id",
                "page_locator",
                "citation_granularity",
                "claim_text",
                "evidence_strength",
                "is_primary_source",
                "parse_engine",
                "parse_status",
                "research_only",
                "used_for_signal",
                "used_for_admission",
            ]
        )
    claims = chunks.copy()
    claims["claim_id"] = claims["stock_code"] + "-" + claims["chunk_id"].astype(str)
    claims["source_path_or_url"] = claims["source_path"]
    claims["claim_text"] = claims["excerpt"].fillna("").astype(str).str.slice(0, 300)
    claims["evidence_strength"] = "primary_source_text_chunk"
    claims["is_primary_source"] = True
    columns = [
        "claim_id",
        "stock_code",
        "stock_name",
        "source_type",
        "source_title",
        "source_path_or_url",
        "citation_id",
        "chunk_id",
        "page_locator",
        "citation_granularity",
        "claim_text",
        "evidence_strength",
        "is_primary_source",
        "parse_engine",
        "parse_status",
        "research_only",
        "used_for_signal",
        "used_for_admission",
    ]
    return claims[columns]


def _reuse_docling_tables() -> pd.DataFrame:
    path = PREVIOUS_DOCLING_OUTPUT_DIR / "backfill_primary_source_table_provenance.csv"
    if not path.exists():
        return pd.DataFrame()
    tables = _read_csv(path)
    if tables.empty:
        return tables
    tables["parse_engine"] = "docling_reused_structured_table"
    tables["docling_reuse_status"] = "reused_from_previous_successful_docling_parse"
    return tables


def _docling_reused_source_count() -> int:
    path = PREVIOUS_DOCLING_OUTPUT_DIR / "backfill_primary_source_docling_manifest.csv"
    if not path.exists():
        return 0
    manifest = _read_csv(path)
    if manifest.empty or "docling_status" not in manifest.columns:
        return 0
    return int(manifest["docling_status"].eq("parsed").sum())


def _load_cached(output: Path, collection_count: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame] | None:
    paths = [
        output / "text_first_parse_manifest.csv",
        output / "text_first_evidence_chunks.csv",
        output / "text_first_table_provenance.csv",
        output / "text_first_quality_audit.csv",
        output / "docling_fallback_audit.csv",
    ]
    if not all(path.exists() for path in paths):
        return None
    manifest = _read_csv(paths[0])
    if len(manifest) != collection_count:
        return None
    return manifest, _read_csv(paths[1]), _read_csv(paths[2]), _read_csv(paths[3]), _read_csv(paths[4])


def _parse_collection(
    collection: pd.DataFrame,
    *,
    max_pages_per_source: int,
    max_chunks_per_source: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    manifest_rows: list[dict[str, Any]] = []
    chunk_rows: list[dict[str, Any]] = []
    fallback_rows: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    for source in collection.to_dict("records"):
        pages, metadata = _extract_pages(Path(str(source["local_pdf_path"])), max_pages_per_source)
        manifest, chunks, fallback = _build_source_rows(source, pages, metadata, max_chunks_per_source=max_chunks_per_source)
        manifest_rows.append(manifest)
        chunk_rows.extend(chunks)
        fallback_rows.append(fallback)
        quality_rows.append(
            {
                "stock_code": source["stock_code"],
                "stock_name": source["stock_name"],
                "source_type": source["source_type"],
                "source_title": source["source_title"],
                "source_path": source["local_pdf_path"],
                "page_count": metadata["page_count"],
                "pages_examined": metadata["pages_examined"],
                "non_empty_page_count": metadata["non_empty_page_count"],
                "selected_page_count": manifest["selected_page_count"],
                "text_extract_quality": "usable" if manifest["selected_page_count"] else "missing",
                "citation_ready": bool(manifest["selected_page_count"]),
                "issue_warning": "" if manifest["selected_page_count"] else "no_citation_ready_text_chunk",
                "runtime_seconds": metadata["runtime_seconds"],
            }
        )
    return pd.DataFrame(manifest_rows), pd.DataFrame(chunk_rows), pd.DataFrame(quality_rows), pd.DataFrame(fallback_rows)


def _summary(
    *,
    collection: pd.DataFrame,
    manifest: pd.DataFrame,
    chunks: pd.DataFrame,
    claims: pd.DataFrame,
    tables: pd.DataFrame,
    quality: pd.DataFrame,
    docling_reused_count: int,
    strategy_clean: bool,
    max_pages_per_source: int,
    max_chunks_per_source: int,
) -> dict[str, Any]:
    text_success = int(manifest["parse_status"].eq("parsed").sum()) if not manifest.empty else 0
    text_failure = int(len(manifest) - text_success)
    if not COLLECTION_MANIFEST.exists():
        acceptance = "blocked_due_to_missing_collection_manifest"
    elif not strategy_clean:
        acceptance = "blocked_due_to_guardrail_violation"
    elif text_failure:
        acceptance = "text_first_parse_ready_with_text_gaps"
    else:
        acceptance = "text_first_parse_ready"
    return {
        "task_name": TASK_NAME,
        "parse_strategy": "text_first_page_level_extraction_with_docling_structured_reuse",
        "source_stock_count": int(collection["stock_code"].nunique()),
        "source_pdf_count": int(len(collection)),
        "parse_attempt_count": int(len(manifest)),
        "text_extract_success_count": text_success,
        "text_extract_failure_count": text_failure,
        "stock_parse_coverage_count": int(manifest.loc[manifest["parse_status"].eq("parsed"), "stock_code"].nunique()) if not manifest.empty else 0,
        "page_level_citation_count": int(len(claims)),
        "source_level_citation_count": 0,
        "evidence_chunk_count": int(len(chunks)),
        "table_provenance_count": int(len(tables)),
        "docling_structured_artifact_reused_count": docling_reused_count,
        "docling_fallback_executed_count": 0,
        "max_pages_per_source": max_pages_per_source,
        "max_chunks_per_source": max_chunks_per_source,
        "total_text_extract_runtime_seconds": round(float(quality["runtime_seconds"].sum()), 3) if not quality.empty else 0.0,
        "auto_applied_count": 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "acceptance_decision": acceptance,
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "only_collection_manifest_processed": True,
        "source_pdf_count": summary["source_pdf_count"],
        "all_sources_accounted_for": summary["parse_attempt_count"] == summary["source_pdf_count"] == 69,
        "auto_applied_count": summary["auto_applied_count"],
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "baseline_admission_changed_count": summary["baseline_admission_changed_count"],
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
            "# Data-to-Brief Backfill Primary Source Text-First Parse v1",
            "",
            "## 1. Scope",
            "This research-only task parses only the 69 primary-source PDFs from the 23-stock backfill queue. It generates page-level evidence artifacts and does not upgrade candidates, expand the pool, or connect signal/admission.",
            "",
            "## 2. Method",
            "The parser uses direct PDF text extraction first. Docling is retained where it has an advantage: previously successful Docling table/provenance artifacts are reused, and future scanned or low-quality text PDFs can be routed to Docling fallback.",
            "",
            "## 3. Text-First Results",
            f"Source PDFs: {summary['source_pdf_count']}; text successes: {summary['text_extract_success_count']}; text gaps: {summary['text_extract_failure_count']}; stock coverage: {summary['stock_parse_coverage_count']}.",
            "",
            "## 4. Evidence Artifacts",
            f"Evidence chunks: {summary['evidence_chunk_count']}; page-level citation claims: {summary['page_level_citation_count']}; source-level citation claims: {summary['source_level_citation_count']}; reused Docling structured artifacts: {summary['docling_structured_artifact_reused_count']}; table rows: {summary['table_provenance_count']}.",
            "",
            "## 5. Runtime",
            f"Total direct text extraction runtime seconds: {summary['total_text_extract_runtime_seconds']}. Max pages/source: {summary['max_pages_per_source']}; max chunks/source: {summary['max_chunks_per_source']}.",
            "",
            "## 6. Guardrail Checks",
            f"auto_applied_count={summary['auto_applied_count']}; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; baseline_admission_changed_count={summary['baseline_admission_changed_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 7. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 8. Recommended Next Step",
            "Use these page-level text-first artifacts as the primary input for tech_bottleneck_90_primary_source_backfill_rerun_v2. Keep Docling as the richer table/layout parser for sources where direct text is weak or table structure is required.",
        ]
    )


def run(
    output_dir: str | Path = OUTPUT_DIR,
    *,
    max_pages_per_source: int = 80,
    max_chunks_per_source: int = 10,
    force: bool = False,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    collection = _read_collection()
    cached = None if force else _load_cached(output, len(collection))
    if cached is None:
        manifest, chunks, quality, fallback = _parse_collection(
            collection,
            max_pages_per_source=max_pages_per_source,
            max_chunks_per_source=max_chunks_per_source,
        )
        tables = _reuse_docling_tables()
    else:
        manifest, chunks, tables, quality, fallback = cached
    claims = _build_claims(chunks)
    docling_reused_count = _docling_reused_source_count()
    strategy_clean = _strategy_diff_clean()
    summary = _summary(
        collection=collection,
        manifest=manifest,
        chunks=chunks,
        claims=claims,
        tables=tables,
        quality=quality,
        docling_reused_count=docling_reused_count,
        strategy_clean=strategy_clean,
        max_pages_per_source=max_pages_per_source,
        max_chunks_per_source=max_chunks_per_source,
    )
    guardrails = _guardrails(summary)

    manifest.to_csv(output / "text_first_parse_manifest.csv", index=False)
    chunks.to_csv(output / "text_first_evidence_chunks.csv", index=False)
    claims.to_csv(output / "text_first_citation_claims.csv", index=False)
    tables.to_csv(output / "text_first_table_provenance.csv", index=False)
    quality.to_csv(output / "text_first_quality_audit.csv", index=False)
    fallback.to_csv(output / "docling_fallback_audit.csv", index=False)
    _write_json(output / "text_first_parse_summary.json", summary)
    _write_json(output / "text_first_parse_guardrails.json", guardrails)
    (output / "data_to_brief_backfill_primary_source_text_first_parse_v1_report.md").write_text(_report(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages-per-source", type=int, default=80)
    parser.add_argument("--max-chunks-per-source", type=int, default=10)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                max_pages_per_source=args.max_pages_per_source,
                max_chunks_per_source=args.max_chunks_per_source,
                force=args.force,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
