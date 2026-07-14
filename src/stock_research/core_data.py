from stock_research.config import SETTINGS
from stock_research.db import connect, execute
from stock_research.db import execute_many
from stock_research.eastmoney_http import curl_eastmoney_json

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
        CAST(NULL AS text) AS region,
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
        region = COALESCE(NULLIF(a.region, ''), EXCLUDED.region),
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
    INSERT INTO asset_master (
        asset_id, market, symbol, exchange, name, currency, status, source, updated_at
    )
    VALUES (%s, %s, %s, %s, %s, %s, 'listed', 'akshare:stock_info_a_code_name', now())
    ON CONFLICT (asset_id) DO UPDATE SET
        market = EXCLUDED.market,
        symbol = EXCLUDED.symbol,
        exchange = EXCLUDED.exchange,
        name = EXCLUDED.name,
        currency = EXCLUDED.currency,
        updated_at = now()
    """
    core_sql = """
    INSERT INTO core.asset_master (
        asset_id,
        ts_code,
        akshare_code,
        symbol,
        name,
        exchange,
        board,
        is_active,
        is_beijing,
        is_star,
        is_chinext,
        source,
        updated_at
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'akshare:stock_info_a_code_name', now())
    ON CONFLICT (asset_id) DO UPDATE SET
        ts_code = EXCLUDED.ts_code,
        akshare_code = EXCLUDED.akshare_code,
        symbol = EXCLUDED.symbol,
        name = EXCLUDED.name,
        exchange = EXCLUDED.exchange,
        board = EXCLUDED.board,
        is_active = EXCLUDED.is_active,
        is_beijing = EXCLUDED.is_beijing,
        is_star = EXCLUDED.is_star,
        is_chinext = EXCLUDED.is_chinext,
        updated_at = now()
    """
    public_rows = [
        (asset_id, SETTINGS.default_market, symbol, exchange, name, SETTINGS.default_currency)
        for asset_id, symbol, name, exchange, _ts_code in rows
    ]
    core_rows = [
        (
            asset_id,
            ts_code,
            symbol,
            symbol,
            name,
            exchange,
            _asset_board(symbol, exchange),
            True,
            exchange == "BJ",
            exchange == "SH" and symbol.startswith("688"),
            exchange == "SZ" and symbol.startswith(("300", "301", "302")),
        )
        for asset_id, symbol, name, exchange, ts_code in rows
    ]
    execute_many(conn, public_sql, public_rows)
    execute_many(conn, core_sql, core_rows)
    return len(rows)


def _normalize_akshare_code_name_rows(frame) -> list[tuple[str, str, str, str, str]]:
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
        rows.append((f"CN:{exchange}:{symbol}", symbol, name, exchange, f"{symbol}.{exchange}"))
    return rows


def _asset_board(symbol: str, exchange: str) -> str:
    if exchange == "BJ":
        return "BSE"
    if exchange == "SH" and symbol.startswith("688"):
        return "STAR"
    if exchange == "SZ" and symbol.startswith(("300", "301", "302")):
        return "CHINEXT"
    if exchange == "SH":
        return "SSE_MAIN"
    return "SZSE_MAIN"


def sync_concept_memberships_from_akshare(
    conn,
    *,
    trade_date: str,
    concept_system: str = "em",
    board_fetcher=None,
    constituent_fetcher=None,
    max_concepts: int | None = None,
) -> dict[str, object]:
    if ak is None and (board_fetcher is None or constituent_fetcher is None):
        raise RuntimeError("akshare is required to sync concept memberships")

    default_em_fetchers = board_fetcher is None and constituent_fetcher is None and concept_system == "em"
    if default_em_fetchers:
        board_fetcher = fetch_eastmoney_concept_boards_direct
        constituent_fetcher = ak.stock_board_concept_cons_em
        board_source = "eastmoney:qt_clist_concept_board"
        constituent_source = "akshare:stock_board_concept_cons_em"
    else:
        board_fetcher = board_fetcher or ak.stock_board_concept_name_ths
        constituent_fetcher = constituent_fetcher or ak.stock_board_concept_cons_em
        board_source = "akshare:stock_board_concept_name_ths"
        constituent_source = "akshare:concept_constituents"
    try:
        boards = _normalize_concept_boards(_call_with_single_retry(board_fetcher))
    except Exception as exc:  # noqa: BLE001 - vendor board-list failures should be reported, not crash cron.
        return {
            "boards": 0,
            "memberships": 0,
            "failed_concepts": [f"board_fetch_failed: {exc}"],
        }
    if max_concepts is not None:
        boards = boards[: max(0, int(max_concepts))]

    board_rows = [
        (
            concept_system,
            board["concept_code"],
            board["concept_name"],
            board_source,
            True,
        )
        for board in boards
    ]
    if board_rows:
        board_sql = """
        INSERT INTO core.concept_board (
            concept_system,
            concept_code,
            concept_name,
            source,
            is_active
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (concept_system, concept_code) DO UPDATE SET
            concept_name = EXCLUDED.concept_name,
            source = EXCLUDED.source,
            is_active = EXCLUDED.is_active,
            updated_at = now()
        """
        execute_many(conn, board_sql, board_rows)

    membership_rows: list[tuple[str, str, str, str, str, str]] = []
    failed_concepts: list[str] = []
    current_assets_by_concept: dict[str, list[str]] = {}
    for board in boards:
        concept_code = board["concept_code"]
        concept_name = board["concept_name"]
        constituent_symbol = concept_code if default_em_fetchers else concept_name
        try:
            constituents = _normalize_concept_constituents(
                _call_with_single_retry(constituent_fetcher, constituent_symbol)
            )
        except Exception:  # noqa: BLE001 - vendor failures should not erase local concept history.
            failed_concepts.append(concept_name)
            continue

        current_assets: list[str] = []
        for asset_id in constituents:
            current_assets.append(asset_id)
            membership_rows.append(
                (
                    asset_id,
                    concept_system,
                    concept_code,
                    concept_name,
                    trade_date,
                    constituent_source,
                )
            )
        current_assets_by_concept[concept_code] = current_assets

    if membership_rows:
        membership_sql = """
        INSERT INTO core.concept_membership (
            asset_id,
            concept_system,
            concept_code,
            concept_name,
            start_date,
            source
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (asset_id, concept_system, concept_code, start_date) DO UPDATE SET
            concept_name = EXCLUDED.concept_name,
            source = EXCLUDED.source,
            updated_at = now()
        """
        execute_many(conn, membership_sql, membership_rows)

    close_sql = """
    UPDATE core.concept_membership
    SET end_date = %s,
        updated_at = now()
    WHERE concept_system = %s
      AND concept_code = %s
      AND end_date IS NULL
      AND start_date < %s
      AND NOT (asset_id = ANY(%s))
    """
    for concept_code, current_assets in current_assets_by_concept.items():
        execute(conn, close_sql, [trade_date, concept_system, concept_code, trade_date, current_assets])

    return {
        "boards": len(board_rows),
        "memberships": len(membership_rows),
        "failed_concepts": failed_concepts,
    }


def _normalize_concept_boards(frame) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if frame is None or frame.empty:
        return rows
    for item in frame.to_dict("records"):
        concept_name = str(item.get("name") or item.get("概念名称") or item.get("板块名称") or "").strip()
        concept_code = str(item.get("code") or item.get("代码") or item.get("板块代码") or concept_name).strip()
        if concept_name and concept_code:
            rows.append({"concept_code": concept_code, "concept_name": concept_name})
    return rows


def fetch_eastmoney_concept_boards_direct(
    *,
    page_size: int = 100,
    retries: int = 3,
    retry_sleep_seconds: float = 1.0,
):
    import pandas as pd

    url_candidates = [
        "https://79.push2.eastmoney.com/api/qt/clist/get",
        "https://push2.eastmoney.com/api/qt/clist/get",
    ]
    fields = "f12,f14"
    base_params = {
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f12",
        "fs": "m:90 t:3 f:!50",
        "fields": fields,
    }
    first = curl_eastmoney_json(
        url_candidates,
        {**base_params, "pn": "1", "pz": str(page_size)},
        retries=retries,
        retry_sleep_seconds=retry_sleep_seconds,
    )
    data = first.get("data") or {}
    rows = list(data.get("diff") or [])
    total = int(data.get("total") or len(rows))
    pages = max(1, (total + page_size - 1) // page_size)
    for page in range(2, pages + 1):
        payload = curl_eastmoney_json(
            url_candidates,
            {**base_params, "pn": str(page), "pz": str(page_size)},
            retries=retries,
            retry_sleep_seconds=retry_sleep_seconds,
        )
        rows.extend((payload.get("data") or {}).get("diff") or [])
    return pd.DataFrame(
        [
            {"板块名称": str(row.get("f14") or "").strip(), "板块代码": str(row.get("f12") or "").strip()}
            for row in rows
            if str(row.get("f14") or "").strip() and str(row.get("f12") or "").strip()
        ]
    )


def _call_with_single_retry(func, *args):
    last_error = None
    for _attempt in range(2):
        try:
            return func(*args)
        except Exception as exc:  # noqa: BLE001 - external data vendors often fail transiently.
            last_error = exc
    raise last_error


def _normalize_concept_constituents(frame) -> list[str]:
    if frame is None or frame.empty:
        return []
    assets: list[str] = []
    for item in frame.to_dict("records"):
        raw_code = str(item.get("代码") or item.get("code") or item.get("股票代码") or "").strip()
        asset_id = _asset_id_from_cn_stock_code(raw_code)
        if asset_id:
            assets.append(asset_id)
    return sorted(set(assets))


def _asset_id_from_cn_stock_code(raw_code: str) -> str | None:
    code = raw_code.strip().upper()
    if not code:
        return None
    if "." in code:
        left, right = code.split(".", 1)
        if right in {"SH", "SZ", "BJ"} and left.isdigit():
            return f"CN:{right}:{left.zfill(6)}"
        if left in {"SH", "SZ", "BJ"} and right.isdigit():
            return f"CN:{left}:{right.zfill(6)}"
    digits = "".join(ch for ch in code if ch.isdigit())
    if len(digits) != 6:
        return None
    if digits.startswith(("600", "601", "603", "605", "688", "689")):
        exchange = "SH"
    elif digits.startswith(("000", "001", "002", "003", "300", "301", "302")):
        exchange = "SZ"
    elif digits.startswith(("4", "8", "9")):
        exchange = "BJ"
    else:
        return None
    return f"CN:{exchange}:{digits}"


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


def build_concept_daily_bars_for_service(
    start_date: str | None = None,
    end_date: str | None = None,
    concept_system: str = "ths",
    adjust_type: str = "qfq",
    service: str = SETTINGS.research_service,
) -> None:
    with connect(service) as conn:
        build_concept_daily_bars(
            conn,
            start_date=start_date,
            end_date=end_date,
            concept_system=concept_system,
            adjust_type=adjust_type,
        )


def build_concept_daily_bars(
    conn,
    start_date: str | None = None,
    end_date: str | None = None,
    concept_system: str = "ths",
    adjust_type: str = "qfq",
) -> None:
    filters = [
        "m.concept_system = %s",
        "b.adjust_type = %s",
        "m.start_date <= b.trade_date",
        "(m.end_date IS NULL OR b.trade_date < m.end_date)",
    ]
    params = [concept_system, adjust_type]
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
            m.concept_system,
            m.concept_code,
            max(m.concept_name) AS concept_name,
            m.asset_id,
            b.adjust_type,
            b.trade_date
        FROM market_daily_bar b
        JOIN core.concept_membership m
          ON m.asset_id = b.asset_id
        WHERE {where_sql}
        GROUP BY
            m.concept_system,
            m.concept_code,
            m.asset_id,
            b.adjust_type,
            b.trade_date
    )
    INSERT INTO market.concept_daily_bar (
        concept_system,
        concept_code,
        concept_name,
        trade_date,
        open,
        high,
        low,
        close,
        preclose,
        volume,
        amount,
        stock_count,
        up_count,
        down_count,
        source
    )
    SELECT
        m.concept_system,
        m.concept_code,
        m.concept_name,
        b.trade_date,
        avg(b.open) AS open,
        max(b.high) AS high,
        min(b.low) AS low,
        avg(b.close) AS close,
        avg(b.preclose) AS preclose,
        sum(b.volume) AS volume,
        sum(b.amount) AS amount,
        count(DISTINCT b.asset_id)::int AS stock_count,
        count(DISTINCT b.asset_id) FILTER (WHERE b.pct_chg > 0)::int AS up_count,
        count(DISTINCT b.asset_id) FILTER (WHERE b.pct_chg < 0)::int AS down_count,
        'derived:concept_membership_market_daily_bar' AS source
    FROM market_daily_bar b
    JOIN membership m
      ON m.asset_id = b.asset_id
     AND m.adjust_type = b.adjust_type
     AND m.trade_date = b.trade_date
    GROUP BY
        m.concept_system,
        m.concept_code,
        m.concept_name,
        b.trade_date
    ON CONFLICT (concept_system, concept_code, trade_date) DO UPDATE SET
        concept_name = EXCLUDED.concept_name,
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        preclose = EXCLUDED.preclose,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        stock_count = EXCLUDED.stock_count,
        up_count = EXCLUDED.up_count,
        down_count = EXCLUDED.down_count,
        source = EXCLUDED.source,
        updated_at = now()
    """
    execute(conn, sql, params)
