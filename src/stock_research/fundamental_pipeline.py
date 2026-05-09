import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def load_point_in_time_indicators(
    trade_date: str,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    SELECT DISTINCT ON (asset_id)
        asset_id,
        report_period,
        announcement_date,
        roe,
        roa,
        gross_margin,
        net_margin,
        debt_ratio,
        revenue_yoy,
        np_yoy,
        deduct_np_yoy,
        ocf_to_np
    FROM finance.indicator_quarter
    WHERE announcement_date <= %s
    ORDER BY asset_id, announcement_date DESC, report_period DESC
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [trade_date])
    return pd.DataFrame(rows)


def load_point_in_time_value_inputs(
    trade_date: str,
    service: str = SETTINGS.research_service,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    price_sql = """
    SELECT asset_id, trade_date, close
    FROM market_daily_bar
    WHERE trade_date = %s
      AND adjust_type = 'hfq'
    """
    finance_sql = """
    SELECT DISTINCT ON (asset_id)
        asset_id,
        np_parent AS np_parent_ttm,
        revenue AS revenue_ttm,
        total_equity AS equity_parent
    FROM finance.income_statement
    LEFT JOIN finance.balance_sheet USING (asset_id, report_period, report_type, announcement_date, source)
    WHERE announcement_date <= %s
    ORDER BY asset_id, announcement_date DESC, report_period DESC
    """
    share_sql = """
    SELECT DISTINCT ON (asset_id)
        asset_id,
        total_share,
        float_share
    FROM finance.share_capital_event
    WHERE event_date <= %s
      AND (announcement_date IS NULL OR announcement_date <= %s)
    ORDER BY asset_id, event_date DESC
    """
    with connect(service) as conn:
        prices = pd.DataFrame(fetch_all(conn, price_sql, [trade_date]))
        finance = pd.DataFrame(fetch_all(conn, finance_sql, [trade_date]))
        shares = pd.DataFrame(fetch_all(conn, share_sql, [trade_date, trade_date]))
    return prices, finance, shares
