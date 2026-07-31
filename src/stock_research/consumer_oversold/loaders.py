from __future__ import annotations

import math
from collections.abc import Iterable
from decimal import Decimal
from numbers import Real
from typing import Any

import pandas as pd

from stock_research.db import connect, fetch_all
from stock_research.services.finance_ttm import calc_ttm_from_cumulative_rows

from .contracts import validate_trade_date


ASSET_COLUMNS = ("asset_id", "stock_code", "name", "list_date")
STATUS_COLUMNS = ("asset_id", "is_st", "is_delisting_risk", "is_suspended")
LIQUIDITY_COLUMNS = ("asset_id", "avg_turnover_amount")
INDUSTRY_COLUMNS = ("asset_id", "industry_system", "industry_name")
MARKET_COLUMNS = (
    "asset_id",
    "trade_date",
    "close",
    "raw_close",
    "amount",
    "turnover_rate",
    "pct_chg",
    "is_st",
    "trade_status",
)
TURNOVER_DERIVATION_INPUTS_ATTR = "consumer_turnover_derivation_inputs"
TURNOVER_DERIVATION_COVERAGE_ATTR = "consumer_turnover_derivation_coverage"
_MARKET_QUERY_COLUMNS = (
    *MARKET_COLUMNS,
    "turnover_volume",
    "turnover_source",
)
SHARE_CAPACITY_COLUMNS = (
    "asset_id",
    "total_share",
    "float_share",
    "free_float_share",
)
FINANCE_COLUMNS = (
    "asset_id",
    "report_period",
    "announcement_date",
    "revenue_ttm",
    "revenue_growth",
    "np_parent_ttm",
    "profit_growth",
    "gross_margin",
    "net_margin",
    "roe",
    "ocf_to_np",
    "debt_ratio",
    "equity_parent",
    "operating_cash_flow",
    "total_share",
)
VALUATION_COLUMNS = (
    "asset_id",
    "valuation_date",
    "pe_ttm",
    "ps_ttm",
    "ev_ebitda",
    "industry_system",
    "industry_name",
)
EARNINGS_COLUMNS = (
    "asset_id",
    "event_type",
    "announcement_date",
    "report_period",
    "forecast_type",
    "forecast_np_min",
    "forecast_np_max",
    "forecast_np_change_min",
    "forecast_np_change_max",
    "revenue",
    "revenue_yoy",
    "np_parent",
    "np_yoy",
    "summary",
    "source",
    "source_endpoint",
)
V2_HFQ_DAILY_COLUMNS = ("asset_id", "trade_date", "hfq_close")
V2_RAW_DAILY_COLUMNS = (
    "asset_id",
    "trade_date",
    "raw_open",
    "raw_high",
    "raw_low",
    "raw_close",
)
V2_MINUTE_OUTCOME_COLUMNS = (
    "asset_id",
    "trade_date",
    "trade_time",
    "open",
    "high",
    "low",
    "close",
    "limit_up_price",
)


def normalize_market_amount(amount: Any, source: Any) -> Any:
    if isinstance(amount, bool):
        raise ValueError("market amount must be a finite numeric value")
    if isinstance(amount, Decimal):
        if not amount.is_finite():
            raise ValueError("market amount must be a finite numeric value")
    elif isinstance(amount, Real):
        if not math.isfinite(amount):
            raise ValueError("market amount must be a finite numeric value")
    else:
        raise ValueError("market amount must be a finite numeric value")

    if source is None:
        normalized_source = ""
    elif isinstance(source, str):
        normalized_source = source.casefold()
    else:
        raise ValueError("market amount source must be a string or None")
    return amount * 1000 if "tushare" in normalized_source else amount


def _finite_positive_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
    elif not isinstance(value, Real):
        return None
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0.0 else None


def _missing_scalar(value: Any) -> bool:
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return isinstance(missing, bool) and missing


def _turnover_volume_multiplier(source: Any) -> tuple[float, str] | None:
    if not isinstance(source, str):
        return None
    marker = source.strip().casefold()
    if not marker:
        return None
    if "tushare" in marker:
        return 10_000.0, marker
    if "baostock" in marker:
        return 100.0, marker
    return None


