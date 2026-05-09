import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def load_factor_eval_inputs(
    factor_name: str,
    start_date: str,
    end_date: str,
    horizon: int,
    calc_version: str = "v1",
    label_set: str = "forward_return",
    label_version: str = "v1",
    service: str = SETTINGS.research_service,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    factor_sql = """
    SELECT trade_date, asset_id, factor_value
    FROM factor.factor_daily
    WHERE factor_name = %s
      AND calc_version = %s
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date, asset_id
    """
    return_sql = """
    SELECT
        trade_date,
        asset_id,
        label_value AS forward_return
    FROM label_snapshot
    WHERE label_set = %s
      AND label_version = %s
      AND horizon = %s
      AND label_name IN ('forward_return', 'future_return')
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date, asset_id
    """
    return_col = f"forward_return_{horizon}d"
    with connect(service) as conn:
        factor_rows = fetch_all(conn, factor_sql, [factor_name, calc_version, start_date, end_date])
        return_rows = fetch_all(
            conn,
            return_sql,
            [label_set, label_version, horizon, start_date, end_date],
        )
    returns = pd.DataFrame(return_rows)
    if not returns.empty:
        returns = returns.rename(columns={"forward_return": return_col})
    return pd.DataFrame(factor_rows), returns
