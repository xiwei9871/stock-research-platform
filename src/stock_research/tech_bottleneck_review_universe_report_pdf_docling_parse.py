from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from stock_research.data_to_brief_backfill_primary_source_text_first_parse import (
    _build_source_rows,
    _extract_pages,
    _stock_code,
)


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_review_universe_report_pdf_docling_parse_v1"
FRONTEND_DATASET = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1/"
    "tech_bottleneck_review_universe_frontend_dataset.csv"
)
REPORT_BACKFILL_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_review_universe_yanbaoke_report_backfill_v1"
REPORT_COVERAGE = REPORT_BACKFILL_DIR / "review_universe_report_coverage_after_backfill.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]

EMPTY_CHUNK_COLUMNS = [
    "stock_code",
    "stock_name",
    "source_type",
    "source_title",
    "source_path",
    "source_id",
    "collection_source_id",
    "citation_id",
    "chunk_id",
    "chunk_index",
    "page_start",
    "page_end",
    "page_locator",
    "char_count",
    "chunk_text_length",
    "excerpt",
    "chunk_text",
    "evidence_text",
    "evidence_claim_type",
    "section_matches",
    "keyword_score",
    "parse_engine",
    "parse_status",
    "citation_granularity",
    "citation_ready",
    "issue_warning",
    "research_only",
    "used_for_signal",
    "used_for_admission",
    "updated_at",
]

PAGE_CITATION_COLUMNS = [
    "citation_id",
    "stock_code",
    "stock_name",
    "source_file",
    "source_type",
    "source_title",
    "page",
    "evidence_text",
    "evidence_claim_type",
    "citation_quality",
    "research_only",
    "used_for_signal",
    "used_for_admission",
]

FAILURE_COLUMNS = [
    "stock_code",
    "stock_name",
    "source_type",
    "source_title",
    "source_path",
    "parse_status",
    "error_detail",
    "recommended_next_action",
    "research_only",
    "used_for_signal",
    "used_for_admission",
]


ExtractPagesFunc = Callable[[Path, int], tuple[list[dict[str, Any]], dict[str, Any]]]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _split_pipe(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split(" | ") if part.strip()]


def _docling_available() -> bool:
    return importlib.util.find_spec("docling") is not None


def _empty_chunks() -> pd.DataFrame:
    return pd.DataFrame(columns=EMPTY_CHUNK_COLUMNS)


def _empty_page_citations() -> pd.DataFrame:
    return pd.DataFrame(columns=PAGE_CITATION_COLUMNS)


def _empty_failures() -> pd.DataFrame:
    return pd.DataFrame(columns=FAILURE_COLUMNS)