def derive_consumer_market_turnover_history(
    bars: pd.DataFrame,
    share_capacity: pd.DataFrame,
    *,
    trade_date: str,
) -> pd.DataFrame:
    """Derive only missing PIT turnover rates from auditable loader metadata."""
    if not isinstance(bars, pd.DataFrame):
        raise TypeError("bars must be a pandas DataFrame")
    if not isinstance(share_capacity, pd.DataFrame):
        raise TypeError("share_capacity must be a pandas DataFrame")
    cutoff = validate_trade_date(trade_date)
    result = bars.copy(deep=True)
    required_bar_columns = {"asset_id", "trade_date", "turnover_rate"}
    required_share_columns = {"asset_id", "float_share"}
    if not required_bar_columns.issubset(result.columns):
        return result

    raw_inputs = bars.attrs.get(TURNOVER_DERIVATION_INPUTS_ATTR, [])
    metadata_rows = raw_inputs if isinstance(raw_inputs, list) else []
    metadata_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    duplicate_metadata: set[tuple[str, str]] = set()
    for raw in metadata_rows:
        if not isinstance(raw, dict):
            continue
        asset_id = str(raw.get("asset_id") or "").strip()
        try:
            date_text = _date_text(raw.get("trade_date"))
        except ValueError:
            continue
        if not asset_id or not isinstance(date_text, str) or date_text > cutoff:
            continue
        key = (asset_id, date_text)
        if key in metadata_by_key:
            duplicate_metadata.add(key)
        metadata_by_key[key] = raw
    for key in duplicate_metadata:
        metadata_by_key.pop(key, None)

    share_by_asset: dict[str, float] = {}
    if required_share_columns.issubset(share_capacity.columns):
        normalized_shares = share_capacity.loc[:, ["asset_id", "float_share"]].copy()
        normalized_shares["asset_id"] = (
            normalized_shares["asset_id"].astype(str).str.strip()
        )
        duplicate_shares = set(
            normalized_shares.loc[
                normalized_shares["asset_id"].duplicated(keep=False), "asset_id"
            ]
        )
        for row in normalized_shares.itertuples(index=False):
            if row.asset_id in duplicate_shares:
                continue
            shares = _finite_positive_number(row.float_share)
            if row.asset_id and shares is not None:
                share_by_asset[row.asset_id] = shares

    missing_rows = 0
    derived_rows = 0
    derived_by_source: dict[str, int] = {}
    turnover_position = result.columns.get_loc("turnover_rate")
    for position, row in enumerate(result.itertuples(index=False)):
        current = getattr(row, "turnover_rate")
        if not _missing_scalar(current):
            continue
        try:
            date_text = _date_text(getattr(row, "trade_date"))
        except ValueError:
            continue
        if not isinstance(date_text, str) or date_text > cutoff:
            continue
        missing_rows += 1
        asset_id = str(getattr(row, "asset_id") or "").strip()
        metadata = metadata_by_key.get((asset_id, date_text))
        shares = share_by_asset.get(asset_id)
        if metadata is None or shares is None:
            continue
        volume = _finite_positive_number(metadata.get("volume"))
        source_units = _turnover_volume_multiplier(metadata.get("source"))
        if volume is None or source_units is None:
            continue
        multiplier, marker = source_units
        derived = volume * multiplier / shares
        if not math.isfinite(derived) or derived <= 0.0:
            continue
        result.iat[position, turnover_position] = derived
        derived_rows += 1
        derived_by_source[marker] = derived_by_source.get(marker, 0) + 1

    result.attrs[TURNOVER_DERIVATION_COVERAGE_ATTR] = {
        "method": "pit_source_aware_v1",
        "share_capacity_cutoff": cutoff,
        "missing_turnover_rows": missing_rows,
        "derived_rows": derived_rows,
        "unresolved_rows": missing_rows - derived_rows,
        "derived_rows_by_source": dict(sorted(derived_by_source.items())),
    }
    result.attrs.pop(TURNOVER_DERIVATION_INPUTS_ATTR, None)
    return result


def _asset_ids(values: list[str]) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("asset_ids must be a list of unique non-empty strings")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("asset_ids must contain unique non-empty strings")
        normalized.append(value.strip())
    if len(set(normalized)) != len(normalized):
        raise ValueError("asset_ids must contain unique non-empty strings")
    return normalized


def _frame(rows: Iterable[dict[str, Any]], columns: tuple[str, ...]) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=list(columns))


def _date_text(value: Any) -> Any:
    if value is None or pd.isna(value):
        return pd.NA
    try:
        return pd.Timestamp(value).date().isoformat()
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"database returned invalid date: {value!r}") from exc


