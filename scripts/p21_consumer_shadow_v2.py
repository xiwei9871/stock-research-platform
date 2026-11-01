#!/usr/bin/env python3
"""P2.1-Final-B — consumer shadow with correct two-level PIT semantics.

Level 1: latest report_period publicly available at as_of.
Level 2: within the period, version by (max ann per source) then
         source preference.

Legacy:    announcement_date <= trade_date
Corrected: announcement_date <  trade_date  (D+1)

Change classes: period_change / version_change / source_change /
lost_availability / gained_none->some. Sentinel-only assets are
evidence_insufficient. Real-sample spot checks call the actual consumer
queries (point_in_time_finance-style ORDER BY ann DESC) to confirm the
legacy selector predicts the real read path.
"""
import bisect
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "src")
from stock_research.db import connect, fetch_all  # noqa: E402
from stock_research.config import SETTINGS  # noqa: E402

OUT = Path("docs/research_upgrade/p21/final")
SENT = "1900-01-01"
TABLES = {"income": "finance.income_statement",
          "balance": "finance.balance_sheet",
          "cash_flow": "finance.cash_flow"}
SRC_PREF = {"income": ("akshare_em_profit_sheet", "baostock",
                       "akshare_sina"),
            "balance": ("akshare_em", "akshare_sina"),
            "cash_flow": ("akshare_em", "akshare_sina")}


def select(rows, td, legacy, pref):
    """rows: [(ann, rp, src)] sorted by ann. Two-level pick."""
    anns = sorted({a for a, _, _ in rows})
    i = bisect.bisect_right(anns, td) if legacy \
        else bisect.bisect_left(anns, td)
    if i == 0:
        return None
    known = [r for r in rows if r[0] <= anns[i - 1]] if legacy else \
        [r for r in rows if r[0] < td]
    if not known:
        return None
    rp = max(r[1] for r in known)                    # level 1
    cands = [r for r in known if r[1] == rp]
    per_src = {}
    for a, p, s in cands:                            # level 2
        if s not in per_src or a > per_src[s][0]:
            per_src[s] = (a, p, s)
    def key(v):
        return pref.index(v[2]) if v[2] in pref else len(pref)
    return sorted(per_src.values(), key=key)[0]


def main():
    with connect(SETTINGS.research_service) as conn:
        dates = sorted(r["d"] for r in fetch_all(conn, """
          SELECT DISTINCT trade_date::text d FROM core.asset_status_daily
          WHERE trade_date >= '2020-01-01'"""))
        month_ends = sorted({d[:7] for d in dates})
        med = [max(d for d in dates if d.startswith(m))
               for m in month_ends]
        ann_dates = {r["d"] for r in fetch_all(conn, """
          SELECT DISTINCT announcement_date::text d
          FROM finance.income_statement
          WHERE announcement_date>='2020-01-01'
            AND announcement_date<='2026-12-31'""")}
        eval_dates = sorted(set(med) | (ann_dates & set(dates)))
        print(f"{len(eval_dates)} eval dates")
        rows, cls = [], Counter()
        sentinel_assets = defaultdict(set)
        spot = []
        for st, t in TABLES.items():
            amap = defaultdict(list)
            for r in fetch_all(conn, f"""
                SELECT asset_id, announcement_date::text ann,
                       report_period::text rp, source
                FROM {t}
                WHERE announcement_date >= '2019-01-01'
                   OR announcement_date IS NULL
                   OR announcement_date='{SENT}'"""):
                if not r["ann"] or r["ann"] == SENT:
                    sentinel_assets[st].add(r["asset_id"])
                    continue
                amap[r["asset_id"]].append((r["ann"], r["rp"], r["source"]))
            pref = SRC_PREF[st]
            diff = 0
            for asset, rr in amap.items():
                first = min(a for a, _, _ in rr)
                j0 = bisect.bisect_left(eval_dates, first)
                for d in eval_dates[j0:]:
                    l, c = select(rr, d, True, pref), select(rr, d, False, pref)
                    if l == c:
                        continue
                    diff += 1
                    if l is None or c is None:
                        k = "lost_availability" if c is None else "gained"
                    elif l[1] != c[1]:
                        k = "period_change"
                    elif l[0] != c[0]:
                        k = "version_change"
                    else:
                        k = "source_change"
                    cls[f"{st}:{k}"] += 1
                    rows.append({"asset_id": asset, "td": d, "st": st,
                                 "kind": k,
                                 "legacy": l and "/".join(l),
                                 "corrected": c and "/".join(c)})
            print(f"  {st}: {diff} diffs", flush=True)
            # real-path spot check: legacy pick must equal actual
            # ORDER BY announcement_date DESC, report_period DESC LIMIT 1
            for r in fetch_all(conn, f"""
                SELECT asset_id FROM {t}
                WHERE announcement_date>='2024-01-01' LIMIT 3"""):
                a = r["asset_id"]
                real = fetch_all(conn, f"""
                  SELECT report_period::text rp,
                         announcement_date::text ann, source
                  FROM {t} WHERE asset_id=%s AND announcement_date<=%s
                  ORDER BY announcement_date DESC, report_period DESC
                  LIMIT 1""", [a, med[-1]])
                pred = select(amap.get(a, []), med[-1], True, pref)
                real_sel = (real[0]["ann"], real[0]["rp"],
                            real[0]["source"]) if real else None
                shadow_sel = (pred[0], pred[1], pred[2]) if pred else None
                match = (real_sel and pred and
                         real_sel[1] == shadow_sel[1])
                spot.append({"statement": st, "asset": a,
                             "td": med[-1], "real": real_sel,
                             "shadow": shadow_sel,
                             "period_match": match})

    with open(OUT / "consumer_shadow_diff_v2.csv", "w", newline="") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    summary = {
        "eval_dates": len(eval_dates), "changed_selections": len(rows),
        "by_kind": dict(cls),
        "sentinel_assets": {k: sorted(v) for k, v in
                            sentinel_assets.items()},
        "real_path_spot_checks": spot,
        "v1_vs_v2": {"v1_changed": 286704, "v2_changed": len(rows),
                     "attribution": "v1 counted bare (ann,rp) tuple "
                                    "mismatch incl. source-less picks; "
                                    "v2 applies two-level selection "
                                    "with explicit source preference"},
    }
    (OUT / "CONSUMER_SHADOW_CORRECTED.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in ("eval_dates",)}, ensure_ascii=False,
                     indent=1)[:3000])


if __name__ == "__main__":
    main()
