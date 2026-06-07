from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pandas as pd
import requests

from stock_research.config import SETTINGS
from stock_research.hibor_reports import (
    DEFAULT_HIBOR_INSTITUTIONS_CONFIG,
    choose_hibor_reports_by_tier,
    load_hibor_a_tier_institutions,
    normalize_hibor_broker,
)
from stock_research.stock_report_pdf_backfill import (
    build_stock_report_pdf_field_backfill,
    upsert_stock_report_pdf_fields,
)
from stock_research.stock_report_web_collection import (
    build_stock_report_features_from_events,
    upsert_stock_report_features,
    upsert_stock_report_sources_events,
)


YANBAOKE_SOURCE_TYPE = "yanbaoke_api"
YANBAOKE_SOURCE_NAME = "研报客 API"
YANBAOKE_SKILL_ID = "yanbaoke-research-report-download"
YANBAOKE_SKILL_VERSION = "2.1.0"
YANBAOKE_SEARCH_URL = "https://api.yanbaoke.cn/skills/search_report"
YANBAOKE_DOWNLOAD_URL = "https://api.yanbaoke.cn/skills/report_download"
YANBAOKE_TASKS_FILE = "yanbaoke_backfill_tasks.csv"
YANBAOKE_DISCOVERED_FILE = "yanbaoke_discovered_reports.csv"
YANBAOKE_FILTERED_FILE = "yanbaoke_filtered_reports.csv"
YANBAOKE_DOWNLOADS_FILE = "yanbaoke_downloaded_reports.csv"
YANBAOKE_REPORT_FILE = "yanbaoke_backfill_report.md"
YANBAOKE_SOURCE_FILE = "yanbaoke_report_source_candidates.csv"
YANBAOKE_EVENT_FILE = "yanbaoke_report_event_candidates.csv"


def search_yanbaoke_reports(
    *,
    keyword: str,
    size: int = 100,
    search_type: str = "title",
    org: str | None = None,
    report_type: str | None = None,
    stock: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    min_pages: int | None = None,
    max_pages: int | None = None,
    get_json: Any | None = None,
) -> dict[str, Any]:
    params = {
        "keyword": keyword,
        "size": str(max(1, min(int(size), 500))),
        "search_type": search_type,
    }
    if org:
        params["institution"] = org
    if report_type:
        params["reporttype"] = report_type
    if stock:
        params["stockname"] = stock
    if start_date:
        params["startdate"] = start_date
    if end_date:
        params["enddate"] = end_date
    if min_pages is not None:
        params["minpagenum"] = str(min_pages)
    if max_pages is not None:
        params["maxpagenum"] = str(max_pages)
    headers = _yanbaoke_headers()
    fetch_json = get_json or _http_get_json
    payload = fetch_json(f"{YANBAOKE_SEARCH_URL}?{urlencode(params)}", headers=headers)
    if not payload.get("success"):
        raise ValueError(str(payload.get("message") or "Yanbaoke search failed"))
    reports = pd.DataFrame(payload.get("data") or [])
    return {
        "total": int(payload.get("total") or len(reports)),
        "message": str(payload.get("message") or ""),
        "reports": reports,
    }


