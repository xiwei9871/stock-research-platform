from collections import defaultdict

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.technical_feature_store import (
    TECHNICAL_FEATURE_CALC_VERSION,
    TECHNICAL_FEATURE_SOURCE,
)


def run_technical_feature_gap_check(
    *,
    start_date: str,
    end_date: str,
    adjust_type: str = "qfq",
    calc_version: str = TECHNICAL_FEATURE_CALC_VERSION,
    source_data_version: str | None = None,
    service: str = SETTINGS.research_service,
) -> dict:
    resolved_source_data_version = source_data_version or f"market_daily_bar:{adjust_type}"
    with connect(service) as conn:
        market_rows = fetch_all(
            conn,
            """
            SELECT DISTINCT trade_date, asset_id
            FROM market_daily_bar
            WHERE adjust_type = %s
              AND trade_date BETWEEN %s AND %s
            ORDER BY trade_date, asset_id
            """,
            [adjust_type, start_date, end_date],
        )
        feature_rows = fetch_all(
            conn,
            """
            SELECT DISTINCT trade_date, asset_id
            FROM factor.stock_technical_features_daily
            WHERE adjust_type = %s
              AND source = %s
              AND source_data_version = %s
              AND calc_version = %s
              AND trade_date BETWEEN %s AND %s
            ORDER BY trade_date, asset_id
            """,
            [
                adjust_type,
                TECHNICAL_FEATURE_SOURCE,
                resolved_source_data_version,
                calc_version,
                start_date,
                end_date,
            ],
        )

    market_assets_by_date = _assets_by_date(market_rows)
    feature_assets_by_date = _assets_by_date(feature_rows)
    trade_dates = sorted(set(market_assets_by_date) | set(feature_assets_by_date))

    date_rows = []
    dates_with_gaps = 0
    for trade_date in trade_dates:
        market_assets = market_assets_by_date.get(trade_date, set())
        feature_assets = feature_assets_by_date.get(trade_date, set())
        missing_assets = sorted(market_assets - feature_assets)
        stale_assets = sorted(feature_assets - market_assets)
        has_gap = bool(missing_assets or stale_assets or len(market_assets) != len(feature_assets))
        if has_gap:
            dates_with_gaps += 1
        date_rows.append(
            {
                "trade_date": trade_date,
                "market_assets": len(market_assets),
                "feature_rows": len(feature_assets),
                "missing": len(missing_assets),
                "stale": len(stale_assets),
                "missing_assets": missing_assets,
                "stale_assets": stale_assets,
                "has_gap": has_gap,
            }
        )

    return {
        "start_date": start_date,
        "end_date": end_date,
        "adjust_type": adjust_type,
        "calc_version": calc_version,
        "source_data_version": resolved_source_data_version,
        "dates": date_rows,
        "summary": {
            "dates": len(trade_dates),
            "dates_with_gaps": dates_with_gaps,
        },
    }


def _assets_by_date(rows: list[dict]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        trade_date = str(row["trade_date"])[:10]
        asset_id = str(row["asset_id"])
        result[trade_date].add(asset_id)
    return dict(result)
