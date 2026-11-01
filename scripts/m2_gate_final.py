#!/usr/bin/env python3
"""P0-C acceptance — writer freshness, canary gate, consumer reqs.

Runs on stock_m2_test only. Writes:
  prelaunch/INTEGRITY_GATE_FINAL.json  + FINVER_WRITER_READINESS.md data
"""
import json
import os
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")
import m2_testdb_fixtures as fx  # noqa: E402
from stock_research.core_data import build_asset_status_daily  # noqa: E402
from stock_research.data_integrity_gate import (  # noqa: E402
    evaluate_eod_canary, evaluate_finver_writer,
    evaluate_requirements, v1_digest)
from stock_research.db import execute, fetch_all  # noqa: E402
from stock_research.eod_v2_writer import run_eod_v2_stage  # noqa: E402
from stock_research import financial_version_store as fvs  # noqa: E402

S = "finver"
T = "core.asset_status_daily"
VER = "pit_rules_v1"
D0, D1 = "2026-10-20", "2026-10-21"
OUT = "docs/research_upgrade/implementation/m2/prelaunch/" \
      "INTEGRITY_GATE_FINAL.json"
R = {}
A, EP = "CN:SH:600001", "zcfz_em"


def seed_finver(c, seen="2025-09-01T10:00"):
    for st in fvs.ddl(S).split(";"):
        if st.strip():
            execute(c, st)
    p = [{"REPORT_DATE": "2025-06-30", "NOTICE_DATE": "2025-08-28",
          "REPORT_TYPE": "中报", "NETPROFIT": 100.0}]
    rid = execute(c, """
        INSERT INTO raw_akshare.finance_payload
          (source_endpoint, asset_id, payload, payload_hash)
        VALUES (%s,%s,%s::jsonb,%s) RETURNING id""",
                  [EP, A, json.dumps(p), "h1"])
    rid = fetch_all(c, "SELECT max(id) i FROM "
                    "raw_akshare.finance_payload")[0]["i"]
    fvs.ingest_payload(c, S, A, EP, seen, p, rid, "h1")
    return p


