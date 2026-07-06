from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.data_to_brief_docling_adapter_provenance_backfill_batch import _load_yanbaoke_api_key
from stock_research.data_to_brief_docling_90_stock_batch_precheck import OUTPUT_DIR as PRECHECK_OUTPUT_DIR
from stock_research.data_to_brief_docling_parser_poc import discover_pilot_sources
from stock_research.yanbaoke_reports import download_yanbaoke_report_pdf, search_yanbaoke_reports


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TASK_NAME = "data_to_brief_docling_90_stock_pdf_acquisition_v1"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def run_data_to_brief_docling_90_stock_pdf_acquisition(
    *,
    output_dir: str | Path = OUTPUT_DIR,
    max_reports_per_stock: int = 2,
    sleep_seconds: float = 1.0,
    retry_sleep_seconds: float = 8.0,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    download_dir = output / "yanbaoke_pdfs"
    download_dir.mkdir(parents=True, exist_ok=True)

    missing = _load_missing_pdf_stocks()
    api_key = _load_yanbaoke_api_key()
    existing_sources = discover_pilot_sources(source_roots=[download_dir], pilot_stocks=missing, limit_per_stock=max_reports_per_stock)
    existing_by_code: dict[str, list[Any]] = {}
    for source in existing_sources:
        if source.pdf_path is not None:
            existing_by_code.setdefault(source.stock_code, []).append(source)

    search_rows: list[dict[str, Any]] = []
    download_rows: list[dict[str, Any]] = []
    for stock in missing:
        code = stock["stock_code"]
        name = stock["stock_name"]
        if code in existing_by_code:
            for rank, source in enumerate(existing_by_code[code][:max_reports_per_stock], start=1):
                download_rows.append(
                    {
                        **stock,
                        "uuid": "",
                        "selected_rank": rank,
                        "selected_reason": "already_downloaded",
                        "status": "already_downloaded",
                        "pdf_path": str(source.pdf_path or ""),
                        "error_type": "",
                        "error_message": "",
                    }
                )
            continue
        if not api_key:
            download_rows.append(_gap_row(stock, status="api_key_missing", error_type="api_key_missing"))
            continue

        candidates, search_audit = _search_with_retries(stock, retry_sleep_seconds=retry_sleep_seconds)
        search_rows.extend(search_audit)
        ranked = _rank_download_candidates(candidates, stock).head(max_reports_per_stock)
        if ranked.empty:
            download_rows.append(_gap_row(stock, status="yanbaoke_no_download_candidate"))
            continue
        for rank, (_, report) in enumerate(ranked.iterrows(), start=1):
            uuid = str(report.get("uuid") or "")
            try:
                download = download_yanbaoke_report_pdf(uuid=uuid, output_dir=download_dir, api_key=api_key)
                download_rows.append(
                    {
                        **stock,
                        "uuid": uuid,
                        "selected_rank": rank,
                        "selected_reason": str(report.get("selection_reason") or ""),
                        "report_title": str(report.get("title") or report.get("report_title") or ""),
                        "publish_date": str(report.get("publish_date") or report.get("time") or "")[:10],
                        "pagenum": report.get("pagenum", ""),
                        "org_name": str(report.get("org_name") or report.get("broker") or ""),
                        "status": str(download.get("status") or "download_failed"),
                        "pdf_path": str(download.get("pdf_path") or ""),
                        "download_url": str(download.get("download_url") or ""),
                        "filename": str(download.get("filename") or ""),
                        "error_type": "",
                        "error_message": "",
                    }
                )
            except Exception as exc:  # noqa: BLE001 - acquisition errors are audited, not fatal.
                download_rows.append(
                    {
                        **stock,
                        "uuid": uuid,
                        "selected_rank": rank,
                        "selected_reason": str(report.get("selection_reason") or ""),
                        "report_title": str(report.get("title") or report.get("report_title") or ""),
                        "publish_date": str(report.get("publish_date") or report.get("time") or "")[:10],
                        "pagenum": report.get("pagenum", ""),
                        "org_name": str(report.get("org_name") or report.get("broker") or ""),
                        "status": "download_error",
                        "pdf_path": "",
                        "download_url": "",
                        "filename": "",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc)[:500],
                    }
                )
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

    search_df = pd.DataFrame(search_rows)
    downloads_df = pd.DataFrame(download_rows)
    search_df.to_csv(output / "yanbaoke_missing_pdf_search_audit.csv", index=False)
    downloads_df.to_csv(output / "yanbaoke_missing_pdf_download_audit.csv", index=False)
    summary = _build_summary(missing, search_df, downloads_df, download_dir)
    _write_json(output / "yanbaoke_missing_pdf_acquisition_summary.json", summary)
    (output / "data_to_brief_docling_90_stock_pdf_acquisition_v1_report.md").write_text(
        _render_report(summary, downloads_df),
        encoding="utf-8",
    )
    return {"summary": summary, "downloads": downloads_df, "search": search_df}


