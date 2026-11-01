#!/usr/bin/env python3
"""M2.0.1 P0-B — controlled V2 backfill executor (hardened).

SAFETY MODEL (no silent writes anywhere):
  * default --mode is `dry-run`: full plan+emit executed then ROLLED BACK
  * target instance identity is verified from CONNECTION INFO, never
    from flags alone — --dsn cannot bypass prod protection
  * three classes: test (localhost + *_test db), prod (192.168.3.187
    stock_research), unknown — write mode refuses anything but test or
    double-permitted prod
  * prod write requires BOTH --allow-prod AND --prod-confirm
    "192.168.3.187:5432:stock_research" (typed identity, double permit)
  * target table must match ^<schema>.asset_status* and pass the v2
    contract column check
  * checkpoint DDL is NOT auto-created — ops_m2.v2_backfill_checkpoint
    must exist (separate reviewed migration), else BLOCKED
  * reconciliation: coverage_ok only when the FULL expected trade-date
    set is checkpointed done WITH the expected version AND the
    data-vs-checkpoint aggregate audit matches
  * stop: --stop-file + SIGTERM/SIGINT — current batch commits, next
    batch not started; resume is idempotent
  * resources: --max-wal-mb reads pg_ls_waldir per batch; local targets
    get real `df` free-space checks; unmeasurable remote disk requires
    explicit --disk-unmeasurable-ack (still refused for prod)

Production execution is NOT authorized. All drills run on the
independent local PG16 instance (stock_m2_test).
"""
import argparse
import json
import os
import re
import shutil
import signal
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, "src")
import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from stock_research.eod_v2_writer import emit_eod_v2_flags  # noqa: E402

PROD_IDENTITY = {"host": "192.168.3.187", "port": 5432,
                 "dbname": "stock_research"}
PROD_TABLE = "core.asset_status_daily"
TARGET_RE = re.compile(r"^[a-z_][a-z0-9_]*\.asset_status[a-z0-9_]*$")
CKPT_TABLE = "ops_m2.v2_backfill_checkpoint"

CKPT_REQUIRED_COLS = {
    "target_table", "trade_date", "flags_version", "status",
    "row_count", "checksum", "run_id", "started_at", "finished_at",
}

_STOP = {"flag": False}


def _sig(_n, _f):
    _STOP["flag"] = True


def _identify(conn):
    """Classify the connected instance from conninfo + db facts."""
    info = conn.info
    host = (info.host or "").lower()
    try:
        port = int(info.port)
    except (TypeError, ValueError):
        port = 0
    db = info.dbname or ""
    is_local = host in {"localhost", "127.0.0.1", "::1"}
    if host == PROD_IDENTITY["host"] and port == PROD_IDENTITY["port"] \
            and db == PROD_IDENTITY["dbname"]:
        kind = "prod"
    elif is_local and "test" in db:
        kind = "test"
    else:
        kind = "unknown"
    return {"host": host, "port": port, "dbname": db, "kind": kind,
            "is_local": is_local}


def _wal_bytes(conn):
    row = conn.execute(
        "SELECT COALESCE(sum(size),0) b FROM pg_ls_waldir()").fetchone()
    return int(row["b"] if isinstance(row, dict) else row[0])


def _disk_free_mb(conn, ident):
    """Real free space when measurable, else None."""
    if ident["is_local"]:
        data_dir = conn.execute(
            "SELECT setting FROM pg_settings WHERE name='data_directory'"
        ).fetchone()
        data_dir = (data_dir or {}).get("setting") \
            if isinstance(data_dir, dict) else (data_dir or [None])[0]
        if data_dir:
            return shutil.disk_usage(data_dir).free // (1024 * 1024)
    return None


def _check_checkpoint_schema(conn):
    cols = {r["column_name"] for r in conn.execute(
        """SELECT column_name FROM information_schema.columns
           WHERE table_schema='ops_m2'
             AND table_name='v2_backfill_checkpoint'""")}
    return CKPT_REQUIRED_COLS - cols


def _expected_dates(conn, target, start, end):
    return [r["d"] for r in conn.execute(
        f"""SELECT DISTINCT trade_date::text d FROM {target}
            WHERE trade_date BETWEEN %s AND %s ORDER BY 1""",
        [start, end])]


def _ckpt_rows(conn, target):
    return {r["trade_date"]: r for r in conn.execute(
        f"""SELECT trade_date::text trade_date, flags_version, status,
                   row_count, checksum
            FROM {CKPT_TABLE} WHERE target_table=%s""",
        [target])}


