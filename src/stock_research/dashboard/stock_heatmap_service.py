from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all

SUPPORTED_MARKET = "all"
SUPPORTED_PERIOD = "1d"
SUPPORTED_GROUP = "industry"
SUPPORTED_SIZE_BY = "amount"
DEFAULT_INDUSTRY_SYSTEM = "csrc"


def build_stock_heatmap_payload(
    trade_date: str,
    *,
    market: str = SUPPORTED_MARKET,
    period: str = SUPPORTED_PERIOD,
    group: str = SUPPORTED_GROUP,
    size_by: str = SUPPORTED_SIZE_BY,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    _validate_options(market=market, period=period, group=group, size_by=size_by)
    rows = load_stock_heatmap_rows(trade_date, service=service)
    if not rows:
        return {
            "trade_date": trade_date,
            "market": market,
            "period": period,
            "group": group,
            "size_by": size_by,
            "updated_at": None,
            "source": "market_daily_bar,asset_master,core.industry_membership",
            "data_status": "missing",
            "warnings": ["stock heatmap rows are unavailable"],
            "summary": _empty_summary(),
            "groups": [],
        }

    groups: dict[str, dict[str, Any]] = {}
    stock_count = up_count = flat_count = down_count = 0
    total_amount = 0.0

    for row in rows:
        stock = _normalize_stock(row)
        stock_count += 1
        amount = stock["amount"] or 0.0
        change_pct = stock["change_pct"] or 0.0
        total_amount += amount
        if change_pct > 0.001:
            up_count += 1
        elif change_pct < -0.001:
            down_count += 1
        else:
            flat_count += 1

        group_id = stock["group_id"]
        current = groups.setdefault(
            group_id,
            {
                "group_id": group_id,
                "group_name": stock["group_name"],
                "value": 0.0,
                "_weighted_change": 0.0,
                "_weight": 0.0,
                "stock_count": 0,
                "children": [],
            },
        )
        value = stock["value"] or 1.0
        current["value"] += value
        current["_weighted_change"] += change_pct * value
        current["_weight"] += value
        current["stock_count"] += 1
        current["children"].append(stock)

    normalized_groups = []
    for item in groups.values():
        weight = item.pop("_weight")
        weighted_change = item.pop("_weighted_change")
        item["change_pct"] = weighted_change / weight if weight > 0 else 0.0
        item["children"].sort(key=lambda child: child["value"], reverse=True)
        normalized_groups.append(item)

    normalized_groups.sort(key=lambda item: item["value"], reverse=True)

    return {
        "trade_date": trade_date,
        "market": market,
        "period": period,
        "group": group,
        "size_by": size_by,
        "updated_at": _latest_updated_at(rows),
        "source": _combine_sources(rows),
        "data_status": "completed",
        "warnings": [],
        "summary": {
            "stock_count": stock_count,
            "up_count": up_count,
            "flat_count": flat_count,
            "down_count": down_count,
            "total_amount": total_amount,
        },
        "groups": normalized_groups,
    }


def stock_heatmap_read_model(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "trade_date": str(payload.get("trade_date") or ""),
        "market": str(payload.get("market") or SUPPORTED_MARKET),
        "period": str(payload.get("period") or SUPPORTED_PERIOD),
        "group": str(payload.get("group") or SUPPORTED_GROUP),
        "size_by": str(payload.get("size_by") or SUPPORTED_SIZE_BY),
        "updated_at": payload.get("updated_at"),
        "source": str(payload.get("source") or ""),
        "data_status": str(payload.get("data_status") or "missing"),
        "warnings": list(payload.get("warnings") or []),
        "summary": dict(payload.get("summary") or _empty_summary()),
        "groups": [_group_read_model(group) for group in payload.get("groups") or []],
    }


def load_stock_heatmap_rows(
    trade_date: str,
    *,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    sql = """
        SELECT
            bars.trade_date,
            bars.asset_id,
            COALESCE(core_asset.symbol, asset.symbol, bars.asset_id) AS symbol,
            COALESCE(core_asset.name, asset.name, bars.asset_id) AS name,
            COALESCE(industry.industry_code, 'UNKNOWN') AS industry_code,
            COALESCE(industry.industry_name, '未分组') AS industry_name,
            bars.close,
            bars.pct_chg,
            bars.amount,
            bars.source,
            bars.updated_at
        FROM market_daily_bar bars
        LEFT JOIN asset_master asset
          ON asset.asset_id = bars.asset_id
        LEFT JOIN core.asset_master core_asset
          ON core_asset.asset_id = bars.asset_id
        LEFT JOIN core.industry_membership industry
          ON industry.asset_id = bars.asset_id
         AND industry.industry_system = %s
         AND industry.level = 1
         AND industry.start_date <= %s
         AND (industry.end_date IS NULL OR %s < industry.end_date)
        WHERE bars.trade_date = %s
          AND bars.adjust_type = 'qfq'
        ORDER BY bars.amount DESC NULLS LAST, bars.asset_id
    """
    with connect(service) as conn:
        return [dict(row) for row in fetch_all(conn, sql, [DEFAULT_INDUSTRY_SYSTEM, trade_date, trade_date, trade_date])]


def _validate_options(*, market: str, period: str, group: str, size_by: str) -> None:
    if market != SUPPORTED_MARKET or period != SUPPORTED_PERIOD or group != SUPPORTED_GROUP or size_by != SUPPORTED_SIZE_BY:
        raise ValueError("unsupported_stock_heatmap_option")


def _normalize_stock(row: dict[str, Any]) -> dict[str, Any]:
    amount = _number(row.get("amount")) or 0.0
    change_pct = _change_pct(row.get("pct_chg"))
    group_id = str(row.get("industry_code") or "UNKNOWN")
    group_name = str(row.get("industry_name") or "未分组")
    return {
        "asset_id": str(row.get("asset_id") or ""),
        "symbol": str(row.get("symbol") or row.get("asset_id") or ""),
        "name": str(row.get("name") or row.get("asset_id") or ""),
        "price": _number(row.get("close")),
        "change_pct": change_pct,
        "amount": amount,
        "value": max(amount, 1.0),
        "group_id": group_id,
        "group_name": group_name,
    }


def _group_read_model(group: dict[str, Any]) -> dict[str, Any]:
    return {
        "group_id": str(group.get("group_id") or ""),
        "group_name": str(group.get("group_name") or ""),
        "value": _number(group.get("value")),
        "change_pct": _number(group.get("change_pct")),
        "stock_count": int(group.get("stock_count") or 0),
        "children": [_stock_read_model(stock) for stock in group.get("children") or []],
    }


def _stock_read_model(stock: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": str(stock.get("asset_id") or ""),
        "symbol": str(stock.get("symbol") or ""),
        "name": str(stock.get("name") or ""),
        "price": _number(stock.get("price")),
        "change_pct": _number(stock.get("change_pct")),
        "amount": _number(stock.get("amount")),
        "value": _number(stock.get("value")),
        "group_id": str(stock.get("group_id") or ""),
        "group_name": str(stock.get("group_name") or ""),
    }


def _empty_summary() -> dict[str, Any]:
    return {
        "stock_count": 0,
        "up_count": 0,
        "flat_count": 0,
        "down_count": 0,
        "total_amount": 0.0,
    }


def _combine_sources(rows: list[dict[str, Any]]) -> str:
    sources = sorted({str(row.get("source") or "") for row in rows if row.get("source")})
    if "core.industry_membership" not in sources:
        sources.append("core.industry_membership")
    return ",".join(sources) if sources else "market_daily_bar,core.industry_membership"


def _latest_updated_at(rows: list[dict[str, Any]]) -> str | None:
    updated = [str(row.get("updated_at")) for row in rows if row.get("updated_at")]
    return max(updated) if updated else None


def _change_pct(value: Any) -> float | None:
    normalized = _number(value)
    if normalized is None:
        return None
    return normalized / 100.0


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        return float(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, int):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
