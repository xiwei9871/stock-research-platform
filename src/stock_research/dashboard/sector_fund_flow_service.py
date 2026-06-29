from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.schemas import SectorFundFlowItem, SectorFundFlowPayload, SectorType

FUND_FLOW_SOURCE = "third_party_fund_flow_signal"
FUND_FLOW_MISSING_WARNING = (
    "fund flow source is unavailable; returning empty directional signal payload"
)


def build_sector_fund_flow_payload(
    trade_date: str,
    *,
    sector_type: SectorType = "industry",
    period: str = "1d",
    service: str = SETTINGS.research_service,
) -> SectorFundFlowPayload:
    rows = load_sector_fund_flow_rows(
        trade_date,
        sector_type,
        period=period,
        service=service,
    )
    if not rows:
        return {
            "trade_date": trade_date,
            "updated_at": None,
            "source": FUND_FLOW_SOURCE,
            "data_status": "missing",
            "warnings": [FUND_FLOW_MISSING_WARNING],
            "inflow": [],
            "outflow": [],
        }

    normalized = [_normalize_fund_flow_item(row, sector_type=sector_type) for row in rows]
    inflow_items = [item for item in normalized if (item.main_net_inflow or 0.0) > 0]
    outflow_items = [item for item in normalized if (item.main_net_inflow or 0.0) < 0]
    inflow_items.sort(key=lambda item: item.main_net_inflow or 0.0, reverse=True)
    outflow_items.sort(key=lambda item: item.main_net_inflow or 0.0)

    return {
        "trade_date": trade_date,
        "updated_at": _latest_updated_at(rows),
        "source": _combine_sources(rows, default=FUND_FLOW_SOURCE),
        "data_status": "completed",
        "warnings": [
            "fund flow values are third-party directional signals and may be incomplete"
        ],
        "inflow": [_with_rank(item, rank + 1).to_dict() for rank, item in enumerate(inflow_items)],
        "outflow": [_with_rank(item, rank + 1).to_dict() for rank, item in enumerate(outflow_items)],
    }


def load_sector_fund_flow_rows(
    trade_date: str,
    sector_type: SectorType,
    *,
    period: str = "1d",
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    del trade_date, sector_type, period, service
    return []


def _normalize_fund_flow_item(row: dict[str, Any], *, sector_type: SectorType) -> SectorFundFlowItem:
    return SectorFundFlowItem(
        rank=int(row.get("rank") or 0),
        sector_id=str(row.get("sector_id") or row.get("industry_code") or ""),
        sector_name=str(row.get("sector_name") or row.get("industry_name") or ""),
        sector_type=sector_type,
        change_pct=_change_pct(row.get("change_pct"), row.get("close"), row.get("preclose")),
        amount=_number(row.get("amount")),
        main_net_inflow=_number(row.get("main_net_inflow")),
        main_net_inflow_ratio=_number(row.get("main_net_inflow_ratio")),
        leading_stock_name=_string_or_none(row.get("leading_stock_name")),
    )


def _with_rank(item: SectorFundFlowItem, rank: int) -> SectorFundFlowItem:
    return SectorFundFlowItem(
        rank=rank,
        sector_id=item.sector_id,
        sector_name=item.sector_name,
        sector_type=item.sector_type,
        change_pct=item.change_pct,
        amount=item.amount,
        main_net_inflow=item.main_net_inflow,
        main_net_inflow_ratio=item.main_net_inflow_ratio,
        leading_stock_name=item.leading_stock_name,
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


def _string_or_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


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
