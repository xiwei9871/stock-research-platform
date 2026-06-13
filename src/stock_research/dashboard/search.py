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


def _normalise_query(value: object) -> str:
    return str(value or "").strip().casefold()


def _code_forms(value: object) -> set[str]:
    raw = _normalise_query(value)
    if not raw:
        return set()
    forms = {raw}
    if "." in raw:
        forms.add(raw.split(".", 1)[0])
    if ":" in raw:
        forms.add(raw.rsplit(":", 1)[-1])
    return {form for form in forms if form}


def _contains(value: object, query: str) -> bool:
    return bool(query and query in _normalise_query(value))


def _asset_relevance(row: dict[str, Any], query: str) -> tuple[int, str, list[str]]:
    query_forms = _code_forms(query)
    asset_id = _normalise_query(row.get("asset_id"))
    ts_code = _normalise_query(row.get("ts_code"))
    ts_code_forms = _code_forms(ts_code)
    symbol = _normalise_query(row.get("symbol"))
    name = _normalise_query(row.get("name"))
    stock_name = _normalise_query(row.get("stock_name"))

    if query and query == asset_id:
        return 100, "Exact code match", ["asset_id"]
    if symbol and symbol in query_forms:
        return 95, "Exact code match", ["symbol"]
    if ts_code and (query == ts_code or bool(query_forms & ts_code_forms)):
        return 94, "Exact code match", ["ts_code"]
    if query and query == name:
        return 90, "Stock name match", ["name"]
    if query and query == stock_name:
        return 90, "Stock name match", ["stock_name"]
    if query and symbol.startswith(query):
        return 80, "Stock symbol prefix match", ["symbol"]
    if _contains(name, query):
        return 70, "Stock name match", ["name"]
    if _contains(stock_name, query):
        return 70, "Stock name match", ["stock_name"]
    return 10, "Source result", ["source"]


def _linked_stock_matches(
    stocks: list[dict[str, Any]], query: str
) -> tuple[str, list[str]] | None:
    for stock in stocks:
        score, _reason, _fields = _asset_relevance(stock, query)
        if score > 10:
            return "Linked stock mention", ["linked_stock"]
    return None


def _first_linked_asset_id(stocks: list[dict[str, Any]]) -> str:
    for stock in stocks:
        asset_id = str(stock.get("asset_id") or "")
        if asset_id:
            return asset_id
    return ""


def _research_report_relevance(row: dict[str, Any], query: str) -> tuple[int, str, list[str]]:
    asset_score, asset_reason, asset_fields = _asset_relevance(
        {
            "asset_id": row.get("asset_id"),
            "ts_code": row.get("ts_code"),
            "symbol": row.get("symbol"),
            "name": row.get("stock_name"),
        },
        query,
    )
    if asset_score > 10:
        return asset_score, asset_reason, asset_fields

    title = _normalise_query(row.get("report_title"))
    broker = _normalise_query(row.get("broker"))
    analyst = _normalise_query(row.get("analyst"))
    industry_name = _normalise_query(row.get("industry_name"))
    if query and query == title:
        return 85, "Research report title match", ["report_title"]
    if _contains(title, query):
        return 75, "Research report title match", ["report_title"]
    if _contains(broker, query):
        return 55, "Broker match", ["broker"]
    if _contains(analyst, query):
        return 52, "Analyst match", ["analyst"]
    if _contains(industry_name, query):
        return 50, "Industry match", ["industry_name"]
    return 10, "Source result", ["source"]


def _generated_report_relevance(row: dict[str, Any], query: str) -> tuple[int, str, list[str]]:
    title = _normalise_query(row.get("title"))
    report_type = _normalise_query(row.get("report_type"))
    path = _normalise_query(row.get("path"))
    trade_date = _normalise_query(row.get("trade_date"))

    if query and query == title:
        return 85, "Generated report title match", ["title"]
    if _contains(title, query):
        return 75, "Generated report title match", ["title"]
    if _contains(report_type, query):
        return 60, "Generated report type match", ["report_type"]
    if _contains(path, query):
        return 50, "Generated report path match", ["path"]
    if _contains(trade_date, query):
        return 40, "Generated report date match", ["trade_date"]
    return 10, "Source result", ["source"]


def _sort_group_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (int(item.get("score") or 0), str(item.get("timestamp") or "")),
        reverse=True,
    )


def _asset_results(query: str, limit: int) -> list[dict[str, Any]]:
    items = [_asset_item(row, query) for row in search_assets(query, limit)]
    return _sort_group_items(items)[:limit]


