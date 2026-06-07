from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime, time
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.factor_backfill import load_trade_dates_for_backfill


INTRADAY_FEATURE_CALC_VERSION = "intraday_v1"
INTRADAY_FEATURE_SOURCE = "intraday_features"

STOCK_INTRADAY_FEATURE_NAMES = [
    "intraday_return",
    "morning_return",
    "afternoon_return",
    "last_30m_return",
    "intraday_volatility_5min",
    "max_intraday_drawdown",
    "close_position_in_day",
    "amount_front_1h_ratio",
    "amount_tail_1h_ratio",
    "close_to_vwap",
]

INDUSTRY_INTRADAY_FEATURE_NAMES = [
    "industry_intraday_return_median",
    "industry_up_ratio",
    "industry_tail_strength_median",
    "industry_intraday_volatility_median",
    "industry_amount_tail_1h_ratio_median",
]


def source_data_version(freq: str, adjust_type: str) -> str:
    return f"stock_minute_bar:{freq}:{adjust_type}"


def load_stock_minute_bars_for_intraday_features(
    *,
    trade_date: str,
    freq: str = "5min",
    adjust_type: str = "raw",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    SELECT
        trade_date::text AS trade_date,
        asset_id,
        ts_code,
        trade_time,
        open,
        high,
        low,
        close,
        volume,
        amount
    FROM market.stock_minute_bar
    WHERE trade_date = %s
      AND freq = %s
      AND adjust_type = %s
    ORDER BY asset_id, trade_time
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [trade_date, freq, adjust_type])
    return pd.DataFrame(rows)


def load_industry_memberships_for_intraday_features(
    *,
    trade_date: str,
    industry_system: str = "csrc",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    SELECT asset_id, industry_code, industry_name
    FROM core.industry_membership
    WHERE industry_system = %s
      AND start_date <= %s
      AND (end_date IS NULL OR %s < end_date)
    ORDER BY asset_id, level DESC, start_date DESC
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [industry_system, trade_date, trade_date])
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=["asset_id", "industry_code", "industry_name"])
    return frame.drop_duplicates("asset_id", keep="first")[
        ["asset_id", "industry_code", "industry_name"]
    ]