def _format_dates(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        if column in result:
            result[column] = result[column].map(_date_text)
    return result


def _sort(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if frame.empty:
        return frame.reset_index(drop=True)
    return frame.sort_values(columns, kind="stable", na_position="last").reset_index(drop=True)


def resolve_latest_complete_consumer_trade_date(*, service: str) -> str:
    sql = """
    WITH recent_open_dates AS (
        SELECT DISTINCT trade_date
        FROM market.trading_calendar
        WHERE is_open = TRUE
          AND trade_date <=
              (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date
        ORDER BY trade_date DESC
        LIMIT %s
    ), expected_assets AS (
        SELECT d.trade_date, a.asset_id
        FROM recent_open_dates d
        JOIN core.asset_master a
          ON a.list_date <= d.trade_date
         AND (a.delist_date IS NULL OR a.delist_date >= d.trade_date)
        LEFT JOIN core.asset_status_daily s
          ON s.asset_id = a.asset_id
         AND s.trade_date = d.trade_date
        WHERE s.is_suspended IS DISTINCT FROM TRUE
    ), bar_presence AS (
        SELECT e.trade_date,
               e.asset_id,
               BOOL_OR(b.adjust_type = 'raw') AS has_raw,
               BOOL_OR(b.adjust_type = 'hfq') AS has_hfq
        FROM expected_assets e
        LEFT JOIN market_daily_bar b
          ON b.trade_date = e.trade_date
         AND b.asset_id = e.asset_id
         AND b.adjust_type IN ('raw', 'hfq')
        GROUP BY e.trade_date, e.asset_id
    )
    SELECT d.trade_date,
           TRUE AS is_open,
           COUNT(p.asset_id) AS expected_asset_count,
           COUNT(p.asset_id) FILTER (WHERE p.has_raw) AS raw_asset_count,
           COUNT(p.asset_id) FILTER (WHERE p.has_hfq) AS hfq_asset_count,
           COUNT(p.asset_id)
               FILTER (WHERE p.has_raw AND p.has_hfq) AS paired_asset_count
    FROM recent_open_dates d
    LEFT JOIN bar_presence p ON p.trade_date = d.trade_date
    GROUP BY d.trade_date
    ORDER BY d.trade_date DESC
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [20])
    if not rows:
        raise ValueError("no complete consumer trade date found in database")
    count_fields = (
        "expected_asset_count",
        "raw_asset_count",
        "hfq_asset_count",
        "paired_asset_count",
    )
    required = {"trade_date", "is_open", *count_fields}
    parsed: list[tuple[str, int, int, int, int]] = []
    seen_dates: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError("database returned invalid consumer trade-date row")
        if row["is_open"] is not True:
            raise ValueError("database returned invalid closed consumer trade-date row")
        trade_date = _date_text(row["trade_date"])
        if not isinstance(trade_date, str) or trade_date in seen_dates:
            raise ValueError("database returned invalid consumer trade date")
        counts: list[int] = []
        for field in count_fields:
            value = row[field]
            if type(value) is not int or value < 0:
                raise ValueError(f"database returned invalid {field}")
            counts.append(value)
        seen_dates.add(trade_date)
        expected_count, raw_count, hfq_count, paired_count = counts
        if (
            raw_count > expected_count
            or hfq_count > expected_count
            or paired_count > raw_count
            or paired_count > hfq_count
        ):
            raise ValueError("database returned invalid consumer coverage counts")
        parsed.append(
            (trade_date, expected_count, raw_count, hfq_count, paired_count)
        )
    for trade_date, expected_count, raw_count, hfq_count, paired_count in sorted(
        parsed, reverse=True
    ):
        if (
            expected_count > 0
            and raw_count * 100 >= expected_count * 99
            and hfq_count * 100 >= expected_count * 99
            and paired_count * 100 >= expected_count * 99
        ):
            return trade_date
    raise ValueError("no complete consumer trade date found in database")


def load_consumer_universe_frames(
    trade_date: str,
    *,
    service: str,
) -> dict[str, pd.DataFrame]:
    cutoff = validate_trade_date(trade_date)
    assets_sql = """
    SELECT asset_id, symbol AS stock_code, name, list_date
    FROM core.asset_master
    WHERE list_date <= %s
      AND (delist_date IS NULL OR delist_date >= %s)
    ORDER BY asset_id
    """
    statuses_sql = """
    SELECT a.asset_id,
           COALESCE(s.is_st, latest_bar.is_st, FALSE) AS is_st,
           (a.delist_date IS NOT NULL AND a.delist_date <= %s)
               AS is_delisting_risk,
           COALESCE(s.is_suspended, TRUE) AS is_suspended
    FROM core.asset_master a
    LEFT JOIN core.asset_status_daily s
      ON s.asset_id = a.asset_id AND s.trade_date = %s
    LEFT JOIN LATERAL (
        SELECT b.is_st
        FROM market_daily_bar b
        WHERE b.asset_id = a.asset_id
          AND b.trade_date <= %s
          AND b.adjust_type = 'hfq'
        ORDER BY b.trade_date DESC
        LIMIT 1
    ) latest_bar ON TRUE
    WHERE a.list_date <= %s
      AND (a.delist_date IS NULL OR a.delist_date >= %s)
    ORDER BY a.asset_id
    """
    # Tushare-derived amounts are stored in thousands of yuan; other sources
    # already use yuan. Normalize each bar before aggregating the liquidity gate.
    liquidity_sql = """
    WITH latest_dates AS (
        SELECT DISTINCT trade_date
        FROM market_daily_bar
        WHERE trade_date <= %s
          AND adjust_type = 'hfq'
        ORDER BY trade_date DESC
        LIMIT 20
    )
    SELECT b.asset_id,
           AVG(CASE WHEN lower(COALESCE(b.source, '')) LIKE '%%tushare%%'
                    THEN b.amount * 1000 ELSE b.amount END) AS avg_turnover_amount
    FROM market_daily_bar b
    JOIN latest_dates d ON d.trade_date = b.trade_date
    WHERE b.adjust_type = 'hfq'
    GROUP BY b.asset_id
    ORDER BY b.asset_id
    """
    industries_sql = """
    WITH ranked AS (
        SELECT asset_id, industry_system, industry_name,
               ROW_NUMBER() OVER (
                   PARTITION BY asset_id
                   ORDER BY CASE lower(industry_system)
                                WHEN 'sw' THEN 0
                                WHEN 'citics' THEN 1
                                WHEN 'csrc' THEN 2
                                ELSE 9
                            END,
                            level DESC, start_date DESC, industry_code
               ) AS row_number
        FROM core.industry_membership
        WHERE start_date <= %s
          AND (end_date IS NULL OR %s < end_date)
    )
    SELECT asset_id, industry_system, industry_name
    FROM ranked
    WHERE row_number = 1
    ORDER BY asset_id, industry_system, industry_name
    """
    with connect(service) as conn:
        asset_rows = fetch_all(conn, assets_sql, [cutoff, cutoff])
        # Missing daily status is conservative: suspension defaults true; ST falls
        # back to the latest PIT daily bar and only then to false.
        status_rows = fetch_all(conn, statuses_sql, [cutoff] * 5)
        liquidity_rows = fetch_all(conn, liquidity_sql, [cutoff])
        industry_rows = fetch_all(conn, industries_sql, [cutoff, cutoff])

    assets = _format_dates(_frame(asset_rows, ASSET_COLUMNS), ("list_date",))
    industries = _frame(industry_rows, INDUSTRY_COLUMNS)
    if not industries.empty:
        priorities = industries["industry_system"].map(
            lambda value: {"sw": 0, "citics": 1, "csrc": 2}.get(
                str(value).strip().lower(), 9
            )
        )
        industries = (
            industries.assign(_system_priority=priorities)
            .sort_values(
                ["asset_id", "_system_priority", "industry_system", "industry_name"],
                kind="stable",
            )
            .drop_duplicates("asset_id", keep="first")
            .drop(columns="_system_priority")
        )
    return {
        "assets": _sort(assets, ["asset_id"]),
        "statuses": _sort(_frame(status_rows, STATUS_COLUMNS), ["asset_id"]),
        "liquidity": _sort(_frame(liquidity_rows, LIQUIDITY_COLUMNS), ["asset_id"]),
        "industries": _sort(
            industries,
            ["asset_id", "industry_system", "industry_name"],
        ),
    }


def load_consumer_market_history(
    trade_date: str,
    *,
    service: str,
    asset_ids: list[str] | None = None,
) -> pd.DataFrame:
    cutoff = validate_trade_date(trade_date)
    assets = _asset_ids(asset_ids) if asset_ids is not None else None
    if assets == []:
        result = _frame([], MARKET_COLUMNS)
        result.attrs[TURNOVER_DERIVATION_INPUTS_ATTR] = []
        return result
    asset_clause = "\n      AND b.asset_id = ANY(%s)" if assets is not None else ""
    sql = f"""
    WITH latest_dates AS (
        SELECT DISTINCT trade_date
        FROM market_daily_bar
        WHERE trade_date <= %s
          AND adjust_type = 'hfq'
        ORDER BY trade_date DESC
        LIMIT %s
    )
    SELECT b.asset_id, b.trade_date, b.close, raw.close AS raw_close,
           CASE WHEN lower(COALESCE(b.source, '')) LIKE '%%tushare%%'
                THEN b.amount * 1000 ELSE b.amount END AS amount,
           b.turnover_rate, b.pct_chg, b.is_st, b.trade_status,
           b.volume AS turnover_volume, b.source AS turnover_source
    FROM market_daily_bar b
    JOIN latest_dates d ON d.trade_date = b.trade_date
    LEFT JOIN market_daily_bar raw
      ON raw.asset_id = b.asset_id
     AND raw.trade_date = b.trade_date
     AND raw.adjust_type = 'raw'
    WHERE b.adjust_type = 'hfq'
    {asset_clause}
    ORDER BY b.asset_id, b.trade_date
    """
    params: list[Any] = [cutoff, 520]
    if assets is not None:
        params.append(assets)
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    internal = _format_dates(_frame(rows, _MARKET_QUERY_COLUMNS), ("trade_date",))
    internal = _sort(internal, ["asset_id", "trade_date"])
    result = internal.loc[:, MARKET_COLUMNS].copy()
    missing_turnover = internal.loc[internal["turnover_rate"].isna()]
    result.attrs[TURNOVER_DERIVATION_INPUTS_ATTR] = [
        {
            "asset_id": row["asset_id"],
            "trade_date": row["trade_date"],
            "volume": row["turnover_volume"],
            "source": row["turnover_source"],
        }
        for row in missing_turnover.to_dict(orient="records")
    ]
    return result


def _outcome_date_range(start_date: str, end_date: str) -> tuple[str, str]:
    start = validate_trade_date(start_date)
    end = validate_trade_date(end_date)
    if start > end:
        raise ValueError("start_date must be on or before end_date")
    return start, end


def load_consumer_v2_outcome_calendar(
    start_date: str,
    end_date: str,
    *,
    service: str,
) -> list[str]:
    start, end = _outcome_date_range(start_date, end_date)
    sql = """
    SELECT trade_date
    FROM market.trading_calendar
    WHERE is_open = TRUE
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [start, end])
    dates: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"trade_date"}:
            raise ValueError("database returned invalid outcome calendar row")
        value = _date_text(row["trade_date"])
        if not isinstance(value, str) or not start <= value <= end:
            raise ValueError("database returned outcome calendar date outside requested range")
        dates.append(value)
    if len(set(dates)) != len(dates) or dates != sorted(dates):
        raise ValueError("database returned duplicate or unordered outcome calendar dates")
    return dates