def filter_yanbaoke_reports(
    reports: pd.DataFrame,
    *,
    ts_code: str,
    stock_name: str,
    start_date: str,
    end_date: str,
    institutions_path: str | Path = DEFAULT_HIBOR_INSTITUTIONS_CONFIG,
    fallback_tier: str | None = "B",
) -> pd.DataFrame:
    if reports.empty:
        return pd.DataFrame()
    rules = load_hibor_a_tier_institutions(institutions_path)
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    symbol = ts_code.split(".")[0]
    rows = []
    for row in reports.fillna("").to_dict("records"):
        title = str(row.get("title") or "")
        org_name = str(row.get("org_name") or "")
        publish_date = _safe_date(row.get("time")) or _date_from_yanbaoke_title(title)
        if not publish_date:
            continue
        publish_ts = pd.Timestamp(publish_date)
        if publish_ts < start or publish_ts > end:
            continue
        if stock_name and stock_name not in title and stock_name not in str(row.get("content") or ""):
            continue
        if symbol and symbol not in title and symbol not in str(row.get("content") or ""):
            continue
        rule = normalize_hibor_broker(f"{org_name} {title}", rules)
        if not rule:
            continue
        if "pdf" not in [str(fmt).lower() for fmt in row.get("formats") or []]:
            continue
        enriched = dict(row)
        report_title = _clean_yanbaoke_report_title(title, stock_name=stock_name, symbol=symbol, broker=rule.get("institution_name", ""))
        enriched.update(
            {
                "detail_url": str(row.get("url") or ""),
                "publish_date": publish_date,
                "asset_id": f"CN:{_exchange_from_ts_code(ts_code)}:{symbol}",
                "ts_code": ts_code,
                "symbol": symbol,
                "stock_name": stock_name,
                "broker": rule.get("institution_name", ""),
                "broker_alias": rule.get("alias", ""),
                "broker_tier": rule.get("tier", ""),
                "broker_group": rule.get("group", ""),
                "broker_region": rule.get("region", ""),
                "report_title": report_title,
                "dedupe_key": _stable_token([str(row.get("uuid") or ""), title, publish_date]),
            }
        )
        rows.append(enriched)
    filtered = pd.DataFrame(rows)
    if filtered.empty:
        return filtered
    filtered = filtered.drop_duplicates(subset=["dedupe_key"]).reset_index(drop=True)
    return choose_hibor_reports_by_tier(filtered, fallback_tier=fallback_tier)


