from datetime import date, datetime
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


FEATURE_SET = "p0_daily"
FEATURE_VERSION = "v1"
SOURCE_DATA_VERSION = "market_daily_bar:hfq"

FEATURE_NAMES = [
    "ret_5d",
    "ret_20d",
    "ret_60d",
    "amount_20d_avg",
    "turnover_20d_avg",
    "volatility_20d",
    "ma20_deviation",
    "max_drawdown_20d",
]


def max_drawdown(series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return None

    rolling_max = clean.cummax()
    drawdown = clean / rolling_max - 1.0
    value = drawdown.min()
    if pd.isna(value):
        return None
    return float(value)


def _trade_date_string(value: Any) -> str:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def compute_p0_features_for_asset(asset_id: str, bars: pd.DataFrame) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame()

    # Raw technical features only; selection/risk stages apply ST and suspension filters.
    frame = bars.sort_values("trade_date").copy()
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce")
    frame["turnover_rate"] = pd.to_numeric(frame["turnover_rate"], errors="coerce")

    close = frame["close"]
    frame["ret_5d"] = close / close.shift(5) - 1.0
    frame["ret_20d"] = close / close.shift(20) - 1.0
    frame["ret_60d"] = close / close.shift(60) - 1.0
    frame["amount_20d_avg"] = frame["amount"].rolling(20).mean()
    frame["turnover_20d_avg"] = frame["turnover_rate"].rolling(20).mean()
    frame["volatility_20d"] = close.pct_change().rolling(20).std()
    frame["ma20_deviation"] = close / close.rolling(20).mean() - 1.0
    frame["max_drawdown_20d"] = close.rolling(20).apply(max_drawdown, raw=False)

    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        trade_date = _trade_date_string(row["trade_date"])
        for feature_name in FEATURE_NAMES:
            value = row[feature_name]
            if pd.isna(value):
                continue
            rows.append(
                {
                    "asset_id": asset_id,
                    "trade_date": trade_date,
                    "feature_set": FEATURE_SET,
                    "feature_version": FEATURE_VERSION,
                    "feature_name": feature_name,
                    "feature_value": float(value),
                    "source_data_version": SOURCE_DATA_VERSION,
                }
            )

    return pd.DataFrame(rows)


def features_for_trade_date(features: pd.DataFrame, trade_date: str) -> pd.DataFrame:
    if features.empty:
        return pd.DataFrame()

    requested_date = _trade_date_string(trade_date)
    mask = features["trade_date"].map(_trade_date_string) == requested_date
    return features.loc[mask].reset_index(drop=True).copy()


def load_bars_for_features(
    trade_date: str,
    lookback_bars: int = 120,
) -> dict[str, pd.DataFrame]:
    sql = """
    WITH ranked AS (
        SELECT
            asset_id,
            trade_date,
            close,
            amount,
            turnover_rate,
            is_st,
            trade_status,
            row_number() over (partition by asset_id order by trade_date desc) AS row_num
        FROM market_daily_bar
        WHERE adjust_type = 'hfq'
          AND trade_date <= %s
    )
    SELECT asset_id, trade_date, close, amount, turnover_rate, is_st, trade_status
    FROM ranked
    WHERE row_num <= %s
    ORDER BY asset_id, trade_date
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, [trade_date, lookback_bars])

    frame = pd.DataFrame(rows)
    if frame.empty:
        return {}

    grouped = frame.groupby("asset_id", sort=False)
    return {
        asset_id: group.drop(columns=["asset_id"]).reset_index(drop=True).copy()
        for asset_id, group in grouped
    }


def upsert_feature_snapshot(features: pd.DataFrame) -> int:
    if features.empty:
        return 0

    sql = """
    INSERT INTO feature_snapshot (
        asset_id, trade_date, feature_set, feature_version, feature_name,
        feature_value, source_data_version
    )
    VALUES (
        %(asset_id)s, %(trade_date)s, %(feature_set)s, %(feature_version)s,
        %(feature_name)s, %(feature_value)s, %(source_data_version)s
    )
    ON CONFLICT (asset_id, trade_date, feature_set, feature_version, feature_name)
    DO UPDATE SET
        feature_value = EXCLUDED.feature_value,
        source_data_version = EXCLUDED.source_data_version,
        computed_at = now()
    """
    rows = features.to_dict("records")
    with connect(SETTINGS.research_service) as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
    return len(rows)


def compute_and_store_p0_features(trade_date: str) -> int:
    total = 0
    for asset_id, bars in load_bars_for_features(trade_date).items():
        features = features_for_trade_date(
            compute_p0_features_for_asset(asset_id, bars),
            trade_date,
        )
        total += upsert_feature_snapshot(features)
    return total