def _load_missing_pdf_stocks() -> list[dict[str, str]]:
    manifest_path = PRECHECK_OUTPUT_DIR / "batch_manifest.csv"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing precheck manifest: {manifest_path}")
    frame = pd.read_csv(manifest_path, dtype={"stock_code": str}).fillna("")
    missing = frame[frame["pdf_missing"].eq(True)].copy()
    if missing.empty and "pdf_path" in frame:
        missing = frame[frame["pdf_path"].astype(str).str.contains(TASK_NAME, regex=False)].copy()
    rows = []
    for _, row in missing.iterrows():
        code = _normalize_code(row.get("stock_code"))
        rows.append({"stock_code": code, "stock_name": str(row.get("stock_name") or ""), "asset_id": _asset_id(code)})
    return rows


def _search_with_retries(stock: dict[str, str], *, retry_sleep_seconds: float) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    audit_rows: list[dict[str, Any]] = []
    frames: list[pd.DataFrame] = []
    queries = [
        {"keyword": stock["stock_name"], "stock": stock["stock_name"], "search_type": "title"},
        {"keyword": stock["stock_code"], "stock": None, "search_type": "title"},
        {"keyword": stock["stock_name"], "stock": None, "search_type": "title"},
    ]
    for query_id, query in enumerate(queries, start=1):
        for attempt in range(1, 4):
            try:
                result = search_yanbaoke_reports(
                    keyword=query["keyword"],
                    stock=query["stock"],
                    search_type=query["search_type"],
                    start_date="2021-01-01",
                    end_date="2026-07-06",
                    size=80,
                )
                reports = result["reports"].copy()
                if not reports.empty:
                    reports["query_id"] = query_id
                    frames.append(reports)
                audit_rows.append(
                    {
                        **stock,
                        "query_id": query_id,
                        "query_keyword": query["keyword"],
                        "query_stock": query["stock"] or "",
                        "attempt": attempt,
                        "status": "ok",
                        "candidate_count": int(len(reports)),
                        "error_type": "",
                        "error_message": "",
                    }
                )
                break
            except Exception as exc:  # noqa: BLE001 - retryable source lookup.
                audit_rows.append(
                    {
                        **stock,
                        "query_id": query_id,
                        "query_keyword": query["keyword"],
                        "query_stock": query["stock"] or "",
                        "attempt": attempt,
                        "status": "error",
                        "candidate_count": 0,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc)[:500],
                    }
                )
                if attempt < 3 and retry_sleep_seconds > 0:
                    time.sleep(retry_sleep_seconds)
    if not frames:
        return pd.DataFrame(), audit_rows
    candidates = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["uuid"], keep="first")
    return candidates, audit_rows


def _rank_download_candidates(candidates: pd.DataFrame, stock: dict[str, str]) -> pd.DataFrame:
    if candidates.empty:
        return candidates
    code = stock["stock_code"]
    name = stock["stock_name"]
    rows: list[dict[str, Any]] = []
    for row in candidates.fillna("").to_dict("records"):
        title = str(row.get("title") or "")
        content = str(row.get("content") or "")
        formats = str(row.get("formats") or "").lower()
        if "pdf" not in formats:
            continue
        if name not in title and name not in content and code not in title and code not in content:
            continue
        publish_date = str(row.get("time") or row.get("publish_date") or "")[:10]
        score = 0
        reason = []
        if name in title or code in title:
            score += 40
            reason.append("title_match")
        if "年度报告" in title:
            score += 35
            reason.append("annual_report")
        if "半年度报告" in title:
            score += 28
            reason.append("semiannual_report")
        if any(token in title for token in ["深度", "首次覆盖", "跟踪报告", "公司研究"]):
            score += 24
            reason.append("research_report")
        if "季度报告" in title:
            score -= 12
            reason.append("quarterly_report_backup")
        try:
            pages = int(float(row.get("pagenum") or 0))
        except Exception:
            pages = 0
        score += min(pages, 260) / 20
        try:
            days = (pd.Timestamp(publish_date) - pd.Timestamp("2021-01-01")).days
            score += max(0, days) / 365
        except Exception:
            pass
        enriched = dict(row)
        enriched.update({"selection_score": round(score, 4), "selection_reason": "|".join(reason), "publish_date": publish_date, "pagenum": pages})
        rows.append(enriched)
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    return frame.sort_values(["selection_score", "publish_date", "pagenum"], ascending=[False, False, False]).reset_index(drop=True)


