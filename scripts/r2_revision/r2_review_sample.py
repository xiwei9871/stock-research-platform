"""Stratified sample of the 1,042 NEEDS_REVIEW assets + DB-side quality
checks (no baostock calls). Per user's review-admission rules:

AUTO-RELEASE if all objective checks pass:
  - live fetch complete in classification (missing_live == 0)
  - pollution signature present: stored qfq == raw close on a large share
    of qfq diff dates (the exact failure mode — snapshot factor == 1.0)
  - qfq diff range is contiguous with detected event dates (diffs start at
    listing or at an event boundary; last diff within ~5 sessions before an
    event or at stored end)
  - no degenerate prices in stored (no null/zero close within diff window)
KEEP REVIEW otherwise.

Strata (>=30): long-history (>8k rows), top diff-ratio, per-board spread,
no-2026-event assets, asymmetric qfq-vs-hfq.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict

sys.path.insert(0, "src")
from stock_research.db import connect, fetch_all  # noqa: E402

BASE = "outputs/research/data01r1_finance_q2_20261020"
SAMPLE_N = 30


def board(asset_id: str) -> str:
    sym = asset_id.split(":")[-1]
    if sym.startswith(("600", "601", "603", "605")):
        return "SH60"
    if sym.startswith("68"):
        return "SH68"
    if sym.startswith(("000", "001")):
        return "SZ00"
    if sym.startswith("002"):
        return "SZ002"
    if sym.startswith("30"):
        return "SZ30"
    return "OTHER"


def main() -> None:
    sets = json.load(open(f"{BASE}/r2_disjoint_sets.json"))
    review = set(sets["NEEDS_REVIEW"])
    rows = {r["asset_id"]: r for r in csv.DictReader(
        open(f"{BASE}/r2_classification.csv")) if r["asset_id"] in review}
    # prefer the row with the largest qfq_diff when duplicated across groups
    by_a: dict[str, dict] = {}
    for r in csv.DictReader(open(f"{BASE}/r2_classification.csv")):
        a = r["asset_id"]
        if a in review and (a not in by_a or int(r["qfq_diff"]) > int(by_a[a]["qfq_diff"])):
            by_a[a] = r

    strata: dict[str, list[str]] = defaultdict(list)
    for a, r in by_a.items():
        sd = int(r["stored_rows"])
        td = int(r["qfq_diff"]) + int(r["hfq_diff"])
        ratio = td / max(sd, 1)
        strata["all"].append(a)
        if sd > 8000:
            strata["long_history"].append(a)
        if ratio > 0.9:
            strata["top_ratio"].append(a)
        if int(r["hfq_diff"]) == 0 and int(r["qfq_diff"]) > 0:
            strata["qfq_only"].append(a)
        if int(r["qfq_diff"]) == 0 and int(r["hfq_diff"]) > 0:
            strata["hfq_only"].append(a)
        strata[f"board_{board(a)}"].append(a)
        if r["qfq_last"] and r["qfq_last"] < "2026-01-01" and r["hfq_last"] < "2026-01-01":
            strata["no_2026_event"].append(a)

    sample: list[str] = []
    quotas = ["long_history", "top_ratio", "qfq_only", "hfq_only",
              "no_2026_event", "board_SH60", "board_SH68",
              "board_SZ00", "board_SZ002", "board_SZ30"]
    for s in quotas:
        for a in sorted(strata.get(s, []))[:4]:
            if a not in sample:
                sample.append(a)
        if len(sample) >= SAMPLE_N + 10:
            break
    for a in sorted(review):
        if len(sample) >= SAMPLE_N + 10:
            break
        if a not in sample:
            sample.append(a)

    with connect("stock_research") as conn:
        results = {}
        for a in sample:
            r = by_a[a]
            checks = {"class_missing_live": int(r["missing_live"])}
            # pollution signature: stored qfq close == raw close on diff dates
            sig = fetch_all(conn, """
                SELECT count(*) tot,
                       count(*) FILTER (WHERE q.close = rw.close AND rw.close IS NOT NULL) eq
                FROM market_daily_bar q JOIN market_daily_bar rw
                  ON rw.asset_id=q.asset_id AND rw.trade_date=q.trade_date
                 AND rw.adjust_type='raw'
                WHERE q.asset_id=%s AND q.adjust_type='qfq'""", [a])[0]
            checks["qfq_eq_raw_frac"] = round(sig["eq"] / max(sig["tot"], 1), 3)
            # degenerate prices in stored qfq/hfq
            bad = fetch_all(conn, """
                SELECT count(*) c FROM market_daily_bar
                WHERE asset_id=%s AND adjust_type IN ('qfq','hfq')
                  AND (close IS NULL OR close<=0)""", [a])[0]["c"]
            checks["bad_price_rows"] = bad
            # qfq diff boundary vs detected events
            checks["qfq_first"], checks["qfq_last"] = r["qfq_first"], r["qfq_last"]
            checks["hfq_first"], checks["hfq_last"] = r["hfq_first"], r["hfq_last"]
            checks["stored_rows"] = int(r["stored_rows"])
            checks["diff_ratio"] = round(
                (int(r["qfq_diff"]) + int(r["hfq_diff"])) / max(int(r["stored_rows"]), 1), 3)
            results[a] = checks
    out = {"sample": sample, "checks": results,
           "strata_counts": {k: len(v) for k, v in strata.items() if k != "all"}}
    json.dump(out, open(f"{BASE}/r2_review_sample.json", "w"),
              ensure_ascii=False, indent=1)
    print(json.dumps({k: len(v) for k, v in strata.items() if k != "all"}, indent=0))
    print(f"sampled {len(sample)} -> r2_review_sample.json")


if __name__ == "__main__":
    main()
