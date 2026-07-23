from stock_research.config import SETTINGS
from stock_research.db import connect, execute
from stock_research.db import execute_many

try:
    import akshare as ak
except Exception:  # pragma: no cover - dependency is optional for non-sync tests
    ak = None


def sync_core_asset_master_for_service(
    service: str = SETTINGS.research_service,
) -> None:
    with connect(service) as conn:
        sync_core_asset_master(conn)


def sync_core_asset_master(conn) -> None:
    sql = """
    INSERT INTO core.asset_master (
        asset_id,
        ts_code,
        baostock_code,
        akshare_code,
        symbol,
        name,
        exchange,
        board,
        list_date,
        delist_date,
        is_active,
        is_beijing,
        is_star,
        is_chinext,
        region,
        source
    )
    SELECT
        asset_id,
        NULL AS ts_code,
        lower(exchange) || '.' || symbol AS baostock_code,
        symbol AS akshare_code,
        symbol,
        name,
        exchange,
        CASE
            WHEN exchange = 'BJ' THEN 'BSE'
            WHEN exchange = 'SH' AND symbol LIKE '688%' THEN 'STAR'
            WHEN exchange = 'SZ' AND symbol ~ '^(300|301|302)' THEN 'CHINEXT'
            WHEN exchange = 'SH' THEN 'SSE_MAIN'
            WHEN exchange = 'SZ' THEN 'SZSE_MAIN'
            ELSE exchange
        END AS board,
        list_date,
        delist_date,
        status = 'listed' AND delist_date IS NULL AS is_active,
        exchange = 'BJ' AS is_beijing,
        exchange = 'SH' AND symbol LIKE '688%' AS is_star,
        exchange = 'SZ' AND symbol ~ '^(300|301|302)' AS is_chinext,
        NULL AS region,
        source
    FROM asset_master
    ON CONFLICT (asset_id) DO UPDATE SET
        ts_code = EXCLUDED.ts_code,
        baostock_code = EXCLUDED.baostock_code,
        akshare_code = EXCLUDED.akshare_code,
        symbol = EXCLUDED.symbol,
        name = EXCLUDED.name,
        exchange = EXCLUDED.exchange,
        board = EXCLUDED.board,
        list_date = EXCLUDED.list_date,
        delist_date = EXCLUDED.delist_date,
        is_active = EXCLUDED.is_active,
        is_beijing = EXCLUDED.is_beijing,
        is_star = EXCLUDED.is_star,
        is_chinext = EXCLUDED.is_chinext,
        region = EXCLUDED.region,
        source = EXCLUDED.source,
        updated_at = now()
    """
    execute(conn, sql)


def sync_chinese_stock_names_from_akshare_for_service(
    service: str = SETTINGS.research_service,
) -> int:
    with connect(service) as conn:
        return sync_chinese_stock_names_from_akshare(conn)


def sync_chinese_stock_names_from_akshare(conn) -> int:
    if ak is None:
        raise RuntimeError("akshare package is required to sync Chinese stock names")
    frame = ak.stock_info_a_code_name()
    rows = _normalize_akshare_code_name_rows(frame)
    if not rows:
        return 0
    public_sql = """
    UPDATE asset_master AS a
    SET
        name = data.name,
        updated_at = now()
    FROM (VALUES (%s, %s, %s)) AS data(symbol, name, ts_code)
    WHERE a.symbol = data.symbol
      AND (a.name IS NULL OR a.name = '' OR a.name = a.symbol OR a.name <> data.name)
    """
    core_sql = """
    UPDATE core.asset_master AS a
    SET
        name = data.name,
        ts_code = data.ts_code,
        updated_at = now()
    FROM (VALUES (%s, %s, %s)) AS data(symbol, name, ts_code)
    WHERE a.symbol = data.symbol
      AND (
          a.name IS NULL OR a.name = '' OR a.name = a.symbol OR a.name <> data.name
          OR a.ts_code IS NULL OR a.ts_code = ''
      )
    """
    execute_many(conn, public_sql, rows)
    execute_many(conn, core_sql, rows)
    return len(rows)


def _normalize_akshare_code_name_rows(frame) -> list[tuple[str, str, str]]:
    if frame is None or frame.empty:
        return []
    code_column = "code" if "code" in frame.columns else "代码"
    name_column = "name" if "name" in frame.columns else "名称"
    if code_column not in frame.columns or name_column not in frame.columns:
        return []
    rows = []
    for row in frame[[code_column, name_column]].dropna().to_dict("records"):
        symbol = str(row[code_column]).strip().zfill(6)
        name = str(row[name_column]).strip()
        if not symbol or not name or name == symbol:
            continue
        if symbol.startswith(("600", "601", "603", "605", "688", "689")):
            exchange = "SH"
        elif symbol.startswith(("000", "001", "002", "003", "300", "301", "302")):
            exchange = "SZ"
        elif symbol.startswith(("43", "83", "87", "92")):
            exchange = "BJ"
        else:
            continue
        rows.append((symbol, name, f"{symbol}.{exchange}"))
    return rows


