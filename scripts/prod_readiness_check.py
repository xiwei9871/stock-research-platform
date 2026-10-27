#!/usr/bin/env python3
"""M2.0.1 — pre-action production readiness check (READ-ONLY).

Run before ANY approved production action (T1/F1/backfill). Emits a
JSON verdict; exits 2 when a hard precondition fails. Writes nothing.
"""
import json
import sys

sys.path.insert(0, "src")
import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402


def check(dsn):
    c = psycopg.connect(dsn, row_factory=dict_row)
    out = {"checks": {}, "hard_fail": []}
    q = lambda s, p=None: c.execute(s, p or []).fetchall()

    ver = q("SELECT version() v")[0]["v"]
    out["checks"]["pg_version"] = ver
    out["checks"]["server"] = q("""SELECT inet_server_addr() a,
        inet_server_port() p, current_database() d""")[0]

    out["checks"]["long_tx"] = q("""
        SELECT pid, now()-xact_start dur, state, left(query,60) q
        FROM pg_stat_activity
        WHERE xact_start < now() - interval '10 minutes'
          AND pid <> pg_backend_pid()""")
    if out["checks"]["long_tx"]:
        out["hard_fail"].append("long transactions present")

    out["checks"]["blocked_locks"] = q("""
        SELECT count(*) n FROM pg_locks WHERE NOT granted""")[0]["n"]

    st = q("""SELECT archive_mode, wal_level FROM
        (SELECT setting archive_mode FROM pg_settings
          WHERE name='archive_mode') a,
        (SELECT setting wal_level FROM pg_settings
          WHERE name='wal_level') b""")[0]
    out["checks"]["wal"] = st
    if st["archive_mode"] == "off":
        out["checks"]["wal"]["note"] = \
            "no PITR — restore only to last full backup"

    out["checks"]["replicas"] = q(
        "SELECT count(*) n FROM pg_stat_replication")[0]["n"]
    out["checks"]["db_size"] = q(
        "SELECT pg_size_pretty(pg_database_size(current_database())) s"
    )[0]["s"]
    out["checks"]["wal_dir"] = q(
        "SELECT pg_size_pretty(sum(size)::bigint) s "
        "FROM pg_ls_waldir()")[0]["s"]

    # v2 contract / finver presence facts (no writes)
    out["checks"]["v2_cols"] = q("""
        SELECT count(*) n FROM information_schema.columns
        WHERE table_schema='core' AND table_name='asset_status_daily'
          AND column_name IN ('is_limit_up_v2','is_limit_down_v2',
          'limit_state_v2','limit_rule_id_v2','limit_flags_version')"""
                               )[0]["n"]
    out["checks"]["finver_tables"] = q("""
        SELECT count(*) n FROM information_schema.tables
        WHERE table_schema='finver'""")[0]["n"]
    c.close()
    out["ok"] = not out["hard_fail"]
    return out


if __name__ == "__main__":
    dsn = sys.argv[1] if len(sys.argv) > 1 else "service=stock_research"
    res = check(dsn)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    sys.exit(0 if res["ok"] else 2)