def load_consumer_v2_hfq_daily_closes(
    asset_ids: list[str],
    start_date: str,
    end_date: str,
    *,
    service: str,
) -> pd.DataFrame:
    assets = _asset_ids(asset_ids)
    start, end = _outcome_date_range(start_date, end_date)
    if not assets:
        return _frame([], V2_HFQ_DAILY_COLUMNS)
    sql = """
    SELECT asset_id, trade_date, close AS hfq_close
    FROM market_daily_bar
    WHERE asset_id = ANY(%s)
      AND trade_date BETWEEN %s AND %s
      AND adjust_type = 'hfq'
    ORDER BY asset_id, trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [assets, start, end])
    result = _format_dates(_frame(rows, V2_HFQ_DAILY_COLUMNS), ("trade_date",))
    if not result.empty:
        result = result.loc[
            result["asset_id"].isin(assets)
            & result["trade_date"].between(start, end, inclusive="both")
        ]
    return _sort(result, ["asset_id", "trade_date"])


def load_consumer_v2_raw_daily_bars(
    asset_ids: list[str],
    start_date: str,
    end_date: str,
    *,
    service: str,
) -> pd.DataFrame:
    assets = _asset_ids(asset_ids)
    start, end = _outcome_date_range(start_date, end_date)
    if not assets:
        return _frame([], V2_RAW_DAILY_COLUMNS)
    sql = """
    SELECT asset_id, trade_date,
           open AS raw_open, high AS raw_high, low AS raw_low, close AS raw_close
    FROM market_daily_bar
    WHERE asset_id = ANY(%s)
      AND trade_date BETWEEN %s AND %s
      AND adjust_type = 'raw'
    ORDER BY asset_id, trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [assets, start, end])
    result = _format_dates(_frame(rows, V2_RAW_DAILY_COLUMNS), ("trade_date",))
    if not result.empty:
        result = result.loc[
            result["asset_id"].isin(assets)
            & result["trade_date"].between(start, end, inclusive="both")
        ]
    return _sort(result, ["asset_id", "trade_date"])


