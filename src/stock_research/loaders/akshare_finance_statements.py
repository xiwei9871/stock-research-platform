import math
from typing import Any

import akshare as ak

from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many, fetch_all
from stock_research.loaders.akshare_finance_loader import store_finance_payload


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if value != value:
        return None
    text = str(value).strip()
    if text == "" or text.lower() == "nan":
        return None
    return float(text)


def date_text(value: Any) -> str:
    return str(value)[:10]


def sina_date_text(value: Any) -> str:
    text = str(value).strip()
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return date_text(value)


def report_type_from_period(report_period: str) -> str:
    if str(report_period).endswith("-12-31"):
        return "FY"
    return "Q"


def json_safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe_value(item) for item in value]
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def dataframe_payload(df) -> list[dict[str, Any]]:
    return json_safe_value(df.to_dict("records"))


def asset_id_from_em_secucode(secucode: str) -> str:
    symbol, exchange = str(secucode).split(".", 1)
    return f"CN:{exchange.upper()}:{symbol}"


def report_type_from_em(value: Any) -> str:
    text = str(value)
    if "年" in text:
        return "FY"
    return "Q"


def normalize_em_balance_sheet_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": asset_id_from_em_secucode(str(row["SECUCODE"])),
        "report_period": date_text(row["REPORT_DATE"]),
        "report_type": report_type_from_em(row.get("REPORT_TYPE")),
        "announcement_date": date_text(row["NOTICE_DATE"]),
        "total_assets": parse_float(row.get("TOTAL_ASSETS")),
        "total_liabilities": parse_float(row.get("TOTAL_LIABILITIES")),
        "total_equity": parse_float(row.get("TOTAL_EQUITY")),
        "monetary_funds": parse_float(row.get("MONETARYFUNDS")),
        "accounts_receivable": parse_float(row.get("ACCOUNTS_RECE")),
        "inventory": parse_float(row.get("INVENTORY")),
        "goodwill": parse_float(row.get("GOODWILL")),
        "source": "akshare_em",
    }


def normalize_em_cash_flow_row(row: dict[str, Any]) -> dict[str, Any]:
    operating_cash_flow = parse_float(row.get("NETCASH_OPERATE"))
    capex = parse_float(row.get("CONSTRUCT_LONG_ASSET"))
    free_cash_flow = None
    if operating_cash_flow is not None and capex is not None:
        free_cash_flow = operating_cash_flow - capex
    return {
        "asset_id": asset_id_from_em_secucode(str(row["SECUCODE"])),
        "report_period": date_text(row["REPORT_DATE"]),
        "report_type": report_type_from_em(row.get("REPORT_TYPE")),
        "announcement_date": date_text(row["NOTICE_DATE"]),
        "net_operate_cash_flow": operating_cash_flow,
        "net_invest_cash_flow": parse_float(row.get("NETCASH_INVEST")),
        "net_finance_cash_flow": parse_float(row.get("NETCASH_FINANCE")),
        "capex": capex,
        "free_cash_flow": free_cash_flow,
        "source": "akshare_em",
    }


def normalize_sina_balance_sheet_row(
    row: dict[str, Any],
    asset_id: str,
) -> dict[str, Any]:
    report_period = sina_date_text(row["报告日"])
    return {
        "asset_id": asset_id,
        "report_period": report_period,
        "report_type": report_type_from_period(report_period),
        "announcement_date": sina_date_text(row["公告日期"]),
        "total_assets": parse_float(row.get("资产总计")),
        "total_liabilities": parse_float(row.get("负债合计")),
        "total_equity": parse_float(
            row.get("所有者权益(或股东权益)合计", row.get("所有者权益"))
        ),
        "monetary_funds": parse_float(row.get("货币资金")),
        "accounts_receivable": parse_float(
            row.get("应收账款", row.get("应收票据及应收账款"))
        ),
        "inventory": parse_float(row.get("存货")),
        "goodwill": parse_float(row.get("商誉")),
        "source": "akshare_sina",
    }


