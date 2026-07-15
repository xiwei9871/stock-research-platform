from io import StringIO

import requests

from stock_research.config import SETTINGS
from stock_research.db import connect, execute
from stock_research.db import execute_many
from stock_research.db import fetch_all
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


def sync_concept_memberships_from_akshare(
    conn,
    *,
    trade_date: str,
    concept_system: str = "em",
    board_fetcher=None,
    constituent_fetcher=None,
    max_concepts: int | None = None,
    offset: int = 0,
) -> dict[str, object]:
    if ak is None and (board_fetcher is None or constituent_fetcher is None):
        raise RuntimeError("akshare is required to sync concept memberships")

    default_em_fetchers = board_fetcher is None and constituent_fetcher is None and concept_system == "em"
    default_ths_fetchers = board_fetcher is None and constituent_fetcher is None and concept_system == "ths"
    if default_em_fetchers:
        board_fetcher = fetch_eastmoney_concept_boards_direct
        constituent_fetcher = ak.stock_board_concept_cons_em
        board_source = "eastmoney:qt_clist_concept_board"
        constituent_source = "akshare:stock_board_concept_cons_em"
    elif default_ths_fetchers:
        board_fetcher = ak.stock_board_concept_name_ths
        constituent_fetcher = fetch_ths_concept_constituents_direct
        board_source = "akshare:stock_board_concept_name_ths"
        constituent_source = "ths:q.10jqka.com.cn_gn_detail"
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
    if offset:
        boards = boards[max(0, int(offset)) :]
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
        constituent_symbol = concept_code if default_em_fetchers or default_ths_fetchers else concept_name
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
    seen_codes: set[str] = set()
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
        "https://33.push2.eastmoney.com/api/qt/clist/get",
        "https://79.push2.eastmoney.com/api/qt/clist/get",
        "https://82.push2.eastmoney.com/api/qt/clist/get",
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


def fetch_ths_concept_constituents_direct(
    symbol: str,
    *,
    max_pages: int = 50,
    timeout_seconds: int = 15,
):
    import pandas as pd

    rows: list[dict[str, str]] = []
    seen_codes: set[str] = set()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36"
        )
    }
    for page in range(1, max_pages + 1):
        url = f"http://q.10jqka.com.cn/gn/detail/field/199112/order/desc/page/{page}/ajax/1/code/{symbol}"
        response = requests.get(url, headers=headers, timeout=timeout_seconds)
        if hasattr(response, "encoding"):
            response.encoding = response.encoding or getattr(response, "apparent_encoding", None) or "gbk"
        try:
            tables = pd.read_html(StringIO(response.text))
        except ValueError:
            break

        page_rows: list[dict[str, str]] = []
        for table in tables:
            columns = {str(column).strip(): column for column in table.columns}
            code_column = columns.get("代码")
            name_column = columns.get("名称")
            if code_column is None or name_column is None:
                continue
            for item in table[[code_column, name_column]].to_dict("records"):
                code = str(item.get(code_column) or "").strip().zfill(6)
                name = str(item.get(name_column) or "").strip()
                if code.isdigit() and len(code) == 6 and name:
                    page_rows.append({"代码": code, "名称": name})
        new_rows = [row for row in page_rows if row["代码"] not in seen_codes]
        if not new_rows:
            break
        for row in new_rows:
            seen_codes.add(row["代码"])
        rows.extend(new_rows)
    return pd.DataFrame(rows, columns=["代码", "名称"])


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
        assert_asset_status_daily_quality(conn, start_date=start_date, end_date=end_date)


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
            WHEN resolved_is_st THEN 4.8
            WHEN is_beijing THEN 29.8
            WHEN is_star OR is_chinext THEN 19.8
            ELSE 9.8
        END
    """
    sql = f"""
    WITH same_day_lhb AS (
        SELECT
            trade_date,
            ts_code,
            max(NULLIF(name, '')) AS same_day_lhb_name
        FROM market.lhb_top_list_daily
        GROUP BY trade_date, ts_code
    ),
    resolved AS (
        SELECT
            b.*,
            a.is_star,
            a.is_chinext,
            a.is_beijing,
            l.same_day_lhb_name,
            COALESCE(
                l.same_day_lhb_name ~* '^(\\*?ST|S\\*ST)',
                b.is_st,
                false
            ) AS resolved_is_st,
            CASE
                WHEN l.same_day_lhb_name IS NOT NULL THEN 'same_day_lhb_name'
                WHEN b.is_st THEN 'daily_bar'
                ELSE 'daily_bar_unverified_false'
            END AS status_quality
        FROM market_daily_bar b
        LEFT JOIN core.asset_master a
          ON a.asset_id = b.asset_id
        LEFT JOIN same_day_lhb l
          ON l.trade_date = b.trade_date
         AND l.ts_code = a.ts_code
        WHERE {where_sql}
    )
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
        b.resolved_is_st,
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
        b.source || ':status_quality=' || b.status_quality
    FROM resolved b
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


def assert_asset_status_daily_quality(
    conn,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, object]:
    filters = ["NULLIF(l.name, '') ~* '^(\\*?ST|S\\*ST)'"]
    params: list[object] = []
    if start_date:
        filters.append("l.trade_date >= %s")
        params.append(start_date)
    if end_date:
        filters.append("l.trade_date <= %s")
        params.append(end_date)
    rows = fetch_all(
        conn,
        f"""
        WITH lhb_st AS (
            SELECT
                l.trade_date,
                count(DISTINCT l.ts_code)::int AS lhb_st_count
            FROM market.lhb_top_list_daily l
            WHERE {' AND '.join(filters)}
            GROUP BY l.trade_date
        ),
        status_st AS (
            SELECT
                s.trade_date,
                count(DISTINCT s.asset_id)::int AS asset_status_st_count
            FROM core.asset_status_daily s
            WHERE s.is_st
            GROUP BY s.trade_date
        )
        SELECT
            l.trade_date::text AS trade_date,
            l.lhb_st_count,
            COALESCE(s.asset_status_st_count, 0)::int AS asset_status_st_count
        FROM lhb_st l
        LEFT JOIN status_st s ON s.trade_date = l.trade_date
        WHERE COALESCE(s.asset_status_st_count, 0) = 0
        ORDER BY l.trade_date
        """,
        params,
    )
    if rows:
        sample = ", ".join(
            f"{row.get('trade_date')}:lhb_st={row.get('lhb_st_count')}:status_st={row.get('asset_status_st_count')}"
            for row in rows[:5]
        )
        raise RuntimeError(f"asset status ST quality violation: {sample}")
    return {"violation_count": 0, "start_date": start_date, "end_date": end_date}


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
