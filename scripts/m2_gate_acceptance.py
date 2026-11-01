#!/usr/bin/env python3
"""M2-0-B4 — integrity gate adversarial acceptance (test instance).

Each case mutates ONLY the local stock_m2_test database.
Output: INTEGRITY_GATE_ACCEPTANCE.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")
import m2_testdb_fixtures as fx  # noqa: E402
import stock_research.financial_version_store as fvs  # noqa: E402
from stock_research.data_integrity_gate import (  # noqa: E402
    combine, evaluate_financial, evaluate_requirements,
    evaluate_tradeability)
from stock_research.db import execute, fetch_all  # noqa: E402

OUT = Path("docs/research_upgrade/implementation/m2/preflight")
T = "core.asset_status_daily"
VER = "pit_rules_v1"
EP = "stock_profit_sheet_by_report_em"


def flag_some(conn, date, n_offset, n_limit, version=VER,
              state=1, rule="sse_main_normal_10"):
    execute(conn, f"""UPDATE {T}
      SET is_limit_up_v2=false, is_limit_down_v2=false,
          limit_state_v2=%s, limit_rule_id_v2=%s,
          limit_flags_version=%s
      WHERE trade_date=%s AND asset_id IN (
        SELECT asset_id FROM {T} WHERE trade_date=%s
        ORDER BY asset_id OFFSET %s LIMIT %s)""",
            [state, rule, version, date, date, n_offset, n_limit])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cases = []
    with fx.connect_test() as conn:
        fx.reset(conn)
        fx.seed(conn)
        conn.commit()
        # fill base status
        from stock_research.core_data import build_asset_status_daily
        with fx.connect_test() as b:
            build_asset_status_daily(b, "2026-10-20", "2026-10-22",
                                     "hfq")
            b.commit()

        def check(name, expect, got, detail=""):
            cases.append({"case": name, "expect": expect,
                          "got": got, "detail": detail,
                          "pass": got == expect})

        # C1 combine edges
        check("combine_empty", "BLOCKED", combine())
        check("combine_unknown", "BLOCKED",
              combine("READY", "SOMETHING_ELSE"))
        check("combine_blocked_wins", "BLOCKED",
              combine("V2_READY", "BLOCKED"))
        check("combine_degraded", "DEGRADED",
              combine("READY", "DEGRADED"))

        # C2 legacy cannot satisfy v2 requirement
        r = evaluate_requirements(conn, {"tradeability": {
            "require_v2": True, "expected_version": VER,
            "trade_dates": ["2026-10-20"]}})
        # fixture table HAS v2 cols; zero flags → DEGRADED→require_v2
        # forces BLOCKED. A table without v2 cols → LEGACY→BLOCKED.
        execute(conn, f"""CREATE TABLE IF NOT EXISTS
          core.asset_status_v1only
          (LIKE core.asset_status_daily INCLUDING ALL)""")
        execute(conn, f"""ALTER TABLE core.asset_status_v1only
          DROP COLUMN IF EXISTS is_limit_up_v2,
          DROP COLUMN IF EXISTS is_limit_down_v2,
          DROP COLUMN IF EXISTS limit_state_v2,
          DROP COLUMN IF EXISTS limit_rule_id_v2,
          DROP COLUMN IF EXISTS limit_flags_version""")
        execute(conn, f"""INSERT INTO core.asset_status_v1only
          (trade_date, asset_id, is_trade, is_st, is_suspended, source)
          SELECT trade_date, asset_id, is_trade, is_st, is_suspended,
                 source FROM {T}""")
        r2 = evaluate_tradeability(conn, "core.asset_status_v1only",
                                   require_v2=True,
                                   expected_version=VER,
                                   trade_dates=["2026-10-20"])
        check("legacy_cannot_satisfy_v2", "BLOCKED", r2["state"],
              "v1-only table + require_v2")
        r2b = evaluate_tradeability(conn, "core.asset_status_v1only",
                                    require_v2=False,
                                    trade_dates=["2026-10-20"])
        check("legacy_v1_healthy", "LEGACY_READY", r2b["state"])

        # C3 zero coverage under v2 cols -> not READY
        r3 = evaluate_tradeability(conn, T, require_v2=True,
                                   expected_version=VER,
                                   trade_dates=["2026-10-20"])
        check("zero_coverage_blocked", "BLOCKED", r3["state"],
              "require_v2 + zero flags → blocked")

        # C4 partial coverage -> DEGRADED (or BLOCKED under require_v2)
        flag_some(conn, "2026-10-20", 0, 3)
        r4 = evaluate_tradeability(conn, T, trade_dates=["2026-10-20"])
        check("partial_coverage", "DEGRADED", r4["state"])
        r4b = evaluate_tradeability(conn, T, require_v2=True,
                                    expected_version=VER,
                                    trade_dates=["2026-10-20"])
        check("partial_require_v2", "BLOCKED", r4b["state"])

        # C5 correct version but missing rule_id -> BLOCKED
        flag_some(conn, "2026-10-21", 0, 2, rule="")
        r5 = evaluate_tradeability(conn, T,
                                   expected_version=VER,
                                   trade_dates=["2026-10-21"])
        check("missing_rule_id", "BLOCKED", r5["state"],
              "rule_id '' must fail-closed")
        execute(conn, f"""UPDATE {T}
          SET is_limit_up_v2=NULL, is_limit_down_v2=NULL,
              limit_state_v2=NULL, limit_rule_id_v2=NULL,
              limit_flags_version=NULL WHERE trade_date='2026-10-21'""")

        # C6 wrong expected version -> BLOCKED
        flag_some(conn, "2026-10-22", 0, 9, version="rogue_vX")
        r6 = evaluate_tradeability(conn, T, expected_version=VER,
                                   require_v2=True,
                                   trade_dates=["2026-10-22"])
        check("foreign_version", "BLOCKED", r6["state"])
        execute(conn, f"""UPDATE {T} SET is_limit_up_v2=NULL,
          is_limit_down_v2=NULL, limit_state_v2=NULL,
          limit_rule_id_v2=NULL, limit_flags_version=NULL
          WHERE trade_date='2026-10-22'""")

        # C7 per-date consistency: full+valid coverage on one date
        flag_some(conn, "2026-10-20", 0, 99)
        r7 = evaluate_tradeability(conn, T, expected_version=VER,
                                   require_v2=True,
                                   trade_dates=["2026-10-20"])
        check("full_valid_coverage", "V2_READY", r7["state"])
        # date window spanning a fully-flagged + unflagged date
        r7b = evaluate_tradeability(conn, T, expected_version=VER,
                                    require_v2=True,
                                    trade_dates=["2026-10-20",
                                                 "2026-10-21"])
        check("window_partial", "BLOCKED", r7b["state"],
              "10-21 has zero flags in window")

        # C8 unverifiable states counted (not silently tradable)
        execute(conn, f"""UPDATE {T} SET limit_state_v2=3
          WHERE trade_date='2026-10-20' AND asset_id IN (
            SELECT asset_id FROM {T} WHERE trade_date='2026-10-20'
            LIMIT 2)""")
        r8 = evaluate_tradeability(conn, T, expected_version=VER,
                                   trade_dates=["2026-10-20"])
        check("unverifiable_counted", "V2_READY", r8["state"],
              f"unverifiable_rows={r8['checks'].get('unverifiable_rows')}")
        cases[-1]["unverifiable_rows"] = r8["checks"].get(
            "unverifiable_rows")

        # F1 finver: prod schema absent -> BLOCKED; shadow ≠ prod
        rf1 = evaluate_financial(conn, "finver")
        check("finver_prod_absent", "BLOCKED", rf1["state"],
              "no finver schema yet")
        # deploy schema only (no writes) -> DEGRADED not READY
        for stmt in fvs.ddl("finver").split(";"):
            if stmt.strip():
                execute(conn, stmt)
        conn.commit()
        rf2 = evaluate_financial(conn, "finver")
        check("finver_schema_only", "DEGRADED", rf2["state"],
              "tables exist, zero write evidence")
        # shadow schema present must NOT promote production verdict
        for stmt in fvs.ddl("m1_shadow_test").split(";"):
            if stmt.strip():
                execute(conn, stmt)
        fvs.ingest_payload(conn, "m1_shadow_test", "CN:X:1", EP,
                           "2025-01-01",
                           [{"REPORT_DATE": "2024-12-31",
                             "NETPROFIT": 1}], 1, "x")
        conn.commit()
        rf3 = evaluate_financial(conn, "finver")
        check("shadow_not_prod", "DEGRADED", rf3["state"],
              "shadow finver data must not promote 'finver' verdict")
        # real writes + raw evidence -> READY
        fvs.ingest_payload(conn, "finver", "CN:X:1", EP, "2025-01-01",
                           [{"REPORT_DATE": "2024-12-31",
                             "NETPROFIT": 1}], 1, "x")
        execute(conn, """INSERT INTO raw_akshare.finance_payload
          (source_endpoint, asset_id, payload, payload_hash)
          VALUES ('ep','CN:X:1','[]','h')""")
        conn.commit()
        rf4 = evaluate_financial(conn, "finver")
        check("finver_with_data", "READY", rf4["state"])

        # G combine requirement: empty requirements -> BLOCKED
        rg = evaluate_requirements(conn, {})
        check("requirements_empty", "BLOCKED", rg["combined"])
        rg2 = evaluate_requirements(conn, {"nonsense": {}})
        check("requirements_no_domains", "BLOCKED", rg2["combined"])

        passed = sum(1 for c in cases if c["pass"])
        out = {"instance": "stock_m2_test (local PG16)",
               "cases": cases, "total": len(cases),
               "passed": passed, "all_pass": passed == len(cases)}
        conn.rollback()

    (OUT / "INTEGRITY_GATE_ACCEPTANCE.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({"passed": f"{passed}/{len(cases)}",
                      "failed": [c["case"] for c in cases
                                 if not c["pass"]]}, indent=1))


if __name__ == "__main__":
    main()
