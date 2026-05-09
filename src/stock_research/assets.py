import re

from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many, fetch_all


TABLE_RE = re.compile(
    r"^(sh(600|601|603|605|688|689)\d{3}|sz(000|001|002|003|300|301|302)\d{3}|bj\d{6})$"
)


def is_stock_table(table_name: str) -> bool:
    return TABLE_RE.fullmatch(table_name) is not None


def asset_id_from_baostock_code(code: str) -> str:
    validated_code = baostock_code_from_table(table_from_baostock_code(code))
    exchange, symbol = validated_code.split(".", 1)
    return f"CN:{exchange.upper()}:{symbol}"


def table_from_baostock_code(code: str) -> str:
    table_name = code.lower().replace(".", "")
    if not is_stock_table(table_name):
        raise ValueError(f"Invalid stock table name derived from Baostock code: {code}")
    return table_name


def baostock_code_from_table(table_name: str) -> str:
    if not is_stock_table(table_name):
        raise ValueError(f"Invalid stock table name: {table_name}")
    return f"{table_name[:2]}.{table_name[2:]}"


def discover_source_tables(service: str) -> list[str]:
    sql = """
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_type = 'BASE TABLE'
      AND (table_name LIKE 'sh%' OR table_name LIKE 'sz%' OR table_name LIKE 'bj%')
    ORDER BY table_name
    """
    with connect(service) as conn:
        return [row["table_name"] for row in fetch_all(conn, sql) if is_stock_table(row["table_name"])]


def infer_asset_rows(table_names: list[str], source: str = "baostock") -> list[tuple]:
    rows = []
    for table_name in table_names:
        code = baostock_code_from_table(table_name)
        exchange = code[:2].upper()
        symbol = code[3:]
        rows.append(
            (
                asset_id_from_baostock_code(code),
                SETTINGS.default_market,
                symbol,
                exchange,
                symbol,
                SETTINGS.default_currency,
                "",
                "listed",
                None,
                None,
                source,
            )
        )
    return rows


def sync_asset_master(
    source_service: str = SETTINGS.hfq_service,
    research_service: str = SETTINGS.research_service,
) -> int:
    tables = discover_source_tables(source_service)
    rows = infer_asset_rows(tables)
    sql = """
    INSERT INTO asset_master (
        asset_id, market, symbol, exchange, name, currency, industry, status,
        list_date, delist_date, source
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (asset_id) DO UPDATE SET
        market = EXCLUDED.market,
        symbol = EXCLUDED.symbol,
        exchange = EXCLUDED.exchange,
        currency = EXCLUDED.currency,
        source = EXCLUDED.source,
        updated_at = now()
    """
    with connect(research_service) as conn:
        execute_many(conn, sql, rows)
    return len(rows)
