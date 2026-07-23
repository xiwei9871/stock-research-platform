from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.schemas import ScoreRow
from stock_research.db import connect, fetch_all


def load_platform_summary(
    score_version: str = "manual_v1",
    top_n: int = 5,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    with connect(service) as conn:
        market = fetch_all(
            conn,
            """
            SELECT max(trade_date) AS latest_market_date,
                   count(DISTINCT asset_id) AS market_asset_count
            FROM market_daily_bar
            WHERE adjust_type = 'qfq'
              AND trade_date = (SELECT max(trade_date) FROM market_daily_bar WHERE adjust_type = 'qfq')
            """,
        )[0]
        score = fetch_all(
            conn,
            """
            SELECT max(trade_date) AS latest_score_date,
                   count(DISTINCT asset_id) AS score_asset_count
            FROM factor.stock_score_daily
            WHERE score_version = %s
              AND trade_date = (
                SELECT max(trade_date)
                FROM factor.stock_score_daily
                WHERE score_version = %s
              )
            """,
            [score_version, score_version],
        )[0]
        factors = fetch_all(
            conn,
            """
            SELECT count(DISTINCT factor_name) AS factor_count,
                   max(trade_date) AS latest_factor_date
            FROM factor.factor_daily
            WHERE trade_date = (SELECT max(trade_date) FROM factor.factor_daily)
            """,
        )[0]
        market_monitor = fetch_all(
            conn,
            """
            WITH industry_dates AS (
                SELECT trade_date
                FROM market.industry_daily_bar
                WHERE industry_system = 'csrc'
                GROUP BY trade_date
                HAVING count(*) > 0
            ),
            index_dates AS (
                SELECT trade_date
                FROM market.index_daily_bar
                GROUP BY trade_date
                HAVING count(*) > 0
            )
            SELECT max(industry_dates.trade_date) AS latest_market_monitor_date
            FROM industry_dates
            JOIN index_dates USING (trade_date)
            """,
        )[0]
        versions = fetch_all(
            conn,
            """
            SELECT DISTINCT score_version
            FROM factor.stock_score_daily
            ORDER BY score_version
            """,
        )
    latest_score_date = str(score.get("latest_score_date") or "")
    if latest_score_date:
        with connect(service) as conn:
            topn_rows = fetch_all(
                conn,
                """
                SELECT trade_date, asset_id, rank, score_total, score_version, score_components
                FROM factor.stock_score_daily
                WHERE trade_date = %s
                  AND score_version = %s
                ORDER BY rank, asset_id
                LIMIT %s
                """,
                [latest_score_date, score_version, top_n],
            )
    else:
        topn_rows = []
    latest_market_date = str(market.get("latest_market_date") or "")
    return {
        "latest_market_date": latest_market_date,
        "latest_market_monitor_date": str(
            market_monitor.get("latest_market_monitor_date") or ""
        ),
        "latest_score_date": latest_score_date,
        "latest_factor_date": str(factors.get("latest_factor_date") or ""),
        "market_asset_count": int(market.get("market_asset_count") or 0),
        "score_asset_count": int(score.get("score_asset_count") or 0),
        "factor_count": int(factors.get("factor_count") or 0),
        "score_versions": [str(row["score_version"]) for row in versions],
        "topn_preview": [_score_row(row).to_dict() for row in topn_rows],
    }


def _score_row(row: dict[str, Any]) -> ScoreRow:
    return ScoreRow(
        trade_date=str(row["trade_date"]),
        asset_id=str(row["asset_id"]),
        rank=int(row["rank"]),
        score_total=float(row["score_total"]),
        score_version=str(row["score_version"]),
        score_components=dict(row.get("score_components") or {}),
    )
