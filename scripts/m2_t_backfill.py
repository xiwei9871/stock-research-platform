#!/usr/bin/env python3
"""M2-0-C3 — controlled V2 backfill executor (production-shaped).

SAFETY: --allow-prod MUST be passed explicitly for the production
service; default run targets the isolated test instance.

Design contract:
  * explicit target-table contract check (v2 columns) — refuses early
  * per-DATE batch transaction; each batch = emit_v2_flags + verify +
    checkpoint row, committed atomically
  * checkpoint table <schema>.v2_backfill_checkpoint — resume-safe:
    completed dates skipped; 'running' leftovers from a killed run are
    reclaimed and re-executed
  * idempotent by the writer's own contract (same version rewrite)
  * throttle between batches + stop flag + post-run full diff audit
Usage (test instance):
  python m2_t_backfill.py --dsn "<conninfo>" --from 2026-10-20 --to 2026-10-22
Production (NOT authorized yet): --service research --allow-prod
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")
import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from stock_research.eod_v2_writer import emit_eod_v2_flags  # noqa: E402

CKPT_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.v2_backfill_checkpoint (
  target_table   text NOT NULL,
  trade_date     date NOT NULL,
  flags_version  text NOT NULL,
  status         text NOT NULL,          -- running | done | failed
  base_rows      int, matched_rows int,
  missing_keys   int, invalid_rows int,
  started_at     timestamptz NOT NULL DEFAULT now(),
  finished_at    timestamptz,
  PRIMARY KEY (target_table, trade_date)
)"""


def _schema_of(table):
    return table.split(".")[0]


def run_backfill(*, dsn=None, service=None, target, flags_version,
                 start, end, throttle_ms=150, stop_flag=None,
                 allow_prod=False, emit_fn=None):
    from stock_research.db import execute, fetch_all
    from stock_research.eod_v2_writer import _check_target
    if service and not allow_prod:
        raise RuntimeError("refusing service target without --allow-prod")
    if dsn:
        conn = psycopg.connect(dsn, row_factory=dict_row)
    else:
        from stock_research.db import connect
        conn = connect(service).__enter__()
    emit_fn = emit_fn or emit_eod_v2_flags
    out = {"target": target, "version": flags_version,
           "range": [start, end], "batches": [], "state": "running"}
    try:
        schema = _schema_of(target)
        missing_cols = _check_target(conn, target)
        if missing_cols:
            out["state"] = "aborted"
            out["reason"] = f"target lacks v2 contract cols {missing_cols}"
            conn.rollback()
            return out
        execute(conn, CKPT_DDL.format(schema=schema))
        conn.commit()

        dates = [r["d"] for r in fetch_all(conn, f"""
          SELECT DISTINCT trade_date::text d FROM {target}
          WHERE trade_date BETWEEN %s AND %s ORDER BY 1""",
                                           [start, end])]
        done = {r["trade_date"] for r in fetch_all(conn, f"""
          SELECT trade_date::text trade_date FROM
          {schema}.v2_backfill_checkpoint
          WHERE target_table=%s AND status='done'""", [target])}
        for d in dates:
            if stop_flag and stop_flag():
                out["state"] = "stopped"
                break
            if d in done:
                continue
            execute(conn, f"""
              INSERT INTO {schema}.v2_backfill_checkpoint
                (target_table, trade_date, flags_version, status)
              VALUES (%s,%s,%s,'running')
              ON CONFLICT (target_table, trade_date)
              DO UPDATE SET status='running', started_at=now()""",
                    [target, d, flags_version])
            r = emit_fn(conn, d, target, flags_version, enabled=True)
            batch = {"date": d, "status": r["status"],
                     "matched": r.get("matched_rows"),
                     "missing": r.get("missing_keys"),
                     "invalid": r.get("invalid_rows")}
            if r["status"] in ("written", "idempotent"):
                execute(conn, f"""
                  UPDATE {schema}.v2_backfill_checkpoint
                  SET status='done', base_rows=%s, matched_rows=%s,
                      missing_keys=%s, invalid_rows=%s, finished_at=now()
                  WHERE target_table=%s AND trade_date=%s""",
                        [r.get("base_rows"), r["matched_rows"],
                         r["missing_keys"], r["invalid_rows"],
                         target, d])
                conn.commit()
            else:
                conn.rollback()
                batch["failed"] = True
                out["batches"].append(batch)
                out["state"] = "failed"
                break
            out["batches"].append(batch)
            if throttle_ms:
                time.sleep(throttle_ms / 1000)
        else:
            out["state"] = "done"
        if out["state"] == "running":
            out["state"] = "done"
        # post-run audit: any date in range with non-done checkpoint
        audit = fetch_all(conn, f"""
          SELECT trade_date::text d, status FROM
          {schema}.v2_backfill_checkpoint
          WHERE target_table=%s AND status<>'done'""", [target])
        out["audit_pending"] = audit
        out["coverage_ok"] = not audit and out["state"] == "done"
        conn.commit()
    finally:
        conn.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn")
    ap.add_argument("--service")
    ap.add_argument("--target", default="core.asset_status_daily")
    ap.add_argument("--version", default="pit_rules_v1")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--throttle-ms", type=int, default=150)
    ap.add_argument("--allow-prod", action="store_true")
    a = ap.parse_args()
    out = run_backfill(dsn=a.dsn, service=a.service, target=a.target,
                       flags_version=a.version, start=a.start,
                       end=a.end, throttle_ms=a.throttle_ms,
                       allow_prod=a.allow_prod)
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
