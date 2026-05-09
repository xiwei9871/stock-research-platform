from datetime import date, datetime
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


LABEL_SET = "forward_return"
LABEL_VERSION = "v1"
HORIZONS = [5, 20, 60]


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


def compute_and_store_labels(end_date: str) -> int:
    total = 0
    for asset_id, bars in load_bars_for_labels(end_date).items():
        total += upsert_label_snapshot(compute_labels_for_asset(asset_id, bars))
    return total