def _data_audit(conn, target, start, end, version):
    return {r["trade_date"]: r for r in conn.execute(
        f"""SELECT trade_date::text trade_date, count(*) base_n,
              count(*) FILTER (WHERE limit_flags_version=%s
                AND limit_state_v2 IS NOT NULL
                AND limit_rule_id_v2 IS NOT NULL) covered_n
            FROM {target}
            WHERE trade_date BETWEEN %s AND %s GROUP BY 1""",
        [version, start, end])}


def _batch_checksum(conn, target, d, version):
    r = conn.execute(
        f"""SELECT count(*) n,
              COALESCE(sum(limit_state_v2),-1) state_sum,
              count(DISTINCT limit_rule_id_v2) rules
            FROM {target} WHERE trade_date=%s""",
        [d]).fetchone()
    return f"n={r['n']};ss={r['state_sum']};ru={r['rules']};v={version}"


def run_backfill(*, dsn=None, service=None, target, flags_version,
                 start, end, mode="dry-run", throttle_ms=150,
                 allow_prod=False, prod_confirm=None,
                 stop_file=None, max_wal_mb=20480, min_free_mb=2048,
                 disk_unmeasurable_ack=False, emit_fn=None):
    from stock_research.db import execute
    from stock_research.eod_v2_writer import _check_target

    conn = (psycopg.connect(dsn, row_factory=dict_row) if dsn
            else psycopg.connect(f"service={service}",
                                 row_factory=dict_row))
    emit_fn = emit_fn or emit_eod_v2_flags
    run_id = str(uuid.uuid4())[:8]
    out = {"run_id": run_id, "target": target, "version": flags_version,
           "range": [start, end], "mode": mode, "batches": [],
           "state": "running"}
    try:
        signal.signal(signal.SIGTERM, _sig)
        signal.signal(signal.SIGINT, _sig)
    except ValueError:
        pass  # non-main thread: caller manages stopping via _STOP/stop-file
    wal0 = None
    try:
        # --- B1: identity + authorization ---
        ident = _identify(conn)
        out["identity"] = ident
        if not TARGET_RE.match(target):
            out.update(state="refused", reason="target outside "
                       "asset_status* scope")
            return out
        if mode == "write":
            if ident["kind"] == "unknown":
                out.update(state="refused",
                           reason="unrecognized instance — write denied")
                return out
            if ident["kind"] == "prod":
                typed = f"{ident['host']}:{ident['port']}:{ident['dbname']}"
                if not (allow_prod and prod_confirm == typed):
                    out.update(state="refused", reason="prod needs "
                               "--allow-prod AND --prod-confirm "
                               f"'{typed}'")
                    return out
                if target != PROD_TABLE:
                    out.update(state="refused",
                               reason=f"prod scope is {PROD_TABLE} only")
                    return out

        # --- B2: checkpoint contract must pre-exist ---
        missing = _check_checkpoint_schema(conn)
        if missing:
            out.update(state="blocked", reason="checkpoint table "
                       f"{CKPT_TABLE} missing cols {sorted(missing)} — "
                       "apply reviewed DDL first")
            conn.rollback()
            return out
        missing_cols = _check_target(conn, target)
        if missing_cols:
            out.update(state="aborted", reason="target lacks v2 "
                       f"contract cols {missing_cols}")
            conn.rollback()
            return out

        # --- B4: resource watermarks ---
        wal0 = _wal_bytes(conn)
        free_mb = _disk_free_mb(conn, ident)
        out["disk_free_mb"] = free_mb
        if mode == "write":
            if free_mb is None and not (disk_unmeasurable_ack
                                        and ident["kind"] == "test"):
                out.update(state="refused", reason="host disk not "
                           "measurable — long backfill forbidden "
                           "(test may pass --disk-unmeasurable-ack)")
                return out
            if free_mb is not None and free_mb < min_free_mb:
                out.update(state="blocked", reason="disk free "
                           f"{free_mb}MB < {min_free_mb}MB")
                return out

        # --- B3: reconciliation plan ---
        dates = _expected_dates(conn, target, start, end)
        ck = _ckpt_rows(conn, target)
        plan = {"expected_dates": len(dates), "pending": [],
                "retry_running": [], "wrong_version": [], "done": 0}
        for d in dates:
            c = ck.get(d)
            if not c or c["status"] == "failed":
                plan["pending"].append(d)
            elif c["status"] == "running":
                plan["retry_running"].append(d)
            elif c["flags_version"] != flags_version:
                plan["wrong_version"].append(d)
            else:
                plan["done"] += 1
        todo = plan["pending"] + plan["retry_running"] + \
            plan["wrong_version"]
        out["plan"] = {k: (len(v) if isinstance(v, list) else v)
                       for k, v in plan.items()}

        for d in todo:
            if _STOP["flag"] or (stop_file and Path(stop_file).exists()):
                out["state"] = "stopped"
                break
            if wal0 is not None and _wal_bytes(conn) - wal0 > \
                    max_wal_mb * 1024 * 1024:
                out["state"] = "blocked"
                out["reason"] = f"WAL growth exceeded {max_wal_mb}MB"
                break
            execute(conn, f"""
              INSERT INTO {CKPT_TABLE}
                (target_table, trade_date, flags_version, status,
                 run_id, started_at)
              VALUES (%s,%s,%s,'running',%s,now())
              ON CONFLICT (target_table, trade_date)
              DO UPDATE SET status='running', run_id=%s,
                            started_at=now(), finished_at=NULL""",
                    [target, d, flags_version, run_id, run_id])
            r = emit_fn(conn, d, target, flags_version, enabled=True)
            batch = {"date": d, "status": r["status"],
                     "matched": r.get("matched_rows"),
                     "missing": r.get("missing_keys"),
                     "invalid": r.get("invalid_rows")}
            if r["status"] in ("written", "idempotent"):
                cksum = _batch_checksum(conn, target, d, flags_version)
                execute(conn, f"""
                  UPDATE {CKPT_TABLE}
                  SET status='done', row_count=%s, checksum=%s,
                      finished_at=now()
                  WHERE target_table=%s AND trade_date=%s""",
                        [r["matched_rows"], cksum, target, d])
                if mode == "write":
                    conn.commit()
                else:
                    batch["dry_run_rolled_back"] = True
                out["batches"].append(batch)
            else:
                conn.rollback()
                batch["failed"] = True
                out["batches"].append(batch)
                out["state"] = "failed"
                break
            if throttle_ms and mode == "write":
                time.sleep(throttle_ms / 1000)
        else:
            if out["state"] == "running":
                out["state"] = "done"

        # --- B3 final audit: FULL expected set vs data ---
        if out["state"] == "done":
            data = _data_audit(conn, target, start, end, flags_version)
            ck2 = _ckpt_rows(conn, target)
            gaps = []
            for d in dates:
                c = ck2.get(d)
                dinfo = data.get(d, {})
                if not c or c["status"] != "done" or \
                        c["flags_version"] != flags_version:
                    gaps.append({"date": d, "issue": "checkpoint"})
                elif dinfo.get("covered_n", 0) < dinfo.get("base_n", 1):
                    gaps.append({"date": d, "issue": "data_incomplete",
                                 "covered": dinfo.get("covered_n"),
                                 "base": dinfo.get("base_n")})
            out["audit_gaps"] = gaps
            out["coverage_ok"] = not gaps
        out["wal_delta_mb"] = (
            (_wal_bytes(conn) - wal0) // (1024 * 1024)
            if wal0 is not None else None)
        if mode == "dry-run":
            conn.rollback()
            out["rolled_back"] = True
        else:
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
    ap.add_argument("--mode", choices=["dry-run", "write"],
                    default="dry-run")
    ap.add_argument("--throttle-ms", type=int, default=150)
    ap.add_argument("--allow-prod", action="store_true")
    ap.add_argument("--prod-confirm")
    ap.add_argument("--stop-file")
    ap.add_argument("--max-wal-mb", type=int, default=20480)
    ap.add_argument("--min-free-mb", type=int, default=2048)
    ap.add_argument("--disk-unmeasurable-ack", action="store_true")
    a = ap.parse_args()
    if not (a.dsn or a.service):
        ap.error("--dsn or --service required")
    out = run_backfill(dsn=a.dsn, service=a.service, target=a.target,
                       flags_version=a.version, start=a.start,
                       end=a.end, mode=a.mode, throttle_ms=a.throttle_ms,
                       allow_prod=a.allow_prod, prod_confirm=a.prod_confirm,
                       stop_file=a.stop_file, max_wal_mb=a.max_wal_mb,
                       min_free_mb=a.min_free_mb,
                       disk_unmeasurable_ack=a.disk_unmeasurable_ack)
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