def normalize_sina_cash_flow_row(
    row: dict[str, Any],
    asset_id: str,
) -> dict[str, Any]:
    report_period = sina_date_text(row["报告日"])
    operating_cash_flow = parse_float(row.get("经营活动产生的现金流量净额"))
    capex = parse_float(row.get("购建固定资产、无形资产和其他长期资产支付的现金"))
    free_cash_flow = None
    if operating_cash_flow is not None and capex is not None:
        free_cash_flow = operating_cash_flow - capex
    return {
        "asset_id": asset_id,
        "report_period": report_period,
        "report_type": report_type_from_period(report_period),
        "announcement_date": sina_date_text(row["公告日期"]),
        "net_operate_cash_flow": operating_cash_flow,
        "net_invest_cash_flow": parse_float(row.get("投资活动产生的现金流量净额")),
        "net_finance_cash_flow": parse_float(row.get("筹资活动产生的现金流量净额")),
        "capex": capex,
        "free_cash_flow": free_cash_flow,
        "source": "akshare_sina",
    }


def upsert_balance_sheets(conn, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = """
    INSERT INTO finance.balance_sheet (
        asset_id,
        report_period,
        report_type,
        announcement_date,
        total_assets,
        total_liabilities,
        total_equity,
        monetary_funds,
        accounts_receivable,
        inventory,
        goodwill,
        source
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (asset_id, report_period, report_type, announcement_date, source)
    DO UPDATE SET
        total_assets = EXCLUDED.total_assets,
        total_liabilities = EXCLUDED.total_liabilities,
        total_equity = EXCLUDED.total_equity,
        monetary_funds = EXCLUDED.monetary_funds,
        accounts_receivable = EXCLUDED.accounts_receivable,
        inventory = EXCLUDED.inventory,
        goodwill = EXCLUDED.goodwill,
        updated_at = now()
    """
    execute_many(conn, sql, [_balance_tuple(row) for row in rows])
    return len(rows)


def upsert_cash_flows(conn, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = """
    INSERT INTO finance.cash_flow (
        asset_id,
        report_period,
        report_type,
        announcement_date,
        net_operate_cash_flow,
        net_invest_cash_flow,
        net_finance_cash_flow,
        capex,
        free_cash_flow,
        source
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (asset_id, report_period, report_type, announcement_date, source)
    DO UPDATE SET
        net_operate_cash_flow = EXCLUDED.net_operate_cash_flow,
        net_invest_cash_flow = EXCLUDED.net_invest_cash_flow,
        net_finance_cash_flow = EXCLUDED.net_finance_cash_flow,
        capex = EXCLUDED.capex,
        free_cash_flow = EXCLUDED.free_cash_flow,
        updated_at = now()
    """
    execute_many(conn, sql, [_cash_flow_tuple(row) for row in rows])
    return len(rows)


def _balance_tuple(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["asset_id"],
        row["report_period"],
        row["report_type"],
        row["announcement_date"],
        row["total_assets"],
        row["total_liabilities"],
        row["total_equity"],
        row["monetary_funds"],
        row["accounts_receivable"],
        row["inventory"],
        row["goodwill"],
        row["source"],
    )


def _cash_flow_tuple(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["asset_id"],
        row["report_period"],
        row["report_type"],
        row["announcement_date"],
        row["net_operate_cash_flow"],
        row["net_invest_cash_flow"],
        row["net_finance_cash_flow"],
        row["capex"],
        row["free_cash_flow"],
        row["source"],
    )


def sync_finance_statements_for_asset(
    asset_id: str,
    akshare_symbol: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, int]:
    balance_df = ak.stock_balance_sheet_by_report_em(symbol=akshare_symbol)
    cash_df = ak.stock_cash_flow_sheet_by_report_em(symbol=akshare_symbol)
    balance_payload = dataframe_payload(balance_df)
    cash_payload = dataframe_payload(cash_df)
    balance_rows = [
        normalize_em_balance_sheet_row(row)
        for row in balance_payload
        if row.get("NOTICE_DATE")
    ]
    cash_rows = [
        normalize_em_cash_flow_row(row)
        for row in cash_payload
        if row.get("NOTICE_DATE")
    ]
    with connect(service) as conn:
        store_finance_payload(
            conn,
            "stock_balance_sheet_by_report_em",
            {"symbol": akshare_symbol},
            balance_payload,
            asset_id=asset_id,
        )
        store_finance_payload(
            conn,
            "stock_cash_flow_sheet_by_report_em",
            {"symbol": akshare_symbol},
            cash_payload,
            asset_id=asset_id,
        )
        balance_count = upsert_balance_sheets(conn, balance_rows)
        cash_count = upsert_cash_flows(conn, cash_rows)
    return {"balance_sheet": balance_count, "cash_flow": cash_count, "raw_payload": 2}


def akshare_symbol_from_asset_id(asset_id: str) -> str:
    _market, exchange, symbol = asset_id.split(":", 2)
    return f"{exchange}{symbol}"


def sina_stock_code_from_asset_id(asset_id: str) -> str:
    _market, exchange, symbol = asset_id.split(":", 2)
    return f"{exchange.lower()}{symbol}"


def sync_sina_finance_statements_for_asset(
    asset_id: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, int]:
    stock_code = sina_stock_code_from_asset_id(asset_id)
    balance_df = ak.stock_financial_report_sina(stock=stock_code, symbol="资产负债表")
    cash_df = ak.stock_financial_report_sina(stock=stock_code, symbol="现金流量表")
    balance_payload = dataframe_payload(balance_df)
    cash_payload = dataframe_payload(cash_df)
    balance_rows = [
        normalize_sina_balance_sheet_row(row, asset_id)
        for row in balance_payload
        if row.get("报告日") and row.get("公告日期")
    ]
    cash_rows = [
        normalize_sina_cash_flow_row(row, asset_id)
        for row in cash_payload
        if row.get("报告日") and row.get("公告日期")
    ]
    with connect(service) as conn:
        store_finance_payload(
            conn,
            "stock_financial_report_sina",
            {"stock": stock_code, "symbol": "资产负债表"},
            balance_payload,
            asset_id=asset_id,
        )
        store_finance_payload(
            conn,
            "stock_financial_report_sina",
            {"stock": stock_code, "symbol": "现金流量表"},
            cash_payload,
            asset_id=asset_id,
        )
        balance_count = upsert_balance_sheets(conn, balance_rows)
        cash_count = upsert_cash_flows(conn, cash_rows)
    return {"balance_sheet": balance_count, "cash_flow": cash_count, "raw_payload": 2}


def sync_finance_statements_for_assets(
    *,
    limit: int,
    offset: int,
    service: str = SETTINGS.research_service,
) -> dict[str, int]:
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            """
            SELECT asset_id
            FROM core.asset_master
            WHERE akshare_code IS NOT NULL
              AND exchange IN ('SH', 'SZ')
            ORDER BY asset_id
            OFFSET %s
            LIMIT %s
            """,
            [offset, limit],
        )

    totals = {"queried_assets": 0, "balance_sheet": 0, "cash_flow": 0, "raw_payload": 0}
    for row in rows:
        asset_id = str(row["asset_id"])
        counts = sync_finance_statements_for_asset(
            asset_id,
            akshare_symbol_from_asset_id(asset_id),
            service=service,
        )
        totals["queried_assets"] += 1
        totals["balance_sheet"] += int(counts.get("balance_sheet", 0))
        totals["cash_flow"] += int(counts.get("cash_flow", 0))
        totals["raw_payload"] += int(counts.get("raw_payload", 0))
    return totals
