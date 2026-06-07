from __future__ import annotations

import hashlib
import html
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse, parse_qs

import pandas as pd
import requests

from stock_research.config import SETTINGS
from stock_research.stock_report_pdf_backfill import (
    build_stock_report_pdf_field_backfill,
    upsert_stock_report_pdf_fields,
)
from stock_research.stock_report_web_collection import (
    build_stock_report_features_from_events,
    upsert_stock_report_features,
)
from stock_research.stock_report_web_collection import upsert_stock_report_sources_events


HIBOR_SOURCE_TYPE = "hibor_manual"
HIBOR_SOURCE_NAME = "慧博智能策略终端"
HIBOR_QUEUE_FILE = "hibor_download_queue.csv"
HIBOR_QUEUE_REPORT = "hibor_download_queue_report.md"
HIBOR_DOWNLOADS_FILE = "hibor_downloaded_reports.csv"
HIBOR_SOURCE_FILE = "hibor_report_source_candidates.csv"
HIBOR_EVENT_FILE = "hibor_report_event_candidates.csv"
HIBOR_IMPORT_REPORT = "hibor_report_import_report.md"
HIBOR_A_TIER_TASKS_FILE = "hibor_a_tier_backfill_tasks.csv"
HIBOR_A_TIER_REPORT = "hibor_a_tier_backfill_report.md"
HIBOR_A_TIER_DISCOVERED_FILE = "hibor_a_tier_discovered_reports.csv"
HIBOR_A_TIER_FILTERED_FILE = "hibor_a_tier_filtered_reports.csv"
HIBOR_A_TIER_DOWNLOADS_FILE = "hibor_a_tier_downloaded_reports.csv"
DEFAULT_HIBOR_INSTITUTIONS_CONFIG = Path("config/hibor_institutions.csv")
DEFAULT_HIBOR_A_TIER_CONFIG = Path("config/hibor_a_tier_institutions.csv")
DEFAULT_TOP_BROKERS = (
    "中信证券",
    "中金公司",
    "华泰证券",
    "国泰君安",
    "招商证券",
    "海通证券",
    "广发证券",
    "申万宏源",
    "中信建投",
    "兴业证券",
    "国信证券",
    "光大证券",
    "东吴证券",
)
AUTH_KEYS = ("abc", "def", "vidd", "keyy", "xyz", "op")
HIBOR_CACHE_ROOT = Path("~/Library/Caches/com.shhy.macHB").expanduser()


class HiborRateLimitError(RuntimeError):
    pass


def load_hibor_a_tier_institutions(path: str | Path = DEFAULT_HIBOR_A_TIER_CONFIG) -> list[dict[str, str]]:
    frame = pd.read_csv(path, dtype=str).fillna("")
    return frame.to_dict("records")


def normalize_hibor_broker(value: str, rules: list[dict[str, str]]) -> dict[str, str] | None:
    text = _normalize_match_text(value)
    if not text:
        return None
    sorted_rules = sorted(rules, key=lambda item: len(_normalize_match_text(item.get("alias", ""))), reverse=True)
    for rule in sorted_rules:
        alias = _normalize_match_text(rule.get("alias", ""))
        if alias and alias in text:
            return dict(rule)
    return None


def parse_hibor_pdf_filename(path: str | Path) -> dict[str, str]:
    pdf_path = Path(path)
    stem = pdf_path.stem
    parts = stem.split("-", 4)
    if len(parts) >= 5 and len(parts[0]) == 8 and parts[0].isdigit():
        date_raw, broker, stock_name, symbol, title = parts
    else:
        parts = stem.split("-", 4)
        if len(parts) != 5:
            raise ValueError(f"Unsupported Hibor PDF filename: {pdf_path.name}")
        broker, stock_name, symbol, title, date_short = parts
        if len(date_short) != 6 or not date_short.isdigit():
            raise ValueError(f"Unsupported Hibor PDF filename: {pdf_path.name}")
        date_raw = f"20{date_short}"
    if not symbol.isdigit() or len(symbol) != 6:
        raise ValueError(f"Unsupported Hibor stock symbol in filename: {pdf_path.name}")
    exchange = _exchange_from_symbol(symbol)
    publish_date = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
    return {
        "publish_date": publish_date,
        "broker": broker.strip(),
        "stock_name": stock_name.strip(),
        "symbol": symbol,
        "exchange": exchange,
        "ts_code": f"{symbol}.{exchange}",
        "asset_id": f"CN:{exchange}:{symbol}",
        "report_title": title.strip(),
    }


