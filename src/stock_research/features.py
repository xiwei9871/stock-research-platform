from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime
from math import ceil
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.research_windows import (
    derive_feature_window,
    load_market_date_bounds,
    load_trade_dates,
)


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
# A small number of source rows can be non-tradable or lack amount/turnover;
# the guard is for interrupted/partial jobs, not for fabricating those values.
MIN_COMPLETE_ASSET_COVERAGE_RATIO = 0.99


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
    WITH lookback_dates AS (
        SELECT DISTINCT trade_date
        FROM market_daily_bar
        WHERE adjust_type = 'hfq'
          AND trade_date <= %s
        ORDER BY trade_date DESC
        LIMIT %s
    )
    SELECT
        bars.asset_id,
        bars.trade_date,
        bars.close,
        bars.amount,
        bars.turnover_rate,
        bars.is_st,
        bars.trade_status
    FROM market_daily_bar bars
    JOIN lookback_dates dates
      ON dates.trade_date = bars.trade_date
    WHERE bars.adjust_type = 'hfq'
    ORDER BY bars.asset_id, bars.trade_date
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


def replace_feature_snapshot(trade_date: str, features: pd.DataFrame) -> int:
    """Replace the p0 snapshot for one date in a single database transaction."""
    insert_sql = """
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
    delete_sql = """
    DELETE FROM feature_snapshot
    WHERE trade_date = %s
      AND feature_set = %s
      AND feature_version = %s
    """
    rows = features.to_dict("records") if not features.empty else []
    with connect(SETTINGS.research_service) as conn:
        with conn.cursor() as cur:
            cur.execute(delete_sql, [trade_date, FEATURE_SET, FEATURE_VERSION])
            if rows:
                cur.executemany(insert_sql, rows)
    return len(rows)


def _validate_feature_snapshot_coverage(
    features: pd.DataFrame,
    *,
    trade_date: str,
    expected_asset_count: int,
) -> None:
    """Prevent a partial computation from deleting a previously good snapshot."""
    expected_minimum = ceil(
        expected_asset_count * MIN_COMPLETE_ASSET_COVERAGE_RATIO
    )
    counts = (
        features.groupby("feature_name")["asset_id"].nunique()
        if not features.empty
        else pd.Series(dtype="int64")
    )
    missing = [
        name
        for name in FEATURE_NAMES
        if int(counts.get(name, 0)) < expected_minimum
    ]
    if missing:
        raise RuntimeError(
            "refusing to replace incomplete feature snapshot "
            f"for {trade_date}: expected at least {expected_minimum} assets per "
            f"feature, missing coverage for {', '.join(missing)}"
        )


def compute_and_store_p0_features(trade_date: str, lookback_bars: int = 120) -> int:
    pending: list[pd.DataFrame] = []
    bars_by_asset = load_bars_for_features(
        trade_date,
        lookback_bars=lookback_bars,
    )
    if not bars_by_asset:
        return 0
    for asset_id, bars in bars_by_asset.items():
        features = features_for_trade_date(
            compute_p0_features_for_asset(asset_id, bars),
            trade_date,
        )
        if not features.empty:
            pending.append(features)
    snapshot = pd.concat(pending, ignore_index=True) if pending else pd.DataFrame()
    requested_trade_date = _trade_date_string(trade_date)
    expected_asset_count = sum(
        requested_trade_date
        in {_trade_date_string(value) for value in bars["trade_date"]}
        for bars in bars_by_asset.values()
    )
    if expected_asset_count <= 0:
        return 0
    _validate_feature_snapshot_coverage(
        snapshot,
        trade_date=requested_trade_date,
        expected_asset_count=expected_asset_count,
    )
    return replace_feature_snapshot(trade_date, snapshot)


def derive_feature_backfill_window(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    lookback_bars: int = 120,
    adjust_type: str = "hfq",
) -> dict[str, str | int | None]:
    bounds = load_market_date_bounds(adjust_type=adjust_type)
    window_start = start_date or bounds["start_date"]
    window_end = end_date or bounds["end_date"]
    if window_start is None or window_end is None:
        return {"start_date": None, "end_date": None, "date_count": 0}
    return derive_feature_window(
        start_date=str(window_start),
        end_date=str(window_end),
        lookback_bars=lookback_bars,
        adjust_type=adjust_type,
    )


def load_complete_feature_dates(
    start_date: str,
    end_date: str,
    expected_feature_count: int | None = None,
) -> set[str]:
    expected = expected_feature_count or len(FEATURE_NAMES)
    sql = """
    WITH market_assets AS (
        SELECT trade_date, count(DISTINCT asset_id)::int AS expected_assets
        FROM market_daily_bar
        WHERE trade_date BETWEEN %s AND %s
          AND adjust_type = 'hfq'
        GROUP BY trade_date
    ),
    feature_asset_counts AS (
        SELECT f.trade_date, f.feature_name, count(DISTINCT f.asset_id)::int AS asset_count
        FROM feature_snapshot f
        JOIN market_daily_bar m
          ON m.trade_date = f.trade_date
         AND m.asset_id = f.asset_id
         AND m.adjust_type = 'hfq'
        WHERE f.trade_date BETWEEN %s AND %s
          AND f.feature_set = %s
          AND f.feature_version = %s
          AND f.feature_name = ANY(%s)
        GROUP BY f.trade_date, f.feature_name
    ),
    date_coverage AS (
        SELECT
            trade_date,
            count(DISTINCT feature_name)::int AS feature_count,
            min(asset_count)::int AS min_asset_count
        FROM feature_asset_counts
        GROUP BY trade_date
    )
    SELECT coverage.trade_date
    FROM date_coverage coverage
    JOIN market_assets market ON market.trade_date = coverage.trade_date
    WHERE coverage.feature_count >= %s
      AND coverage.min_asset_count >= CEIL(market.expected_assets * %s)
    ORDER BY coverage.trade_date
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(
            conn,
            sql,
            [
                start_date,
                end_date,
                start_date,
                end_date,
                FEATURE_SET,
                FEATURE_VERSION,
                FEATURE_NAMES,
                expected,
                MIN_COMPLETE_ASSET_COVERAGE_RATIO,
            ],
        )
    return {str(row["trade_date"])[:10] for row in rows}