def choose_yanbaoke_download_candidates(
    candidates: pd.DataFrame,
    *,
    existing_downloads: pd.DataFrame,
    top_ts_codes: set[str] | None = None,
    position_ts_codes: set[str] | None = None,
    monthly_budget: int = 1000,
    base_budget: int = 600,
    top_budget: int = 300,
    reserve_budget: int = 100,
    base_target_per_stock: int = 1,
    depth_target_per_stock: int = 3,
    max_broker_share: float | None = 0.25,
) -> pd.DataFrame:
    if candidates.empty or monthly_budget <= 0:
        return pd.DataFrame(columns=list(candidates.columns) + ["budget_bucket"])
    top_codes = set(top_ts_codes or set())
    position_codes = set(position_ts_codes or set())
    existing = existing_downloads.copy() if not existing_downloads.empty else pd.DataFrame()
    downloaded_existing = existing[existing.get("status", pd.Series(dtype=object)).astype(str).eq("downloaded")] if not existing.empty else existing
    existing_uuids = set(downloaded_existing.get("uuid", pd.Series(dtype=object)).astype(str)) if not downloaded_existing.empty else set()
    existing_counts = downloaded_existing.groupby("ts_code").size().to_dict() if not downloaded_existing.empty and "ts_code" in downloaded_existing else {}
    existing_broker_counts = (
        downloaded_existing.groupby("broker").size().to_dict()
        if not downloaded_existing.empty and "broker" in downloaded_existing
        else {}
    )
    existing_brokers_by_stock = (
        downloaded_existing.groupby("ts_code")["broker"].apply(lambda values: set(values.dropna().astype(str))).to_dict()
        if not downloaded_existing.empty and {"ts_code", "broker"}.issubset(downloaded_existing.columns)
        else {}
    )
    frame = candidates.copy()
    frame = frame[~frame["uuid"].astype(str).isin(existing_uuids)].copy()
    if frame.empty:
        return pd.DataFrame(columns=list(candidates.columns) + ["budget_bucket"])
    if "pagenum" not in frame.columns:
        frame["pagenum"] = 0
    frame["_tier_rank"] = frame["broker_tier"].astype(str).str.upper().map({"A": 0, "B": 1}).fillna(9)
    frame["_date_rank"] = pd.to_datetime(frame.get("publish_date", ""), errors="coerce")
    frame = frame.sort_values(["_tier_rank", "_date_rank", "pagenum"], ascending=[True, False, False], na_position="last")

    remaining = {"monthly": monthly_budget, "base_coverage": base_budget, "weekly_top10": top_budget, "reserve": reserve_budget}
    chosen: list[dict[str, Any]] = []
    chosen_counts: dict[str, int] = {}
    chosen_broker_counts: dict[str, int] = {}
    used_brokers: dict[str, set[str]] = {str(ts_code): set(brokers) for ts_code, brokers in existing_brokers_by_stock.items()}
    broker_cap = None
    if max_broker_share is not None and float(max_broker_share) > 0:
        broker_cap = max(1, int(math.ceil(float(monthly_budget) * float(max_broker_share))))

    def can_take(ts_code: str, target: int) -> bool:
        return int(existing_counts.get(ts_code, 0)) + int(chosen_counts.get(ts_code, 0)) < target

    def can_take_broker(broker: str) -> bool:
        if not broker or broker_cap is None:
            return True
        return int(existing_broker_counts.get(broker, 0)) + int(chosen_broker_counts.get(broker, 0)) < broker_cap

    def take(rows: pd.DataFrame, bucket: str, target: int) -> None:
        nonlocal chosen
        if remaining["monthly"] <= 0 or remaining[bucket] <= 0:
            return
        for row in rows.to_dict("records"):
            if remaining["monthly"] <= 0 or remaining[bucket] <= 0:
                break
            ts_code = str(row.get("ts_code") or "")
            if not can_take(ts_code, target):
                continue
            broker = str(row.get("broker") or "")
            if not can_take_broker(broker):
                continue
            if broker and broker in used_brokers.get(ts_code, set()) and can_take(ts_code, target):
                same_stock = rows[rows["ts_code"].astype(str).eq(ts_code)]
                if len(set(same_stock.get("broker", pd.Series(dtype=object)).astype(str)) - used_brokers.get(ts_code, set())) > 0:
                    continue
            enriched = dict(row)
            enriched["budget_bucket"] = bucket
            chosen.append(enriched)
            chosen_counts[ts_code] = chosen_counts.get(ts_code, 0) + 1
            chosen_broker_counts[broker] = chosen_broker_counts.get(broker, 0) + 1
            used_brokers.setdefault(ts_code, set()).add(broker)
            remaining["monthly"] -= 1
            remaining[bucket] -= 1

    base_rows = frame[~frame["ts_code"].astype(str).isin(top_codes | position_codes)].copy()
    take(base_rows, "base_coverage", base_target_per_stock)

    depth_rows = frame[frame["ts_code"].astype(str).isin(top_codes | position_codes)].copy()
    take(depth_rows, "weekly_top10", depth_target_per_stock)

    already = {str(row.get("uuid") or "") for row in chosen}
    reserve_rows = frame[~frame["uuid"].astype(str).isin(already)].copy()
    for _, group in reserve_rows.groupby("ts_code", sort=False):
        target = depth_target_per_stock if str(group.iloc[0].get("ts_code") or "") in top_codes | position_codes else base_target_per_stock
        take(group, "reserve", target)

    result = pd.DataFrame(chosen)
    if result.empty:
        return pd.DataFrame(columns=list(candidates.columns) + ["budget_bucket"])
    return result.drop(columns=[column for column in ["_tier_rank", "_date_rank"] if column in result.columns]).reset_index(drop=True)