def main():
    with fx.connect_test() as conn:
        fx.reset(conn)
        fx.seed(conn)
        build_asset_status_daily(conn, D0, D1, "hfq")
        conn.commit()

        # ---- W1: stale observation -> WRITER_READY False ----
        seed_finver(conn, "2020-01-01T00:00")
        conn.commit()
        w = evaluate_finver_writer(conn, S, staleness_hours=24)
        R["W1_stale_writer_rejected"] = (
            w["layers"]["WRITER_READY"] is False)

        # ---- W2: heartbeat evidence -> WRITER_READY True ----
        w = evaluate_finver_writer(conn, S, staleness_hours=24,
                                   heartbeat_at="now()")
        R["W2_heartbeat_accepted"] = w["layers"]["WRITER_READY"] is True

        # ---- W3: fresh observation -> True ----
        c2 = fx.connect_test()
        c2.execute(f"UPDATE {S}.finver_observation SET seen_at=now()")
        c2.commit(); c2.close()
        w = evaluate_finver_writer(conn, S, staleness_hours=24)
        R["W3_fresh_obs"] = w["layers"]["WRITER_READY"] is True

        # ---- W4: DATA_READY needs declared scope ----
        w = evaluate_finver_writer(conn, S, staleness_hours=24)
        R["W4_undeclared_scope_not_ready"] = (
            w["layers"]["DATA_READY"] is False)
        w = evaluate_finver_writer(conn, S, staleness_hours=24,
                                   expected_endpoints=[EP])
        R["W4b_scoped_data_ready"] = w["layers"]["DATA_READY"] is True

        # ---- W5: raw without observation counted ----
        execute(conn, """INSERT INTO raw_akshare.finance_payload
          (source_endpoint, asset_id, payload, payload_hash)
          VALUES (%s,%s,'[]','hx')""", [EP, "CN:SZ:000001"])
        w = evaluate_finver_writer(conn, S, staleness_hours=24,
                                   expected_endpoints=[EP])
        R["W5_raw_unreconciled"] = (
            w["layers"]["raw_without_observation"] >= 1
            and w["layers"]["DATA_READY"] is False)
        # clean up so later checks pass
        execute(conn, "DELETE FROM raw_akshare.finance_payload "
                "WHERE payload_hash='hx'")
        conn.commit()

        # ---- W6: chain corruption detected ----
        execute(conn, f"""UPDATE {S}.finver_key_chain
            SET n_versions = n_versions + 5""")
        w = evaluate_finver_writer(conn, S, staleness_hours=24,
                                   expected_endpoints=[EP])
        R["W6_chain_mismatch"] = (
            w["layers"]["nversions_mismatch"] >= 1
            and w["layers"]["DATA_READY"] is False)
        execute(conn, f"""UPDATE {S}.finver_key_chain
            SET n_versions = n_versions - 5""")
        conn.commit()

        # ---- C1: canary on un-emitted date -> not publishable ----
        ca = evaluate_eod_canary(conn, D0, VER, T)
        R["C1_pre_emit_not_publishable"] = ca["publishable"] is False

        # ---- C2: emit via real stage -> publishable, v1 intact ----
        dig0 = v1_digest(conn, D0, T)
        r = run_eod_v2_stage(fx.TEST_DSN, D0, T, VER, enabled=True)
        ca = evaluate_eod_canary(conn, D0, VER, T,
                                 v1_digest_before=dig0)
        R["C2_canary_publishable"] = (
            r["committed"] and ca["publishable"] is True
            and ca["checks"]["v1_digest"] == dig0)

        # ---- C3: foreign version -> not publishable ----
        ca = evaluate_eod_canary(conn, D0, "other_v9", T)
        R["C3_foreign_version"] = ca["publishable"] is False

        # ---- C4: sabotage one row -> not publishable ----
        execute(conn, f"""UPDATE {T} SET limit_rule_id_v2=NULL
            WHERE trade_date=%s AND asset_id='CN:SH:600001'""", [D0])
        ca = evaluate_eod_canary(conn, D0, VER, T)
        R["C4_invalid_row_blocks"] = ca["publishable"] is False
        execute(conn, f"""UPDATE {T} SET limit_rule_id_v2='sse_main_10'
            WHERE trade_date=%s AND asset_id='CN:SH:600001'""", [D0])
        conn.commit()

        # ---- Q1: V2 consumer on legacy table -> BLOCKED ----
        execute(conn, "DROP TABLE IF EXISTS core.legacy_status")
        execute(conn, f"""CREATE TABLE core.legacy_status AS
            SELECT trade_date, asset_id, is_trade, is_st,
                   is_suspended, is_limit_up, is_limit_down,
                   limit_up_price, limit_down_price, source,
                   updated_at FROM {T}""")
        conn.commit()
        q = evaluate_requirements(conn, {
            "tradeability": {"require_v2": True,
                             "expected_version": VER,
                             "table": "core.legacy_status",
                             "trade_dates": [D0]}})
        R["Q1_legacy_cant_satisfy_v2"] = (
            q["satisfied"]["tradeability"] is False
            and q["combined"] == "BLOCKED")

        # ---- Q2: V2 consumer on emitted date -> satisfied ----
        q = evaluate_requirements(conn, {
            "tradeability": {"require_v2": True,
                             "expected_version": VER,
                             "table": T,
                             "trade_dates": [D0]}})
        R["Q2_v2_consumer_satisfied"] = (
            q["satisfied"]["tradeability"] is True
            and q["combined"] == "READY")

        # ---- Q3: writer-required consumer, stale writer -> BLOCKED -
        c2 = fx.connect_test()
        c2.execute(f"UPDATE {S}.finver_observation "
                   "SET seen_at='2020-01-01'")
        c2.commit(); c2.close()
        q = evaluate_requirements(conn, {
            "financial": {"require_writer": True,
                          "staleness_hours": 24,
                          "expected_endpoints": [EP],
                          "min_state": "writer"}})
        R["Q3_stale_writer_blocks"] = (
            q["satisfied"]["financial"] is False
            and q["combined"] == "BLOCKED")

        # ---- Q4: allow_degraded explicitly declared ----
        q = evaluate_requirements(conn, {
            "financial": {"require_writer": True,
                          "staleness_hours": 24,
                          "min_state": "schema",
                          "allow_degraded": True}})
        R["Q4_declared_degraded_ok"] = (
            q["satisfied"]["financial"] is True)

    res = {"instance": "stock_m2_test (independent PG16)",
           "cases": R,
           "passed": sum(1 for v in R.values() if v),
           "total": len(R), "all_pass": all(R.values())}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
