from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import pandas as pd

import stock_research.data_to_brief_docling_adapter_provenance_backfill_batch as batch
from stock_research.data_to_brief_docling_parser_poc import run_data_to_brief_docling_parser_poc


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TASK_NAME = "data_to_brief_docling_90_stock_full_cold_parse_batch_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
PRECHECK_OUTPUT_DIR = PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_stock_batch_precheck_v1"
SOURCE_ROOTS = [
    PROJECT_ROOT / "data/manual",
    PROJECT_ROOT / "outputs/research/data_to_brief_docling_adapter_provenance_backfill_and_10_stock_batch_pilot_v1/source_acquisition/yanbaoke_pdfs",
    PROJECT_ROOT / "outputs/research/data_to_brief_docling_30_stock_batch_pilot_v1/source_acquisition/yanbaoke_pdfs",
    PROJECT_ROOT / "outputs/research/data_to_brief_docling_90_stock_pdf_acquisition_v1/yanbaoke_pdfs",
]
SEED_ARTIFACT_DIRS = [
    PROJECT_ROOT / "outputs/research/data_to_brief_docling_30_stock_batch_pilot_v1/parser_artifacts",
    PROJECT_ROOT / "outputs/research/data_to_brief_docling_adapter_provenance_backfill_and_10_stock_batch_pilot_v1/parser_artifacts",
]
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def run_data_to_brief_docling_90_stock_full_cold_parse_batch(
    *,
    output_dir: str | Path = OUTPUT_DIR,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()

    stocks = _load_90_stocks()
    parser_dir = output / "parser_artifacts"
    prep = _prepare_parser_artifacts(output, parser_dir, stocks)

    old_task = batch.TASK_NAME
    old_stocks = batch.PILOT_STOCKS
    try:
        batch.TASK_NAME = TASK_NAME
        batch.PILOT_STOCKS = stocks
        batch.run_docling_adapter_provenance_backfill_10_stock_batch(
            output_dir=output,
            source_roots=SOURCE_ROOTS,
            sleep_seconds=0.0,
        )
    finally:
        batch.TASK_NAME = old_task
        batch.PILOT_STOCKS = old_stocks

    total_runtime = time.perf_counter() - started
    chunks = _read_csv(output / "batch_source_chunk_manifest.csv")
    tables = _read_csv(output / "batch_table_inventory.csv")
    claims = _read_csv(output / "batch_claim_citation_map.csv")
    status = _read_csv(output / "batch_report_status.csv")
    parser_quality = _read_csv(output / "batch_parser_quality_audit.csv")
    citation_integrity = _read_csv(output / "batch_citation_integrity_audit.csv")
    table_quality = _read_csv(output / "batch_table_quality_audit.csv")

    batch_manifest = _build_batch_manifest(stocks, prep, status)
    parser_audit = _build_parser_artifact_audit(stocks, prep, parser_quality, chunks)
    citation_audit = _build_citation_audit(stocks, status, claims)
    table_audit = _build_table_provenance_audit(stocks, tables)
    report_audit = _build_report_generation_audit(output, status)
    runtime_audit = _build_runtime_audit(stocks, prep, total_runtime)
    summary = _build_summary(
        batch_manifest=batch_manifest,
        parser_audit=parser_audit,
        chunks=chunks,
        tables=tables,
        claims=claims,
        status=status,
        citation_audit=citation_audit,
        table_audit=table_audit,
        runtime_audit=runtime_audit,
        total_runtime=total_runtime,
        prep=prep,
        citation_integrity=citation_integrity,
        table_quality=table_quality,
    )

    batch_manifest.to_csv(output / "batch_manifest.csv", index=False)
    parser_audit.to_csv(output / "parser_artifact_audit.csv", index=False)
    chunks.to_csv(output / "source_chunk_manifest_all.csv", index=False)
    tables.to_csv(output / "table_inventory_all.csv", index=False)
    citation_audit.to_csv(output / "citation_audit.csv", index=False)
    table_audit.to_csv(output / "table_provenance_audit.csv", index=False)
    report_audit.to_csv(output / "report_generation_audit.csv", index=False)
    runtime_audit.to_csv(output / "runtime_audit.csv", index=False)
    _write_json(output / "quality_audit.json", summary)
    (output / "summary.md").write_text(_render_report(summary, report_audit, parser_audit), encoding="utf-8")
    _copy_reports_to_90_names(output, report_audit)
    return {"summary": summary}


def _prepare_parser_artifacts(output: Path, parser_dir: Path, stocks: list[dict[str, str]]) -> dict[str, Any]:
    parser_dir.mkdir(parents=True, exist_ok=True)
    existing_summary = _read_json(parser_dir / "pilot_run_summary.json")
    existing_chunks = _read_csv(parser_dir / "source_chunk_manifest.csv")
    if int(existing_summary.get("pilot_stock_count") or 0) == len(stocks) and _ready_stock_count(existing_chunks) >= 85:
        return _prep_from_existing(parser_dir, stocks)

    stock_codes = [stock["stock_code"] for stock in stocks]
    cache = _load_seed_cache(stock_codes)
    reused_codes = sorted(code for code, payload in cache.items() if payload["page_ready"])
    cold_stocks = [stock for stock in stocks if stock["stock_code"] not in set(reused_codes)]
    cold_dir = output / "cold_parser_artifacts"
    cold_started = time.perf_counter()
    if cold_stocks and not _cold_artifacts_ready(cold_dir, cold_stocks):
        run_data_to_brief_docling_parser_poc(
            output_dir=cold_dir,
            source_roots=SOURCE_ROOTS,
            pilot_stocks=cold_stocks,
            limit_per_stock=1,
        )
    cold_runtime = time.perf_counter() - cold_started
    cold_cache = _cache_from_artifact_dir(cold_dir, [stock["stock_code"] for stock in cold_stocks])

    chunks, tables, comparison = _merge_artifacts(stocks, cache, cold_cache)
    _renumber_citations(chunks, tables)
    chunks.to_csv(parser_dir / "source_chunk_manifest.csv", index=False)
    tables.to_csv(parser_dir / "table_inventory.csv", index=False)
    comparison.to_csv(parser_dir / "parser_comparison_matrix.csv", index=False)
    _write_json(
        parser_dir / "pilot_run_summary.json",
        {
            "task_name": TASK_NAME,
            "pilot_stock_count": len(stocks),
            "local_pdf_count": int(comparison["pdf_path"].fillna("").astype(str).str.len().gt(0).groupby(comparison["stock_code"]).any().sum()),
            "docling_parsed_count": int(comparison["docling_status"].eq("parsed").groupby(comparison["stock_code"]).any().sum()),
            "docling_failed_count": int(comparison["docling_status"].isin(["parse_error", "import_error"]).sum()),
            "evidence_required_stock_count": 0,
            "chunk_count": int(len(chunks)),
            "table_count": int(len(tables)),
            "research_only": True,
            "allowed_for_signal": False,
            "allowed_for_admission": False,
            "production_update": False,
        },
    )
    cold_ready_codes = [code for code, payload in cold_cache.items() if payload["page_ready"]]
    return {
        "cached_parser_artifact_reused_count": len(reused_codes),
        "reused_codes": reused_codes,
        "cold_parse_required_count": len(cold_stocks),
        "cold_parse_success_count": len(cold_ready_codes),
        "cold_parse_failed_count": len(cold_stocks) - len(cold_ready_codes),
        "cold_ready_codes": cold_ready_codes,
        "cold_failed_codes": [stock["stock_code"] for stock in cold_stocks if stock["stock_code"] not in set(cold_ready_codes)],
        "cold_parse_runtime_seconds": round(cold_runtime, 3),
        "parser_dir": str(parser_dir),
    }


def _prep_from_existing(parser_dir: Path, stocks: list[dict[str, str]]) -> dict[str, Any]:
    chunks = _read_csv(parser_dir / "source_chunk_manifest.csv")
    ready_codes = sorted(
        code
        for code, group in chunks.groupby("stock_code")
        if group.get("page_locator", pd.Series(dtype=object)).fillna("").astype(str).str.len().gt(0).any()
    )
    stock_codes = [stock["stock_code"] for stock in stocks]
    seed_cache = _load_seed_cache(stock_codes)
    reused_codes = sorted(code for code in ready_codes if code in seed_cache)
    cold_ready_codes = sorted(code for code in ready_codes if code not in set(reused_codes))
    cold_failed_codes = [code for code in stock_codes if code not in set(ready_codes)]
    return {
        "cached_parser_artifact_reused_count": len(reused_codes),
        "reused_codes": reused_codes,
        "cold_parse_required_count": len(cold_ready_codes) + len(cold_failed_codes),
        "cold_parse_success_count": len(cold_ready_codes),
        "cold_parse_failed_count": len(cold_failed_codes),
        "cold_ready_codes": cold_ready_codes,
        "cold_failed_codes": cold_failed_codes,
        "cold_parse_runtime_seconds": _estimate_artifact_runtime_seconds(parser_dir.parent / "cold_parser_artifacts"),
        "parser_dir": str(parser_dir),
        "already_combined_artifacts_reused": True,
    }


def _load_seed_cache(stock_codes: list[str]) -> dict[str, dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = {}
    for artifact_dir in SEED_ARTIFACT_DIRS:
        for code, payload in _cache_from_artifact_dir(artifact_dir, stock_codes).items():
            if code not in cache and payload["page_ready"]:
                cache[code] = payload
    return cache


def _cache_from_artifact_dir(artifact_dir: Path, stock_codes: list[str]) -> dict[str, dict[str, Any]]:
    chunks = _read_csv(artifact_dir / "source_chunk_manifest.csv")
    tables = _read_csv(artifact_dir / "table_inventory.csv")
    comparison = _read_csv(artifact_dir / "parser_comparison_matrix.csv")
    cache: dict[str, dict[str, Any]] = {}
    for code in stock_codes:
        stock_chunks = chunks[chunks["stock_code"].eq(code)].copy() if "stock_code" in chunks else pd.DataFrame()
        stock_tables = tables[tables["stock_code"].eq(code)].copy() if "stock_code" in tables else pd.DataFrame()
        stock_comparison = comparison[comparison["stock_code"].eq(code)].copy() if "stock_code" in comparison else pd.DataFrame()
        page_ready = not stock_chunks.empty and stock_chunks.get("page_locator", pd.Series(dtype=object)).fillna("").astype(str).str.len().gt(0).any()
        if not stock_chunks.empty or not stock_comparison.empty:
            cache[code] = {
                "chunks": stock_chunks,
                "tables": stock_tables,
                "comparison": stock_comparison,
                "page_ready": bool(page_ready),
                "artifact_dir": str(artifact_dir),
            }
    return cache


def _merge_artifacts(stocks: list[dict[str, str]], cache: dict[str, dict[str, Any]], cold_cache: dict[str, dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    chunk_frames: list[pd.DataFrame] = []
    table_frames: list[pd.DataFrame] = []
    comparison_frames: list[pd.DataFrame] = []
    for stock in stocks:
        code = stock["stock_code"]
        payload = cache.get(code) or cold_cache.get(code)
        if not payload:
            comparison_frames.append(pd.DataFrame([{"stock_code": code, "stock_name": stock["stock_name"], "pdf_path": "", "docling_status": "missing_artifact"}]))
            continue
        if not payload["chunks"].empty:
            chunk_frames.append(payload["chunks"].copy())
        if not payload["tables"].empty:
            table_frames.append(payload["tables"].copy())
        if not payload["comparison"].empty:
            comparison_frames.append(payload["comparison"].copy())
    chunks = pd.concat(chunk_frames, ignore_index=True) if chunk_frames else pd.DataFrame()
    tables = pd.concat(table_frames, ignore_index=True) if table_frames else pd.DataFrame()
    comparison = pd.concat(comparison_frames, ignore_index=True) if comparison_frames else pd.DataFrame()
    return chunks, tables, comparison


def _renumber_citations(chunks: pd.DataFrame, tables: pd.DataFrame) -> None:
    if chunks.empty:
        return
    mapping: dict[tuple[str, str], str] = {}
    for index, row_index in enumerate(chunks.index, start=1):
        old = str(chunks.at[row_index, "citation_id"] if "citation_id" in chunks else "")
        code = str(chunks.at[row_index, "stock_code"])
        new = f"S{index}"
        mapping[(code, old)] = new
        chunks.at[row_index, "citation_id"] = new
        chunks.at[row_index, "source_id"] = new
    if not tables.empty:
        for row_index in tables.index:
            code = str(tables.at[row_index, "stock_code"])
            old = str(tables.at[row_index, "citation_id"] if "citation_id" in tables else "")
            new = mapping.get((code, old))
            if not new:
                stock_matches = [value for (stock_code, _old), value in mapping.items() if stock_code == code]
                new = stock_matches[0] if stock_matches else f"S{len(mapping) + 1}"
            tables.at[row_index, "citation_id"] = new
            tables.at[row_index, "source_id"] = new


def _build_batch_manifest(stocks: list[dict[str, str]], prep: dict[str, Any], status: pd.DataFrame) -> pd.DataFrame:
    status_by_code = status.set_index("stock_code").to_dict("index") if not status.empty else {}
    reused = set(prep.get("reused_codes", []))
    cold_ready = set(prep.get("cold_ready_codes", []))
    cold_failed = set(prep.get("cold_failed_codes", []))
    rows = []
    for stock in stocks:
        code = stock["stock_code"]
        row = status_by_code.get(code, {})
        rows.append(
            {
                **stock,
                "local_pdf_available": bool(row.get("has_local_pdf", True)),
                "evidence_required": row.get("report_status") == "evidence_required",
                "parser_artifact_source": "reused_cache" if code in reused else "cold_parse" if code in cold_ready else "cold_parse_failed" if code in cold_failed else "unknown",
                "parser_artifact_ready": code in reused or code in cold_ready,
                "report_status": row.get("report_status", ""),
                "allowed_for_signal": False,
                "allowed_for_admission": False,
                "production_update": False,
            }
        )
    return pd.DataFrame(rows)


def _build_parser_artifact_audit(stocks: list[dict[str, str]], prep: dict[str, Any], parser_quality: pd.DataFrame, chunks: pd.DataFrame) -> pd.DataFrame:
    reused = set(prep.get("reused_codes", []))
    cold_ready = set(prep.get("cold_ready_codes", []))
    cold_failed = set(prep.get("cold_failed_codes", []))
    quality_by_code = parser_quality.set_index("stock_code").to_dict("index") if not parser_quality.empty else {}
    rows = []
    for stock in stocks:
        code = stock["stock_code"]
        stock_chunks = chunks[chunks["stock_code"].eq(code)] if "stock_code" in chunks else pd.DataFrame()
        if code in reused:
            status = "reused_page_level"
        elif code in cold_ready:
            status = "cold_parse_page_level"
        elif code in cold_failed:
            status = "parse_failed"
        else:
            status = "invalid"
        rows.append(
            {
                **stock,
                "parser_artifact_status": status,
                "chunk_count": int(len(stock_chunks)),
                "page_level_chunk_count": int(stock_chunks.get("citation_granularity", pd.Series(dtype=object)).eq("page_level").sum()) if not stock_chunks.empty else 0,
                "docling_status": quality_by_code.get(code, {}).get("docling_status", ""),
                "issue_warning": quality_by_code.get(code, {}).get("issue_warning", ""),
            }
        )
    return pd.DataFrame(rows)


def _build_citation_audit(stocks: list[dict[str, str]], status: pd.DataFrame, claims: pd.DataFrame) -> pd.DataFrame:
    status_by_code = status.set_index("stock_code").to_dict("index") if not status.empty else {}
    rows = []
    for stock in stocks:
        code = stock["stock_code"]
        stock_claims = claims[claims["stock_code"].eq(code)] if "stock_code" in claims else pd.DataFrame()
        rows.append(
            {
                **stock,
                "citation_claim_count": int(len(stock_claims)),
                "citations_with_page_locator_count": int(stock_claims.get("page_locator", pd.Series(dtype=object)).fillna("").astype(str).str.len().gt(0).sum()) if not stock_claims.empty else 0,
                "page_level_citation_row_count": int(stock_claims.get("citation_granularity", pd.Series(dtype=object)).eq("page_level").sum()) if not stock_claims.empty else 0,
                "source_level_citation_count": int(stock_claims.get("citation_granularity", pd.Series(dtype=object)).eq("source_level").sum()) if not stock_claims.empty else 0,
                "report_status": status_by_code.get(code, {}).get("report_status", ""),
            }
        )
    return pd.DataFrame(rows)


def _build_table_provenance_audit(stocks: list[dict[str, str]], tables: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for stock in stocks:
        code = stock["stock_code"]
        stock_tables = tables[tables["stock_code"].eq(code)] if "stock_code" in tables else pd.DataFrame()
        page = stock_tables.get("page_locator", pd.Series(dtype=object)).fillna("").astype(str).str.len().gt(0) if not stock_tables.empty else pd.Series(dtype=bool)
        row = stock_tables.get("row_count", pd.Series(dtype=object)).fillna("").astype(str).str.len().gt(0) if not stock_tables.empty else pd.Series(dtype=bool)
        col = stock_tables.get("column_count", pd.Series(dtype=object)).fillna("").astype(str).str.len().gt(0) if not stock_tables.empty else pd.Series(dtype=bool)
        rows.append(
            {
                **stock,
                "table_row_count": int(len(stock_tables)),
                "table_provenance_full_count": int((page & row & col).sum()) if not stock_tables.empty else 0,
                "table_provenance_partial_count": int(((page | row | col) & ~(page & row & col)).sum()) if not stock_tables.empty else 0,
                "table_provenance_missing_count": int((~(page | row | col)).sum()) if not stock_tables.empty else 0,
            }
        )
    return pd.DataFrame(rows)


def _build_report_generation_audit(output: Path, status: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in status.iterrows():
        code = str(row["stock_code"]).zfill(6)
        name = str(row["stock_name"])
        report_status = str(row["report_status"])
        rows.append(
            {
                "stock_code": code,
                "stock_name": name,
                "report_status": "failed" if report_status == "evidence_required" else report_status,
                "blocker_reason": row.get("blocker_reason", ""),
                "report_md_path": str(output / "reports_md" / f"{code}_{name}_docling_10_stock_pilot_report.md"),
                "report_html_path": str(output / "reports_html" / f"{code}_{name}_docling_10_stock_pilot_report.html"),
                "report_pdf_path": str(output / "reports_pdf" / f"{code}_{name}_docling_10_stock_pilot_report.pdf"),
                "evidence_matrix_path": str(output / "evidence" / code / "evidence_matrix.csv"),
                "claim_citation_map_path": str(output / "evidence" / code / "claim_citation_map.csv"),
                "sources_jsonl_path": str(output / "evidence" / code / "sources.jsonl"),
                "allowed_for_signal": False,
                "allowed_for_admission": False,
                "production_update": False,
            }
        )
    return pd.DataFrame(rows)


def _build_runtime_audit(stocks: list[dict[str, str]], prep: dict[str, Any], total_runtime: float) -> pd.DataFrame:
    cold_codes = set(prep.get("cold_ready_codes", [])) | set(prep.get("cold_failed_codes", []))
    cold_runtime = float(prep.get("cold_parse_runtime_seconds") or 0)
    per_cold = cold_runtime / max(1, len(cold_codes))
    rows = []
    for stock in stocks:
        code = stock["stock_code"]
        rows.append(
            {
                **stock,
                "runtime_stage": "cold_parse" if code in cold_codes else "cached_reuse",
                "per_stock_runtime_seconds": round(per_cold if code in cold_codes else 0.0, 3),
            }
        )
    rows.append({"stock_code": "ALL", "stock_name": "batch_total", "asset_id": "", "runtime_stage": "total", "per_stock_runtime_seconds": round(total_runtime, 3)})
    return pd.DataFrame(rows)


def _build_summary(
    *,
    batch_manifest: pd.DataFrame,
    parser_audit: pd.DataFrame,
    chunks: pd.DataFrame,
    tables: pd.DataFrame,
    claims: pd.DataFrame,
    status: pd.DataFrame,
    citation_audit: pd.DataFrame,
    table_audit: pd.DataFrame,
    runtime_audit: pd.DataFrame,
    total_runtime: float,
    prep: dict[str, Any],
    citation_integrity: pd.DataFrame,
    table_quality: pd.DataFrame,
) -> dict[str, Any]:
    stock_count = int(len(batch_manifest))
    evidence_required = int(status["report_status"].eq("evidence_required").sum()) if not status.empty else 0
    report_success = int(status["report_status"].ne("evidence_required").sum()) if not status.empty else 0
    report_failed = stock_count - report_success
    parser_ready = int(parser_audit["parser_artifact_status"].isin(["reused_page_level", "cold_parse_page_level"]).sum())
    parse_failed = int(parser_audit["parser_artifact_status"].eq("parse_failed").sum())
    source_level = int(citation_audit["source_level_citation_count"].sum()) if not citation_audit.empty else 0
    citation_claim_count = int(len(claims))
    citations_with_page = int(citation_audit["citations_with_page_locator_count"].sum()) if not citation_audit.empty else 0
    table_full = int(table_audit["table_provenance_full_count"].sum()) if not table_audit.empty else 0
    table_partial = int(table_audit["table_provenance_partial_count"].sum()) if not table_audit.empty else 0
    table_missing = int(table_audit["table_provenance_missing_count"].sum()) if not table_audit.empty else 0
    blocking: list[str] = []
    warnings: list[str] = []
    if parser_ready < 85 or parse_failed > 5:
        blocking.append("parser_artifact_readiness_below_acceptance")
    if report_success < 85:
        blocking.append("report_success_below_acceptance")
    if source_level:
        blocking.append("source_level_citations_present")
    if table_partial or table_missing:
        warnings.append("table_provenance_non_blocking_gaps")
    strategy_diff = _git_diff_formal_strategy_files()
    if parser_ready >= 85 and parse_failed <= 5 and report_success >= 85 and source_level == 0 and strategy_diff == "":
        acceptance = "ready_for_90_stock_review_and_dashboard_integration"
    elif parser_ready < 85 or parse_failed > 5:
        acceptance = "parser_hardening_required"
    else:
        acceptance = "report_pipeline_hardening_required"
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "stock_count": stock_count,
        "local_pdf_stock_count": int(batch_manifest["local_pdf_available"].eq(True).sum()),
        "evidence_required_count": evidence_required,
        "cached_parser_artifact_reused_count": int(prep.get("cached_parser_artifact_reused_count", 0)),
        "cold_parse_required_count": int(prep.get("cold_parse_required_count", 0)),
        "cold_parse_success_count": int(prep.get("cold_parse_success_count", 0)),
        "cold_parse_failed_count": int(prep.get("cold_parse_failed_count", 0)),
        "docling_parse_success_count": parser_ready,
        "docling_parse_failed_count": parse_failed,
        "parser_artifact_ready_count": parser_ready,
        "parser_artifact_invalid_count": int(parser_audit["parser_artifact_status"].isin(["parse_failed", "invalid"]).sum()),
        "source_chunk_count": int(len(chunks)),
        "table_row_count": int(len(tables)),
        "citation_claim_count": citation_claim_count,
        "citations_with_page_locator_count": citations_with_page,
        "page_level_citation_row_count": int(citation_audit["page_level_citation_row_count"].sum()) if not citation_audit.empty else 0,
        "source_level_citation_count": source_level,
        "table_provenance_full_count": table_full,
        "table_provenance_partial_count": table_partial,
        "table_provenance_missing_count": table_missing,
        "report_success_count": report_success,
        "report_failed_count": report_failed,
        "total_runtime_seconds": round(total_runtime, 3),
        "cached_postprocess_runtime_seconds": round(total_runtime, 3),
        "cold_parse_runtime_seconds": float(prep.get("cold_parse_runtime_seconds") or 0),
        "runtime_measurement_scope": "cached_reuse_plus_cold_parse",
        "failed_stocks": parser_audit[parser_audit["parser_artifact_status"].isin(["parse_failed", "invalid"])]["stock_name"].tolist(),
        "degraded_stocks": status[status["report_status"].eq("partial_docling_enriched")]["stock_name"].tolist() if not status.empty else [],
        "citation_integrity_fail_count": int(citation_integrity.get("integrity_status", pd.Series(dtype=object)).eq("fail").sum()) if not citation_integrity.empty else 0,
        "table_quality_weak_count": int(table_quality.get("table_quality_status", pd.Series(dtype=object)).ne("usable").sum()) if not table_quality.empty else 0,
        "blocking_issues": blocking,
        "non_blocking_warnings": warnings,
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
        "strategy_file_diff_clean": strategy_diff == "",
        "formal_strategy_files_modified": strategy_diff != "",
        "acceptance_decision": acceptance,
    }


def _render_report(summary: dict[str, Any], report_audit: pd.DataFrame, parser_audit: pd.DataFrame) -> str:
    failed = parser_audit[parser_audit["parser_artifact_status"].isin(["parse_failed", "invalid"])]
    return f"""# Data-to-Brief Docling 90-stock full cold parse batch v1

Research-only full batch. No production signal, admission, scoring, strategy, or candidate-universe logic changed.

## Summary

- stock_count: {summary['stock_count']}
- local_pdf_stock_count: {summary['local_pdf_stock_count']}
- evidence_required_count: {summary['evidence_required_count']}
- cached_parser_artifact_reused_count: {summary['cached_parser_artifact_reused_count']}
- cold_parse_required_count: {summary['cold_parse_required_count']}
- cold_parse_success_count: {summary['cold_parse_success_count']}
- cold_parse_failed_count: {summary['cold_parse_failed_count']}
- parser_artifact_ready_count: {summary['parser_artifact_ready_count']}
- source_chunk_count: {summary['source_chunk_count']}
- table_row_count: {summary['table_row_count']}
- citation_claim_count: {summary['citation_claim_count']}
- citations_with_page_locator_count: {summary['citations_with_page_locator_count']}
- source_level_citation_count: {summary['source_level_citation_count']}
- report_success_count: {summary['report_success_count']}
- report_failed_count: {summary['report_failed_count']}
- cached_postprocess_runtime_seconds: {summary['cached_postprocess_runtime_seconds']}
- cold_parse_runtime_seconds: {summary['cold_parse_runtime_seconds']}

## Failed / Degraded Stocks

{failed[['stock_code', 'stock_name', 'parser_artifact_status', 'docling_status', 'issue_warning']].to_markdown(index=False) if not failed.empty else 'No parser-failed stocks.'}

## Report Generation Status

{report_audit['report_status'].value_counts().to_markdown()}

## Guardrails

- allowed_for_signal: false
- allowed_for_admission: false
- production_update: false
- strategy_file_diff_clean: {summary['strategy_file_diff_clean']}
- acceptance_decision: {summary['acceptance_decision']}
"""


def _copy_reports_to_90_names(output: Path, report_audit: pd.DataFrame) -> None:
    for _, row in report_audit.iterrows():
        code = str(row["stock_code"]).zfill(6)
        name = str(row["stock_name"])
        for subdir, ext in [("reports_md", "md"), ("reports_html", "html"), ("reports_pdf", "pdf")]:
            old = output / subdir / f"{code}_{name}_docling_10_stock_pilot_report.{ext}"
            new = output / subdir / f"{code}_{name}_docling_90_stock_full_batch_report.{ext}"
            if old.exists() and old != new:
                shutil.copyfile(old, new)


def _cold_artifacts_ready(cold_dir: Path, cold_stocks: list[dict[str, str]]) -> bool:
    summary = _read_json(cold_dir / "pilot_run_summary.json")
    chunks = _read_csv(cold_dir / "source_chunk_manifest.csv")
    if int(summary.get("pilot_stock_count") or 0) != len(cold_stocks):
        return False
    return _ready_stock_count(chunks) >= max(0, len(cold_stocks) - 5)


def _estimate_artifact_runtime_seconds(path: Path) -> float:
    if not path.exists():
        return 0.0
    files = [item for item in path.rglob("*") if item.is_file()]
    if len(files) < 2:
        return 0.0
    mtimes = [item.stat().st_mtime for item in files]
    return round(max(mtimes) - min(mtimes), 3)


def _ready_stock_count(chunks: pd.DataFrame) -> int:
    if chunks.empty or "stock_code" not in chunks:
        return 0
    return int(
        chunks.assign(_ready=chunks.get("page_locator", pd.Series(dtype=object)).fillna("").astype(str).str.len().gt(0))
        .groupby("stock_code")["_ready"]
        .any()
        .sum()
    )


def _load_90_stocks() -> list[dict[str, str]]:
    manifest = _read_csv(PRECHECK_OUTPUT_DIR / "batch_manifest.csv")
    if manifest.empty:
        raise FileNotFoundError("90-stock precheck batch_manifest.csv is required")
    rows = []
    for _, row in manifest.head(90).iterrows():
        code = _normalize_code(row.get("stock_code"))
        rows.append({"stock_code": code, "stock_name": str(row.get("stock_name") or ""), "asset_id": _asset_id(code)})
    return rows


def _asset_id(code: str) -> str:
    return f"{code}.SH" if code.startswith("6") else f"{code}.SZ"


def _normalize_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() and len(text) <= 6 else text


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    frame = pd.read_csv(path, dtype={"stock_code": str}, low_memory=False).fillna("")
    if "stock_code" in frame:
        frame["stock_code"] = frame["stock_code"].map(_normalize_code)
    return frame


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout or result.stderr or ""
