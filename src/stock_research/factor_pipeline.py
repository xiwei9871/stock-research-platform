import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def load_market_bars_for_factor_date(
    trade_date: str,
    lookback_bars: int = 130,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    WITH ranked AS (
        SELECT
            trade_date,
            asset_id,
            open,
            high,
            low,
            close,
            preclose,
            volume,
            amount,
            turnover_rate,
            trade_status,
            is_st,
            row_number() over (partition by asset_id order by trade_date desc) AS row_num
        FROM market_daily_bar
        WHERE trade_date <= %s
          AND adjust_type = %s
    )
    SELECT
        trade_date,
        asset_id,
        open,
        high,
        low,
        close,
        preclose,
        volume,
        amount,
        turnover_rate,
        trade_status,
        is_st
    FROM ranked
    WHERE row_num <= %s
    ORDER BY asset_id, trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [trade_date, adjust_type, lookback_bars])
    return pd.DataFrame(rows)
