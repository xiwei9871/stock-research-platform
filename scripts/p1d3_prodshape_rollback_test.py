"""DATA-R3-P1d.3 preflight — production-shaped V2 UPDATE & rollback drill.

Rehearses the REAL migration form on an isolated replica of
core.asset_status_daily — never on the production table:

  1. replica = LIKE ... INCLUDING ALL + data copy (2024 full year)
  2. additive DDL: the exact 5 v2 columns from the runbook
  3. column-level UPDATE ... FROM shadow (production migration shape)
  4. per-batch: rows affected, statement ms, WAL bytes, lock mode
  5. interruption: statement_timeout aborts a mid UPDATE -> zero partial
  6. column-level rollback -> checksum returns to pre-update image
  7. v1 columns verified unchanged throughout
  8. EOD emit interleaved with backfill -> identical version, no dupes

Writes docs/research_upgrade/p1d3/final/V2_UPDATE_ROLLBACK.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")
from stock_research.config import SETTINGS  # noqa: E402
from stock_research.core_data import emit_v2_flags  # noqa: E402
from stock_research.db import connect, execute, fetch_all  # noqa: E402

REPLICA = "p1d3_shadow.prod_replica"
SHADOW = "p1d3_shadow.asset_status_daily_v2"
OUT = Path("docs/research_upgrade/p1d3/final")
YEAR = ("2024-01-01", "2024-12-31")
MONTHS = [(f"2024-{m:02d}-01", f"2024-{m + 1:02d}-01" if m < 12
           else "2025-01-01") for m in range(1, 13)]

V2_DDL = """ALTER TABLE %s
    ADD COLUMN IF NOT EXISTS is_limit_up_v2      boolean,
    ADD COLUMN IF NOT EXISTS is_limit_down_v2    boolean,
    ADD COLUMN IF NOT EXISTS limit_state_v2      smallint,
    ADD COLUMN IF NOT EXISTS limit_rule_id_v2    text,
    ADD COLUMN IF NOT EXISTS limit_flags_version text"""

UPDATE_SQL = f"""UPDATE {{t}} r
   SET is_limit_up_v2      = s.is_limit_up_v2,
       is_limit_down_v2    = s.is_limit_down_v2,
       limit_state_v2      = s.limit_state_v2,
       limit_rule_id_v2    = s.limit_rule_id_v2,
       limit_flags_version = s.limit_flags_version
  FROM {SHADOW} s
 WHERE r.trade_date = s.trade_date AND r.asset_id = s.asset_id
   AND r.trade_date >= %s AND r.trade_date < %s"""


def wal_lsn(conn) -> int:
    return int(fetch_all(conn,
                         "SELECT pg_current_wal_lsn()::pg_lsn - '0/0'::pg_lsn "
                         "AS l")[0]["l"])


def checksum_v2(conn, d0, d1):
    r = fetch_all(conn, f"""
        SELECT count(*) FILTER (WHERE limit_flags_version IS NOT NULL) AS v2n,
               md5(coalesce(string_agg(md5(asset_id||trade_date||
                   is_limit_up_v2::text||is_limit_down_v2::text||
                   limit_state_v2::text||coalesce(limit_rule_id_v2,'')),
                   '' ORDER BY asset_id, trade_date),'')) AS h
        FROM {REPLICA} WHERE trade_date BETWEEN %s AND %s""", [d0, d1])[0]
    return {"v2_rows": int(r["v2n"]), "hash": r["h"]}


def checksum_v1(conn):
    r = fetch_all(conn, f"""
        SELECT md5(string_agg(md5(asset_id||trade_date||
            is_limit_up::text||is_limit_down::text||is_suspended::text||
            is_st::text), '' ORDER BY asset_id, trade_date)) AS h
        FROM {REPLICA}""")[0]
    return r["h"]


def build_replica(conn) -> dict:
    execute(conn, f"DROP TABLE IF EXISTS {REPLICA}")
    execute(conn, f"""CREATE TABLE {REPLICA}
        (LIKE core.asset_status_daily INCLUDING ALL)""")
    t0 = time.monotonic()
    execute(conn, f"""INSERT INTO {REPLICA}
        SELECT * FROM core.asset_status_daily
        WHERE trade_date BETWEEN %s AND %s""", list(YEAR))
    n = fetch_all(conn, f"SELECT count(*) AS n FROM {REPLICA}")[0]["n"]
    execute(conn, V2_DDL % REPLICA)
    return {"rows": int(n), "copy_seconds": round(time.monotonic() - t0, 1)}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    res: dict = {"replica": REPLICA, "year": YEAR, "batches": [],
                 "checks": {}}
    with connect(SETTINGS.research_service) as conn:
        execute(conn, "SET max_parallel_workers_per_gather = 0")
        res["replica_build"] = build_replica(conn)
        conn.commit()
        res["v1_checksum_before"] = checksum_v1(conn)
        res["v2_checksum_empty"] = checksum_v2(conn, *YEAR)

        # --- production-shaped UPDATE, month batches -------------------
        interrupted = {"done": False}
        eod_date = None
        for i, (d0, d1) in enumerate(MONTHS):
            end = d1
            batch = {"month": d0[:7], "range": [d0, end]}
            # inject real interruption on batch 4: tiny statement_timeout
            # inside the same transaction -> abort -> nothing persists
            if i == 3 and not interrupted["done"]:
                try:
                    execute(conn, "SET LOCAL statement_timeout = '50ms'")
                    execute(conn, UPDATE_SQL.format(t=REPLICA), [d0, end])
                except Exception as exc:  # noqa: BLE001
                    conn.rollback()
                    batch["interruption"] = {
                        "error": f"{type(exc).__name__}",
                        "partial_rows_after_abort": fetch_all(conn, f"""
                            SELECT count(*) AS n FROM {REPLICA}
                            WHERE trade_date >= %s AND trade_date < %s
                              AND limit_flags_version IS NOT NULL""",
                            [d0, end])[0]["n"]}
                    interrupted["done"] = True
                    res["batches"].append(batch)
                    execute(conn,
                            "SET LOCAL statement_timeout = '0'")
            # interleave an EOD-style emit on batch 7's first day BEFORE
            # its backfill UPDATE — version consistency check
            if i == 6:
                eod_date = fetch_all(conn, f"""
                    SELECT min(trade_date)::text AS d FROM {REPLICA}
                    WHERE trade_date >= %s AND trade_date < %s""",
                    [d0, end])[0]["d"]
                emit_v2_flags(conn, eod_date, eod_date, REPLICA)
                batch["eod_emit_before_backfill"] = eod_date
            w0, t0 = wal_lsn(conn), time.monotonic()
            locks = fetch_all(conn, f"""
                SELECT mode FROM pg_locks
                WHERE relation = %s::regclass""", [REPLICA])
            execute(conn, UPDATE_SQL.format(t=REPLICA), [d0, end])
            affected = fetch_all(conn, f"""
                SELECT count(*) AS n FROM {REPLICA}
                WHERE trade_date >= %s AND trade_date < %s
                  AND limit_flags_version IS NOT NULL""", [d0, end])[0]["n"]
            conn.commit()
            batch.update({
                "rows_affected": int(affected),
                "statement_ms": round((time.monotonic() - t0) * 1000),
                "wal_bytes": wal_lsn(conn) - w0,
                "lock_mode_seen": [l["mode"] for l in locks]})
            res["batches"].append(batch)
            print(json.dumps(batch), flush=True)

        res["v2_checksum_after_update"] = checksum_v2(conn, *YEAR)
        res["v1_checksum_after_update"] = checksum_v1(conn)

        # EOD/backfill consistency on the interleaved date
        ref = fetch_all(conn, f"""
            SELECT count(*) AS n, count(DISTINCT limit_flags_version) AS v
            FROM {REPLICA} WHERE trade_date = %s""", [eod_date])[0]
        agree = fetch_all(conn, f"""
            SELECT count(*) AS n FROM {REPLICA} r
            JOIN {SHADOW} s USING (trade_date, asset_id)
            WHERE r.trade_date = %s AND
              (r.is_limit_up_v2 IS DISTINCT FROM s.is_limit_up_v2
            OR r.is_limit_down_v2 IS DISTINCT FROM s.is_limit_down_v2
            OR r.limit_state_v2 IS DISTINCT FROM s.limit_state_v2)""",
            [eod_date])[0]["n"]
        res["eod_interleaved_date"] = eod_date
        res["checks"]["eod_backfill_single_version"] = int(ref["v"]) == 1

        # --- column-level rollback ------------------------------------
        w0, t0 = wal_lsn(conn), time.monotonic()
        execute(conn, f"""UPDATE {REPLICA}
            SET is_limit_up_v2=NULL, is_limit_down_v2=NULL,
                limit_state_v2=NULL, limit_rule_id_v2=NULL,
                limit_flags_version=NULL
            WHERE trade_date BETWEEN %s AND %s""", list(YEAR))
        conn.commit()
        res["rollback"] = {
            "statement_ms": round((time.monotonic() - t0) * 1000),
            "wal_bytes": wal_lsn(conn) - w0,
            "checksum_after_rollback": checksum_v2(conn, *YEAR)}
        res["v1_checksum_final"] = checksum_v1(conn)

        res["checks"].update({
            "zero_partial_on_abort": all(
                b.get("interruption", {})
                .get("partial_rows_after_abort", 0) == 0
                for b in res["batches"] if "interruption" in b),
            "all_months_backfilled":
                res["v2_checksum_after_update"]["v2_rows"]
                == res["replica_build"]["rows"],
            "v1_unchanged_through_update":
                res["v1_checksum_before"] == res["v1_checksum_after_update"],
            "rollback_restores_empty_v2":
                res["rollback"]["checksum_after_rollback"]
                == res["v2_checksum_empty"],
            "v1_unchanged_through_rollback":
                res["v1_checksum_before"] == res["v1_checksum_final"],
            "eod_backfill_values_match_shadow": int(agree) == 0,
        })
        res["all_pass"] = all(res["checks"].values())
    p = OUT / "V2_UPDATE_ROLLBACK.json"
    p.write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps({"all_pass": res["all_pass"], "checks": res["checks"],
                      "v2_rows": res["v2_checksum_after_update"]["v2_rows"],
                      "wal_total": sum(b["wal_bytes"] for b in
                                       res["batches"]),
                      "update_ms_total": sum(b["statement_ms"] for b in
                                             res["batches"])}, indent=2))
    return 0 if res["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