def download_yanbaoke_report_pdf(
    *,
    uuid: str,
    output_dir: str | Path,
    api_key: str | None = None,
    file_format: str = "pdf",
    get_json: Any | None = None,
    get_binary: Any | None = None,
) -> dict[str, Any]:
    key = api_key or os.environ.get("YANBAOKE_API_KEY", "")
    if not key:
        raise ValueError("YANBAOKE_API_KEY is required for Yanbaoke downloads")
    headers = _yanbaoke_headers(api_key=key)
    fetch_json = get_json or _http_get_json
    payload = fetch_json(f"{YANBAOKE_DOWNLOAD_URL}/{uuid}?format={file_format}", headers=headers)
    report = _yanbaoke_download_report(payload)
    download_url = str(report.get("download_url") or "")
    if not download_url:
        raise ValueError("Yanbaoke download URL missing")
    fetch_binary = get_binary or _http_get_binary
    content = fetch_binary(download_url)
    if not content.startswith(b"%PDF"):
        return {
            "uuid": uuid,
            "status": "not_pdf",
            "download_url": download_url,
            "pdf_path": "",
            "filename": str(report.get("filename") or ""),
        }
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(str(report.get("filename") or f"{uuid}.pdf"))
    pdf_path = output / filename
    pdf_path.write_bytes(content)
    return {
        "uuid": uuid,
        "status": "downloaded",
        "download_url": download_url,
        "pdf_path": str(pdf_path),
        "filename": filename,
        "title": str(report.get("title") or ""),
        "format": str(report.get("format") or file_format),
        "expires_in": int(report.get("expires_in") or 60),
    }


def build_yanbaoke_sources_events_from_downloads(downloads: pd.DataFrame) -> dict[str, pd.DataFrame]:
    source_rows = []
    event_rows = []
    for row in downloads.fillna("").to_dict("records"):
        status = str(row.get("status") or "downloaded")
        if status != "downloaded" or not row.get("pdf_path"):
            continue
        pdf_path = Path(str(row["pdf_path"])).expanduser().resolve()
        source_url = pdf_path.as_uri()
        report_id = f"yanbaoke_{_stable_token([str(row.get('uuid') or ''), source_url])}"
        metadata = {
            "yanbaoke": {
                "uuid": row.get("uuid") or "",
                "detail_url": row.get("detail_url") or "",
                "download_url": row.get("download_url") or "",
                "local_pdf_path": str(pdf_path),
                "filename": pdf_path.name,
                "broker_tier": row.get("broker_tier") or "",
                "broker_group": row.get("broker_group") or "",
                "broker_region": row.get("broker_region") or "",
                "selected_tier_reason": row.get("selected_tier_reason") or "",
                "rtype_name": row.get("rtype_name") or "",
                "pagenum": row.get("pagenum") or "",
            }
        }
        source_rows.append(
            {
                "report_id": report_id,
                "source_type": YANBAOKE_SOURCE_TYPE,
                "source_name": YANBAOKE_SOURCE_NAME,
                "broker": row.get("broker") or row.get("org_name") or "",
                "analyst": "",
                "report_title": row.get("report_title") or row.get("title") or "",
                "publish_date": row.get("publish_date") or row.get("time") or "",
                "source_url": source_url,
                "public_access": False,
                "copyright_note": "Downloaded from Yanbaoke API for internal research use only.",
                "source_confidence": 0.9 if row.get("broker_tier") == "A" else 0.75,
                "raw_summary": str(row.get("content") or "")[:2000],
                "metadata": json.dumps(metadata, ensure_ascii=False),
            }
        )
        event_rows.append(
            {
                "report_id": report_id,
                "asset_id": row.get("asset_id") or "",
                "ts_code": row.get("ts_code") or "",
                "stock_name": row.get("stock_name") or "",
                "industry_name": "",
                "report_date": row.get("publish_date") or row.get("time") or "",
                "rating": "",
                "rating_change": "",
                "target_price": pd.NA,
                "target_upside": pd.NA,
                "industry_view": "",
                "company_view": "",
                "risk_summary": "",
                "effective_start_date": row.get("publish_date") or row.get("time") or "",
                "effective_end_date": pd.NA,
                "auto_trade_enabled": False,
                "metadata": json.dumps(metadata, ensure_ascii=False),
            }
        )
    return {
        "sources": pd.DataFrame(source_rows, dtype=object),
        "events": pd.DataFrame(event_rows, dtype=object),
    }