def _asset_item(row: dict[str, Any], query: str) -> dict[str, Any]:
    asset_id = str(row.get("asset_id") or "")
    symbol = str(row.get("symbol") or "")
    exchange = str(row.get("exchange") or "")
    title = str(row.get("name") or symbol or asset_id)
    subtitle_parts = [part for part in [symbol, exchange] if part]
    score, match_reason, match_fields = _asset_relevance(row, _normalise_query(query))
    return _result_item(
        id=f"asset:{asset_id}",
        type="asset",
        title=title,
        subtitle=" / ".join(subtitle_parts),
        timestamp="",
        target={"workspace": "stock", "asset_id": asset_id},
        score=score,
        match_reason=match_reason,
        match_fields=match_fields,
        metadata={
            "symbol": symbol,
            "exchange": exchange,
            "board": row.get("board"),
            "is_active": bool(row.get("is_active")),
        },
    )


def _news_results(query: str, limit: int) -> list[dict[str, Any]]:
    payload = load_public_news_for_dashboard(q=query, limit=limit)
    items = [_news_item(row, query) for row in payload.get("items", [])]
    return _sort_group_items(items)[:limit]


def _news_item(row: dict[str, Any], query: str) -> dict[str, Any]:
    news_id = str(row.get("news_id") or row.get("id") or "")
    stocks = row.get("stocks") if isinstance(row.get("stocks"), list) else []
    stock_rows = [stock for stock in stocks if isinstance(stock, dict)]
    linked_asset_id = _first_linked_asset_id(stock_rows)
    target: dict[str, Any] = {"workspace": "news", "news_id": news_id, "q": query}
    if linked_asset_id:
        target["asset_id"] = linked_asset_id
    normalised_query = _normalise_query(query)
    linked_match = _linked_stock_matches(stock_rows, normalised_query)
    title = row.get("title")
    summary = row.get("summary")
    if linked_match:
        score = 85
        match_reason, match_fields = linked_match
    elif normalised_query and normalised_query == _normalise_query(title):
        score, match_reason, match_fields = 80, "News title match", ["title"]
    elif _contains(title, normalised_query):
        score, match_reason, match_fields = 75, "News title match", ["title"]
    elif _contains(summary, normalised_query):
        score, match_reason, match_fields = 65, "News summary match", ["summary"]
    else:
        score, match_reason, match_fields = 10, "Source result", ["source"]
    return _result_item(
        id=f"news:{news_id}",
        type="news",
        title=str(row.get("title") or news_id),
        subtitle=str(row.get("source_channel") or row.get("source") or row.get("category") or ""),
        timestamp=str(row.get("published_at") or row.get("collected_at") or ""),
        target=target,
        score=score,
        match_reason=match_reason,
        match_fields=match_fields,
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
    items = [_research_report_item(row, query) for row in payload.get("items", [])]
    return _sort_group_items(items)[:limit]


def _research_report_item(row: dict[str, Any], query: str) -> dict[str, Any]:
    report_id = str(row.get("report_id") or row.get("event_key") or "")
    asset_id = str(row.get("asset_id") or "")
    event_key = str(row.get("event_key") or "")
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
    score, match_reason, match_fields = _research_report_relevance(
        row,
        _normalise_query(query),
    )
    return _result_item(
        id=f"research_report:{report_id}:{asset_id}",
        type="research_report",
        title=str(row.get("report_title") or report_id),
        subtitle=" / ".join(subtitle_parts),
        timestamp=str(
            row.get("published_at") or row.get("publish_date") or row.get("report_date") or ""
        ),
        target={
            "workspace": "researchReports",
            "report_id": report_id,
            "event_key": event_key,
            "asset_id": asset_id,
            "q": query,
        },
        score=score,
        match_reason=match_reason,
        match_fields=match_fields,
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
    return _sort_group_items(matches)[:limit]


def _matches_report(row: dict[str, Any], query: str) -> bool:
    term = query.casefold()
    haystack = " ".join(
        str(row.get(key) or "")
        for key in ["title", "report_type", "path", "trade_date"]
    ).casefold()
    return term in haystack


def _generated_report_item(row: dict[str, Any], query: str) -> dict[str, Any]:
    path = str(row.get("path") or "")
    score, match_reason, match_fields = _generated_report_relevance(
        row,
        _normalise_query(query),
    )
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
        score=score,
        match_reason=match_reason,
        match_fields=match_fields,
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
    match_reason: str,
    match_fields: list[str],
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
        "match_reason": match_reason,
        "match_fields": match_fields,
        "metadata": metadata,
    }
