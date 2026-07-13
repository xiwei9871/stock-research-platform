from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

import pandas as pd

import stock_research.data_to_brief_docling_adapter_provenance_backfill_batch as batch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TASK_NAME = "data_to_brief_docling_30_stock_batch_pilot_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
THIRTY_STOCKS = [
    {"stock_code": "000400", "stock_name": "许继电气", "asset_id": "000400.SZ"},
    {"stock_code": "000682", "stock_name": "东方电子", "asset_id": "000682.SZ"},
    {"stock_code": "002171", "stock_name": "楚江新材", "asset_id": "002171.SZ"},
    {"stock_code": "002402", "stock_name": "和而泰", "asset_id": "002402.SZ"},
    {"stock_code": "002414", "stock_name": "高德红外", "asset_id": "002414.SZ"},
    {"stock_code": "003026", "stock_name": "中晶科技", "asset_id": "003026.SZ"},
    {"stock_code": "300316", "stock_name": "晶盛机电", "asset_id": "300316.SZ"},
    {"stock_code": "601100", "stock_name": "恒立液压", "asset_id": "601100.SH"},
    {"stock_code": "601689", "stock_name": "拓普集团", "asset_id": "601689.SH"},
    {"stock_code": "603200", "stock_name": "上海洗霸", "asset_id": "603200.SH"},
    {"stock_code": "603308", "stock_name": "应流股份", "asset_id": "603308.SH"},
    {"stock_code": "603396", "stock_name": "金辰股份", "asset_id": "603396.SH"},
    {"stock_code": "603501", "stock_name": "豪威集团", "asset_id": "603501.SH"},
    {"stock_code": "603530", "stock_name": "神马电力", "asset_id": "603530.SH"},
    {"stock_code": "603806", "stock_name": "福斯特", "asset_id": "603806.SH"},
    {"stock_code": "688002", "stock_name": "睿创微纳", "asset_id": "688002.SH"},
    {"stock_code": "688011", "stock_name": "新光光电", "asset_id": "688011.SH"},
    {"stock_code": "688019", "stock_name": "安集科技", "asset_id": "688019.SH"},
    {"stock_code": "688120", "stock_name": "华海清科", "asset_id": "688120.SH"},
    {"stock_code": "688233", "stock_name": "神工股份", "asset_id": "688233.SH"},
    {"stock_code": "688261", "stock_name": "东微半导", "asset_id": "688261.SH"},
    {"stock_code": "688361", "stock_name": "中科飞测", "asset_id": "688361.SH"},
    {"stock_code": "688486", "stock_name": "龙迅股份", "asset_id": "688486.SH"},
    {"stock_code": "688600", "stock_name": "皖仪科技", "asset_id": "688600.SH"},
    {"stock_code": "002371", "stock_name": "北方华创", "asset_id": "002371.SZ"},
    {"stock_code": "688012", "stock_name": "中微公司", "asset_id": "688012.SH"},
    {"stock_code": "002222", "stock_name": "福晶科技", "asset_id": "002222.SZ"},
    {"stock_code": "002028", "stock_name": "思源电气", "asset_id": "002028.SZ"},
    {"stock_code": "002121", "stock_name": "科陆电子", "asset_id": "002121.SZ"},
    {"stock_code": "002176", "stock_name": "江特电机", "asset_id": "002176.SZ"},
]


def run_data_to_brief_docling_30_stock_batch_pilot(
    *,
    output_dir: str | Path = OUTPUT_DIR,
) -> dict[str, Any]:
    output = Path(output_dir)
    parser_cache_exists = (output / "parser_artifacts/source_chunk_manifest.csv").exists() and (
        output / "parser_artifacts/pilot_run_summary.json"
    ).exists()
    started = time.perf_counter()
    old_task = batch.TASK_NAME
    old_stocks = batch.PILOT_STOCKS
    try:
        batch.TASK_NAME = TASK_NAME
        batch.PILOT_STOCKS = THIRTY_STOCKS
        batch.run_docling_adapter_provenance_backfill_10_stock_batch(output_dir=output, sleep_seconds=0.0)
    finally:
        batch.TASK_NAME = old_task
        batch.PILOT_STOCKS = old_stocks
    total_runtime = time.perf_counter() - started

    status = _read_csv(output / "batch_report_status.csv")
    chunks = _read_csv(output / "batch_source_chunk_manifest.csv")
    tables = _read_csv(output / "batch_table_inventory.csv")
    claims = _read_csv(output / "batch_claim_citation_map.csv")
    parser_quality = _read_csv(output / "batch_parser_quality_audit.csv")
    citation_audit = _read_csv(output / "batch_citation_integrity_audit.csv")
    acquisition = _read_csv(output / "source_acquisition/yanbaoke_source_acquisition_audit.csv")

    _copy_stock_reports_to_30_names(output, status)
    _copy_dashboard_manifest_to_30(output)
    runtime_audit = _runtime_audit(status, total_runtime)
    runtime_audit.to_csv(output / "per_stock_runtime_audit.csv", index=False)

    summary = _build_summary(
        status=status,
        chunks=chunks,
        tables=tables,
        claims=claims,
        parser_quality=parser_quality,
        citation_audit=citation_audit,
        acquisition=acquisition,
        total_runtime=total_runtime,
        cached_parser_artifacts_used=parser_cache_exists,
    )
    _write_json(output / "docling_30_stock_batch_pilot_summary.json", summary)
    (output / "data_to_brief_docling_30_stock_batch_pilot_v1_report.md").write_text(
        _render_report(summary, status, acquisition),
        encoding="utf-8",
    )
    return {"summary": summary}


