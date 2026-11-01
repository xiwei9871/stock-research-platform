#!/usr/bin/env python3
"""M2-0 fixtures — independent PostgreSQL test instance (E4).

Builds production-shaped minimal objects in the LOCAL test database
(stock_m2_test @ 127.0.0.1, PostgreSQL 16 — separate instance from the
production DB host). NOTHING here touches production.
"""
import sys

sys.path.insert(0, "src")
import psycopg  # noqa: E402

TEST_DSN = "host=127.0.0.1 port=5432 dbname=stock_m2_test user=xiwei"
DATES = ["2026-10-20", "2026-10-21", "2026-10-22"]

# (asset_id, ts_code, symbol, exchange, board, flags..., pct_chg pattern)
ASSETS = [
    ("CN:SH:600001", "600001.SH", "600001", "SH", "main",
     False, False, False, 10.4),     # SSE main limit up (10%)
    ("CN:SZ:000001", "000001.SZ", "000001", "SZ", "main",
     False, False, False, -10.4),   # SZSE main limit down
    ("CN:SH:688001", "688001.SH", "688001", "SH", "star",
     True, False, False, 20.4),     # STAR limit up (20%)
    ("CN:SZ:300001", "300001.SZ", "300001", "SZ", "chinext",
     False, True, False, 21.0),     # ChiNext beyond limit
    ("CN:BJ:430001", "430001.BJ", "430001", "BJ", "bse",
     False, False, True, 29.9),     # BSE ~limit
    ("CN:SH:601001", "601001.SH", "601001", "SH", "main",
     False, False, False, 4.9),     # ST bar -> 5% cap
    ("CN:SH:601002", "601002.SH", "601002", "SH", "main",
     False, False, False, 1.0),     # normal day
    ("CN:SZ:002001", "002001.SZ", "002001", "SZ", "main",
     False, False, False, 0.0),     # suspended day (trade_status 0)
]

DDL = """
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS market;
CREATE SCHEMA IF NOT EXISTS finance;
CREATE SCHEMA IF NOT EXISTS raw_akshare;

CREATE TABLE IF NOT EXISTS core.asset_master (
    asset_id text PRIMARY KEY, ts_code text, baostock_code text,
    akshare_code text, symbol text NOT NULL, name text NOT NULL,
    exchange text NOT NULL, board text, list_date date,
    delist_date date, is_active boolean NOT NULL,
    is_beijing boolean NOT NULL, is_star boolean NOT NULL,
    is_chinext boolean NOT NULL, region text, source text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS core.asset_status_daily (
    trade_date date NOT NULL, asset_id text NOT NULL,
    is_trade boolean NOT NULL, is_st boolean NOT NULL,
    is_suspended boolean NOT NULL, is_limit_up boolean,
    is_limit_down boolean, limit_up_price numeric,
    limit_down_price numeric, source text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    is_limit_up_v2 boolean, is_limit_down_v2 boolean,
    limit_state_v2 smallint, limit_rule_id_v2 text,
    limit_flags_version text,
    PRIMARY KEY (trade_date, asset_id));

CREATE TABLE IF NOT EXISTS market.trading_calendar (
    exchange text NOT NULL, trade_date date NOT NULL,
    is_open boolean NOT NULL, source text NOT NULL,
    source_version text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (exchange, trade_date, source_version));

CREATE TABLE IF NOT EXISTS public.market_daily_bar (
    asset_id text, trade_date date, open numeric, high numeric,
    low numeric, close numeric, preclose numeric, volume numeric,
    amount numeric, turnover_rate numeric, pct_chg numeric,
    trade_status text, is_st boolean, adjust_type text,
    source text, updated_at timestamptz DEFAULT now(),
    PRIMARY KEY (asset_id, trade_date, adjust_type));

CREATE TABLE IF NOT EXISTS market.lhb_top_list_daily (
    trade_date date NOT NULL, ts_code text NOT NULL, name text,
    source text NOT NULL DEFAULT 'test',
    PRIMARY KEY (trade_date, ts_code, source));

CREATE TABLE IF NOT EXISTS raw_akshare.finance_payload (
    id bigserial PRIMARY KEY, source_endpoint text,
    request_params jsonb, asset_id text, payload jsonb,
    payload_hash text,
    fetched_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS finance.income_statement (
    asset_id text, report_period date, report_type text,
    announcement_date date, source text, revenue numeric,
    net_profit numeric, updated_at timestamptz DEFAULT now(),
    PRIMARY KEY (asset_id, report_period, report_type,
                 announcement_date, source));
CREATE TABLE IF NOT EXISTS finance.balance_sheet (
    LIKE finance.income_statement);
CREATE TABLE IF NOT EXISTS finance.cash_flow (
    LIKE finance.income_statement);
"""


