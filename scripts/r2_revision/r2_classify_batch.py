"""R2 batch classification: live-vs-stored close-price diff for every
candidate asset (primary + early-only + control). Checkpoints to CSV so it
can resume. Read-only. Run only when baostock session is free.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time

import baostock as bs
from baostock_guard import assert_baostock_free  # noqa: E402

sys.path.insert(0, "src")
from stock_research.adjustment_revision import (  # noqa: E402
    classify_asset_revision,
    diff_stored_vs_live,
)
from stock_research.db import connect, fetch_all  # noqa: E402

BASE = "outputs/research/data01r1_finance_q2_20261020"
CAND = json.load(open(f"{BASE}/r2_candidates.json"))
OUT = f"{BASE}/r2_classification.csv"
END = "2026-10-20"
ADJUSTFLAG = {"qfq": "2", "hfq": "1"}

assets = (
    [(a, "primary") for a in CAND["primary_assets"]]
    + [(a, "early_only") for a in CAND["early_only_assets"]]
    + [(a, "control") for a in CAND["control_assets"]]
)


def bs_code(asset_id: str) -> str:
    _, exch, sym = asset_id.split(":")
    return f"{exch.lower()}.{sym}"


def fetch_live_close(code: str, adjustflag: str, start: str) -> dict[str, float]:
    rs = bs.query_history_k_data_plus(
        code, "date,close", start_date=start, end_date=END,
        frequency="d", adjustflag=adjustflag,
    )
    if rs.error_code != "0":
        raise RuntimeError(f"{code} flag={adjustflag}: {rs.error_code} {rs.error_msg}")
    out = {}
    while rs.next():
        d = rs.get_row_data()
        if d[1]:
            out[d[0]] = float(d[1])
    return out


def main() -> None:
    done = set()
    if os.path.exists(OUT):
        with open(OUT) as f:
            done = {r["asset_id"] for r in csv.DictReader(f)}
    assert_baostock_free()
    login = bs.login()
    if login.error_code != "0":
        raise SystemExit(f"login failed {login.error_code} {login.error_msg}")
    new = not os.path.exists(OUT)
    try:
        with connect("stock_research") as conn, open(OUT, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["asset_id", "group", "status", "qfq_diff", "qfq_first",
                            "qfq_last", "hfq_diff", "hfq_first", "hfq_last",
                            "stored_rows", "missing_live", "error"])
            for i, (asset_id, group) in enumerate(assets, 1):
                if asset_id in done:
                    continue
                try:
                    stored = {}
                    for adj in ("qfq", "hfq"):
                        rows = fetch_all(
                            conn,
                            "SELECT trade_date, close FROM market_daily_bar "
                            "WHERE asset_id=%s AND adjust_type=%s AND trade_date<=%s",
                            [asset_id, adj, END],
                        )
                        stored[adj] = {str(r["trade_date"]): float(r["close"]) for r in rows}
                    start = min((min(v) for v in stored.values() if v), default="2026-01-01")
                    diffs = {}
                    for adj, flag in ADJUSTFLAG.items():
                        live = fetch_live_close(bs_code(asset_id), flag, start)
                        diffs[adj] = diff_stored_vs_live(stored[adj], live)
                    status = classify_asset_revision(
                        qfq_diff=diffs["qfq"], hfq_diff=diffs["hfq"],
                        stored_rows=len(stored["qfq"]) + len(stored["hfq"]),
                    )
                    w.writerow([
                        asset_id, group, status,
                        diffs["qfq"]["diff_count"], diffs["qfq"]["first_diff"], diffs["qfq"]["last_diff"],
                        diffs["hfq"]["diff_count"], diffs["hfq"]["first_diff"], diffs["hfq"]["last_diff"],
                        len(stored["qfq"]) + len(stored["hfq"]),
                        diffs["qfq"]["missing_in_live"] + diffs["hfq"]["missing_in_live"], "",
                    ])
                except Exception as exc:  # noqa: BLE001
                    w.writerow([asset_id, group, "ERROR", "", "", "", "", "", "", "", "",
                                f"{type(exc).__name__}: {exc}"[:180]])
                f.flush()
                if i % 100 == 0:
                    print(f"classified {i}/{len(assets)}", flush=True)
                    time.sleep(0.5)
    finally:
        bs.logout()
    print("classification done")


if __name__ == "__main__":
    main()
