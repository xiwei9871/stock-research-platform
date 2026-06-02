from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.schemas import AssetSummary, ScoreRow
from stock_research.db import connect, fetch_all


def search_assets(
    query: str,
    limit: int = 20,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    term = f"%{query.strip()}%"
    sql = """
    SELECT asset_id, symbol, name, exchange, board, is_active
    FROM core.asset_master
    WHERE asset_id ILIKE %s
       OR symbol ILIKE %s
       OR name ILIKE %s
    ORDER BY is_active DESC, asset_id
    LIMIT %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [term, term, term, limit])
    return [
        AssetSummary(
            asset_id=str(row["asset_id"]),
            symbol=str(row["symbol"]),
            name=str(row["name"]),
            exchange=str(row["exchange"]),
            board=row.get("board"),
            is_active=bool(row["is_active"]),
        ).to_dict()
        for row in rows
    ]


def load_asset_detail(
    asset_id: str,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    sql = """
    SELECT asset_id, symbol, name, exchange, board, is_active
    FROM core.asset_master
    WHERE asset_id = %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [asset_id])
    if not rows:
        return None
    row = rows[0]
    return AssetSummary(
        asset_id=str(row["asset_id"]),
        symbol=str(row["symbol"]),
        name=str(row["name"]),
        exchange=str(row["exchange"]),
        board=row.get("board"),
        is_active=bool(row["is_active"]),
    ).to_dict()


def load_top_scores_for_dashboard(
    trade_date: str,
    score_version: str,
    top_n: int,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    sql = """
    SELECT trade_date, asset_id, rank, score_total, score_version, score_components
    FROM factor.stock_score_daily
    WHERE trade_date = %s
      AND score_version = %s
    ORDER BY rank, asset_id
    LIMIT %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [trade_date, score_version, top_n])
    return [_score_row(row).to_dict() for row in rows]


def load_asset_score_for_dashboard(
    asset_id: str,
    trade_date: str,
    score_version: str,
    service: str = SETTINGS.research_service,
) -> dict[str, Any] | None:
    sql = """
    SELECT trade_date, asset_id, rank, score_total, score_version, score_components
    FROM factor.stock_score_daily
    WHERE asset_id = %s
      AND trade_date = %s
      AND score_version = %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [asset_id, trade_date, score_version])
    if not rows:
        return None
    return _score_row(rows[0]).to_dict()


def _score_row(row: dict[str, Any]) -> ScoreRow:
    return ScoreRow(
        trade_date=str(row["trade_date"]),
        asset_id=str(row["asset_id"]),
        rank=int(row["rank"]),
        score_total=float(row["score_total"]),
        score_version=str(row["score_version"]),
        score_components=dict(row.get("score_components") or {}),
    )
