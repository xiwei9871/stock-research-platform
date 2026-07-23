from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.schemas import SectorHeatmapItem, SectorHeatmapPayload, SectorType
from stock_research.db import connect, fetch_all

DEFAULT_INDUSTRY_SYSTEM = "csrc"
CONCEPT_SOURCE_WARNING = "concept sector source is unavailable; returning empty payload"


def build_sector_heatmap_payload(
    trade_date: str,
    *,
    sector_type: SectorType = "industry",
    service: str = SETTINGS.research_service,
) -> SectorHeatmapPayload:
    if sector_type == "concept":
        return {
            "trade_date": trade_date,
            "updated_at": None,
            "source": "concept_sector_source",
            "data_status": "missing",
            "warnings": [CONCEPT_SOURCE_WARNING],
            "items": [],
        }

    rows = load_sector_heatmap_rows(trade_date, sector_type, service=service)
    warnings: list[str] = []
    if not rows:
        warnings.append("industry sector heatmap rows are unavailable")
    items = [_normalize_heatmap_item(row, sector_type=sector_type) for row in rows]

    return {
        "trade_date": trade_date,
        "updated_at": _latest_updated_at(rows),
        "source": _combine_sources(rows, default="market.industry_daily_bar"),
        "data_status": "completed" if items else "missing",
        "warnings": warnings,
        "items": [item.to_dict() for item in items],
    }


def load_sector_heatmap_rows(
    trade_date: str,
    sector_type: SectorType,
    *,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    if sector_type != "industry":
        return []
    sql = """
        WITH member_stats AS (
            SELECT
                m.industry_system,
                m.industry_code,
                count(DISTINCT b.asset_id) FILTER (WHERE b.asset_id IS NOT NULL) AS stock_count,
                count(DISTINCT b.asset_id) FILTER (WHERE b.pct_chg > 0) AS up_count,
                count(DISTINCT b.asset_id) FILTER (WHERE b.pct_chg < 0) AS down_count
            FROM core.industry_membership m
            LEFT JOIN market_daily_bar b
              ON b.asset_id = m.asset_id
             AND b.trade_date = %s
             AND b.adjust_type = 'qfq'
            WHERE m.industry_system = %s
              AND m.level = 1
              AND m.start_date <= %s
              AND (m.end_date IS NULL OR %s < m.end_date)
            GROUP BY m.industry_system, m.industry_code
        )
        SELECT
            bars.trade_date,
            bars.industry_system,
            bars.industry_code,
            bars.industry_name,
            bars.close,
            bars.preclose,
            bars.amount * 1000 AS amount,
            bars.source,
            bars.updated_at,
            stats.stock_count,
            stats.up_count,
            stats.down_count
        FROM market.industry_daily_bar bars
        LEFT JOIN member_stats stats
          ON stats.industry_system = bars.industry_system
         AND stats.industry_code = bars.industry_code
        WHERE bars.trade_date = %s
          AND bars.industry_system = %s
        ORDER BY bars.amount DESC NULLS LAST, bars.industry_code
    """
    params = [
        trade_date,
        DEFAULT_INDUSTRY_SYSTEM,
        trade_date,
        trade_date,
        trade_date,
        DEFAULT_INDUSTRY_SYSTEM,
    ]
    with connect(service) as conn:
        return [dict(row) for row in fetch_all(conn, sql, params)]


def _normalize_heatmap_item(row: dict[str, Any], *, sector_type: SectorType) -> SectorHeatmapItem:
    return SectorHeatmapItem(
        sector_id=str(row.get("sector_id") or row.get("industry_code") or ""),
        sector_name=str(row.get("sector_name") or row.get("industry_name") or ""),
        sector_type=sector_type,
        change_pct=_change_pct(row.get("change_pct"), row.get("close"), row.get("preclose")),
        amount=_number(row.get("amount")),
        up_count=_int_or_none(row.get("up_count")),
        down_count=_int_or_none(row.get("down_count")),
        main_net_inflow=_number(row.get("main_net_inflow")),
        stock_count=_int_or_none(row.get("stock_count")),
    )


def _combine_sources(rows: list[dict[str, Any]], *, default: str) -> str:
    sources = sorted({str(row.get("source") or "") for row in rows if row.get("source")})
    return ",".join(sources) if sources else default


def _latest_updated_at(rows: list[dict[str, Any]]) -> str | None:
    updated = [str(row.get("updated_at")) for row in rows if row.get("updated_at")]
    return max(updated) if updated else None


def _change_pct(change_pct: Any, close: Any, preclose: Any) -> float | None:
    normalized_change = _number(change_pct)
    if normalized_change is not None:
        return normalized_change
    normalized_close = _number(close)
    normalized_preclose = _number(preclose)
    if normalized_close is None or normalized_preclose in (None, 0):
        return None
    return normalized_close / normalized_preclose - 1.0


def _int_or_none(value: Any) -> int | None:
    normalized = _number(value)
    return int(normalized) if normalized is not None else None


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