def build_stock_intraday_features_daily(
    minute_bars: pd.DataFrame,
    *,
    trade_date: str,
    freq: str = "5min",
    adjust_type: str = "raw",
    calc_version: str = INTRADAY_FEATURE_CALC_VERSION,
) -> pd.DataFrame:
    columns = [
        "trade_date",
        "asset_id",
        "freq",
        "adjust_type",
        "feature_name",
        "feature_value",
        "calc_version",
        "source",
        "source_data_version",
    ]
    if minute_bars.empty:
        return pd.DataFrame(columns=columns)

    frame = minute_bars.copy()
    frame["trade_time"] = pd.to_datetime(frame["trade_time"])
    for column in ["open", "high", "low", "close", "volume", "amount"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    rows: list[dict[str, Any]] = []
    for asset_id, asset_bars in frame.groupby("asset_id", sort=False):
        features = _compute_stock_feature_values(asset_bars)
        for feature_name, feature_value in features.items():
            rows.append(
                {
                    "trade_date": _date_text(trade_date),
                    "asset_id": str(asset_id),
                    "freq": freq,
                    "adjust_type": adjust_type,
                    "feature_name": feature_name,
                    "feature_value": feature_value,
                    "calc_version": calc_version,
                    "source": INTRADAY_FEATURE_SOURCE,
                    "source_data_version": source_data_version(freq, adjust_type),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def build_industry_intraday_features_daily(
    stock_features: pd.DataFrame,
    memberships: pd.DataFrame,
    *,
    trade_date: str,
    industry_system: str = "csrc",
    freq: str = "5min",
    adjust_type: str = "raw",
    calc_version: str = INTRADAY_FEATURE_CALC_VERSION,
) -> pd.DataFrame:
    columns = [
        "trade_date",
        "industry_system",
        "industry_code",
        "industry_name",
        "freq",
        "adjust_type",
        "feature_name",
        "feature_value",
        "calc_version",
        "source",
        "source_data_version",
    ]
    if stock_features.empty or memberships.empty:
        return pd.DataFrame(columns=columns)

    wide = (
        stock_features.pivot_table(
            index="asset_id",
            columns="feature_name",
            values="feature_value",
            aggfunc="last",
        )
        .reset_index()
        .merge(memberships, on="asset_id", how="inner")
    )
    if wide.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, Any]] = []
    for (industry_code, industry_name), group in wide.groupby(
        ["industry_code", "industry_name"],
        sort=False,
    ):
        feature_values = {
            "industry_intraday_return_median": _median(group.get("intraday_return")),
            "industry_up_ratio": _mean_bool(group.get("intraday_return"), threshold=0.0),
            "industry_tail_strength_median": _median(group.get("last_30m_return")),
            "industry_intraday_volatility_median": _median(
                group.get("intraday_volatility_5min")
            ),
            "industry_amount_tail_1h_ratio_median": _median(
                group.get("amount_tail_1h_ratio")
            ),
        }
        for feature_name, feature_value in feature_values.items():
            rows.append(
                {
                    "trade_date": _date_text(trade_date),
                    "industry_system": industry_system,
                    "industry_code": str(industry_code),
                    "industry_name": str(industry_name),
                    "freq": freq,
                    "adjust_type": adjust_type,
                    "feature_name": feature_name,
                    "feature_value": feature_value,
                    "calc_version": calc_version,
                    "source": INTRADAY_FEATURE_SOURCE,
                    "source_data_version": source_data_version(freq, adjust_type),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def build_and_store_intraday_features_daily(
    *,
    trade_date: str,
    freq: str = "5min",
    adjust_type: str = "raw",
    industry_system: str = "csrc",
    service: str = SETTINGS.research_service,
) -> dict[str, int]:
    bars = load_stock_minute_bars_for_intraday_features(
        trade_date=trade_date,
        freq=freq,
        adjust_type=adjust_type,
        service=service,
    )
    stock_features = build_stock_intraday_features_daily(
        bars,
        trade_date=trade_date,
        freq=freq,
        adjust_type=adjust_type,
    )
    stock_rows = upsert_stock_intraday_features_daily(stock_features, service=service)

    memberships = load_industry_memberships_for_intraday_features(
        trade_date=trade_date,
        industry_system=industry_system,
        service=service,
    )
    industry_features = build_industry_intraday_features_daily(
        stock_features,
        memberships,
        trade_date=trade_date,
        industry_system=industry_system,
        freq=freq,
        adjust_type=adjust_type,
    )
    industry_rows = upsert_industry_intraday_features_daily(
        industry_features,
        service=service,
    )
    return {"stock_rows": stock_rows, "industry_rows": industry_rows}


def upsert_stock_intraday_features_daily(
    features: pd.DataFrame,
    *,
    service: str = SETTINGS.research_service,
) -> int:
    if features.empty:
        return 0
    sql = """
    INSERT INTO factor.stock_intraday_features_daily (
        trade_date, asset_id, freq, adjust_type, feature_name, feature_value,
        calc_version, source, source_data_version
    )
    VALUES (
        %(trade_date)s, %(asset_id)s, %(freq)s, %(adjust_type)s, %(feature_name)s,
        %(feature_value)s, %(calc_version)s, %(source)s, %(source_data_version)s
    )
    ON CONFLICT (trade_date, asset_id, freq, adjust_type, feature_name, calc_version)
    DO UPDATE SET
        feature_value = EXCLUDED.feature_value,
        source = EXCLUDED.source,
        source_data_version = EXCLUDED.source_data_version,
        computed_at = now()
    """
    rows = _jsonable_rows(features)
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
    return len(rows)


def upsert_industry_intraday_features_daily(
    features: pd.DataFrame,
    *,
    service: str = SETTINGS.research_service,
) -> int:
    if features.empty:
        return 0
    sql = """
    INSERT INTO factor.industry_intraday_features_daily (
        trade_date, industry_system, industry_code, industry_name, freq, adjust_type,
        feature_name, feature_value, calc_version, source, source_data_version
    )
    VALUES (
        %(trade_date)s, %(industry_system)s, %(industry_code)s, %(industry_name)s,
        %(freq)s, %(adjust_type)s, %(feature_name)s, %(feature_value)s,
        %(calc_version)s, %(source)s, %(source_data_version)s
    )
    ON CONFLICT (
        trade_date, industry_system, industry_code, freq, adjust_type,
        feature_name, calc_version
    )
    DO UPDATE SET
        industry_name = EXCLUDED.industry_name,
        feature_value = EXCLUDED.feature_value,
        source = EXCLUDED.source,
        source_data_version = EXCLUDED.source_data_version,
        computed_at = now()
    """
    rows = _jsonable_rows(features)
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
    return len(rows)


def backfill_intraday_features_daily_range(
    *,
    start_date: str,
    end_date: str,
    freq: str = "5min",
    adjust_type: str = "raw",
    industry_system: str = "csrc",
    workers: int = 1,
    skip_complete: bool = False,
    progress: Any | None = None,
) -> pd.DataFrame:
    trade_dates = load_trade_dates_for_backfill(
        start_date=start_date,
        end_date=end_date,
        adjust_type="hfq",
    )
    if skip_complete and trade_dates:
        complete_dates = load_complete_intraday_feature_dates(
            start_date=min(trade_dates),
            end_date=max(trade_dates),
            freq=freq,
            adjust_type=adjust_type,
        )
        trade_dates = [item for item in trade_dates if item not in complete_dates]
    if workers < 1:
        raise ValueError("workers must be >= 1")

    rows: list[dict[str, Any]] = []
    total = len(trade_dates)
    if workers == 1:
        for index, trade_date in enumerate(trade_dates, start=1):
            item = build_and_store_intraday_features_daily(
                trade_date=trade_date,
                freq=freq,
                adjust_type=adjust_type,
                industry_system=industry_system,
            )
            row = {"trade_date": trade_date, **item}
            rows.append(row)
            if progress is not None:
                progress({"event": "done", "index": index, "total": total, **row})
        return pd.DataFrame(rows)

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _build_intraday_features_daily_task,
                trade_date,
                freq,
                adjust_type,
                industry_system,
            ): {"trade_date": trade_date, "index": index}
            for index, trade_date in enumerate(trade_dates, start=1)
        }
        for future in as_completed(futures):
            metadata = futures[future]
            item = future.result()
            row = {"trade_date": metadata["trade_date"], **item}
            rows.append(row)
            if progress is not None:
                progress(
                    {
                        "event": "done",
                        "index": metadata["index"],
                        "total": total,
                        **row,
                    }
                )
    return pd.DataFrame(rows).sort_values("trade_date").reset_index(drop=True)


def load_complete_intraday_feature_dates(
    *,
    start_date: str,
    end_date: str,
    freq: str = "5min",
    adjust_type: str = "raw",
    calc_version: str = INTRADAY_FEATURE_CALC_VERSION,
    service: str = SETTINGS.research_service,
) -> set[str]:
    result = run_intraday_feature_gap_check(
        start_date=start_date,
        end_date=end_date,
        freq=freq,
        adjust_type=adjust_type,
        calc_version=calc_version,
        service=service,
    )
    return {
        row["trade_date"]
        for row in result["dates"]
        if not row["has_stock_gap"] and not row["has_industry_gap"]
    }


def run_intraday_feature_gap_check(
    *,
    start_date: str,
    end_date: str,
    freq: str = "5min",
    adjust_type: str = "raw",
    calc_version: str = INTRADAY_FEATURE_CALC_VERSION,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    version = source_data_version(freq, adjust_type)
    with connect(service) as conn:
        minute_rows = fetch_all(
            conn,
            """
            SELECT DISTINCT trade_date, asset_id
            FROM market.stock_minute_bar
            WHERE trade_date BETWEEN %s AND %s
              AND freq = %s
              AND adjust_type = %s
            ORDER BY trade_date, asset_id
            """,
            [start_date, end_date, freq, adjust_type],
        )
        stock_feature_rows = fetch_all(
            conn,
            """
            SELECT DISTINCT trade_date, asset_id
            FROM factor.stock_intraday_features_daily
            WHERE trade_date BETWEEN %s AND %s
              AND freq = %s
              AND adjust_type = %s
              AND source_data_version = %s
              AND calc_version = %s
            ORDER BY trade_date, asset_id
            """,
            [start_date, end_date, freq, adjust_type, version, calc_version],
        )
        industry_feature_rows = fetch_all(
            conn,
            """
            SELECT DISTINCT trade_date, industry_code
            FROM factor.industry_intraday_features_daily
            WHERE trade_date BETWEEN %s AND %s
              AND freq = %s
              AND adjust_type = %s
              AND source_data_version = %s
              AND calc_version = %s
            ORDER BY trade_date, industry_code
            """,
            [start_date, end_date, freq, adjust_type, version, calc_version],
        )

    minute_assets = _values_by_date(minute_rows, "asset_id")
    stock_assets = _values_by_date(stock_feature_rows, "asset_id")
    industry_codes = _values_by_date(industry_feature_rows, "industry_code")
    trade_dates = sorted(set(minute_assets) | set(stock_assets) | set(industry_codes))

    date_rows = []
    stock_gap_dates = 0
    industry_gap_dates = 0
    for trade_date in trade_dates:
        expected_assets = minute_assets.get(trade_date, set())
        actual_assets = stock_assets.get(trade_date, set())
        stock_missing = len(expected_assets - actual_assets)
        stock_stale = len(actual_assets - expected_assets)
        has_stock_gap = bool(stock_missing or stock_stale)
        has_industry_gap = bool(expected_assets and not industry_codes.get(trade_date))
        if has_stock_gap:
            stock_gap_dates += 1
        if has_industry_gap:
            industry_gap_dates += 1
        date_rows.append(
            {
                "trade_date": trade_date,
                "minute_assets": len(expected_assets),
                "stock_feature_assets": len(actual_assets),
                "stock_missing": stock_missing,
                "stock_stale": stock_stale,
                "industry_feature_groups": len(industry_codes.get(trade_date, set())),
                "has_stock_gap": has_stock_gap,
                "has_industry_gap": has_industry_gap,
            }
        )
    return {
        "start_date": start_date,
        "end_date": end_date,
        "freq": freq,
        "adjust_type": adjust_type,
        "calc_version": calc_version,
        "source_data_version": version,
        "dates": date_rows,
        "summary": {
            "dates": len(date_rows),
            "dates_with_stock_gaps": stock_gap_dates,
            "dates_with_industry_gaps": industry_gap_dates,
        },
    }


def _build_intraday_features_daily_task(
    trade_date: str,
    freq: str,
    adjust_type: str,
    industry_system: str,
) -> dict[str, int]:
    return build_and_store_intraday_features_daily(
        trade_date=trade_date,
        freq=freq,
        adjust_type=adjust_type,
        industry_system=industry_system,
    )


def _compute_stock_feature_values(asset_bars: pd.DataFrame) -> dict[str, float | None]:
    bars = asset_bars.sort_values("trade_time").copy()
    bars = bars.dropna(subset=["open", "high", "low", "close"])
    if bars.empty:
        return {name: None for name in STOCK_INTRADAY_FEATURE_NAMES}

    first_open = _first_number(bars["open"])
    last_close = _last_number(bars["close"])
    high = _max_number(bars["high"])
    low = _min_number(bars["low"])
    total_amount = _sum_number(bars["amount"])
    close_returns = bars["close"].pct_change().dropna()
    vwap = (
        _sum_number(bars["amount"]) / _sum_number(bars["volume"])
        if _sum_number(bars["volume"]) not in (None, 0)
        else None
    )
    close_cummax = bars["close"].cummax()
    drawdown = bars["close"] / close_cummax - 1.0

    morning = _window(bars, start=time(9, 30), end=time(11, 30))
    afternoon = _window(bars, start=time(13, 0), end=time(15, 0))
    tail_30m = _window(bars, start=time(14, 30), end=time(15, 0))
    front_1h = _window(bars, start=time(9, 30), end=time(10, 30))
    tail_1h = _window(bars, start=time(14, 0), end=time(15, 0))

    return {
        "intraday_return": _return(first_open, last_close),
        "morning_return": _window_return(morning),
        "afternoon_return": _window_return(afternoon),
        "last_30m_return": _window_return(tail_30m),
        "intraday_volatility_5min": _optional_float(close_returns.std(ddof=0)),
        "max_intraday_drawdown": _optional_float(drawdown.min()),
        "close_position_in_day": (
            _optional_float((last_close - low) / (high - low))
            if None not in (last_close, high, low) and high != low
            else None
        ),
        "amount_front_1h_ratio": _ratio(_sum_number(front_1h["amount"]), total_amount),
        "amount_tail_1h_ratio": _ratio(_sum_number(tail_1h["amount"]), total_amount),
        "close_to_vwap": _return(vwap, last_close),
    }


def _window(frame: pd.DataFrame, *, start: time, end: time) -> pd.DataFrame:
    clock = frame["trade_time"].dt.time
    return frame[(clock >= start) & (clock <= end)]


def _window_return(frame: pd.DataFrame) -> float | None:
    if frame.empty:
        return None
    return _return(_first_number(frame["open"]), _last_number(frame["close"]))


def _return(start_value: float | None, end_value: float | None) -> float | None:
    if start_value in (None, 0) or end_value is None:
        return None
    return _optional_float(end_value / start_value - 1.0)


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return _optional_float(numerator / denominator)


def _first_number(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.iloc[0])


def _last_number(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.iloc[-1])


def _max_number(series: pd.Series) -> float | None:
    value = pd.to_numeric(series, errors="coerce").max()
    return _optional_float(value)


def _min_number(series: pd.Series) -> float | None:
    value = pd.to_numeric(series, errors="coerce").min()
    return _optional_float(value)


def _sum_number(series: pd.Series) -> float | None:
    if series.empty:
        return None
    value = pd.to_numeric(series, errors="coerce").sum()
    return _optional_float(value)


def _median(series: pd.Series | None) -> float | None:
    if series is None:
        return None
    return _optional_float(pd.to_numeric(series, errors="coerce").median())


def _mean_bool(series: pd.Series | None, *, threshold: float) -> float | None:
    if series is None:
        return None
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return None
    return float((values > threshold).mean())


def _optional_float(value: Any) -> float | None:
    if pd.isna(value):
        return None
    return float(value)


def _date_text(value: object) -> str:
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _jsonable_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for row in frame.to_dict("records"):
        rows.append({key: (None if pd.isna(value) else value) for key, value in row.items()})
    return rows


def _values_by_date(rows: list[dict[str, Any]], value_column: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        result[_date_text(row["trade_date"])].add(str(row[value_column]))
    return dict(result)
