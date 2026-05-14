from datetime import date, datetime
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.technical_features import (
    TECHNICAL_FEATURE_COLUMNS,
    compute_daily_technical_features,
)


TECHNICAL_FEATURE_METADATA_COLUMNS = [
    "trade_date",
    "asset_id",
    "ts_code",
    "adjust_type",
    "source",
    "source_data_version",
    "calc_version",
]

TECHNICAL_FEATURE_TABLE_COLUMNS = [
    *TECHNICAL_FEATURE_METADATA_COLUMNS,
    *TECHNICAL_FEATURE_COLUMNS,
]

TECHNICAL_FEATURE_CALC_VERSION = "v1"
TECHNICAL_FEATURE_SOURCE = "technical_features"


def load_bars_for_technical_features(
    trade_date: str,
    lookback_bars: int = 260,
    adjust_type: str = "qfq",
    service: str = SETTINGS.research_service,
) -> dict[str, pd.DataFrame]:
    sql = """
    WITH lookback_dates AS (
        SELECT DISTINCT trade_date
        FROM market_daily_bar
        WHERE adjust_type = %s
          AND trade_date <= %s
        ORDER BY trade_date DESC
        LIMIT %s
    )
    SELECT
        bars.trade_date,
        bars.asset_id,
        bars.open,
        bars.high,
        bars.low,
        bars.close,
        bars.preclose,
        bars.volume,
        bars.amount,
        bars.turnover_rate
    FROM market_daily_bar bars
    JOIN lookback_dates dates
      ON dates.trade_date = bars.trade_date
    WHERE bars.adjust_type = %s
    ORDER BY bars.asset_id, bars.trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [adjust_type, trade_date, lookback_bars, adjust_type])

    frame = pd.DataFrame(rows)
    if frame.empty:
        return {}

    grouped = frame.groupby("asset_id", sort=False)
    return {
        str(asset_id): group.drop(columns=["asset_id"]).reset_index(drop=True).copy()
        for asset_id, group in grouped
    }


def build_stock_technical_features_daily(
    trade_date: str,
    lookback_bars: int = 260,
    adjust_type: str = "qfq",
    source_data_version: str | None = None,
) -> pd.DataFrame:
    normalized_trade_date = _date_string(trade_date)
    resolved_source_data_version = source_data_version or f"market_daily_bar:{adjust_type}"
    rows: list[dict[str, Any]] = []
    for asset_id, bars in load_bars_for_technical_features(
        normalized_trade_date,
        lookback_bars=lookback_bars,
        adjust_type=adjust_type,
    ).items():
        features = compute_daily_technical_features(bars)
        if features.empty:
            continue

        matching = features.loc[
            features["trade_date"].map(_date_string) == normalized_trade_date
        ]
        if matching.empty:
            continue

        latest = matching.iloc[-1]
        row = {
            "trade_date": normalized_trade_date,
            "asset_id": str(asset_id),
            "ts_code": str(asset_id),
            "adjust_type": str(adjust_type),
            "source": TECHNICAL_FEATURE_SOURCE,
            "source_data_version": resolved_source_data_version,
            "calc_version": TECHNICAL_FEATURE_CALC_VERSION,
        }
        for column in TECHNICAL_FEATURE_COLUMNS:
            row[column] = _optional_float(latest.get(column))
        rows.append(row)

    return pd.DataFrame(rows, columns=TECHNICAL_FEATURE_TABLE_COLUMNS)


def upsert_stock_technical_features_daily(
    features: pd.DataFrame,
    service: str = SETTINGS.research_service,
) -> int:
    if features.empty:
        return 0

    rows = [_technical_feature_row(row) for row in features.to_dict("records")]
    create_temp_sql = """
    CREATE TEMP TABLE tmp_stock_technical_features_daily (
        trade_date date,
        asset_id text,
        ts_code text,
        adjust_type text,
        source text,
        source_data_version text,
        calc_version text,
        ma5 double precision,
        ma10 double precision,
        ma20 double precision,
        ma60 double precision,
        ma120 double precision,
        ema12 double precision,
        ema26 double precision,
        macd_dif double precision,
        macd_dea double precision,
        macd_hist double precision,
        rsi6 double precision,
        rsi12 double precision,
        rsi24 double precision,
        boll_upper_20 double precision,
        boll_mid_20 double precision,
        boll_lower_20 double precision,
        atr14 double precision,
        cci14 double precision,
        kdj_k double precision,
        kdj_d double precision,
        kdj_j double precision,
        adx14 double precision,
        obv double precision,
        ret_1d double precision,
        ret_20d double precision,
        close_position_in_day double precision
    ) ON COMMIT DROP
    """
    copy_sql = """
    COPY tmp_stock_technical_features_daily (
        trade_date, asset_id, ts_code, adjust_type, source, source_data_version,
        calc_version, ma5, ma10, ma20, ma60, ma120, ema12, ema26, macd_dif,
        macd_dea, macd_hist, rsi6, rsi12, rsi24, boll_upper_20, boll_mid_20,
        boll_lower_20, atr14, cci14, kdj_k, kdj_d, kdj_j, adx14, obv, ret_1d,
        ret_20d, close_position_in_day
    ) FROM STDIN
    """
    update_columns = [
        "ts_code",
        "source",
        "source_data_version",
        *TECHNICAL_FEATURE_COLUMNS,
    ]
    assignments = ",\n        ".join(
        f"{column} = EXCLUDED.{column}" for column in update_columns
    )
    upsert_sql = f"""
    INSERT INTO factor.stock_technical_features_daily (
        trade_date, asset_id, ts_code, adjust_type, source, source_data_version,
        calc_version, ma5, ma10, ma20, ma60, ma120, ema12, ema26, macd_dif,
        macd_dea, macd_hist, rsi6, rsi12, rsi24, boll_upper_20, boll_mid_20,
        boll_lower_20, atr14, cci14, kdj_k, kdj_d, kdj_j, adx14, obv, ret_1d,
        ret_20d, close_position_in_day
    )
    SELECT
        trade_date, asset_id, ts_code, adjust_type, source, source_data_version,
        calc_version, ma5, ma10, ma20, ma60, ma120, ema12, ema26, macd_dif,
        macd_dea, macd_hist, rsi6, rsi12, rsi24, boll_upper_20, boll_mid_20,
        boll_lower_20, atr14, cci14, kdj_k, kdj_d, kdj_j, adx14, obv, ret_1d,
        ret_20d, close_position_in_day
    FROM tmp_stock_technical_features_daily
    ON CONFLICT (trade_date, asset_id, adjust_type, source_data_version, calc_version)
    DO UPDATE SET
        {assignments},
        computed_at = now(),
        updated_at = now()
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(create_temp_sql)
            with cur.copy(copy_sql) as copy:
                for row in rows:
                    copy.write_row([row[column] for column in TECHNICAL_FEATURE_TABLE_COLUMNS])
            cur.execute(upsert_sql)
    return len(rows)


def build_and_store_stock_technical_features_daily(
    trade_date: str,
    lookback_bars: int = 260,
    adjust_type: str = "qfq",
    source_data_version: str | None = None,
) -> int:
    features = build_stock_technical_features_daily(
        trade_date,
        lookback_bars=lookback_bars,
        adjust_type=adjust_type,
        source_data_version=source_data_version,
    )
    return upsert_stock_technical_features_daily(features)


def _technical_feature_row(row: dict[str, Any]) -> dict[str, Any]:
    result = {column: row.get(column) for column in TECHNICAL_FEATURE_TABLE_COLUMNS}
    result["trade_date"] = _date_string(result["trade_date"])
    result["asset_id"] = str(result["asset_id"])
    result["ts_code"] = str(result["ts_code"])
    result["adjust_type"] = str(result["adjust_type"])
    result["source"] = str(result["source"])
    result["source_data_version"] = str(result["source_data_version"])
    result["calc_version"] = str(result["calc_version"])
    for column in TECHNICAL_FEATURE_COLUMNS:
        result[column] = _optional_float(result[column])
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