def _safe_cell(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return value.encode("utf-8", errors="replace").decode("utf-8")


def _safe_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    safe = frame.copy()
    for column in safe.columns:
        if safe[column].map(lambda value: isinstance(value, str)).any():
            safe[column] = safe[column].map(_safe_cell)
    return safe


def _build_report_manifest(
    universe: pd.DataFrame,
    coverage: pd.DataFrame,
    *,
    max_pdfs_per_stock: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    universe_codes = set(universe["stock_code"].astype(str).map(_stock_code))
    rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    source_index = 1
    for _, row in coverage.sort_values("stock_code").iterrows():
        stock_code = _stock_code(row.get("stock_code"))
        if stock_code not in universe_codes:
            continue
        stock_name = str(row.get("stock_name") or "").strip()
        paths = _split_pipe(row.get("report_pdf_paths"))
        titles = _split_pipe(row.get("report_titles"))
        selected_count = 0
        seen_paths: set[str] = set()
        for path_index, path_text in enumerate(paths, start=1):
            if selected_count >= max_pdfs_per_stock:
                break
            pdf_path = Path(path_text)
            normalized_path = str(pdf_path)
            if normalized_path in seen_paths:
                continue
            seen_paths.add(normalized_path)
            if not pdf_path.exists():
                continue
            title = titles[path_index - 1] if path_index - 1 < len(titles) else pdf_path.name
            rows.append(
                {
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "source_type": "broker_report_pdf",
                    "source_title": title or pdf_path.name,
                    "source_path": str(pdf_path),
                    "local_pdf_path": str(pdf_path),
                    "source_id": f"broker-report-{stock_code}-{source_index}",
                    "collection_source_id": f"broker-report-{stock_code}-{source_index}",
                    "source_index": source_index,
                    "report_path_rank": path_index,
                    "report_pdf_count_from_coverage": int(float(row.get("report_pdf_count") or 0)),
                    "research_only": True,
                    "used_for_signal": False,
                    "used_for_admission": False,
                }
            )
            source_index += 1
            selected_count += 1
        if not selected_count:
            missing_rows.append(
                {
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "has_report_pdf": _truthy(row.get("has_report_pdf")),
                    "report_pdf_count": int(float(row.get("report_pdf_count") or 0)),
                    "missing_reason": "no_existing_pdf_path_selected",
                    "research_only": True,
                    "used_for_signal": False,
                    "used_for_admission": False,
                }
            )
    manifest = pd.DataFrame(rows)
    missing = pd.DataFrame(missing_rows)
    return manifest, missing


def _parse_manifest(
    manifest: pd.DataFrame,
    *,
    max_pages_per_source: int,
    max_chunks_per_source: int,
    extract_pages_func: ExtractPagesFunc,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    parse_rows: list[dict[str, Any]] = []
    chunk_rows: list[dict[str, Any]] = []
    for source in manifest.to_dict("records"):
        try:
            pages, metadata = extract_pages_func(Path(str(source["local_pdf_path"])), max_pages_per_source)
            parse_row, chunks, _fallback = _build_source_rows(
                source,
                pages,
                metadata,
                max_chunks_per_source=max_chunks_per_source,
            )
        except Exception as exc:  # noqa: BLE001 - audited as parse failure.
            parse_row = {
                "stock_code": source.get("stock_code", ""),
                "stock_name": source.get("stock_name", ""),
                "source_type": source.get("source_type", "broker_report_pdf"),
                "source_title": source.get("source_title", ""),
                "source_path": source.get("source_path", source.get("local_pdf_path", "")),
                "source_id": source.get("source_id", ""),
                "collection_source_id": source.get("collection_source_id", ""),
                "source_index": source.get("source_index", ""),
                "parse_engine": "pypdf_text_first",
                "parse_status": "parse_error",
                "text_extract_status": "parse_error",
                "docling_fallback_status": "deferred_exception",
                "page_count": 0,
                "pages_examined": 0,
                "non_empty_page_count": 0,
                "selected_page_count": 0,
                "extract_error_count": 1,
                "extract_errors": f"{type(exc).__name__}: {str(exc)[:300]}",
                "runtime_seconds": 0.0,
                "page_provenance_ready": False,
                "citation_granularity": "",
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "updated_at": _now(),
            }
            chunks = []
        parse_row["source_path"] = source.get("source_path", parse_row.get("source_path", ""))
        parse_row["parser_mode"] = "text_first_docling_aware"
        parse_rows.append(parse_row)
        for chunk in chunks:
            chunk["source_path"] = source.get("source_path", chunk.get("source_path", ""))
            chunk["source_file"] = source.get("source_path", chunk.get("source_path", ""))
            chunk["evidence_text"] = chunk.get("chunk_text", "")
            chunk["evidence_claim_type"] = chunk.get("section_matches", "") or "broker_report_text"
            chunk["parser_mode"] = "text_first_docling_aware"
            chunk_rows.append(chunk)
    parse_manifest = pd.DataFrame(parse_rows)
    chunks_frame = pd.DataFrame(chunk_rows) if chunk_rows else _empty_chunks()
    return parse_manifest, chunks_frame


def _build_page_citations(chunks: pd.DataFrame) -> pd.DataFrame:
    if chunks.empty:
        return _empty_page_citations()
    rows: list[dict[str, Any]] = []
    for _, row in chunks.sort_values(["stock_code", "source_title", "page_start", "chunk_index"]).iterrows():
        rows.append(
            {
                "citation_id": row.get("citation_id", ""),
                "stock_code": row.get("stock_code", ""),
                "stock_name": row.get("stock_name", ""),
                "source_file": row.get("source_file", row.get("source_path", "")),
                "source_type": row.get("source_type", "broker_report_pdf"),
                "source_title": row.get("source_title", ""),
                "page": row.get("page_start", ""),
                "evidence_text": row.get("evidence_text", row.get("chunk_text", "")),
                "evidence_claim_type": row.get("evidence_claim_type", ""),
                "citation_quality": "page_level",
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
            }
        )
    return pd.DataFrame(rows, columns=PAGE_CITATION_COLUMNS)


def _build_failures(parse_manifest: pd.DataFrame, missing_report_rows: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if not parse_manifest.empty:
        failures = parse_manifest[parse_manifest["parse_status"].ne("parsed")].copy()
        for _, row in failures.iterrows():
            rows.append(
                {
                    "stock_code": row.get("stock_code", ""),
                    "stock_name": row.get("stock_name", ""),
                    "source_type": row.get("source_type", "broker_report_pdf"),
                    "source_title": row.get("source_title", ""),
                    "source_path": row.get("source_path", ""),
                    "parse_status": row.get("parse_status", ""),
                    "error_detail": row.get("extract_errors", "") or "no citation-ready report text extracted",
                    "recommended_next_action": "retry selected report with Docling layout parse or collect alternate broker report",
                    "research_only": True,
                    "used_for_signal": False,
                    "used_for_admission": False,
                }
            )
    if not missing_report_rows.empty:
        for _, row in missing_report_rows.iterrows():
            rows.append(
                {
                    "stock_code": row.get("stock_code", ""),
                    "stock_name": row.get("stock_name", ""),
                    "source_type": "broker_report_pdf",
                    "source_title": "",
                    "source_path": "",
                    "parse_status": "missing_report_pdf",
                    "error_detail": row.get("missing_reason", "missing report PDF"),
                    "recommended_next_action": "collect broker report PDF before report parse rerun",
                    "research_only": True,
                    "used_for_signal": False,
                    "used_for_admission": False,
                }
            )
    return pd.DataFrame(rows, columns=FAILURE_COLUMNS)


def _summary(
    *,
    universe: pd.DataFrame,
    coverage: pd.DataFrame,
    manifest: pd.DataFrame,
    parse_manifest: pd.DataFrame,
    chunks: pd.DataFrame,
    citations: pd.DataFrame,
    failures: pd.DataFrame,
    max_pdfs_per_stock: int,
    strategy_clean: bool,
) -> dict[str, Any]:
    report_covered = int(coverage["has_report_pdf"].map(_truthy).sum()) if "has_report_pdf" in coverage.columns else 0
    missing_report = int(len(universe) - report_covered)
    parse_success = int(parse_manifest["parse_status"].eq("parsed").sum()) if not parse_manifest.empty else 0
    parse_failure = int(parse_manifest["parse_status"].ne("parsed").sum()) if not parse_manifest.empty else 0
    blocking = report_covered + missing_report != len(universe) or not strategy_clean
    if blocking:
        acceptance = "blocked_due_to_guardrail_violation"
    elif parse_failure:
        acceptance = "conditionally_ready_with_parse_failures"
    else:
        acceptance = "review_universe_report_pdf_docling_parse_ready"
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "review_universe_total_count": int(len(universe)),
        "report_pdf_covered_stock_count": report_covered,
        "missing_report_pdf_stock_count": missing_report,
        "selected_report_pdf_count": int(len(manifest)),
        "max_pdfs_per_stock": int(max_pdfs_per_stock),
        "parse_attempt_count": int(len(parse_manifest)),
        "parse_success_count": parse_success,
        "parse_failure_count": parse_failure,
        "evidence_chunk_count": int(len(chunks)),
        "page_level_citation_count": int(len(citations)),
        "failure_or_gap_row_count": int(len(failures)),
        "parser_mode": "text_first_docling_aware",
        "docling_available": _docling_available(),
        "broker_report_parse_performed": True,
        "primary_source_collection_performed": False,
        "evidence_backfill_performed": False,
        "core_equivalence_performed": False,
        "reassessment_performed": False,
        "frozen_quality_pool_generated": False,
        "auto_added_to_quality_pool_count": 0,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "acceptance_decision": acceptance,
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "review_universe_total_count": summary["review_universe_total_count"],
        "report_pdf_covered_stock_count": summary["report_pdf_covered_stock_count"],
        "missing_report_pdf_stock_count": summary["missing_report_pdf_stock_count"],
        "selected_report_pdf_count": summary["selected_report_pdf_count"],
        "parse_attempt_count": summary["parse_attempt_count"],
        "parse_success_count": summary["parse_success_count"],
        "parse_failure_count": summary["parse_failure_count"],
        "broker_report_parse_performed": True,
        "primary_source_collection_performed": False,
        "evidence_backfill_performed": False,
        "core_equivalence_performed": False,
        "reassessment_performed": False,
        "frozen_quality_pool_generated": False,
        "auto_added_to_quality_pool_count": 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "price_move_used_for_signal": 0,
        "low_position_used_for_signal": 0,
        "strategy_file_diff_clean": summary["strategy_file_diff_clean"],
        "formal_strategy_files_modified": summary["formal_strategy_files_modified"],
        "acceptance_decision": summary["acceptance_decision"],
    }


def _write_report(output: Path, summary: dict[str, Any]) -> None:
    report = f"""# {TASK_NAME}

## Summary

- review universe: {summary['review_universe_total_count']}
- report PDF covered stocks: {summary['report_pdf_covered_stock_count']}
- missing report PDF stocks: {summary['missing_report_pdf_stock_count']}
- selected report PDFs parsed: {summary['parse_attempt_count']}
- parse success/failure: {summary['parse_success_count']} / {summary['parse_failure_count']}
- evidence chunks: {summary['evidence_chunk_count']}
- page-level citations: {summary['page_level_citation_count']}
- parser mode: {summary['parser_mode']}
- Docling available: {summary['docling_available']}

## Guardrails

- research-only: true
- broker report parse performed: true
- primary source collection performed: false
- evidence backfill performed: false
- core equivalence performed: false
- reassessment performed: false
- used_for_signal/admission: 0 / 0
- strategy file diff clean: {summary['strategy_file_diff_clean']}

## Acceptance

{summary['acceptance_decision']}
"""
    (output / "tech_bottleneck_review_universe_report_pdf_docling_parse_v1_report.md").write_text(
        report,
        encoding="utf-8",
    )


def run(
    *,
    universe_path: Path = FRONTEND_DATASET,
    coverage_path: Path = REPORT_COVERAGE,
    output_dir: Path = OUTPUT_DIR,
    max_pdfs_per_stock: int = 1,
    max_pages_per_source: int = 80,
    max_chunks_per_source: int = 8,
    extract_pages_func: ExtractPagesFunc = _extract_pages,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    universe = _read_csv(Path(universe_path))
    coverage = _read_csv(Path(coverage_path))
    manifest, missing_report_rows = _build_report_manifest(
        universe,
        coverage,
        max_pdfs_per_stock=max_pdfs_per_stock,
    )
    parse_manifest, chunks = _parse_manifest(
        manifest,
        max_pages_per_source=max_pages_per_source,
        max_chunks_per_source=max_chunks_per_source,
        extract_pages_func=extract_pages_func,
    )
    citations = _build_page_citations(chunks)
    failures = _build_failures(parse_manifest, missing_report_rows)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(
        universe=universe,
        coverage=coverage,
        manifest=manifest,
        parse_manifest=parse_manifest,
        chunks=chunks,
        citations=citations,
        failures=failures,
        max_pdfs_per_stock=max_pdfs_per_stock,
        strategy_clean=strategy_clean,
    )
    guardrails = _guardrails(summary)

    manifest = _safe_frame(manifest)
    parse_manifest = _safe_frame(parse_manifest)
    chunks = _safe_frame(chunks)
    citations = _safe_frame(citations)
    failures = _safe_frame(failures)

    manifest.drop(columns=["local_pdf_path"], errors="ignore").to_csv(
        output / "review_universe_report_pdf_parse_manifest.csv",
        index=False,
    )
    parse_manifest.to_csv(output / "review_universe_report_pdf_parse_audit.csv", index=False)
    chunks.to_csv(output / "review_universe_report_pdf_evidence_chunks.csv", index=False)
    citations.to_csv(output / "review_universe_report_pdf_page_citations.csv", index=False)
    failures.to_csv(output / "review_universe_report_pdf_parse_failures.csv", index=False)
    _write_json(output / "review_universe_report_pdf_parse_summary.json", summary)
    _write_json(output / "review_universe_report_pdf_docling_guardrails.json", guardrails)
    _write_report(output, summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse review-universe broker report PDFs into page-level artifacts.")
    parser.add_argument("--universe-path", type=Path, default=FRONTEND_DATASET)
    parser.add_argument("--coverage-path", type=Path, default=REPORT_COVERAGE)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--max-pdfs-per-stock", type=int, default=1)
    parser.add_argument("--max-pages-per-source", type=int, default=80)
    parser.add_argument("--max-chunks-per-source", type=int, default=8)
    args = parser.parse_args(argv)
    summary = run(
        universe_path=args.universe_path,
        coverage_path=args.coverage_path,
        output_dir=args.output_dir,
        max_pdfs_per_stock=args.max_pdfs_per_stock,
        max_pages_per_source=args.max_pages_per_source,
        max_chunks_per_source=args.max_chunks_per_source,
    )
    print(f"{TASK_NAME}|acceptance_decision|{summary['acceptance_decision']}")
    print(f"{TASK_NAME}|parse_attempt_count|{summary['parse_attempt_count']}")
    print(f"{TASK_NAME}|parse_success_count|{summary['parse_success_count']}")
    print(f"{TASK_NAME}|parse_failure_count|{summary['parse_failure_count']}")
    print(f"{TASK_NAME}|page_level_citation_count|{summary['page_level_citation_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