def build_asset_status_daily_for_service(
    start_date: str | None = None,
    end_date: str | None = None,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> None:
    with connect(service) as conn:
        build_asset_status_daily(conn, start_date, end_date, adjust_type)


def build_asset_status_daily(
    conn,
    start_date: str | None = None,
    end_date: str | None = None,
    adjust_type: str = "hfq",
) -> None:
    filters = ["b.adjust_type = %s"]
    params = [adjust_type]
    if start_date:
        filters.append("b.trade_date >= %s")
        params.append(start_date)
    if end_date:
        filters.append("b.trade_date <= %s")
        params.append(end_date)

    where_sql = " AND ".join(filters)
    limit_threshold_sql = """
        CASE
            WHEN b.is_st THEN 4.8
            WHEN a.is_star OR a.is_chinext OR a.is_beijing THEN 19.8
            ELSE 9.8
        END
    """
    sql = f"""
    INSERT INTO core.asset_status_daily (
        trade_date,
        asset_id,
        is_trade,
        is_st,
        is_suspended,
        is_limit_up,
        is_limit_down,
        limit_up_price,
        limit_down_price,
        source
    )
    SELECT
        b.trade_date,
        b.asset_id,
        b.trade_status = '1' AS is_trade,
        b.is_st,
        b.trade_status <> '1' AS is_suspended,
        b.pct_chg >= {limit_threshold_sql} AS is_limit_up,
        b.pct_chg <= -{limit_threshold_sql} AS is_limit_down,
        CASE
            WHEN b.preclose IS NULL THEN NULL
            ELSE b.preclose * (1 + ({limit_threshold_sql} / 100.0))
        END AS limit_up_price,
        CASE
            WHEN b.preclose IS NULL THEN NULL
            ELSE b.preclose * (1 - ({limit_threshold_sql} / 100.0))
        END AS limit_down_price,
        b.source
    FROM market_daily_bar b
    LEFT JOIN core.asset_master a
      ON a.asset_id = b.asset_id
    WHERE {where_sql}
    ON CONFLICT (trade_date, asset_id) DO UPDATE SET
        is_trade = EXCLUDED.is_trade,
        is_st = EXCLUDED.is_st,
        is_suspended = EXCLUDED.is_suspended,
        is_limit_up = EXCLUDED.is_limit_up,
        is_limit_down = EXCLUDED.is_limit_down,
        limit_up_price = EXCLUDED.limit_up_price,
        limit_down_price = EXCLUDED.limit_down_price,
        source = EXCLUDED.source,
        updated_at = now()
    """
    execute(conn, sql, params)


def build_industry_daily_bars_for_service(
    start_date: str | None = None,
    end_date: str | None = None,
    industry_system: str = "csrc",
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> None:
    with connect(service) as conn:
        build_industry_daily_bars(
            conn,
            start_date=start_date,
            end_date=end_date,
            industry_system=industry_system,
            adjust_type=adjust_type,
        )


def build_industry_daily_bars(
    conn,
    start_date: str | None = None,
    end_date: str | None = None,
    industry_system: str = "csrc",
    adjust_type: str = "hfq",
) -> None:
    filters = [
        "m.industry_system = %s",
        "m.level = 1",
        "b.adjust_type = %s",
        "m.start_date <= b.trade_date",
        "(m.end_date IS NULL OR b.trade_date < m.end_date)",
    ]
    params = [industry_system, adjust_type]
    if start_date:
        filters.append("b.trade_date >= %s")
        params.append(start_date)
    if end_date:
        filters.append("b.trade_date <= %s")
        params.append(end_date)

    where_sql = " AND ".join(filters)
    sql = f"""
    WITH membership AS (
        SELECT
            m.industry_system,
            m.industry_code,
            max(m.industry_name) AS industry_name,
            m.asset_id,
            b.adjust_type,
            b.trade_date
        FROM market_daily_bar b
        JOIN core.industry_membership m
          ON m.asset_id = b.asset_id
        WHERE {where_sql}
        GROUP BY
            m.industry_system,
            m.industry_code,
            m.asset_id,
            b.adjust_type,
            b.trade_date
    )
    INSERT INTO market.industry_daily_bar (
        industry_system,
        industry_code,
        industry_name,
        trade_date,
        open,
        high,
        low,
        close,
        preclose,
        volume,
        amount,
        source
    )
    SELECT
        m.industry_system,
        m.industry_code,
        m.industry_name,
        b.trade_date,
        avg(b.open) AS open,
        max(b.high) AS high,
        min(b.low) AS low,
        avg(b.close) AS close,
        avg(b.preclose) AS preclose,
        sum(b.volume) AS volume,
        sum(b.amount) AS amount,
        'derived:market_daily_bar' AS source
    FROM market_daily_bar b
    JOIN membership m
      ON m.asset_id = b.asset_id
     AND m.adjust_type = b.adjust_type
     AND m.trade_date = b.trade_date
    GROUP BY
        m.industry_system,
        m.industry_code,
        m.industry_name,
        b.trade_date
    ON CONFLICT (industry_system, industry_code, trade_date) DO UPDATE SET
        industry_name = EXCLUDED.industry_name,
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        preclose = EXCLUDED.preclose,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        source = EXCLUDED.source,
        updated_at = now()
    """
    execute(conn, sql, params)
