from __future__ import annotations

from typing import Any, Callable

from stock_research.dashboard.news import load_public_news_for_dashboard
from stock_research.dashboard.platform import load_platform_summary
from stock_research.dashboard.reports import load_report_links
from stock_research.dashboard.research_reports import list_research_reports
from stock_research.dashboard.scores import search_assets

GROUPS = [
    ("assets", "Stocks"),
    ("news", "News"),
    ("research_reports", "Research Reports"),
    ("generated_reports", "Generated Reports"),
]


def load_global_search(q: object, *, limit: int = 5) -> dict[str, Any]:
    query = str(q or "").strip()
    groups = _empty_groups()
    if len(query) < 2:
        return {"query": query, "groups": groups, "warnings": []}

    bounded_limit = _bounded_limit(limit)
    warnings: list[str] = []
    group_loaders: dict[str, Callable[[], list[dict[str, Any]]]] = {
        "assets": lambda: _asset_results(query, bounded_limit),
        "news": lambda: _news_results(query, bounded_limit),
        "research_reports": lambda: _research_report_results(query, bounded_limit),
        "generated_reports": lambda: _generated_report_results(query, bounded_limit),
    }

    for group in groups:
        key = str(group["key"])
        try:
            group["items"] = group_loaders[key]()
        except Exception as exc:
            group["items"] = []
            warnings.append(f"{key} search failed: {exc}")

    return {"query": query, "groups": groups, "warnings": warnings}


def _empty_groups() -> list[dict[str, Any]]:
    return [{"key": key, "label": label, "items": []} for key, label in GROUPS]


def _bounded_limit(limit: int) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = 5
    return max(1, min(10, value))


def _asset_results(query: str, limit: int) -> list[dict[str, Any]]:
    return [_asset_item(row) for row in search_assets(query, limit)[:limit]]


def _asset_item(row: dict[str, Any]) -> dict[str, Any]:
    asset_id = str(row.get("asset_id") or "")
    symbol = str(row.get("symbol") or "")
    exchange = str(row.get("exchange") or "")
    title = str(row.get("name") or symbol or asset_id)
    subtitle_parts = [part for part in [symbol, exchange] if part]
    return _result_item(
        id=f"asset:{asset_id}",
        type="asset",
        title=title,
        subtitle=" / ".join(subtitle_parts),
        timestamp="",
        target={"workspace": "stock", "asset_id": asset_id},
        score=100,
        metadata={
            "symbol": symbol,
            "exchange": exchange,
            "board": row.get("board"),
            "is_active": bool(row.get("is_active")),
        },
    )


def _news_results(query: str, limit: int) -> list[dict[str, Any]]:
    payload = load_public_news_for_dashboard(q=query, limit=limit)
    return [_news_item(row, query) for row in payload.get("items", [])[:limit]]


def _news_item(row: dict[str, Any], query: str) -> dict[str, Any]:
    news_id = str(row.get("news_id") or row.get("id") or "")
    stocks = row.get("stocks") if isinstance(row.get("stocks"), list) else []
    first_stock = stocks[0] if stocks and isinstance(stocks[0], dict) else {}
    target: dict[str, Any] = {"workspace": "news", "news_id": news_id, "q": query}
    if first_stock.get("asset_id"):
        target["asset_id"] = first_stock["asset_id"]
    return _result_item(
        id=f"news:{news_id}",
        type="news",
        title=str(row.get("title") or news_id),
        subtitle=str(row.get("source_channel") or row.get("source") or row.get("category") or ""),
        timestamp=str(row.get("published_at") or row.get("collected_at") or ""),
        target=target,
        score=80,
        metadata={
            "source": row.get("source"),
            "category": row.get("category"),
            "url": row.get("url"),
            "status": row.get("status"),
            "stocks": stocks,
        },
    )


def _research_report_results(query: str, limit: int) -> list[dict[str, Any]]:
    payload = list_research_reports(q=query, limit=limit)
    return [_research_report_item(row, query) for row in payload.get("items", [])[:limit]]


def _research_report_item(row: dict[str, Any], query: str) -> dict[str, Any]:
    report_id = str(row.get("report_id") or row.get("event_key") or "")
    asset_id = str(row.get("asset_id") or "")
    subtitle_parts = [
        str(part)
        for part in [
            row.get("stock_name"),
            row.get("ts_code"),
            row.get("broker"),
            row.get("rating"),
        ]
        if part
    ]
    return _result_item(
        id=f"research_report:{report_id}:{asset_id}",
        type="research_report",
        title=str(row.get("report_title") or report_id),
        subtitle=" / ".join(subtitle_parts),
        timestamp=str(row.get("publish_date") or row.get("report_date") or ""),
        target={
            "workspace": "researchReports",
            "report_id": report_id,
            "asset_id": asset_id,
            "q": query,
        },
        score=70,
        metadata={
            "ts_code": row.get("ts_code"),
            "stock_name": row.get("stock_name"),
            "broker": row.get("broker"),
            "rating": row.get("rating"),
            "source_url": row.get("source_url"),
        },
    )


def _generated_report_results(query: str, limit: int) -> list[dict[str, Any]]:
    summary = load_platform_summary()
    trade_date = str(summary.get("latest_market_date") or "")
    if not trade_date:
        raise RuntimeError("latest market date unavailable")
    matches = [
        _generated_report_item(row, query)
        for row in load_report_links(trade_date)
        if _matches_report(row, query)
    ]
    return matches[:limit]


def _matches_report(row: dict[str, Any], query: str) -> bool:
    term = query.casefold()
    haystack = " ".join(
        str(row.get(key) or "")
        for key in ["title", "report_type", "path", "trade_date"]
    ).casefold()
    return term in haystack


def _generated_report_item(row: dict[str, Any], query: str) -> dict[str, Any]:
    path = str(row.get("path") or "")
    return _result_item(
        id=f"generated_report:{path}",
        type="generated_report",
        title=str(row.get("title") or path),
        subtitle=str(row.get("report_type") or row.get("format") or ""),
        timestamp=str(row.get("trade_date") or ""),
        target={
            "workspace": "generatedReports",
            "path": path,
            "q": query,
            "trade_date": row.get("trade_date"),
        },
        score=60,
        metadata={
            "report_type": row.get("report_type"),
            "format": row.get("format"),
            "trade_date": row.get("trade_date"),
        },
    )


def _result_item(
    *,
    id: str,
    type: str,
    title: str,
    subtitle: str,
    timestamp: str,
    target: dict[str, Any],
    score: int,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": id,
        "type": type,
        "title": title,
        "subtitle": subtitle,
        "timestamp": timestamp,
        "target": target,
        "score": score,
        "metadata": metadata,
    }
