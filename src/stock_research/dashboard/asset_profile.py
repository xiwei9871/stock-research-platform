from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.bars import load_daily_bars, normalize_market_asset_id
from stock_research.dashboard.decisions import load_asset_decision_history
from stock_research.dashboard.outcomes import load_asset_outcome_history
from stock_research.dashboard.scores import (
    load_asset_detail,
    load_asset_score_for_dashboard,
)
from stock_research.dashboard.watchlist import (
    load_asset_watchlist_signals_for_dashboard,
)
from stock_research.db import connect, fetch_all


def build_asset_profile(
    asset_id: str,
    trade_date: str,
    start_date: str,
    end_date: str,
    score_version: str = "manual_v1",
    adjust_type: str = "qfq",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    canonical_asset_id = normalize_market_asset_id(asset_id)
    share_snapshot = _load_share_snapshot(canonical_asset_id, end_date, service=service)
    spot_snapshot = _load_spot_snapshot(canonical_asset_id, asset_id, end_date, service=service)
    factor_valuation = _load_factor_valuation(canonical_asset_id, end_date, service=service)
    quote_snapshot = _load_quote_snapshot(
        canonical_asset_id,
        asset_id,
        end_date,
        adjust_type,
        share_snapshot=share_snapshot,
        service=service,
    )

    return {
        "asset_id": asset_id,
        "canonical_asset_id": canonical_asset_id,
        "asset": load_asset_detail(
            canonical_asset_id,
            service=service,
        )
        or load_asset_detail(asset_id, service=service),
        "quote_snapshot": quote_snapshot,
        "company_profile": _load_company_profile(
            canonical_asset_id,
            service=service,
        ),
        "valuation_snapshot": _load_valuation_snapshot(
            quote_snapshot=quote_snapshot,
            share_snapshot=share_snapshot,
            spot_snapshot=spot_snapshot,
            factor_valuation=factor_valuation,
        ),
        "bars": load_daily_bars(
            asset_id,
            start_date,
            end_date,
            adjust_type,
            service=service,
        ),
        "score": load_asset_score_for_dashboard(
            canonical_asset_id,
            trade_date,
            score_version,
            service=service,
        ),
        "signals": load_asset_watchlist_signals_for_dashboard(
            canonical_asset_id,
            trade_date,
            service=service,
        ),
        "decisions": load_asset_decision_history(
            canonical_asset_id,
            start_date,
            end_date,
            50,
            service=service,
        ),
        "outcomes": load_asset_outcome_history(
            canonical_asset_id,
            start_date,
            end_date,
            None,
            50,
            service=service,
        ),
        "factor_values": _load_factor_values(
            canonical_asset_id,
            trade_date,
            service=service,
        ),
        "coverage": _load_data_coverage(canonical_asset_id, service=service),
    }


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_date_text(value: Any) -> str | None:
    return str(value)[:10] if value else None


def _normalise_quote_amount(row: dict[str, Any]) -> float | None:
    amount = _to_float(row.get("amount"))
    if amount is None:
        return None
    close = _to_float(row.get("close"))
    volume = _to_float(row.get("volume"))
    if close is None or volume is None or close <= 0 or volume <= 0 or amount <= 0:
        return amount
    theoretical_amount_yuan = close * volume * 100
    ratio = theoretical_amount_yuan / amount
    if 100 <= ratio <= 10000:
        return amount * 1000
    return amount


def _derive_turnover_rate(row: dict[str, Any], share_snapshot: dict[str, Any] | None) -> float | None:
    turnover_rate = _to_float(row.get("turnover_rate"))
    if turnover_rate is not None and turnover_rate > 0:
        return turnover_rate
    float_share = _to_float((share_snapshot or {}).get("float_share"))
    volume = _to_float(row.get("volume"))
    if float_share is None or float_share <= 0 or volume is None or volume <= 0:
        return None
    return volume * 100 / float_share * 100


def _ts_code_candidates(asset_id: str, fallback_asset_id: str | None = None) -> list[str]:
    candidates: list[str] = []
    for value in [asset_id, fallback_asset_id]:
        text = str(value or "").strip().upper()
        if not text:
            continue
        if text.startswith("CN:"):
            parts = text.split(":")
            if len(parts) == 3:
                text = f"{parts[2]}.{parts[1]}"
        if "." in text and text not in candidates:
            candidates.append(text)
    return candidates


def _load_quote_snapshot(
    asset_id: str,
    fallback_asset_id: str | None,
    end_date: str,
    adjust_type: str = "qfq",
    share_snapshot: dict[str, Any] | None = None,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    asset_ids = [asset_id]
    if fallback_asset_id and fallback_asset_id not in asset_ids:
        asset_ids.append(fallback_asset_id)
    sql = """
    SELECT trade_date::text AS trade_date,
           open,
           high,
           low,
           close,
           preclose,
           volume,
           amount,
           turnover_rate,
           pct_chg
    FROM market_daily_bar
    WHERE asset_id = %s
      AND trade_date <= %s
      AND adjust_type = %s
    ORDER BY trade_date DESC
    LIMIT 20
    """
    rows: list[dict[str, Any]] = []
    with connect(service) as conn:
        for candidate_asset_id in asset_ids:
            rows = fetch_all(conn, sql, [candidate_asset_id, end_date, adjust_type])
            if rows:
                break

    if not rows:
        missing_fields = [
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "preclose",
            "volume",
            "amount",
            "turnover_rate",
            "pct_chg",
            "amount_ratio_20d",
        ]
        return {
            "trade_date": None,
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "preclose": None,
            "volume": None,
            "amount": None,
            "turnover_rate": None,
            "pct_chg": None,
            "amount_ratio_20d": None,
            "data_status": "missing",
            "missing_fields": missing_fields,
        }

    latest = dict(rows[0])
    amounts = [_normalise_quote_amount(dict(row)) for row in rows]
    latest_amount = _to_float(latest.get("amount"))
    normalised_latest_amount = _normalise_quote_amount(latest)
    positive_amounts = [value for value in amounts if value is not None and value > 0]
    comparable_amounts = (
        [
            value
            for value in positive_amounts
            if normalised_latest_amount is not None and normalised_latest_amount / 10 <= value <= normalised_latest_amount * 10
        ]
        if normalised_latest_amount is not None and normalised_latest_amount > 0
        else positive_amounts
    )
    average_amount = sum(comparable_amounts) / len(comparable_amounts) if comparable_amounts else None
    amount_ratio_20d = normalised_latest_amount / average_amount if normalised_latest_amount is not None and average_amount else None
    snapshot = {
        "trade_date": _to_date_text(latest.get("trade_date")),
        "open": _to_float(latest.get("open")),
        "high": _to_float(latest.get("high")),
        "low": _to_float(latest.get("low")),
        "close": _to_float(latest.get("close")),
        "preclose": _to_float(latest.get("preclose")),
        "volume": _to_float(latest.get("volume")),
        "amount": normalised_latest_amount,
        "turnover_rate": _derive_turnover_rate(latest, share_snapshot),
        "pct_chg": _to_float(latest.get("pct_chg")),
        "amount_ratio_20d": amount_ratio_20d,
    }
    missing_fields = [key for key, value in snapshot.items() if key != "trade_date" and value is None]
    if snapshot["trade_date"] is None:
        missing_fields.append("trade_date")
    return {
        **snapshot,
        "data_status": "available" if not missing_fields else "partial",
        "missing_fields": missing_fields,
    }


def _load_share_snapshot(
    asset_id: str,
    end_date: str,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    sql = """
    SELECT total_share,
           float_share,
           event_date::text AS event_date
    FROM finance.share_capital_event
    WHERE asset_id = %s
      AND event_date <= %s
      AND (announcement_date IS NULL OR announcement_date <= %s)
    ORDER BY event_date DESC
    LIMIT 1
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [asset_id, end_date, end_date])
    return dict(rows[0]) if rows else None


def _load_spot_snapshot(
    asset_id: str,
    fallback_asset_id: str | None,
    end_date: str,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    ts_codes = _ts_code_candidates(asset_id, fallback_asset_id)
    if not ts_codes:
        return None
    sql = """
    SELECT trade_date::text AS trade_date,
           volume_ratio,
           NULLIF(turnover_rate, 0) AS turnover_rate,
           NULLIF(payload->>'总市值', '')::numeric AS total_market_cap,
           NULLIF(payload->>'流通市值', '')::numeric AS float_market_cap,
           NULLIF(payload->>'市盈率-动态', '')::numeric AS pe_ttm,
           NULLIF(payload->>'市净率', '')::numeric AS pb
    FROM staging.eastmoney_stock_spot_snapshot
    WHERE ts_code = ANY(%s)
      AND trade_date <= %s
    ORDER BY trade_date DESC, target_time DESC
    LIMIT 1
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [ts_codes, end_date])
    return dict(rows[0]) if rows else None


def _load_factor_valuation(
    asset_id: str,
    end_date: str,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    sql = """
    SELECT DISTINCT ON (factor_name)
           factor_name,
           factor_value
    FROM factor.factor_daily
    WHERE asset_id = %s
      AND trade_date <= %s
      AND factor_name IN ('market_cap', 'float_market_cap', 'pe_ttm', 'pb', 'volume_ratio_5_20')
    ORDER BY factor_name, trade_date DESC
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [asset_id, end_date])
    return {str(row.get("factor_name")): _to_float(row.get("factor_value")) for row in rows}


def _load_company_profile(
    asset_id: str,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    sql = """
    SELECT asset_id,
           ts_code,
           symbol,
           name,
           exchange,
           board,
           list_date::text AS list_date,
           is_active,
           is_beijing,
           is_star,
           is_chinext,
           region,
           source
    FROM core.asset_master
    WHERE asset_id = %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [asset_id])
    if not rows:
        return None
    row = dict(rows[0])
    return {
        "asset_id": row.get("asset_id"),
        "ts_code": row.get("ts_code"),
        "symbol": row.get("symbol"),
        "name": row.get("name"),
        "exchange": row.get("exchange"),
        "board": row.get("board"),
        "list_date": _to_date_text(row.get("list_date")),
        "is_active": row.get("is_active"),
        "is_beijing": row.get("is_beijing"),
        "is_star": row.get("is_star"),
        "is_chinext": row.get("is_chinext"),
        "region": row.get("region"),
        "source": "core.asset_master",
    }


def _load_valuation_snapshot(
    *,
    quote_snapshot: dict[str, Any],
    share_snapshot: dict[str, Any] | None,
    spot_snapshot: dict[str, Any] | None,
    factor_valuation: dict[str, Any],
) -> dict[str, Any]:
    close = _to_float(quote_snapshot.get("close"))
    total_share = _to_float((share_snapshot or {}).get("total_share"))
    float_share = _to_float((share_snapshot or {}).get("float_share"))
    total_market_cap = close * total_share if close is not None and total_share is not None else None
    float_market_cap = close * float_share if close is not None and float_share is not None else None
    values = {
        "total_market_cap": total_market_cap
        or _to_float((spot_snapshot or {}).get("total_market_cap"))
        or factor_valuation.get("market_cap"),
        "float_market_cap": float_market_cap
        or _to_float((spot_snapshot or {}).get("float_market_cap"))
        or factor_valuation.get("float_market_cap"),
        "pe_ttm": _to_float((spot_snapshot or {}).get("pe_ttm")) or factor_valuation.get("pe_ttm"),
        "pb": _to_float((spot_snapshot or {}).get("pb")) or factor_valuation.get("pb"),
        "volume_ratio": _to_float((spot_snapshot or {}).get("volume_ratio"))
        or factor_valuation.get("volume_ratio_5_20"),
    }
    missing_fields = [key for key, value in values.items() if value is None]
    data_status = "available" if not missing_fields else "partial" if len(missing_fields) < len(values) else "unavailable"
    return {
        **values,
        "data_status": data_status,
        "missing_fields": missing_fields,
    }


def _load_factor_values(
    asset_id: str,
    trade_date: str,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    sql = """
    SELECT factor_name,
           factor_group,
           factor_value,
           calc_version,
           source,
           source_data_version
    FROM factor.factor_daily
    WHERE asset_id = %s
      AND trade_date = %s
    ORDER BY factor_group, factor_name
    """
    with connect(service) as conn:
        return fetch_all(conn, sql, [asset_id, trade_date])


def _load_data_coverage(
    asset_id: str,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    daily_bar_sql = """
    SELECT min(trade_date)::text AS min_date,
           max(trade_date)::text AS max_date,
           count(*) AS row_count
    FROM market_daily_bar
    WHERE asset_id = %s
      AND adjust_type = 'qfq'
    """
    factor_sql = """
    SELECT max(trade_date)::text AS latest_factor_date,
           count(DISTINCT factor_name) AS factor_count
    FROM factor.factor_daily
    WHERE asset_id = %s
    """
    with connect(service) as conn:
        daily_bars = fetch_all(conn, daily_bar_sql, [asset_id])
        factors = fetch_all(conn, factor_sql, [asset_id])

    return {
        "daily_bars": dict(daily_bars[0]) if daily_bars else {},
        "factors": dict(factors[0]) if factors else {},
    }
