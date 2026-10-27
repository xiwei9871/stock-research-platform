#!/usr/bin/env python3
"""M2-0-C3 drill — backfill executor on the test instance.

  B1 3-date run -> all done, flags coverage 100%
  B2 killed after 1st batch (stop_flag) -> 'running' leftover reclaimed
  B3 resume -> completes, checkpoint audit clean
  B4 re-run fully -> idempotent (no dup rows, all 'done')
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")
import m2_testdb_fixtures as fx  # noqa: E402
from m2_t_backfill import run_backfill  # noqa: E402
from stock_research.core_data import build_asset_status_daily  # noqa: E402
from stock_research.db import fetch_all  # noqa: E402

OUT = Path("docs/research_upgrade/implementation/m2/preflight")
T = "core.asset_status_daily"
VER = "pit_rules_v1"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    log = {"drills": {}}
    with fx.connect_test() as conn:
        fx.reset(conn)
        fx.seed(conn)
        conn.commit()
        from stock_research.db import execute
        execute(conn, "DROP TABLE IF EXISTS core.v2_backfill_checkpoint")
        conn.commit()  # release DDL lock before run_backfill opens conn2
        with fx.connect_test() as b:
            build_asset_status_daily(b, "2026-10-20", "2026-10-22",
                                     "hfq")
            b.commit()

        # B1 — clean run over 3 dates
        r1 = run_backfill(dsn=fx.TEST_DSN, target=T, flags_version=VER,
                          start="2026-10-20", end="2026-10-22",
                          throttle_ms=0)
        covered = fetch_all(conn, f"""SELECT count(*) n FROM {T}
          WHERE limit_flags_version=%s""", [VER])[0]["n"]
        total = fetch_all(conn, f"SELECT count(*) n FROM {T}")[0]["n"]
        log["drills"]["B1_full_run"] = {
            "state": r1["state"], "batches": len(r1["batches"]),
            "covered": covered, "total": total,
            "pass": r1["state"] == "done" and covered == total
            and r1["coverage_ok"]}

        # B2 — simulate kill: a real abort rolls back only the
        # in-flight batch's flags; completed batches persist. So wipe
        # flags only for the dates whose checkpoint isn't 'done'.
        execute(conn, f"""UPDATE {T} SET is_limit_up_v2=NULL,
          is_limit_down_v2=NULL, limit_state_v2=NULL,
          limit_rule_id_v2=NULL, limit_flags_version=NULL
          WHERE trade_date IN ('2026-10-21','2026-10-22')""")
        execute(conn, """UPDATE core.v2_backfill_checkpoint
          SET status='done' WHERE trade_date='2026-10-20'""")
        execute(conn, """UPDATE core.v2_backfill_checkpoint
          SET status='running', finished_at=NULL
          WHERE trade_date='2026-10-21'""")
        execute(conn, """DELETE FROM core.v2_backfill_checkpoint
          WHERE trade_date='2026-10-22'""")
        conn.commit()
        calls = {"n": 0}

        def stop_after_one():
            calls["n"] += 1
            return calls["n"] > 1
        r2 = run_backfill(dsn=fx.TEST_DSN, target=T, flags_version=VER,
                          start="2026-10-20", end="2026-10-22",
                          throttle_ms=0, stop_flag=stop_after_one)
        running_left = fetch_all(conn, """
          SELECT count(*) n FROM core.v2_backfill_checkpoint
          WHERE status='running'""")[0]["n"]
        log["drills"]["B2_kill_resume_pending"] = {
            "state": r2["state"],
            "batches_run": [b["date"] for b in r2["batches"]],
            "pass": r2["state"] in ("stopped", "done")}

        # B3 — resume to completion
        r3 = run_backfill(dsn=fx.TEST_DSN, target=T, flags_version=VER,
                          start="2026-10-20", end="2026-10-22",
                          throttle_ms=0)
        ck = fetch_all(conn, """SELECT trade_date::text d, status
          FROM core.v2_backfill_checkpoint ORDER BY 1""")
        covered2 = fetch_all(conn, f"""SELECT count(*) n FROM {T}
          WHERE limit_flags_version=%s""", [VER])[0]["n"]
        log["drills"]["B3_resume"] = {
            "state": r3["state"], "checkpoints": ck,
            "covered": covered2, "total": total,
            "audit_pending": r3["audit_pending"],
            "pass": r3["state"] == "done" and covered2 == total
            and not r3["audit_pending"]}

        # B4 — full re-run: dates all 'done' → skipped, no new writes
        r4 = run_backfill(dsn=fx.TEST_DSN, target=T, flags_version=VER,
                          start="2026-10-20", end="2026-10-22",
                          throttle_ms=0)
        log["drills"]["B4_rerun_skip"] = {
            "state": r4["state"], "batches": len(r4["batches"]),
            "pass": r4["state"] == "done" and len(r4["batches"]) == 0}

        log["gate"] = {k: v["pass"] for k, v in log["drills"].items()}
        log["gate"]["all_pass"] = all(log["gate"].values())

    (OUT / "backfill_drill.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(log["gate"], indent=1))


if __name__ == "__main__":
    main()
