from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.market_monitor import load_market_emotion_row
from stock_research.dashboard.schemas import (
    MarketOverviewIndex,
    MarketOverviewPayload,
)
from stock_research.db import connect, fetch_all

MARKET_OVERVIEW_INDEX_IDS = (
    "SSE_COMPOSITE",
    "SZSE_COMPONENT",
    "CHINEXT",
    "STAR_50",
    "BSE_50",
)

INDEX_NAME_MAP = {
    "SSE_COMPOSITE": "上证指数",
    "SZSE_COMPONENT": "深证成指",
    "CHINEXT": "创业板指",
    "STAR_50": "科创50",
    "BSE_50": "北证50",
}


def build_market_overview_payload(
    trade_date: str,
    *,
    service: str = SETTINGS.research_service,
) -> MarketOverviewPayload:
    overview_row = load_market_overview_row(trade_date, service=service) or {}
    index_rows = load_market_index_rows(trade_date, service=service)
    warnings: list[str] = []

    if not overview_row:
        warnings.append("market breadth overview source is unavailable")
    if not index_rows:
        warnings.append("market index snapshot source is unavailable")

    indices = [_normalize_index_row(row) for row in index_rows]
    available_index_ids = {str(row.get("index_id") or "") for row in index_rows}
    missing_index_ids = [index_id for index_id in MARKET_OVERVIEW_INDEX_IDS if index_id not in available_index_ids]
    if missing_index_ids and index_rows:
        warnings.append(
            "market overview is missing index rows for: "
            + ", ".join(INDEX_NAME_MAP.get(index_id, index_id) for index_id in missing_index_ids)
        )

    data_status = _data_status(
        has_overview=bool(overview_row),
        available_index_ids=available_index_ids,
    )
    return {
        "trade_date": trade_date,
        "updated_at": _latest_updated_at([overview_row, *index_rows]),
        "source": _combine_sources([overview_row, *index_rows], default="market_overview"),
        "data_status": data_status,
        "warnings": warnings,
        "indices": [item.to_dict() for item in indices],
        "total_amount": _number(overview_row.get("total_amount")),
        "up_count": _int_or_none(overview_row.get("up_count")),
        "down_count": _int_or_none(overview_row.get("down_count")),
        "limit_up_count": _int_or_none(overview_row.get("limit_up_count")),
        "limit_down_count": _int_or_none(overview_row.get("limit_down_count")),
    }


def load_market_overview_row(
    trade_date: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    row = load_market_emotion_row(trade_date, service=service)
    return dict(row) if row else None


def load_market_index_rows(
    trade_date: str,
    *,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    sql = """
        SELECT
            index_id,
            close,
            preclose,
            source,
            updated_at
        FROM market.index_daily_bar
        WHERE trade_date = %s
          AND index_id = ANY(%s)
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [trade_date, list(MARKET_OVERVIEW_INDEX_IDS)])
    ordered = sorted(
        rows,
        key=lambda row: (
            MARKET_OVERVIEW_INDEX_IDS.index(str(row.get("index_id") or ""))
            if str(row.get("index_id") or "") in MARKET_OVERVIEW_INDEX_IDS
            else len(MARKET_OVERVIEW_INDEX_IDS),
            str(row.get("index_id") or ""),
        ),
    )
    return [dict(row) for row in ordered]


def _normalize_index_row(row: dict[str, Any]) -> MarketOverviewIndex:
    index_id = str(row.get("index_id") or "")
    return MarketOverviewIndex(
        code=index_id,
        name=str(row.get("index_name") or INDEX_NAME_MAP.get(index_id, index_id)),
        close=_number(row.get("close")),
        change_pct=_change_pct(row.get("close"), row.get("preclose")),
    )


def _data_status(*, has_overview: bool, available_index_ids: set[str]) -> str:
    has_any_required_indices = bool(available_index_ids.intersection(MARKET_OVERVIEW_INDEX_IDS))
    has_all_required_indices = all(
        index_id in available_index_ids for index_id in MARKET_OVERVIEW_INDEX_IDS
    )
    if has_overview and has_all_required_indices:
        return "completed"
    if has_overview or has_any_required_indices:
        return "partial"
    return "missing"


def _combine_sources(rows: list[dict[str, Any]], *, default: str) -> str:
    sources = sorted({str(row.get("source") or "") for row in rows if row.get("source")})
    return ",".join(sources) if sources else default


def _latest_updated_at(rows: list[dict[str, Any]]) -> str | None:
    updated = [str(row.get("updated_at")) for row in rows if row.get("updated_at")]
    return max(updated) if updated else None


def _change_pct(close: Any, preclose: Any) -> float | None:
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
