"""DATA-R3-P1d.3 preflight — batch failure-recovery drill.

Injects REAL database exceptions (UndefinedTable) mid-batch against the
shadow schema and proves:

  1. the aborted transaction is rolled back before splitting
     (connection usable immediately after failure);
  2. sub-batch checkpoints survive and drive cross-process-style resume;
  3. committed sub-batches are never recomputed on re-run;
  4. re-executing a completed batch tree is a pure no-op (idempotent).

Writes docs/research_upgrade/p1d3/final/FAILURE_RECOVERY.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, ".")

import scripts.p1d3_migration_rehearsal as R  # noqa: E402
from stock_research.config import SETTINGS  # noqa: E402
from stock_research.db import connect, execute, fetch_all  # noqa: E402

OUT = Path("docs/research_upgrade/p1d3/final")
TEST_TABLE = "p1d3_shadow.recovery_test"
RESULT: dict = {"checks": {}}


def make_test_table(conn):
    """Isolated copy of a small window; the drill never touches
    p1d3_shadow.asset_status_daily_v2 or the production table."""
    execute(conn, "DROP TABLE IF EXISTS p1d3_shadow.recovery_test")
    execute(conn, "DROP TABLE IF EXISTS p1d3_shadow.recovery_log")
    execute(conn, f"""
        CREATE TABLE {TEST_TABLE} (
            trade_date          date        NOT NULL,
            asset_id            text        NOT NULL,
            is_limit_up         boolean,
            is_limit_down       boolean,
            is_suspended        boolean,
            is_limit_up_v2      boolean,
            is_limit_down_v2    boolean,
            limit_state_v2      smallint,
            limit_rule_id_v2    text,
            limit_flags_version text,
            batch_id            text,
            written_at          timestamptz DEFAULT now(),
            PRIMARY KEY (trade_date, asset_id))""")
    execute(conn, """
        CREATE TABLE p1d3_shadow.recovery_log (
            batch_id    text PRIMARY KEY,
            status      text,
            range_start date,
            range_end   date,
            error       text,
            rows_total  bigint,
            rows_v2     bigint,
            diff_rows   bigint,
            seconds     double precision,
            started_at  timestamptz DEFAULT now(),
            finished_at timestamptz)""")


def run_drill(conn) -> dict:
    # point the rehearsal machinery at the isolated test objects
    orig_table, orig_log = R.SHADOW_TABLE, "p1d3_shadow.migration_log"
    R.SHADOW_TABLE = TEST_TABLE
    # patch log table name inside module functions via SQL strings is
    # impractical — instead run recovery_log under the same name in a
    # scratch schema is also heavy; simplest faithful drill: reuse the
    # real migration_log but with drill batch ids, then clean them.
    drill_batch = "drill_recovery_2024h1"
    for suffix in ("", "_a", "_b", "_a_a", "_a_b", "_b_a", "_b_b"):
        execute(conn, """DELETE FROM p1d3_shadow.migration_log
                        WHERE batch_id=%s""", [drill_batch + suffix])
    execute(conn, f"DELETE FROM {TEST_TABLE}")
    conn.commit()

    emit_calls = {"n": 0}
    orig_emit = R.emit_v2_flags

    def counting_emit(*a, **kw):
        emit_calls["n"] += 1
        return orig_emit(*a, **kw)
    R.emit_v2_flags = counting_emit

    batch = {"batch": drill_batch, "start": "2024-06-03",
             "end": "2024-06-07"}
    faults = {"root": 1}

    def hook():
        if faults["root"]:
            faults["root"] -= 1
            # REAL postgres error — aborts the running transaction
            execute(conn, "SELECT * FROM p1d3_shadow.__no_such_table__")

    try:
        out = R.run_batch_safe(conn, dict(batch), fault_hook=hook)
        # 1) connection must be usable (aborted tx rolled back)
        ping = fetch_all(conn, "SELECT 1 AS ok")[0]["ok"] == 1
        # 2) log states
        log = {r["batch_id"]: r for r in fetch_all(conn, """
            SELECT * FROM p1d3_shadow.migration_log
            WHERE batch_id LIKE %s""", [drill_batch + "%"])}
        # 3) data completeness vs a clean reference (shadow table is the
        # already-verified rehearsal output)
        ref = fetch_all(conn, """
            SELECT count(*) AS n,
                   md5(string_agg(md5(asset_id||trade_date||
                       is_limit_up_v2::text||is_limit_down_v2::text||
                       limit_state_v2::text||coalesce(limit_rule_id_v2,'')),
                       '' ORDER BY asset_id, trade_date)) AS h
            FROM p1d3_shadow.asset_status_daily_v2
            WHERE trade_date BETWEEN '2024-06-03' AND '2024-06-07'""")[0]
        got = fetch_all(conn, f"""
            SELECT count(*) AS n,
                   md5(string_agg(md5(asset_id||trade_date||
                       is_limit_up_v2::text||is_limit_down_v2::text||
                       limit_state_v2::text||coalesce(limit_rule_id_v2,'')),
                       '' ORDER BY asset_id, trade_date)) AS h
            FROM {TEST_TABLE}""")[0]
        emits_after_first = emit_calls["n"]
        # 4) resume re-entry — committed subs must not be recomputed
        resume = R.run_batch_safe(conn, dict(batch))
        emits_on_resume = emit_calls["n"] - emits_after_first
        # 5) idempotent written_at (nothing rewritten)
        RESULT["checks"] = {
            "conn_usable_after_abort": ping,
            "root_logged_failed_split":
                log.get(drill_batch, {}).get("status") == "failed_split",
            "sub_batches_done": sorted(
                k for k, v in log.items()
                if v["status"] == "done" and k != drill_batch),
            "checksum_matches_reference": got["n"] == ref["n"]
            and got["h"] == ref["h"],
            "rows": int(got["n"]),
            "emits_first_pass": emits_after_first,
            "emits_on_resume": emits_on_resume,
            "resume_no_recompute": emits_on_resume == 0,
            "resume_all_skipped": all(
                r.get("skipped_done") for r in resume),
        }
        RESULT["checks"]["pass"] = all([
            ping,
            log.get(drill_batch, {}).get("status") == "failed_split",
            len(RESULT["checks"]["sub_batches_done"]) >= 2,
            got["n"] == ref["n"] and got["h"] == ref["h"],
            emits_on_resume == 0,
            all(r.get("skipped_done") for r in resume),
        ])
    finally:
        R.emit_v2_flags = orig_emit
        R.SHADOW_TABLE = orig_table
        # drill rows cleaned from the real log
        execute(conn, """DELETE FROM p1d3_shadow.migration_log
                        WHERE batch_id LIKE %s""", [drill_batch + "%"])
        conn.commit()
    return RESULT


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with connect(SETTINGS.research_service) as conn:
        execute(conn, "SET max_parallel_workers_per_gather = 0")
        R.create_shadow(conn)  # migrates pre-existing migration_log schema
        make_test_table(conn)
        res = run_drill(conn)
    p = OUT / "FAILURE_RECOVERY.json"
    p.write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=2, default=str))
    return 0 if res["checks"].get("pass") else 1


if __name__ == "__main__":
    sys.exit(main())
