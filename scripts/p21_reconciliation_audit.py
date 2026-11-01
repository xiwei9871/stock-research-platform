#!/usr/bin/env python3
"""P2.1-A — exact cross-source reconciliation census + publication anomaly
stratification + Q2 evidence levels. READ-ONLY. No LIMIT-200 shortcuts.

Outputs under docs/research_upgrade/p21/:
  cross_source_census.json, PUBLICATION_ANOMALY_SAMPLES.csv,
  q2_evidence_levels.json
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "src")
from stock_research.db import connect, fetch_all  # noqa: E402
from stock_research.config import SETTINGS  # noqa: E402

OUT = Path("docs/research_upgrade/p21")
METRICS = ["revenue", "operating_profit", "total_profit", "net_profit",
           "np_parent", "np_parent_deducted", "eps_basic"]
RANK = {"conflict": 5, "unit_scale": 4, "null_conflict": 3,
        "precision": 2, "equal": 1}


def classify(a, b):
    if a is None and b is None:
        return "equal"
    if a is None or b is None:
        return "null_conflict"
    fa, fb = float(a), float(b)
    if fa == fb:
        return "equal"
    m = max(abs(fa), abs(fb))
    if m == 0:
        return "conflict"
    if abs(fa - fb) <= m * 1e-4:
        return "precision"
    if fb != 0:
        r = abs(fa / fb)
        for k in range(1, 9):
            if abs(r - 10.0 ** k) / 10.0 ** k <= 0.02 or \
               abs(r - 10.0 ** -k) / 10.0 ** -k <= 0.02:
                return "unit_scale"
    return "conflict"


def census(conn):
    sel = ", ".join(f"a.{m} a_{m}, b.{m} b_{m}" for m in METRICS)
    rows = fetch_all(conn, f"""
      SELECT a.asset_id, a.report_period::text rp, a.report_type,
             a.announcement_date::text a_ann, b.announcement_date::text b_ann,
             {sel}
      FROM finance.income_statement a
      JOIN finance.income_statement b
        ON b.asset_id=a.asset_id AND b.report_period=a.report_period
       AND b.report_type=a.report_type
      WHERE a.source='akshare_em_profit_sheet' AND b.source='baostock'""")
    key_cls = Counter()
    metric_cls = {m: Counter() for m in METRICS}
    worst_metric = Counter()
    samples = defaultdict(list)
    for r in rows:
        cls, worst, wm = {}, "equal", None
        for m in METRICS:
            c = classify(r[f"a_{m}"], r[f"b_{m}"])
            cls[m] = c
            metric_cls[m][c] += 1
            if RANK[c] > RANK[worst]:
                worst, wm = c, m
        key_cls[worst] += 1
        if worst != "equal":
            worst_metric[wm] += 1
        if len(samples[worst]) < 8:
            samples[worst].append({
                "asset_id": r["asset_id"], "rp": r["rp"],
                "a": r[f"a_{wm}"], "b": r[f"b_{wm}"],
                "metric": wm, "classes": cls})
    return {"dual_source_keys": len(rows),
            "per_key_worst": dict(key_cls),
            "per_metric": {m: dict(c) for m, c in metric_cls.items()},
            "worst_metric_dist": dict(worst_metric),
            "samples": dict(samples)}


def anomaly_strata(conn):
    """Stratified samples for ann > period+180d, by source x period-decade."""
    strata = fetch_all(conn, """
      SELECT source,
        (extract(year FROM report_period)::int/10)*10 AS decade,
        report_type, count(*) n,
        count(DISTINCT asset_id) assets,
        min(announcement_date)::text min_ann,
        max(announcement_date)::text max_ann
      FROM finance.income_statement
      WHERE announcement_date > report_period + interval '180 days'
      GROUP BY 1,2,3 ORDER BY n DESC""")
    samples = fetch_all(conn, """
      SELECT asset_id, report_period::text rp, report_type rt, source,
             announcement_date::text ann, updated_at::text upd,
             revenue::text rev
      FROM finance.income_statement
      WHERE announcement_date > report_period + interval '180 days'
      ORDER BY report_period, asset_id""")
    # every 4000th → ~20 rows across the whole range
    pick = samples[::max(1, len(samples) // 20)]
    # do the same periods exist with earlier ann under baostock?
    check = []
    for s in pick[:12]:
        alt = fetch_all(conn, """
          SELECT source, announcement_date::text ann
          FROM finance.income_statement
          WHERE asset_id=%s AND report_period=%s AND report_type=%s
          ORDER BY announcement_date""",
                        [s["asset_id"], s["rp"], s["rt"]])
        check.append({**s, "all_versions": alt})
    return strata, check


def q2_levels(conn):
    recon_path = Path(
        "outputs/research/data01r1_finance_q2_20261020/"
        "akshare_q2_reconciliation.json")
    if not recon_path.exists():
        recon_path = Path(
            "/Users/xiwei/stock_research/" + str(recon_path))
    recon = json.loads(recon_path.read_text())
    out = []
    for grp, g in recon["missing_breakdown"].items():
        for a in g["assets"]:
            m = fetch_all(conn, """
              SELECT delist_date::text dd, list_date::text ld
              FROM core.asset_master WHERE asset_id=%s""", [a])
            m = m[0] if m else {}
            lvl = ("L3_external_announcement" if grp.startswith("truly")
                   else "L2_db_delist_plus_source_absent")
            out.append({"asset_id": a, "recon_class": grp,
                        "evidence_level": lvl,
                        "delist_date": m.get("dd"),
                        "independently_verified_disclosure":
                            grp.startswith("truly"),
                        "note": g.get("reason", "")[:200]})
    return out, recon.get("coverage")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with connect(SETTINGS.research_service) as conn:
        c = census(conn)
        strata, picks = anomaly_strata(conn)
        q2, q2cov = q2_levels(conn)
    (OUT / "cross_source_census.json").write_text(
        json.dumps(c, ensure_ascii=False, indent=1, default=str))
    (OUT / "q2_evidence_levels.json").write_text(
        json.dumps({"coverage_baseline": q2cov, "assets": q2},
                   ensure_ascii=False, indent=1, default=str))
    with open(OUT / "PUBLICATION_ANOMALY_SAMPLES.csv", "w",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(picks[0].keys()))
        w.writeheader()
        for p in picks:
            p = dict(p)
            p["all_versions"] = json.dumps(p["all_versions"],
                                           ensure_ascii=False)
            w.writerow(p)
    print(json.dumps({"dual_keys": c["dual_source_keys"],
                      "per_key_worst": c["per_key_worst"],
                      "strata_top": strata[:6],
                      "q2": {q["recon_class"]: sum(
                          1 for x in q2
                          if x["recon_class"] == q["recon_class"])
                          for q in q2}},
                     ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
