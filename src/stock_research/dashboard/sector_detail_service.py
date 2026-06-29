from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.schemas import (
    SectorDetailPayload,
    SectorLeadingStock,
    SectorType,
)
from stock_research.db import connect, fetch_all

from .sector_heatmap_service import DEFAULT_INDUSTRY_SYSTEM, load_sector_heatmap_rows

CONCEPT_DETAIL_WARNING = "concept sector detail source is unavailable; returning empty payload"


def build_sector_detail_payload(
    trade_date: str,
    sector_id: str,
    *,
    sector_type: SectorType = "industry",
    service: str = SETTINGS.research_service,
) -> SectorDetailPayload:
    detail_row = load_sector_detail_row(
        trade_date,
        sector_id,
        sector_type,
        service=service,
    )
    leading_rows = load_sector_leading_stocks(
        trade_date,
        sector_id,
        sector_type,
        service=service,
    )

    if sector_type == "concept":
        return _empty_detail_payload(
            trade_date,
            sector_id,
            sector_type,
            source="concept_sector_source",
            warnings=[CONCEPT_DETAIL_WARNING],
        )
    if not detail_row:
        return _empty_detail_payload(
            trade_date,
            sector_id,
            sector_type,
            source="market.industry_daily_bar",
            warnings=["sector detail row is unavailable"],
        )

    leading_stocks = [_normalize_leading_stock(row) for row in leading_rows]
    warnings: list[str] = []
    data_status = "completed"
    if _number(detail_row.get("main_net_inflow")) is None or _number(
        detail_row.get("main_net_inflow_ratio")
    ) is None:
        data_status = "partial"
        warnings.append(
            "fund flow fields are unavailable for sector detail; returning partial payload"
        )
    return {
        "trade_date": trade_date,
        "updated_at": _latest_updated_at([detail_row, *leading_rows]),
        "source": _combine_sources([detail_row, *leading_rows], default="market.industry_daily_bar"),
        "data_status": data_status,
        "warnings": warnings,
        "sector_id": str(detail_row.get("sector_id") or detail_row.get("industry_code") or sector_id),
        "sector_name": str(detail_row.get("sector_name") or detail_row.get("industry_name") or sector_id),
        "sector_type": sector_type,
        "change_pct": _change_pct(
            detail_row.get("change_pct"),
            detail_row.get("close"),
            detail_row.get("preclose"),
        ),
        "amount": _number(detail_row.get("amount")),
        "up_count": _int_or_none(detail_row.get("up_count")),
        "down_count": _int_or_none(detail_row.get("down_count")),
        "main_net_inflow": _number(detail_row.get("main_net_inflow")),
        "main_net_inflow_ratio": _number(detail_row.get("main_net_inflow_ratio")),
        "stock_count": _int_or_none(detail_row.get("stock_count")),
        "leading_stocks": [item.to_dict() for item in leading_stocks],
    }


def load_sector_detail_row(
    trade_date: str,
    sector_id: str,
    sector_type: SectorType,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    if sector_type != "industry":
        return None
    rows = load_sector_heatmap_rows(trade_date, sector_type, service=service)
    for row in rows:
        if str(row.get("industry_code") or row.get("sector_id") or "") == sector_id:
            return dict(row)
    return None


def load_sector_leading_stocks(
    trade_date: str,
    sector_id: str,
    sector_type: SectorType,
    *,
    service: str = SETTINGS.research_service,
    limit: int = 10,
) -> list[dict[str, Any]]:
    if sector_type != "industry":
        return []
    sql = """
        SELECT
            b.asset_id,
            COALESCE(a.name, b.asset_id) AS name,
            b.pct_chg,
            b.amount,
            b.source,
            b.updated_at
        FROM core.industry_membership m
        JOIN market_daily_bar b
          ON b.asset_id = m.asset_id
         AND b.trade_date = %s
         AND b.adjust_type = 'qfq'
        LEFT JOIN core.asset_master a
          ON a.asset_id = b.asset_id
        WHERE m.industry_system = %s
          AND m.industry_code = %s
          AND m.level = 1
          AND m.start_date <= %s
          AND (m.end_date IS NULL OR %s < m.end_date)
        ORDER BY b.pct_chg DESC NULLS LAST, b.amount DESC NULLS LAST, b.asset_id
        LIMIT %s
    """
    params = [
        trade_date,
        DEFAULT_INDUSTRY_SYSTEM,
        sector_id,
        trade_date,
        trade_date,
        max(0, int(limit)),
    ]
    with connect(service) as conn:
        return [dict(row) for row in fetch_all(conn, sql, params)]


def _normalize_leading_stock(row: dict[str, Any]) -> SectorLeadingStock:
    asset_id = str(row.get("asset_id") or "")
    return SectorLeadingStock(
        asset_id=asset_id,
        name=str(row.get("name") or asset_id),
        change_pct=_pct_chg_points_to_ratio(row.get("pct_chg")),
    )


def _empty_detail_payload(
    trade_date: str,
    sector_id: str,
    sector_type: SectorType,
    *,
    source: str,
    warnings: list[str],
) -> SectorDetailPayload:
    return {
        "trade_date": trade_date,
        "updated_at": None,
        "source": source,
        "data_status": "missing",
        "warnings": warnings,
        "sector_id": sector_id,
        "sector_name": sector_id,
        "sector_type": sector_type,
        "change_pct": None,
        "amount": None,
        "up_count": None,
        "down_count": None,
        "main_net_inflow": None,
        "main_net_inflow_ratio": None,
        "stock_count": None,
        "leading_stocks": [],
    }


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


def _pct_chg_points_to_ratio(value: Any) -> float | None:
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