def _build_summary(
    *,
    status: pd.DataFrame,
    chunks: pd.DataFrame,
    tables: pd.DataFrame,
    claims: pd.DataFrame,
    parser_quality: pd.DataFrame,
    citation_audit: pd.DataFrame,
    acquisition: pd.DataFrame,
    total_runtime: float,
    cached_parser_artifacts_used: bool,
) -> dict[str, Any]:
    local_pdf = int(status["has_local_pdf"].eq(True).sum()) if not status.empty else 0
    missing_pdf = int(status["has_local_pdf"].eq(False).sum()) if not status.empty else 0
    evidence_required = int(status["report_status"].eq("evidence_required").sum()) if not status.empty else 0
    parse_success = int(status["report_status"].isin(["page_level_docling_enriched", "partial_docling_enriched", "source_level_docling_enriched"]).sum()) if not status.empty else 0
    parse_failed = int(parser_quality["docling_status"].isin(["parse_error", "import_error"]).sum()) if not parser_quality.empty else 0
    page_locator_count = int(chunks["page_locator"].fillna("").astype(str).str.len().gt(0).sum()) if not chunks.empty and "page_locator" in chunks else 0
    citation_claim_count = int(len(claims))
    citations_with_page_locator = int(claims["page_locator"].fillna("").astype(str).str.len().gt(0).sum()) if not claims.empty and "page_locator" in claims else 0
    source_level = int(claims["citation_granularity"].eq("source_level").sum()) if not claims.empty and "citation_granularity" in claims else 0
    table_full, table_partial, table_missing = _table_provenance_counts(tables)
    page_level_reports = int(status["report_status"].eq("page_level_docling_enriched").sum()) if not status.empty else 0
    if page_level_reports >= 24:
        acceptance = "ready_for_90_stock_batch_precheck"
    elif evidence_required >= parse_failed:
        acceptance = "conditional_pdf_discovery_required"
    else:
        acceptance = "conditional_parser_tuning_required"
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "stock_count": int(len(status)),
        "local_pdf_stock_count": local_pdf,
        "missing_pdf_stock_count": missing_pdf,
        "evidence_required_count": evidence_required,
        "docling_parse_success_count": parse_success,
        "docling_parse_failed_count": parse_failed,
        "source_chunk_count": int(len(chunks)),
        "table_row_count": int(len(tables)),
        "citation_claim_count": citation_claim_count,
        "page_locator_count": page_locator_count,
        "citations_with_page_locator_count": citations_with_page_locator,
        "source_level_citation_count": source_level,
        "table_provenance_full_count": table_full,
        "table_provenance_partial_count": table_partial,
        "table_provenance_missing_count": table_missing,
        "total_runtime_seconds": round(total_runtime, 3),
        "runtime_measurement_scope": "cached_postprocess" if cached_parser_artifacts_used else "cold_docling_batch_run",
        "cached_parser_artifacts_used": bool(cached_parser_artifacts_used),
        "avg_runtime_seconds_per_stock": round(total_runtime / max(1, len(status)), 3),
        "unresolved_evidence_gaps": evidence_required,
        "source_acquisition_downloaded_count": int(acquisition["status"].eq("downloaded").sum()) if not acquisition.empty and "status" in acquisition else 0,
        "citation_integrity_fail_count": int(citation_audit["integrity_status"].eq("fail").sum()) if not citation_audit.empty else 0,
        "adapter_emits_page_provenance": page_locator_count > 0,
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
        "strategy_file_diff_clean": _strategy_diff_clean(),
        "formal_strategy_files_modified": not _strategy_diff_clean(),
        "acceptance_decision": acceptance,
    }


