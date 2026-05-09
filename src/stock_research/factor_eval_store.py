import json
from typing import Any

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


def load_multi_horizon_factor_eval_inputs(
    factor_name: str,
    start_date: str,
    end_date: str,
    horizons: list[int],
    calc_version: str = "v1",
    label_set: str = "forward_return",
    label_version: str = "v1",
    service: str = SETTINGS.research_service,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not horizons:
        raise ValueError("horizons must not be empty")

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
        horizon,
        label_value AS forward_return
    FROM label_snapshot
    WHERE label_set = %s
      AND label_version = %s
      AND horizon = ANY(%s)
      AND label_name IN ('forward_return', 'future_return')
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date, asset_id, horizon
    """
    with connect(service) as conn:
        factor_rows = fetch_all(conn, factor_sql, [factor_name, calc_version, start_date, end_date])
        return_rows = fetch_all(
            conn,
            return_sql,
            [label_set, label_version, horizons, start_date, end_date],
        )

    returns_long = pd.DataFrame(return_rows)
    if returns_long.empty:
        columns = ["trade_date", "asset_id", *[f"forward_return_{horizon}d" for horizon in horizons]]
        return pd.DataFrame(factor_rows), pd.DataFrame(columns=columns)

    returns = (
        returns_long.pivot_table(
            index=["trade_date", "asset_id"],
            columns="horizon",
            values="forward_return",
            aggfunc="last",
        )
        .reset_index()
        .rename(columns={horizon: f"forward_return_{int(horizon)}d" for horizon in horizons})
        .sort_values(["trade_date", "asset_id"])
        .reset_index(drop=True)
    )
    return pd.DataFrame(factor_rows), returns


def store_factor_eval_run(
    run_id: str,
    factor_name: str,
    calc_version: str,
    start_date: str,
    end_date: str,
    horizons: list[int],
    primary_horizon: int,
    status: str,
    reason: str,
    metrics: dict[str, Any],
    service: str = SETTINGS.research_service,
) -> None:
    sql = """
    INSERT INTO factor.factor_eval_run (
        run_id, factor_name, calc_version, start_date, end_date, horizons,
        primary_horizon, status, reason, metrics
    )
    VALUES (
        %(run_id)s, %(factor_name)s, %(calc_version)s, %(start_date)s, %(end_date)s,
        %(horizons)s, %(primary_horizon)s, %(status)s, %(reason)s, %(metrics)s::jsonb
    )
    ON CONFLICT (run_id) DO UPDATE SET
        status = EXCLUDED.status,
        reason = EXCLUDED.reason,
        metrics = EXCLUDED.metrics
    """
    params = {
        "run_id": run_id,
        "factor_name": factor_name,
        "calc_version": calc_version,
        "start_date": start_date,
        "end_date": end_date,
        "horizons": horizons,
        "primary_horizon": primary_horizon,
        "status": status,
        "reason": reason,
        "metrics": json.dumps(metrics, ensure_ascii=False),
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)


def store_factor_approval(
    factor_name: str,
    calc_version: str,
    score_version: str,
    status: str,
    reason: str,
    eval_run_id: str,
    service: str = SETTINGS.research_service,
) -> None:
    sql = """
    INSERT INTO factor.factor_approval (
        factor_name, calc_version, score_version, status, reason, eval_run_id
    )
    VALUES (
        %(factor_name)s, %(calc_version)s, %(score_version)s, %(status)s,
        %(reason)s, %(eval_run_id)s
    )
    ON CONFLICT (factor_name, calc_version, score_version)
    DO UPDATE SET
        status = EXCLUDED.status,
        reason = EXCLUDED.reason,
        eval_run_id = EXCLUDED.eval_run_id,
        approved_at = now()
    """
    params = {
        "factor_name": factor_name,
        "calc_version": calc_version,
        "score_version": score_version,
        "status": status,
        "reason": reason,
        "eval_run_id": eval_run_id,
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
