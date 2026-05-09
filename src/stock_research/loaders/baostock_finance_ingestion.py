from typing import Any

import baostock as bs

from stock_research.assets import asset_id_from_baostock_code
from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many, fetch_all


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    return float(text)


def report_type_from_period(report_period: str) -> str:
    if str(report_period).endswith("-12-31"):
        return "FY"
    return "Q"


def merge_finance_rows(*row_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for rows in row_groups:
        for row in rows:
            key = (str(row["code"]), str(row["pubDate"]), str(row["statDate"]))
            merged.setdefault(key, {}).update(row)
    return [merged[key] for key in sorted(merged)]


def normalize_indicator_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": asset_id_from_baostock_code(str(row["code"])),
        "report_period": str(row["statDate"]),
        "announcement_date": str(row["pubDate"]),
        "roe": parse_float(row.get("roeAvg")),
        "roa": parse_float(row.get("ROA")),
        "gross_margin": parse_float(row.get("gpMargin")),
        "net_margin": parse_float(row.get("npMargin")),
        "debt_ratio": parse_float(row.get("liabilityToAsset")),
        "revenue_yoy": parse_float(row.get("YOYEquity")),
        "np_yoy": parse_float(row.get("YOYNI")),
        "deduct_np_yoy": parse_float(row.get("YOYPNI")),
        "ocf_to_np": parse_float(row.get("CFOToNP")),
        "asset_turnover": parse_float(row.get("AssetTurnRatio")),
        "current_ratio": parse_float(row.get("currentRatio")),
        "quick_ratio": parse_float(row.get("quickRatio")),
        "source": "baostock",
        "calc_version": "baostock_v1",
    }


def normalize_income_row(row: dict[str, Any]) -> dict[str, Any]:
    report_period = str(row["statDate"])
    return {
        "asset_id": asset_id_from_baostock_code(str(row["code"])),
        "report_period": report_period,
        "report_type": report_type_from_period(report_period),
        "announcement_date": str(row["pubDate"]),
        "revenue": parse_float(row.get("MBRevenue")),
        "operating_profit": parse_float(row.get("operateProfit")),
        "total_profit": parse_float(row.get("totalProfit")),
        "net_profit": parse_float(row.get("netProfit")),
        "np_parent": parse_float(row.get("parentNetProfit")),
        "np_parent_deducted": parse_float(row.get("deductParentNetProfit")),
        "eps_basic": parse_float(row.get("epsTTM")),
        "source": "baostock",
    }


def normalize_share_capital_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": asset_id_from_baostock_code(str(row["code"])),
        "event_date": str(row["statDate"]),
        "announcement_date": str(row["pubDate"]),
        "total_share": parse_float(row.get("totalShare")),
        "float_share": parse_float(row.get("liqaShare")),
        "free_float_share": parse_float(row.get("freeFloatShare")),
        "reason": row.get("reason"),
        "source": "baostock",
    }


def upsert_finance_rows(
    conn,
    *,
    indicators: list[dict[str, Any]],
    incomes: list[dict[str, Any]],
    share_capital_events: list[dict[str, Any]],
) -> dict[str, int]:
    indicator_count = upsert_indicator_quarters(conn, indicators)
    income_count = upsert_income_statements(conn, incomes)
    share_count = upsert_share_capital_events(conn, share_capital_events)
    return {
        "indicator_quarter": indicator_count,
        "income_statement": income_count,
        "share_capital_event": share_count,
    }


