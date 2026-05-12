from datetime import date, datetime
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.research_windows import derive_label_window, load_market_date_bounds


LABEL_SET = "forward_return"
LABEL_VERSION = "v1"
HORIZONS = [5, 10, 20, 60]


def _trade_date_string(value: Any) -> str:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def compute_labels_for_asset(asset_id: str, bars: pd.DataFrame) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame()

    frame = bars.sort_values("trade_date").copy()
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")

    rows: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        future_return = frame["close"].shift(-horizon) / frame["close"] - 1.0
        for index, row in frame.iterrows():
            value = future_return.loc[index]
            if pd.isna(value):
                continue
            rows.append(
                {
                    "asset_id": asset_id,
                    "trade_date": _trade_date_string(row["trade_date"]),
                    "label_set": LABEL_SET,
                    "label_version": LABEL_VERSION,
                    "horizon": horizon,
                    "label_name": "future_return",
                    "label_value": float(value),
                }
            )

    return pd.DataFrame(rows)


def load_bars_for_labels(end_date: str) -> dict[str, pd.DataFrame]:
    sql = """
    SELECT asset_id, trade_date, close
    FROM market_daily_bar
    WHERE adjust_type = 'hfq'
      AND trade_date <= %s
    ORDER BY asset_id, trade_date
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, [end_date])

    frame = pd.DataFrame(rows)
    if frame.empty:
        return {}

    grouped = frame.groupby("asset_id", sort=False)
    return {
        asset_id: group.drop(columns=["asset_id"]).reset_index(drop=True).copy()
        for asset_id, group in grouped
    }


def upsert_label_snapshot(labels: pd.DataFrame) -> int:
    if labels.empty:
        return 0

    sql = """
    INSERT INTO label_snapshot (
        asset_id, trade_date, label_set, label_version, horizon, label_name,
        label_value
    )
    VALUES (
        %(asset_id)s, %(trade_date)s, %(label_set)s, %(label_version)s,
        %(horizon)s, %(label_name)s, %(label_value)s
    )
    ON CONFLICT (asset_id, trade_date, label_set, label_version, horizon, label_name)
    DO UPDATE SET
        label_value = EXCLUDED.label_value,
        computed_at = now()
    """
    rows = labels.to_dict("records")
    with connect(SETTINGS.research_service) as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
    return len(rows)


def derive_label_backfill_window(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    horizons: list[int] | None = None,
    adjust_type: str = "hfq",
) -> dict[str, str | int | None]:
    bounds = load_market_date_bounds(adjust_type=adjust_type)
    window_start = start_date or bounds["start_date"]
    window_end = end_date or bounds["end_date"]
    if window_start is None or window_end is None:
        return {"start_date": None, "end_date": None, "date_count": 0}
    return derive_label_window(
        start_date=str(window_start),
        end_date=str(window_end),
        horizons=horizons or HORIZONS,
        adjust_type=adjust_type,
    )


def upsert_label_snapshot_for_horizon(
    end_date: str,
    horizon: int,
    *,
    start_date: str | None = None,
) -> int:
    start_date_filter = "AND trade_date >= %(start_date)s" if start_date else ""
    sql = f"""
    INSERT INTO label_snapshot (
        asset_id, trade_date, label_set, label_version, horizon, label_name,
        label_value
    )
    SELECT
        asset_id,
        trade_date,
        %(label_set)s,
        %(label_version)s,
        %(horizon)s,
        %(label_name)s,
        future_close / close - 1.0
    FROM (
        SELECT
            asset_id,
            trade_date,
            close,
            LEAD(close, {int(horizon)}) OVER (
                PARTITION BY asset_id
                ORDER BY trade_date
            ) AS future_close
        FROM market_daily_bar
        WHERE adjust_type = 'hfq'
          {start_date_filter}
          AND trade_date <= %(end_date)s
    ) priced
    WHERE close IS NOT NULL
      AND close <> 0
      AND future_close IS NOT NULL
    ON CONFLICT (asset_id, trade_date, label_set, label_version, horizon, label_name)
    DO UPDATE SET
        label_value = EXCLUDED.label_value,
        computed_at = now()
    """
    params = {
        "end_date": end_date,
        "label_set": LABEL_SET,
        "label_version": LABEL_VERSION,
        "horizon": horizon,
        "label_name": "future_return",
        "start_date": start_date,
    }
    with connect(SETTINGS.research_service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return int(cur.rowcount)


def compute_and_store_labels(
    end_date: str,
    *,
    start_date: str | None = None,
    horizons: list[int] | None = None,
) -> int:
    selected_horizons = horizons or HORIZONS
    return sum(
        upsert_label_snapshot_for_horizon(
            end_date,
            horizon,
            start_date=start_date,
        )
        for horizon in selected_horizons
    )
