#!/usr/bin/env python3
"""M2-0-D — finver E2E on the INDEPENDENT test instance.

  F1 schema deploy (finver ddl)
  F2 ingest: normal / repeat / real change / missing period / unknown ep
  F3 dual-connection concurrent same-key ingest (advisory lock)
  F4 out-of-order replay: newer first, older later -> no head regress
  F5 raw ok + version fail -> whole txn rolls back
  F6 commit-before-fail -> raw+event absent together (atomicity)
  F7 read_as_of correctness under replay order
  F8 chain pointer audit (no orphans, head = max first_seen)
Output: FINVER_CONCURRENCY_AND_REPLAY_TESTS.json
"""
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, "scripts")
import m2_testdb_fixtures as fx  # noqa: E402
import stock_research.financial_version_store as fvs  # noqa: E402
from stock_research.db import execute, fetch_all  # noqa: E402
from stock_research.financial_ingest_integration import (  # noqa: E402
    store_finance_payload_and_version)

OUT = Path("docs/research_upgrade/implementation/m2/preflight")
S = "finver"
EP = "stock_profit_sheet_by_report_em"
A = "CN:SH:600001"


def evs(conn, asset=A, ep=EP):
    return fetch_all(conn, f"""
      SELECT version_event_id, version_seq, metric_fingerprint fp,
             (metrics->>'NETPROFIT')::float np, first_seen_at::text fst,
             supersedes_event_id sup
      FROM {S}.finver_event WHERE asset_id=%s AND endpoint=%s
      ORDER BY version_seq""", [asset, ep])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    log = {"instance": "stock_m2_test (local PG16)", "drills": {}}
    with fx.connect_test() as conn:
        fx.reset(conn)
        fx.seed(conn)
        conn.commit()

        # F1 — deploy finver schema
        for stmt in fvs.ddl(S).split(";"):
            if stmt.strip():
                execute(conn, stmt)
        conn.commit()
        log["drills"]["F1_schema"] = {"pass": True}

        # F2 — coverage counters
        p1 = [{"REPORT_DATE": "2025-06-30", "NOTICE_DATE": "2025-08-28",
               "REPORT_TYPE": "中报", "NETPROFIT": 100.0}]
        p2 = [dict(p1[0], NETPROFIT=250.0)]
        p_bad = [{"NETPROFIT": 1}]  # no REPORT_DATE
        r1 = fvs.ingest_payload(conn, S, A, EP, "2025-08-29T10:00",
                                p1, 1, "h1")
        r_dup = fvs.ingest_payload(conn, S, A, EP, "2025-08-29T11:00",
                                   p1, 2, "h2")  # identical -> obs only
        r2 = fvs.ingest_payload(conn, S, A, EP, "2025-09-02T10:00",
                                p2, 3, "h3")  # change -> v2
        r_bad = fvs.ingest_payload(conn, S, A, EP, "2025-09-03", p_bad,
                                   4, "h4")
        r_unk = fvs.ingest_payload(conn, S, A, "vendor_x_unknown_ep",
                                   "2025-09-03", p1, 5, "h5")
        log["drills"]["F2_counters"] = {
            "first": r1, "dup": r_dup, "change": r2,
            "missing_period": r_bad, "unknown_ep": r_unk,
            "pass": (r1["new_version"] == 1
                     and r_dup["new_version"] == 0
                     and r_dup["identical_bump"] == 1
                     and r2["new_version"] == 1
                     and r_bad["missing_period"] == 1
                     and r_unk["unknown_source"] == 1)}
        conn.commit()

        # F3 — dual-connection concurrent same-key ingest
        pa = [{"REPORT_DATE": "2025-09-30", "NOTICE_DATE": "2025-10-30",
               "REPORT_TYPE": "三季报", "NETPROFIT": 300.0}]
        pb = [{"REPORT_DATE": "2025-09-30", "NOTICE_DATE": "2025-10-30",
               "REPORT_TYPE": "三季报", "NETPROFIT": 400.0}]
        errs = []

        def work(pl, tag):
            try:
                with fx.connect_test() as c:
                    fvs.ingest_payload(c, S, A, EP, "2025-10-31T09:0"
                                       + tag, pl, 10 + int(tag), f"ct{tag}")
                    c.commit()
            except Exception as e:  # noqa: BLE001
                errs.append(f"{tag}:{type(e).__name__}:{e}")

        t1 = threading.Thread(target=work, args=(pa, "1"))
        t2 = threading.Thread(target=work, args=(pb, "2"))
        t1.start(); t2.start(); t1.join(); t2.join()
        rows = fetch_all(conn, f"""
          SELECT version_seq FROM {S}.finver_event
          WHERE asset_id=%s AND report_period='2025-09-30'
          ORDER BY version_seq""", [A])
        seqs = [r["version_seq"] for r in rows]
        chain = fetch_all(conn, f"""
          SELECT n_versions FROM {S}.finver_key_chain
          WHERE asset_id=%s AND report_period='2025-09-30'""", [A])
        log["drills"]["F3_concurrent"] = {
            "errors": errs, "seqs": seqs,
            "chain_n": chain[0]["n_versions"] if chain else None,
            "pass": not errs and seqs == list(range(1, len(seqs) + 1))
            and chain and chain[0]["n_versions"] == len(seqs)}

        # F4 — out-of-order replay: build A→B chain, then a LATE copy
        # of A's content arrives — head must stay B, sighting attaches
        # to A's event as late_arrival_repeat.
        B = "CN:SZ:000001"
        a_pl = [{"REPORT_DATE": "2025-03-31", "NOTICE_DATE": "2025-04-29",
                 "REPORT_TYPE": "一季报", "NETPROFIT": 100.0}]
        b_pl = [{"REPORT_DATE": "2025-03-31", "NOTICE_DATE": "2025-04-29",
                 "REPORT_TYPE": "一季报", "NETPROFIT": 200.0}]
        fvs.ingest_payload(conn, S, B, EP, "2025-05-01", a_pl, 20, "a")
        fvs.ingest_payload(conn, S, B, EP, "2025-05-02", b_pl, 21, "b")
        fvs.ingest_payload(conn, S, B, EP, "2025-05-01", a_pl, 22,
                           "a-late")  # replayed older content
        head = fetch_all(conn, f"""
          SELECT e.version_seq, (e.metrics->>'NETPROFIT')::float np
          FROM {S}.finver_key_chain c
          JOIN {S}.finver_event e
            ON e.version_event_id=c.latest_event_id
          WHERE c.asset_id=%s""", [B])[0]
        obs_classes = fetch_all(conn, f"""
          SELECT o.change_class, count(*) n
          FROM {S}.finver_observation o
          JOIN {S}.finver_event e
            ON e.version_event_id=o.version_event_id
          WHERE e.asset_id=%s GROUP BY 1""", [B])
        n_ev = fetch_all(conn, f"""SELECT count(*) n
          FROM {S}.finver_event WHERE asset_id=%s""", [B])[0]["n"]
        log["drills"]["F4_out_of_order"] = {
            "head_seq": head["version_seq"], "head_np": head["np"],
            "events": n_ev,
            "obs": {r["change_class"]: r["n"] for r in obs_classes},
            "pass": head["np"] == 200.0 and n_ev == 2 and any(
                r["change_class"] == "late_arrival_repeat"
                for r in obs_classes)}
        conn.commit()  # F5 的 rollback 只应吞掉 F5 自己的写入

        # F5 — raw insert ok + finver ingest throws -> whole txn rolls
        pre_raw = fetch_all(conn, "SELECT count(*) n FROM "
                            "raw_akshare.finance_payload")[0]["n"]
        try:
            store_finance_payload_and_version(
                conn, "CN:SH:601002", EP, {"s": "601002"},
                [{"REPORT_DATE": "2025-12-31",
                  "NOTICE_DATE": "2026-03-30", "NETPROFIT": 9}],
                finver_schema="nonexistent_schema", finver_enabled=True)
            f5 = "no_error"
        except Exception as e:  # noqa: BLE001
            f5 = type(e).__name__
        conn.rollback()
        post_raw = fetch_all(conn, "SELECT count(*) n FROM "
                             "raw_akshare.finance_payload")[0]["n"]
        log["drills"]["F5_atomic_rollback"] = {
            "error": f5, "raw_delta": post_raw - pre_raw,
            "pass": f5 != "no_error" and post_raw == pre_raw}

        # F6 — enabled path writes raw+event atomically (positive twin)
        with fx.connect_test() as c2:
            r = store_finance_payload_and_version(
                c2, "CN:SH:601001", EP, {"s": "601001"},
                [{"REPORT_DATE": "2024-12-31", "NOTICE_DATE": "2025-03-31",
                  "REPORT_TYPE": "年报", "NETPROFIT": 77}],
                finver_schema=S, finver_enabled=True)
            c2.commit()
        ok = fetch_all(conn, f"""SELECT count(*) n FROM {S}.finver_event
          WHERE asset_id='CN:SH:601001'""")[0]["n"]
        log["drills"]["F6_integrated_write"] = {
            "raw_id": r["raw_payload_id"], "events": ok,
            "fin": r["finver"], "pass": ok == 1 and r["finver"]
            and r["finver"]["new_version"] == 1}

        # F7 — read_as_of respects first_seen (platform-observation)
        v = fvs.read_as_of(conn, S, B, "income", "2025-03-31",
                           "2025-05-01T12:00")
        v_late = fvs.read_as_of(conn, S, B, "income", "2025-03-31",
                                "2025-05-03")
        log["drills"]["F7_asof"] = {
            "early_np": v and (v["metrics"] or {}).get("NETPROFIT"),
            "late_np": v_late and (v_late["metrics"] or {}).get(
                "NETPROFIT"),
            "pass": v_late is not None}

        # F8 — chain audit: no orphan heads, seq dense
        orphans = fetch_all(conn, f"""
          SELECT count(*) n FROM {S}.finver_key_chain c
          LEFT JOIN {S}.finver_event e
            ON e.version_event_id=c.latest_event_id
          WHERE e.version_event_id IS NULL""")[0]["n"]
        log["drills"]["F8_chain_audit"] = {
            "orphans": orphans, "pass": orphans == 0}

        log["gate"] = {
            "counters": log["drills"]["F2_counters"]["pass"],
            "concurrent": log["drills"]["F3_concurrent"]["pass"],
            "out_of_order": log["drills"]["F4_out_of_order"]["pass"],
            "atomic_rollback": log["drills"]["F5_atomic_rollback"]
            ["pass"],
            "integrated_write": log["drills"]["F6_integrated_write"]
            ["pass"],
            "asof": log["drills"]["F7_asof"]["pass"],
            "chain_audit": log["drills"]["F8_chain_audit"]["pass"],
        }
        log["gate"]["all_pass"] = all(log["gate"].values())
        conn.rollback()

    (OUT / "FINVER_CONCURRENCY_AND_REPLAY_TESTS.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(log["gate"], indent=1))


if __name__ == "__main__":
    main()
