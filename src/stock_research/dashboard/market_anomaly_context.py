from __future__ import annotations

import math
from collections import defaultdict
from decimal import Decimal
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all

DEFAULT_INDUSTRY_SYSTEM = "csrc"
VOLUME_SPIKE_RATIO = 2.0
STRONG_UP_THRESHOLD = 0.05
STRONG_DOWN_THRESHOLD = -0.05


def build_market_anomaly_context(
    trade_date: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    rows = [_normalize_row(row) for row in load_market_anomaly_rows(trade_date, service=service)]
    if not rows:
        return {
            "trade_date": trade_date,
            "data_status": "missing",
            "summary": _empty_summary(),
            "hot_industries": [],
            "hot_stocks": [],
            "warnings": ["market anomaly rows are unavailable"],
        }

    tagged_rows = [_tag_stock(row) for row in rows]
    industries = _rank_industries(tagged_rows)
    hot_stocks = [
        row for row in sorted(tagged_rows, key=lambda item: (-item["anomaly_score"], item["asset_id"])) if row["anomaly_tags"]
    ][:20]

    return {
        "trade_date": trade_date,
        "data_status": "completed",
        "summary": {
            "hot_industry_count": len(industries),
            "hot_stock_count": len(hot_stocks),
            "volume_spike_count": sum(1 for row in tagged_rows if "volume_spike" in row["anomaly_tags"]),
            "strong_move_count": sum(
                1 for row in tagged_rows if "strong_up" in row["anomaly_tags"] or "strong_down" in row["anomaly_tags"]
            ),
        },
        "hot_industries": industries[:10],
        "hot_stocks": hot_stocks,
        "warnings": [],
    }


def market_anomaly_context_read_model(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "trade_date": str(payload.get("trade_date") or ""),
        "data_status": str(payload.get("data_status") or "missing"),
        "summary": _summary_read_model(payload.get("summary")),
        "hot_industries": [_industry_read_model(item) for item in payload.get("hot_industries") or []],
        "hot_stocks": [_stock_read_model(item) for item in payload.get("hot_stocks") or []],
        "warnings": list(payload.get("warnings") or []),
    }


def load_market_anomaly_rows(
    trade_date: str,
    *,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    sql = """
        WITH history AS (
            SELECT
                asset_id,
                avg(amount) AS amount_avg_20d
            FROM (
                SELECT
                    asset_id,
                    trade_date,
                    amount,
                    row_number() OVER (PARTITION BY asset_id ORDER BY trade_date DESC) AS rn
                FROM market_daily_bar
                WHERE adjust_type = 'qfq'
                  AND trade_date < %s
                  AND trade_date >= (%s::date - interval '60 day')
            ) ranked
            WHERE rn <= 20
            GROUP BY asset_id
        )
        SELECT
            bars.asset_id,
            COALESCE(core_asset.symbol, asset.symbol, bars.asset_id) AS symbol,
            COALESCE(core_asset.name, asset.name, bars.asset_id) AS name,
            COALESCE(industry.industry_code, 'UNKNOWN') AS industry_id,
            COALESCE(industry.industry_name, '未分组') AS industry_name,
            bars.close,
            bars.pct_chg,
            bars.amount,
            history.amount_avg_20d,
            bars.turnover_rate,
            COALESCE(status.is_limit_up, false) AS is_limit_up,
            COALESCE(status.is_limit_down, false) AS is_limit_down
        FROM market_daily_bar bars
        LEFT JOIN history
          ON history.asset_id = bars.asset_id
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
        LEFT JOIN core.asset_status_daily status
          ON status.trade_date = bars.trade_date
         AND status.asset_id = bars.asset_id
        WHERE bars.trade_date = %s
          AND bars.adjust_type = 'qfq'
        ORDER BY bars.amount DESC NULLS LAST, bars.asset_id
    """
    with connect(service) as conn:
        return [
            dict(row)
            for row in fetch_all(
                conn,
                sql,
                [trade_date, trade_date, DEFAULT_INDUSTRY_SYSTEM, trade_date, trade_date, trade_date],
            )
        ]


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    amount = _number(row.get("amount")) or 0.0
    amount_avg_20d = _number(row.get("amount_avg_20d"))
    amount_ratio = amount / amount_avg_20d if amount_avg_20d and amount_avg_20d > 0 else None
    return {
        "asset_id": str(row.get("asset_id") or ""),
        "symbol": str(row.get("symbol") or row.get("asset_id") or ""),
        "name": str(row.get("name") or row.get("asset_id") or ""),
        "industry_id": str(row.get("industry_id") or row.get("industry_code") or "UNKNOWN"),
        "industry_name": str(row.get("industry_name") or "未分组"),
        "change_pct": _change_pct(row.get("pct_chg")),
        "amount": amount,
        "amount_ratio_20d": amount_ratio,
        "turnover_rate": _number(row.get("turnover_rate")),
        "is_limit_up": bool(row.get("is_limit_up")),
        "is_limit_down": bool(row.get("is_limit_down")),
    }


def _tag_stock(row: dict[str, Any]) -> dict[str, Any]:
    tags: list[str] = []
    bullets: list[str] = []
    change_pct = row["change_pct"]
    amount_ratio = row["amount_ratio_20d"]

    if amount_ratio is not None and amount_ratio >= VOLUME_SPIKE_RATIO:
        tags.append("volume_spike")
        bullets.append(f"放量：成交额约为近20日均值 {amount_ratio:.1f}x。")
    if change_pct is not None and change_pct >= STRONG_UP_THRESHOLD:
        tags.append("strong_up")
        bullets.append(f"涨幅 {change_pct:.2%}，属于强势上涨。")
    if change_pct is not None and change_pct <= STRONG_DOWN_THRESHOLD:
        tags.append("strong_down")
        bullets.append(f"跌幅 {change_pct:.2%}，属于强势下跌。")
    if row["is_limit_up"]:
        tags.append("limit_up")
        bullets.append("收盘触及涨停，需关注板块扩散。")
    if row["is_limit_down"]:
        tags.append("limit_down")
        bullets.append("收盘触及跌停，需关注风险扩散。")

    score = _stock_anomaly_score(change_pct, amount_ratio, tags)
    return {
        **row,
        "anomaly_tags": tags,
        "explanation_bullets": bullets,
        "anomaly_score": score,
    }


def _rank_industries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["industry_id"]].append(row)

    industries = []
    for industry_id, items in grouped.items():
        amount = sum(item["amount"] or 0.0 for item in items)
        weighted_change = sum((item["change_pct"] or 0.0) * (item["amount"] or 0.0) for item in items)
        change_pct = weighted_change / amount if amount > 0 else 0.0
        up_count = sum(1 for item in items if (item["change_pct"] or 0.0) > 0.001)
        down_count = sum(1 for item in items if (item["change_pct"] or 0.0) < -0.001)
        volume_spike_count = sum(1 for item in items if "volume_spike" in item["anomaly_tags"])
        strong_move_count = sum(
            1 for item in items if "strong_up" in item["anomaly_tags"] or "strong_down" in item["anomaly_tags"]
        )
        breadth_imbalance = abs(up_count - down_count) / max(len(items), 1)
        score = (
            abs(change_pct) * 100
            + min(amount / 10000000000, 5)
            + volume_spike_count * 1.5
            + strong_move_count * 1.2
            + breadth_imbalance
        )
        industries.append(
            {
                "industry_id": industry_id,
                "industry_name": items[0]["industry_name"],
                "change_pct": change_pct,
                "amount": amount,
                "stock_count": len(items),
                "up_count": up_count,
                "down_count": down_count,
                "volume_spike_count": volume_spike_count,
                "strong_move_count": strong_move_count,
                "anomaly_score": round(score, 4),
                "explanation_bullets": _industry_bullets(
                    items[0]["industry_name"],
                    change_pct,
                    amount,
                    volume_spike_count,
                    strong_move_count,
                    up_count,
                    down_count,
                ),
            }
        )

    return sorted(industries, key=lambda item: (-item["anomaly_score"], item["industry_id"]))


def _industry_bullets(
    industry_name: str,
    change_pct: float | None,
    amount: float,
    volume_spike_count: int,
    strong_move_count: int,
    up_count: int,
    down_count: int,
) -> list[str]:
    bullets = [f"{industry_name}成交额约 {amount / 100000000:.1f} 亿。"]
    if change_pct is not None:
        bullets.append(f"板块加权涨跌幅 {change_pct:.2%}。")
    if volume_spike_count:
        bullets.append(f"{volume_spike_count} 只成分股出现放量信号。")
    if strong_move_count:
        bullets.append(f"{strong_move_count} 只成分股出现大幅涨跌。")
    if up_count != down_count:
        direction = "上涨扩散" if up_count > down_count else "下跌扩散"
        bullets.append(f"{direction}：上涨 {up_count} / 下跌 {down_count}。")
    return bullets


def _stock_anomaly_score(change_pct: float | None, amount_ratio: float | None, tags: list[str]) -> float:
    score = abs(change_pct or 0.0) * 100
    if amount_ratio is not None:
        score += min(amount_ratio, 5)
    score += len(tags)
    return round(score, 4)


def _summary_read_model(summary: Any) -> dict[str, int]:
    raw = summary if isinstance(summary, dict) else {}
    return {
        "hot_industry_count": int(raw.get("hot_industry_count") or 0),
        "hot_stock_count": int(raw.get("hot_stock_count") or 0),
        "volume_spike_count": int(raw.get("volume_spike_count") or 0),
        "strong_move_count": int(raw.get("strong_move_count") or 0),
    }


def _industry_read_model(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "industry_id": str(item.get("industry_id") or ""),
        "industry_name": str(item.get("industry_name") or ""),
        "change_pct": _number(item.get("change_pct")),
        "amount": _number(item.get("amount")),
        "stock_count": int(item.get("stock_count") or 0),
        "up_count": int(item.get("up_count") or 0),
        "down_count": int(item.get("down_count") or 0),
        "volume_spike_count": int(item.get("volume_spike_count") or 0),
        "strong_move_count": int(item.get("strong_move_count") or 0),
        "anomaly_score": float(_number(item.get("anomaly_score")) or 0.0),
        "explanation_bullets": list(item.get("explanation_bullets") or []),
    }


def _stock_read_model(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": str(item.get("asset_id") or ""),
        "symbol": str(item.get("symbol") or ""),
        "name": str(item.get("name") or ""),
        "industry_id": str(item.get("industry_id") or ""),
        "industry_name": str(item.get("industry_name") or ""),
        "change_pct": _number(item.get("change_pct")),
        "amount": _number(item.get("amount")),
        "amount_ratio_20d": _number(item.get("amount_ratio_20d")),
        "turnover_rate": _number(item.get("turnover_rate")),
        "anomaly_tags": list(item.get("anomaly_tags") or []),
        "explanation_bullets": list(item.get("explanation_bullets") or []),
    }


def _empty_summary() -> dict[str, int]:
    return {
        "hot_industry_count": 0,
        "hot_stock_count": 0,
        "volume_spike_count": 0,
        "strong_move_count": 0,
    }


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