def _compute_p0_features_for_task(trade_date: str, lookback_bars: int) -> dict[str, Any]:
    return {
        "trade_date": trade_date,
        "feature_rows": compute_and_store_p0_features(
            trade_date,
            lookback_bars=lookback_bars,
        ),
    }


def compute_and_store_p0_features_range(
    *,
    start_date: str,
    end_date: str,
    lookback_bars: int = 120,
    adjust_type: str = "hfq",
    workers: int = 1,
    skip_complete: bool = False,
) -> pd.DataFrame:
    if workers < 1:
        raise ValueError("workers must be >= 1")
    trade_dates = load_trade_dates(start_date, end_date, adjust_type=adjust_type)
    if skip_complete:
        complete_dates = load_complete_feature_dates(start_date, end_date)
        trade_dates = [
            trade_date for trade_date in trade_dates if trade_date not in complete_dates
        ]
    if not trade_dates:
        return pd.DataFrame(columns=["trade_date", "feature_rows"])

    rows = []
    if workers > 1:
        with ProcessPoolExecutor(
            max_workers=workers,
            max_tasks_per_child=1,
        ) as executor:
            futures = [
                executor.submit(_compute_p0_features_for_task, trade_date, lookback_bars)
                for trade_date in trade_dates
            ]
            for future in as_completed(futures):
                rows.append(future.result())
        return pd.DataFrame(rows).sort_values("trade_date").reset_index(drop=True)

    for trade_date in trade_dates:
        rows.append(_compute_p0_features_for_task(trade_date, lookback_bars))
    return pd.DataFrame(rows)
