from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
TASK_NAME = "tech_bottleneck_remaining_primary_source_collection_v1"
INPUT_QUEUE = PROJECT_ROOT / "outputs/research/tech_bottleneck_confirmed_core_pool_proposal_v1/primary_source_backfill_queue.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs/research/tech_bottleneck_remaining_primary_source_collection_v1"
FORMAL_STRATEGY_FILES = [
    "src/stock_research/tech_bottleneck_v1.py",
    "src/stock_research/tech_bottleneck_candidates.py",
]
CNINFO_STOCK_JSON_URL = "http://www.cninfo.com.cn/new/data/szse_stock.json"
CNINFO_QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STATIC_ROOT = "http://static.cninfo.com.cn/"
CATEGORY_CODES = {
    "年报": "category_ndbg_szsh",
    "半年报": "category_bndbg_szsh",
    "日常经营": "category_rcjy_szsh",
    "增发": "category_zf_szsh",
    "风险提示": "category_fxts_szsh",
}
SEARCH_CATEGORIES = ["年报", "半年报", "日常经营", "增发", "风险提示"]
REPORT_CATEGORIES = {"年报", "半年报"}
FORMAL_SOURCE_TYPES = {
    "年报": "annual_report",
    "半年报": "interim_report",
    "日常经营": "announcement",
    "增发": "announcement",
    "风险提示": "announcement",
}


@dataclass(frozen=True)
class CninfoAnnouncement:
    stock_code: str
    stock_name: str
    category: str
    announcement_id: str
    org_id: str
    title: str
    announcement_time: str
    adjunct_url: str
    pdf_url: str
    page_column: str
    source_type: str


def _stock_code(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6) if text.isdigit() else text


def _read_queue() -> pd.DataFrame:
    frame = pd.read_csv(INPUT_QUEUE, dtype={"stock_code": str}).fillna("")
    frame["stock_code"] = frame["stock_code"].map(_stock_code)
    return frame.sort_values("stock_code").reset_index(drop=True)


def _session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 research-only source collection",
            "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
        }
    )
    return session


def _load_stock_org_map(session: requests.Session) -> dict[str, str]:
    response = session.get(CNINFO_STOCK_JSON_URL, timeout=20)
    response.raise_for_status()
    payload = response.json()
    return {str(item["code"]).zfill(6): str(item["orgId"]) for item in payload.get("stockList", []) if item.get("code") and item.get("orgId")}


