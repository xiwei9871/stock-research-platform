import json
from datetime import date, datetime
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.factor_config import manual_v1_config
from stock_research.scoring.pipeline import score_factor_daily
from stock_research.services.universe_service import (
    UniverseResult,
    filter_dataframe_by_universe,
)


FACTOR_COLUMNS = [
    "trade_date",
    "asset_id",
    "factor_name",
    "factor_group",
    "factor_value",
    "calc_version",
    "source",
    "source_data_version",
]

SCORE_COLUMNS = [
    "trade_date",
    "asset_id",
    "rank",
    "score_total",
    "score_version",
    "score_components",
    "calc_version",
    "source_data_version",
]


def upsert_factor_daily(
    factors: pd.DataFrame,
    service: str = SETTINGS.research_service,
) -> int:
    if factors.empty:
        return 0

    rows = [_factor_row(row) for row in factors.to_dict("records")]
    create_temp_sql = """
    CREATE TEMP TABLE tmp_factor_daily (
        trade_date date,
        asset_id text,
        factor_name text,
        factor_group text,
        factor_value double precision,
        calc_version text,
        source text,
        source_data_version text
    ) ON COMMIT DROP
    """
    copy_sql = """
    COPY tmp_factor_daily (
        trade_date, asset_id, factor_name, factor_group, factor_value,
        calc_version, source, source_data_version
    ) FROM STDIN
    """
    upsert_sql = """
    INSERT INTO factor.factor_daily (
        trade_date, asset_id, factor_name, factor_group, factor_value,
        calc_version, source, source_data_version
    )
    SELECT
        trade_date, asset_id, factor_name, factor_group, factor_value,
        calc_version, source, source_data_version
    FROM tmp_factor_daily
    ON CONFLICT (trade_date, asset_id, factor_name, calc_version)
    DO UPDATE SET
        factor_group = EXCLUDED.factor_group,
        factor_value = EXCLUDED.factor_value,
        source = EXCLUDED.source,
        source_data_version = EXCLUDED.source_data_version,
        computed_at = now()
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(create_temp_sql)
            with cur.copy(copy_sql) as copy:
                for row in rows:
                    copy.write_row([row[column] for column in FACTOR_COLUMNS])
            cur.execute(upsert_sql)
    return len(rows)


def upsert_stock_score_daily(
    scores: pd.DataFrame,
    calc_version: str = "v1",
    source_data_version: str = "factor_daily",
    service: str = SETTINGS.research_service,
) -> int:
    if scores.empty:
        return 0

    rows = [
        _score_row(row, calc_version=calc_version, source_data_version=source_data_version)
        for row in scores.to_dict("records")
    ]
    sql = """
    INSERT INTO factor.stock_score_daily (
        trade_date, asset_id, rank, score_total, score_version,
        score_components, calc_version, source_data_version
    )
    VALUES (
        %(trade_date)s, %(asset_id)s, %(rank)s, %(score_total)s,
        %(score_version)s, %(score_components)s::jsonb,
        %(calc_version)s, %(source_data_version)s
    )
    ON CONFLICT (trade_date, asset_id, score_version)
    DO UPDATE SET
        rank = EXCLUDED.rank,
        score_total = EXCLUDED.score_total,
        score_components = EXCLUDED.score_components,
        calc_version = EXCLUDED.calc_version,
        source_data_version = EXCLUDED.source_data_version,
        computed_at = now()
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
    return len(rows)


