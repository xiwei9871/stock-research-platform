from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all

DEFAULT_INDUSTRY_SYSTEM = "csrc"


def build_stock_market_context_heatmap(
    asset_id: str,
    trade_date: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    rows = load_peer_heatmap_rows(asset_id, trade_date, service=service)
    if not rows:
        return _missing_payload(asset_id, trade_date, ["peer heatmap rows are unavailable"])

    normalized_rows = [_normalize_row(row) for row in rows]
    selected = _find_selected(normalized_rows, asset_id)
    selected_id = str(selected["asset_id"]) if selected else _canonical_input(asset_id)
    industry = _industry_from_rows(normalized_rows)
    peers = _rank_peers(normalized_rows, selected_id)
    selected_peer = next((peer for peer in peers if peer["is_selected"]), None)

    return {
        "asset_id": asset_id,
        "canonical_asset_id": selected_id,
        "trade_date": trade_date,
        "industry": industry,
        "selected": _selected_model(selected_peer),
        "summary": _summary(peers, selected_peer is not None),
        "peers": peers,
        "data_status": "completed" if selected_peer else "partial",
        "warnings": [] if selected_peer else ["selected stock is not present in peer daily bars"],
    }


def stock_market_context_heatmap_read_model(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": str(payload.get("asset_id") or ""),
        "canonical_asset_id": str(payload.get("canonical_asset_id") or ""),
        "trade_date": str(payload.get("trade_date") or ""),
        "industry": _industry_read_model(payload.get("industry")),
        "selected": _selected_read_model(payload.get("selected")),
        "summary": _summary_read_model(payload.get("summary")),
        "peers": [_peer_read_model(peer) for peer in payload.get("peers") or []],
        "data_status": str(payload.get("data_status") or "missing"),
        "warnings": list(payload.get("warnings") or []),
    }


def load_peer_heatmap_rows(
    asset_id: str,
    trade_date: str,
    *,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    variants = _asset_id_variants(asset_id)
    sql = """
        WITH selected_industry AS (
            SELECT
                membership.industry_code,
                membership.industry_name,
                membership.industry_system
            FROM core.industry_membership membership
            WHERE membership.asset_id = ANY(%s)
              AND membership.industry_system = %s
              AND membership.level = 1
              AND membership.start_date <= %s
              AND (membership.end_date IS NULL OR %s < membership.end_date)
            ORDER BY membership.start_date DESC
            LIMIT 1
        )
        SELECT
            bars.trade_date,
            bars.asset_id,
            COALESCE(core_asset.symbol, asset.symbol, bars.asset_id) AS symbol,
            COALESCE(core_asset.name, asset.name, bars.asset_id) AS name,
            selected_industry.industry_code AS industry_id,
            selected_industry.industry_name AS industry_name,
            selected_industry.industry_system AS industry_system,
            bars.close,
            bars.pct_chg,
            bars.amount,
            bars.source,
            bars.updated_at
        FROM selected_industry
        JOIN core.industry_membership membership
          ON membership.industry_code = selected_industry.industry_code
         AND membership.industry_system = selected_industry.industry_system
         AND membership.level = 1
         AND membership.start_date <= %s
         AND (membership.end_date IS NULL OR %s < membership.end_date)
        JOIN market_daily_bar bars
          ON bars.asset_id = membership.asset_id
         AND bars.trade_date = %s
         AND bars.adjust_type = 'qfq'
        LEFT JOIN asset_master asset
          ON asset.asset_id = bars.asset_id
        LEFT JOIN core.asset_master core_asset
          ON core_asset.asset_id = bars.asset_id
        ORDER BY bars.amount DESC NULLS LAST, bars.asset_id
    """
    params = [
        variants,
        DEFAULT_INDUSTRY_SYSTEM,
        trade_date,
        trade_date,
        trade_date,
        trade_date,
        trade_date,
    ]
    with connect(service) as conn:
        return [dict(row) for row in fetch_all(conn, sql, params)]


def _missing_payload(asset_id: str, trade_date: str, warnings: list[str]) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "canonical_asset_id": _canonical_input(asset_id),
        "trade_date": trade_date,
        "industry": None,
        "selected": None,
        "summary": _empty_summary(),
        "peers": [],
        "data_status": "missing",
        "warnings": warnings,
    }


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    amount = _number(row.get("amount")) or 0.0
    return {
        "asset_id": str(row.get("asset_id") or ""),
        "symbol": str(row.get("symbol") or row.get("asset_id") or ""),
        "name": str(row.get("name") or row.get("symbol") or row.get("asset_id") or ""),
        "price": _number(row.get("close")),
        "change_pct": _change_pct(row.get("pct_chg")),
        "amount": amount,
        "value": max(amount, 1.0),
        "industry_id": str(row.get("industry_id") or row.get("industry_code") or "UNKNOWN"),
        "industry_name": str(row.get("industry_name") or "未分组"),
        "industry_system": str(row.get("industry_system") or DEFAULT_INDUSTRY_SYSTEM),
    }


def _find_selected(rows: list[dict[str, Any]], asset_id: str) -> dict[str, Any] | None:
    variants = set(_asset_id_variants(asset_id))
    for row in rows:
        if row["asset_id"] in variants:
            return row
    input_code = _six_digit_code(asset_id)
    if input_code:
        return next((row for row in rows if _six_digit_code(row["asset_id"]) == input_code), None)
    return None


def _industry_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    first = rows[0]
    return {
        "industry_id": first["industry_id"],
        "industry_name": first["industry_name"],
        "industry_system": first["industry_system"],
    }


def _rank_peers(rows: list[dict[str, Any]], selected_id: str) -> list[dict[str, Any]]:
    amount_ranks = _rank_by(rows, "amount")
    change_ranks = _rank_by(rows, "change_pct")
    total = len(rows)
    selected_code = _six_digit_code(selected_id)
    peers = []
    for row in rows:
        is_selected = row["asset_id"] == selected_id or (
            bool(selected_code) and _six_digit_code(row["asset_id"]) == selected_code
        )
        amount_rank = amount_ranks.get(row["asset_id"])
        change_rank = change_ranks.get(row["asset_id"])
        peer = {
            "asset_id": row["asset_id"],
            "symbol": row["symbol"],
            "name": row["name"],
            "price": row["price"],
            "change_pct": row["change_pct"],
            "amount": row["amount"],
            "value": row["value"],
            "is_selected": is_selected,
            "amount_rank": amount_rank,
            "change_rank": change_rank,
            "amount_percentile": _percentile(amount_rank, total),
            "change_percentile": _percentile(change_rank, total),
        }
        peers.append(peer)
    peers.sort(key=lambda item: (not item["is_selected"], -(item["value"] or 0.0), item["asset_id"]))
    return peers


def _rank_by(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    sorted_rows = sorted(rows, key=lambda row: (_number(row.get(field)) is None, -(_number(row.get(field)) or 0.0), row["asset_id"]))
    return {row["asset_id"]: index + 1 for index, row in enumerate(sorted_rows)}


def _selected_model(peer: dict[str, Any] | None) -> dict[str, Any] | None:
    if peer is None:
        return None
    return {
        "asset_id": peer["asset_id"],
        "symbol": peer["symbol"],
        "name": peer["name"],
        "price": peer["price"],
        "change_pct": peer["change_pct"],
        "amount": peer["amount"],
        "amount_rank": peer["amount_rank"],
        "change_rank": peer["change_rank"],
        "amount_percentile": peer["amount_percentile"],
        "change_percentile": peer["change_percentile"],
    }


def _summary(peers: list[dict[str, Any]], selected_in_peer_set: bool) -> dict[str, Any]:
    up_count = flat_count = down_count = 0
    total_amount = 0.0
    for peer in peers:
        change_pct = peer.get("change_pct") or 0.0
        total_amount += peer.get("amount") or 0.0
        if change_pct > 0.001:
            up_count += 1
        elif change_pct < -0.001:
            down_count += 1
        else:
            flat_count += 1
    return {
        "peer_count": len(peers),
        "up_count": up_count,
        "flat_count": flat_count,
        "down_count": down_count,
        "total_amount": total_amount,
        "selected_in_peer_set": selected_in_peer_set,
    }


def _empty_summary() -> dict[str, Any]:
    return {
        "peer_count": 0,
        "up_count": 0,
        "flat_count": 0,
        "down_count": 0,
        "total_amount": 0.0,
        "selected_in_peer_set": False,
    }


def _industry_read_model(industry: Any) -> dict[str, Any] | None:
    if not isinstance(industry, dict):
        return None
    return {
        "industry_id": str(industry.get("industry_id") or ""),
        "industry_name": str(industry.get("industry_name") or ""),
        "industry_system": str(industry.get("industry_system") or ""),
    }


def _selected_read_model(selected: Any) -> dict[str, Any] | None:
    if not isinstance(selected, dict):
        return None
    return {
        "asset_id": str(selected.get("asset_id") or ""),
        "symbol": str(selected.get("symbol") or ""),
        "name": str(selected.get("name") or ""),
        "price": _number(selected.get("price")),
        "change_pct": _number(selected.get("change_pct")),
        "amount": _number(selected.get("amount")),
        "amount_rank": _int_or_none(selected.get("amount_rank")),
        "change_rank": _int_or_none(selected.get("change_rank")),
        "amount_percentile": _number(selected.get("amount_percentile")),
        "change_percentile": _number(selected.get("change_percentile")),
    }


def _summary_read_model(summary: Any) -> dict[str, Any]:
    if not isinstance(summary, dict):
        return _empty_summary()
    return {
        "peer_count": int(summary.get("peer_count") or 0),
        "up_count": int(summary.get("up_count") or 0),
        "flat_count": int(summary.get("flat_count") or 0),
        "down_count": int(summary.get("down_count") or 0),
        "total_amount": _number(summary.get("total_amount")) or 0.0,
        "selected_in_peer_set": bool(summary.get("selected_in_peer_set")),
    }


def _peer_read_model(peer: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": str(peer.get("asset_id") or ""),
        "symbol": str(peer.get("symbol") or ""),
        "name": str(peer.get("name") or ""),
        "price": _number(peer.get("price")),
        "change_pct": _number(peer.get("change_pct")),
        "amount": _number(peer.get("amount")),
        "value": _number(peer.get("value")),
        "is_selected": bool(peer.get("is_selected")),
    }


def _percentile(rank: int | None, total: int) -> float | None:
    if rank is None or total <= 0:
        return None
    if total == 1:
        return 1.0
    return round((total - rank) / (total - 1), 4)


def _asset_id_variants(asset_id: str) -> list[str]:
    raw = asset_id.strip()
    code = _six_digit_code(raw)
    variants = {raw}
    if code:
        if raw.endswith(".SZ") or ":SZ:" in raw:
            variants.update({f"{code}.SZ", f"CN:SZ:{code}"})
        elif raw.endswith(".SH") or ":SH:" in raw:
            variants.update({f"{code}.SH", f"CN:SH:{code}"})
        else:
            variants.update({code, f"{code}.SZ", f"{code}.SH", f"CN:SZ:{code}", f"CN:SH:{code}"})
    return sorted(variants)


def _canonical_input(asset_id: str) -> str:
    raw = asset_id.strip()
    code = _six_digit_code(raw)
    if raw.startswith("CN:"):
        return raw
    if code and (raw.endswith(".SZ") or ":SZ:" in raw):
        return f"CN:SZ:{code}"
    if code and (raw.endswith(".SH") or ":SH:" in raw):
        return f"CN:SH:{code}"
    return raw


def _six_digit_code(asset_id: str) -> str:
    digits = "".join(char for char in str(asset_id) if char.isdigit())
    return digits[:6] if len(digits) >= 6 else ""


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


def _int_or_none(value: Any) -> int | None:
    numeric = _number(value)
    return int(numeric) if numeric is not None else None
