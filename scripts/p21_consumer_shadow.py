#!/usr/bin/env python3
"""P2.1-C — same-day-announcement forward-bias shadow.

Legacy:    announcement_date <= trade_date   (current consumers)
Corrected: announcement_date <  trade_date   (D+1 conservative)

For every (asset, eval trade date) compute the statement version each
convention selects; count selection + report-period changes.
Eval dates = all month-end trade dates since 2020 plus every date that
is itself an announcement date (the exact leak surface).
Read-only; no factor/backtest outputs overwritten.
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

OUT = Path("docs/research_upgrade/p21")
TABLES = {"income": "finance.income_statement",
          "balance": "finance.balance_sheet",
          "cash_flow": "finance.cash_flow"}


def pick(anns, td, legacy):
    """anns: sorted list of (ann, rp). Return selected (ann,rp) or None."""
    i = bisect.bisect_right([a for a, _ in anns], td) if legacy \
        else bisect.bisect_left([a for a, _ in anns], td)
    if i == 0:
        return None
    # latest ann meeting the rule; within it the latest rp
    ann = anns[i - 1][0]
    rps = [rp for a, rp in anns if a == ann]
    return ann, max(rps)


def main():
    with connect(SETTINGS.research_service) as conn:
        dates = sorted(r["d"] for r in fetch_all(conn, """
          SELECT DISTINCT trade_date::text d FROM core.asset_status_daily
          WHERE trade_date >= '2020-01-01'"""))
        month_ends = sorted({d[:7] for d in dates})
        med = [max(d for d in dates if d.startswith(m)) for m in month_ends]
        ann_dates = {r["d"] for r in fetch_all(conn, """
          SELECT DISTINCT announcement_date::text d
          FROM finance.income_statement
          WHERE announcement_date>='2020-01-01'
            AND announcement_date<='2026-12-31'""")}
        eval_dates = sorted(set(med) | (ann_dates & set(dates)))
        idx = {d: i for i, d in enumerate(eval_dates)}
        print(f"{len(dates)} trade dates, {len(med)} month-ends, "
              f"{len(eval_dates)} eval dates")
        rows = []
        for st, t in TABLES.items():
            amap = defaultdict(list)
            for r in fetch_all(conn, f"""
                SELECT asset_id, announcement_date::text ann,
                       report_period::text rp
                FROM {t}
                WHERE announcement_date IS NOT NULL
                  AND announcement_date <> '1900-01-01'
                  AND announcement_date >= '2019-01-01'"""):
                amap[r["asset_id"]].append((r["ann"], r["rp"]))
            for v in amap.values():
                v.sort()
            diff = 0
            for asset, anns in amap.items():
                first = anns[0][0]
                j0 = bisect.bisect_left(eval_dates, first)
                for d in eval_dates[j0:]:
                    l, c = pick(anns, d, True), pick(anns, d, False)
                    if l != c:
                        diff += 1
                        rows.append({"asset_id": asset, "td": d,
                                     "statement": st,
                                     "legacy_sel": l and f"{l[0]}/{l[1]}",
                                     "corr_sel": c and f"{c[0]}/{c[1]}",
                                     "period_shift": bool(
                                         l and c and l[1] != c[1])})
            print(f"  {st}: {diff} changed selections", flush=True)

    rows.sort(key=lambda r: (r["td"], r["asset_id"]))
    with open(OUT / "consumer_shadow_diff.csv", "w", newline="") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    by_date, by_st = Counter(r["td"] for r in rows), Counter(
        r["statement"] for r in rows)
    summary = {
        "eval_dates": eval_dates,
        "changed_selections": len(rows),
        "by_statement": dict(by_st),
        "period_shifts": sum(1 for r in rows if r["period_shift"]),
        "affected_dates_n": len(by_date),
        "affected_dates_top": by_date.most_common(20),
        "note": "legacy-vs-D+1 selection diff over asset x eval-date; "
                "P&L-level factor/backtest rerun is repair-phase scope",
    }
    (OUT / "consumer_shadow_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in summary.items()
                      if k != "eval_dates"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
