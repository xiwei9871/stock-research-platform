"""DATA-R3-P1d.3 — C. EOD V2 dual-write drill (isolated replica).

Simulates the post-migration EOD sequence on an isolated replica table
(p1d3_shadow.eod_replica), NEVER the production table:

  per trading day:  v1-row write + emit_v2_flags in ONE transaction
                    (the exact dual-write shape of
                    build_asset_status_daily(emit_v2_target=...))

Proves:
  - consecutive days write v2 with rule_id + state + version
  - re-running the same day is a no-op (idempotent, same input ->
    same v2 output)
  - a mid-day exception rolls the WHOLE day back (v1 row included) —
    no half-written day can advance a success watermark
  - retry after abort completes cleanly
  - rule_unknown / data_insufficient stay explicit, never False-defaulted

Writes docs/research_upgrade/p1d3/final/EOD_DUAL_WRITE.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
from stock_research.config import SETTINGS  # noqa: E402
from stock_research.core_data import emit_v2_flags  # noqa: E402
from stock_research.db import connect, execute, fetch_all  # noqa: E402

R = "p1d3_shadow.eod_replica"
DAYS = ["2024-06-03", "2024-06-04", "2024-06-05"]
OUT = Path("docs/research_upgrade/p1d3/final")


def make_replica(conn):
    execute(conn, f"DROP TABLE IF EXISTS {R}")
    execute(conn, f"""CREATE TABLE {R}
        (LIKE core.asset_status_daily INCLUDING ALL)""")
    execute(conn, f"""ALTER TABLE {R}
        ADD COLUMN IF NOT EXISTS is_limit_up_v2 boolean,
        ADD COLUMN IF NOT EXISTS is_limit_down_v2 boolean,
        ADD COLUMN IF NOT EXISTS limit_state_v2 smallint,
        ADD COLUMN IF NOT EXISTS limit_rule_id_v2 text,
        ADD COLUMN IF NOT EXISTS limit_flags_version text""")


def day_state(conn, day) -> dict:
    r = fetch_all(conn, f"""
        SELECT count(*) AS rows,
               count(*) FILTER (WHERE limit_flags_version
                                = 'pit_rules_v1') AS v2,
               count(*) FILTER (WHERE limit_state_v2 = 2) AS unknown,
               count(*) FILTER (WHERE limit_state_v2 = 3) AS insuff,
               md5(coalesce(string_agg(md5(asset_id||
                   is_limit_up_v2::text||is_limit_down_v2::text||
                   limit_state_v2::text||coalesce(limit_rule_id_v2,'')),
                   '' ORDER BY asset_id),'')) AS h
        FROM {R} WHERE trade_date = %s""", [day])[0]
    return {"rows": int(r["rows"]), "v2": int(r["v2"]),
            "rule_unknown": int(r["unknown"]),
            "data_insufficient": int(r["insuff"]), "hash": r["h"]}


def eod_day(conn, day, fault=False):
    """One atomic EOD batch: v1 rows + v2 emit in a single transaction."""
    execute(conn, f"""
        INSERT INTO {R} (trade_date, asset_id, is_trade, is_st,
                         is_suspended, is_limit_up, is_limit_down,
                         limit_up_price, limit_down_price, source)
        SELECT trade_date, asset_id, is_trade, is_st, is_suspended,
               is_limit_up, is_limit_down, limit_up_price,
               limit_down_price, source
        FROM core.asset_status_daily WHERE trade_date = %s
        ON CONFLICT (trade_date, asset_id) DO NOTHING""", [day])
    if fault:  # inject a REAL db error mid-batch
        execute(conn, "SELECT * FROM p1d3_shadow.__no_such_table__")
    emit_v2_flags(conn, day, day, R)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    res = {"replica": R, "days": {}, "checks": {}}
    with connect(SETTINGS.research_service) as conn:
        execute(conn, "SET max_parallel_workers_per_gather = 0")
        make_replica(conn)
        # 1) three consecutive days, atomic dual-write each
        for d in DAYS:
            try:
                eod_day(conn, d)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            res["days"][d] = day_state(conn, d)
        # 2) idempotent re-run of the middle day
        h0 = res["days"][DAYS[1]]["hash"]
        eod_day(conn, DAYS[1])
        conn.commit()
        h1 = day_state(conn, DAYS[1])["hash"]
        res["checks"]["idempotent_rerun_same_day"] = (h0 == h1)
        # 3) interruption mid-batch -> whole day rolled back
        bad_day = "2024-06-06"
        try:
            eod_day(conn, bad_day, fault=True)
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            res["fault_error"] = f"{type(exc).__name__}"
            conn.rollback()
        after_abort = day_state(conn, bad_day)
        res["checks"]["abort_leaves_zero_rows"] = (
            after_abort["rows"] == 0)
        # 4) retry completes
        eod_day(conn, bad_day)
        conn.commit()
        after_retry = day_state(conn, bad_day)
        res["checks"]["retry_completes"] = (
            after_retry["rows"] > 0
            and after_retry["v2"] == after_retry["rows"])
        res["days"][bad_day] = after_retry
        # 5) explicit states never silently defaulted: every v2 row has
        # state in {1,2,3} and a non-null rule_id
        r = fetch_all(conn, f"""
            SELECT count(*) FILTER (WHERE limit_state_v2 NOT IN (1,2,3)
                     OR limit_rule_id_v2 IS NULL
                     OR limit_flags_version IS NULL) AS bad
            FROM {R}""")[0]
        res["checks"]["no_stateless_rows"] = int(r["bad"]) == 0
        res["checks"]["all_days_v2_complete"] = all(
            s["v2"] == s["rows"] and s["rows"] > 0
            for s in res["days"].values())
        res["all_pass"] = all(res["checks"].values())
    p = OUT / "EOD_DUAL_WRITE.json"
    p.write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=2, default=str))
    return 0 if res["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
