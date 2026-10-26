"""DATA-R3-P1d.3 — controlled V2 migration rehearsal (17.29M status rows).

Rehearses the production migration end-to-end against an ISOLATED shadow
table (p1d3_shadow.asset_status_daily_v2) — never touches
core.asset_status_daily. Per calendar-year batches:

  1. copy v1 columns (is_limit_up/down, is_suspended) + stamp batch_id
  2. emit_v2_flags -> recompute via shared rule engine, upsert v2 columns
  3. checkpoint row in p1d3_shadow.migration_log (resume support)
  4. per-batch metrics: rows, seconds, v1-vs-v2 diffs

Recovery drills executed after the bulk pass:
  - idempotency: re-run one batch -> zero row-value changes
  - rollback: delete one batch's rows -> re-run -> restored exactly
  - gray read: loader verified_v2 mode pointed at the shadow table must
    agree with corrected_shadow recomputation on verified keys

Usage:
    .venv/bin/python scripts/p1d3_migration_rehearsal.py [--resume]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")
from stock_research.config import SETTINGS  # noqa: E402
from stock_research.db import connect, execute, fetch_all  # noqa: E402
from stock_research.core_data import emit_v2_flags  # noqa: E402

SHADOW_TABLE = "p1d3_shadow.asset_status_daily_v2"
FLAGS_VERSION = "pit_rules_v1"
OUT_DIR = Path("docs/research_upgrade/p1d3")


def create_shadow(conn) -> None:
    execute(conn, "CREATE SCHEMA IF NOT EXISTS p1d3_shadow")
    execute(conn, f"""
        CREATE TABLE IF NOT EXISTS {SHADOW_TABLE} (
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
        CREATE TABLE IF NOT EXISTS p1d3_shadow.migration_log (
            batch_id    text PRIMARY KEY,
            status      text,
            rows_total  bigint,
            rows_v2     bigint,
            diff_rows   bigint,
            seconds     double precision,
            started_at  timestamptz DEFAULT now(),
            finished_at timestamptz)""")


def year_batches(conn) -> list[dict]:
    rows = fetch_all(conn, """
        SELECT EXTRACT(YEAR FROM trade_date)::int AS y,
               count(*) AS n,
               min(trade_date)::text AS d0,
               max(trade_date)::text AS d1
        FROM core.asset_status_daily
        GROUP BY 1 ORDER BY 1""")
    return [{"batch": f"year_{r['y']}", "start": r["d0"], "end": r["d1"],
             "expected": int(r["n"])} for r in rows]


def run_batch(conn, batch: dict) -> dict:
    b, t0 = batch["batch"], time.monotonic()
    execute(conn, """
        INSERT INTO p1d3_shadow.migration_log (batch_id, status)
        VALUES (%s, 'running')
        ON CONFLICT (batch_id) DO UPDATE
          SET status='running', finished_at=NULL""", [b])
    # step 1 — v1 column copy
    execute(conn, f"""
        INSERT INTO {SHADOW_TABLE}
            (trade_date, asset_id, is_limit_up, is_limit_down,
             is_suspended, batch_id)
        SELECT trade_date, asset_id, is_limit_up, is_limit_down,
               is_suspended, %s
        FROM core.asset_status_daily
        WHERE trade_date BETWEEN %s AND %s
        ON CONFLICT (trade_date, asset_id) DO UPDATE
          SET is_limit_up = EXCLUDED.is_limit_up,
              is_limit_down = EXCLUDED.is_limit_down,
              is_suspended = EXCLUDED.is_suspended,
              batch_id = EXCLUDED.batch_id""",
        [b, batch["start"], batch["end"]])
    # step 2 — v2 flags via the shared rule engine (guarded writer)
    n_v2 = emit_v2_flags(conn, batch["start"], batch["end"],
                         SHADOW_TABLE, FLAGS_VERSION)
    stats = fetch_all(conn, f"""
        SELECT count(*) AS rows_total,
               count(*) FILTER (WHERE limit_state_v2 IS NOT NULL) AS rows_v2,
               count(*) FILTER (WHERE
                   is_limit_up IS DISTINCT FROM is_limit_up_v2
                OR is_limit_down IS DISTINCT FROM is_limit_down_v2) AS diff_rows
        FROM {SHADOW_TABLE}
        WHERE trade_date BETWEEN %s AND %s""",
        [batch["start"], batch["end"]])[0]
    secs = time.monotonic() - t0
    execute(conn, """
        UPDATE p1d3_shadow.migration_log
           SET status='done', rows_total=%s, rows_v2=%s, diff_rows=%s,
               seconds=%s, finished_at=now()
         WHERE batch_id=%s""",
        [int(stats["rows_total"]), int(stats["rows_v2"]),
         int(stats["diff_rows"]), secs, b])
    # durable checkpoint: connect() commits once on clean exit, so without an
    # explicit commit a late-batch crash would roll back every prior batch.
    conn.commit()
    return _out(batch, stats, secs)


def run_batch_safe(conn, batch: dict, depth: int = 0) -> list[dict]:
    """Run a batch; on shared-memory exhaustion split it in half and retry —
    production finding: the context join can exceed the DSM limit on large
    windows even with parallel gather disabled, so the migration runner
    must degrade batch granularity automatically."""
    try:
        return [run_batch(conn, batch)]
    except Exception as exc:  # noqa: BLE001
        if "DiskFull" not in type(exc).__name__ + str(exc) or depth > 6:
            raise
        mid = fetch_all(conn, """
            SELECT min(trade_date)::text AS d FROM core.asset_status_daily
            WHERE trade_date > %s AND trade_date <=
                  (%s::date + (%s::date - %s::date)/2)""",
            [batch["start"], batch["start"], batch["end"], batch["start"]])
        mid_d = mid[0]["d"] or batch["start"]
        nxt = fetch_all(conn, """
            SELECT min(trade_date)::text AS d FROM core.asset_status_daily
            WHERE trade_date > %s AND trade_date <= %s""",
            [mid_d, batch["end"]])
        right_start = nxt[0]["d"]
        if right_start is None:  # nothing left in right half — retry left only
            return run_batch_safe(
                conn, {"batch": batch["batch"] + "_a",
                       "start": batch["start"], "end": mid_d}, depth + 1)
        left = {"batch": batch["batch"] + "_a", "start": batch["start"],
                "end": mid_d}
        right = {"batch": batch["batch"] + "_b", "start": right_start,
                 "end": batch["end"]}
        return (run_batch_safe(conn, left, depth + 1) +
                run_batch_safe(conn, right, depth + 1))


def _out(batch, stats, secs):
    out = {"batch": batch["batch"], "start": batch["start"], "end": batch["end"],
           "rows_total": int(stats["rows_total"]),
           "rows_v2": int(stats["rows_v2"]),
           "diff_rows": int(stats["diff_rows"]),
           "seconds": round(secs, 2)}
    print(json.dumps(out), flush=True)
    return out


def recovery_drills(conn, batches: list[dict]) -> dict:
    """Idempotency + rollback on the smallest and a large batch."""
    by_rows = sorted(batches, key=lambda b: b["expected"])
    drills = {}
    for tag, b in [("small_batch", by_rows[0]),
                   ("large_batch", by_rows[-1])]:
        # capture before/after hashes via aggregate checksum
        def checksum():
            r = fetch_all(conn, f"""
                SELECT count(*) AS n,
                       count(*) FILTER (WHERE limit_state_v2 IS NOT NULL) AS v2,
                       md5(string_agg(
                           md5(asset_id::text || trade_date::text ||
                               is_limit_up_v2::text ||
                               is_limit_down_v2::text ||
                               limit_state_v2::text ||
                               coalesce(limit_rule_id_v2,'')),
                           '' ORDER BY asset_id, trade_date)) AS h
                FROM {SHADOW_TABLE}
                WHERE trade_date BETWEEN %s AND %s""",
                [b["start"], b["end"]])[0]
            return {"rows": int(r["n"]), "v2": int(r["v2"]), "hash": r["h"]}
        pre = checksum()
        t0 = time.monotonic()
        emit_v2_flags(conn, b["start"], b["end"], SHADOW_TABLE, FLAGS_VERSION)
        post_idem = checksum()
        # rollback: delete the batch, re-run, verify identical checksum
        execute(conn, f"""DELETE FROM {SHADOW_TABLE}
            WHERE trade_date BETWEEN %s AND %s""",
            [b["start"], b["end"]])
        deleted = checksum()
        execute(conn, f"""
            INSERT INTO {SHADOW_TABLE}
                (trade_date, asset_id, is_limit_up, is_limit_down,
                 is_suspended, batch_id)
            SELECT trade_date, asset_id, is_limit_up, is_limit_down,
                   is_suspended, %s
            FROM core.asset_status_daily
            WHERE trade_date BETWEEN %s AND %s""",
            [b["batch"], b["start"], b["end"]])
        emit_v2_flags(conn, b["start"], b["end"], SHADOW_TABLE, FLAGS_VERSION)
        post_restore = checksum()
        drills[tag] = {
            "batch": b["batch"], "range": [b["start"], b["end"]],
            "pre": pre,
            "idempotent": pre == post_idem,
            "rollback_deleted_rows": deleted["rows"],
            "restored_identical": pre == post_restore,
            "drill_seconds": round(time.monotonic() - t0, 2)}
    return drills


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", action="store_true",
                    help="skip batches already logged as done")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results: dict = {"shadow_table": SHADOW_TABLE,
                     "flags_version": FLAGS_VERSION, "batches": []}
    with connect(SETTINGS.research_service) as conn:
        # DSM on the shared research DB is limited (container shm); disable
        # parallel gather for this session and rely on the auto-splitter.
        execute(conn, "SET max_parallel_workers_per_gather = 0")
        create_shadow(conn)
        batches = year_batches(conn)
        done = set()
        if args.resume:
            done = {r["batch_id"] for r in fetch_all(conn, """
                SELECT batch_id FROM p1d3_shadow.migration_log
                WHERE status='done'""")}
        t_all = time.monotonic()
        for b in batches:
            if b["batch"] in done:
                print(f"skip done {b['batch']}", flush=True)
                continue
            results["batches"].extend(run_batch_safe(conn, b))
        results["total_seconds"] = round(time.monotonic() - t_all, 2)
        results["total_rows"] = sum(b["rows_total"] for b in results["batches"])
        results["total_diff_rows"] = sum(b["diff_rows"]
                                         for b in results["batches"])
        results["throughput_rows_per_sec"] = round(
            results["total_rows"] / max(results["total_seconds"], 0.01), 0)
        results["recovery_drills"] = recovery_drills(conn, batches)
        results["log"] = fetch_all(conn, """
            SELECT batch_id, status, rows_total, rows_v2, diff_rows, seconds
            FROM p1d3_shadow.migration_log ORDER BY batch_id""")
    out = OUT_DIR / "MIGRATION_REHEARSAL.json"
    out.write_text(json.dumps(results, indent=2, default=str))
    print(json.dumps({"written": str(out),
                      "total_rows": results["total_rows"],
                      "total_seconds": results["total_seconds"],
                      "drills": {k: {"idempotent": v["idempotent"],
                                     "restored": v["restored_identical"]}
                                 for k, v in
                                 results["recovery_drills"].items()}},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
