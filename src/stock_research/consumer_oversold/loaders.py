from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

from stock_research.db import connect, fetch_all
from stock_research.services.finance_ttm import calc_ttm_from_cumulative_rows

from .contracts import validate_trade_date


ASSET_COLUMNS = ("asset_id", "stock_code", "name", "list_date")
STATUS_COLUMNS = ("asset_id", "is_st", "is_delisting_risk", "is_suspended")
LIQUIDITY_COLUMNS = ("asset_id", "avg_turnover_amount")
INDUSTRY_COLUMNS = ("asset_id", "industry_system", "industry_name")
MARKET_COLUMNS = ("asset_id", "trade_date", "close")
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
    liquidity_sql = """
    WITH latest_dates AS (
        SELECT DISTINCT trade_date
        FROM market_daily_bar
        WHERE trade_date <= %s
          AND adjust_type = 'hfq'
        ORDER BY trade_date DESC
        LIMIT 20
    )
    SELECT b.asset_id, AVG(b.amount) AS avg_turnover_amount
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
                   PARTITION BY asset_id, industry_system
                   ORDER BY level DESC, start_date DESC, industry_code
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
    return {
        "assets": _sort(assets, ["asset_id"]),
        "statuses": _sort(_frame(status_rows, STATUS_COLUMNS), ["asset_id"]),
        "liquidity": _sort(_frame(liquidity_rows, LIQUIDITY_COLUMNS), ["asset_id"]),
        "industries": _sort(
            _frame(industry_rows, INDUSTRY_COLUMNS),
            ["asset_id", "industry_system", "industry_name"],
        ),
    }


def load_consumer_market_history(
    trade_date: str,
    *,
    service: str,
) -> pd.DataFrame:
    cutoff = validate_trade_date(trade_date)
    sql = """
    WITH latest_dates AS (
        SELECT DISTINCT trade_date
        FROM market_daily_bar
        WHERE trade_date <= %s
          AND adjust_type = 'hfq'
        ORDER BY trade_date DESC
        LIMIT %s
    )
    SELECT b.asset_id, b.trade_date, b.close
    FROM market_daily_bar b
    JOIN latest_dates d ON d.trade_date = b.trade_date
    WHERE b.adjust_type = 'hfq'
    ORDER BY b.asset_id, b.trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [cutoff, 260])
    result = _format_dates(_frame(rows, MARKET_COLUMNS), ("trade_date",))
    return _sort(result, ["asset_id", "trade_date"])


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


def _ttm_at_period(
    rows: list[dict[str, Any]],
    *,
    asset_id: str,
    report_period: str,
    asof: str,
    value_column: str,
) -> float | None:
    available = [
        row
        for row in rows
        if row["asset_id"] == asset_id
        and row["report_period"] <= report_period
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
        SELECT asset_id, report_period, announcement_date, total_equity, source
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
    with connect(service) as conn:
        raw_income, raw_indicator, raw_balance, raw_cash = [
            fetch_all(conn, sql, [assets, cutoff]) for sql in queries
        ]

    income = _disclosed_rows(raw_income, cutoff)
    indicator = _disclosed_rows(raw_indicator, cutoff)
    balance = _disclosed_rows(raw_balance, cutoff)
    cash = _disclosed_rows(raw_cash, cutoff)
    latest_sources = [
        _latest_by_period(source_rows)
        for source_rows in (income, indicator, balance, cash)
    ]
    keys = sorted(set().union(*(source.keys() for source in latest_sources)))
    output: list[dict[str, Any]] = []
    for asset_id, report_period in keys:
        income_row, indicator_row, balance_row, cash_row = [
            source.get((asset_id, report_period)) for source in latest_sources
        ]
        source_rows = [row for row in (income_row, indicator_row, balance_row, cash_row) if row]
        asof = max(row["announcement_date"] for row in source_rows)
        output.append(
            {
                "asset_id": asset_id,
                "report_period": report_period,
                "announcement_date": asof,
                "revenue_ttm": _ttm_at_period(
                    income,
                    asset_id=asset_id,
                    report_period=report_period,
                    asof=asof,
                    value_column="revenue",
                ),
                "revenue_growth": (indicator_row or {}).get("revenue_yoy"),
                "np_parent_ttm": _ttm_at_period(
                    income,
                    asset_id=asset_id,
                    report_period=report_period,
                    asof=asof,
                    value_column="np_parent",
                ),
                "profit_growth": (indicator_row or {}).get("np_yoy"),
                "gross_margin": (indicator_row or {}).get("gross_margin"),
                "net_margin": (indicator_row or {}).get("net_margin"),
                "roe": (indicator_row or {}).get("roe"),
                "ocf_to_np": (indicator_row or {}).get("ocf_to_np"),
                "debt_ratio": (indicator_row or {}).get("debt_ratio"),
                "equity_parent": (balance_row or {}).get("total_equity"),
                "operating_cash_flow": _ttm_at_period(
                    cash,
                    asset_id=asset_id,
                    report_period=report_period,
                    asof=asof,
                    value_column="net_operate_cash_flow",
                ),
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
      AND f.computed_at::date <= %s
      AND f.factor_name IN ('pe_ttm', 'ps_ttm', 'ev_ebitda')
    ORDER BY f.asset_id, f.trade_date, f.factor_name, f.computed_at DESC, f.calc_version DESC
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [assets, cutoff, cutoff, cutoff])
    if not rows:
        return _frame([], VALUATION_COLUMNS)
    raw = pd.DataFrame(rows)
    raw["trade_date"] = raw["trade_date"].map(_date_text)
    if "computed_at" not in raw:
        raw["computed_at"] = pd.NaT
    else:
        visible_version = raw["computed_at"].map(
            lambda value: pd.isna(value) or _date_text(value) <= cutoff
        )
        raw = raw.loc[visible_version].copy()
        if raw.empty:
            return _frame([], VALUATION_COLUMNS)
        raw["computed_at"] = pd.to_datetime(raw["computed_at"], errors="coerce", utc=True)
    if "calc_version" not in raw:
        raw["calc_version"] = ""
    else:
        raw["calc_version"] = raw["calc_version"].fillna("").astype(str)
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