def load_consumer_v2_minute_outcome_bars(
    asset_ids: list[str],
    start_date: str,
    end_date: str,
    *,
    service: str,
) -> pd.DataFrame:
    assets = _asset_ids(asset_ids)
    start, end = _outcome_date_range(start_date, end_date)
    if not assets:
        return _frame([], V2_MINUTE_OUTCOME_COLUMNS)
    sql = """
    WITH minute AS (
        SELECT DISTINCT ON (asset_id, trade_date, trade_time)
               asset_id, trade_date, trade_time, open, high, low, close
        FROM market.stock_minute_bar
        WHERE asset_id = ANY(%s)
          AND trade_date BETWEEN %s AND %s
          AND freq = '5min'
          AND adjust_type = 'raw'
        ORDER BY asset_id, trade_date, trade_time,
                 CASE source
                     WHEN 'baostock' THEN 0
                     WHEN 'tushare' THEN 1
                     WHEN 'akshare' THEN 2
                     WHEN 'eastmoney' THEN 3
                     ELSE 9
                 END
    )
    SELECT minute.asset_id, minute.trade_date, minute.trade_time,
           minute.open, minute.high, minute.low, minute.close,
           ROUND(
               previous.raw_close * (
                   1 + CASE
                       WHEN asset.symbol LIKE '4%%'
                         OR asset.symbol LIKE '8%%'
                         OR asset.symbol LIKE '920%%' THEN 0.30
                       WHEN asset.symbol LIKE '300%%'
                         OR asset.symbol LIKE '301%%'
                         OR asset.symbol LIKE '688%%'
                         OR asset.symbol LIKE '689%%' THEN 0.20
                       WHEN COALESCE(daily.is_st, FALSE) THEN 0.05
                       ELSE 0.10
                   END
               ),
               2
           ) AS limit_up_price
    FROM minute
    JOIN core.asset_master asset ON asset.asset_id = minute.asset_id
    LEFT JOIN market_daily_bar daily
      ON daily.asset_id = minute.asset_id
     AND daily.trade_date = minute.trade_date
     AND daily.adjust_type = 'raw'
    LEFT JOIN LATERAL (
        SELECT close AS raw_close
        FROM market_daily_bar previous_bar
        WHERE previous_bar.asset_id = minute.asset_id
          AND previous_bar.trade_date < minute.trade_date
          AND previous_bar.adjust_type = 'raw'
        ORDER BY previous_bar.trade_date DESC
        LIMIT 1
    ) previous ON TRUE
    ORDER BY minute.asset_id, minute.trade_date, minute.trade_time
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [assets, start, end])
    result = _format_dates(
        _frame(rows, V2_MINUTE_OUTCOME_COLUMNS), ("trade_date",)
    )
    if not result.empty:
        result["trade_time"] = pd.to_datetime(result["trade_time"], errors="coerce")
        result = result.loc[
            result["asset_id"].isin(assets)
            & result["trade_date"].between(start, end, inclusive="both")
            & result["trade_time"].notna()
        ]
    return _sort(result, ["asset_id", "trade_date", "trade_time"])


def load_consumer_share_capacity(
    asset_ids: list[str],
    trade_date: str,
    *,
    service: str,
) -> pd.DataFrame:
    assets = _asset_ids(asset_ids)
    cutoff = validate_trade_date(trade_date)
    if not assets:
        return _frame([], SHARE_CAPACITY_COLUMNS)
    sql = """
    SELECT DISTINCT ON (asset_id)
           asset_id, total_share, float_share, free_float_share
    FROM finance.share_capital_event
    WHERE asset_id = ANY(%s)
      AND event_date <= %s
      AND (announcement_date IS NULL OR announcement_date <= %s)
    ORDER BY asset_id, event_date DESC, announcement_date DESC NULLS LAST, source ASC
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [assets, cutoff, cutoff])
    return _sort(_frame(rows, SHARE_CAPACITY_COLUMNS), ["asset_id"])


