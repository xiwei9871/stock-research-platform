"""Database-only point-in-time inputs for the rolling oversold workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from stock_research.consumer_oversold.loaders import (
    FINANCE_COLUMNS,
    VALUATION_COLUMNS,
    load_consumer_finance_history,
    load_consumer_valuation_history,
)
from stock_research.db import connect, fetch_all

from .contracts import RollingOversoldConfig


TRADING_DATE_COLUMNS = ("trade_date",)
INDEX_BAR_COLUMNS = ("index_id", "trade_date", "close", "preclose", "volume", "amount")
STOCK_BAR_COLUMNS = (
    "asset_id", "trade_date", "close", "high", "low", "pct_chg", "volume", "amount",
)
STOCK_STATUS_COLUMNS = (
    "asset_id", "trade_date", "is_trade", "is_st", "is_suspended", "is_limit_up", "is_limit_down",
)
INDUSTRY_MEMBERSHIP_COLUMNS = (
    "asset_id", "industry_system", "industry_code", "industry_name", "level", "start_date", "end_date",
)
CONCEPT_MEMBERSHIP_COLUMNS = (
    "asset_id", "concept_system", "concept_code", "concept_name", "start_date", "end_date",
)
INDUSTRY_BAR_COLUMNS = (
    "industry_system", "industry_code", "industry_name", "trade_date", "close", "preclose", "volume", "amount",
)
CONCEPT_BAR_COLUMNS = (
    "concept_system", "concept_code", "concept_name", "trade_date", "close", "preclose", "volume", "amount",
)


@dataclass(frozen=True)
class RollingInputs:
    anchor_date: date
    data_cutoff_date: date
    trading_dates: pd.DataFrame
    index_bars: pd.DataFrame
    stock_bars: pd.DataFrame
    stock_status: pd.DataFrame
    industry_membership: pd.DataFrame
    concept_membership: pd.DataFrame
    industry_bars: pd.DataFrame
    concept_bars: pd.DataFrame
    finance: pd.DataFrame
    valuation: pd.DataFrame
    index_ids: tuple[str, ...] = ()
    score_version: str = "rolling_oversold_v1"


def load_rolling_inputs(
    *, anchor_date: date, config: RollingOversoldConfig, service: str
) -> RollingInputs:
    """Read all rolling-strategy inputs from the configured database only."""
    if not isinstance(anchor_date, date):
        raise TypeError("anchor_date must be a date")
    if not isinstance(config, RollingOversoldConfig):
        raise TypeError("config must be a RollingOversoldConfig")

    anchor = anchor_date.isoformat()
    history_sql = """
    SELECT DISTINCT trade_date
    FROM market.trading_calendar
    WHERE is_open = TRUE
      AND trade_date <= %s
    ORDER BY trade_date DESC
    LIMIT %s
    """
    with connect(service) as conn:
        history_rows = fetch_all(conn, history_sql, [anchor, 252])
        history_dates = _dates_from_rows(history_rows)
        if not history_dates:
            raise ValueError(
                "no complete open trading session exists on or before anchor_date"
            )
        cutoff = max(history_dates)
        history_start = min(history_dates)
        cutoff_text = cutoff.isoformat()
        history_start_text = history_start.isoformat()
        future_rows = fetch_all(
            conn,
            """
            SELECT DISTINCT trade_date
            FROM market.trading_calendar
            WHERE is_open = TRUE
              AND trade_date > %s
            ORDER BY trade_date
            LIMIT %s
            """,
            [cutoff_text, max(config.forecast_horizons)],
        )
        index_rows = fetch_all(
            conn,
            """
            SELECT index_id, trade_date, close, preclose, volume, amount
            FROM market.index_daily_bar
            WHERE index_id = ANY(%s)
              AND trade_date BETWEEN %s AND %s
            ORDER BY index_id, trade_date
            """,
            [list(config.index_ids), history_start_text, cutoff_text],
        )
        stock_rows = fetch_all(
            conn,
            """
            SELECT asset_id, trade_date, close, high, low, pct_chg, volume, amount
            FROM market_daily_bar
            WHERE adjust_type = %s
              AND trade_date BETWEEN %s AND %s
            ORDER BY asset_id, trade_date
            """,
            [config.adjust_type, history_start_text, cutoff_text],
        )
        status_rows = fetch_all(
            conn,
            """
            SELECT DISTINCT ON (asset_id)
                   asset_id, trade_date, is_trade, is_st, is_suspended,
                   is_limit_up, is_limit_down
            FROM core.asset_status_daily
            WHERE trade_date BETWEEN %s AND %s
            ORDER BY asset_id, trade_date DESC
            """,
            [history_start_text, cutoff_text],
        )
        industry_membership_rows = fetch_all(
            conn,
            _membership_sql("core.industry_membership", "industry", config.industry_systems),
            _membership_params(anchor, config.industry_systems),
        )
        concept_membership_rows = fetch_all(
            conn,
            _membership_sql("core.concept_membership", "concept", config.concept_systems),
            _membership_params(anchor, config.concept_systems),
        )
        industry_rows = fetch_all(
            conn,
            _sector_bar_sql("industry", config.industry_systems),
            _sector_bar_params(
                history_start_text,
                cutoff_text,
                config.industry_systems,
            ),
        )
        concept_rows = fetch_all(
            conn,
            _sector_bar_sql("concept", config.concept_systems),
            _sector_bar_params(
                history_start_text,
                cutoff_text,
                config.concept_systems,
            ),
        )

    future_dates = _dates_from_rows(future_rows)
    trading_dates = _frame(
        [{"trade_date": value} for value in sorted(set(history_dates + future_dates))],
        TRADING_DATE_COLUMNS,
        ("trade_date",),
        ("trade_date",),
    )
    industry_membership = _frame(
        industry_membership_rows, INDUSTRY_MEMBERSHIP_COLUMNS,
        ("start_date", "end_date"), ("asset_id", "industry_system", "industry_code", "level"),
    )
    concept_membership = _frame(
        concept_membership_rows, CONCEPT_MEMBERSHIP_COLUMNS,
        ("start_date", "end_date"), ("asset_id", "concept_system", "concept_code"),
    )
    asset_ids = sorted(
        {
            str(value).strip()
            for frame in (industry_membership, concept_membership)
            for value in frame.get("asset_id", pd.Series(dtype="object"))
            if str(value).strip()
        }
    )
    finance = _normalize_external_frame(
        load_consumer_finance_history(
            asset_ids,
            anchor,
            service=service,
            # A cumulative Q1/Q2/Q3 row may need the prior same quarter plus
            # the prior fiscal year.  With all quarters present that anchor
            # can be the fifth distinct disclosed period, so four rows are
            # insufficient for point-in-time TTM reconstruction.
            max_report_periods=5,
        ),
        FINANCE_COLUMNS,
        ("report_period", "announcement_date"),
        ("asset_id", "report_period", "announcement_date"),
    )
    valuation = _normalize_external_frame(
        load_consumer_valuation_history(
            asset_ids,
            anchor,
            service=service,
            latest_only=True,
        ),
        VALUATION_COLUMNS,
        ("valuation_date",),
        ("asset_id", "valuation_date", "industry_system", "industry_name"),
    )
    return RollingInputs(
        anchor_date=anchor_date,
        data_cutoff_date=cutoff,
        trading_dates=trading_dates,
        index_bars=_frame(index_rows, INDEX_BAR_COLUMNS, ("trade_date",), ("index_id", "trade_date")),
        stock_bars=_frame(stock_rows, STOCK_BAR_COLUMNS, ("trade_date",), ("asset_id", "trade_date")),
        stock_status=_frame(status_rows, STOCK_STATUS_COLUMNS, ("trade_date",), ("asset_id", "trade_date")),
        industry_membership=industry_membership,
        concept_membership=concept_membership,
        industry_bars=_frame(industry_rows, INDUSTRY_BAR_COLUMNS, ("trade_date",), ("industry_system", "industry_code", "trade_date")),
        concept_bars=_frame(concept_rows, CONCEPT_BAR_COLUMNS, ("trade_date",), ("concept_system", "concept_code", "trade_date")),
        finance=finance,
        valuation=valuation,
        index_ids=tuple(config.index_ids),
        score_version=config.score_version,
    )


def _membership_sql(table: str, prefix: str, systems: tuple[str, ...] | None) -> str:
    system_clause = f"\n      AND m.{prefix}_system = ANY(%s)" if systems is not None else ""
    columns = (
        f"m.asset_id, m.{prefix}_system, m.{prefix}_code, m.{prefix}_name, "
        "m.start_date, m.end_date"
        if prefix == "concept"
        else "m.asset_id, m.industry_system, m.industry_code, m.industry_name, "
        "m.level, m.start_date, m.end_date"
    )
    return f"""
    SELECT {columns}
    FROM {table} m
    JOIN core.asset_master a ON a.asset_id = m.asset_id
    WHERE m.start_date <= %s
      AND (m.end_date IS NULL OR m.end_date > %s)
      AND (a.list_date IS NULL OR a.list_date <= %s)
      AND (a.delist_date IS NULL OR a.delist_date > %s)
      AND COALESCE(a.exchange, '') <> 'BJ'{system_clause}
    ORDER BY m.asset_id, m.{prefix}_system, m.{prefix}_code, m.start_date
    """


def _membership_params(cutoff: str, systems: tuple[str, ...] | None) -> list[Any]:
    return [cutoff, cutoff, cutoff, cutoff, *([list(systems)] if systems is not None else [])]


def _sector_bar_sql(
    prefix: str,
    systems: tuple[str, ...] | None,
) -> str:
    system_clause = f"\n      AND {prefix}_system = ANY(%s)" if systems is not None else ""
    return f"""
    SELECT {prefix}_system, {prefix}_code, {prefix}_name,
           trade_date, close, preclose, volume, amount
    FROM market.{prefix}_daily_bar
    WHERE trade_date BETWEEN %s AND %s{system_clause}
    ORDER BY {prefix}_system, {prefix}_code, trade_date
    """


def _sector_bar_params(
    history_start: str, cutoff: str, systems: tuple[str, ...] | None
) -> list[Any]:
    return [history_start, cutoff, *([list(systems)] if systems is not None else [])]


def _dates_from_rows(rows: list[dict[str, Any]]) -> list[date]:
    dates: list[date] = []
    for row in rows:
        value = _date_value(row.get("trade_date"))
        if value is not None:
            dates.append(value)
    return dates


def _date_value(value: object) -> date | None:
    if value is None or pd.isna(value):
        return None
    try:
        return pd.Timestamp(value).date()
    except (TypeError, ValueError, OverflowError):
        return None


def _frame(
    rows: list[dict[str, Any]], columns: tuple[str, ...], date_columns: tuple[str, ...], sort_columns: tuple[str, ...]
) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=list(columns))
    for column in date_columns:
        parsed = pd.to_datetime(frame[column], errors="coerce")
        frame[column] = parsed.dt.strftime("%Y-%m-%d").astype("string")
    if not frame.empty:
        frame = frame.sort_values(list(sort_columns), kind="stable", na_position="last")
    return frame.reset_index(drop=True)


def _normalize_external_frame(
    frame: pd.DataFrame, columns: tuple[str, ...], date_columns: tuple[str, ...], sort_columns: tuple[str, ...]
) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("database loader must return a pandas DataFrame")
    rows = frame.reindex(columns=list(columns)).to_dict(orient="records")
    return _frame(rows, columns, date_columns, sort_columns)
