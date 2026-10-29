"""Compute per-lane daily AUM (shares x NAV, yi yuan) for both
classification modes -> data/lane_aum_{pit,fixed}.csv.

Reads etf_daily_flows_v2.csv (POC-02.1 pipeline output). NAV is
forward-filled per fund so AUM stays continuous on unpriced days.
Visualization input for the "占当日规模%" display mode.
"""
import pandas as pd

COLS = ["date", "fund_code", "shares", "valuation",
        "class_fixed", "class_pit"]

d = pd.read_csv("data/etf_daily_flows_v2.csv", usecols=COLS,
                dtype={"fund_code": str, "valuation": float},
                parse_dates=["date"])
d["fund_code"] = d["fund_code"].str.zfill(6)
d["shares"] = pd.to_numeric(d["shares"], errors="coerce")
d = d.sort_values(["fund_code", "date"])
d["navf"] = d.groupby("fund_code")["valuation"].ffill()
d["mv"] = d["shares"] * d["navf"] / 1e8
for cls in ("pit", "fixed"):
    aum = (d.groupby(["date", f"class_{cls}"])["mv"].sum()
            .unstack().fillna(0))
    aum.index = aum.index.strftime("%Y-%m-%d")
    aum.to_csv(f"data/lane_aum_{cls}.csv")
    print(cls, aum.shape)
