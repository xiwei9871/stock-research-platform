#!/usr/bin/env python3
"""DATA-R3-P2 financial PIT audit — READ-ONLY.

Produces the data artifacts under docs/research_upgrade/p2/:
  STATEMENT_COVERAGE_MATRIX.csv, PUBLICATION_DATE_AUDIT.csv,
  RESTATEMENT_VERSION_AUDIT samples, Q2_14_GAP_RECONCILIATION.csv,
  DELISTED_COMPANY_RETENTION_AUDIT data, FINANCIAL_PIT_EDGE_CASES.json,
  audit_summary.json.
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
from stock_research.db import connect, fetch_all  # noqa: E402
from stock_research.config import SETTINGS  # noqa: E402
from stock_research.financial_pit import financial_pit_at, ANN_SENTINEL  # noqa: E402

OUT = Path("docs/research_upgrade/p2")
RECON = Path("outputs/research/data01r1_finance_q2_20261020/"
            "akshare_q2_reconciliation.json")
TABLES = {"income": "income_statement",
          "balance": "balance_sheet",
          "cash_flow": "cash_flow"}


def cov_matrix(conn):
    """asset x report_period x statement coverage over the 5,213-universe."""
    sql = """
    WITH per AS (
      SELECT report_period,
        count(DISTINCT asset_id) FILTER (WHERE st='income') AS inc_n,
        count(DISTINCT asset_id) FILTER (WHERE st='balance') AS bal_n,
        count(DISTINCT asset_id) FILTER (WHERE st='cash')   AS cf_n
      FROM (
        SELECT 'income' st, asset_id, report_period FROM finance.income_statement
        UNION ALL SELECT 'balance', asset_id, report_period FROM finance.balance_sheet
        UNION ALL SELECT 'cash', asset_id, report_period FROM finance.cash_flow
      ) u GROUP BY report_period
    )
    SELECT report_period::text, inc_n, bal_n, cf_n,
      least(inc_n,bal_n,cf_n) AS max_possible_all3
    FROM per ORDER BY report_period"""
    rows = fetch_all(conn, sql)
    # all-three count needs a join; do it per period for recent+annual only
    all3 = {}
    for r in fetch_all(conn, """
        SELECT report_period::text AS p, count(*) n FROM (
          SELECT i.report_period, i.asset_id
          FROM finance.income_statement i
          JOIN finance.balance_sheet b
            ON b.asset_id=i.asset_id AND b.report_period=i.report_period
          JOIN finance.cash_flow c
            ON c.asset_id=i.asset_id AND c.report_period=i.report_period
          GROUP BY i.report_period, i.asset_id) x
        GROUP BY report_period"""):
        all3[r["p"]] = r["n"]
    universe = fetch_all(conn,
                         "SELECT count(DISTINCT asset_id) n FROM "
                         "finance.income_statement")[0]["n"]
    for r in rows:
        r["all_three"] = all3.get(r["report_period"], 0)
        r["universe"] = universe
    return rows


def pubdate_audit(conn):
    """announcement_date anomalies per table."""
    out = []
    for st, t in TABLES.items():
        s = fetch_all(conn, f"""
          SELECT count(*) rows_total,
            count(*) FILTER (WHERE announcement_date IS NULL) null_ann,
            count(*) FILTER (WHERE announcement_date='{ANN_SENTINEL}') sentinel,
            count(*) FILTER (WHERE announcement_date < report_period) ann_before_period,
            count(*) FILTER (WHERE announcement_date = report_period) ann_eq_period,
            count(*) FILTER (WHERE announcement_date >
                               report_period + interval '180 days') ann_lag180plus,
            min(announcement_date) FILTER (WHERE announcement_date>'1900-01-01')
              ::text AS min_real_ann,
            max(announcement_date)::text AS max_ann,
            count(DISTINCT asset_id) FILTER (
              WHERE announcement_date='{ANN_SENTINEL}') sentinel_assets
          FROM finance.{t}""")[0]
        s["statement"] = st
        out.append(s)
    return out


def restatement_audit(conn):
    """Multi-version keys + same-key cross-source value conflicts."""
    multi = {}
    for st, t in TABLES.items():
        multi[st] = fetch_all(conn, f"""
          SELECT asset_id, report_period::text AS report_period, report_type,
                 source, count(DISTINCT announcement_date) ann_versions,
                 min(announcement_date)::text first_ann,
                 max(announcement_date)::text last_ann
          FROM finance.{t}
          GROUP BY 1,2,3,4 HAVING count(DISTINCT announcement_date)>1
          ORDER BY ann_versions DESC LIMIT 50""")
    # cross-source value conflict: same (asset,period,type), different sources,
    # different revenue/total_assets/net_cash → flag. income has akshare+baostock.
    conflicts = fetch_all(conn, """
      SELECT i.asset_id, i.report_period::text AS report_period,
        count(DISTINCT i.source) nsrc,
        count(DISTINCT COALESCE(i.revenue::text,'NULL')) n_revenue,
        count(DISTINCT COALESCE(i.np_parent::text,'NULL')) n_np
      FROM finance.income_statement i
      GROUP BY 1,2
      HAVING count(DISTINCT i.source)>1
         AND count(DISTINCT COALESCE(i.revenue::text,'NULL'))>1
      ORDER BY report_period DESC LIMIT 200""")
    return multi, conflicts


def delisted_retention(conn):
    """Do delisted assets retain financial history?"""
    return fetch_all(conn, """
      SELECT a.delist_date::text AS dd, count(DISTINCT a.asset_id) assets,
        count(DISTINCT i.asset_id) with_income,
        count(DISTINCT b.asset_id) with_balance,
        count(DISTINCT c.asset_id) with_cf
      FROM core.asset_master a
      LEFT JOIN finance.income_statement i ON i.asset_id=a.asset_id
      LEFT JOIN finance.balance_sheet b ON b.asset_id=a.asset_id
      LEFT JOIN finance.cash_flow c ON c.asset_id=a.asset_id
      WHERE a.delist_date IS NOT NULL
      GROUP BY 1 ORDER BY 1 DESC NULLS LAST LIMIT 40"""), fetch_all(conn, """
      SELECT count(DISTINCT asset_id) AS delisted_total FROM core.asset_master
      WHERE delist_date IS NOT NULL""")


def q2_gap(conn):
    """Reconcile the 14 missing 2026-06-30 balance+cashflow assets."""
    recon = json.loads(RECON.read_text())
    missing = []
    for grp, g in recon["missing_breakdown"].items():
        for a in g["assets"]:
            missing.append({"asset_id": a, "recon_class": grp,
                            "reason": g.get("reason", "")})
    out = []
    for m in missing:
        a = m["asset_id"]
        info = fetch_all(conn, """
          SELECT asset_id, list_date::text, delist_date::text, exchange
          FROM core.asset_master WHERE asset_id=%s""", [a])
        info = info[0] if info else {}
        periods = {}
        for st, t in TABLES.items():
            r = fetch_all(conn, f"""
              SELECT max(report_period)::text mp, count(*) n
              FROM finance.{t} WHERE asset_id=%s""", [a])[0]
            periods[f"latest_{st}"] = r["mp"]
            periods[f"n_{st}"] = r["n"]
        out.append({**m, **info, **periods})
    return out, recon


def edge_cases(conn):
    """Real-DB adversarial samples for FINANCIAL_PIT_EDGE_CASES.json."""
    cases = {}
    # 1. period ended but announcement later than a chosen as_of
    r = financial_pit_at(conn, "CN:SH:600000", "2024-04-01", "income",
                         report_period="2023-12-31")
    cases["period_ended_ann_pending"] = r.__dict__ if r.pit_status else r
    r2 = financial_pit_at(conn, "CN:SH:600000", "2024-06-01", "income",
                          report_period="2023-12-31")
    cases["after_announcement"] = r2.__dict__
    # 2. same-day conservatism: as_of == announcement_date must NOT be public
    rows = fetch_all(conn, """
      SELECT asset_id, report_period::text rp,
             announcement_date::text ann, source
      FROM finance.income_statement
      WHERE announcement_date > '2024-01-01' LIMIT 1""")
    if rows:
        rr = rows[0]
        same = financial_pit_at(conn, rr["asset_id"], rr["ann"], "income",
                                report_period=rr["rp"])
        nxt = financial_pit_at(conn, rr["asset_id"],
                               str(__import__("datetime").date.fromisoformat(
                                   rr["ann"]) +
                                   __import__("datetime").timedelta(days=1)),
                               "income", report_period=rr["rp"])
        cases["same_day_as_ann_blocked"] = same.__dict__
        cases["day_after_ann_visible"] = nxt.__dict__
    # 3. sentinel rows fail closed
    sent = fetch_all(conn, """
      SELECT asset_id, report_period::text rp FROM finance.balance_sheet
      WHERE announcement_date='1900-01-01' LIMIT 1""")
    if sent:
        s = financial_pit_at(conn, sent[0]["asset_id"], "2026-01-01",
                             "balance", report_period=sent[0]["rp"])
        cases["sentinel_ann_fail_closed"] = s.__dict__
    # 4. delisted asset retains queryable history
    d = fetch_all(conn, """
      SELECT a.asset_id, max(i.report_period)::text rp
      FROM core.asset_master a JOIN finance.income_statement i
        ON i.asset_id=a.asset_id
      WHERE a.delist_date IS NOT NULL
      GROUP BY 1 HAVING max(i.report_period)>'2020-01-01' LIMIT 1""")
    if d:
        hist = financial_pit_at(conn, d[0]["asset_id"], "2027-01-01",
                                "income", report_period=d[0]["rp"])
        cases["delisted_history_queryable"] = {**hist.__dict__,
                                               "asset": d[0]["asset_id"]}
    # 5. initial vs latest policy on multi-version key (if any)
    mv = fetch_all(conn, """
      SELECT asset_id, report_period::text rp FROM finance.balance_sheet
      GROUP BY 1,2,report_type,source
      HAVING count(DISTINCT announcement_date)>1 LIMIT 1""")
    if mv:
        latest = financial_pit_at(conn, mv[0]["asset_id"], "2027-01-01",
                                  "balance", report_period=mv[0]["rp"],
                                  version_policy="latest_public")
        init = financial_pit_at(conn, mv[0]["asset_id"], "2027-01-01",
                                "balance", report_period=mv[0]["rp"],
                                version_policy="initial_public")
        cases["version_policy_latest"] = latest.__dict__
        cases["version_policy_initial"] = init.__dict__
    # 6. determinism: repeat same query
    a = financial_pit_at(conn, "CN:SH:600000", "2024-06-01", "income")
    b = financial_pit_at(conn, "CN:SH:600000", "2024-06-01", "income")
    cases["deterministic_repeat"] = {"equal": a.__dict__ == b.__dict__}
    return cases


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with connect(SETTINGS.research_service) as conn:
        cov = cov_matrix(conn)
        pub = pubdate_audit(conn)
        multi, conflicts = restatement_audit(conn)
        delist_rows, delist_total = delisted_retention(conn)
        q2, recon = q2_gap(conn)
        edges = edge_cases(conn)

    with open(OUT / "STATEMENT_COVERAGE_MATRIX.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(cov[0].keys()))
        w.writeheader()
        w.writerows(cov)
    with open(OUT / "PUBLICATION_DATE_AUDIT.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(pub[0].keys()))
        w.writeheader()
        w.writerows(pub)
    with open(OUT / "Q2_14_GAP_RECONCILIATION.csv", "w", newline="") as f:
        keys = sorted({k for r in q2 for k in r})
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(q2)
    with open(OUT / "FINANCIAL_PIT_EDGE_CASES.json", "w") as f:
        json.dump(edges, f, ensure_ascii=False, indent=2, default=str)
    summary = {
        "coverage_periods": len(cov),
        "pubdate_audit": pub,
        "multi_version_keys": {k: len(v) for k, v in multi.items()},
        "multi_version_samples": {k: v[:10] for k, v in multi.items()},
        "cross_source_conflicts_n": len(conflicts),
        "cross_source_conflict_samples": conflicts[:30],
        "delisted_total": delist_total[0]["delisted_total"],
        "delisted_retention_by_year": delist_rows,
        "q2_gap": q2,
        "q2_recon_coverage": recon.get("coverage"),
        "q2_recon_generated": recon.get("generated"),
        "edge_case_statuses": {
            k: (v.get("pit_status") if isinstance(v, dict) else v)
            for k, v in edges.items()},
    }
    with open(OUT / "audit_summary.json", "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
    print(json.dumps({k: summary[k] for k in
                      ["coverage_periods", "multi_version_keys",
                       "cross_source_conflicts_n", "delisted_total",
                       "edge_case_statuses", "q2_recon_coverage"]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