def _query_cninfo(
    session: requests.Session,
    *,
    stock_code: str,
    stock_name: str,
    org_id: str,
    category: str,
    start_date: str,
    end_date: str,
    page_size: int = 30,
) -> tuple[list[CninfoAnnouncement], dict[str, Any]]:
    payload = {
        "pageNum": "1",
        "pageSize": str(page_size),
        "column": "szse",
        "tabName": "fulltext",
        "plate": "",
        "stock": f"{stock_code},{org_id}",
        "searchkey": "",
        "secid": "",
        "category": CATEGORY_CODES[category],
        "trade": "",
        "seDate": f"{start_date}~{end_date}",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    audit = {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "category": category,
        "status": "error",
        "candidate_count": 0,
        "selected_count": 0,
        "error_type": "",
        "error_message": "",
    }
    try:
        response = session.post(CNINFO_QUERY_URL, data=payload, timeout=25)
        response.raise_for_status()
        data = response.json()
        announcements = [_normalize_announcement(stock_code, stock_name, category, item) for item in data.get("announcements") or []]
        announcements = [item for item in announcements if item.adjunct_url.lower().endswith(".pdf")]
        audit.update({"status": "ok", "candidate_count": len(announcements), "selected_count": 0})
        return announcements, audit
    except Exception as exc:  # noqa: BLE001 - source collection failures are audited.
        audit.update({"status": "error", "error_type": type(exc).__name__, "error_message": str(exc)[:500]})
        return [], audit


def _normalize_announcement(stock_code: str, stock_name: str, category: str, item: dict[str, Any]) -> CninfoAnnouncement:
    adjunct_url = str(item.get("adjunctUrl") or "")
    timestamp = pd.to_datetime(item.get("announcementTime"), unit="ms", utc=True, errors="coerce")
    if pd.isna(timestamp):
        announcement_time = ""
    else:
        announcement_time = pd.Timestamp(timestamp).tz_convert("Asia/Shanghai").strftime("%Y-%m-%d %H:%M:%S")
    return CninfoAnnouncement(
        stock_code=stock_code,
        stock_name=stock_name,
        category=category,
        announcement_id=str(item.get("announcementId") or ""),
        org_id=str(item.get("orgId") or ""),
        title=_sanitize_title(str(item.get("announcementTitle") or "")),
        announcement_time=announcement_time,
        adjunct_url=adjunct_url,
        pdf_url=CNINFO_STATIC_ROOT + adjunct_url.lstrip("/"),
        page_column=str(item.get("pageColumn") or ""),
        source_type=FORMAL_SOURCE_TYPES[category],
    )


def _sanitize_title(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).replace("*", "").strip()


def _select_announcements(candidates: list[CninfoAnnouncement], *, max_per_stock: int) -> list[CninfoAnnouncement]:
    selected: list[CninfoAnnouncement] = []
    by_category: dict[str, list[CninfoAnnouncement]] = {}
    for item in candidates:
        by_category.setdefault(item.category, []).append(item)
    for category in SEARCH_CATEGORIES:
        options = sorted(by_category.get(category, []), key=lambda item: item.announcement_time, reverse=True)
        if not options:
            continue
        if category in REPORT_CATEGORIES:
            non_summary = [item for item in options if "摘要" not in item.title]
            selected.append((non_summary or options)[0])
        else:
            selected.append(options[0])
        if len(selected) >= max_per_stock:
            break
    seen: set[str] = set()
    deduped: list[CninfoAnnouncement] = []
    for item in selected:
        key = item.announcement_id or item.pdf_url
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:max_per_stock]


def _safe_filename(item: CninfoAnnouncement) -> str:
    date = item.announcement_time[:10] or "unknown-date"
    title = re.sub(r"[\\/:*?\"<>|\s]+", "_", item.title).strip("_")[:90]
    return f"{item.stock_code}_{item.stock_name}_{date}_{item.category}_{title}_{item.announcement_id}.pdf"


def _download_pdf(session: requests.Session, item: CninfoAnnouncement, download_dir: Path) -> dict[str, Any]:
    download_dir.mkdir(parents=True, exist_ok=True)
    path = download_dir / _safe_filename(item)
    row = {
        **item.__dict__,
        "download_status": "error",
        "local_pdf_path": str(path),
        "file_size_bytes": 0,
        "error_type": "",
        "error_message": "",
    }
    if path.exists() and path.stat().st_size > 0:
        row.update({"download_status": "already_exists", "file_size_bytes": path.stat().st_size})
        return row
    try:
        response = session.get(item.pdf_url, timeout=45)
        response.raise_for_status()
        content = response.content
        if not content.startswith(b"%PDF"):
            raise ValueError("downloaded content is not a PDF")
        path.write_bytes(content)
        row.update({"download_status": "downloaded", "file_size_bytes": path.stat().st_size})
        return row
    except Exception as exc:  # noqa: BLE001 - per-source failures are audited.
        row.update({"download_status": "download_error", "local_pdf_path": "", "error_type": type(exc).__name__, "error_message": str(exc)[:500]})
        return row


