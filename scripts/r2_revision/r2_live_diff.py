"""R2 read-only live-vs-stored adjustment diff for 5 sample ex-rights stocks.

Queries baostock (single session) for raw/qfq/hfq full-history daily bars and
diffs close prices against market_daily_bar. Read-only: no writes.
"""
from __future__ import annotations

import json
import sys

import baostock as bs

sys.path.insert(0, "src")
from stock_research.db import connect, fetch_all  # noqa: E402

SAMPLES = {
    "CN:SH:600016": "2026-09-15",
    "CN:SZ:000568": "2026-08-28",
    "CN:SH:600028": "2026-09-30",
    "CN:SH:600380": "2026-10-20",
    "CN:SZ:301237": "2026-09-01",
}
ADJUSTFLAG = {"raw": "3", "qfq": "2", "hfq": "1"}  # baostock: 1=hfq 2=qfq 3=raw
END = "2026-10-20"


def bs_code(asset_id: str) -> str:
    _, exch, sym = asset_id.split(":")
    return f"{exch.lower()}.{sym}"


def fetch_live(code: str, adjustflag: str, start: str) -> dict[str, float]:
    rs = bs.query_history_k_data_plus(
        code, "date,close",
        start_date=start, end_date=END,
        frequency="d", adjustflag=adjustflag,
    )
    if rs.error_code != "0":
        raise RuntimeError(f"{code} adjustflag={adjustflag}: {rs.error_code} {rs.error_msg}")
    out = {}
    while rs.next():
        row = rs.get_row_data()
        if row[1]:
            out[row[0]] = float(row[1])
    return out


def main() -> None:
    login = bs.login()
    if login.error_code != "0":
        raise SystemExit(f"login failed: {login.error_code} {login.error_msg}")
    report = {}
    try:
        with connect("stock_research") as conn:
            for asset_id, ex_date in SAMPLES.items():
                code = bs_code(asset_id)
                stored = {
                    r["adjust_type"]: {str(r["trade_date"]): float(r["close"])
                                       for r in fetch_all(
                            conn,
                            "SELECT trade_date, close, adjust_type FROM market_daily_bar "
                            "WHERE asset_id=%s AND adjust_type=%s AND trade_date<=%s "
                            "ORDER BY trade_date",
                            [asset_id, r["adjust_type"], END])}
                    for r in [{"adjust_type": a} for a in ADJUSTFLAG]
                }
                start = min(min(d) for d in stored.values() if d)
                asset_rep = {"ex_date": ex_date, "history_start": start}
                for adj, flag in ADJUSTFLAG.items():
                    live = fetch_live(code, flag, start)
                    diffs = [
                        {"d": d, "stored": stored[adj][d], "live": live[d]}
                        for d in stored[adj]
                        if d in live and abs(live[d] - stored[adj][d]) / stored[adj][d] > 0.0005
                    ]
                    missing_live = [d for d in stored[adj] if d not in live]
                    extra_live = [d for d in live if d not in stored[adj]]
                    asset_rep[adj] = {
                        "stored_rows": len(stored[adj]),
                        "live_rows": len(live),
                        "diff_rows": len(diffs),
                        "first_diff": diffs[0]["d"] if diffs else None,
                        "last_diff": diffs[-1]["d"] if diffs else None,
                        "missing_in_live": len(missing_live),
                        "extra_in_live": len(extra_live),
                        "sample_diffs": diffs[:3] + diffs[-3:] if len(diffs) > 6 else diffs,
                    }
                report[asset_id] = asset_rep
    finally:
        bs.logout()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