def load_top_scores(
    trade_date: object,
    score_version: str,
    top_n: int,
    universe_result: UniverseResult | None = None,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    params: list[object] = [_date_string(trade_date), score_version]
    limit_sql = "LIMIT %s"
    if universe_result is None:
        params.append(top_n)
    else:
        limit_sql = ""
    sql = f"""
    SELECT
        trade_date,
        asset_id,
        rank,
        score_total,
        score_version,
        score_components
    FROM factor.stock_score_daily
    WHERE trade_date = %s
      AND score_version = %s
    ORDER BY rank, asset_id
    {limit_sql}
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    frame = filter_dataframe_by_universe(
        pd.DataFrame(rows),
        universe_result,
        asset_id_col="asset_id",
    )
    if universe_result is not None:
        frame = frame.head(top_n).reset_index(drop=True)
    return frame.to_dict("records")


def load_factor_daily(
    trade_date: object,
    calc_version: str = "v1",
    approved_only: bool = False,
    score_version: str | None = None,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    if approved_only and not score_version:
        raise ValueError("score_version is required when approved_only=True")

    if approved_only:
        sql = """
        SELECT
            daily.trade_date,
            daily.asset_id,
            daily.factor_name,
            daily.factor_group,
            daily.factor_value,
            daily.calc_version,
            daily.source,
            daily.source_data_version
        FROM factor.factor_daily daily
        JOIN factor.factor_approval approval
          ON approval.factor_name = daily.factor_name
         AND approval.calc_version = daily.calc_version
        WHERE daily.trade_date = %s
          AND daily.calc_version = %s
          AND approval.score_version = %s
          AND approval.status = 'approved'
        ORDER BY daily.asset_id, daily.factor_name
        """
        params = [_date_string(trade_date), calc_version, score_version]
    else:
        sql = """
        SELECT
            trade_date,
            asset_id,
            factor_name,
            factor_group,
            factor_value,
            calc_version,
            source,
            source_data_version
        FROM factor.factor_daily
        WHERE trade_date = %s
          AND calc_version = %s
        ORDER BY asset_id, factor_name
        """
        params = [_date_string(trade_date), calc_version]
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return pd.DataFrame(rows)


def score_and_store_factor_daily(
    factor_daily: pd.DataFrame,
    factor_directions: dict[str, str],
    weights: dict[str, float],
    score_version: str,
    calc_version: str = "v1",
    service: str = SETTINGS.research_service,
) -> int:
    if factor_daily.empty:
        return 0

    scores = score_factor_daily(
        factor_daily,
        factor_directions=factor_directions,
        weights=weights,
        score_version=score_version,
    )
    score_columns = [column for column in weights if column in scores.columns]
    scores = scores.copy()
    scores["score_components"] = scores[score_columns].to_dict("records")
    return upsert_stock_score_daily(
        scores,
        calc_version=calc_version,
        source_data_version=f"factor_daily:{score_version}",
        service=service,
    )


def score_stored_factor_daily(
    trade_date: object,
    score_version: str = "manual_v1",
    calc_version: str = "v1",
    approved_only: bool = False,
    service: str = SETTINGS.research_service,
) -> int:
    config = manual_v1_config()
    factors = load_factor_daily(
        trade_date=trade_date,
        calc_version=calc_version,
        approved_only=approved_only,
        score_version=score_version,
        service=service,
    )
    return score_and_store_factor_daily(
        factors,
        factor_directions=config["factor_directions"],
        weights=config["weights"],
        score_version=score_version,
        calc_version=calc_version,
        service=service,
    )


def _factor_row(row: dict[str, Any]) -> dict[str, Any]:
    result = {column: row.get(column) for column in FACTOR_COLUMNS}
    result["trade_date"] = _date_string(result["trade_date"])
    result["asset_id"] = str(result["asset_id"])
    result["factor_name"] = str(result["factor_name"])
    result["factor_group"] = str(result["factor_group"])
    result["factor_value"] = _optional_float(result["factor_value"])
    result["calc_version"] = str(result["calc_version"])
    result["source"] = str(result["source"])
    result["source_data_version"] = str(result["source_data_version"])
    return result


def _score_row(
    row: dict[str, Any],
    calc_version: str,
    source_data_version: str,
) -> dict[str, Any]:
    result = {column: row.get(column) for column in SCORE_COLUMNS}
    result["trade_date"] = _date_string(result["trade_date"])
    result["asset_id"] = str(result["asset_id"])
    result["rank"] = int(result["rank"])
    result["score_total"] = float(result["score_total"])
    result["score_version"] = str(result["score_version"])
    result["score_components"] = json.dumps(
        _jsonable(result.get("score_components") or {}),
        ensure_ascii=False,
    )
    result["calc_version"] = str(row.get("calc_version") or calc_version)
    result["source_data_version"] = str(row.get("source_data_version") or source_data_version)
    return result


def _date_string(value: object) -> str:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _optional_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)