def import_yanbaoke_report_downloads(
    downloads: pd.DataFrame,
    *,
    output_dir: str | Path,
    write_db: bool = False,
    service: str = SETTINGS.research_service,
    run_pdf_backfill: bool = True,
    feature_trade_date: str | None = None,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    built = build_yanbaoke_sources_events_from_downloads(downloads)
    sources = built["sources"]
    events = built["events"]
    source_path = output / YANBAOKE_SOURCE_FILE
    event_path = output / YANBAOKE_EVENT_FILE
    sources.to_csv(source_path, index=False)
    events.to_csv(event_path, index=False)
    db_result = None
    if write_db:
        db_result = upsert_stock_report_sources_events(sources=sources, events=events, service=service)
    pdf_result = None
    feature_events = events
    if run_pdf_backfill:
        pdf_result = build_stock_report_pdf_field_backfill(sources=sources, output_dir=output, resume=True)
        if write_db:
            pdf_result["db"] = upsert_stock_report_pdf_fields(pdf_result["fields"], service=service)
    feature_result = None
    if feature_trade_date:
        feature_result = build_stock_report_features_from_events(feature_events, trade_date=feature_trade_date, output_dir=output)
        if write_db:
            feature_result["db"] = upsert_stock_report_features(features=feature_result["features"], service=service)
    paths = {"sources": str(source_path), "events": str(event_path)}
    if pdf_result and pdf_result.get("paths", {}).get("fields"):
        paths["fields"] = pdf_result["paths"]["fields"]
    if feature_result and feature_result.get("paths", {}).get("features"):
        paths["features"] = feature_result["paths"]["features"]
    return {
        "summary": {"pdf_count": len(sources), "source_rows": len(sources), "event_rows": len(events), "write_db": write_db},
        "sources": sources,
        "events": events,
        "pdf": pdf_result,
        "features": feature_result["features"] if feature_result else pd.DataFrame(),
        "db": db_result,
        "paths": paths,
    }


def run_yanbaoke_report_backfill(
    *,
    tasks_path: str | Path,
    output_dir: str | Path = "outputs/research/yanbaoke_backfill",
    download_dir: str | Path | None = None,
    api_key: str | None = None,
    institutions_path: str | Path = DEFAULT_HIBOR_INSTITUTIONS_CONFIG,
    fallback_tier: str | None = "B",
    max_tasks: int | None = None,
    max_downloads: int | None = None,
    monthly_budget: int = 1000,
    base_budget: int = 600,
    top_budget: int = 300,
    reserve_budget: int = 100,
    top_ts_codes: set[str] | None = None,
    position_ts_codes: set[str] | None = None,
    base_target_per_stock: int = 1,
    depth_target_per_stock: int = 3,
    max_broker_share: float | None = 0.25,
    write_db: bool = False,
    service: str = SETTINGS.research_service,
    import_pdfs: bool = True,
    run_pdf_backfill: bool = True,
    feature_trade_date: str | None = None,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    task_file = Path(tasks_path)
    tasks = pd.read_csv(task_file, dtype=object).fillna("")
    pdf_dir = Path(download_dir) if download_dir is not None else output / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    discovered_rows = _load_rows(output / YANBAOKE_DISCOVERED_FILE)
    filtered_rows = _load_rows(output / YANBAOKE_FILTERED_FILE)
    download_rows = _load_rows(output / YANBAOKE_DOWNLOADS_FILE)
    processed = 0
    downloaded_total = 0
    run_budget = max_downloads if max_downloads is not None else monthly_budget
    for idx, task in tasks.iterrows():
        if str(task.get("status") or "") != "pending":
            continue
        if max_tasks is not None and processed >= max_tasks:
            break
        if max_downloads is not None and downloaded_total >= max_downloads:
            break
        processed += 1
        tasks.at[idx, "started_at"] = _utc_now_iso()
        ts_code = str(task.get("ts_code") or "")
        stock_name = str(task.get("stock_name") or "")
        try:
            search_result = search_yanbaoke_reports(
                keyword=stock_name or ts_code.split(".")[0],
                start_date=str(task.get("start_date") or ""),
                end_date=str(task.get("end_date") or ""),
                size=100,
            )
            discovered = search_result["reports"]
            if not discovered.empty:
                discovered["asset_id"] = str(task.get("asset_id") or "")
                discovered["ts_code"] = ts_code
                discovered["stock_name"] = stock_name
                discovered_rows.extend(discovered.to_dict("records"))
            selected_all = filter_yanbaoke_reports(
                discovered,
                ts_code=ts_code,
                stock_name=stock_name,
                start_date=str(task.get("start_date") or ""),
                end_date=str(task.get("end_date") or ""),
                institutions_path=institutions_path,
                fallback_tier=fallback_tier,
            )
            tasks.at[idx, "discovered_count"] = len(selected_all)
            if not selected_all.empty:
                filtered_rows.extend(selected_all.to_dict("records"))
            if selected_all.empty:
                tasks.at[idx, "status"] = "no_qualified_report"
                tasks.at[idx, "downloaded_count"] = 0
                tasks.at[idx, "finished_at"] = _utc_now_iso()
                _persist(output, task_file, tasks, discovered_rows, filtered_rows, download_rows)
                continue
            selected = choose_yanbaoke_download_candidates(
                selected_all,
                existing_downloads=_manifest_frame(download_rows),
                top_ts_codes=top_ts_codes,
                position_ts_codes=position_ts_codes,
                monthly_budget=max(0, run_budget - downloaded_total),
                base_budget=base_budget,
                top_budget=top_budget,
                reserve_budget=reserve_budget,
                base_target_per_stock=base_target_per_stock,
                depth_target_per_stock=depth_target_per_stock,
                max_broker_share=max_broker_share,
            )
            if selected.empty:
                tasks.at[idx, "status"] = "coverage_satisfied"
                tasks.at[idx, "downloaded_count"] = 0
                tasks.at[idx, "finished_at"] = _utc_now_iso()
                _persist(output, task_file, tasks, discovered_rows, filtered_rows, download_rows)
                continue
            downloaded_count = 0
            for report in selected.to_dict("records"):
                if downloaded_total >= run_budget:
                    break
                download = download_yanbaoke_report_pdf(uuid=str(report.get("uuid") or ""), output_dir=pdf_dir, api_key=api_key)
                record = {**report, **download}
                download_rows.append(record)
                if download.get("status") == "downloaded":
                    downloaded_count += 1
                    downloaded_total += 1
            tasks.at[idx, "downloaded_count"] = downloaded_count
            tasks.at[idx, "status"] = "done" if downloaded_count == len(selected) else "pending"
            if downloaded_count != len(selected):
                tasks.at[idx, "error_type"] = "download_budget_exhausted"
                tasks.at[idx, "error_message"] = f"downloaded={downloaded_count}; expected={len(selected)}"
            tasks.at[idx, "finished_at"] = _utc_now_iso()
            _persist(output, task_file, tasks, discovered_rows, filtered_rows, download_rows)
        except Exception as exc:
            tasks.at[idx, "status"] = "search_error"
            tasks.at[idx, "error_type"] = type(exc).__name__
            tasks.at[idx, "error_message"] = str(exc)[:500]
            tasks.at[idx, "finished_at"] = _utc_now_iso()
            _persist(output, task_file, tasks, discovered_rows, filtered_rows, download_rows)
    paths = _persist(output, task_file, tasks, discovered_rows, filtered_rows, download_rows)
    import_result = None
    downloads = _manifest_frame(download_rows)
    if import_pdfs:
        import_result = import_yanbaoke_report_downloads(
            downloads,
            output_dir=output / "import",
            write_db=write_db,
            service=service,
            run_pdf_backfill=run_pdf_backfill,
            feature_trade_date=feature_trade_date,
        )
    return {
        "tasks": tasks,
        "discovered": _manifest_frame(discovered_rows),
        "filtered": _manifest_frame(filtered_rows),
        "downloads": downloads,
        "import": import_result,
        "summary": {
            "processed_tasks": processed,
            "downloaded_count": int(downloads["status"].eq("downloaded").sum()) if "status" in downloads else 0,
            "done_tasks": int(tasks["status"].eq("done").sum()) if "status" in tasks else 0,
        },
        "paths": paths,
    }


def _yanbaoke_headers(api_key: str | None = None) -> dict[str, str]:
    headers = {"X-Skill-Version": YANBAOKE_SKILL_VERSION, "X-Skill-ID": YANBAOKE_SKILL_ID}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _http_get_json(url: str, *, headers: dict[str, str]) -> dict[str, Any]:
    response = requests.get(url, timeout=30, headers=headers)
    response.raise_for_status()
    return response.json()


def _http_get_binary(url: str) -> bytes:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def _yanbaoke_download_report(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("choices") and payload["choices"][0].get("report"):
        return payload["choices"][0]["report"]
    if payload.get("download_url"):
        return payload
    raise ValueError("Unexpected Yanbaoke download response")


def _safe_date(value: Any) -> str:
    text = str(value or "")[:10]
    try:
        return pd.Timestamp(text).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _date_from_yanbaoke_title(title: str) -> str:
    match = re.search(r"(?P<date>20\d{6})", str(title or ""))
    if not match:
        return ""
    raw = match.group("date")
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def _clean_yanbaoke_report_title(title: str, *, stock_name: str, symbol: str, broker: str) -> str:
    text = re.sub(r"^20\d{6}-", "", str(title or ""))
    for part in [broker, stock_name, f"{symbol}.SH", f"{symbol}.SZ", f"{symbol}.BJ", symbol]:
        if part:
            text = text.replace(part, "")
    text = re.sub(r"[-_]+", " ", text).strip()
    text = re.sub(r"\s*(\d+页|\d+kb|\d+mb)\s*", "", text, flags=re.IGNORECASE)
    return text.strip(" -_") or str(title or "")


def _exchange_from_ts_code(ts_code: str) -> str:
    return ts_code.split(".")[-1] if "." in ts_code else "SH"


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]", "_", value).strip()
    return cleaned if cleaned.lower().endswith(".pdf") else f"{cleaned}.pdf"


def _stable_token(parts: list[str] | tuple[str, ...]) -> str:
    return hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:16]


def _utc_now_iso() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        return pd.read_csv(path, dtype=object).fillna("").to_dict("records")
    except pd.errors.EmptyDataError:
        return []


def _manifest_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    subset = [column for column in ["dedupe_key", "uuid", "pdf_path"] if column in frame.columns]
    if subset:
        frame = frame.drop_duplicates(subset=subset, keep="last")
    return frame


def _persist(
    output: Path,
    task_file: Path,
    tasks: pd.DataFrame,
    discovered_rows: list[dict[str, Any]],
    filtered_rows: list[dict[str, Any]],
    download_rows: list[dict[str, Any]],
) -> dict[str, str]:
    paths = {
        "tasks": task_file,
        "discovered": output / YANBAOKE_DISCOVERED_FILE,
        "filtered": output / YANBAOKE_FILTERED_FILE,
        "downloads": output / YANBAOKE_DOWNLOADS_FILE,
        "report": output / YANBAOKE_REPORT_FILE,
    }
    tasks.to_csv(paths["tasks"], index=False)
    _manifest_frame(discovered_rows).to_csv(paths["discovered"], index=False)
    _manifest_frame(filtered_rows).to_csv(paths["filtered"], index=False)
    _manifest_frame(download_rows).to_csv(paths["downloads"], index=False)
    paths["report"].write_text(_render_report(tasks, download_rows), encoding="utf-8")
    return {key: str(value) for key, value in paths.items()}


def _render_report(tasks: pd.DataFrame, download_rows: list[dict[str, Any]]) -> str:
    status_counts = tasks["status"].value_counts().to_dict() if "status" in tasks else {}
    lines = ["# Yanbaoke Report Backfill", "", f"- Tasks: {len(tasks)}", f"- Downloaded PDFs: {sum(1 for row in download_rows if row.get('status') == 'downloaded')}", "", "## Status"]
    for status, count in sorted(status_counts.items()):
        lines.append(f"- {status}: {count}")
    return "\n".join(lines) + "\n"
