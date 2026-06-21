from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.stock_report_web_collection import (
    POSITIVE_RATINGS,
    TOP_BROKER_KEYWORDS,
    _feature_columns,
    _feature_metadata_from_events,
    _metadata_dict,
    _research_support_score,
    _normalize_akshare_report_rows,
    build_stock_report_features_from_events,
    build_stock_report_sources_events_from_collection,
    upsert_stock_report_features,
    upsert_stock_report_sources_events,
)

try:
    import akshare as ak
except Exception:  # pragma: no cover - optional runtime dependency
    ak = None


TASKS_FILE = "stock_report_backfill_tasks_2025_to_2026.csv"
STATUS_FILE = "stock_report_backfill_status_2025_to_2026.csv"
SOURCES_FILE = "stock_report_backfill_source_candidates_2025_to_2026.csv"
EVENTS_FILE = "stock_report_backfill_event_candidates_2025_to_2026.csv"
FEATURES_FILE = "stock_report_feature_backfill_2025_to_2026.csv"
REPORT_FILE = "stock_report_backfill_report.md"
FEATURE_REPORT_FILE = "stock_report_feature_backfill_report.md"


def run_stock_report_backfill_plan(
    *,
    start_date: str,
    end_date: str,
    output_dir: str | Path = "outputs/research",
    sample_size: int | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    assets = load_stock_report_asset_universe(service=service)
    if sample_size is not None:
        assets = assets.head(sample_size).copy()
    return build_stock_report_backfill_plan(
        assets=assets,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
    )


def load_stock_report_asset_universe(*, service: str = SETTINGS.research_service) -> pd.DataFrame:
    sql = """
        SELECT
            asset_id,
            COALESCE(ts_code, symbol || '.' || exchange) AS ts_code,
            name AS stock_name,
            symbol
        FROM core.asset_master
        WHERE symbol IS NOT NULL
          AND exchange IN ('SH', 'SZ', 'BJ')
          AND (is_active IS NULL OR is_active)
        ORDER BY symbol
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql)
    return pd.DataFrame(rows, columns=["asset_id", "ts_code", "stock_name", "symbol"])


def build_stock_report_backfill_plan(
    *,
    assets: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    frame = assets.copy()
    for column in ["asset_id", "ts_code", "stock_name", "symbol"]:
        if column not in frame.columns:
            frame[column] = ""
    rows = []
    for row in frame.to_dict("records"):
        symbol = _safe_text(row.get("symbol")) or _safe_text(row.get("ts_code")).split(".")[0]
        ts_code = _safe_text(row.get("ts_code")) or _ts_code_from_symbol(symbol)
        rows.append(
            {
                "task_id": f"stock_report_akshare_em_{symbol}",
                "provider": "akshare_em",
                "asset_id": _safe_text(row.get("asset_id")),
                "ts_code": ts_code,
                "stock_name": _safe_text(row.get("stock_name")),
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
                "status": "pending",
                "report_count": 0,
                "latest_report_date": "",
                "error_type": "",
                "error_message": "",
                "started_at": "",
                "finished_at": "",
            }
        )
    tasks = pd.DataFrame(rows)
    report = _render_plan_report(tasks, start_date=start_date, end_date=end_date)
    result: dict[str, Any] = {"tasks": tasks, "report": report, "paths": {}}
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {"tasks": output / TASKS_FILE, "report": output / REPORT_FILE}
        tasks.to_csv(paths["tasks"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def run_stock_report_backfill_run(
    *,
    tasks_path: str | Path,
    start_date: str,
    end_date: str,
    batch_size: int = 100,
    sleep_seconds: float = 0.5,
    sample_size: int | None = None,
    output_dir: str | Path = "outputs/research",
    write_db: bool = False,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    tasks = pd.read_csv(
        tasks_path,
        dtype={"symbol": "string", "ts_code": "string", "asset_id": "string", "task_id": "string"},
        low_memory=False,
    )
    if sample_size is not None:
        tasks = tasks.head(sample_size).copy()
    status_path = Path(output_dir) / STATUS_FILE
    if status_path.exists():
        existing_status = pd.read_csv(
            status_path,
            dtype={"symbol": "string", "ts_code": "string", "asset_id": "string", "task_id": "string"},
            low_memory=False,
        )
        tasks = merge_existing_status_into_tasks(tasks, existing_status)
    result = run_stock_report_backfill_tasks(
        tasks,
        start_date=start_date,
        end_date=end_date,
        batch_size=batch_size,
        sleep_seconds=sleep_seconds,
        output_dir=output_dir,
    )
    result.setdefault("paths", {})["tasks"] = str(tasks_path)
    if write_db:
        upsert_stock_report_sources_events(
            sources=result["sources"],
            events=result["events"],
            service=service,
        )
    return result


def merge_existing_status_into_tasks(tasks: pd.DataFrame, status: pd.DataFrame) -> pd.DataFrame:
    if tasks.empty or status.empty or "task_id" not in tasks.columns or "task_id" not in status.columns:
        return tasks
    result = tasks.copy().astype("object")
    status_latest = status.dropna(subset=["task_id"]).drop_duplicates(subset=["task_id"], keep="last")
    status_by_task = status_latest.set_index("task_id").to_dict("index")
    for idx, row in result.iterrows():
        task_id = row.get("task_id")
        if task_id not in status_by_task:
            continue
        existing = status_by_task[task_id]
        existing_status = str(existing.get("status", ""))
        if existing_status in {"done", "no_report"}:
            for column, value in existing.items():
                if column in result.columns:
                    result.at[idx, column] = value
    return result


def run_stock_report_backfill_tasks(
    tasks: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    batch_size: int = 100,
    sleep_seconds: float = 0.0,
    fetcher: Any | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    fetch = fetcher or _fetch_akshare_em_reports
    status_by_task = {str(row.get("task_id", "")): dict(row) for row in tasks.to_dict("records")}
    collection_frames = []
    retryable = tasks[tasks["status"].astype(str).isin({"pending", "fetch_error", "schema_error", ""})].copy()
    eligible = retryable.head(batch_size).copy() if batch_size else retryable.copy()
    output = Path(output_dir) if output_dir is not None else None
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
    for row in eligible.to_dict("records"):
        task_id = str(row.get("task_id", ""))
        status = str(row.get("status", "pending"))
        if status not in {"pending", "fetch_error", "schema_error", ""}:
            skipped = dict(row)
            skipped["status"] = "skipped"
            status_by_task[task_id] = skipped
            continue
        started_at = pd.Timestamp.now(tz="UTC").isoformat()
        try:
            reports = fetch(_safe_text(row.get("symbol")))
            collection = _reports_to_collection(
                reports,
                task=row,
                start_date=start_date,
                end_date=end_date,
            )
            count = int(len(collection))
            done = dict(row)
            done.update(
                {
                    "status": "done" if count else "no_report",
                    "report_count": count,
                    "latest_report_date": collection["publish_date"].max() if count else "",
                    "error_type": "",
                    "error_message": "",
                    "started_at": started_at,
                    "finished_at": pd.Timestamp.now(tz="UTC").isoformat(),
                }
            )
            status_by_task[task_id] = done
            if count:
                collection_frames.append(collection)
        except Exception as exc:
            failed = dict(row)
            no_report = _is_no_report_exception(exc)
            failed.update(
                {
                    "status": "no_report" if no_report else "fetch_error",
                    "report_count": 0,
                    "latest_report_date": "",
                    "error_type": "" if no_report else type(exc).__name__,
                    "error_message": str(exc),
                    "started_at": started_at,
                    "finished_at": pd.Timestamp.now(tz="UTC").isoformat(),
                }
            )
            status_by_task[task_id] = failed
        if output is not None:
            pd.DataFrame(status_by_task.values()).to_csv(output / STATUS_FILE, index=False)
        if sleep_seconds:
            time.sleep(sleep_seconds)

    status_frame = pd.DataFrame(status_by_task.values())
    collection = pd.concat(collection_frames, ignore_index=True) if collection_frames else _empty_collection()
    sources, events = build_stock_report_sources_events_from_collection(collection)
    report = _render_run_report(status_frame, sources=sources, events=events)
    result: dict[str, Any] = {
        "status": status_frame,
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
            "status": output / STATUS_FILE,
            "sources": output / SOURCES_FILE,
            "events": output / EVENTS_FILE,
            "report": output / REPORT_FILE,
        }
        status_frame.to_csv(paths["status"], index=False)
        sources.to_csv(paths["sources"], index=False)
        events.to_csv(paths["events"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def run_stock_report_feature_backfill(
    *,
    start_date: str,
    end_date: str,
    events_path: str | Path | None = None,
    output_dir: str | Path = "outputs/research",
    write_db: bool = False,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    events = pd.read_csv(events_path, low_memory=False) if events_path else load_stock_report_events(service=service)
    trade_dates = load_trade_dates(start_date=start_date, end_date=end_date, service=service)
    result = build_stock_report_feature_backfill(events=events, trade_dates=trade_dates, output_dir=output_dir)
    if write_db:
        upsert_stock_report_features(features=result["features"], service=service)
    return result


def load_stock_report_events(*, service: str = SETTINGS.research_service) -> pd.DataFrame:
    sql = """
        SELECT
            e.report_id,
            e.asset_id,
            e.ts_code,
            e.stock_name,
            s.broker,
            e.rating,
            e.rating_change,
            e.target_price,
            e.target_upside,
            e.risk_summary,
            e.metadata,
            e.report_date::text AS report_date,
            false AS negative_report_flag
        FROM research.stock_report_event e
        LEFT JOIN research.stock_report_source s ON s.report_id = e.report_id
        WHERE e.report_date IS NOT NULL
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql)
    return pd.DataFrame(rows)