def _gap_row(stock: dict[str, str], *, status: str, error_type: str = "", error_message: str = "") -> dict[str, Any]:
    return {
        **stock,
        "uuid": "",
        "selected_rank": 0,
        "selected_reason": "",
        "report_title": "",
        "publish_date": "",
        "pagenum": "",
        "org_name": "",
        "status": status,
        "pdf_path": "",
        "download_url": "",
        "filename": "",
        "error_type": error_type,
        "error_message": error_message,
    }


def _build_summary(missing: list[dict[str, str]], search: pd.DataFrame, downloads: pd.DataFrame, download_dir: Path) -> dict[str, Any]:
    available = (
        downloads[downloads.get("status", pd.Series(dtype=object)).astype(str).isin(["downloaded", "already_downloaded"])]
        if not downloads.empty
        else downloads
    )
    newly_downloaded = downloads[downloads.get("status", pd.Series(dtype=object)).astype(str).eq("downloaded")] if not downloads.empty else downloads
    downloaded_stock_count = int(available["stock_code"].nunique()) if not available.empty else 0
    search_ok = search[search.get("status", pd.Series(dtype=object)).astype(str).eq("ok")] if not search.empty else search
    candidate_stock_count = int(search_ok[search_ok.get("candidate_count", pd.Series(dtype=int)).astype(int).gt(0)]["stock_code"].nunique()) if not search_ok.empty else 0
    reused = downloads[downloads.get("status", pd.Series(dtype=object)).astype(str).eq("already_downloaded")] if not downloads.empty else downloads
    strategy_diff = _git_diff_formal_strategy_files()
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "missing_pdf_input_count": len(missing),
        "yanbaoke_candidate_stock_count": max(candidate_stock_count, downloaded_stock_count),
        "downloaded_pdf_count": int(len(available)) if not available.empty else 0,
        "newly_downloaded_pdf_count": int(len(newly_downloaded)) if not newly_downloaded.empty else 0,
        "reused_existing_pdf_count": int(len(reused)) if not reused.empty else 0,
        "downloaded_stock_count": downloaded_stock_count,
        "download_failed_count": int(len(downloads) - len(available)) if not downloads.empty else len(missing),
        "max_reports_per_stock": 2,
        "download_dir": str(download_dir),
        "allowed_for_signal": False,
        "allowed_for_admission": False,
        "production_update": False,
        "strategy_file_diff_clean": strategy_diff == "",
        "formal_strategy_files_modified": strategy_diff != "",
    }


def _render_report(summary: dict[str, Any], downloads: pd.DataFrame) -> str:
    status = downloads["status"].value_counts().to_markdown() if not downloads.empty and "status" in downloads else "No download rows."
    downloaded = downloads[downloads.get("status", pd.Series(dtype=object)).astype(str).eq("downloaded")] if not downloads.empty else pd.DataFrame()
    return f"""# Data-to-Brief Docling 90-stock PDF acquisition v1

Research-only Yanbaoke PDF acquisition for the 90-stock Docling precheck missing-PDF set.

## Summary

- missing_pdf_input_count: {summary['missing_pdf_input_count']}
- yanbaoke_candidate_stock_count: {summary['yanbaoke_candidate_stock_count']}
- downloaded_pdf_count: {summary['downloaded_pdf_count']}
- downloaded_stock_count: {summary['downloaded_stock_count']}
- download_dir: {summary['download_dir']}

## Download Status

{status}

## Downloaded PDFs

{downloaded[['stock_code', 'stock_name', 'selected_rank', 'report_title', 'pdf_path']].to_markdown(index=False) if not downloaded.empty else 'No downloaded PDFs.'}

## Guardrails

- allowed_for_signal: false
- allowed_for_admission: false
- production_update: false
- strategy_file_diff_clean: {summary['strategy_file_diff_clean']}
"""


def _asset_id(code: str) -> str:
    return f"{code}.SH" if code.startswith("6") else f"{code}.SZ"


def _normalize_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() and len(text) <= 6 else text


def _write_json(path: Path, payload: Any) -> None:
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