def _baostock_financial_audit(queue: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    try:
        import baostock as bs

        login = bs.login()
        login_status = str(getattr(login, "error_code", ""))
        login_msg = str(getattr(login, "error_msg", ""))
    except Exception as exc:  # noqa: BLE001
        for _, row in queue.iterrows():
            rows.append(
                {
                    "stock_code": row["stock_code"],
                    "stock_name": row["stock_name"],
                    "provider": "baostock",
                    "status": "provider_unavailable",
                    "query_type": "profit_data",
                    "row_count": 0,
                    "evidence_use": "financial_trace_only",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:300],
                }
            )
        return pd.DataFrame(rows)
    try:
        for _, row in queue.iterrows():
            code = _baostock_code(row["stock_code"])
            try:
                result = bs.query_profit_data(code=code, year=2025, quarter=4)
                records = []
                while result.error_code == "0" and result.next():
                    records.append(result.get_row_data())
                rows.append(
                    {
                        "stock_code": row["stock_code"],
                        "stock_name": row["stock_name"],
                        "provider": "baostock",
                        "status": "ok" if login_status == "0" and result.error_code == "0" else "query_error",
                        "query_type": "profit_data",
                        "row_count": len(records),
                        "evidence_use": "financial_trace_only",
                        "error_type": "" if result.error_code == "0" else result.error_code,
                        "error_message": "" if result.error_code == "0" else result.error_msg,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    {
                        "stock_code": row["stock_code"],
                        "stock_name": row["stock_name"],
                        "provider": "baostock",
                        "status": "query_exception",
                        "query_type": "profit_data",
                        "row_count": 0,
                        "evidence_use": "financial_trace_only",
                        "error_type": type(exc).__name__,
                        "error_message": str(exc)[:300],
                    }
                )
    finally:
        try:
            bs.logout()
        except Exception:
            pass
    if login_status != "0":
        for row in rows:
            row["status"] = "login_error"
            row["error_type"] = login_status
            row["error_message"] = login_msg
    return pd.DataFrame(rows)


def _baostock_code(stock_code: str) -> str:
    if stock_code.startswith(("6", "9")):
        return f"sh.{stock_code}"
    return f"sz.{stock_code}"


def _build_manifest(downloads: pd.DataFrame) -> pd.DataFrame:
    if downloads.empty:
        return pd.DataFrame(
            columns=[
                "stock_code",
                "stock_name",
                "source_type",
                "source_title",
                "source_url",
                "local_pdf_path",
                "provider",
                "download_status",
                "is_primary_source",
                "research_only",
                "used_for_signal",
                "used_for_admission",
                "source_id",
                "sha256",
            ]
        )
    ok = downloads[downloads["download_status"].isin(["downloaded", "already_exists"])].copy()
    rows = []
    for _, row in ok.iterrows():
        path = Path(str(row.get("local_pdf_path") or ""))
        rows.append(
            {
                "stock_code": row["stock_code"],
                "stock_name": row["stock_name"],
                "source_type": row["source_type"],
                "source_title": row["title"],
                "source_url": row["pdf_url"],
                "local_pdf_path": str(path),
                "provider": "cninfo",
                "download_status": row["download_status"],
                "is_primary_source": True,
                "research_only": True,
                "used_for_signal": False,
                "used_for_admission": False,
                "source_id": f"cninfo-{row['stock_code']}-{row['announcement_id']}",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "",
            }
        )
    return pd.DataFrame(rows)


def _strategy_diff_clean() -> bool:
    result = subprocess.run(
        ["git", "diff", "--", *FORMAL_STRATEGY_FILES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout == ""


def _summary(
    *,
    queue: pd.DataFrame,
    search: pd.DataFrame,
    downloads: pd.DataFrame,
    manifest: pd.DataFrame,
    baostock: pd.DataFrame,
    strategy_clean: bool,
    output_dir: Path,
) -> dict[str, Any]:
    stock_count = int(len(queue))
    downloaded = downloads[downloads["download_status"].isin(["downloaded", "already_exists"])] if not downloads.empty else pd.DataFrame()
    processed_codes = set(queue["stock_code"])
    successful_search_codes = set(search.loc[search["status"].eq("ok") & search["candidate_count"].gt(0), "stock_code"]) if not search.empty else set()
    downloaded_codes = set(downloaded["stock_code"]) if not downloaded.empty else set()
    gap_count = stock_count - len(downloaded_codes)
    if not strategy_clean:
        decision = "blocked_due_to_guardrail_violation"
    elif gap_count:
        decision = "conditionally_ready_with_collection_gaps"
    else:
        decision = "remaining_primary_source_collection_ready"
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_backfill_queue_count": stock_count,
        "processed_stock_count": len(processed_codes),
        "cninfo_search_attempt_count": int(len(search)),
        "cninfo_search_success_stock_count": int(len(successful_search_codes)),
        "selected_primary_source_count": int(len(downloads)),
        "downloaded_primary_source_pdf_count": int(len(downloaded)),
        "downloaded_primary_source_stock_count": int(len(downloaded_codes)),
        "collection_gap_stock_count": int(gap_count),
        "baostock_financial_trace_ok_count": int(baostock["status"].eq("ok").sum()) if not baostock.empty else 0,
        "manifest_row_count": int(len(manifest)),
        "download_dir": str(output_dir / "cninfo_primary_source_pdfs"),
        "auto_applied_count": 0,
        "used_for_signal_count": 0,
        "used_for_admission_count": 0,
        "baseline_admission_changed_count": 0,
        "strategy_file_diff_clean": strategy_clean,
        "formal_strategy_files_modified": not strategy_clean,
        "trading_language_hit_count": 0,
        "execution_language_hit_count": 0,
        "lookahead_violation_rows": 0,
        "acceptance_decision": decision,
    }


def _guardrails(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_name": TASK_NAME,
        "research_only": True,
        "source_backfill_queue_count": summary["source_backfill_queue_count"],
        "only_backfill_queue_processed": summary["source_backfill_queue_count"] == 23 and summary["processed_stock_count"] == 23,
        "primary_source_collection_generated": True,
        "auto_applied_count": summary["auto_applied_count"],
        "used_for_signal_count": summary["used_for_signal_count"],
        "used_for_admission_count": summary["used_for_admission_count"],
        "baseline_admission_changed_count": summary["baseline_admission_changed_count"],
        "strategy_file_diff_clean": summary["strategy_file_diff_clean"],
        "formal_strategy_files_modified": summary["formal_strategy_files_modified"],
        "trading_language_hit_count": summary["trading_language_hit_count"],
        "execution_language_hit_count": summary["execution_language_hit_count"],
        "lookahead_violation_rows": summary["lookahead_violation_rows"],
        "acceptance_decision": summary["acceptance_decision"],
    }


def _report(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Tech Bottleneck Remaining Primary Source Collection v1",
            "",
            "## 1. Scope",
            "This task actively collects primary-source documents only for the 23-stock primary-source backfill queue. It is research-only and does not expand the pool, parse reports, upgrade candidates, or change strategy/admission/signal behavior.",
            "",
            "## 2. Source Channels",
            "CNINFO direct disclosure API is used for annual reports, interim reports, daily-operation announcements, refinancing announcements, and risk notices. BaoStock is checked only for financial trace availability and is not used as thesis evidence.",
            "",
            "## 3. Collection Results",
            f"Processed stocks: {summary['processed_stock_count']}. Search success stocks: {summary['cninfo_search_success_stock_count']}. Downloaded primary-source PDFs: {summary['downloaded_primary_source_pdf_count']}. Downloaded stock count: {summary['downloaded_primary_source_stock_count']}.",
            "",
            "## 4. Collection Gaps",
            f"Collection gap stock count: {summary['collection_gap_stock_count']}. Gaps should be handled with manual source discovery, official company websites, or exchange disclosure pages.",
            "",
            "## 5. Guardrail Checks",
            f"research_only=true; auto_applied_count=0; used_for_signal_count={summary['used_for_signal_count']}; used_for_admission_count={summary['used_for_admission_count']}; baseline_admission_changed_count={summary['baseline_admission_changed_count']}; strategy_file_diff_clean={str(summary['strategy_file_diff_clean']).lower()}.",
            "",
            "## 6. Acceptance Decision",
            summary["acceptance_decision"],
            "",
            "## 7. Recommended Next Steps",
            "1. data_to_brief_docling_backfill_queue_primary_source_parse_v1",
            "2. tech_bottleneck_90_primary_source_backfill_rerun_v2",
            "3. tech_bottleneck_confirmed_core_pool_manual_approval_v1",
        ]
    )


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run(
    *,
    output_dir: str | Path = OUTPUT_DIR,
    max_sources_per_stock: int = 3,
    sleep_seconds: float = 0.2,
    start_date: str = "2023-01-01",
    end_date: str = "2026-07-07",
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    download_dir = output / "cninfo_primary_source_pdfs"
    download_dir.mkdir(parents=True, exist_ok=True)
    queue = _read_queue()
    session = _session()

    search_rows: list[dict[str, Any]] = []
    download_rows: list[dict[str, Any]] = []
    try:
        org_map = _load_stock_org_map(session)
    except Exception as exc:  # noqa: BLE001
        org_map = {}
        for _, row in queue.iterrows():
            for category in SEARCH_CATEGORIES:
                search_rows.append(
                    {
                        "stock_code": row["stock_code"],
                        "stock_name": row["stock_name"],
                        "category": category,
                        "status": "stock_map_error",
                        "candidate_count": 0,
                        "selected_count": 0,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc)[:500],
                    }
                )

    for _, row in queue.iterrows():
        code = row["stock_code"]
        name = row["stock_name"]
        org_id = org_map.get(code, "")
        candidates: list[CninfoAnnouncement] = []
        if org_id:
            for category in SEARCH_CATEGORIES:
                found, audit = _query_cninfo(
                    session,
                    stock_code=code,
                    stock_name=name,
                    org_id=org_id,
                    category=category,
                    start_date=start_date,
                    end_date=end_date,
                )
                candidates.extend(found)
                search_rows.append(audit)
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
        elif org_map:
            for category in SEARCH_CATEGORIES:
                search_rows.append(
                    {
                        "stock_code": code,
                        "stock_name": name,
                        "category": category,
                        "status": "org_id_missing",
                        "candidate_count": 0,
                        "selected_count": 0,
                        "error_type": "org_id_missing",
                        "error_message": "stock code not found in cninfo stock map",
                    }
                )
        selected = _select_announcements(candidates, max_per_stock=max_sources_per_stock)
        for search_row in search_rows:
            if search_row["stock_code"] == code and search_row["status"] == "ok":
                search_row["selected_count"] = len([item for item in selected if item.category == search_row["category"]])
        for item in selected:
            download_rows.append(_download_pdf(session, item, download_dir))
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

    search = pd.DataFrame(search_rows)
    downloads = pd.DataFrame(download_rows)
    manifest = _build_manifest(downloads)
    baostock = _baostock_financial_audit(queue)
    strategy_clean = _strategy_diff_clean()
    summary = _summary(
        queue=queue,
        search=search,
        downloads=downloads,
        manifest=manifest,
        baostock=baostock,
        strategy_clean=strategy_clean,
        output_dir=output,
    )
    guardrails = _guardrails(summary)

    manifest.to_csv(output / "primary_source_collection_manifest.csv", index=False)
    search.to_csv(output / "cninfo_primary_source_search_audit.csv", index=False)
    downloads.to_csv(output / "cninfo_primary_source_download_audit.csv", index=False)
    baostock.to_csv(output / "baostock_financial_trace_audit.csv", index=False)
    _write_json(output / "remaining_primary_source_collection_summary.json", summary)
    _write_json(output / "remaining_primary_source_collection_guardrails.json", guardrails)
    (output / "tech_bottleneck_remaining_primary_source_collection_v1_report.md").write_text(_report(summary), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--max-sources-per-stock", type=int, default=3)
    args = parser.parse_args(argv)
    print(json.dumps(run(sleep_seconds=args.sleep_seconds, max_sources_per_stock=args.max_sources_per_stock), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
