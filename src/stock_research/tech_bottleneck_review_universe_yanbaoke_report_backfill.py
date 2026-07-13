from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from stock_research.data_to_brief_docling_adapter_provenance_backfill_batch import _load_yanbaoke_api_key
from stock_research.yanbaoke_reports import download_yanbaoke_report_pdf, search_yanbaoke_reports


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TASK_NAME = "tech_bottleneck_review_universe_yanbaoke_report_backfill_v1"
DEFAULT_UNIVERSE_PATH = (
    PROJECT_ROOT
    / "outputs/research/tech_bottleneck_review_universe_frontend_dataset_v1"
    / "tech_bottleneck_review_universe_frontend_dataset.csv"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs/research" / TASK_NAME
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]


def build_existing_report_pdf_coverage(
    universe: pd.DataFrame,
    *,
    search_roots: list[str | Path] | None = None,
) -> pd.DataFrame:
    stocks = _normalize_universe(universe)
    coverage: dict[str, list[dict[str, str]]] = {row["stock_code"]: [] for row in stocks}
    stock_by_code = {row["stock_code"]: row for row in stocks}
    name_to_code = {row["stock_name"]: row["stock_code"] for row in stocks if row["stock_name"]}
    roots = [Path(path) for path in (search_roots or [PROJECT_ROOT / "outputs/research", PROJECT_ROOT / "data/manual", PROJECT_ROOT / "data/reports"])]

    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.pdf"):
            low = str(path).lower()
            if "yanbaoke" not in low and "stock_report" not in low and "研报" not in str(path):
                continue
            if not _is_broker_research_candidate(title=path.name, org_name=""):
                continue
            matched_codes = _codes_from_text(str(path), set(coverage))
            if not matched_codes:
                matched_codes = {code for name, code in name_to_code.items() if name and name in path.name}
            for code in matched_codes:
                coverage[code].append({"coverage_kind": "pdf_file", "coverage_path": str(path), "report_title": path.name})

    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.csv"):
            low = str(path).lower()
            if "yanbaoke" not in low or "download" not in path.name.lower():
                continue
            try:
                frame = pd.read_csv(path, dtype=str, low_memory=False).fillna("")
            except Exception:
                continue
            for row in frame.to_dict("records"):
                status = str(row.get("status") or "").lower()
                if status and status not in {"downloaded", "already_downloaded"}:
                    continue
                pdf_path = str(row.get("pdf_path") or "")
                filename = str(row.get("filename") or "")
                if not pdf_path and not filename:
                    continue
                text = " ".join(
                    str(row.get(column) or "")
                    for column in [
                        "stock_code",
                        "ts_code",
                        "symbol",
                        "asset_id",
                        "pdf_path",
                        "filename",
                        "report_title",
                        "title",
                        "stock_name",
                    ]
                )
                codes = _codes_from_text(text, set(coverage))
                stock_name = str(row.get("stock_name") or "")
                if not codes and stock_name in name_to_code:
                    codes = {name_to_code[stock_name]}
                for code in codes:
                    title = str(row.get("report_title") or row.get("title") or filename)
                    title_codes = set(re.findall(r"(?<!\d)([0-9]{6})(?:\.(?:SZ|SH|BJ))?(?!\d)", title))
                    if title_codes and code not in title_codes:
                        continue
                    stock_label = stock_by_code.get(code, {}).get("stock_name", "")
                    title_or_filename = f"{title} {filename}"
                    if stock_label and stock_label not in title_or_filename and code not in title_or_filename:
                        continue
                    if not _is_broker_research_candidate(title=title_or_filename, org_name=str(row.get("org_name") or row.get("broker") or "")):
                        continue
                    coverage[code].append(
                        {
                            "coverage_kind": "download_manifest",
                            "coverage_path": str(path),
                            "report_title": title,
                            "pdf_path": pdf_path,
                        }
                    )

    rows: list[dict[str, Any]] = []
    for code in sorted(coverage):
        entries = _dedupe_entries(coverage[code])
        rows.append(
            {
                "stock_code": code,
                "stock_name": stock_by_code[code]["stock_name"],
                "has_report_pdf": bool(entries),
                "report_pdf_count": len(entries),
                "report_pdf_paths": " | ".join(entry.get("coverage_path", "") for entry in entries[:5]),
                "report_titles": " | ".join(entry.get("report_title", "") for entry in entries[:5]),
            }
        )
    frame = pd.DataFrame(rows)
    if "has_report_pdf" in frame:
        frame["has_report_pdf"] = frame["has_report_pdf"].astype(object)
    return frame