def load_trade_dates(*, start_date: str, end_date: str, service: str = SETTINGS.research_service) -> list[str]:
    sql = """
        SELECT trade_date::text AS trade_date
        FROM market_daily_bar
        WHERE trade_date BETWEEN %s AND %s
        GROUP BY trade_date
        ORDER BY trade_date
    """
    with connect(service) as conn:
        return [row["trade_date"] for row in fetch_all(conn, sql, [start_date, end_date])]


def build_stock_report_feature_backfill(
    *,
    events: pd.DataFrame,
    trade_dates: list[str],
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    feature_frame = _build_stock_report_feature_backfill_fast(events=events, trade_dates=trade_dates)
    report = _render_feature_report(feature_frame, trade_dates=trade_dates)
    result: dict[str, Any] = {"features": feature_frame, "report": report, "paths": {}}
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {"features": output / FEATURES_FILE, "report": output / FEATURE_REPORT_FILE}
        feature_frame.to_csv(paths["features"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result


def _build_stock_report_feature_backfill_fast(*, events: pd.DataFrame, trade_dates: list[str]) -> pd.DataFrame:
    columns = _feature_columns()
    if events.empty or not trade_dates:
        return pd.DataFrame(columns=columns)
    normalized = events.copy()
    for column in ["asset_id", "ts_code", "stock_name", "broker", "rating", "rating_change"]:
        if column not in normalized.columns:
            normalized[column] = ""
    for column in ["target_price", "target_upside"]:
        if column not in normalized.columns:
            normalized[column] = pd.NA
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    if "negative_report_flag" not in normalized.columns:
        normalized["negative_report_flag"] = False
    normalized["negative_report_flag"] = normalized["negative_report_flag"].fillna(False).astype(bool)
    if "metadata" not in normalized.columns:
        normalized["metadata"] = [{} for _ in range(len(normalized))]
    normalized["metadata"] = normalized["metadata"].map(_metadata_dict)
    if "risk_summary" not in normalized.columns:
        normalized["risk_summary"] = ""
    normalized["report_date"] = pd.to_datetime(normalized.get("report_date"), errors="coerce")
    normalized = normalized.dropna(subset=["report_date", "ts_code"]).copy()
    if normalized.empty:
        return pd.DataFrame(columns=columns)

    trade_date_index = pd.to_datetime(pd.Series(trade_dates), errors="coerce").dropna().sort_values()
    rows: list[dict[str, Any]] = []
    for ts_code, group in normalized.sort_values("report_date").groupby("ts_code", sort=True):
        group = group.reset_index(drop=True)
        report_dates = group["report_date"]
        report_dates_np = report_dates.to_numpy(dtype="datetime64[D]")
        active_trade_dates = trade_date_index[trade_date_index.ge(report_dates.min())]
        if active_trade_dates.empty:
            continue
        positive_flags = (
            group["rating"]
            .fillna("")
            .astype(str)
            .str.lower()
            .map(lambda value: any(token in value for token in POSITIVE_RATINGS))
            .astype(int)
            .to_numpy()
        )
        upgrade_flags = (
            group["rating_change"]
            .fillna("")
            .astype(str)
            .str.contains("上调|upgrade", case=False, regex=True)
            .astype(int)
            .to_numpy()
        )
        negative_flags = group["negative_report_flag"].fillna(False).astype(bool).astype(int).to_numpy()
        positive_prefix = np.concatenate(([0], np.cumsum(positive_flags)))
        upgrade_prefix = np.concatenate(([0], np.cumsum(upgrade_flags)))
        negative_prefix = np.concatenate(([0], np.cumsum(negative_flags)))
        broker_values = group["broker"].fillna("").astype(str).to_numpy()
        target_price_values = pd.to_numeric(group["target_price"], errors="coerce").to_numpy(dtype=float)
        target_upside_values = pd.to_numeric(group["target_upside"], errors="coerce").to_numpy(dtype=float)
        asset_id = group["asset_id"].iloc[0] if "asset_id" in group else ""
        stock_name = group["stock_name"].iloc[0] if "stock_name" in group else ts_code
        for as_of in active_trade_dates:
            as_of_np = np.datetime64(as_of.date(), "D")
            end = int(np.searchsorted(report_dates_np, as_of_np, side="right"))
            if end <= 0:
                continue
            start_90 = int(np.searchsorted(report_dates_np, as_of_np - np.timedelta64(90, "D"), side="left"))
            start_30 = int(np.searchsorted(report_dates_np, as_of_np - np.timedelta64(30, "D"), side="left"))
            positive_count = int(positive_prefix[end] - positive_prefix[start_90])
            upgrade_count = int(upgrade_prefix[end] - upgrade_prefix[start_90])
            negative = bool(negative_prefix[end] - negative_prefix[start_90] > 0)
            brokers = sorted({value for value in broker_values[start_90:end] if value})
            target_prices = target_price_values[start_90:end]
            target_prices = target_prices[~np.isnan(target_prices)]
            target_upsides = target_upside_values[start_90:end]
            target_upsides = target_upsides[~np.isnan(target_upsides)]
            target_upside_median = float(np.median(target_upsides)) if len(target_upsides) else pd.NA
            metadata = _feature_metadata_from_events(group.iloc[start_90:end])
            rows.append(
                {
                    "trade_date": as_of.strftime("%Y-%m-%d"),
                    "asset_id": asset_id,
                    "ts_code": ts_code,
                    "stock_name": stock_name,
                    "report_count_30d": int(end - start_30),
                    "report_count_90d": int(end - start_90),
                    "latest_report_days": int((as_of_np - report_dates_np[end - 1]).astype("timedelta64[D]").astype(int)),
                    "positive_rating_count": positive_count,
                    "rating_upgrade_count": upgrade_count,
                    "target_price_median": float(np.median(target_prices)) if len(target_prices) else pd.NA,
                    "target_upside_median": target_upside_median,
                    "target_price_dispersion": float(np.std(target_prices, ddof=0)) if len(target_prices) > 1 else 0.0,
                    "broker_coverage_count": int(len(brokers)),
                    "top_broker_coverage_count": int(sum(any(key in broker for key in TOP_BROKER_KEYWORDS) for broker in brokers)),
                    "negative_report_flag": negative,
                    "research_support_score": _research_support_score(
                        report_count_90d=end - start_90,
                        positive_rating_count=positive_count,
                        rating_upgrade_count=upgrade_count,
                        target_upside_median=target_upside_median,
                        negative_report_flag=negative,
                    ),
                    "source_count": int(end - start_90),
                    "auto_trade_enabled": False,
                    "metadata": metadata,
                }
            )
    return pd.DataFrame(rows, columns=columns)


def _fetch_akshare_em_reports(symbol: str) -> pd.DataFrame:
    if ak is None:
        raise RuntimeError("akshare package is required for stock report backfill")
    return ak.stock_research_report_em(symbol=symbol)


def _reports_to_collection(
    reports: pd.DataFrame,
    *,
    task: dict[str, Any],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    search_task = {
        "task_id": task.get("task_id", ""),
        "trade_date": end_date,
        "asset_id": task.get("asset_id", ""),
        "ts_code": task.get("ts_code", ""),
        "stock_name": task.get("stock_name", ""),
        "industry_name": "",
        "candidate_rank": 999,
        "query_type": "broker_report",
        "source_domain": "eastmoney",
        "search_query": f"{task.get('stock_name', '')} {task.get('ts_code', '')} 东方财富 研报",
        "search_url": "",
        "priority": 999,
        "status": "pending",
        "auto_trade_enabled": False,
        "notes": "Backfill metadata only; do not fetch report full text.",
    }
    collection = _normalize_akshare_report_rows(reports, task=search_task)
    if collection.empty:
        return collection
    collection["publish_date"] = pd.to_datetime(collection["publish_date"], errors="coerce")
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    collection = collection[
        collection["publish_date"].ge(start)
        & collection["publish_date"].le(end)
    ].copy()
    collection["publish_date"] = collection["publish_date"].dt.strftime("%Y-%m-%d")
    return collection.reset_index(drop=True)


def _empty_collection() -> pd.DataFrame:
    return _normalize_akshare_report_rows(pd.DataFrame(), task={})


def _is_no_report_exception(exc: Exception) -> bool:
    return isinstance(exc, KeyError) and "infoCode" in str(exc)


def _render_plan_report(tasks: pd.DataFrame, *, start_date: str, end_date: str) -> str:
    return "\n".join(
        [
            "# Stock Report Backfill Plan v1",
            "",
            f"- start_date: {start_date}",
            f"- end_date: {end_date}",
            f"- task_count: {len(tasks)}",
            "",
            "只回填公开研报元数据，不抓取研报全文，不生成交易指令。",
        ]
    ) + "\n"


def _render_run_report(status: pd.DataFrame, *, sources: pd.DataFrame, events: pd.DataFrame) -> str:
    status_counts = status["status"].value_counts().rename_axis("status").reset_index(name="count") if not status.empty else pd.DataFrame()
    return "\n".join(
        [
            "# Stock Report Backfill Run v1",
            "",
            f"- task_rows: {len(status)}",
            f"- source_rows: {len(sources)}",
            f"- event_rows: {len(events)}",
            "",
            status_counts.to_markdown(index=False) if not status_counts.empty else "No tasks.",
        ]
    ) + "\n"


def _render_feature_report(features: pd.DataFrame, *, trade_dates: list[str]) -> str:
    return "\n".join(
        [
            "# Stock Report Feature Backfill v1",
            "",
            f"- trade_date_count: {len(trade_dates)}",
            f"- feature_rows: {len(features)}",
            "",
            "Features are point-in-time: report_date <= trade_date.",
        ]
    ) + "\n"


def _safe_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _ts_code_from_symbol(symbol: str) -> str:
    if symbol.startswith(("600", "601", "603", "605", "688", "689")):
        return f"{symbol}.SH"
    if symbol.startswith(("000", "001", "002", "003", "300", "301", "302")):
        return f"{symbol}.SZ"
    if symbol.startswith(("43", "83", "87", "92")):
        return f"{symbol}.BJ"
    return symbol