def _disclosed_rows(rows: list[dict[str, Any]], cutoff: str) -> list[dict[str, Any]]:
    disclosed: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        announcement_date = _date_text(row.get("announcement_date"))
        report_period = _date_text(row.get("report_period"))
        if pd.isna(announcement_date) or pd.isna(report_period) or announcement_date > cutoff:
            continue
        row["asset_id"] = str(row["asset_id"])
        row["announcement_date"] = announcement_date
        row["report_period"] = report_period
        disclosed.append(row)
    return disclosed


def _latest_by_period(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    ordered = sorted(
        rows,
        key=lambda row: (
            row["asset_id"],
            row["report_period"],
            row["announcement_date"],
            str(row.get("source") or ""),
            str(row.get("calc_version") or ""),
        ),
        reverse=True,
    )
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in ordered:
        latest.setdefault((row["asset_id"], row["report_period"]), row)
    return latest


def _latest_fields_by_period(
    rows: list[dict[str, Any]],
    fields: tuple[str, ...],
) -> dict[tuple[str, str], dict[str, Any]]:
    ordered = sorted(
        rows,
        key=lambda row: (
            row["asset_id"],
            row["report_period"],
            row["announcement_date"],
            str(row.get("source") or ""),
            str(row.get("calc_version") or ""),
        ),
        reverse=True,
    )
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in ordered:
        key = (row["asset_id"], row["report_period"])
        selected = latest.setdefault(key, dict(row))
        for field in fields:
            if pd.isna(selected.get(field)) and not pd.isna(row.get(field)):
                selected[field] = row[field]
    return latest


def _finite_ratio(numerator: Any, denominator: Any) -> Any:
    if pd.isna(numerator) or pd.isna(denominator) or denominator == 0:
        return None
    try:
        ratio = numerator / denominator
        return ratio if math.isfinite(float(ratio)) else None
    except (ArithmeticError, TypeError, ValueError, OverflowError):
        return None


def _ttm_at_period(
    rows: list[dict[str, Any]],
    *,
    report_period: str,
    asof: str,
    value_column: str,
) -> float | None:
    available = [
        row
        for row in rows
        if row["report_period"] <= report_period
        and row["announcement_date"] <= asof
    ]
    if not any(
        row["report_period"] == report_period and row.get(value_column) is not None
        for row in available
    ):
        return None
    available.sort(
        key=lambda row: (
            row["announcement_date"],
            str(row.get("source") or ""),
            str(row.get("calc_version") or ""),
        ),
        reverse=True,
    )
    return calc_ttm_from_cumulative_rows(
        available,
        value_column=value_column,
        trade_date=asof,
    )


def _rows_by_asset(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["asset_id"], []).append(row)
    return grouped


def _latest_share_by_asset(rows: list[dict[str, Any]], cutoff: str) -> dict[str, dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        event_date = _date_text(row.get("event_date"))
        announcement_date = _date_text(row.get("announcement_date"))
        if pd.isna(event_date) or event_date > cutoff:
            continue
        if not pd.isna(announcement_date) and announcement_date > cutoff:
            continue
        row["asset_id"] = str(row["asset_id"])
        row["event_date"] = event_date
        row["announcement_date"] = announcement_date
        normalized.append(row)
    normalized.sort(
        key=lambda row: (
            row["asset_id"],
            -pd.Timestamp(row["event_date"]).toordinal(),
            pd.isna(row["announcement_date"]),
            -pd.Timestamp(row["announcement_date"]).toordinal()
            if not pd.isna(row["announcement_date"])
            else 0,
            str(row.get("source") or ""),
        )
    )
    latest: dict[str, dict[str, Any]] = {}
    for row in normalized:
        latest.setdefault(row["asset_id"], row)
    return latest


def load_consumer_finance_history(
    asset_ids: list[str],
    trade_date: str,
    *,
    service: str,
) -> pd.DataFrame:
    assets = _asset_ids(asset_ids)
    cutoff = validate_trade_date(trade_date)
    if not assets:
        return _frame([], FINANCE_COLUMNS)

    queries = (
        """
        SELECT asset_id, report_period, announcement_date, revenue, np_parent, source
        FROM finance.income_statement
        WHERE asset_id = ANY(%s) AND announcement_date <= %s
        ORDER BY asset_id, report_period, announcement_date DESC, source DESC
        """,
        """
        SELECT asset_id, report_period, announcement_date, revenue_yoy, np_yoy,
               gross_margin, net_margin, roe, ocf_to_np, debt_ratio, source, calc_version
        FROM finance.indicator_quarter
        WHERE asset_id = ANY(%s) AND announcement_date <= %s
        ORDER BY asset_id, report_period, announcement_date DESC, source DESC, calc_version DESC
        """,
        """
        SELECT asset_id, report_period, announcement_date, total_equity,
               total_assets, total_liabilities, source
        FROM finance.balance_sheet
        WHERE asset_id = ANY(%s) AND announcement_date <= %s
        ORDER BY asset_id, report_period, announcement_date DESC, source DESC
        """,
        """
        SELECT asset_id, report_period, announcement_date, net_operate_cash_flow, source
        FROM finance.cash_flow
        WHERE asset_id = ANY(%s) AND announcement_date <= %s
        ORDER BY asset_id, report_period, announcement_date DESC, source DESC
        """,
    )
    share_sql = """
    SELECT DISTINCT ON (asset_id)
           asset_id, event_date, announcement_date, total_share, source
    FROM finance.share_capital_event
    WHERE asset_id = ANY(%s)
      AND event_date <= %s
      AND (announcement_date IS NULL OR announcement_date <= %s)
    ORDER BY asset_id, event_date DESC, announcement_date DESC NULLS LAST, source ASC
    """
    with connect(service) as conn:
        raw_income, raw_indicator, raw_balance, raw_cash = [
            fetch_all(conn, sql, [assets, cutoff]) for sql in queries
        ]
        raw_shares = fetch_all(conn, share_sql, [assets, cutoff, cutoff])

    income = _disclosed_rows(raw_income, cutoff)
    indicator = _disclosed_rows(raw_indicator, cutoff)
    balance = _disclosed_rows(raw_balance, cutoff)
    cash = _disclosed_rows(raw_cash, cutoff)
    income_by_asset = _rows_by_asset(income)
    cash_by_asset = _rows_by_asset(cash)
    shares_by_asset = _latest_share_by_asset(raw_shares, cutoff)
    latest_sources = [
        _latest_by_period(income),
        _latest_fields_by_period(
            indicator,
            (
                "revenue_yoy",
                "np_yoy",
                "gross_margin",
                "net_margin",
                "roe",
                "ocf_to_np",
                "debt_ratio",
            ),
        ),
        _latest_fields_by_period(
            balance,
            ("total_equity", "total_assets", "total_liabilities"),
        ),
        _latest_by_period(cash),
    ]
    keys = sorted(set().union(*(source.keys() for source in latest_sources)))
    output: list[dict[str, Any]] = []
    for asset_id, report_period in keys:
        income_row, indicator_row, balance_row, cash_row = [
            source.get((asset_id, report_period)) for source in latest_sources
        ]
        source_rows = [row for row in (income_row, indicator_row, balance_row, cash_row) if row]
        asof = max(row["announcement_date"] for row in source_rows)
        balance_debt_ratio = _finite_ratio(
            (balance_row or {}).get("total_liabilities"),
            (balance_row or {}).get("total_assets"),
        )
        output.append(
            {
                "asset_id": asset_id,
                "report_period": report_period,
                "announcement_date": asof,
                "revenue_ttm": _ttm_at_period(
                    income_by_asset.get(asset_id, []),
                    report_period=report_period,
                    asof=asof,
                    value_column="revenue",
                ),
                "revenue_growth": (indicator_row or {}).get("revenue_yoy"),
                "np_parent_ttm": _ttm_at_period(
                    income_by_asset.get(asset_id, []),
                    report_period=report_period,
                    asof=asof,
                    value_column="np_parent",
                ),
                "profit_growth": (indicator_row or {}).get("np_yoy"),
                "gross_margin": (indicator_row or {}).get("gross_margin"),
                "net_margin": (indicator_row or {}).get("net_margin"),
                "roe": (indicator_row or {}).get("roe"),
                "ocf_to_np": (indicator_row or {}).get("ocf_to_np"),
                "debt_ratio": (
                    balance_debt_ratio
                    if balance_debt_ratio is not None
                    else (indicator_row or {}).get("debt_ratio")
                ),
                "equity_parent": (balance_row or {}).get("total_equity"),
                "operating_cash_flow": _ttm_at_period(
                    cash_by_asset.get(asset_id, []),
                    report_period=report_period,
                    asof=asof,
                    value_column="net_operate_cash_flow",
                ),
                "total_share": (shares_by_asset.get(asset_id) or {}).get("total_share"),
            }
        )
    assets_with_periods = {row["asset_id"] for row in output}
    for asset_id in sorted(set(shares_by_asset) - assets_with_periods):
        share = shares_by_asset[asset_id]
        output.append(
            {
                "asset_id": asset_id,
                "report_period": None,
                "announcement_date": share["announcement_date"],
                "total_share": share.get("total_share"),
            }
        )
    return _sort(_frame(output, FINANCE_COLUMNS), ["asset_id", "report_period", "announcement_date"])


def load_consumer_valuation_history(
    asset_ids: list[str],
    trade_date: str,
    *,
    service: str,
) -> pd.DataFrame:
    assets = _asset_ids(asset_ids)
    cutoff = validate_trade_date(trade_date)
    if not assets:
        return _frame([], VALUATION_COLUMNS)
    sql = """
    SELECT f.asset_id, f.trade_date, f.factor_name, f.factor_value,
           f.computed_at, f.calc_version,
           membership.industry_system, membership.industry_name
    FROM factor.factor_daily f
    LEFT JOIN LATERAL (
        SELECT m.industry_system, m.industry_name
        FROM core.industry_membership m
        WHERE m.asset_id = f.asset_id
          AND m.start_date <= f.trade_date
          AND (m.end_date IS NULL OR f.trade_date < m.end_date)
        ORDER BY m.level DESC, m.start_date DESC, m.industry_system, m.industry_code
        LIMIT 1
    ) membership ON TRUE
    WHERE f.asset_id = ANY(%s)
      AND f.trade_date <= %s
      AND f.trade_date >= %s::date - INTERVAL '5 years'
      AND f.computed_at < ((%s::date + interval '1 day') AT TIME ZONE 'Asia/Shanghai')
      AND f.factor_name IN ('pe_ttm', 'ps_ttm', 'ev_ebitda')
    ORDER BY f.asset_id, f.trade_date, f.factor_name, f.computed_at DESC, f.calc_version DESC
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [assets, cutoff, cutoff, cutoff])
    if not rows:
        return _frame([], VALUATION_COLUMNS)
    raw = pd.DataFrame(rows)
    for column in ("computed_at", "calc_version"):
        if column not in raw.columns or raw[column].isna().any():
            raise ValueError(f"valuation database rows require non-null {column}")
    raw["trade_date"] = raw["trade_date"].map(_date_text)
    raw["computed_at"] = pd.to_datetime(raw["computed_at"], errors="coerce", utc=True)
    if raw["computed_at"].isna().any():
        raise ValueError("valuation database rows contain invalid computed_at")
    cutoff_end = (
        pd.Timestamp(cutoff, tz="Asia/Shanghai") + pd.Timedelta(days=1)
    ).tz_convert("UTC")
    raw = raw.loc[raw["computed_at"].lt(cutoff_end)].copy()
    if raw.empty:
        return _frame([], VALUATION_COLUMNS)
    raw["calc_version"] = raw["calc_version"].astype(str)
    for column in ("industry_system", "industry_name"):
        if column not in raw:
            raw[column] = pd.NA
    raw = raw.sort_values(
        ["asset_id", "trade_date", "factor_name", "computed_at", "calc_version"],
        ascending=[True, True, True, False, False],
        kind="stable",
    ).drop_duplicates(["asset_id", "trade_date", "factor_name"], keep="first")
    pivot_rows: list[dict[str, Any]] = []
    identifiers = ["asset_id", "trade_date", "industry_system", "industry_name"]
    for key, group in raw.groupby(identifiers, dropna=False, sort=False):
        asset_id, valuation_date, industry_system, industry_name = key
        values = dict(zip(group["factor_name"], group["factor_value"], strict=True))
        pivot_rows.append(
            {
                "asset_id": asset_id,
                "valuation_date": valuation_date,
                "pe_ttm": values.get("pe_ttm"),
                "ps_ttm": values.get("ps_ttm"),
                "ev_ebitda": values.get("ev_ebitda"),
                "industry_system": industry_system,
                "industry_name": industry_name,
            }
        )
    result = _frame(pivot_rows, VALUATION_COLUMNS)
    result = result.where(pd.notna(result), None)
    return _sort(result, ["asset_id", "valuation_date", "industry_system", "industry_name"])


def load_consumer_earnings_forecasts(
    asset_ids: list[str],
    trade_date: str,
    *,
    service: str,
) -> pd.DataFrame:
    assets = _asset_ids(asset_ids)
    cutoff = validate_trade_date(trade_date)
    if not assets:
        return _frame([], EARNINGS_COLUMNS)
    forecast_sql = """
    SELECT asset_id, announcement_date, report_period, forecast_type,
           forecast_np_min, forecast_np_max,
           forecast_np_change_min, forecast_np_change_max,
           summary, source, source_endpoint
    FROM event.earnings_forecast
    WHERE asset_id = ANY(%s) AND announcement_date <= %s
    ORDER BY asset_id, announcement_date, report_period, event_id
    """
    express_sql = """
    SELECT asset_id, announcement_date, report_period, revenue, revenue_yoy,
           np_parent, np_parent_yoy, source, source_endpoint
    FROM event.earnings_express
    WHERE asset_id = ANY(%s) AND announcement_date <= %s
    ORDER BY asset_id, announcement_date, report_period, event_id
    """
    with connect(service) as conn:
        forecast_rows = fetch_all(conn, forecast_sql, [assets, cutoff])
        express_rows = fetch_all(conn, express_sql, [assets, cutoff])

    unified: list[dict[str, Any]] = []
    for raw in forecast_rows:
        row = dict(raw)
        row["event_type"] = "forecast"
        unified.append(row)
    for raw in express_rows:
        row = dict(raw)
        row["event_type"] = "express"
        row["np_yoy"] = row.get("np_parent_yoy")
        unified.append(row)
    result = _format_dates(
        _frame(unified, EARNINGS_COLUMNS),
        ("announcement_date", "report_period"),
    )
    return _sort(result, ["asset_id", "announcement_date", "event_type", "report_period"])