def run_tech_bottleneck_review_universe_yanbaoke_report_backfill(
    *,
    universe_path: str | Path = DEFAULT_UNIVERSE_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    search_roots: list[str | Path] | None = None,
    max_reports_per_stock: int = 1,
    max_missing_stocks: int | None = None,
    start_date: str = "2021-01-01",
    end_date: str = "2026-07-09",
    sleep_seconds: float = 0.2,
    retry_attempts: int = 3,
    retry_sleep_seconds: float = 3.0,
    api_key: str | None = None,
    search_func: Callable[..., dict[str, Any]] = search_yanbaoke_reports,
    download_func: Callable[..., dict[str, Any]] = download_yanbaoke_report_pdf,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    download_dir = output / "yanbaoke_pdfs"
    download_dir.mkdir(parents=True, exist_ok=True)

    universe = pd.read_csv(universe_path, dtype={"stock_code": str}).fillna("")
    stocks = _normalize_universe(universe)
    coverage = build_existing_report_pdf_coverage(pd.DataFrame(stocks), search_roots=search_roots)
    missing = coverage[~coverage["has_report_pdf"].astype(bool)].copy()
    if max_missing_stocks is not None:
        missing = missing.head(max_missing_stocks).copy()

    search_rows: list[dict[str, Any]] = []
    download_rows: list[dict[str, Any]] = []
    key = (api_key if api_key is not None else _load_yanbaoke_api_key()).strip()

    for stock in missing.fillna("").to_dict("records"):
        code = str(stock["stock_code"])
        name = str(stock["stock_name"])
        if not key:
            download_rows.append(_download_gap_row(stock, status="api_key_missing", error_type="api_key_missing"))
            continue
        candidates, audit_rows = _search_candidates_for_stock(
            stock_code=code,
            stock_name=name,
            start_date=start_date,
            end_date=end_date,
            search_func=search_func,
            retry_attempts=retry_attempts,
            retry_sleep_seconds=retry_sleep_seconds,
        )
        search_rows.extend(audit_rows)
        if candidates.empty and audit_rows and all(row.get("status") == "search_error" for row in audit_rows):
            last_error = audit_rows[-1]
            download_rows.append(
                _download_gap_row(
                    stock,
                    status="search_error",
                    error_type=str(last_error.get("error_type") or ""),
                    error_message=str(last_error.get("error_message") or ""),
                )
            )
            continue

        selected = rank_yanbaoke_report_candidates_for_stock(candidates, stock_code=code, stock_name=name).head(max_reports_per_stock)
        if selected.empty:
            download_rows.append(_download_gap_row(stock, status="yanbaoke_no_download_candidate"))
            continue
        downloaded_for_stock = 0
        for rank, report in enumerate(selected.to_dict("records"), start=1):
            uuid = str(report.get("uuid") or "")
            try:
                download = download_func(uuid=uuid, output_dir=download_dir, api_key=key)
                status = str(download.get("status") or "download_failed")
                if status == "downloaded":
                    downloaded_for_stock += 1
                download_rows.append(
                    {
                        "stock_code": code,
                        "stock_name": name,
                        "uuid": uuid,
                        "selected_rank": rank,
                        "selection_score": report.get("selection_score", ""),
                        "selection_reason": report.get("selection_reason", ""),
                        "report_title": str(report.get("title") or report.get("report_title") or download.get("title") or ""),
                        "publish_date": str(report.get("publish_date") or report.get("time") or "")[:10],
                        "pagenum": report.get("pagenum", ""),
                        "org_name": str(report.get("org_name") or report.get("broker") or ""),
                        "status": status,
                        "pdf_path": str(download.get("pdf_path") or ""),
                        "download_url": str(download.get("download_url") or ""),
                        "filename": str(download.get("filename") or ""),
                        "error_type": "",
                        "error_message": "",
                    }
                )
            except Exception as exc:  # noqa: BLE001
                download_rows.append(
                    {
                        "stock_code": code,
                        "stock_name": name,
                        "uuid": uuid,
                        "selected_rank": rank,
                        "selection_score": report.get("selection_score", ""),
                        "selection_reason": report.get("selection_reason", ""),
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
        if downloaded_for_stock == 0 and not any(str(row.get("stock_code")) == code for row in download_rows[-len(selected) :]):
            download_rows.append(_download_gap_row(stock, status="download_error"))
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    search_df = pd.DataFrame(search_rows)
    downloads_df = pd.DataFrame(download_rows)
    downloaded = downloads_df[downloads_df.get("status", pd.Series(dtype=object)).astype(str).eq("downloaded")] if not downloads_df.empty else downloads_df
    coverage_after_codes = set(coverage.loc[coverage["has_report_pdf"].astype(bool), "stock_code"].astype(str))
    if not downloaded.empty:
        coverage_after_codes.update(downloaded["stock_code"].dropna().astype(str))
    unresolved_codes = sorted(set(coverage["stock_code"].astype(str)) - coverage_after_codes)

    coverage.to_csv(output / "review_universe_report_coverage_audit.csv", index=False)
    missing.to_csv(output / "review_universe_missing_report_queue.csv", index=False)
    search_df.to_csv(output / "review_universe_yanbaoke_report_search_results.csv", index=False)
    downloads_df.to_csv(output / "review_universe_yanbaoke_report_download_manifest.csv", index=False)

    summary = _build_summary(
        universe_count=len(stocks),
        coverage=coverage,
        missing=missing,
        search=search_df,
        downloads=downloads_df,
        unresolved_codes=unresolved_codes,
        download_dir=download_dir,
    )
    guardrails = _build_guardrails(summary)
    _write_json(output / "review_universe_yanbaoke_report_backfill_summary.json", summary)
    _write_json(output / "review_universe_yanbaoke_report_backfill_guardrails.json", guardrails)
    (output / "tech_bottleneck_review_universe_yanbaoke_report_backfill_v1_report.md").write_text(
        _render_report(summary, downloads_df, unresolved_codes),
        encoding="utf-8",
    )
    return {
        "summary": summary,
        "guardrails": guardrails,
        "coverage": coverage,
        "missing": missing,
        "search": search_df,
        "downloads": downloads_df,
    }


def rank_yanbaoke_report_candidates_for_stock(candidates: pd.DataFrame, *, stock_code: str, stock_name: str) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for row in candidates.fillna("").to_dict("records"):
        title = str(row.get("title") or row.get("report_title") or "")
        content = str(row.get("content") or "")
        org_name = str(row.get("org_name") or row.get("broker") or "")
        formats = str(row.get("formats") or "").lower()
        if "pdf" not in formats:
            continue
        if not _is_broker_research_candidate(title=title, org_name=org_name):
            continue
        title_codes = set(re.findall(r"(?<!\d)([0-9]{6})(?:\.(?:SZ|SH|BJ))?(?!\d)", title))
        if title_codes and stock_code not in title_codes:
            continue
        if stock_name and stock_name not in title and stock_code not in title:
            continue
        if stock_name and stock_name not in title and stock_name not in content and stock_code not in title and stock_code not in content:
            continue
        score = 0.0
        reasons: list[str] = []
        if stock_name and stock_name in title:
            score += 40
            reasons.append("title_stock_name_match")
        if stock_code in title:
            score += 36
            reasons.append("title_stock_code_match")
        if any(token in title for token in ["深度", "首次覆盖", "公司深度"]):
            score += 28
            reasons.append("deep_or_initiation_report")
        if any(token in title for token in ["公司研究", "点评", "跟踪", "年报", "中报"]):
            score += 18
            reasons.append("company_report")
        if any(token in title for token in ["行业", "策略", "周报"]) and stock_name not in title:
            score -= 20
            reasons.append("industry_or_strategy_penalty")
        pages = _safe_int(row.get("pagenum"))
        score += min(pages, 80) / 10
        publish_date = str(row.get("time") or row.get("publish_date") or "")[:10]
        try:
            score += max(0, (pd.Timestamp(publish_date) - pd.Timestamp("2021-01-01")).days) / 365
        except Exception:
            pass
        enriched = dict(row)
        enriched.update(
            {
                "publish_date": publish_date,
                "pagenum": pages,
                "selection_score": round(score, 4),
                "selection_reason": "|".join(reasons),
            }
        )
        rows.append(enriched)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["selection_score", "publish_date", "pagenum"], ascending=[False, False, False]).reset_index(drop=True)


def _search_candidates_for_stock(
    *,
    stock_code: str,
    stock_name: str,
    start_date: str,
    end_date: str,
    search_func: Callable[..., dict[str, Any]],
    retry_attempts: int,
    retry_sleep_seconds: float,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    queries = [
        {"keyword": stock_name or stock_code, "stock": stock_name or None, "search_type": "title"},
        {"keyword": stock_code, "stock": None, "search_type": "title"},
        {"keyword": stock_name or stock_code, "stock": None, "search_type": "title"},
        {"keyword": stock_name or stock_code, "stock": None, "search_type": "content"},
        {"keyword": stock_code, "stock": None, "search_type": "content"},
    ]
    frames: list[pd.DataFrame] = []
    audit_rows: list[dict[str, Any]] = []
    seen_uuids: set[str] = set()
    for query_id, query in enumerate(queries, start=1):
        for attempt in range(1, max(1, retry_attempts) + 1):
            try:
                result = search_func(
                    keyword=query["keyword"],
                    stock=query["stock"],
                    search_type=query["search_type"],
                    start_date=start_date,
                    end_date=end_date,
                    size=80,
                )
                reports = result.get("reports", pd.DataFrame()).copy()
                if not reports.empty:
                    reports["query_id"] = query_id
                    reports["query_keyword"] = query["keyword"]
                    reports["query_stock"] = query["stock"] or ""
                    if "uuid" in reports:
                        reports = reports[~reports["uuid"].astype(str).isin(seen_uuids)].copy()
                        seen_uuids.update(reports["uuid"].astype(str))
                    frames.append(reports)
                audit_rows.append(
                    {
                        "stock_code": stock_code,
                        "stock_name": stock_name,
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
                combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
                if not rank_yanbaoke_report_candidates_for_stock(combined, stock_code=stock_code, stock_name=stock_name).empty:
                    return combined, audit_rows
                break
            except Exception as exc:  # noqa: BLE001 - retries are audited per query.
                audit_rows.append(
                    {
                        "stock_code": stock_code,
                        "stock_name": stock_name,
                        "query_id": query_id,
                        "query_keyword": query["keyword"],
                        "query_stock": query["stock"] or "",
                        "attempt": attempt,
                        "status": "search_error",
                        "candidate_count": 0,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc)[:500],
                    }
                )
                if attempt < max(1, retry_attempts) and retry_sleep_seconds > 0:
                    time.sleep(retry_sleep_seconds)
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), audit_rows


def _is_broker_research_candidate(*, title: str, org_name: str) -> bool:
    text = f"{org_name} {title}"
    if any(token in text for token in ["上交所", "深交所", "北交所", "交易所", "巨潮资讯", "证券时报", "公司公告"]):
        return False
    filing_patterns = [
        r"\d{4}年年度报告",
        r"半年度报告",
        r"季度报告",
        r"招股说明书",
        r"募集说明书",
        r"上市保荐书",
        r"法律意见书",
    ]
    if any(re.search(pattern, title) for pattern in filing_patterns):
        return False
    broker_tokens = [
        "证券",
        "中金",
        "中国国际金融",
        "华泰",
        "国泰君安",
        "国泰海通",
        "招商",
        "申万宏源",
        "兴业",
        "广发",
        "光大",
        "东吴",
        "国信",
        "中信",
        "中信建投",
        "海通",
        "天风",
        "浙商",
        "民生",
        "国金",
        "华鑫",
        "开源",
        "长江",
        "东方财富",
        "交银国际",
        "摩根",
        "高盛",
        "瑞银",
        "花旗",
        "汇丰",
    ]
    if any(token in text for token in broker_tokens):
        return True
    return any(token in title for token in ["证券-", "深度报告", "首次覆盖", "公司研究", "年报点评", "中报点评", "季报点评"])


def _normalize_universe(universe: pd.DataFrame) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in universe.fillna("").to_dict("records"):
        code = _normalize_code(row.get("stock_code"))
        if not code:
            continue
        rows.append({"stock_code": code, "stock_name": str(row.get("stock_name") or "")})
    deduped = {row["stock_code"]: row for row in rows}
    return [deduped[code] for code in sorted(deduped)]


def _normalize_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    if "." in text:
        text = text.split(".")[0]
    return text.zfill(6) if text.isdigit() and len(text) <= 6 else text


def _codes_from_text(text: str, allowed: set[str]) -> set[str]:
    return {code for code in re.findall(r"(?<!\d)([0-9]{6})(?:\.(?:SZ|SH|BJ))?(?!\d)", text) if code in allowed}


def _dedupe_entries(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for entry in entries:
        key = (entry.get("coverage_path", ""), entry.get("report_title", ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return result


def _download_gap_row(stock: dict[str, Any], *, status: str, error_type: str = "", error_message: str = "") -> dict[str, Any]:
    return {
        "stock_code": str(stock.get("stock_code") or ""),
        "stock_name": str(stock.get("stock_name") or ""),
        "uuid": "",
        "selected_rank": 0,
        "selection_score": "",
        "selection_reason": "",
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


def _safe_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def _build_summary(
    *,
    universe_count: int,
    coverage: pd.DataFrame,
    missing: pd.DataFrame,
    search: pd.DataFrame,
    downloads: pd.DataFrame,
    unresolved_codes: list[str],
    download_dir: Path,
) -> dict[str, Any]:
    downloaded = downloads[downloads.get("status", pd.Series(dtype=object)).astype(str).eq("downloaded")] if not downloads.empty else downloads
    candidate_search = search[search.get("candidate_count", pd.Series(dtype=int)).astype(int).gt(0)] if not search.empty else search
    strategy_diff = _git_diff_formal_strategy_files()
    acceptance = "review_universe_yanbaoke_report_backfill_ready"
    if unresolved_codes:
        acceptance = "conditionally_ready_with_report_gaps"
    if strategy_diff:
        acceptance = "blocked_due_to_guardrail_violation"
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "review_universe_count": universe_count,
        "existing_report_pdf_covered_count": int(coverage["has_report_pdf"].astype(bool).sum()) if not coverage.empty else 0,
        "missing_report_pdf_before_count": int(len(missing)),
        "processed_missing_count": int(len(missing)),
        "yanbaoke_candidate_stock_count": int(candidate_search["stock_code"].nunique()) if not candidate_search.empty else 0,
        "downloaded_pdf_count": int(len(downloaded)) if not downloaded.empty else 0,
        "downloaded_stock_count": int(downloaded["stock_code"].nunique()) if not downloaded.empty else 0,
        "unresolved_missing_report_pdf_count": int(len(unresolved_codes)),
        "unresolved_missing_stock_codes": unresolved_codes,
        "download_dir": str(download_dir),
        "primary_source_collection_performed": False,
        "broker_report_collection_performed": True,
        "auto_added_to_quality_pool_count": 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "strategy_file_diff_clean": strategy_diff == "",
        "formal_strategy_files_modified": strategy_diff != "",
        "acceptance_decision": acceptance,
    }


def _build_guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "review_universe_count": summary["review_universe_count"],
        "missing_report_pdf_before_count": summary["missing_report_pdf_before_count"],
        "processed_missing_count": summary["processed_missing_count"],
        "broker_report_collection_performed": True,
        "primary_source_collection_performed": False,
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


def _render_report(summary: dict[str, Any], downloads: pd.DataFrame, unresolved_codes: list[str]) -> str:
    status_counts = downloads["status"].value_counts().to_markdown() if not downloads.empty and "status" in downloads else "No download rows."
    return f"""# Tech Bottleneck Review Universe Yanbaoke Report Backfill v1

Research-only broker-report PDF coverage audit and Yanbaoke backfill for the 378-stock review universe.

## Summary

- review_universe_count: {summary['review_universe_count']}
- existing_report_pdf_covered_count: {summary['existing_report_pdf_covered_count']}
- missing_report_pdf_before_count: {summary['missing_report_pdf_before_count']}
- processed_missing_count: {summary['processed_missing_count']}
- downloaded_pdf_count: {summary['downloaded_pdf_count']}
- downloaded_stock_count: {summary['downloaded_stock_count']}
- unresolved_missing_report_pdf_count: {summary['unresolved_missing_report_pdf_count']}

## Download Status

{status_counts}

## Remaining Gaps

{', '.join(unresolved_codes) if unresolved_codes else 'No remaining report PDF gaps.'}

## Guardrails

- research_only: true
- primary_source_collection_performed: false
- used_for_signal_count: 0
- used_for_admission_count: 0
- strategy_file_diff_clean: {summary['strategy_file_diff_clean']}
- acceptance_decision: {summary['acceptance_decision']}
"""


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
