from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def load_index_universe(
    conn,
    index_id: str,
    trade_date: str,
    source_version: str | None = None,
) -> list[dict]:
    sql = """
    SELECT
        index_id,
        asset_id,
        start_date,
        end_date,
        weight,
        source,
        source_version
    FROM market.index_constituent
    WHERE index_id = %s
      AND start_date <= %s
      AND (end_date IS NULL OR %s <= end_date)
    """
    params = [index_id, trade_date, trade_date]
    if source_version is not None:
        sql += " AND source_version = %s"
        params.append(source_version)
    sql += "\n    ORDER BY asset_id"
    return fetch_all(conn, sql, params)


def load_index_universe_for_service(
    index_id: str,
    trade_date: str,
    source_version: str | None = None,
    service: str = SETTINGS.research_service,
) -> list[dict]:
    with connect(service) as conn:
        return load_index_universe(conn, index_id, trade_date, source_version=source_version)
