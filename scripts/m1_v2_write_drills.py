#!/usr/bin/env python3
"""M1-B v2 drills — EOD V2 write gate on a replica table (fixed).

P0-2: the fault-injection date now HAS base rows; we prove rollback +
checksum preservation + retry completion, and we synthesize partial/
invalid v2 states to prove the gate never reports false success.
Isolated schema only.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
from stock_research.db import connect, execute, fetch_all  # noqa: E402
from stock_research.config import SETTINGS  # noqa: E402
from stock_research.eod_v2_writer import emit_eod_v2_flags  # noqa: E402

OUT = Path("docs/research_upgrade/implementation/m1/final")
T = "m1_shadow.asset_status_daily"
VER = "pit_rules_v1"
DATES = ["2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"]


def cksum(conn, date, v2_only=False):
    rows = fetch_all(conn, f"""
        SELECT asset_id, is_limit_up v1u, is_limit_down v1d,
               is_limit_up_v2 u, is_limit_down_v2 d,
               limit_state_v2 s, limit_rule_id_v2 r,
               limit_flags_version ver
        FROM {T} WHERE trade_date=%s ORDER BY asset_id""", [date])
    if v2_only:
        rows = [{k: r[k] for k in ("asset_id", "u", "d", "s", "r", "ver")}
                for r in rows]
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
        n = setup(conn)
        conn.commit()
        log["replica_rows"] = n

        # S1: three consecutive days
        for d in DATES[:3]:
            r = emit_eod_v2_flags(conn, d, T, VER, enabled=True)
            log["scenarios"][f"write_{d}"] = {**r,
                                            "checksum": cksum(conn, d)}
        conn.commit()

        # S2: idempotent repeat with field-completeness validation
        before = cksum(conn, DATES[1])
        r = emit_eod_v2_flags(conn, DATES[1], T, VER, enabled=True)
        log["scenarios"]["repeat_day2"] = {
            **r, "idempotent": before == cksum(conn, DATES[1])}
        conn.commit()

        # S3: base rows absent -> blocked
        r = emit_eod_v2_flags(conn, "2026-10-25", T, VER, enabled=True)
        log["scenarios"]["missing_base"] = r
        conn.rollback()

        # S4: switch off -> blocked
        r = emit_eod_v2_flags(conn, DATES[0], T, VER, enabled=False)
        log["scenarios"]["switch_off"] = r

        # S5: version conflict -> blocked
        r = emit_eod_v2_flags(conn, DATES[0], T, "pit_rules_vX",
                              enabled=True)
        log["scenarios"]["version_mismatch"] = r

        # P0-2 — fault injection on a date WITH base rows (10-23)
        pre_v1 = cksum(conn, "2026-10-23")
        try:
            execute(conn, "SET statement_timeout = '1ms'")
            emit_eod_v2_flags(conn, "2026-10-23", T, VER, enabled=True)
            ab = {"status": "no_error"}
        except Exception as e:  # noqa: BLE001
            ab = {"status": "aborted", "error": type(e).__name__}
        finally:
            conn.rollback()
        post_v1 = cksum(conn, "2026-10-23")
        r = emit_eod_v2_flags(conn, "2026-10-23", T, VER, enabled=True)
        retry = {**r, "checksum": cksum(conn, "2026-10-23")}
        conn.commit()
        log["scenarios"]["fault_injection_1023"] = {
            "inject": ab, "pre_checksum": pre_v1,
            "post_abort_checksum": post_v1,
            "rollback_clean": pre_v1 == post_v1,
            "retry": retry}

        # P0-2 — synthesize partial + invalid v2, prove INCOMPLETE
        # strip version from 40 rows -> partial coverage
        execute(conn, f"""
          UPDATE {T} SET limit_flags_version=NULL
          WHERE trade_date='2026-10-22'
            AND asset_id IN (SELECT asset_id FROM {T}
              WHERE trade_date='2026-10-22' ORDER BY asset_id
              LIMIT 40)""")
        # corrupt 10 rows -> invalid fields under the version
        execute(conn, f"""
          UPDATE {T} SET limit_state_v2=3, is_limit_up_v2=NULL,
                 limit_rule_id_v2=''
          WHERE trade_date='2026-10-22'
            AND asset_id IN (SELECT asset_id FROM {T}
              WHERE trade_date='2026-10-22' ORDER BY asset_id
              OFFSET 40 LIMIT 10)""")
        r = emit_eod_v2_flags(conn, "2026-10-22", T, VER, enabled=True)
        healed = fetch_all(conn, f"""
          SELECT count(*) n FROM {T}
          WHERE trade_date='2026-10-22' AND limit_flags_version=%s
            AND limit_state_v2 IN (0,1,2,3) AND is_limit_up_v2 IS NOT NULL
            AND limit_rule_id_v2 IS NOT NULL AND btrim(limit_rule_id_v2)<>''""",
                           [VER])[0]["n"]
        base22 = fetch_all(conn, f"""SELECT count(*) n FROM {T}
                           WHERE trade_date='2026-10-22'""")[0]["n"]
        log["scenarios"]["partial_then_rewrite"] = {
            "rewrite_status": r["status"], "missing": r["missing_keys"],
            "invalid": r["invalid_rows"], "valid_after": healed,
            "base": base22,
            "pass": healed == base22 and r["status"] in
            ("written", "incomplete")}
        conn.commit()

        # unknown-state flags never coerced
        nonbool = fetch_all(conn, f"""
            SELECT count(*) n FROM {T} WHERE limit_state_v2 IN (2,3)
            AND (is_limit_up_v2 OR is_limit_down_v2)
            AND limit_flags_version=%s""", [VER])[0]["n"]
        log["scenarios"]["unknown_not_false"] = {
            "flagged_rows_in_unknown_states": nonbool}

        log["gate"] = {
            "idempotent": log["scenarios"]["repeat_day2"]["idempotent"],
            "missing_base_blocked":
                log["scenarios"]["missing_base"]["status"] == "blocked",
            "switch_off_blocked":
                log["scenarios"]["switch_off"]["status"] == "blocked",
            "version_conflict_blocked":
                log["scenarios"]["version_mismatch"]["status"]
                == "blocked",
            "fault_abort_rolled_back":
                log["scenarios"]["fault_injection_1023"]["rollback_clean"],
            "retry_completed":
                log["scenarios"]["fault_injection_1023"]["retry"]
                ["status"] == "written",
            "partial_rewrite_heals":
                log["scenarios"]["partial_then_rewrite"]["pass"],
            "unknown_fail_closed":
                log["scenarios"]["unknown_not_false"]
                ["flagged_rows_in_unknown_states"] == 0,
            "metrics_reported": all(
                log["scenarios"][f"write_{d}"]["computed_keys"] > 0
                for d in DATES[:3]),
        }
        log["gate"]["all_pass"] = all(log["gate"].values())
        conn.rollback()

    (OUT / "EOD_FAILURE_DRILLS.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(log["gate"], indent=1))


if __name__ == "__main__":
    main()
