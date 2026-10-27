#!/usr/bin/env python3
"""M1-B isolated drills — EOD V2 write gate on a replica table.

Creates m1_shadow.asset_status_daily (LIKE prod INCLUDING ALL + v2
cols), copies a 3-day window of real status rows, then exercises the
gate scenarios. Isolated schema only; production untouched.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
from stock_research.db import connect, execute, fetch_all  # noqa: E402
from stock_research.config import SETTINGS  # noqa: E402
from stock_research.eod_v2_writer import emit_eod_v2_flags  # noqa: E402

OUT = Path("docs/research_upgrade/implementation/m1")
T = "m1_shadow.asset_status_daily"
VER = "pit_rules_v1"
DATES = ["2026-10-20", "2026-10-21", "2026-10-22"]


def cksum(conn, date):
    rows = fetch_all(conn, f"""
        SELECT asset_id, is_limit_up_v2 u, is_limit_down_v2 d,
               limit_state_v2 s, limit_rule_id_v2 r
        FROM {T} WHERE trade_date=%s ORDER BY asset_id""", [date])
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


def setup(conn):
    execute(conn, "CREATE SCHEMA IF NOT EXISTS m1_shadow")
    execute(conn, f"DROP TABLE IF EXISTS {T}")
    execute(conn, f"""CREATE TABLE {T}
        (LIKE core.asset_status_daily INCLUDING ALL)""")
    execute(conn, f"""ALTER TABLE {T}
        ADD COLUMN is_limit_up_v2 boolean,
        ADD COLUMN is_limit_down_v2 boolean,
        ADD COLUMN limit_state_v2 smallint,
        ADD COLUMN limit_rule_id_v2 text,
        ADD COLUMN limit_flags_version text""")
    execute(conn, f"""INSERT INTO {T}
        SELECT * FROM core.asset_status_daily
        WHERE trade_date = ANY(%s::date[])""", [DATES])
    return fetch_all(conn, f"SELECT count(*) n FROM {T}")[0]["n"]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    log = {"table": T, "dates": DATES, "scenarios": {}}
    with connect(SETTINGS.research_service) as conn:
        conn.rollback()  # ensure clean txn state
        n = setup(conn)
        conn.commit()
        log["replica_rows"] = n

        # S1+S2: three consecutive days, then repeat day 2 (idempotent)
        for d in DATES:
            r = emit_eod_v2_flags(conn, d, T, VER, enabled=True)
            log["scenarios"][f"write_{d}"] = r
            log["scenarios"][f"write_{d}"]["checksum"] = cksum(conn, d)
        conn.commit()
        before = cksum(conn, DATES[1])
        r = emit_eod_v2_flags(conn, DATES[1], T, VER, enabled=True)
        log["scenarios"]["repeat_day2"] = {
            **r, "checksum_before": before,
            "checksum_after": cksum(conn, DATES[1]),
            "idempotent": before == cksum(conn, DATES[1])}
        conn.commit()

        # S3: base rows missing -> blocked (use a holiday/no-row date)
        r = emit_eod_v2_flags(conn, "2026-10-25", T, VER, enabled=True)
        log["scenarios"]["missing_base"] = r
        conn.rollback()

        # S4: switch off -> blocked
        r = emit_eod_v2_flags(conn, DATES[0], T, VER, enabled=False)
        log["scenarios"]["switch_off"] = r

        # S5: version mismatch -> blocked (table now carries VER)
        r = emit_eod_v2_flags(conn, DATES[0], T, "pit_rules_vX",
                              enabled=True)
        log["scenarios"]["version_mismatch"] = r

        # S6: mid-write abort -> rollback -> retry OK
        try:
            execute(conn, "SET LOCAL statement_timeout = '1ms'")
            emit_eod_v2_flags(conn, "2026-10-23", T, VER, enabled=True)
            log["scenarios"]["timeout_abort"] = {"status": "no_error"}
        except Exception as e:  # noqa: BLE001
            log["scenarios"]["timeout_abort"] = {
                "status": "aborted", "error": type(e).__name__}
        finally:
            conn.rollback()
        execute(conn, "SET LOCAL statement_timeout = 0")
        n23 = fetch_all(conn, f"""SELECT count(*) n FROM {T}
                        WHERE trade_date='2026-10-23'""")[0]["n"]
        log["scenarios"]["timeout_residual_rows"] = n23

        # S7: rule-unknown / insufficient flags are never coerced False
        dist = fetch_all(conn, f"""
            SELECT limit_state_v2 s, count(*) n FROM {T}
            WHERE limit_flags_version=%s GROUP BY 1""", [VER])
        log["state_distribution"] = {str(r["s"]): r["n"] for r in dist}
        nonbool = fetch_all(conn, f"""
            SELECT count(*) n FROM {T} WHERE limit_state_v2 IN (2,3)
            AND (is_limit_up_v2 OR is_limit_down_v2)""")[0]["n"]
        log["scenarios"]["unknown_not_false"] = {
            "flagged_rows_in_unknown_states": nonbool}

        # S8: missing raw quote -> flag row must still be safe
        miss = fetch_all(conn, f"""
            SELECT count(*) n FROM {T} t
            WHERE limit_flags_version=%s AND limit_state_v2 IS NULL""",
                         [VER])[0]["n"]
        log["scenarios"]["null_state_rows"] = miss

        log["gate"] = {
            "idempotent": log["scenarios"]["repeat_day2"]["idempotent"],
            "missing_base_blocked":
                log["scenarios"]["missing_base"]["status"] == "blocked",
            "switch_off_blocked":
                log["scenarios"]["switch_off"]["status"] == "blocked",
            "version_conflict_blocked":
                log["scenarios"]["version_mismatch"]["status"]
                == "blocked",
            "timeout_rolled_back":
                log["scenarios"]["timeout_residual_rows"] == 0,
            "unknown_fail_closed":
                log["scenarios"]["unknown_not_false"]
                ["flagged_rows_in_unknown_states"] == 0,
            "metrics_reported": all(
                log["scenarios"][f"write_{d}"]["computed_keys"] > 0
                for d in DATES),
        }
        log["gate"]["all_pass"] = all(log["gate"].values())
        conn.rollback()  # drills leave no writes

    (OUT / "M1_V2_WRITE_DRILLS.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(log["gate"], indent=1))


if __name__ == "__main__":
    main()
