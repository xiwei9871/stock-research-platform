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

    return {
        "asset_id": asset_id,
        "canonical_asset_id": canonical_asset_id,
        "asset": load_asset_detail(
            canonical_asset_id,
            service=service,
        )
        or load_asset_detail(asset_id, service=service),
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