def upsert_indicator_quarters(conn, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = """
    INSERT INTO finance.indicator_quarter (
        asset_id,
        report_period,
        announcement_date,
        roe,
        roa,
        gross_margin,
        net_margin,
        debt_ratio,
        revenue_yoy,
        np_yoy,
        deduct_np_yoy,
        ocf_to_np,
        asset_turnover,
        current_ratio,
        quick_ratio,
        source,
        calc_version
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (asset_id, report_period, announcement_date, source, calc_version)
    DO UPDATE SET
        roe = EXCLUDED.roe,
        roa = EXCLUDED.roa,
        gross_margin = EXCLUDED.gross_margin,
        net_margin = EXCLUDED.net_margin,
        debt_ratio = EXCLUDED.debt_ratio,
        revenue_yoy = EXCLUDED.revenue_yoy,
        np_yoy = EXCLUDED.np_yoy,
        deduct_np_yoy = EXCLUDED.deduct_np_yoy,
        ocf_to_np = EXCLUDED.ocf_to_np,
        asset_turnover = EXCLUDED.asset_turnover,
        current_ratio = EXCLUDED.current_ratio,
        quick_ratio = EXCLUDED.quick_ratio,
        updated_at = now()
    """
    execute_many(conn, sql, [_indicator_tuple(row) for row in rows])
    return len(rows)


def upsert_income_statements(conn, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = """
    INSERT INTO finance.income_statement (
        asset_id,
        report_period,
        report_type,
        announcement_date,
        revenue,
        operating_profit,
        total_profit,
        net_profit,
        np_parent,
        np_parent_deducted,
        eps_basic,
        source
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (asset_id, report_period, report_type, announcement_date, source)
    DO UPDATE SET
        revenue = EXCLUDED.revenue,
        operating_profit = EXCLUDED.operating_profit,
        total_profit = EXCLUDED.total_profit,
        net_profit = EXCLUDED.net_profit,
        np_parent = EXCLUDED.np_parent,
        np_parent_deducted = EXCLUDED.np_parent_deducted,
        eps_basic = EXCLUDED.eps_basic,
        updated_at = now()
    """
    execute_many(conn, sql, [_income_tuple(row) for row in rows])
    return len(rows)


def upsert_share_capital_events(conn, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = """
    INSERT INTO finance.share_capital_event (
        asset_id,
        event_date,
        announcement_date,
        total_share,
        float_share,
        free_float_share,
        reason,
        source
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (asset_id, event_date, source)
    DO UPDATE SET
        announcement_date = EXCLUDED.announcement_date,
        total_share = EXCLUDED.total_share,
        float_share = EXCLUDED.float_share,
        free_float_share = EXCLUDED.free_float_share,
        reason = EXCLUDED.reason,
        updated_at = now()
    """
    execute_many(conn, sql, [_share_capital_tuple(row) for row in rows])
    return len(rows)


def _indicator_tuple(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["asset_id"],
        row["report_period"],
        row["announcement_date"],
        row["roe"],
        row["roa"],
        row["gross_margin"],
        row["net_margin"],
        row["debt_ratio"],
        row["revenue_yoy"],
        row["np_yoy"],
        row["deduct_np_yoy"],
        row["ocf_to_np"],
        row["asset_turnover"],
        row["current_ratio"],
        row["quick_ratio"],
        row["source"],
        row["calc_version"],
    )


def _income_tuple(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["asset_id"],
        row["report_period"],
        row["report_type"],
        row["announcement_date"],
        row["revenue"],
        row["operating_profit"],
        row["total_profit"],
        row["net_profit"],
        row["np_parent"],
        row["np_parent_deducted"],
        row["eps_basic"],
        row["source"],
    )


def _share_capital_tuple(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["asset_id"],
        row["event_date"],
        row["announcement_date"],
        row["total_share"],
        row["float_share"],
        row["free_float_share"],
        row["reason"],
        row["source"],
    )


def _rows_from_result(rs) -> list[dict[str, str]]:
    rows = []
    while rs.next():
        rows.append(dict(zip(rs.fields, rs.get_row_data(), strict=True)))
    return rows


def _query_rows(func, code: str, year: int, quarter: int) -> list[dict[str, str]]:
    rs = func(code=code, year=year, quarter=quarter)
    if rs.error_code != "0":
        raise RuntimeError(
            f"baostock finance query failed for {code}: {rs.error_code} {rs.error_msg}"
        )
    return _rows_from_result(rs)


def _baostock_codes(
    conn,
    limit: int | None = None,
    offset: int = 0,
) -> list[str]:
    sql = """
    SELECT baostock_code
    FROM core.asset_master
    WHERE baostock_code IS NOT NULL
      AND exchange IN ('SH', 'SZ')
    ORDER BY asset_id
    """
    rows = fetch_all(conn, sql)
    codes = [row["baostock_code"] for row in rows]
    sliced = codes[offset:]
    return sliced[:limit] if limit is not None else sliced


def sync_finance_for_period(
    year: int,
    quarter: int,
    *,
    limit: int | None = None,
    offset: int = 0,
    service: str = SETTINGS.research_service,
) -> dict[str, int]:
    with connect(service) as conn:
        codes = _baostock_codes(conn, limit, offset)

    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"baostock login failed: {login.error_code} {login.error_msg}")
    try:
        indicators = []
        incomes = []
        share_capital_events = []
        for code in codes:
            print(f"baostock_finance_query|{code}", flush=True)
            profit_rows = _query_rows(bs.query_profit_data, code, year, quarter)
            merged_rows = merge_finance_rows(
                profit_rows,
                _query_rows(bs.query_balance_data, code, year, quarter),
                _query_rows(bs.query_cash_flow_data, code, year, quarter),
                _query_rows(bs.query_growth_data, code, year, quarter),
                _query_rows(bs.query_operation_data, code, year, quarter),
                _query_rows(bs.query_dupont_data, code, year, quarter),
            )
            for row in merged_rows:
                indicators.append(normalize_indicator_row(row))
            for row in profit_rows:
                incomes.append(normalize_income_row(row))
                share_capital_events.append(normalize_share_capital_row(row))

        with connect(service) as conn:
            counts = upsert_finance_rows(
                conn,
                indicators=indicators,
                incomes=incomes,
                share_capital_events=share_capital_events,
            )
        counts["queried_assets"] = len(codes)
        return counts
    finally:
        bs.logout()