def _table_provenance_counts(tables: pd.DataFrame) -> tuple[int, int, int]:
    if tables.empty:
        return 0, 0, 0
    page = tables.get("page_locator", pd.Series(dtype=object)).fillna("").astype(str).str.len().gt(0)
    row = tables.get("row_count", pd.Series(dtype=object)).fillna("").astype(str).str.len().gt(0)
    col = tables.get("column_count", pd.Series(dtype=object)).fillna("").astype(str).str.len().gt(0)
    full = int((page & row & col).sum())
    partial = int(((page | row | col) & ~(page & row & col)).sum())
    missing = int((~(page | row | col)).sum())
    return full, partial, missing


def _runtime_audit(status: pd.DataFrame, total_runtime: float) -> pd.DataFrame:
    rows = []
    per_stock = round(total_runtime / max(1, len(status)), 3)
    for _, row in status.iterrows():
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "estimated_runtime_seconds": per_stock,
                "report_status": row["report_status"],
                "blocker_reason": row.get("blocker_reason", ""),
            }
        )
    return pd.DataFrame(rows)


def _copy_stock_reports_to_30_names(output: Path, status: pd.DataFrame) -> None:
    for _, row in status.iterrows():
        code = str(row["stock_code"]).zfill(6)
        name = str(row["stock_name"])
        for subdir, ext in [("reports_md", "md"), ("reports_html", "html"), ("reports_pdf", "pdf")]:
            old = output / subdir / f"{code}_{name}_docling_10_stock_pilot_report.{ext}"
            new = output / subdir / f"{code}_{name}_docling_30_stock_pilot_report.{ext}"
            if old.exists() and old != new:
                shutil.copyfile(old, new)


def _copy_dashboard_manifest_to_30(output: Path) -> None:
    old = output / "dashboard_docling_10_stock_manifest_preview.csv"
    new = output / "dashboard_docling_30_stock_manifest_preview.csv"
    if not old.exists():
        return
    frame = pd.read_csv(old, dtype={"stock_code": str})
    for column in ["report_md_path", "report_html_path", "report_pdf_path"]:
        if column in frame:
            frame[column] = frame[column].astype(str).str.replace("_docling_10_stock_pilot_report", "_docling_30_stock_pilot_report", regex=False)
    frame.to_csv(new, index=False)


def _render_report(summary: dict[str, Any], status: pd.DataFrame, acquisition: pd.DataFrame) -> str:
    return f"""# Data-to-Brief Docling 30-stock batch pilot v1

Research-only Docling batch pilot. No production signal, admission, scoring, strategy, or candidate-universe logic changed.

## Summary

- stock_count: {summary['stock_count']}
- local_pdf_stock_count: {summary['local_pdf_stock_count']}
- missing_pdf_stock_count: {summary['missing_pdf_stock_count']}
- evidence_required_count: {summary['evidence_required_count']}
- docling_parse_success_count: {summary['docling_parse_success_count']}
- docling_parse_failed_count: {summary['docling_parse_failed_count']}
- source_chunk_count: {summary['source_chunk_count']}
- table_row_count: {summary['table_row_count']}
- citation_claim_count: {summary['citation_claim_count']}
- citations_with_page_locator_count: {summary['citations_with_page_locator_count']}
- source_level_citation_count: {summary['source_level_citation_count']}
- total_runtime_seconds: {summary['total_runtime_seconds']}

## Per-stock Status

{status[['stock_code', 'stock_name', 'has_local_pdf', 'report_status', 'citation_count', 'page_level_citation_count', 'blocker_reason']].to_markdown(index=False)}

## Source Acquisition

{acquisition[['stock_code', 'stock_name', 'source_acquisition_status', 'status', 'error_type']].to_markdown(index=False) if not acquisition.empty else 'No source acquisition rows.'}

## Scaling Readiness

If at least 24 of 30 stocks produce page-level enriched reports, this pilot is ready for a 90-stock precheck. Missing PDF failures should be handled by source discovery. Parser/runtime failures should be handled by batching and resource tuning. Weak table quality should remain a separate fallback track when text citation provenance is stable.

## Guardrails

- allowed_for_signal: false
- allowed_for_admission: false
- production_update: false
- strategy_file_diff_clean: {summary['strategy_file_diff_clean']}
- acceptance_decision: {summary['acceptance_decision']}
"""


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path, dtype={"stock_code": str}, low_memory=False)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _strategy_diff_clean() -> bool:
    result = batch._git_diff_formal_strategy_files()
    return result == ""
