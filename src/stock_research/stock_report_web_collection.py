from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many, fetch_all

try:
    import akshare as ak
except Exception:  # pragma: no cover - optional adapter dependency
    ak = None


SEARCH_PLAN_FILE = "stock_report_search_plan.csv"
SEARCH_PLAN_REPORT = "stock_report_search_plan_report.md"
COLLECTION_FILE = "stock_report_web_source_collection.csv"
COLLECTION_REPORT = "stock_report_web_source_collection_report.md"
SOURCE_FILE = "stock_report_source_candidates.csv"
EVENT_FILE = "stock_report_event_candidates.csv"
FEATURE_FILE = "stock_report_feature_daily.csv"
FEATURE_REPORT = "stock_report_feature_daily_report.md"

POSITIVE_RATINGS = {"买入", "增持", "强烈推荐", "推荐", "outperform", "buy", "overweight"}
TOP_BROKER_KEYWORDS = {"中信证券", "中金公司", "华泰证券", "国泰君安", "招商证券", "海通证券", "广发证券"}
DEFAULT_STOCK_NAME_LOOKUP_PATHS = (
    "outputs/research/mid_trend_research_packet_20260602/mid_trend_research_packet_candidates.csv",
    "outputs/research/mid_trend_refresh_20260602/mid_trend_watch_funnel_detail.csv",
    "outputs/research/dragon_case_curated_library_2024_2026.csv",
    "outputs/research/dragon_case_factor_snapshot_2024_2026.csv",
    "outputs/research/lhb_event_features_daily_sample.csv",
)
SEARCH_ENGINE_HOSTS = {"www.baidu.com", "baidu.com", "cn.bing.com", "www.bing.com", "duckduckgo.com"}
TARGET_PRICE_RE = re.compile(r"(?:目标价|目标价格|target price)[：: ]*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
SOURCE_DIRECTED_SEARCH_SITES_BY_DOMAIN = {
    "eastmoney": ("pdf.dfcfw.com", "data.eastmoney.com/report"),
    "sina": ("stock.finance.sina.com.cn",),
    "ths": ("10jqka.com.cn",),
    "general": ("pdf.dfcfw.com", "data.eastmoney.com/report", "stock.finance.sina.com.cn", "10jqka.com.cn"),
}


def run_stock_report_search_plan(
    *,
    research_packet_path: str | Path,
    trade_date: str | None = None,
    output_dir: str | Path = "outputs/research",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    candidates = pd.read_csv(research_packet_path, low_memory=False)
    candidates = enrich_candidate_stock_names(candidates, service=service)
    return build_stock_report_search_plan_from_candidates(
        candidates,
        trade_date=trade_date,
        output_dir=output_dir,
        input_path=str(research_packet_path),
    )


def enrich_candidate_stock_names(
    candidates: pd.DataFrame,
    *,
    lookup_paths: list[str | Path] | tuple[str | Path, ...] | None = None,
    service: str = SETTINGS.research_service,
    db_lookup: bool = True,
) -> pd.DataFrame:
    if candidates.empty:
        return candidates
    result = candidates.copy()
    for column in ["asset_id", "ts_code", "stock_name"]:
        if column not in result.columns:
            result[column] = ""
    ts_codes = _ts_codes_from_candidates(result)
    lookup = _load_stock_name_lookup_from_paths(lookup_paths or DEFAULT_STOCK_NAME_LOOKUP_PATHS, ts_codes)
    if db_lookup:
        lookup.update({key: value for key, value in _load_stock_name_lookup_from_db(result, service=service).items() if key not in lookup})
    result["ts_code"] = result.apply(
        lambda row: row["ts_code"] if _has_text(row.get("ts_code")) else _ts_code_from_asset_id(row.get("asset_id")),
        axis=1,
    )
    result["stock_name"] = result.apply(
        lambda row: _resolve_stock_name(
            current_name=row.get("stock_name"),
            asset_id=row.get("asset_id"),
            ts_code=row.get("ts_code"),
            lookup=lookup,
        ),
        axis=1,
    )
    return result


def _load_stock_name_lookup_from_db(candidates: pd.DataFrame, *, service: str) -> dict[str, str]:
    asset_ids = sorted({str(value) for value in candidates.get("asset_id", pd.Series(dtype=object)).dropna().unique() if _has_text(value)})
    ts_codes = _ts_codes_from_candidates(candidates)
    symbols = sorted({code.split(".")[0] for code in ts_codes if "." in code})
    if not asset_ids and not symbols and not ts_codes:
        return {}
    rows: list[dict[str, Any]] = []
    with connect(service) as conn:
        for offset in range(0, len(asset_ids), 500):
            chunk = asset_ids[offset : offset + 500]
            placeholders = ", ".join(["%s"] * len(chunk))
            rows.extend(
                fetch_all(
                    conn,
                    f"""
                    SELECT asset_id, ts_code, name
                    FROM core.asset_master
                    WHERE asset_id IN ({placeholders})
                    """,
                    chunk,
                )
            )
        for values, sql in _stock_name_db_queries(symbols=symbols, ts_codes=ts_codes):
            if not values:
                continue
            rows.extend(fetch_all(conn, sql, values))
    return _stock_name_lookup_from_rows(rows)


def _stock_name_db_queries(*, symbols: list[str], ts_codes: list[str]) -> list[tuple[list[str], str]]:
    queries: list[tuple[list[str], str]] = []
    if symbols:
        placeholders = ", ".join(["%s"] * len(symbols))
        queries.append(
            (
                symbols,
                f"""
                SELECT symbol, name, exchange, NULL::text AS asset_id, NULL::text AS ts_code
                FROM asset_master
                WHERE symbol IN ({placeholders})
                """,
            )
        )
        queries.append(
            (
                symbols,
                f"""
                SELECT symbol, name, exchange, asset_id, ts_code
                FROM core.asset_master
                WHERE symbol IN ({placeholders})
                """,
            )
        )
    if ts_codes:
        placeholders = ", ".join(["%s"] * len(ts_codes))
        queries.append(
            (
                ts_codes,
                f"""
                SELECT symbol, name, exchange, asset_id, ts_code
                FROM core.asset_master
                WHERE ts_code IN ({placeholders})
                """,
            )
        )
    return queries


def run_stock_report_web_source_collection(
    *,
    search_plan_path: str | Path,
    output_dir: str | Path = "outputs/research",
    dry_run: bool = True,
    adapter: str = "web_search",
    max_results_per_task: int = 3,
    workers: int = 1,
    progress_every: int = 50,
    progress_logger: Any | None = None,
    request_sleep_seconds: float = 0.0,
    stop_after_consecutive_fetch_errors: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    write_db: bool = False,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    plan = pd.read_csv(search_plan_path, low_memory=False)
    result = collect_stock_report_web_sources_from_plan(
        plan,
        dry_run=dry_run,
        adapter=adapter,
        max_results_per_task=max_results_per_task,
        workers=workers,
        progress_every=progress_every,
        progress_logger=progress_logger if progress_logger is not None else _stderr_progress_logger,
        request_sleep_seconds=request_sleep_seconds,
        stop_after_consecutive_fetch_errors=stop_after_consecutive_fetch_errors,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        input_path=str(search_plan_path),
    )
    if write_db:
        upsert_stock_report_sources_events(
            sources=result["sources"],
            events=result["events"],
            service=service,
        )
    return result


def run_stock_report_feature_build(
    *,
    events_path: str | Path,
    trade_date: str,
    output_dir: str | Path = "outputs/research",
    write_db: bool = False,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    events = pd.read_csv(events_path, low_memory=False)
    result = build_stock_report_features_from_events(events, trade_date=trade_date, output_dir=output_dir)
    if write_db:
        upsert_stock_report_features(features=result["features"], service=service)
    return result


def build_stock_report_search_plan_from_candidates(
    candidates: pd.DataFrame,
    *,
    trade_date: str | None = None,
    output_dir: str | Path | None = None,
    input_path: str = "",
) -> dict[str, Any]:
    frame = _normalize_candidates(candidates)
    if trade_date:
        frame = frame[frame["trade_date"].eq(pd.to_datetime(trade_date))].copy()
    search_plan = _build_search_plan(frame)
    report = _render_search_plan_report(search_plan, trade_date=trade_date, input_path=input_path)
    result: dict[str, Any] = {"search_plan": search_plan, "report": report, "paths": {}}
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "search_plan": output / SEARCH_PLAN_FILE,
            "report": output / SEARCH_PLAN_REPORT,
        }
        search_plan.to_csv(paths["search_plan"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def collect_stock_report_web_sources_from_plan(
    search_plan: pd.DataFrame,
    *,
    dry_run: bool = True,
    adapter: str = "web_search",
    fetcher: Any | None = None,
    max_results_per_task: int = 3,
    workers: int = 1,
    progress_every: int = 50,
    progress_logger: Any | None = None,
    request_sleep_seconds: float = 0.0,
    stop_after_consecutive_fetch_errors: int | None = None,
    sleeper: Any | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    output_dir: str | Path | None = None,
    input_path: str = "",
) -> dict[str, Any]:
    plan = search_plan.copy()
    collection = (
        _build_dry_run_collection(plan)
        if dry_run
        else (
            _build_akshare_em_collection(plan, max_results_per_task=max_results_per_task)
            if adapter == "akshare_em"
            else (
                _build_bing_site_search_collection(
                    plan,
                    fetcher=fetcher or _default_fetcher,
                    max_results_per_task=max_results_per_task,
                )
                if adapter == "bing_site_search"
                else (
                    _build_sina_report_page_collection(
                        plan,
                        fetcher=fetcher or _default_fetcher,
                        max_results_per_task=max_results_per_task,
                        workers=workers,
                        progress_every=progress_every,
                        progress_logger=progress_logger,
                        request_sleep_seconds=request_sleep_seconds,
                        stop_after_consecutive_fetch_errors=stop_after_consecutive_fetch_errors,
                        sleeper=sleeper,
                    )
                    if adapter == "sina_report_page"
                    else (
                        _build_sohu_jlp_rating_collection(
                            plan,
                            fetcher=fetcher or _default_fetcher,
                            max_results_per_task=max_results_per_task,
                            workers=workers,
                            progress_every=progress_every,
                            progress_logger=progress_logger,
                            request_sleep_seconds=request_sleep_seconds,
                            stop_after_consecutive_fetch_errors=stop_after_consecutive_fetch_errors,
                            sleeper=sleeper,
                        )
                        if adapter == "sohu_jlp_rating"
                        else (
                            _build_cfi_ybyl_collection(
                                plan,
                                fetcher=fetcher or _default_fetcher,
                                max_results_per_task=max_results_per_task,
                                workers=workers,
                                progress_every=progress_every,
                                progress_logger=progress_logger,
                                request_sleep_seconds=request_sleep_seconds,
                                stop_after_consecutive_fetch_errors=stop_after_consecutive_fetch_errors,
                                sleeper=sleeper,
                            )
                            if adapter == "cfi_ybyl"
                            else _build_live_collection(
                                plan,
                                fetcher=fetcher or _default_fetcher,
                                max_results_per_task=max_results_per_task,
                            )
                        )
                    )
                )
            )
        )
    )
    collection = _filter_collection_by_publish_date(collection, start_date=start_date, end_date=end_date)
    sources, events = build_stock_report_sources_events_from_collection(collection)
    report = _render_collection_report(collection, dry_run=dry_run, input_path=input_path)
    result: dict[str, Any] = {
        "collection": collection,
        "sources": sources,
        "events": events,
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "collection": output / COLLECTION_FILE,
            "sources": output / SOURCE_FILE,
            "events": output / EVENT_FILE,
            "report": output / COLLECTION_REPORT,
        }
        collection.to_csv(paths["collection"], index=False)
        sources.to_csv(paths["sources"], index=False)
        events.to_csv(paths["events"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _filter_collection_by_publish_date(
    collection: pd.DataFrame,
    *,
    start_date: str | None,
    end_date: str | None,
) -> pd.DataFrame:
    if collection.empty or (not start_date and not end_date) or "publish_date" not in collection.columns:
        return collection
    result = collection.copy()
    publish_dates = pd.to_datetime(result["publish_date"], errors="coerce")
    mask = pd.Series(True, index=result.index)
    if start_date:
        mask &= publish_dates.ge(pd.to_datetime(start_date))
    if end_date:
        mask &= publish_dates.le(pd.to_datetime(end_date))
    found_mask = result.get("collection_status", pd.Series("", index=result.index)).eq("found")
    return result[~found_mask | mask].reset_index(drop=True)


def build_stock_report_features_from_events(
    events: pd.DataFrame,
    *,
    trade_date: str,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    normalized = _normalize_events(events, trade_date=trade_date)
    features = _aggregate_features(normalized, trade_date=trade_date)
    report = _render_feature_report(features, trade_date=trade_date)
    result: dict[str, Any] = {"features": features, "report": report, "paths": {}}
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "features": output / FEATURE_FILE,
            "report": output / FEATURE_REPORT,
        }
        features.to_csv(paths["features"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _normalize_candidates(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "trade_date" not in result.columns:
        result["trade_date"] = pd.NaT
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce")
    for column in ["asset_id", "ts_code", "stock_name", "industry_name", "fundamental_hard_risk"]:
        if column not in result.columns:
            result[column] = ""
    for column in ["research_packet_rank", "mid_trend_funnel_score"]:
        if column not in result.columns:
            result[column] = np.nan
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result["ts_code"] = result.apply(
        lambda row: row["ts_code"] if _has_text(row.get("ts_code")) else _ts_code_from_asset_id(row.get("asset_id")),
        axis=1,
    )
    result["stock_name"] = result.apply(
        lambda row: row["stock_name"] if _has_text(row.get("stock_name")) else row.get("ts_code"),
        axis=1,
    )
    return result.sort_values(["trade_date", "research_packet_rank", "mid_trend_funnel_score"], ascending=[True, True, False])


def _build_search_plan(candidates: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "task_id",
        "trade_date",
        "asset_id",
        "ts_code",
        "stock_name",
        "industry_name",
        "candidate_rank",
        "query_type",
        "source_domain",
        "search_query",
        "search_url",
        "priority",
        "status",
        "auto_trade_enabled",
        "notes",
    ]
    if candidates.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    templates = [
        ("broker_report", "eastmoney", "{name} {code} 东方财富 研报 目标价 评级", "https://www.baidu.com/s?wd={query}", 10),
        ("broker_report", "sina", "{name} {code} 新浪财经 研报 评级", "https://www.baidu.com/s?wd={query}", 20),
        ("rating_target", "ths", "{name} {code} 同花顺 机构评级 目标价", "https://www.baidu.com/s?wd={query}", 30),
        ("rating_target", "general", "{name} {code} 券商研报 目标价 评级", "https://www.baidu.com/s?wd={query}", 40),
        ("industry_position", "general", "{name} {industry} 行业地位 市占率 龙头", "https://www.baidu.com/s?wd={query}", 50),
    ]
    for _, row in candidates.iterrows():
        trade_date = row["trade_date"].strftime("%Y-%m-%d") if pd.notna(row["trade_date"]) else ""
        rank = int(row["research_packet_rank"]) if pd.notna(row.get("research_packet_rank")) else 999
        name = _safe_text(row.get("stock_name"))
        code = _safe_text(row.get("ts_code"))
        industry = _safe_text(row.get("industry_name"))
        for query_type, domain, template, url_template, offset in templates:
            query = template.format(name=name, code=code, industry=industry).strip()
            rows.append(
                {
                    "task_id": f"{trade_date}_{code}_{domain}_{query_type}",
                    "trade_date": trade_date,
                    "asset_id": row.get("asset_id", ""),
                    "ts_code": code,
                    "stock_name": name,
                    "industry_name": industry,
                    "candidate_rank": rank,
                    "query_type": query_type,
                    "source_domain": domain,
                    "search_query": query,
                    "search_url": url_template.format(query=quote_plus(query)),
                    "priority": rank * 100 + offset,
                    "status": "pending",
                    "auto_trade_enabled": False,
                    "notes": "Public web search metadata only; do not store paid report full text.",
                }
            )
    return pd.DataFrame(rows, columns=columns)


def _build_dry_run_collection(plan: pd.DataFrame) -> pd.DataFrame:
    result = plan.copy()
    for column in [
        "result_rank",
        "source_url",
        "source_title",
        "source_name",
        "publish_date",
        "broker",
        "rating",
        "target_price",
        "target_upside",
        "snippet",
        "source_confidence",
    ]:
        result[column] = pd.NA
    result["collection_status"] = "dry_run_pending"
    result["collection_note"] = "Dry-run only: search_url prepared, no page fetched."
    return result


def _build_live_collection(
    plan: pd.DataFrame,
    *,
    fetcher: Any,
    max_results_per_task: int,
) -> pd.DataFrame:
    base_columns = list(_build_dry_run_collection(plan.head(0)).columns)
    if plan.empty:
        return pd.DataFrame(columns=base_columns)
    rows: list[dict[str, Any]] = []
    for task in plan.to_dict("records"):
        try:
            html = fetcher(str(task.get("search_url", "")))
            candidates = _extract_public_search_results(
                html,
                task=task,
                max_results=max_results_per_task,
            )
        except Exception as exc:
            failed = dict(task)
            failed.update(
                {
                    "result_rank": pd.NA,
                    "source_url": pd.NA,
                    "source_title": pd.NA,
                    "source_name": pd.NA,
                    "publish_date": pd.NA,
                    "broker": pd.NA,
                    "rating": pd.NA,
                    "target_price": pd.NA,
                    "target_upside": pd.NA,
                    "snippet": pd.NA,
                    "source_confidence": 0.0,
                    "collection_status": "fetch_error",
                    "collection_note": f"{type(exc).__name__}: {exc}",
                }
            )
            rows.append(failed)
            continue
        if not candidates:
            missing = dict(task)
            missing.update(
                {
                    "result_rank": pd.NA,
                    "source_url": pd.NA,
                    "source_title": pd.NA,
                    "source_name": pd.NA,
                    "publish_date": pd.NA,
                    "broker": pd.NA,
                    "rating": pd.NA,
                    "target_price": pd.NA,
                    "target_upside": pd.NA,
                    "snippet": pd.NA,
                    "source_confidence": 0.0,
                    "collection_status": "no_result",
                    "collection_note": "No usable public search result found.",
                }
            )
            rows.append(missing)
            continue
        rows.extend(candidates)
    return pd.DataFrame(rows).reindex(columns=base_columns)


def _build_bing_site_search_collection(
    plan: pd.DataFrame,
    *,
    fetcher: Any,
    max_results_per_task: int,
) -> pd.DataFrame:
    directed = _build_bing_site_search_plan(plan)
    return _build_live_collection(directed, fetcher=fetcher, max_results_per_task=max_results_per_task)


def _build_bing_site_search_plan(plan: pd.DataFrame) -> pd.DataFrame:
    if plan.empty:
        return plan.copy()
    rows: list[dict[str, Any]] = []
    for task in plan.to_dict("records"):
        source_domain = _safe_text(task.get("source_domain")) or "general"
        sites = SOURCE_DIRECTED_SEARCH_SITES_BY_DOMAIN.get(source_domain, SOURCE_DIRECTED_SEARCH_SITES_BY_DOMAIN["general"])
        for site in sites:
            query = f"site:{site} {_safe_text(task.get('search_query'))}".strip()
            row = dict(task)
            row["task_id"] = f"{task.get('task_id', '')}_bing_site_{site.replace('/', '_')}"
            row["search_query"] = query
            row["search_url"] = f"https://cn.bing.com/search?q={quote_plus(query)}"
            row["source_domain"] = f"bing_site:{site}"
            row["notes"] = "Bing site-directed public metadata search; do not store paid report full text."
            rows.append(row)
    return pd.DataFrame(rows).reindex(columns=plan.columns)


def _build_sina_report_page_collection(
    plan: pd.DataFrame,
    *,
    fetcher: Any,
    max_results_per_task: int,
    workers: int,
    progress_every: int,
    progress_logger: Any | None,
    request_sleep_seconds: float,
    stop_after_consecutive_fetch_errors: int | None,
    sleeper: Any | None,
) -> pd.DataFrame:
    return _build_direct_source_collection(
        plan,
        fetcher=fetcher,
        max_results_per_task=max_results_per_task,
        url_builder=_sina_report_url,
        parser=_extract_sina_report_page_rows,
        adapter="sina_report_page",
        workers=workers,
        progress_every=progress_every,
        progress_logger=progress_logger,
        request_sleep_seconds=request_sleep_seconds,
        stop_after_consecutive_fetch_errors=stop_after_consecutive_fetch_errors,
        sleeper=sleeper,
    )


def _build_sohu_jlp_rating_collection(
    plan: pd.DataFrame,
    *,
    fetcher: Any,
    max_results_per_task: int,
    workers: int,
    progress_every: int,
    progress_logger: Any | None,
    request_sleep_seconds: float,
    stop_after_consecutive_fetch_errors: int | None,
    sleeper: Any | None,
) -> pd.DataFrame:
    return _build_direct_source_collection(
        plan,
        fetcher=fetcher,
        max_results_per_task=max_results_per_task,
        url_builder=_sohu_jlp_rating_url,
        parser=_extract_sohu_jlp_rating_rows,
        adapter="sohu_jlp_rating",
        workers=workers,
        progress_every=progress_every,
        progress_logger=progress_logger,
        request_sleep_seconds=request_sleep_seconds,
        stop_after_consecutive_fetch_errors=stop_after_consecutive_fetch_errors,
        sleeper=sleeper,
    )


def _build_cfi_ybyl_collection(
    plan: pd.DataFrame,
    *,
    fetcher: Any,
    max_results_per_task: int,
    workers: int,
    progress_every: int,
    progress_logger: Any | None,
    request_sleep_seconds: float,
    stop_after_consecutive_fetch_errors: int | None,
    sleeper: Any | None,
) -> pd.DataFrame:
    return _build_direct_source_collection(
        plan,
        fetcher=fetcher,
        max_results_per_task=max_results_per_task,
        url_builder=_cfi_ybyl_url,
        parser=_extract_cfi_ybyl_rows,
        adapter="cfi_ybyl",
        workers=workers,
        progress_every=progress_every,
        progress_logger=progress_logger,
        request_sleep_seconds=request_sleep_seconds,
        stop_after_consecutive_fetch_errors=stop_after_consecutive_fetch_errors,
        sleeper=sleeper,
    )


def _build_direct_source_collection(
    plan: pd.DataFrame,
    *,
    fetcher: Any,
    max_results_per_task: int,
    url_builder: Any,
    parser: Any,
    adapter: str,
    workers: int,
    progress_every: int,
    progress_logger: Any | None,
    request_sleep_seconds: float,
    stop_after_consecutive_fetch_errors: int | None,
    sleeper: Any | None,
) -> pd.DataFrame:
    base_columns = list(_build_dry_run_collection(plan.head(0)).columns)
    tasks = _unique_stock_tasks(plan)
    if not tasks:
        return pd.DataFrame(columns=base_columns)

    started_at = time.monotonic()
    worker_count = max(1, int(workers or 1))
    progress_interval = max(1, int(progress_every or 1))
    sleep_seconds = max(0.0, float(request_sleep_seconds or 0.0))
    sleep_fn = sleeper or time.sleep
    stop_threshold = max(0, int(stop_after_consecutive_fetch_errors or 0))
    stats = {
        "completed": 0,
        "found_rows": 0,
        "found_stocks": 0,
        "no_result": 0,
        "fetch_error": 0,
    }
    found_stock_codes: set[str] = set()
    _emit_direct_source_progress(
        progress_logger,
        event="start",
        adapter=adapter,
        stats=stats,
        total=len(tasks),
        workers=worker_count,
        started_at=started_at,
    )

    indexed_rows: list[tuple[int, list[dict[str, Any]]]] = []
    if worker_count == 1:
        consecutive_fetch_errors = 0
        for idx, task in enumerate(tasks):
            task_rows = _collect_direct_source_task(
                task,
                fetcher=fetcher,
                max_results_per_task=max_results_per_task,
                url_builder=url_builder,
                parser=parser,
            )
            indexed_rows.append((idx, task_rows))
            _update_direct_source_progress_stats(stats, found_stock_codes, task_rows)
            if any(_safe_text(row.get("collection_status")) == "fetch_error" for row in task_rows):
                consecutive_fetch_errors += 1
            else:
                consecutive_fetch_errors = 0
            if stats["completed"] % progress_interval == 0 or stats["completed"] == len(tasks):
                _emit_direct_source_progress(
                    progress_logger,
                    event="progress",
                    adapter=adapter,
                    stats=stats,
                    total=len(tasks),
                    workers=worker_count,
                    started_at=started_at,
                )
            if stop_threshold and consecutive_fetch_errors >= stop_threshold:
                _emit_direct_source_progress(
                    progress_logger,
                    event="stopped",
                    adapter=adapter,
                    stats=stats,
                    total=len(tasks),
                    workers=worker_count,
                    started_at=started_at,
                )
                break
            if sleep_seconds and idx < len(tasks) - 1:
                sleep_fn(sleep_seconds)
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(
                    _collect_direct_source_task,
                    task,
                    fetcher=fetcher,
                    max_results_per_task=max_results_per_task,
                    url_builder=url_builder,
                    parser=parser,
                ): idx
                for idx, task in enumerate(tasks)
            }
            for future in as_completed(futures):
                idx = futures[future]
                task_rows = future.result()
                indexed_rows.append((idx, task_rows))
                _update_direct_source_progress_stats(stats, found_stock_codes, task_rows)
                if stats["completed"] % progress_interval == 0 or stats["completed"] == len(tasks):
                    _emit_direct_source_progress(
                        progress_logger,
                        event="progress",
                        adapter=adapter,
                        stats=stats,
                        total=len(tasks),
                        workers=worker_count,
                        started_at=started_at,
                    )

    rows: list[dict[str, Any]] = []
    for _, task_rows in sorted(indexed_rows, key=lambda item: item[0]):
        rows.extend(task_rows)
    _emit_direct_source_progress(
        progress_logger,
        event="done",
        adapter=adapter,
        stats=stats,
        total=len(tasks),
        workers=worker_count,
        started_at=started_at,
    )
    return pd.DataFrame(rows).reindex(columns=base_columns)


def _collect_direct_source_task(
    task: dict[str, Any],
    *,
    fetcher: Any,
    max_results_per_task: int,
    url_builder: Any,
    parser: Any,
) -> list[dict[str, Any]]:
    url = url_builder(_safe_text(task.get("ts_code")))
    if not url:
        missing = _direct_source_status_row(task, status="no_result", note="No source-page URL could be built.")
        return [missing]
    try:
        html = fetcher(url)
        parsed_rows = parser(html, task=task, page_url=url, max_results=max_results_per_task)
    except Exception as exc:
        failed = _direct_source_status_row(
            task,
            status="fetch_error",
            note=f"{type(exc).__name__}: {exc}",
            source_confidence=0.0,
        )
        return [failed]
    if parsed_rows:
        return parsed_rows
    missing = _direct_source_status_row(task, status="no_result", note="No usable source-page metadata found.")
    return [missing]


def _direct_source_status_row(
    task: dict[str, Any],
    *,
    status: str,
    note: str,
    source_confidence: float = 0.0,
) -> dict[str, Any]:
    row = dict(task)
    row.update(
        {
            "result_rank": pd.NA,
            "source_url": pd.NA,
            "source_title": pd.NA,
            "source_name": pd.NA,
            "publish_date": pd.NA,
            "broker": pd.NA,
            "rating": pd.NA,
            "target_price": pd.NA,
            "target_upside": pd.NA,
            "snippet": pd.NA,
            "source_confidence": source_confidence,
            "collection_status": status,
            "collection_note": note,
        }
    )
    return row


def _update_direct_source_progress_stats(
    stats: dict[str, int],
    found_stock_codes: set[str],
    task_rows: list[dict[str, Any]],
) -> None:
    stats["completed"] += 1
    statuses = [_safe_text(row.get("collection_status")) for row in task_rows]
    if "found" in statuses:
        stats["found_rows"] += sum(1 for status in statuses if status == "found")
        for row in task_rows:
            if _safe_text(row.get("collection_status")) == "found":
                found_stock_codes.add(_safe_text(row.get("ts_code")))
        stats["found_stocks"] = len(found_stock_codes)
    elif "fetch_error" in statuses:
        stats["fetch_error"] += 1
    else:
        stats["no_result"] += 1


def _emit_direct_source_progress(
    progress_logger: Any | None,
    *,
    event: str,
    adapter: str,
    stats: dict[str, int],
    total: int,
    workers: int,
    started_at: float,
) -> None:
    if progress_logger is None:
        return
    elapsed_seconds = max(0.0, time.monotonic() - started_at)
    completed = int(stats["completed"])
    rate = completed / elapsed_seconds if elapsed_seconds > 0 else 0.0
    line = (
        f"stock_report_web_sources|{event}|adapter={adapter}|completed={completed}|total={total}|"
        f"found_stocks={int(stats['found_stocks'])}|found_rows={int(stats['found_rows'])}|"
        f"no_result={int(stats['no_result'])}|fetch_error={int(stats['fetch_error'])}|"
        f"workers={workers}|elapsed_seconds={elapsed_seconds:.1f}|rate_per_second={rate:.2f}"
    )
    progress_logger(line)


def _stderr_progress_logger(line: str) -> None:
    print(line, file=sys.stderr, flush=True)


def _unique_stock_tasks(plan: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for task in plan.to_dict("records"):
        ts_code = _safe_text(task.get("ts_code"))
        if not ts_code or ts_code in seen:
            continue
        seen.add(ts_code)
        rows.append(task)
    return rows


def _build_akshare_em_collection(plan: pd.DataFrame, *, max_results_per_task: int) -> pd.DataFrame:
    base_columns = list(_build_dry_run_collection(plan.head(0)).columns)
    if plan.empty:
        return pd.DataFrame(columns=base_columns)
    if ak is None:
        result = _build_dry_run_collection(plan)
        result["collection_status"] = "fetch_error"
        result["collection_note"] = "akshare is not available for akshare_em adapter."
        return result

    eligible = plan[
        plan["query_type"].eq("broker_report")
        & plan["source_domain"].eq("eastmoney")
        & plan["ts_code"].map(_has_text)
    ].copy()
    rows: list[dict[str, Any]] = []
    for task in eligible.to_dict("records"):
        symbol = _safe_text(task.get("ts_code")).split(".")[0]
        try:
            reports = ak.stock_research_report_em(symbol=symbol)
        except Exception as exc:
            failed = dict(task)
            failed.update(
                {
                    "result_rank": pd.NA,
                    "source_url": pd.NA,
                    "source_title": pd.NA,
                    "source_name": "eastmoney_research_report_em",
                    "publish_date": pd.NA,
                    "broker": pd.NA,
                    "rating": pd.NA,
                    "target_price": pd.NA,
                    "target_upside": pd.NA,
                    "snippet": pd.NA,
                    "source_confidence": 0.0,
                    "collection_status": "fetch_error",
                    "collection_note": f"{type(exc).__name__}: {exc}",
                }
            )
            rows.append(failed)
            continue
        normalized = _normalize_akshare_report_rows(reports, task=task).head(max_results_per_task)
        if normalized.empty:
            missing = dict(task)
            missing.update(
                {
                    "result_rank": pd.NA,
                    "source_url": pd.NA,
                    "source_title": pd.NA,
                    "source_name": "eastmoney_research_report_em",
                    "publish_date": pd.NA,
                    "broker": pd.NA,
                    "rating": pd.NA,
                    "target_price": pd.NA,
                    "target_upside": pd.NA,
                    "snippet": pd.NA,
                    "source_confidence": 0.0,
                    "collection_status": "no_result",
                    "collection_note": "No Eastmoney research-report metadata returned by AkShare.",
                }
            )
            rows.append(missing)
            continue
        rows.extend(normalized.to_dict("records"))
    return pd.DataFrame(rows).reindex(columns=base_columns)


def _normalize_akshare_report_rows(reports: pd.DataFrame, *, task: dict[str, Any]) -> pd.DataFrame:
    columns = list(_build_dry_run_collection(pd.DataFrame([task])).columns)
    if reports is None or reports.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for idx, report in enumerate(reports.to_dict("records"), start=1):
        source_url = _safe_text(report.get("报告PDF链接"))
        title = _safe_text(report.get("报告名称"))
        if not source_url or not title:
            continue
        row = dict(task)
        report_date = _safe_text(report.get("日期"))
        row.update(
            {
                "result_rank": idx,
                "source_url": source_url,
                "source_title": title,
                "source_name": "eastmoney_research_report_em",
                "publish_date": report_date or pd.NA,
                "broker": _safe_text(report.get("机构")),
                "rating": _safe_text(report.get("东财评级")),
                "target_price": pd.NA,
                "target_upside": pd.NA,
                "snippet": f"{_safe_text(report.get('股票简称'))} {_safe_text(report.get('行业'))} {title}".strip(),
                "source_confidence": 0.75,
                "collection_status": "found",
                "collection_note": "AkShare Eastmoney public research-report metadata; full text not fetched.",
                "auto_trade_enabled": False,
            }
        )
        if _has_text(report.get("股票简称")):
            row["stock_name"] = _safe_text(report.get("股票简称"))
        if _has_text(report.get("行业")):
            row["industry_name"] = _safe_text(report.get("行业"))
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def build_stock_report_sources_events_from_collection(collection: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    source_columns = [
        "report_id",
        "source_type",
        "source_name",
        "broker",
        "analyst",
        "report_title",
        "publish_date",
        "source_url",
        "public_access",
        "copyright_note",
        "source_confidence",
        "raw_summary",
        "metadata",
    ]
    event_columns = [
        "report_id",
        "asset_id",
        "ts_code",
        "stock_name",
        "industry_name",
        "report_date",
        "rating",
        "rating_change",
        "target_price",
        "target_upside",
        "industry_view",
        "company_view",
        "risk_summary",
        "effective_start_date",
        "effective_end_date",
        "auto_trade_enabled",
        "metadata",
    ]
    if collection.empty or "collection_status" not in collection.columns:
        return pd.DataFrame(columns=source_columns), pd.DataFrame(columns=event_columns)
    found = collection[collection["collection_status"].eq("found") & collection["source_url"].map(_has_text)].copy()
    if found.empty:
        return pd.DataFrame(columns=source_columns), pd.DataFrame(columns=event_columns)
    source_rows = []
    event_rows = []
    for row in found.to_dict("records"):
        report_id = _report_id_from_url(str(row.get("source_url", "")))
        report_date = _safe_text(row.get("publish_date"))
        source_rows.append(
            {
                "report_id": report_id,
                "source_type": "public_web_search_result",
                "source_name": _safe_text(row.get("source_name")),
                "broker": _safe_text(row.get("broker")),
                "analyst": "",
                "report_title": _safe_text(row.get("source_title")),
                "publish_date": report_date or pd.NA,
                "source_url": _safe_text(row.get("source_url")),
                "public_access": True,
                "copyright_note": "Search-result metadata only; paid report full text is not stored.",
                "source_confidence": row.get("source_confidence", 0.5),
                "raw_summary": _safe_text(row.get("snippet")),
                "metadata": "{}",
            }
        )
        event_rows.append(
            {
                "report_id": report_id,
                "asset_id": _safe_text(row.get("asset_id")),
                "ts_code": _safe_text(row.get("ts_code")),
                "stock_name": _safe_text(row.get("stock_name")),
                "industry_name": _safe_text(row.get("industry_name")),
                "report_date": report_date or pd.NA,
                "rating": _safe_text(row.get("rating")),
                "rating_change": "",
                "target_price": row.get("target_price", pd.NA),
                "target_upside": row.get("target_upside", pd.NA),
                "industry_view": "",
                "company_view": _safe_text(row.get("snippet")),
                "risk_summary": "",
                "effective_start_date": report_date or pd.NA,
                "effective_end_date": pd.NA,
                "auto_trade_enabled": False,
                "metadata": "{}",
            }
        )
    return pd.DataFrame(source_rows, columns=source_columns), pd.DataFrame(event_rows, columns=event_columns)


def upsert_stock_report_sources_events(
    *,
    sources: pd.DataFrame,
    events: pd.DataFrame,
    service: str = SETTINGS.research_service,
) -> dict[str, int]:
    source_rows = [
        (
            row["report_id"],
            row["source_type"],
            row["source_name"],
            row["broker"],
            row["analyst"],
            row["report_title"],
            _blank_to_none(row["publish_date"]),
            row["source_url"],
            bool(row["public_access"]),
            row["copyright_note"],
            _blank_to_none(row["source_confidence"]),
            row["raw_summary"],
            row["metadata"],
        )
        for row in sources.fillna("").to_dict("records")
    ]
    event_rows = [
        (
            row["report_id"],
            row["asset_id"],
            row["ts_code"],
            row["stock_name"],
            row["industry_name"],
            _blank_to_none(row["report_date"]),
            row["rating"],
            row["rating_change"],
            _blank_to_none(row["target_price"]),
            _blank_to_none(row["target_upside"]),
            row["industry_view"],
            row["company_view"],
            row["risk_summary"],
            _blank_to_none(row["effective_start_date"]),
            _blank_to_none(row["effective_end_date"]),
            bool(row["auto_trade_enabled"]),
            row["metadata"],
        )
        for row in events.fillna("").to_dict("records")
    ]
    with connect(service) as conn:
        if source_rows:
            execute_many(
                conn,
                """
                INSERT INTO research.stock_report_source (
                    report_id, source_type, source_name, broker, analyst, report_title,
                    publish_date, source_url, public_access, copyright_note, source_confidence,
                    raw_summary, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (report_id) DO UPDATE SET
                    source_type = EXCLUDED.source_type,
                    source_name = EXCLUDED.source_name,
                    broker = EXCLUDED.broker,
                    analyst = EXCLUDED.analyst,
                    report_title = EXCLUDED.report_title,
                    publish_date = EXCLUDED.publish_date,
                    source_url = EXCLUDED.source_url,
                    public_access = EXCLUDED.public_access,
                    copyright_note = EXCLUDED.copyright_note,
                    source_confidence = EXCLUDED.source_confidence,
                    raw_summary = EXCLUDED.raw_summary,
                    metadata = EXCLUDED.metadata,
                    updated_at = now()
                """,
                source_rows,
            )
        if event_rows:
            execute_many(
                conn,
                """
                INSERT INTO research.stock_report_event (
                    report_id, asset_id, ts_code, stock_name, industry_name, report_date,
                    rating, rating_change, target_price, target_upside, industry_view,
                    company_view, risk_summary, effective_start_date, effective_end_date,
                    auto_trade_enabled, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (report_id, ts_code) DO UPDATE SET
                    asset_id = EXCLUDED.asset_id,
                    stock_name = EXCLUDED.stock_name,
                    industry_name = EXCLUDED.industry_name,
                    report_date = EXCLUDED.report_date,
                    rating = EXCLUDED.rating,
                    rating_change = EXCLUDED.rating_change,
                    target_price = EXCLUDED.target_price,
                    target_upside = EXCLUDED.target_upside,
                    industry_view = EXCLUDED.industry_view,
                    company_view = EXCLUDED.company_view,
                    risk_summary = EXCLUDED.risk_summary,
                    effective_start_date = EXCLUDED.effective_start_date,
                    effective_end_date = EXCLUDED.effective_end_date,
                    auto_trade_enabled = EXCLUDED.auto_trade_enabled,
                    metadata = EXCLUDED.metadata,
                    updated_at = now()
                """,
                event_rows,
            )
    return {"source_rows": len(source_rows), "event_rows": len(event_rows)}


def upsert_stock_report_features(
    *,
    features: pd.DataFrame,
    service: str = SETTINGS.research_service,
) -> dict[str, int]:
    rows = [
        (
            row["trade_date"],
            row["asset_id"],
            row["ts_code"],
            row["stock_name"],
            int(row["report_count_30d"]),
            int(row["report_count_90d"]),
            _blank_to_none(row["latest_report_days"]),
            int(row["positive_rating_count"]),
            int(row["rating_upgrade_count"]),
            _blank_to_none(row["target_price_median"]),
            _blank_to_none(row["target_upside_median"]),
            _blank_to_none(row["target_price_dispersion"]),
            int(row["broker_coverage_count"]),
            int(row["top_broker_coverage_count"]),
            bool(row["negative_report_flag"]),
            _blank_to_none(row["research_support_score"]),
            int(row["source_count"]),
            bool(row["auto_trade_enabled"]),
            _metadata_to_json(row.get("metadata")),
        )
        for row in features.fillna("").to_dict("records")
    ]
    with connect(service) as conn:
        if rows:
            execute_many(
                conn,
                """
                INSERT INTO research.stock_report_feature_daily (
                    trade_date, asset_id, ts_code, stock_name, report_count_30d,
                    report_count_90d, latest_report_days, positive_rating_count,
                    rating_upgrade_count, target_price_median, target_upside_median,
                    target_price_dispersion, broker_coverage_count, top_broker_coverage_count,
                    negative_report_flag, research_support_score, source_count,
                    auto_trade_enabled, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (trade_date, ts_code) DO UPDATE SET
                    asset_id = EXCLUDED.asset_id,
                    stock_name = EXCLUDED.stock_name,
                    report_count_30d = EXCLUDED.report_count_30d,
                    report_count_90d = EXCLUDED.report_count_90d,
                    latest_report_days = EXCLUDED.latest_report_days,
                    positive_rating_count = EXCLUDED.positive_rating_count,
                    rating_upgrade_count = EXCLUDED.rating_upgrade_count,
                    target_price_median = EXCLUDED.target_price_median,
                    target_upside_median = EXCLUDED.target_upside_median,
                    target_price_dispersion = EXCLUDED.target_price_dispersion,
                    broker_coverage_count = EXCLUDED.broker_coverage_count,
                    top_broker_coverage_count = EXCLUDED.top_broker_coverage_count,
                    negative_report_flag = EXCLUDED.negative_report_flag,
                    research_support_score = EXCLUDED.research_support_score,
                    source_count = EXCLUDED.source_count,
                    auto_trade_enabled = EXCLUDED.auto_trade_enabled,
                    metadata = EXCLUDED.metadata,
                    updated_at = now()
                """,
                rows,
            )
    return {"feature_rows": len(rows)}


def _normalize_events(events: pd.DataFrame, *, trade_date: str) -> pd.DataFrame:
    result = events.copy()
    for column in ["asset_id", "ts_code", "stock_name", "broker", "rating", "rating_change"]:
        if column not in result.columns:
            result[column] = ""
    for column in ["target_price", "target_upside"]:
        if column not in result.columns:
            result[column] = np.nan
        result[column] = pd.to_numeric(result[column], errors="coerce")
    if "report_date" not in result.columns:
        result["report_date"] = pd.NaT
    result["report_date"] = pd.to_datetime(result["report_date"], errors="coerce")
    result["trade_date"] = pd.to_datetime(trade_date)
    if "negative_report_flag" not in result.columns:
        result["negative_report_flag"] = False
    result["negative_report_flag"] = result["negative_report_flag"].fillna(False).astype(bool)
    if "metadata" not in result.columns:
        result["metadata"] = [{} for _ in range(len(result))]
    result["metadata"] = result["metadata"].map(_metadata_dict)
    return result


def _feature_columns() -> list[str]:
    return [
        "trade_date",
        "asset_id",
        "ts_code",
        "stock_name",
        "report_count_30d",
        "report_count_90d",
        "latest_report_days",
        "positive_rating_count",
        "rating_upgrade_count",
        "target_price_median",
        "target_upside_median",
        "target_price_dispersion",
        "broker_coverage_count",
        "top_broker_coverage_count",
        "negative_report_flag",
        "research_support_score",
        "source_count",
        "auto_trade_enabled",
        "metadata",
    ]


def _aggregate_features(events: pd.DataFrame, *, trade_date: str) -> pd.DataFrame:
    columns = _feature_columns()
    if events.empty:
        return pd.DataFrame(columns=columns)
    as_of = pd.to_datetime(trade_date)
    rows = []
    for ts_code, group in events.groupby("ts_code", sort=True):
        dated = group.dropna(subset=["report_date"]).copy()
        days = (as_of - dated["report_date"]).dt.days if not dated.empty else pd.Series(dtype=float)
        point_in_time = dated[days.ge(0)].copy() if not dated.empty else dated
        pit_days = days[days.ge(0)] if not dated.empty else pd.Series(dtype=float)
        last_90 = point_in_time[pit_days.le(90)] if not point_in_time.empty else point_in_time
        last_30 = point_in_time[pit_days.le(30)] if not point_in_time.empty else point_in_time
        if last_90.empty:
            positive_count = 0
            upgrade_count = 0
        else:
            ratings = last_90["rating"].fillna("").astype(str).str.lower()
            positive_count = int(ratings.map(lambda value: any(token in value for token in POSITIVE_RATINGS)).sum())
            upgrade_count = int(
                last_90["rating_change"]
                .fillna("")
                .astype(str)
                .str.contains("上调|upgrade", case=False, regex=True)
                .sum()
            )
        brokers = sorted(set(last_90["broker"].dropna().astype(str)) - {""})
        target_prices = pd.to_numeric(last_90["target_price"], errors="coerce").dropna()
        target_upsides = pd.to_numeric(last_90["target_upside"], errors="coerce").dropna()
        negative = bool(last_90["negative_report_flag"].fillna(False).astype(bool).any()) if not last_90.empty else False
        metadata = _feature_metadata_from_events(last_90)
        support = _research_support_score(
            report_count_90d=len(last_90),
            positive_rating_count=positive_count,
            rating_upgrade_count=upgrade_count,
            target_upside_median=float(target_upsides.median()) if not target_upsides.empty else np.nan,
            negative_report_flag=negative,
        )
        rows.append(
            {
                "trade_date": trade_date,
                "asset_id": group["asset_id"].iloc[0] if "asset_id" in group else "",
                "ts_code": ts_code,
                "stock_name": group["stock_name"].iloc[0] if "stock_name" in group else ts_code,
                "report_count_30d": int(len(last_30)),
                "report_count_90d": int(len(last_90)),
                "latest_report_days": int(pit_days.min()) if len(pit_days) else np.nan,
                "positive_rating_count": positive_count,
                "rating_upgrade_count": upgrade_count,
                "target_price_median": float(target_prices.median()) if not target_prices.empty else np.nan,
                "target_upside_median": float(target_upsides.median()) if not target_upsides.empty else np.nan,
                "target_price_dispersion": float(target_prices.std(ddof=0)) if len(target_prices) > 1 else 0.0,
                "broker_coverage_count": int(len(brokers)),
                "top_broker_coverage_count": int(sum(any(key in broker for key in TOP_BROKER_KEYWORDS) for broker in brokers)),
                "negative_report_flag": negative,
                "research_support_score": support,
                "source_count": int(len(last_90)),
                "auto_trade_enabled": False,
                "metadata": metadata,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _feature_metadata_from_events(events: pd.DataFrame) -> dict[str, Any]:
    if events.empty:
        return {
            "pdf_target_price_count_90d": 0,
            "pdf_target_price_high_confidence_count_90d": 0,
            "pdf_profit_forecast_count_90d": 0,
            "pdf_eps_forecast_count_90d": 0,
            "pdf_pe_forecast_count_90d": 0,
            "pdf_risk_section_count_90d": 0,
            "latest_pdf_risk_summary": "",
        }
    confidences: list[float] = []
    high_confidence_count = 0
    profit_forecast_count = 0
    eps_forecast_count = 0
    pe_forecast_count = 0
    risk_section_count = 0
    latest_risk_summary = ""
    ordered = events.sort_values("report_date") if "report_date" in events.columns else events
    for row in ordered.to_dict("records"):
        pdf = _pdf_extract_metadata(row)
        confidence = _safe_float(pdf.get("target_price_confidence"))
        if confidence is not None:
            confidences.append(confidence)
            if confidence >= 0.75:
                high_confidence_count += 1
        if _truthy(pdf.get("has_profit_forecast")):
            profit_forecast_count += 1
        if _has_sequence_value(pdf.get("forecast_eps_values")):
            eps_forecast_count += 1
        if _has_sequence_value(pdf.get("forecast_pe_values")):
            pe_forecast_count += 1
        risk_summary = _safe_text(pdf.get("risk_summary") or row.get("risk_summary"))
        if _truthy(pdf.get("has_risk_section")) or risk_summary:
            risk_section_count += 1
        if risk_summary:
            latest_risk_summary = risk_summary[:200]
    result: dict[str, Any] = {
        "pdf_target_price_count_90d": int(len(confidences)),
        "pdf_target_price_high_confidence_count_90d": int(high_confidence_count),
        "pdf_profit_forecast_count_90d": int(profit_forecast_count),
        "pdf_eps_forecast_count_90d": int(eps_forecast_count),
        "pdf_pe_forecast_count_90d": int(pe_forecast_count),
        "pdf_risk_section_count_90d": int(risk_section_count),
        "latest_pdf_risk_summary": latest_risk_summary,
    }
    if confidences:
        result["pdf_target_price_confidence_avg_90d"] = round(float(np.mean(confidences)), 4)
    return result


def _pdf_extract_metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = _metadata_dict(row.get("metadata"))
    pdf = metadata.get("pdf_extract") if isinstance(metadata.get("pdf_extract"), dict) else {}
    result = dict(pdf)
    for key in [
        "target_price_confidence",
        "target_price_extract_method",
        "forecast_eps_values",
        "forecast_pe_values",
        "has_profit_forecast",
        "has_risk_section",
        "risk_summary",
    ]:
        if key not in result and key in row:
            result[key] = row.get(key)
    return result


def _metadata_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _metadata_to_json(value: Any) -> str:
    return json.dumps(_metadata_dict(value), ensure_ascii=False, sort_keys=True)


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(parsed):
        return None
    return parsed


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "是"}
    return bool(value)


def _has_sequence_value(value: Any) -> bool:
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0
    if isinstance(value, str):
        text = value.strip()
        if not text or text == "[]":
            return False
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return True
        return isinstance(parsed, list) and len(parsed) > 0
    return False


def _research_support_score(
    *,
    report_count_90d: int,
    positive_rating_count: int,
    rating_upgrade_count: int,
    target_upside_median: float,
    negative_report_flag: bool,
) -> float:
    score = min(report_count_90d, 10) * 5 + min(positive_rating_count, 10) * 6 + min(rating_upgrade_count, 5) * 4
    if pd.notna(target_upside_median):
        score += max(min(target_upside_median, 0.5), -0.5) * 30
    if negative_report_flag:
        score -= 25
    return float(max(min(score, 100), 0))


def _render_search_plan_report(search_plan: pd.DataFrame, *, trade_date: str | None, input_path: str) -> str:
    domain_summary = (
        search_plan["source_domain"].value_counts().rename_axis("source_domain").reset_index(name="count")
        if not search_plan.empty
        else pd.DataFrame(columns=["source_domain", "count"])
    )
    return "\n".join(
        [
            "# Stock Report Search Plan v1",
            "",
            "## 1. Scope",
            "Public web search task plan for stock-report metadata. No paid full text is stored and no trading instruction is produced.",
            "",
            "## 2. Inputs",
            f"- research_packet_path: {input_path}",
            f"- trade_date: {trade_date or 'all available dates'}",
            "",
            "## 3. Summary",
            f"- task_count: {len(search_plan)}",
            f"- stock_count: {search_plan['ts_code'].nunique() if not search_plan.empty else 0}",
            "",
            "## 4. Domains",
            domain_summary.to_markdown(index=False) if not domain_summary.empty else "No tasks.",
        ]
    ) + "\n"


def _render_collection_report(collection: pd.DataFrame, *, dry_run: bool, input_path: str) -> str:
    found_count = int(collection["collection_status"].eq("found").sum()) if "collection_status" in collection else 0
    return "\n".join(
        [
            "# Stock Report Web Source Collection v1",
            "",
            f"- dry_run: {dry_run}",
            f"- search_plan_path: {input_path}",
            f"- rows: {len(collection)}",
            f"- found_results: {found_count}",
            "",
            "This output stores public search-result metadata only. It does not fetch or store paid report full text.",
        ]
    ) + "\n"


def _render_feature_report(features: pd.DataFrame, *, trade_date: str) -> str:
    return "\n".join(
        [
            "# Stock Report Feature Daily v1",
            "",
            f"- trade_date: {trade_date}",
            f"- rows: {len(features)}",
            "",
            "Features are research-support diagnostics only and are not automatic trading signals.",
        ]
    ) + "\n"


def _ts_code_from_asset_id(asset_id: Any) -> str:
    parts = str(asset_id or "").split(":")
    if len(parts) == 3 and parts[0] == "CN" and parts[1] in {"SH", "SZ", "BJ"}:
        return f"{parts[2]}.{parts[1]}"
    return ""


def _ts_codes_from_candidates(candidates: pd.DataFrame) -> list[str]:
    values: set[str] = set()
    if "ts_code" in candidates.columns:
        values.update(str(value).strip().upper() for value in candidates["ts_code"].dropna() if _has_text(value))
    if "asset_id" in candidates.columns:
        values.update(
            _ts_code_from_asset_id(value).upper()
            for value in candidates["asset_id"].dropna()
            if _has_text(_ts_code_from_asset_id(value))
        )
    return sorted(values)


def _load_stock_name_lookup_from_paths(
    lookup_paths: list[str | Path] | tuple[str | Path, ...],
    ts_codes: list[str],
) -> dict[str, str]:
    if not ts_codes:
        return {}
    wanted = {code.upper() for code in ts_codes}
    lookup: dict[str, str] = {}
    for raw_path in lookup_paths:
        path = Path(raw_path)
        if not path.exists():
            continue
        try:
            frame = pd.read_csv(path, usecols=lambda col: col in {"ts_code", "stock_name"}, low_memory=False)
        except Exception:
            continue
        if not {"ts_code", "stock_name"}.issubset(frame.columns):
            continue
        frame = frame.copy()
        frame["ts_code"] = frame["ts_code"].astype(str).str.strip().str.upper()
        frame["stock_name"] = frame["stock_name"].astype(str).str.strip()
        frame = frame[frame["ts_code"].isin(wanted) & frame["stock_name"].map(_has_text)]
        for row in frame.to_dict("records"):
            name = str(row["stock_name"]).strip()
            code = str(row["ts_code"]).strip().upper()
            if not _is_placeholder_stock_name(name, "", code):
                lookup.setdefault(code, name)
    return lookup


def _stock_name_lookup_from_rows(rows: list[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for row in rows:
        name = _safe_text(row.get("name"))
        if not name:
            continue
        ts_code = _safe_text(row.get("ts_code")).upper()
        if not ts_code:
            symbol = _safe_text(row.get("symbol"))
            exchange = _safe_text(row.get("exchange")).upper()
            if symbol and exchange in {"SH", "SZ", "BJ"}:
                ts_code = f"{symbol}.{exchange}"
        if ts_code and not _is_placeholder_stock_name(name, row.get("asset_id"), ts_code):
            lookup.setdefault(ts_code, name)
    return lookup


def _resolve_stock_name(
    *,
    current_name: Any,
    asset_id: Any,
    ts_code: Any,
    lookup: dict[str, str],
) -> str:
    normalized_ts_code = _safe_text(ts_code).upper() or _ts_code_from_asset_id(asset_id).upper()
    current = _safe_text(current_name)
    if current and not _is_placeholder_stock_name(current, asset_id, normalized_ts_code):
        return current
    return lookup.get(normalized_ts_code, current)


def _is_placeholder_stock_name(name: Any, asset_id: Any, ts_code: Any) -> bool:
    text = _safe_text(name)
    if not text:
        return True
    normalized_ts_code = _safe_text(ts_code).upper()
    code = normalized_ts_code.split(".")[0] if normalized_ts_code else ""
    asset_code = _safe_text(asset_id).split(":")[-1]
    return text in {code, asset_code, normalized_ts_code}


def _default_fetcher(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self._current_href = ""
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        href = attrs_dict.get("href") or ""
        if href:
            self._current_href = href
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._current_href:
            return
        title = " ".join(" ".join(self._current_text).split())
        self.links.append({"href": self._current_href, "title": title})
        self._current_href = ""
        self._current_text = []


def _extract_public_search_results(
    html: str,
    *,
    task: dict[str, Any],
    max_results: int,
) -> list[dict[str, Any]]:
    parser = _AnchorParser()
    parser.feed(html or "")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in parser.links:
        source_url = _normalize_result_url(link.get("href", ""))
        title = _safe_text(link.get("title"))
        if not source_url or source_url in seen or not title:
            continue
        if not _is_usable_public_source(source_url):
            continue
        if not _matches_task_context(source_url=source_url, title=title, task=task):
            continue
        seen.add(source_url)
        row = dict(task)
        text = f"{title} {source_url}"
        row.update(
            {
                "result_rank": len(rows) + 1,
                "source_url": source_url,
                "source_title": title,
                "source_name": urlparse(source_url).netloc,
                "publish_date": _extract_date(text) or pd.NA,
                "broker": _extract_broker(text),
                "rating": _extract_rating(text),
                "target_price": _extract_target_price(text),
                "target_upside": pd.NA,
                "snippet": title,
                "source_confidence": _source_confidence(source_url, text),
                "collection_status": "found",
                "collection_note": "Public search-result metadata extracted; full text not fetched.",
                "auto_trade_enabled": False,
            }
        )
        rows.append(row)
        if len(rows) >= max_results:
            break
    return rows


def _normalize_result_url(url: str) -> str:
    text = _safe_text(url)
    if not text:
        return ""
    if text.startswith("//"):
        text = f"https:{text}"
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        return ""
    query = parse_qs(parsed.query)
    for key in ("url", "u", "target"):
        if query.get(key):
            candidate = unquote(query[key][0])
            if urlparse(candidate).scheme in {"http", "https"}:
                return candidate
    return text


def _sina_report_url(ts_code: str) -> str:
    symbol = _market_symbol_from_ts_code(ts_code)
    if not symbol:
        return ""
    return f"https://stock.finance.sina.com.cn/stock/go.php/vReport_List/kind/search/index.phtml?symbol={symbol}&t1=all"


def _sohu_jlp_rating_url(ts_code: str) -> str:
    bare_code = _safe_text(ts_code).split(".")[0]
    if not bare_code:
        return ""
    return f"https://q.stock.sohu.com/cn/{bare_code}/index_kp.shtml"


def _cfi_ybyl_url(ts_code: str) -> str:
    bare_code = _safe_text(ts_code).split(".")[0]
    if not bare_code:
        return ""
    return f"https://quote.cfi.cn/quote.aspx?client=pc&contenttype=ybyl&searchcode={bare_code}"


def _market_symbol_from_ts_code(ts_code: str) -> str:
    text = _safe_text(ts_code)
    if "." not in text:
        return text
    symbol, exchange = text.split(".", 1)
    exchange = exchange.lower()
    if exchange not in {"sh", "sz", "bj"}:
        return ""
    return f"{exchange}{symbol}"


def _extract_sina_report_page_rows(
    html: str,
    *,
    task: dict[str, Any],
    page_url: str,
    max_results: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cells in _extract_html_table_rows(html):
        if len(cells) < 6 or not _safe_text(cells[0]["text"]).isdigit():
            continue
        title = _safe_text(cells[1]["text"])
        report_date = _safe_text(cells[3]["text"])
        broker = _safe_text(cells[4]["text"])
        analyst = _safe_text(cells[5]["text"])
        href = _normalize_sina_result_url(cells[1]["href"])
        if not title or not report_date or not broker:
            continue
        row = dict(task)
        row.update(
            {
                "result_rank": len(rows) + 1,
                "source_url": href or page_url,
                "source_title": title,
                "source_name": "sina_report_page",
                "publish_date": report_date,
                "broker": broker,
                "rating": _extract_rating(title),
                "target_price": _extract_target_price(title),
                "target_upside": pd.NA,
                "snippet": f"{title} {broker} {analyst}".strip(),
                "source_confidence": 0.7,
                "collection_status": "found",
                "collection_note": "Sina public stock-report page metadata; full text not fetched.",
                "auto_trade_enabled": False,
            }
        )
        rows.append(row)
        if len(rows) >= max_results:
            break
    return rows


def _extract_sohu_jlp_rating_rows(
    html: str,
    *,
    task: dict[str, Any],
    page_url: str,
    max_results: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cells in _extract_html_table_rows(_extract_html_table_by_headers(html, ["评级", "目标价", "分析师", "所属机构", "研报日期"])):
        if len(cells) < 5:
            continue
        rating = _safe_text(cells[0]["text"])
        report_date = _safe_text(cells[4]["text"])
        if not rating or not re.match(r"20\d{2}-\d{2}-\d{2}", report_date):
            continue
        broker = _safe_text(cells[3]["text"])
        analyst = _safe_text(cells[2]["text"])
        target_price = _parse_target_price_text(cells[1]["text"])
        stock_name = _safe_text(task.get("stock_name")) or _safe_text(task.get("ts_code"))
        title = f"{stock_name} {rating}评级 {report_date}".strip()
        row = dict(task)
        row.update(
            {
                "result_rank": len(rows) + 1,
                "source_url": f"{page_url}#jlp-{report_date}-{len(rows) + 1}",
                "source_title": title,
                "source_name": "sohu_jlp_rating",
                "publish_date": report_date,
                "broker": broker,
                "rating": rating,
                "target_price": target_price,
                "target_upside": pd.NA,
                "snippet": f"{title} {broker} {analyst}".strip(),
                "source_confidence": 0.6,
                "collection_status": "found",
                "collection_note": "Sohu public JLP rating metadata; full text not fetched.",
                "auto_trade_enabled": False,
            }
        )
        rows.append(row)
        if len(rows) >= max_results:
            break
    return rows


def _extract_cfi_ybyl_rows(
    html: str,
    *,
    task: dict[str, Any],
    page_url: str,
    max_results: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cells in _extract_html_table_rows(_extract_html_table_by_headers(html, ["发布日期", "评级类别", "机构名称", "研报"])):
        if len(cells) < 4:
            continue
        report_date = _safe_text(cells[0]["text"])
        if not re.match(r"20\d{2}-\d{2}-\d{2}", report_date):
            continue
        rating = _safe_text(cells[1]["text"])
        broker = _safe_text(cells[2]["text"])
        title = _safe_text(cells[3]["text"])
        href = _normalize_cfi_result_url(cells[3]["href"], page_url)
        if not title or not broker:
            continue
        row = dict(task)
        row.update(
            {
                "result_rank": len(rows) + 1,
                "source_url": href or page_url,
                "source_title": title,
                "source_name": "cfi_ybyl",
                "publish_date": report_date,
                "broker": broker,
                "rating": rating,
                "target_price": _extract_target_price(title),
                "target_upside": pd.NA,
                "snippet": f"{title} {broker}".strip(),
                "source_confidence": 0.65,
                "collection_status": "found",
                "collection_note": "CFI public YBYL research report metadata; full text not fetched.",
                "auto_trade_enabled": False,
            }
        )
        rows.append(row)
        if len(rows) >= max_results:
            break
    return rows


def _normalize_cfi_result_url(href: str, page_url: str) -> str:
    url = _normalize_result_url(href)
    if url:
        return url
    text = _safe_text(href)
    if text.startswith("/"):
        return f"https://quote.cfi.cn{text}"
    return page_url


def _normalize_sina_result_url(href: str) -> str:
    url = _normalize_result_url(href)
    if url:
        return url
    text = _safe_text(href)
    if text.startswith("/"):
        return f"https://stock.finance.sina.com.cn{text}"
    return ""


def _extract_html_table_by_headers(html: str, headers: list[str]) -> str:
    for table_html in re.findall(r"<table\b[^>]*>.*?</table>", html or "", flags=re.IGNORECASE | re.DOTALL):
        text = _strip_html(table_html)
        if all(header in text for header in headers):
            return table_html
    return ""


def _extract_html_table_rows(html: str) -> list[list[dict[str, str]]]:
    rows: list[list[dict[str, str]]] = []
    for row_html in re.findall(r"<tr\b[^>]*>(.*?)</tr>", html or "", flags=re.IGNORECASE | re.DOTALL):
        cells = []
        for cell_html in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row_html, flags=re.IGNORECASE | re.DOTALL):
            cells.append({"text": _strip_html(cell_html), "href": _first_href(cell_html)})
        if cells:
            rows.append(cells)
    return rows


def _first_href(html: str) -> str:
    match = re.search(r"href=(?:[\"']([^\"']+)[\"']|([^\"'\s>]+))", html or "", flags=re.IGNORECASE)
    if not match:
        return ""
    href = match.group(1) or match.group(2) or ""
    if href.startswith("//"):
        return f"https:{href}"
    return href


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_target_price_text(value: Any) -> float | Any:
    text = _safe_text(value).replace("元", "")
    if not text or text in {"--", "——", "-"}:
        return pd.NA
    try:
        return float(text)
    except ValueError:
        return pd.NA


def _is_usable_public_source(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    if not host or host in SEARCH_ENGINE_HOSTS:
        return False
    return True


def _matches_task_context(*, source_url: str, title: str, task: dict[str, Any]) -> bool:
    text = f"{title} {source_url}".lower()
    stock_name = _safe_text(task.get("stock_name"))
    ts_code = _safe_text(task.get("ts_code"))
    bare_code = ts_code.split(".")[0] if ts_code else ""
    has_stock = (stock_name and stock_name.lower() in text) or (bare_code and bare_code in text)
    query_type = _safe_text(task.get("query_type"))
    if query_type == "industry_position":
        has_context = any(token in text for token in ("行业", "市占", "龙头", "地位", "产品"))
    else:
        has_context = any(token in text for token in ("研报", "评级", "目标价", "买入", "增持", "证券", "research"))
    return bool(has_stock and has_context)


def _extract_date(text: str) -> str:
    match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", text)
    if not match:
        return ""
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _extract_broker(text: str) -> str:
    for broker in TOP_BROKER_KEYWORDS:
        if broker in text:
            return broker
    return ""


def _extract_rating(text: str) -> str:
    for rating in ("强烈推荐", "买入", "增持", "推荐", "中性", "持有", "卖出", "减持"):
        if rating in text:
            return rating
    lowered = text.lower()
    for rating in ("buy", "outperform", "overweight", "neutral", "sell"):
        if rating in lowered:
            return rating
    return ""


def _extract_target_price(text: str) -> float | Any:
    match = TARGET_PRICE_RE.search(text)
    if not match:
        return pd.NA
    return float(match.group(1))


def _source_confidence(url: str, text: str) -> float:
    host = urlparse(url).netloc.lower()
    if any(key in host for key in ("eastmoney", "sina", "10jqka", "hexun", "stcn", "cls")):
        return 0.65
    if any(key in text for key in TOP_BROKER_KEYWORDS):
        return 0.7
    return 0.5


def _report_id_from_url(url: str) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return f"public_web_{digest}"


def _blank_to_none(value: Any) -> Any:
    if value is pd.NA or value is None:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    text = str(value).strip()
    return None if text == "" or text.lower() in {"nan", "nat", "none"} else value


def _has_text(value: Any) -> bool:
    if value is None or pd.isna(value):
        return False
    text = str(value).strip()
    return bool(text) and text.lower() not in {"nan", "none", "nat"}


def _safe_text(value: Any) -> str:
    return str(value).strip() if _has_text(value) else ""