def seed(conn):
    with conn.cursor() as cur:
        for stmt in DDL.split(";"):
            if stmt.strip():
                cur.execute(stmt)
        # calendar: every weekday 1990-2026 open (dense enough for
        # sess_idx math across any test list_date)
        cur.execute("""
          INSERT INTO market.trading_calendar
            (exchange, trade_date, is_open, source, source_version)
          SELECT e, d::date, extract(dow FROM d) NOT IN (0,6),
                 'fixture','v1'
          FROM generate_series('2019-12-01'::date,'2026-12-31'::date,
                               '1 day'::interval) d,
               (VALUES ('SH'),('SZ'),('BJ')) e
          ON CONFLICT DO NOTHING""")
        for (aid, ts, sym, exch, board, star, cnxt, bj, pct) in ASSETS:
            cur.execute("""
              INSERT INTO core.asset_master
                (asset_id, ts_code, symbol, name, exchange, board,
                 list_date, is_active, is_beijing, is_star,
                 is_chinext, source)
              VALUES (%s,%s,%s,%s,%s,%s,'2015-01-05',true,%s,%s,%s,
                      'fixture') ON CONFLICT DO NOTHING""",
                        [aid, ts, sym, f"T{sym}", exch, board, bj,
                         star, cnxt])
            for d in DATES:
                is_st = aid == "CN:SH:601001"
                suspended = aid == "CN:SZ:002001"
                pre = 10.0
                close = round(pre * (1 + pct / 100.0), 2)
                cur.execute("""
                  INSERT INTO public.market_daily_bar
                    (asset_id, trade_date, close, preclose, pct_chg,
                     trade_status, is_st, adjust_type, source)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,'raw','fixture'),
                         (%s,%s,%s,%s,%s,%s,%s,'hfq','fixture')
                  ON CONFLICT DO NOTHING""",
                            [aid, d, close, pre, pct,
                             "0" if suspended else "1", is_st,
                             aid, d, close, pre, pct,
                             "0" if suspended else "1", is_st])
                # asset with NO raw bar -> data_insufficient path
            cur.execute("""
              INSERT INTO public.market_daily_bar
                (asset_id, trade_date, adjust_type, source)
              SELECT 'CN:SH:609999', d, 'raw','fixture'
              FROM unnest(%s::date[]) d ON CONFLICT DO NOTHING""",
                        [DATES])
        cur.execute("""
          INSERT INTO core.asset_master
            (asset_id, ts_code, symbol, name, exchange, board,
             list_date, is_active, is_beijing, is_star, is_chinext,
             source)
          VALUES ('CN:SH:609999','609999.SH','609999','T609999','SH',
                  'main','2015-01-05',true,false,false,false,'fixture')
          ON CONFLICT DO NOTHING""")


def reset(conn):
    with conn.cursor() as cur:
        for s in ("core", "market", "finance", "raw_akshare"):
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {s}")
        cur.execute(f"DROP SCHEMA IF EXISTS finver CASCADE")
        for t in ("core.asset_status_daily", "core.asset_status_v1only",
                  "core.asset_master",
                  "public.market_daily_bar", "market.trading_calendar",
                  "market.lhb_top_list_daily",
                  "raw_akshare.finance_payload",
                  "finance.income_statement", "finance.balance_sheet",
                  "finance.cash_flow"):
            cur.execute(f"DROP TABLE IF EXISTS {t} CASCADE")


def connect_test():
    from psycopg.rows import dict_row
    return psycopg.connect(TEST_DSN, row_factory=dict_row)


if __name__ == "__main__":
    with connect_test() as conn:
        reset(conn)
        seed(conn)
        conn.commit()
    print("fixtures seeded in stock_m2_test (local test instance)")
