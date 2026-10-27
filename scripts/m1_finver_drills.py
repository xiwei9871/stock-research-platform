#!/usr/bin/env python3
"""M1-C isolated drills — financial version event store.

Creates m1_shadow.finver_* (isolated), then:
  D1 replay the 34 real metric-change keys from raw_akshare payloads
     (in fetched_at order) -> expect version chains with supersedes
  D2 duplicate re-ingest -> identical_bump, no new version
  D3 synthetic metric change -> new version
  D4 metadata-only change -> bump only
  D5 read_as_of between fetches -> v1, after -> v2
  D6 missing-initial evidence -> announcement_evidence=unknown stays
     UNKNOWN (no date invention)
Isolated schema only. No production writes to finance tables.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
from stock_research.db import connect, execute, fetch_all  # noqa: E402
from stock_research.config import SETTINGS  # noqa: E402
import stock_research.financial_version_store as fvs  # noqa: E402

OUT = Path("docs/research_upgrade/implementation/m1")
S = "m1_shadow"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    log = {"schema": S, "drills": {}}
    with connect(SETTINGS.research_service) as conn:
        execute(conn, f"DROP TABLE IF EXISTS {S}.finver_key_chain")
        execute(conn, f"DROP TABLE IF EXISTS {S}.finver_event")
        for stmt in fvs.ddl(S).split(";"):
            if stmt.strip():
                execute(conn, stmt)

        # D1 — replay real changed keys (cash_flow endpoint)
        changed_assets = [r["asset_id"] for r in fetch_all(conn, """
            SELECT asset_id FROM raw_akshare.finance_payload
            WHERE source_endpoint='stock_cash_flow_sheet_by_report_em'
            GROUP BY asset_id HAVING count(DISTINCT payload_hash)>1
            ORDER BY asset_id LIMIT 6""")]
        replay = {}
        for a in changed_assets:
            snaps = fetch_all(conn, """
                SELECT id, payload::text pl, payload_hash ph,
                       fetched_at::text ft
                FROM raw_akshare.finance_payload
                WHERE asset_id=%s
                  AND source_endpoint='stock_cash_flow_sheet_by_report_em'
                ORDER BY fetched_at""", [a])
            counts = []
            for s in snaps:
                c = fvs.ingest_payload(conn, S, a,
                                       "stock_cash_flow_sheet_by_report_em",
                                       s["ft"], s["pl"], s["id"], s["ph"])
                counts.append(c["new_version"])
            chains = fetch_all(conn, f"""
                SELECT report_period::text rp, n_versions
                FROM {S}.finver_key_chain WHERE asset_id=%s""", [a])
            replay[a] = {"snapshots": len(snaps), "new_versions": counts,
                         "chains": {r["rp"]: r["n_versions"]
                                    for r in chains}}
        log["drills"]["D1_replay_real"] = replay
        multi = sum(1 for v in replay.values()
                    for n in v["chains"].values() if n > 1)
        log["drills"]["D1_multi_version_chains"] = multi

        # D2 — idempotent re-ingest of the last snapshot
        a0 = changed_assets[0]
        s0 = fetch_all(conn, """
            SELECT id, payload::text pl, payload_hash ph, fetched_at::text ft
            FROM raw_akshare.finance_payload
            WHERE asset_id=%s
              AND source_endpoint='stock_cash_flow_sheet_by_report_em'
            ORDER BY fetched_at DESC LIMIT 1""", [a0])[0]
        n0 = fetch_all(conn, f"SELECT count(*) n FROM {S}.finver_event"
                       )[0]["n"]
        c = fvs.ingest_payload(conn, S, a0,
                               "stock_cash_flow_sheet_by_report_em",
                               s0["ft"], s0["pl"], s0["id"], s0["ph"])
        n1 = fetch_all(conn, f"SELECT count(*) n FROM {S}.finver_event"
                       )[0]["n"]
        log["drills"]["D2_idempotent"] = {
            "ingest_counts": c, "events_before": n0, "events_after": n1,
            "pass": n1 == n0}

        # D3 — synthetic metric change appends a version
        syn = [{"REPORT_DATE": "2025-06-30", "NOTICE_DATE": "2025-08-30",
                "REPORT_TYPE": "中报", "NETPROFIT": 100.0,
                "OPERATE_INCOME": 500.0}]
        fvs.ingest_payload(conn, S, "CN:TEST:000001",
                           "stock_profit_sheet_by_report_em",
                           "2025-09-01T00:00:00", syn, None, "h1")
        syn2 = [dict(syn[0], NETPROFIT=250.0)]
        c = fvs.ingest_payload(conn, S, "CN:TEST:000001",
                               "stock_profit_sheet_by_report_em",
                               "2025-10-01T00:00:00", syn2, None, "h2")
        ch = fetch_all(conn, f"""
          SELECT n_versions FROM {S}.finver_key_chain
          WHERE asset_id='CN:TEST:000001'""")[0]
        log["drills"]["D3_metric_change"] = {
            "ingest": c, "n_versions": ch["n_versions"],
            "pass": c["new_version"] == 1 and ch["n_versions"] == 2}

        # D4 — metadata-only change bumps, no new version
        syn3 = [dict(syn2[0], UPDATE_DATE="2025-10-15")]
        c = fvs.ingest_payload(conn, S, "CN:TEST:000001",
                               "stock_profit_sheet_by_report_em",
                               "2025-10-15T00:00:00", syn3, None, "h3")
        ch = fetch_all(conn, f"""
          SELECT n_versions FROM {S}.finver_key_chain
          WHERE asset_id='CN:TEST:000001'""")[0]
        log["drills"]["D4_metadata_only"] = {
            "ingest": c, "n_versions": ch["n_versions"],
            "pass": ch["n_versions"] == 2}

        # D5 — read_as_of picks the version observed at the time
        v1 = fvs.read_as_of(conn, S, "CN:TEST:000001", "income",
                            "2025-06-30", "2025-09-15")
        v2 = fvs.read_as_of(conn, S, "CN:TEST:000001", "income",
                            "2025-06-30", "2025-11-01")
        log["drills"]["D5_asof_read"] = {
            "v1_seq": v1 and v1["version_seq"],
            "v2_seq": v2 and v2["version_seq"],
            "pass": (v1 and v1["version_seq"] == 1
                     and v2 and v2["version_seq"] == 2)}

        # D6 — unknown ann evidence stays UNKNOWN (no invention)
        syn_noann = [{"REPORT_DATE": "2024-12-31", "NETPROFIT": 1}]
        fvs.ingest_payload(conn, S, "CN:TEST:000002",
                           "stock_profit_sheet_by_report_em",
                           "2025-05-01T00:00:00", syn_noann, None, "hx")
        ev = fetch_all(conn, f"""
          SELECT announcement_evidence, announcement_date
          FROM {S}.finver_event WHERE asset_id='CN:TEST:000002'""")[0]
        log["drills"]["D6_unknown_ann"] = {
            **ev, "pass": ev["announcement_evidence"] == "unknown"
            and ev["announcement_date"] is None}

        log["gate"] = {
            "real_chains_reproduced":
                log["drills"]["D1_multi_version_chains"] > 0,
            "idempotent": log["drills"]["D2_idempotent"]["pass"],
            "metric_change_appends": log["drills"]["D3_metric_change"]
                ["pass"],
            "metadata_no_version": log["drills"]["D4_metadata_only"]
                ["pass"],
            "asof_read_correct": log["drills"]["D5_asof_read"]["pass"],
            "unknown_not_invented": log["drills"]["D6_unknown_ann"]
                ["pass"],
        }
        log["gate"]["all_pass"] = all(log["gate"].values())
        counts = fetch_all(conn, f"""
          SELECT count(*) ev, count(DISTINCT (asset_id,statement_type,
            endpoint,report_period,report_type)) k
          FROM {S}.finver_event""")[0]
        log["totals"] = counts
        conn.commit()  # keep isolated evidence for inspection

    (OUT / "FINANCIAL_VERSION_TESTS.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({"gate": log["gate"], "totals": log["totals"],
                      "D1_multi": log["drills"]
                      ["D1_multi_version_chains"]}, indent=1))


if __name__ == "__main__":
    main()
