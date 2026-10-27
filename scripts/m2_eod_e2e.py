#!/usr/bin/env python3
"""M2-0-C2 — EOD V2 E2E drills on the INDEPENDENT test instance.

Real call chain: build_asset_status_daily (own txn, production shape)
-> run_eod_v2_stage (separate txn) -> verdict read-back.
Proves commit-boundary honesty, failure recovery, incomplete handling.
Output: docs/.../m2/preflight/EOD_E2E_TEST_REPORT data JSON.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")
import m2_testdb_fixtures as fx  # noqa: E402
from stock_research.core_data import build_asset_status_daily  # noqa: E402
from stock_research.eod_v2_writer import (  # noqa: E402
    emit_eod_v2_flags, run_eod_v2_stage)
from stock_research.db import execute, fetch_all  # noqa: E402

OUT = Path("docs/research_upgrade/implementation/m2/preflight")
T = "core.asset_status_daily"
VER = "pit_rules_v1"


def cksum(conn, date):
    rows = fetch_all(conn, f"""
      SELECT asset_id, is_limit_up, is_limit_down,
             is_limit_up_v2 u, is_limit_down_v2 d, limit_state_v2 s,
             limit_rule_id_v2 r, limit_flags_version v
      FROM {T} WHERE trade_date=%s ORDER BY asset_id""", [date])
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    log = {"instance": "stock_m2_test (local PG16, independent)",
           "scenarios": {}}
    with fx.connect_test() as conn:
        fx.reset(conn)
        fx.seed(conn)
        conn.commit()
        # S0: build base status in its OWN txn (production boundary)
        with fx.connect_test() as b:
            build_asset_status_daily(b, "2026-10-20", "2026-10-22",
                                     "hfq")
            b.commit()
        base = fetch_all(conn, f"""SELECT trade_date::text d, count(*)
          n FROM {T} GROUP BY 1 ORDER BY 1""")
        log["scenarios"]["S0_build_own_txn"] = {"per_date": base}

        # S1: V2 stage runs in a SEPARATE txn after base commit
        r = run_eod_v2_stage(fx.TEST_DSN, "2026-10-20", T, VER,
                             enabled=True)
        log["scenarios"]["S1_v2_stage_written"] = r
        r2 = run_eod_v2_stage(fx.TEST_DSN, "2026-10-21", T, VER,
                              enabled=True)
        log["scenarios"]["S1b_day2"] = {"status": r2["status"],
                                        "committed": r2["committed"]}

        # S2: idempotent repeat — no commit needed, valid coverage
        pre = cksum(conn, "2026-10-20")
        r = run_eod_v2_stage(fx.TEST_DSN, "2026-10-20", T, VER,
                             enabled=True)
        log["scenarios"]["S2_idempotent_repeat"] = {
            "status": r["status"], "committed": r["committed"],
            "checksum_stable": pre == cksum(conn, "2026-10-20")}

        # S3: switch OFF -> blocked, nothing committed
        r = run_eod_v2_stage(fx.TEST_DSN, "2026-10-22", T, VER,
                             enabled=False)
        v22 = fetch_all(conn, f"""SELECT count(*) n FROM {T}
          WHERE trade_date='2026-10-22' AND limit_flags_version IS
          NOT NULL""")[0]["n"]
        log["scenarios"]["S3_switch_off"] = {
            "status": r["status"], "committed": r["committed"],
            "rows_flagged": v22}

        # S4: mid-UPDATE abort on populated date -> rollback -> retry
        pre_ck = cksum(conn, "2026-10-22")
        try:
            execute(conn, "SET statement_timeout='1ms'")
            emit_eod_v2_flags(conn, "2026-10-22", T, VER, enabled=True)
            abort = "no_error"
        except Exception as e:  # noqa: BLE001
            abort = type(e).__name__
        finally:
            conn.rollback()
            execute(conn, "RESET statement_timeout")
        post_ck = cksum(conn, "2026-10-22")
        r = run_eod_v2_stage(fx.TEST_DSN, "2026-10-22", T, VER,
                             enabled=True)
        log["scenarios"]["S4_abort_rollback_retry"] = {
            "abort": abort, "rollback_clean": pre_ck == post_ck,
            "retry_status": r["status"], "retry_committed":
            r["committed"]}

        # S5: INCOMPLETE — add a base row for an asset with no master
        with fx.connect_test() as c2:
            execute(c2, f"""INSERT INTO {T}
              (trade_date, asset_id, is_trade, is_st, is_suspended,
               is_limit_up, is_limit_down, source)
              VALUES ('2026-10-23','CN:XX:000000',true,false,false,
                      false,false,'fixture')""")
            c2.commit()
            emit_eod_v2_flags(c2, "2026-10-23", T, VER, enabled=True)
            res = fetch_all(c2, f"""SELECT count(*) n FROM {T}
              WHERE trade_date='2026-10-23'
                AND limit_flags_version=%s""", [VER])[0]["n"]
            base23 = fetch_all(c2, f"""SELECT count(*) n FROM {T}
              WHERE trade_date='2026-10-23'""")[0]["n"]
            r = emit_eod_v2_flags(c2, "2026-10-23", T, VER,
                                  enabled=True)
            log["scenarios"]["S5_incomplete"] = {
                "status": r["status"], "matched": res,
                "base": base23, "missing": r["missing_keys"],
                "pass": r["status"] == "incomplete"
                and r["missing_keys"] == 1}
            c2.rollback()  # discard partial-write txn
            # stage must refuse to commit and roll back
            r = run_eod_v2_stage(fx.TEST_DSN, "2026-10-23", T, VER,
                                 enabled=True)
            log["scenarios"]["S5b_stage_rolls_back"] = {
                "status": r["status"], "committed": r["committed"],
                "pass": not r["committed"]}

        # S6: state-2/3 rows never coerced to tradable booleans
        rows = fetch_all(conn, f"""
          SELECT limit_state_v2 st,
            count(*) FILTER (WHERE is_limit_up_v2 OR is_limit_down_v2)
              flagged_limit,
            count(*) n
          FROM {T} WHERE limit_flags_version=%s
          GROUP BY 1 ORDER BY 1""", [VER])
        log["scenarios"]["S6_state_dist"] = rows

        # S7: version conflict (foreign version) -> blocked, no commit
        with fx.connect_test() as c3:
            execute(c3, f"""UPDATE {T} SET limit_flags_version='rogue'
              WHERE trade_date='2026-10-20'
                AND asset_id='CN:SH:600001'""")
            c3.commit()
            r = run_eod_v2_stage(fx.TEST_DSN, "2026-10-20", T, VER,
                                 enabled=True)
            log["scenarios"]["S7_foreign_version"] = {
                "status": r["status"], "committed": r["committed"],
                "pass": r["status"] == "blocked"
                and not r["committed"]}
            execute(c3, f"""UPDATE {T} SET limit_flags_version=%s
              WHERE trade_date='2026-10-20'
                AND asset_id='CN:SH:600001'""", [VER])
            c3.commit()

        log["gate"] = {
            "build_then_stage": all(
                x["n"] > 0 for x in base),
            "stage_written": log["scenarios"]["S1_v2_stage_written"]
            ["status"] == "written",
            "idempotent": log["scenarios"]["S2_idempotent_repeat"]
            ["status"] == "idempotent",
            "switch_off_blocked":
                log["scenarios"]["S3_switch_off"]["status"]
                == "blocked" and not
                log["scenarios"]["S3_switch_off"]["committed"],
            "abort_rolled_back":
                log["scenarios"]["S4_abort_rollback_retry"]
                ["rollback_clean"],
            "retry_committed":
                log["scenarios"]["S4_abort_rollback_retry"]
                ["retry_committed"],
            "incomplete_detected":
                log["scenarios"]["S5_incomplete"]["pass"],
            "stage_rollback_on_incomplete":
                log["scenarios"]["S5b_stage_rolls_back"]["pass"],
            "foreign_version_blocked":
                log["scenarios"]["S7_foreign_version"]["pass"],
        }
        log["gate"]["all_pass"] = all(log["gate"].values())

    (OUT / "eod_e2e_results.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(log["gate"], indent=1))


if __name__ == "__main__":
    main()