def build_hibor_download_queue(
    candidates: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    output_dir: str | Path | None = None,
    brokers: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    broker_names = list(brokers or DEFAULT_TOP_BROKERS)
    rows = []
    for candidate in candidates.fillna("").to_dict("records"):
        ts_code = str(candidate.get("ts_code") or "")
        symbol = ts_code.split(".")[0] if "." in ts_code else ts_code
        stock_name = str(candidate.get("stock_name") or "")
        if not symbol or not stock_name:
            continue
        for broker in broker_names:
            rows.append(
                {
                    "task_id": f"hibor_{symbol}_{_stable_token([broker, start_date, end_date])}",
                    "ts_code": ts_code,
                    "symbol": symbol,
                    "stock_name": stock_name,
                    "broker": broker,
                    "start_date": start_date,
                    "end_date": end_date,
                    "query": f"{symbol} {stock_name} {broker} 研报",
                    "status": "pending",
                    "downloaded_pdf_path": "",
                    "notes": "",
                }
            )
    queue = pd.DataFrame(rows)
    report = _render_queue_report(queue, start_date=start_date, end_date=end_date)
    result: dict[str, Any] = {"queue": queue, "report": report, "paths": {}}
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "queue": output / HIBOR_QUEUE_FILE,
            "report": output / HIBOR_QUEUE_REPORT,
        }
        queue.to_csv(paths["queue"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def build_hibor_a_tier_backfill_plan(
    assets: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    frame = assets.copy()
    for column in ["asset_id", "ts_code", "stock_name", "symbol"]:
        if column not in frame.columns:
            frame[column] = ""
    rows = []
    for row in frame.fillna("").to_dict("records"):
        symbol = str(row.get("symbol") or "").strip() or str(row.get("ts_code") or "").split(".")[0]
        ts_code = str(row.get("ts_code") or "").strip() or (f"{symbol}.{_exchange_from_symbol(symbol)}" if symbol else "")
        if not symbol:
            continue
        rows.append(
            {
                "task_id": f"hibor_a_tier_{symbol}",
                "asset_id": str(row.get("asset_id") or "").strip(),
                "ts_code": ts_code,
                "symbol": symbol,
                "stock_name": str(row.get("stock_name") or "").strip(),
                "start_date": start_date,
                "end_date": end_date,
                "status": "pending",
                "discovered_count": 0,
                "downloaded_count": 0,
                "error_type": "",
                "error_message": "",
                "started_at": "",
                "finished_at": "",
            }
        )
    tasks = pd.DataFrame(rows)
    report = _render_a_tier_plan_report(tasks, start_date=start_date, end_date=end_date)
    result: dict[str, Any] = {"tasks": tasks, "report": report, "paths": {}}
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {"tasks": output / HIBOR_A_TIER_TASKS_FILE, "report": output / HIBOR_A_TIER_REPORT}
        tasks.to_csv(paths["tasks"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def filter_hibor_a_tier_reports(
    discovered: pd.DataFrame,
    rules: list[dict[str, str]],
    *,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    if discovered.empty:
        return pd.DataFrame(columns=list(discovered.columns) + ["broker", "broker_tier", "broker_group", "broker_region", "report_date"])
    rows = []
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    for row in discovered.fillna("").to_dict("records"):
        title = str(row.get("title") or "")
        rule = normalize_hibor_broker(title, rules)
        report_date = _hibor_report_date_from_title(title)
        if not rule or not report_date:
            continue
        report_ts = pd.Timestamp(report_date)
        if report_ts < start or report_ts > end:
            continue
        enriched = dict(row)
        enriched.update(
            {
                "broker": rule.get("institution_name", ""),
                "broker_alias": rule.get("alias", ""),
                "broker_tier": rule.get("tier", ""),
                "broker_group": rule.get("group", ""),
                "broker_region": rule.get("region", ""),
                "report_date": report_date,
                "dedupe_key": _stable_token(
                    [
                        str(row.get("ts_code") or ""),
                        str(row.get("detail_url") or ""),
                        title,
                        report_date,
                    ]
                ),
            }
        )
        rows.append(enriched)
    filtered = pd.DataFrame(rows)
    if filtered.empty:
        return filtered
    return filtered.drop_duplicates(subset=["dedupe_key"]).reset_index(drop=True)


def choose_hibor_reports_by_tier(filtered: pd.DataFrame, *, fallback_tier: str | None = "B") -> pd.DataFrame:
    if filtered.empty or "broker_tier" not in filtered.columns:
        return filtered.copy()
    frame = filtered.copy()
    tier_text = frame["broker_tier"].astype(str).str.upper()
    primary = frame[tier_text.eq("A")].copy()
    if not primary.empty:
        primary["selected_tier_reason"] = "primary_A"
        return primary.reset_index(drop=True)
    fallback = str(fallback_tier or "").upper()
    if fallback:
        selected = frame[tier_text.eq(fallback)].copy()
        if not selected.empty:
            selected["selected_tier_reason"] = f"fallback_{fallback}"
            return selected.reset_index(drop=True)
    return pd.DataFrame(columns=list(frame.columns) + (["selected_tier_reason"] if "selected_tier_reason" not in frame.columns else []))


def extract_hibor_auth_params_from_text(text: str) -> dict[str, str]:
    urls = re.findall(r"https?://[^\s\"'<>]+", text)
    for url in reversed(urls):
        parsed = urlparse(html.unescape(url))
        params = {key: values[-1] for key, values in parse_qs(parsed.query).items() if values}
        if all(key in params for key in AUTH_KEYS):
            return {key: params[key] for key in AUTH_KEYS}
    raise ValueError("Hibor auth params not found in cached text")


def load_hibor_auth_params_from_cache(cache_root: Path = HIBOR_CACHE_ROOT) -> dict[str, str]:
    chunks = []
    if cache_root.exists():
        for path in sorted(cache_root.rglob("*")):
            if path.is_file() and path.stat().st_size <= 2_000_000:
                chunks.append(path.read_bytes().decode("utf-8", errors="ignore"))
    return extract_hibor_auth_params_from_text("\n".join(chunks))


def parse_hibor_search_results(page_html: str) -> list[dict[str, str]]:
    rows = []
    row_blocks = re.findall(r"<tr[^>]*>(.*?)</tr>", page_html, flags=re.IGNORECASE | re.DOTALL)
    blocks = row_blocks if row_blocks else [page_html]
    for block in blocks:
        read_match = re.search(
            r'<a[^>]+href="(?P<href>[^"]*maibopdfsys\.asp[^"]*)"[^>]*>(?P<label>.*?)</a>',
            block,
            re.IGNORECASE | re.DOTALL,
        )
        if not read_match:
            continue
        title_match = re.search(
            r'<a[^>]+href="[^"]*doc_detail\.asp[^"]*"[^>]*>(?P<title>.*?)</a>',
            block,
            re.IGNORECASE | re.DOTALL,
        )
        raw_title = title_match.group("title") if title_match else read_match.group("label")
        title = re.sub(r"<[^>]+>", "", raw_title)
        title = html.unescape(title).strip()
        href = html.unescape(read_match.group("href")).strip()
        if title and href:
            rows.append({"detail_url": href, "title": title})
    return rows


def download_hibor_report_pdfs(
    candidates: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    download_dir: str | Path,
    auth_params: dict[str, str] | None = None,
    brokers: list[str] | tuple[str, ...] | None = None,
    max_reports_per_candidate: int = 1,
    text_fetcher: Any | None = None,
    binary_fetcher: Any | None = None,
) -> dict[str, Any]:
    params = auth_params or load_hibor_auth_params_from_cache()
    broker_names = list(brokers or DEFAULT_TOP_BROKERS)
    fetch_text = text_fetcher or _http_get_text
    fetch_binary = binary_fetcher or _http_get_binary
    download_path = Path(download_dir)
    download_path.mkdir(parents=True, exist_ok=True)
    rows = []
    for candidate in candidates.fillna("").to_dict("records"):
        ts_code = str(candidate.get("ts_code") or "")
        symbol = ts_code.split(".")[0] if "." in ts_code else ts_code
        stock_name = str(candidate.get("stock_name") or "")
        if not symbol:
            continue
        search_url = _hibor_search_url(symbol=symbol, auth_params=params)
        search_html = fetch_text(search_url)
        links = parse_hibor_search_results(search_html)
        matched_links = [
            link
            for link in links
            if symbol in link["title"]
            and (not stock_name or stock_name in link["title"])
            and any(broker in link["title"] for broker in broker_names)
        ][:max_reports_per_candidate]
        for link in matched_links:
            detail_html = fetch_text(link["detail_url"])
            download_url = _extract_hibor_download_url(detail_html)
            content = fetch_binary(download_url)
            if not content.startswith(b"%PDF"):
                rows.append(
                    {
                        "ts_code": ts_code,
                        "stock_name": stock_name,
                        "title": link["title"],
                        "detail_url": link["detail_url"],
                        "download_url": download_url,
                        "pdf_path": "",
                        "status": "not_pdf",
                    }
                )
                continue
            pdf_path = download_path / _hibor_pdf_filename_from_title(link["title"])
            pdf_path.write_bytes(content)
            rows.append(
                {
                    "ts_code": ts_code,
                    "stock_name": stock_name,
                    "title": link["title"],
                    "detail_url": link["detail_url"],
                    "download_url": download_url,
                    "pdf_path": str(pdf_path),
                    "status": "downloaded",
                }
            )
    downloads = pd.DataFrame(rows)
    manifest_path = download_path / HIBOR_DOWNLOADS_FILE
    downloads.to_csv(manifest_path, index=False)
    return {
        "downloads": downloads,
        "summary": {
            "downloaded_count": int(downloads["status"].eq("downloaded").sum()) if not downloads.empty else 0,
            "attempted_count": len(downloads),
        },
        "paths": {"downloads": str(manifest_path), "download_dir": str(download_path)},
    }


def run_hibor_a_tier_backfill(
    *,
    tasks_path: str | Path,
    output_dir: str | Path = "outputs/research/hibor_a_tier_backfill",
    config_path: str | Path = DEFAULT_HIBOR_INSTITUTIONS_CONFIG,
    download_dir: str | Path | None = None,
    auth_params: dict[str, str] | None = None,
    review_threshold: int = 50,
    max_tasks: int | None = None,
    max_detail_attempts: int | None = None,
    fallback_tier: str | None = "B",
    write_db: bool = False,
    service: str = SETTINGS.research_service,
    import_pdfs: bool = True,
    run_pdf_backfill: bool = True,
    feature_trade_date: str | None = None,
    text_fetcher: Any | None = None,
    binary_fetcher: Any | None = None,
    retry_attempts: int = 3,
    retry_sleep_seconds: float = 2.0,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    task_file = Path(tasks_path)
    tasks = pd.read_csv(task_file, dtype=object).fillna("")
    rules = load_hibor_a_tier_institutions(config_path)
    params = auth_params or load_hibor_auth_params_from_cache()
    base_fetch_text = text_fetcher or _http_get_text
    base_fetch_binary = binary_fetcher or _http_get_binary
    fetch_text = lambda url: _call_with_retries(base_fetch_text, url, attempts=retry_attempts, sleep_seconds=retry_sleep_seconds)
    fetch_binary = lambda url: _call_with_retries(base_fetch_binary, url, attempts=retry_attempts, sleep_seconds=retry_sleep_seconds)
    pdf_dir = Path(download_dir) if download_dir is not None else output / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    discovered_rows = _load_existing_manifest_rows(output / HIBOR_A_TIER_DISCOVERED_FILE)
    filtered_rows = _load_existing_manifest_rows(output / HIBOR_A_TIER_FILTERED_FILE)
    download_rows = _load_existing_manifest_rows(output / HIBOR_A_TIER_DOWNLOADS_FILE)
    processed = 0
    detail_attempts = 0
    stop_batch = False

    for idx, task in tasks.iterrows():
        if stop_batch:
            break
        status = str(task.get("status") or "")
        if status != "pending":
            continue
        if max_tasks is not None and processed >= max_tasks:
            break
        processed += 1
        started_at = _utc_now_iso()
        tasks.at[idx, "started_at"] = started_at
        symbol = str(task.get("symbol") or "").strip() or str(task.get("ts_code") or "").split(".")[0]
        try:
            search_html = fetch_text(_hibor_search_url(symbol=symbol, auth_params=params))
            _raise_if_hibor_rate_limited(search_html)
            discovered = pd.DataFrame(parse_hibor_search_results(search_html))
            if not discovered.empty:
                discovered["asset_id"] = str(task.get("asset_id") or "")
                discovered["ts_code"] = str(task.get("ts_code") or "")
                discovered["symbol"] = symbol
                discovered["stock_name"] = str(task.get("stock_name") or "")
                discovered_rows.extend(discovered.to_dict("records"))
            filtered = filter_hibor_a_tier_reports(
                discovered,
                rules,
                start_date=str(task.get("start_date") or ""),
                end_date=str(task.get("end_date") or ""),
            )
            selected = choose_hibor_reports_by_tier(filtered, fallback_tier=fallback_tier)
            filtered_count = len(selected)
            tasks.at[idx, "discovered_count"] = filtered_count
            if not filtered.empty:
                filtered_rows.extend(filtered.to_dict("records"))
            if filtered_count == 0:
                tasks.at[idx, "status"] = "no_qualified_report"
                tasks.at[idx, "downloaded_count"] = 0
                tasks.at[idx, "finished_at"] = _utc_now_iso()
                _persist_a_tier_artifacts(tasks, discovered_rows, filtered_rows, download_rows, output, task_file)
                continue
            if filtered_count > review_threshold:
                tasks.at[idx, "status"] = "needs_review"
                tasks.at[idx, "downloaded_count"] = 0
                tasks.at[idx, "error_type"] = "review_threshold"
                tasks.at[idx, "error_message"] = f"{filtered_count} A-tier reports retained; threshold={review_threshold}"
                tasks.at[idx, "finished_at"] = _utc_now_iso()
                _persist_a_tier_artifacts(tasks, discovered_rows, filtered_rows, download_rows, output, task_file)
                continue
            downloaded_count = 0
            for report in selected.to_dict("records"):
                if max_detail_attempts is not None and detail_attempts >= max_detail_attempts:
                    stop_batch = True
                    break
                detail_attempts += 1
                download_record = _download_one_hibor_report(report, pdf_dir=pdf_dir, fetch_text=fetch_text, fetch_binary=fetch_binary)
                download_rows.append(download_record)
                if download_record.get("status") == "rate_limited":
                    stop_batch = True
                    break
                if download_record.get("status") == "downloaded":
                    downloaded_count += 1
            tasks.at[idx, "downloaded_count"] = downloaded_count
            if stop_batch:
                if downloaded_count == filtered_count:
                    tasks.at[idx, "status"] = "done"
                elif max_detail_attempts is not None and detail_attempts >= max_detail_attempts:
                    tasks.at[idx, "status"] = "pending"
                    tasks.at[idx, "error_type"] = "detail_budget_exhausted"
                    tasks.at[idx, "error_message"] = f"detail_attempts={detail_attempts}; max_detail_attempts={max_detail_attempts}"
                else:
                    tasks.at[idx, "status"] = "rate_limited"
                    tasks.at[idx, "error_type"] = "HiborRateLimitError"
                    tasks.at[idx, "error_message"] = "Hibor daily browse/download limit reached"
            else:
                tasks.at[idx, "status"] = "done" if downloaded_count == filtered_count else "download_error"
            if downloaded_count != filtered_count and not stop_batch:
                tasks.at[idx, "error_type"] = "download_error"
                tasks.at[idx, "error_message"] = f"downloaded={downloaded_count}; expected={filtered_count}"
            tasks.at[idx, "finished_at"] = _utc_now_iso()
            _persist_a_tier_artifacts(tasks, discovered_rows, filtered_rows, download_rows, output, task_file)
        except HiborRateLimitError as exc:
            tasks.at[idx, "status"] = "rate_limited"
            tasks.at[idx, "error_type"] = type(exc).__name__
            tasks.at[idx, "error_message"] = str(exc)[:500]
            tasks.at[idx, "finished_at"] = _utc_now_iso()
            _persist_a_tier_artifacts(tasks, discovered_rows, filtered_rows, download_rows, output, task_file)
            stop_batch = True
        except Exception as exc:
            tasks.at[idx, "status"] = "search_error"
            tasks.at[idx, "error_type"] = type(exc).__name__
            tasks.at[idx, "error_message"] = str(exc)[:500]
            tasks.at[idx, "finished_at"] = _utc_now_iso()
            _persist_a_tier_artifacts(tasks, discovered_rows, filtered_rows, download_rows, output, task_file)

    paths = _persist_a_tier_artifacts(tasks, discovered_rows, filtered_rows, download_rows, output, task_file)
    import_result = None
    if import_pdfs:
        import_result = import_hibor_report_pdfs(
            input_dir=pdf_dir,
            output_dir=output / "import",
            write_db=write_db,
            service=service,
            run_pdf_backfill=run_pdf_backfill,
            feature_trade_date=feature_trade_date,
        )
        paths["import_report"] = import_result["paths"]["report"]
    return {
        "tasks": tasks,
        "discovered": pd.DataFrame(discovered_rows),
        "filtered": pd.DataFrame(filtered_rows),
        "downloads": pd.DataFrame(download_rows),
        "import": import_result,
        "summary": {
            "processed_tasks": processed,
            "detail_attempts": detail_attempts,
            "done_tasks": int(tasks["status"].eq("done").sum()) if "status" in tasks else 0,
            "needs_review_tasks": int(tasks["status"].eq("needs_review").sum()) if "status" in tasks else 0,
            "downloaded_count": sum(1 for row in download_rows if row.get("status") == "downloaded"),
        },
        "paths": paths,
    }


def build_hibor_sources_events_from_pdfs(pdf_paths: list[str | Path] | tuple[str | Path, ...]) -> dict[str, pd.DataFrame]:
    source_rows = []
    event_rows = []
    for path_value in pdf_paths:
        pdf_path = Path(path_value).expanduser().resolve()
        try:
            meta = parse_hibor_pdf_filename(pdf_path)
        except ValueError:
            continue
        source_url = pdf_path.as_uri()
        report_id = f"hibor_{_stable_token([source_url])}"
        metadata = {
            "hibor": {
                "local_pdf_path": str(pdf_path),
                "filename": pdf_path.name,
                "import_source": HIBOR_SOURCE_TYPE,
            }
        }
        source_rows.append(
            {
                "report_id": report_id,
                "source_type": HIBOR_SOURCE_TYPE,
                "source_name": HIBOR_SOURCE_NAME,
                "broker": meta["broker"],
                "analyst": "",
                "report_title": meta["report_title"],
                "publish_date": meta["publish_date"],
                "source_url": source_url,
                "public_access": False,
                "copyright_note": "Downloaded from Hibor terminal for internal research use only.",
                "source_confidence": 0.9,
                "raw_summary": "",
                "metadata": json.dumps(metadata, ensure_ascii=False),
            }
        )
        event_rows.append(
            {
                "report_id": report_id,
                "asset_id": meta["asset_id"],
                "ts_code": meta["ts_code"],
                "stock_name": meta["stock_name"],
                "industry_name": "",
                "report_date": meta["publish_date"],
                "rating": "",
                "rating_change": "",
                "target_price": pd.NA,
                "target_upside": pd.NA,
                "industry_view": "",
                "company_view": "",
                "risk_summary": "",
                "effective_start_date": meta["publish_date"],
                "effective_end_date": pd.NA,
                "auto_trade_enabled": False,
                "metadata": json.dumps(metadata, ensure_ascii=False),
            }
        )
    return {
        "sources": pd.DataFrame(source_rows, dtype=object),
        "events": pd.DataFrame(event_rows, dtype=object),
    }


def import_hibor_report_pdfs(
    *,
    input_dir: str | Path,
    output_dir: str | Path = "outputs/research/hibor_report_import",
    write_db: bool = False,
    service: str = SETTINGS.research_service,
    run_pdf_backfill: bool = True,
    feature_trade_date: str | None = None,
) -> dict[str, Any]:
    input_path = Path(input_dir).expanduser()
    pdf_paths = sorted(input_path.glob("*.pdf"))
    built = build_hibor_sources_events_from_pdfs(pdf_paths)
    sources = built["sources"]
    events = built["events"]
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    source_path = output / HIBOR_SOURCE_FILE
    event_path = output / HIBOR_EVENT_FILE
    report_path = output / HIBOR_IMPORT_REPORT
    sources.to_csv(source_path, index=False)
    events.to_csv(event_path, index=False)
    db_result = None
    if write_db:
        db_result = upsert_stock_report_sources_events(sources=sources, events=events, service=service)

    pdf_result = None
    feature_events = events
    if run_pdf_backfill:
        pdf_result = build_stock_report_pdf_field_backfill(sources=sources, output_dir=output, resume=True)
        feature_events = _merge_pdf_fields_into_events(events, pdf_result.get("fields", pd.DataFrame()))
        if write_db:
            pdf_result["db"] = upsert_stock_report_pdf_fields(pdf_result["fields"], service=service)

    feature_result = None
    if feature_trade_date:
        feature_result = build_stock_report_features_from_events(feature_events, trade_date=feature_trade_date, output_dir=output)
        if write_db:
            feature_result["db"] = upsert_stock_report_features(features=feature_result["features"], service=service)

    summary = {
        "scanned_pdf_count": len(pdf_paths),
        "pdf_count": len(sources),
        "source_rows": len(sources),
        "event_rows": len(events),
        "write_db": write_db,
    }
    report = _render_import_report(summary, sources)
    report_path.write_text(report, encoding="utf-8")
    paths = {
        "sources": str(source_path),
        "events": str(event_path),
        "report": str(report_path),
    }
    if pdf_result and pdf_result.get("paths", {}).get("fields"):
        paths["fields"] = pdf_result["paths"]["fields"]
    if feature_result and feature_result.get("paths", {}).get("features"):
        paths["features"] = feature_result["paths"]["features"]
    return {
        "summary": summary,
        "sources": sources,
        "events": events,
        "pdf": pdf_result,
        "features": feature_result["features"] if feature_result else pd.DataFrame(),
        "db": db_result,
        "paths": paths,
    }


def watch_hibor_downloads(
    *,
    input_dir: str | Path,
    output_dir: str | Path = "outputs/research/hibor_report_import",
    poll_seconds: float = 5.0,
    max_cycles: int | None = None,
    write_db: bool = False,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    cycles = 0
    last_result: dict[str, Any] | None = None
    while True:
        last_result = import_hibor_report_pdfs(
            input_dir=input_dir,
            output_dir=output_dir,
            write_db=write_db,
            service=service,
            feature_trade_date=None,
        )
        cycles += 1
        if max_cycles is not None and cycles >= max_cycles:
            break
        time.sleep(poll_seconds)
    assert last_result is not None
    last_result["summary"]["watch_cycles"] = cycles
    return last_result


def _exchange_from_symbol(symbol: str) -> str:
    if symbol.startswith(("600", "601", "603", "605", "688", "689")):
        return "SH"
    if symbol.startswith(("000", "001", "002", "003", "300", "301", "302")):
        return "SZ"
    if symbol.startswith(("43", "83", "87", "92")):
        return "BJ"
    return "SH"


def _normalize_match_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _hibor_report_date_from_title(title: str) -> str:
    match = re.search(r"(?:-|_)(?P<date>\d{6})(?:\.pdf)?$", str(title or "").strip(), re.IGNORECASE)
    if not match:
        return ""
    raw = match.group("date")
    date_text = f"20{raw[:2]}-{raw[2:4]}-{raw[4:6]}"
    try:
        pd.Timestamp(date_text)
    except Exception:
        return ""
    return date_text


def _utc_now_iso() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


def _download_one_hibor_report(
    report: dict[str, Any],
    *,
    pdf_dir: Path,
    fetch_text: Any,
    fetch_binary: Any,
) -> dict[str, Any]:
    title = str(report.get("title") or "")
    detail_url = str(report.get("detail_url") or "")
    record = dict(report)
    record.update({"download_url": "", "pdf_path": "", "status": "pending", "error_type": "", "error_message": ""})
    try:
        detail_html = fetch_text(detail_url)
        _raise_if_hibor_rate_limited(detail_html)
        download_url = _extract_hibor_download_url(detail_html)
        content = fetch_binary(download_url)
        record["download_url"] = download_url
        if not content.startswith(b"%PDF"):
            record["status"] = "not_pdf"
            return record
        pdf_path = pdf_dir / _hibor_pdf_filename_from_title(title)
        pdf_path.write_bytes(content)
        record["pdf_path"] = str(pdf_path)
        record["status"] = "downloaded"
        return record
    except HiborRateLimitError as exc:
        record["status"] = "rate_limited"
        record["error_type"] = type(exc).__name__
        record["error_message"] = str(exc)[:500]
        return record
    except Exception as exc:
        record["status"] = "download_error"
        record["error_type"] = type(exc).__name__
        record["error_message"] = str(exc)[:500]
        return record


def _raise_if_hibor_rate_limited(page_text: str) -> None:
    text = html.unescape(str(page_text or ""))
    if "今日的浏览上限" in text or "/delete/limit.html" in text or "limit.gif" in text:
        raise HiborRateLimitError("Hibor daily browse/download limit reached")


def _call_with_retries(func: Any, arg: str, *, attempts: int, sleep_seconds: float) -> Any:
    last_exc: Exception | None = None
    tries = max(1, attempts)
    for attempt in range(tries):
        try:
            return func(arg)
        except Exception as exc:
            last_exc = exc
            if attempt + 1 >= tries:
                break
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
    assert last_exc is not None
    raise last_exc


def _load_existing_manifest_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        frame = pd.read_csv(path, dtype=object).fillna("")
    except pd.errors.EmptyDataError:
        return []
    return frame.to_dict("records")


def _persist_a_tier_artifacts(
    tasks: pd.DataFrame,
    discovered_rows: list[dict[str, Any]],
    filtered_rows: list[dict[str, Any]],
    download_rows: list[dict[str, Any]],
    output: Path,
    task_file: Path,
) -> dict[str, str]:
    paths = {
        "tasks": task_file,
        "discovered": output / HIBOR_A_TIER_DISCOVERED_FILE,
        "filtered": output / HIBOR_A_TIER_FILTERED_FILE,
        "downloads": output / HIBOR_A_TIER_DOWNLOADS_FILE,
        "report": output / HIBOR_A_TIER_REPORT,
    }
    tasks.to_csv(paths["tasks"], index=False)
    _manifest_frame(discovered_rows).to_csv(paths["discovered"], index=False)
    _manifest_frame(filtered_rows).to_csv(paths["filtered"], index=False)
    _manifest_frame(download_rows).to_csv(paths["downloads"], index=False)
    paths["report"].write_text(_render_a_tier_run_report(tasks, download_rows), encoding="utf-8")
    return {key: str(value) for key, value in paths.items()}


def _manifest_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    subset = [column for column in ["dedupe_key", "detail_url", "pdf_path"] if column in frame.columns]
    if subset:
        frame = frame.drop_duplicates(subset=subset, keep="last")
    return frame


def _merge_pdf_fields_into_events(events: pd.DataFrame, fields: pd.DataFrame) -> pd.DataFrame:
    if events.empty or fields.empty:
        return events
    result = events.copy()
    fields_records = fields.fillna("").to_dict("records")
    by_report = {str(row.get("report_id") or ""): row for row in fields_records if str(row.get("report_id") or "")}
    for idx, event in result.iterrows():
        report_id = str(event.get("report_id") or "")
        field = by_report.get(report_id)
        if field is None and len(fields_records) == len(result):
            field = fields_records[idx]
        if not field or str(field.get("status") or "") not in {"parsed", "empty_text"}:
            continue
        if field.get("rating_pdf"):
            result.at[idx, "rating"] = field.get("rating_pdf")
        if field.get("rating_change_type"):
            result.at[idx, "rating_change"] = field.get("rating_change_type")
        if field.get("target_price") not in {"", None}:
            result.at[idx, "target_price"] = field.get("target_price")
        if field.get("risk_summary"):
            result.at[idx, "risk_summary"] = field.get("risk_summary")
        metadata = _json_dict(event.get("metadata"))
        metadata["pdf_extract"] = {
            "status": field.get("status"),
            "pdf_extract_version": field.get("pdf_extract_version") or "",
            "pdf_text_extract_chars": field.get("pdf_text_extract_chars") or 0,
            "target_price_confidence": field.get("target_price_confidence") or "",
            "target_price_extract_method": field.get("target_price_extract_method") or "",
            "rating_pdf": field.get("rating_pdf") or "",
            "forecast_eps_values": field.get("forecast_eps_values") or [],
            "forecast_pe_values": field.get("forecast_pe_values") or [],
            "has_profit_forecast": field.get("has_profit_forecast") or False,
            "has_risk_section": field.get("has_risk_section") or False,
            "risk_summary": field.get("risk_summary") or "",
            "analyst_pdf": field.get("analyst_pdf") or "",
        }
        result.at[idx, "metadata"] = json.dumps(metadata, ensure_ascii=False)
    return result


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _hibor_search_url(*, symbol: str, auth_params: dict[str, str]) -> str:
    query = {
        "tabindex": "2",
        "f": "3",
        "lm": "1",
        "ssfw": "0",
        "sjfw": "12",
        "dtype": "1",
        "page": "1",
        "gjz": symbol,
        **auth_params,
    }
    return "http://sys.hibor.com.cn/gaojisousuo/gaojisousuo/search?" + urlencode(query)


def _extract_hibor_download_url(detail_html: str) -> str:
    match = re.search(r'href="(?P<href>[^"]*downloadType=d[^"]*linkType=(?:pdf|d)[^"]*)"', detail_html, re.IGNORECASE)
    if not match:
        raise ValueError("Hibor download link not found in detail page")
    return urljoin("http://sys.hibor.com.cn", html.unescape(match.group("href")))


def _hibor_pdf_filename_from_title(title: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]", "_", title).strip()
    return f"{cleaned}.pdf" if not cleaned.endswith(".pdf") else cleaned


def _http_get_text(url: str) -> str:
    response = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    response.encoding = response.encoding or "utf-8"
    return response.text


def _http_get_binary(url: str) -> bytes:
    response = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
    response.raise_for_status()
    return response.content


def _stable_token(parts: list[str] | tuple[str, ...]) -> str:
    text = "|".join(str(part) for part in parts)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def _render_queue_report(queue: pd.DataFrame, *, start_date: str, end_date: str) -> str:
    return "\n".join(
        [
            "# Hibor Download Queue",
            "",
            f"- Window: {start_date} to {end_date}",
            f"- Tasks: {len(queue)}",
            f"- Brokers: {', '.join(sorted(queue['broker'].unique())) if not queue.empty else ''}",
            "",
            "Keep Hibor logged in, download matching PDFs, then run `import-hibor-report-pdfs` or `watch-hibor-downloads`.",
        ]
    )


def _render_a_tier_plan_report(tasks: pd.DataFrame, *, start_date: str, end_date: str) -> str:
    return "\n".join(
        [
            "# Hibor A-Tier Backfill Plan",
            "",
            f"- Window: {start_date} to {end_date}",
            f"- Tasks: {len(tasks)}",
            "- Scope: A-tier domestic and foreign/HK/international sell-side institutions",
        ]
    ) + "\n"


def _render_a_tier_run_report(tasks: pd.DataFrame, download_rows: list[dict[str, Any]]) -> str:
    status_counts = tasks["status"].value_counts().to_dict() if "status" in tasks else {}
    lines = [
        "# Hibor A-Tier Backfill Run",
        "",
        f"- Tasks: {len(tasks)}",
        f"- Downloaded PDFs: {sum(1 for row in download_rows if row.get('status') == 'downloaded')}",
        "",
        "## Status",
    ]
    for status, count in sorted(status_counts.items()):
        lines.append(f"- {status}: {count}")
    return "\n".join(lines) + "\n"


def _render_import_report(summary: dict[str, Any], sources: pd.DataFrame) -> str:
    lines = [
        "# Hibor Report Import",
        "",
        f"- Scanned PDFs: {summary['scanned_pdf_count']}",
        f"- PDFs: {summary['pdf_count']}",
        f"- Source rows: {summary['source_rows']}",
        f"- Event rows: {summary['event_rows']}",
        f"- Write DB: {summary['write_db']}",
    ]
    if not sources.empty:
        lines.extend(["", "## Imported Reports"])
        for row in sources.head(20).to_dict("records"):
            lines.append(f"- {row['publish_date']} {row['broker']} {row['report_title']}")
    return "\n".join(lines) + "\n"
