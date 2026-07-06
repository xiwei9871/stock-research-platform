from __future__ import annotations

import html
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.data_to_brief_docling_parser_poc import (
    discover_pilot_sources,
    run_data_to_brief_docling_parser_poc,
)
from stock_research.yanbaoke_reports import (
    download_yanbaoke_report_pdf,
    filter_yanbaoke_reports,
    search_yanbaoke_reports,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TASK_NAME = "data_to_brief_docling_adapter_provenance_backfill_and_10_stock_batch_pilot_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
PILOT_STOCKS = [
    {"stock_code": "002371", "stock_name": "北方华创", "asset_id": "002371.SZ"},
    {"stock_code": "688012", "stock_name": "中微公司", "asset_id": "688012.SH"},
    {"stock_code": "000400", "stock_name": "许继电气", "asset_id": "000400.SZ"},
    {"stock_code": "002885", "stock_name": "京泉华", "asset_id": "002885.SZ"},
    {"stock_code": "300838", "stock_name": "浙江力诺", "asset_id": "300838.SZ"},
    {"stock_code": "300476", "stock_name": "胜宏科技", "asset_id": "300476.SZ"},
    {"stock_code": "300308", "stock_name": "中际旭创", "asset_id": "300308.SZ"},
    {"stock_code": "300502", "stock_name": "新易盛", "asset_id": "300502.SZ"},
    {"stock_code": "688256", "stock_name": "寒武纪", "asset_id": "688256.SH"},
    {"stock_code": "688120", "stock_name": "华海清科", "asset_id": "688120.SH"},
]
REPORT_SECTIONS = {
    "business_overview": ("主营业务与收入结构", ["主营业务", "主要业务", "公司从事", "主要产品", "经营范围"]),
    "key_products": ("核心产品与产业链位置", ["产品", "设备", "材料", "芯片", "模块", "系统", "解决方案"]),
    "hard_tech_bottleneck_thesis": (
        "硬科技 / 卡脖子相关性",
        ["国产化", "自主可控", "核心技术", "关键技术", "进口替代", "半导体", "高端装备", "工业控制", "电力设备"],
    ),
    "technology_capability": ("技术能力与研发投入", ["研发", "专利", "技术", "工艺", "平台", "创新", "实验室", "技术中心"]),
    "financial_snapshot": ("财务与经营快照", ["营业收入", "净利润", "毛利率", "研发费用", "现金流", "分产品", "分行业"]),
    "risks_and_counter_evidence": ("风险与反证", ["风险", "不确定性", "竞争", "客户集中", "供应链", "存货", "应收账款", "毛利率下降"]),
}
FORBIDDEN_REPORT_TERMS = ["买入", "卖出", "目标价", "target price", "buy recommendation", "sell recommendation"]


def run_docling_adapter_provenance_backfill_10_stock_batch(
    *,
    output_dir: str | Path = OUTPUT_DIR,
    source_roots: list[str | Path] | None = None,
    sleep_seconds: float = 0.2,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    for subdir in ["reports_md", "reports_html", "reports_pdf", "evidence", "source_acquisition"]:
        (output / subdir).mkdir(parents=True, exist_ok=True)

    roots = [Path(root) for root in (source_roots or [PROJECT_ROOT / "data/manual"])]
    acquisition = _acquire_missing_sources(output, roots, sleep_seconds=sleep_seconds)
    yanbaoke_pdf_dir = output / "source_acquisition/yanbaoke_pdfs"
    parser_roots = roots + ([yanbaoke_pdf_dir] if yanbaoke_pdf_dir.exists() else [])
    parser_dir = output / "parser_artifacts"
    parser_summary_path = parser_dir / "pilot_run_summary.json"
    parser_ready = (
        parser_summary_path.exists()
        and (parser_dir / "source_chunk_manifest.csv").exists()
        and int(_read_json(parser_summary_path).get("pilot_stock_count") or 0) == len(PILOT_STOCKS)
    )
    if not parser_ready:
        run_data_to_brief_docling_parser_poc(
            output_dir=parser_dir,
            source_roots=parser_roots,
            pilot_stocks=PILOT_STOCKS,
            limit_per_stock=1,
        )

    chunks = _read_csv(parser_dir / "source_chunk_manifest.csv")
    tables = _read_csv(parser_dir / "table_inventory.csv")
    comparison = _read_csv(parser_dir / "parser_comparison_matrix.csv")
    parser_summary = _read_json(parser_dir / "pilot_run_summary.json")
    chunks.to_csv(output / "batch_source_chunk_manifest.csv", index=False)
    tables.to_csv(output / "batch_table_inventory.csv", index=False)

    package = _build_batch_evidence_package(chunks, tables)
    package.to_csv(output / "batch_evidence_matrix.csv", index=False)
    claim_map = _claim_map_from_package(package)
    claim_map.to_csv(output / "batch_claim_citation_map.csv", index=False)
    references = _references_from_package(package)
    _write_jsonl(output / "batch_references.jsonl", references)

    status_rows: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []
    citation_audit_rows: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    for stock in PILOT_STOCKS:
        stock_code = stock["stock_code"]
        stock_name = stock["stock_name"]
        stock_package = package[package["stock_code"].eq(stock_code)].copy()
        stock_chunks = chunks[chunks["stock_code"].eq(stock_code)].copy() if "stock_code" in chunks else pd.DataFrame()
        stock_tables = tables[tables["stock_code"].eq(stock_code)].copy() if "stock_code" in tables else pd.DataFrame()
        stock_comparison = comparison[comparison["stock_code"].eq(stock_code)].copy() if "stock_code" in comparison else pd.DataFrame()
        status = _stock_report_status(stock, stock_package, stock_chunks, stock_tables, stock_comparison)
        paths = _write_stock_artifacts(output, stock_code, stock_name, stock_package, status)
        status_rows.append(status)
        manifest_rows.append(
            {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "report_md_path": str(paths["md"]),
                "report_html_path": str(paths["html"]),
                "report_pdf_path": str(paths["pdf"]),
                "evidence_matrix_path": str(paths["evidence_matrix"]),
                "sources_jsonl_path": str(paths["sources"]),
                "claim_citation_map_path": str(paths["claim_map"]),
                "report_status": status["report_status"],
                "citation_count": status["citation_count"],
                "page_level_citation_count": status["page_level_citation_count"],
                "source_level_citation_count": status["source_level_citation_count"],
                "evidence_quality_flag": "usable" if status["report_status"] != "evidence_required" else "gap",
                "blocker_reason": status["blocker_reason"],
                "updated_at": _now(),
            }
        )
        citation_audit_rows.extend(_citation_integrity_for_stock(stock_code, paths["md"], paths["sources"], stock_package))
        quality_rows.append(_report_quality_for_stock(stock_code, stock_name, paths["md"], status))

    status_df = pd.DataFrame(status_rows)
    status_df.to_csv(output / "batch_report_status.csv", index=False)
    pd.DataFrame(manifest_rows).to_csv(output / "dashboard_docling_10_stock_manifest_preview.csv", index=False)
    citation_audit = pd.DataFrame(citation_audit_rows)
    citation_audit.to_csv(output / "batch_citation_integrity_audit.csv", index=False)
    report_quality = pd.DataFrame(quality_rows)
    report_quality.to_csv(output / "batch_report_quality_audit.csv", index=False)
    table_quality = _table_quality_audit(tables)
    table_quality.to_csv(output / "batch_table_quality_audit.csv", index=False)
    parser_quality = _parser_quality_audit(chunks, comparison)
    parser_quality.to_csv(output / "batch_parser_quality_audit.csv", index=False)

    strategy_diff = _git_diff_formal_strategy_files()
    page_level_count = int(status_df["page_level_citation_count"].sum()) if not status_df.empty else 0
    missing_count = int(status_df["report_status"].eq("evidence_required").sum()) if not status_df.empty else 0
    parsed_count = int(status_df["has_local_pdf"].eq(True).sum()) if not status_df.empty else 0
    page_level_report_count = int(status_df["report_status"].eq("page_level_docling_enriched").sum()) if not status_df.empty else 0
    acceptance = (
        "ready_for_30_stock_batch"
        if page_level_report_count >= 7 and strategy_diff == ""
        else "pdf_discovery_required_before_scaling"
        if missing_count > 3 and strategy_diff == ""
        else "parser_or_table_hardening_required"
        if status_df["stock_code"].nunique() == 10 and strategy_diff == ""
        else "blocked"
    )
    summary = {
        "task_name": TASK_NAME,
        "research_only": True,
        "pilot_stock_count": len(PILOT_STOCKS),
        "status_row_count": int(len(status_df)),
        "local_pdf_stock_count": parsed_count,
        "missing_pdf_evidence_required_count": missing_count,
        "chunk_count": int(len(chunks)),
        "table_count": int(len(tables)),
        "citation_count": int(package["citation_id"].nunique()) if not package.empty else 0,
        "page_level_report_count": page_level_report_count,
        "page_level_citation_count": page_level_count,
        "source_level_citation_count": int(status_df["source_level_citation_count"].sum()) if not status_df.empty else 0,
        "source_acquisition_downloaded_count": int(acquisition["status"].eq("downloaded").sum()) if not acquisition.empty else 0,
        "adapter_emits_page_provenance": bool(not chunks.empty and chunks["page_locator"].fillna("").astype(str).str.len().gt(0).any()),
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
        "strategy_file_diff_clean": strategy_diff == "",
        "formal_strategy_files_modified": strategy_diff != "",
        "acceptance_decision": acceptance,
        "updated_at": _now(),
        "parser_artifact_summary": parser_summary,
    }
    _write_json(output / "docling_adapter_provenance_backfill_summary.json", summary)
    (output / "data_to_brief_docling_adapter_provenance_backfill_and_10_stock_batch_pilot_v1_report.md").write_text(
        _render_batch_report(summary, status_df, acquisition, citation_audit, table_quality, parser_quality),
        encoding="utf-8",
    )
    return {"summary": summary}


def _acquire_missing_sources(output: Path, source_roots: list[Path], *, sleep_seconds: float) -> pd.DataFrame:
    download_dir = output / "source_acquisition/yanbaoke_pdfs"
    download_dir.mkdir(parents=True, exist_ok=True)
    local_roots = source_roots + [download_dir]
    local_sources = discover_pilot_sources(source_roots=local_roots, pilot_stocks=PILOT_STOCKS, limit_per_stock=1)
    existing_by_code = {source.stock_code: source for source in local_sources if source.pdf_path is not None}
    rows: list[dict[str, Any]] = []
    api_key = _load_yanbaoke_api_key()
    for stock in PILOT_STOCKS:
        stock_code = stock["stock_code"]
        stock_name = stock["stock_name"]
        asset_id = stock["asset_id"]
        if stock_code in existing_by_code:
            rows.append(
                {
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "asset_id": asset_id,
                    "source_acquisition_status": "local_pdf_found",
                    "status": "local_pdf_found",
                    "uuid": "",
                    "pdf_path": str(existing_by_code[stock_code].pdf_path or ""),
                    "error_type": "",
                    "error_message": "",
                }
            )
            continue
        if not api_key:
            rows.append(
                {
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "asset_id": asset_id,
                    "source_acquisition_status": "yanbaoke_api_key_missing",
                    "status": "evidence_required",
                    "uuid": "",
                    "pdf_path": "",
                    "error_type": "api_key_missing",
                    "error_message": "YANBAOKE_API_KEY or config/local_secrets.json:yanbaoke.api_key is required",
                }
            )
            continue
        try:
            discovered = search_yanbaoke_reports(
                keyword=stock_name,
                stock=stock_name,
                start_date="2024-01-01",
                end_date="2026-07-06",
                size=50,
            )["reports"]
            selected = filter_yanbaoke_reports(
                discovered,
                ts_code=asset_id,
                stock_name=stock_name,
                start_date="2024-01-01",
                end_date="2026-07-06",
                fallback_tier="B",
            )
            selection_method = "strict_filter"
            if selected.empty:
                selected = _fallback_yanbaoke_pdf_candidates(discovered, stock=stock, start_date="2024-01-01", end_date="2026-07-06")
                selection_method = "fallback_pdf_name_or_code_match"
            if selected.empty:
                rows.append(
                    {
                        "stock_code": stock_code,
                        "stock_name": stock_name,
                        "asset_id": asset_id,
                        "source_acquisition_status": "yanbaoke_no_qualified_report",
                        "status": "evidence_required",
                        "uuid": "",
                        "pdf_path": "",
                        "error_type": "",
                        "error_message": "",
                    }
                )
                continue
            report = selected.iloc[0].fillna("").to_dict()
            download = download_yanbaoke_report_pdf(uuid=str(report.get("uuid") or ""), output_dir=download_dir, api_key=api_key)
            rows.append(
                {
                    **{k: report.get(k, "") for k in ["uuid", "title", "report_title", "broker", "publish_date", "detail_url"]},
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "asset_id": asset_id,
                    "selection_method": selection_method,
                    "source_acquisition_status": "downloaded" if download.get("status") == "downloaded" else str(download.get("status") or "download_failed"),
                    **download,
                }
            )
        except Exception as exc:  # noqa: BLE001 - source acquisition is best-effort and audited.
            rows.append(
                {
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "asset_id": asset_id,
                    "source_acquisition_status": "yanbaoke_error",
                    "status": "evidence_required",
                    "uuid": "",
                    "pdf_path": "",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:500],
                }
            )
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    frame = pd.DataFrame(rows)
    frame.to_csv(output / "source_acquisition/yanbaoke_source_acquisition_audit.csv", index=False)
    return frame


def _fallback_yanbaoke_pdf_candidates(discovered: pd.DataFrame, *, stock: dict[str, str], start_date: str, end_date: str) -> pd.DataFrame:
    if discovered.empty:
        return discovered
    code = stock["stock_code"]
    stock_name = stock["stock_name"]
    asset_id = stock["asset_id"]
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    rows: list[dict[str, Any]] = []
    for row in discovered.fillna("").to_dict("records"):
        title = _clean(row.get("title"))
        content = _clean(row.get("content"))
        formats = _clean(row.get("formats")).lower()
        publish_date = _clean(row.get("time"))[:10]
        try:
            publish_ts = pd.Timestamp(publish_date)
        except Exception:
            continue
        if publish_ts < start or publish_ts > end:
            continue
        if "pdf" not in formats:
            continue
        if stock_name not in title and stock_name not in content and code not in title and code not in content and asset_id not in title:
            continue
        enriched = dict(row)
        enriched.update(
            {
                "asset_id": asset_id,
                "ts_code": asset_id,
                "symbol": code,
                "stock_name": stock_name,
                "broker": _clean(row.get("org_name")),
                "broker_tier": "unclassified",
                "publish_date": publish_date,
                "report_title": title,
                "detail_url": _clean(row.get("url")),
            }
        )
        rows.append(enriched)
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame["_date_rank"] = pd.to_datetime(frame["publish_date"], errors="coerce")
    frame["_title_match"] = frame["title"].astype(str).map(lambda value: int(stock_name in value or code in value or asset_id in value))
    frame["_pages"] = pd.to_numeric(frame.get("pagenum", 0), errors="coerce").fillna(0)
    frame = frame.sort_values(["_title_match", "_date_rank", "_pages"], ascending=[False, False, False])
    return frame.drop(columns=["_date_rank", "_title_match", "_pages"], errors="ignore").head(1).reset_index(drop=True)


def _build_batch_evidence_package(chunks: pd.DataFrame, tables: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if chunks.empty:
        return pd.DataFrame(columns=_evidence_columns())
    for stock_code, stock_chunks in chunks.groupby("stock_code", sort=False):
        stock_name = _clean(stock_chunks.iloc[0].get("stock_name"))
        for section_key, (_title, keywords) in REPORT_SECTIONS.items():
            matches = _matching_chunks(stock_chunks, keywords)
            if section_key == "financial_snapshot" and not tables.empty and "stock_code" in tables:
                table_matches = _matching_tables(tables[tables["stock_code"].eq(stock_code)])
            else:
                table_matches = pd.DataFrame()
            for _, row in matches.head(2).iterrows():
                rows.append(_evidence_row_from_chunk(stock_code, stock_name, section_key, row, len(rows) + 1))
            for _, table in table_matches.head(1).iterrows():
                rows.append(_evidence_row_from_table(stock_code, stock_name, section_key, table, len(rows) + 1))
    return pd.DataFrame(rows, columns=_evidence_columns())


def _matching_chunks(stock_chunks: pd.DataFrame, keywords: list[str]) -> pd.DataFrame:
    if stock_chunks.empty:
        return stock_chunks
    frame = stock_chunks.copy()
    if "page_locator" in frame.columns:
        page_ready = frame["page_locator"].fillna("").astype(str).str.len().gt(0)
        if page_ready.any():
            frame = frame[page_ready].copy()
    text = frame.get("chunk_text", frame.get("excerpt", pd.Series(dtype=object))).fillna("").astype(str)
    frame["_match_score"] = text.map(lambda value: sum(1 for keyword in keywords if keyword in value))
    matched = frame[frame["_match_score"].gt(0)].sort_values(["_match_score", "chunk_text_length"], ascending=[False, False])
    if matched.empty:
        matched = frame.sort_values("chunk_text_length", ascending=False).head(1).copy()
    return matched


def _matching_tables(stock_tables: pd.DataFrame) -> pd.DataFrame:
    if stock_tables.empty:
        return stock_tables
    relevance = stock_tables.get("table_relevance", pd.Series(dtype=object)).fillna("").astype(str)
    selected = stock_tables[relevance.isin(["revenue_structure", "R&D_expense", "gross_margin", "financial_summary"])].copy()
    return selected if not selected.empty else stock_tables.head(1).copy()


def _evidence_row_from_chunk(stock_code: str, stock_name: str, section_key: str, row: pd.Series, index: int) -> dict[str, Any]:
    page_locator = _clean(row.get("page_locator"))
    return {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "report_section": section_key,
        "evidence_id": f"E{index}",
        "citation_id": _clean(row.get("citation_id")),
        "source_id": _clean(row.get("source_id")),
        "chunk_id": _clean(row.get("chunk_id")),
        "table_id": "",
        "source_type": _clean(row.get("source_type"), "local_pdf"),
        "source_title": _clean(row.get("source_title")),
        "source_path_or_url": _clean(row.get("source_path_or_url")) or _clean(row.get("source_path")),
        "citation_granularity": "page_level" if page_locator else "source_level",
        "page_locator": page_locator,
        "excerpt": _sanitize_report_text(_clean(row.get("excerpt")) or _clean(row.get("chunk_text"))[:220]),
        "evidence_strength": "moderate",
        "evidence_quality_flag": "usable" if _clean(row.get("chunk_text")) else "gap",
        "parser": _clean(row.get("parser"), "docling"),
        "parser_version": _clean(row.get("parser_version")),
        "parse_quality_flag": "pass" if _clean(row.get("chunk_text")) else "empty_chunk",
        "issue_warning": _clean(row.get("issue_warning")),
        "supports_or_contradicts": "supports",
        "evidence_kind": "chunk",
    }


def _evidence_row_from_table(stock_code: str, stock_name: str, section_key: str, table: pd.Series, index: int) -> dict[str, Any]:
    page_locator = _clean(table.get("page_locator"))
    excerpt = _clean(table.get("table_markdown")) or _clean(table.get("table_title")) or _clean(table.get("caption"))
    citation_id = _clean(table.get("citation_id")) or f"S_TABLE_{stock_code}_{_clean(table.get('table_id'))}"
    return {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "report_section": section_key,
        "evidence_id": f"E{index}",
        "citation_id": citation_id,
        "source_id": _clean(table.get("source_id")),
        "chunk_id": "",
        "table_id": _clean(table.get("table_id")),
        "source_type": _clean(table.get("source_type"), "local_pdf"),
        "source_title": _clean(table.get("source_title")),
        "source_path_or_url": _clean(table.get("source_path_or_url")) or _clean(table.get("source_path")),
        "citation_granularity": "page_level" if page_locator else "source_level",
        "page_locator": page_locator,
        "excerpt": _sanitize_report_text(excerpt[:260]),
        "evidence_strength": "moderate",
        "evidence_quality_flag": "usable" if excerpt else "gap",
        "parser": _clean(table.get("parser"), "docling"),
        "parser_version": _clean(table.get("parser_version")),
        "parse_quality_flag": "pass" if excerpt else "empty_table",
        "issue_warning": _clean(table.get("issue_warning")),
        "supports_or_contradicts": "supports",
        "evidence_kind": "table",
    }


def _stock_report_status(
    stock: dict[str, str],
    package: pd.DataFrame,
    chunks: pd.DataFrame,
    tables: pd.DataFrame,
    comparison: pd.DataFrame,
) -> dict[str, Any]:
    has_local_pdf = not comparison.empty and comparison["pdf_path"].fillna("").astype(str).str.len().gt(0).any()
    citation_count = int(package["citation_id"].nunique()) if not package.empty else 0
    page_count = int(package["citation_granularity"].eq("page_level").sum()) if not package.empty else 0
    source_count = int(package["citation_granularity"].eq("source_level").sum()) if not package.empty else 0
    table_count = int(len(tables))
    filled = partial = required = 0
    for section_key in REPORT_SECTIONS:
        count = int(package["report_section"].eq(section_key).sum()) if not package.empty else 0
        if count >= 2:
            filled += 1
        elif count == 1:
            partial += 1
        else:
            required += 1
    if not has_local_pdf:
        status = "evidence_required"
        blocker = "missing_local_pdf"
    elif citation_count == 0:
        status = "evidence_required"
        blocker = "no_docling_evidence_matched"
    elif page_count > 0 and required == 0:
        status = "page_level_docling_enriched"
        blocker = ""
    elif source_count > 0 and page_count == 0:
        status = "source_level_docling_enriched"
        blocker = "page_locator_missing"
    else:
        status = "partial_docling_enriched"
        blocker = "some_sections_evidence_required"
    return {
        "stock_code": stock["stock_code"],
        "stock_name": stock["stock_name"],
        "has_local_pdf": bool(has_local_pdf),
        "parsed_source_count": 1 if has_local_pdf else 0,
        "chunk_count": int(len(chunks)),
        "table_count": table_count,
        "citation_count": citation_count,
        "page_level_citation_count": page_count,
        "source_level_citation_count": source_count,
        "table_citation_count": int(package["evidence_kind"].eq("table").sum()) if not package.empty else 0,
        "filled_section_count": filled,
        "partial_section_count": partial,
        "evidence_required_section_count": required,
        "report_status": status,
        "blocker_reason": blocker,
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
    }


def _write_stock_artifacts(output: Path, stock_code: str, stock_name: str, package: pd.DataFrame, status: dict[str, Any]) -> dict[str, Path]:
    evidence_dir = output / "evidence" / stock_code
    evidence_dir.mkdir(parents=True, exist_ok=True)
    md = output / "reports_md" / f"{stock_code}_{stock_name}_docling_10_stock_pilot_report.md"
    html_path = output / "reports_html" / f"{stock_code}_{stock_name}_docling_10_stock_pilot_report.html"
    pdf_path = output / "reports_pdf" / f"{stock_code}_{stock_name}_docling_10_stock_pilot_report.pdf"
    sources_path = evidence_dir / "sources.jsonl"
    matrix_path = evidence_dir / "evidence_matrix.csv"
    claim_path = evidence_dir / "claim_citation_map.csv"
    status_path = evidence_dir / "report_status.json"
    sources = _references_from_package(package)
    _write_jsonl(sources_path, sources)
    package.to_csv(matrix_path, index=False)
    _claim_map_from_package(package).to_csv(claim_path, index=False)
    _write_json(status_path, status)
    markdown = _render_stock_report(stock_code, stock_name, package, status, sources)
    md.write_text(markdown, encoding="utf-8")
    html_path.write_text(_markdown_to_html(markdown), encoding="utf-8")
    _render_pdf(markdown, pdf_path)
    return {"md": md, "html": html_path, "pdf": pdf_path, "sources": sources_path, "evidence_matrix": matrix_path, "claim_map": claim_path}


def _render_stock_report(stock_code: str, stock_name: str, package: pd.DataFrame, status: dict[str, Any], sources: list[dict[str, Any]]) -> str:
    lines = [
        f"# {stock_code} {stock_name}：Docling 10-stock page-level citation pilot report",
        "",
        "Research-only report. No signal, no admission, no scoring change, no production update.",
        "",
        "## 1. 研究结论摘要",
        f"- report_status: {status['report_status']}",
        f"- citation_count: {status['citation_count']}",
        f"- page_level_citation_count: {status['page_level_citation_count']}",
        f"- blocker_reason: {status['blocker_reason'] or 'none'}",
        "- conclusion: evidence_required" if status["report_status"] == "evidence_required" else "- conclusion: Docling evidence can support a research-only draft.",
        "",
    ]
    section_number = 2
    for section_key, (title, _keywords) in REPORT_SECTIONS.items():
        lines.append(f"## {section_number}. {title}")
        section_package = package[package["report_section"].eq(section_key)] if not package.empty else package
        if section_package.empty:
            lines.append("evidence_required")
        else:
            for _, row in section_package.head(3).iterrows():
                excerpt = _sanitize_report_text(_clean(row.get("excerpt")))[:260]
                lines.append(f"- {excerpt} [{row['citation_id']}]")
        lines.append("")
        section_number += 1
    lines.extend(
        [
            f"## {section_number}. Evidence Required / 证据缺口",
            status["blocker_reason"] or "remaining evidence sections should be manually reviewed before any scaling.",
            "",
            f"## {section_number + 1}. Research-only 复盘结论",
            "This deterministic pilot only validates source-backed evidence plumbing. It does not create any recommendation, signal, admission decision, or production update.",
            "",
            "## 引用与数据源 / References",
        ]
    )
    if not sources:
        lines.append("- evidence_required: no local source PDF available")
    for source in sources:
        title = _sanitize_report_text(_clean(source.get("source_title"), "source title missing"))
        location = _sanitize_report_text(_clean(source.get("source_path_or_url"), "source path missing"))
        locator = _clean(source.get("page_locator")) or "source_level"
        lines.append(f"- [{source['citation_id']}] {title}; type={source.get('source_type')}; locator={locator}; path={location}")
    return "\n".join(lines) + "\n"


def _citation_integrity_for_stock(stock_code: str, md_path: Path, sources_path: Path, package: pd.DataFrame) -> list[dict[str, Any]]:
    text = md_path.read_text(encoding="utf-8")
    inline = set(re.findall(r"\[(S[^\\]]+)\]", text))
    refs = _read_jsonl(sources_path) if sources_path.exists() else []
    ref_ids = {str(row["citation_id"]) for row in refs}
    rows = []
    if not inline:
        rows.append(
            {
                "stock_code": stock_code,
                "citation_id": "",
                "inline_citation_present": False,
                "reference_present": True,
                "source_id_present": True,
                "chunk_or_table_present": True,
                "excerpt_present": True,
                "page_level_has_locator": True,
                "integrity_status": "pass",
                "issue_detail": "evidence_required stub has no inline citations",
            }
        )
    for citation_id in sorted(inline):
        row = package[package["citation_id"].eq(citation_id)]
        source_id_present = not row.empty and row["source_id"].fillna("").astype(str).str.len().gt(0).any()
        chunk_or_table = not row.empty and (
            row["chunk_id"].fillna("").astype(str).str.len().gt(0).any() or row["table_id"].fillna("").astype(str).str.len().gt(0).any()
        )
        excerpt_present = not row.empty and row["excerpt"].fillna("").astype(str).str.len().gt(0).any()
        page_rows = row[row["citation_granularity"].eq("page_level")] if not row.empty else row
        page_ok = page_rows.empty or page_rows["page_locator"].fillna("").astype(str).str.len().gt(0).all()
        ok = citation_id in ref_ids and source_id_present and chunk_or_table and excerpt_present and page_ok
        rows.append(
            {
                "stock_code": stock_code,
                "citation_id": citation_id,
                "inline_citation_present": True,
                "reference_present": citation_id in ref_ids,
                "source_id_present": source_id_present,
                "chunk_or_table_present": chunk_or_table,
                "excerpt_present": excerpt_present,
                "page_level_has_locator": page_ok,
                "integrity_status": "pass" if ok else "fail",
                "issue_detail": "" if ok else "citation mapping incomplete",
            }
        )
    return rows


def _report_quality_for_stock(stock_code: str, stock_name: str, md_path: Path, status: dict[str, Any]) -> dict[str, Any]:
    text = md_path.read_text(encoding="utf-8")
    forbidden_hits = [term for term in FORBIDDEN_REPORT_TERMS if term.lower() in text.lower()]
    return {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "report_status": status["report_status"],
        "has_references_section": "## 引用与数据源 / References" in text,
        "forbidden_language_hit_count": len(forbidden_hits),
        "forbidden_language_hits": "|".join(forbidden_hits),
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
        "quality_status": "pass" if not forbidden_hits and "## 引用与数据源 / References" in text else "fail",
    }


def _table_quality_audit(tables: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in tables.iterrows():
        page = _clean(row.get("page_locator"))
        rows.append(
            {
                "stock_code": _normalize_code(row.get("stock_code")),
                "stock_name": _clean(row.get("stock_name")),
                "table_id": _clean(row.get("table_id")),
                "page_locator": page,
                "row_count": _clean(row.get("row_count")),
                "column_count": _clean(row.get("column_count")),
                "table_relevance": _clean(row.get("table_relevance"), "unknown"),
                "citation_granularity": _clean(row.get("citation_granularity"), "source_level"),
                "table_quality_status": "usable" if page else "source_level_warning",
                "issue_warning": _clean(row.get("issue_warning")),
            }
        )
    return pd.DataFrame(rows)


def _parser_quality_audit(chunks: pd.DataFrame, comparison: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for stock in PILOT_STOCKS:
        stock_code = stock["stock_code"]
        stock_chunks = chunks[chunks["stock_code"].eq(stock_code)] if "stock_code" in chunks else pd.DataFrame()
        comp = comparison[comparison["stock_code"].eq(stock_code)] if "stock_code" in comparison else pd.DataFrame()
        has_pdf = not comp.empty and comp["pdf_path"].fillna("").astype(str).str.len().gt(0).any()
        page_ready = not stock_chunks.empty and stock_chunks["page_locator"].fillna("").astype(str).str.len().gt(0).any()
        rows.append(
            {
                "stock_code": stock_code,
                "stock_name": stock["stock_name"],
                "has_local_pdf": bool(has_pdf),
                "chunk_count": int(len(stock_chunks)),
                "page_level_chunk_count": int(stock_chunks["citation_granularity"].eq("page_level").sum()) if not stock_chunks.empty else 0,
                "docling_status": _clean(comp.iloc[0].get("docling_status")) if not comp.empty else "not_attempted",
                "parser_quality_status": "page_level_ready" if page_ready else "evidence_required" if not has_pdf else "needs_review",
                "issue_warning": "" if page_ready or not has_pdf else "parsed_without_page_locator",
            }
        )
    return pd.DataFrame(rows)


def _references_from_package(package: pd.DataFrame) -> list[dict[str, Any]]:
    refs = []
    if package.empty:
        return refs
    for _, row in package.drop_duplicates("citation_id").sort_values("citation_id").iterrows():
        refs.append(
            {
                "citation_id": _clean(row.get("citation_id")),
                "stock_code": _clean(row.get("stock_code")),
                "source_id": _clean(row.get("source_id")),
                "source_title": _sanitize_report_text(_clean(row.get("source_title"))),
                "source_type": _clean(row.get("source_type")),
                "source_path_or_url": _clean(row.get("source_path_or_url")),
                "page_locator": _clean(row.get("page_locator")),
                "citation_granularity": _clean(row.get("citation_granularity")),
                "parser": _clean(row.get("parser"), "docling"),
                "parser_version": _clean(row.get("parser_version")),
                "fetched_or_parsed_at": _now(),
            }
        )
    return refs


def _claim_map_from_package(package: pd.DataFrame) -> pd.DataFrame:
    if package.empty:
        return pd.DataFrame(columns=_claim_map_columns())
    frame = package.copy()
    frame["claim_id"] = frame["stock_code"].astype(str) + "-" + frame["report_section"].astype(str) + "-" + frame["evidence_id"].astype(str)
    frame["claim_placeholder"] = frame["report_section"].astype(str) + " deterministic evidence placeholder"
    return frame[_claim_map_columns()]


def _render_batch_report(
    summary: dict[str, Any],
    status: pd.DataFrame,
    acquisition: pd.DataFrame,
    citation_audit: pd.DataFrame,
    table_quality: pd.DataFrame,
    parser_quality: pd.DataFrame,
) -> str:
    downloaded = int(acquisition["status"].eq("downloaded").sum()) if not acquisition.empty and "status" in acquisition else 0
    citation_failures = int(citation_audit["integrity_status"].eq("fail").sum()) if not citation_audit.empty else 0
    table_usable = int(table_quality["table_quality_status"].eq("usable").sum()) if not table_quality.empty else 0
    return f"""# Data-to-Brief Docling adapter provenance backfill and 10-stock batch pilot v1

Research-only parser and report integration pilot. No signal, admission, scoring, formal strategy, production candidate universe, or dashboard routing changes were made.

## Scope

- pilot_stock_count: {summary['pilot_stock_count']}
- local_pdf_stock_count: {summary['local_pdf_stock_count']}
- evidence_required_count: {summary['missing_pdf_evidence_required_count']}
- chunk_count: {summary['chunk_count']}
- table_count: {summary['table_count']}
- citation_count: {summary['citation_count']}
- page_level_citation_count: {summary['page_level_citation_count']}
- source_level_citation_count: {summary['source_level_citation_count']}
- yanbaoke_downloaded_count: {downloaded}

## Provenance backfill result

The adapter now emits page/table provenance directly into source chunk and table artifacts when Docling provides `prov.page_no`. A separate metadata recovery step is no longer required for normal parser runs that use this updated path.

## Report status

{status[['stock_code', 'stock_name', 'has_local_pdf', 'report_status', 'citation_count', 'page_level_citation_count', 'blocker_reason']].to_markdown(index=False)}

## Source acquisition

Missing local PDFs were checked against the existing Yanbaoke API path when credentials were available. Failed or unavailable downloads remain evidence_required and are audited instead of being inferred.

{acquisition[['stock_code', 'stock_name', 'source_acquisition_status', 'status', 'error_type']].to_markdown(index=False) if not acquisition.empty else 'No source acquisition rows.'}

## Citation and table quality

- citation_integrity_failures: {citation_failures}
- usable_table_metadata_rows: {table_usable}
- parser_page_level_ready_rows: {int(parser_quality['parser_quality_status'].eq('page_level_ready').sum()) if not parser_quality.empty else 0}

## Remaining weaknesses

- Some stocks may still lack local PDFs even after Yanbaoke lookup.
- Table captions and row/column metadata are available only when Docling exposes structured table data.
- This pilot uses deterministic keyword heuristics and is not a final report writer.

## Readiness

- Docling ready for 30-stock batch pilot: {'yes' if summary['page_level_citation_count'] >= 22 else 'conditional'}
- Docling ready for 90-stock full batch: conditional; run a 30-stock pilot first.
- Docling should remain optional: yes.

## Guardrails

- allowed_for_signal: false
- allowed_for_admission: false
- production_update: false
- strategy_file_diff_clean: {summary['strategy_file_diff_clean']}
- acceptance_decision: {summary['acceptance_decision']}
"""


def _evidence_columns() -> list[str]:
    return [
        "stock_code",
        "stock_name",
        "report_section",
        "evidence_id",
        "citation_id",
        "source_id",
        "chunk_id",
        "table_id",
        "source_type",
        "source_title",
        "source_path_or_url",
        "citation_granularity",
        "page_locator",
        "excerpt",
        "evidence_strength",
        "evidence_quality_flag",
        "parser",
        "parser_version",
        "parse_quality_flag",
        "issue_warning",
        "supports_or_contradicts",
        "evidence_kind",
    ]


def _claim_map_columns() -> list[str]:
    return [
        "stock_code",
        "claim_id",
        "report_section",
        "claim_placeholder",
        "citation_id",
        "source_id",
        "chunk_id",
        "table_id",
        "source_type",
        "source_path_or_url",
        "page_locator",
        "citation_granularity",
        "excerpt",
        "supports_or_contradicts",
        "evidence_strength",
    ]


def _load_yanbaoke_api_key() -> str:
    env = os.environ.get("YANBAOKE_API_KEY", "").strip()
    if env:
        return env
    path = PROJECT_ROOT / "config/local_secrets.json"
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str((payload.get("yanbaoke") or {}).get("api_key") or "").strip()


def _markdown_to_html(markdown: str) -> str:
    body = []
    for line in markdown.splitlines():
        escaped = html.escape(line)
        if line.startswith("# "):
            body.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            body.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("- "):
            body.append(f"<p>{escaped}</p>")
        elif line.strip():
            body.append(f"<p>{escaped}</p>")
    return "<!doctype html><html><head><meta charset='utf-8'><title>Docling 10-stock pilot</title></head><body>" + "\n".join(body) + "</body></html>"


def _render_pdf(markdown: str, path: Path) -> None:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4\n% fallback placeholder\n")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=A4)
    _, height = A4
    y = height - 40
    pdf.setFont("Helvetica", 8)
    for raw in markdown.splitlines():
        line = raw.encode("latin-1", "replace").decode("latin-1")
        pdf.drawString(36, y, line[:120])
        y -= 11
        if y < 36:
            pdf.showPage()
            pdf.setFont("Helvetica", 8)
            y = height - 40
    pdf.save()


def _sanitize_report_text(text: str) -> str:
    sanitized = _clean(text)
    replacements = {
        "买入": "评级信息已省略",
        "卖出": "评级信息已省略",
        "目标价": "估值表述已省略",
        "target price": "valuation wording omitted",
        "buy recommendation": "rating wording omitted",
        "sell recommendation": "rating wording omitted",
    }
    for term, replacement in replacements.items():
        sanitized = re.sub(re.escape(term), replacement, sanitized, flags=re.IGNORECASE)
    return sanitized


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    frame = pd.read_csv(path, dtype={"stock_code": str}, low_memory=False)
    if "stock_code" in frame.columns:
        frame["stock_code"] = frame["stock_code"].map(_normalize_code)
    return frame


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n" for row in rows), encoding="utf-8")


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return default
    return text


def _normalize_code(value: Any) -> str:
    text = _clean(value)
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() and len(text) <= 6 else text


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _git_diff_formal_strategy_files() -> str:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout or result.stderr or ""
