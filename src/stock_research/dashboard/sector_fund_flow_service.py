from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.schemas import SectorFundFlowItem, SectorFundFlowPayload, SectorType
from stock_research.db import connect, fetch_all

FUND_FLOW_SOURCE = "derived:industry_amount_price_breadth_proxy"
CONCEPT_FUND_FLOW_SOURCE = "derived:concept_amount_price_breadth_proxy"
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
            "source": CONCEPT_FUND_FLOW_SOURCE if sector_type == "concept" else FUND_FLOW_SOURCE,
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
            (
                "fund flow values are derived directional proxies from amount, price, and breadth"
                if sector_type == "concept"
                else "fund flow values are third-party directional signals and may be incomplete"
            )
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
    del period
    if sector_type == "concept":
        sql = """
            WITH leading_stocks AS (
                SELECT DISTINCT ON (m.concept_system, m.concept_code)
                    m.concept_system,
                    m.concept_code,
                    COALESCE(a.name, b.asset_id) AS leading_stock_name
                FROM core.concept_membership m
                JOIN market_daily_bar b
                  ON b.asset_id = m.asset_id
                 AND b.trade_date = %s
                 AND b.adjust_type = 'qfq'
                LEFT JOIN core.asset_master a
                  ON a.asset_id = b.asset_id
                WHERE m.concept_system = 'ths'
                  AND m.start_date <= %s
                  AND (m.end_date IS NULL OR %s < m.end_date)
                ORDER BY
                    m.concept_system,
                    m.concept_code,
                    b.pct_chg DESC NULLS LAST,
                    b.amount DESC NULLS LAST,
                    b.asset_id
            )
            SELECT
                bars.trade_date,
                bars.concept_system,
                bars.concept_code,
                bars.concept_name,
                bars.close,
                bars.preclose,
                bars.amount * 1000 AS amount,
                (bars.close / NULLIF(bars.preclose, 0) - 1.0) AS change_pct,
                (
                    COALESCE(bars.amount, 0) * 1000
                    * COALESCE((bars.close / NULLIF(bars.preclose, 0) - 1.0), 0)
                    * COALESCE(
                        (bars.up_count - bars.down_count)::numeric / NULLIF(bars.stock_count, 0),
                        0
                    )
                ) AS main_net_inflow,
                CASE
                    WHEN COALESCE(bars.amount, 0) = 0 THEN NULL
                    ELSE (
                        COALESCE((bars.close / NULLIF(bars.preclose, 0) - 1.0), 0)
                        * COALESCE(
                            (bars.up_count - bars.down_count)::numeric / NULLIF(bars.stock_count, 0),
                            0
                        )
                    )
                END AS main_net_inflow_ratio,
                leaders.leading_stock_name,
                'derived:concept_amount_price_breadth_proxy' AS source,
                bars.updated_at
            FROM market.concept_daily_bar bars
            LEFT JOIN leading_stocks leaders
              ON leaders.concept_system = bars.concept_system
             AND leaders.concept_code = bars.concept_code
            WHERE bars.trade_date = %s
              AND bars.concept_system = 'ths'
            ORDER BY abs(
                COALESCE(bars.amount, 0)
                * COALESCE((bars.close / NULLIF(bars.preclose, 0) - 1.0), 0)
                * COALESCE((bars.up_count - bars.down_count)::numeric / NULLIF(bars.stock_count, 0), 0)
            ) DESC,
            bars.concept_code
        """
        params = [trade_date, trade_date, trade_date, trade_date]
        with connect(service) as conn:
            return [dict(row) for row in fetch_all(conn, sql, params)]
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
            WHERE m.industry_system = 'csrc'
              AND m.level = 1
              AND m.start_date <= %s
              AND (m.end_date IS NULL OR %s < m.end_date)
            GROUP BY m.industry_system, m.industry_code
        ),
        leading_stocks AS (
            SELECT DISTINCT ON (m.industry_system, m.industry_code)
                m.industry_system,
                m.industry_code,
                COALESCE(a.name, b.asset_id) AS leading_stock_name
            FROM core.industry_membership m
            JOIN market_daily_bar b
              ON b.asset_id = m.asset_id
             AND b.trade_date = %s
             AND b.adjust_type = 'qfq'
            LEFT JOIN core.asset_master a
              ON a.asset_id = b.asset_id
            WHERE m.industry_system = 'csrc'
              AND m.level = 1
              AND m.start_date <= %s
              AND (m.end_date IS NULL OR %s < m.end_date)
            ORDER BY
                m.industry_system,
                m.industry_code,
                b.pct_chg DESC NULLS LAST,
                b.amount DESC NULLS LAST,
                b.asset_id
        )
        SELECT
            bars.trade_date,
            bars.industry_system,
            bars.industry_code,
            bars.industry_name,
            bars.close,
            bars.preclose,
            bars.amount * 1000 AS amount,
            (bars.close / NULLIF(bars.preclose, 0) - 1.0) AS change_pct,
            (
                COALESCE(bars.amount, 0) * 1000
                * COALESCE((bars.close / NULLIF(bars.preclose, 0) - 1.0), 0)
                * COALESCE(
                    (stats.up_count - stats.down_count)::numeric / NULLIF(stats.stock_count, 0),
                    0
                )
            ) AS main_net_inflow,
            CASE
                WHEN COALESCE(bars.amount, 0) = 0 THEN NULL
                ELSE (
                    COALESCE((bars.close / NULLIF(bars.preclose, 0) - 1.0), 0)
                    * COALESCE(
                        (stats.up_count - stats.down_count)::numeric / NULLIF(stats.stock_count, 0),
                        0
                    )
                )
            END AS main_net_inflow_ratio,
            leaders.leading_stock_name,
            'derived:industry_amount_price_breadth_proxy' AS source,
            bars.updated_at
        FROM market.industry_daily_bar bars
        LEFT JOIN member_stats stats
          ON stats.industry_system = bars.industry_system
         AND stats.industry_code = bars.industry_code
        LEFT JOIN leading_stocks leaders
          ON leaders.industry_system = bars.industry_system
         AND leaders.industry_code = bars.industry_code
        WHERE bars.trade_date = %s
          AND bars.industry_system = 'csrc'
        ORDER BY abs(
            COALESCE(bars.amount, 0)
            * COALESCE((bars.close / NULLIF(bars.preclose, 0) - 1.0), 0)
            * COALESCE((stats.up_count - stats.down_count)::numeric / NULLIF(stats.stock_count, 0), 0)
        ) DESC,
        bars.industry_code
    """
    params = [
        trade_date,
        trade_date,
        trade_date,
        trade_date,
        trade_date,
        trade_date,
        trade_date,
    ]
    with connect(service) as conn:
        return [dict(row) for row in fetch_all(conn, sql, params)]


def _normalize_fund_flow_item(row: dict[str, Any], *, sector_type: SectorType) -> SectorFundFlowItem:
    return SectorFundFlowItem(
        rank=int(row.get("rank") or 0),
        sector_id=str(row.get("sector_id") or row.get("industry_code") or row.get("concept_code") or ""),
        sector_name=str(row.get("sector_name") or row.get("industry_name") or row.get("concept_name") or ""),
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
