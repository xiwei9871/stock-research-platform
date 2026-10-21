"""REVIEW-pool live verification (baostock — run only when repair driver
is idle; single session). Per asset fetches live raw/qfq/hfq and checks:

AUTO_RELEASABLE when ALL hold:
  A. live coverage ⊇ stored dates (no missing source history)
  B. no degenerate closes (<=0 / null) in live series
  C. live qfq/raw factor is piecewise-constant: every |factor| jump >0.1%
     lands on a preclose-corroborated event date (raw preclose vs prev
     raw close differs >0.1%) — i.e. diffs are explained by real
     corporate actions, not a different adjustment convention
  D. live factor within sane range (0 < f <= 1.02 for qfq)
KEEP_REVIEW otherwise (reasons recorded).

Usage: r2_review_verify.py [N]   # first N review assets (default all)
"""
from __future__ import annotations

import csv
import json
import os
import sys

import socket
socket.setdefaulttimeout(120)

import baostock as bs  # noqa: E402

sys.path.insert(0, "src")
from stock_research.db import connect, fetch_all  # noqa: E402

BASE = "outputs/research/data01r1_finance_q2_20261020"
END = "2026-10-20"
FIELDS = "date,code,open,high,low,close,preclose,volume,amount,turn,pctChg,tradestatus,isST"
OUT = f"{BASE}/r2_review_verdicts.jsonl"
EVENT_TOL = 0.001


def fetch(code, flag, start):
    rs = bs.query_history_k_data_plus(
        code, FIELDS, start_date=start, end_date=END,
        frequency="d", adjustflag=flag)
    if rs.error_code != "0":
        raise RuntimeError(f"{code} flag{flag}: {rs.error_code} {rs.error_msg}")
    rows = []
    while rs.next():
        d = rs.get_row_data()
        try:
            close = float(d[5]) if d[5] else None
        except ValueError:
            close = None
        rows.append({"date": d[0], "close": close,
                     "preclose": float(d[6]) if d[6] else None})
    return rows


def verify(conn, asset_id: str) -> dict:
    _, exch, sym = asset_id.split(":")
    code = f"{exch.lower()}.{sym}"
    raw = fetch(code, "3", "1990-01-01")
    qfq = fetch(code, "2", "1990-01-01")
    hfq = fetch(code, "1", "1990-01-01")
    res = {"asset_id": asset_id, "reasons": []}
    # stored-vs-live date-set comparison on all three series
    for adj, rows in (("raw", raw), ("qfq", qfq), ("hfq", hfq)):
        stored_dates = {str(r["trade_date"]) for r in fetch_all(
            conn, "SELECT trade_date FROM market_daily_bar "
                  "WHERE asset_id=%s AND adjust_type=%s AND trade_date<=%s",
            [asset_id, adj, END])}
        live_d = {r["date"] for r in rows}
        missing_live = stored_dates - live_d
        extra_live = live_d - stored_dates
        res[f"{adj}_stored"] = len(stored_dates)
        res[f"{adj}_live"] = len(live_d)
        res[f"{adj}_missing_live"] = len(missing_live)
        res[f"{adj}_extra_live"] = len(extra_live)
        if missing_live:
            res["reasons"].append(
                f"{adj}_live_missing_stored_dates={len(missing_live)}")
        if len(extra_live) > 30:
            # live legitimately extends past stored END only by new days;
            # large excess means a different listing/calendar -> conflict
            res["reasons"].append(f"{adj}_extra_live_dates={len(extra_live)}")
    # raw vs qfq vs hfq should share the same live date set
    if {r["date"] for r in raw} != {r["date"] for r in qfq} or \
            {r["date"] for r in raw} != {r["date"] for r in hfq}:
        res["reasons"].append("live_date_sets_diverge_across_adjust_types")
    bad = sum(1 for r in qfq + hfq if r["close"] is None or r["close"] <= 0)
    if bad:
        res["reasons"].append(f"degenerate_closes={bad}")
    # factor jumps vs preclose corroboration (raw)
    raw_by_date = {r["date"]: r for r in raw}
    dates = sorted(raw_by_date)
    prev = None
    event_dates = set()
    for d in dates:
        r = raw_by_date[d]
        if prev and r["preclose"] and prev["close"] and \
                abs(r["preclose"] - prev["close"]) / prev["close"] > EVENT_TOL:
            event_dates.add(d)
        prev = r
    raw_close = {d: raw_by_date[d]["close"] for d in dates}
    uncorr = []
    prev_f = None
    for r in qfq:
        rc = raw_close.get(r["date"])
        if not rc or not r["close"]:
            continue
        f = r["close"] / rc
        if f <= 0 or f > 1.02:
            res["reasons"].append(f"qfq_factor_out_of_range@{r['date']}:{f:.3f}")
        if prev_f is not None and abs(f / prev_f - 1) > EVENT_TOL:
            if r["date"] not in event_dates:
                uncorr.append(r["date"])
        prev_f = f
    res["uncorroborated_jumps"] = uncorr[:10]
    if uncorr:
        res["reasons"].append(f"uncorroborated_factor_jumps={len(uncorr)}")
    res["live_qfq_rows"] = len(qfq)
    res["event_dates"] = len(event_dates)
    res["verdict"] = "KEEP_REVIEW" if res["reasons"] else "AUTO_RELEASABLE"
    return res


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else None
    sets = json.load(open(f"{BASE}/r2_disjoint_sets.json"))
    pool = sets["NEEDS_REVIEW"][:n] if n else sets["NEEDS_REVIEW"]
    seen = set()
    if os.path.exists(OUT):
        for line in open(OUT):
            try:
                seen.add(json.loads(line)["asset_id"])
            except json.JSONDecodeError:
                pass
    todo = [a for a in pool if a not in seen]
    print(f"review pool {len(pool)} | todo {len(todo)}")
    login = bs.login()
    if login.error_code != "0":
        raise SystemExit(f"login failed {login.error_code}")
    try:
        with connect("stock_research") as conn:
            for i, a in enumerate(todo, 1):
                try:
                    res = verify(conn, a)
                except Exception as exc:
                    res = {"asset_id": a, "verdict": "ERROR",
                           "reasons": [str(exc)[:200]]}
                with open(OUT, "a") as f:
                    f.write(json.dumps(res, ensure_ascii=False) + "\n")
                if i % 25 == 0:
                    print(f"{i}/{len(todo)} {res['verdict']}", flush=True)
    finally:
        bs.logout()


if __name__ == "__main__":
    main()
