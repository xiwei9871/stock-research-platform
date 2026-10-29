"""Fetch the three comparison indices for the POC-03 chart.

上证指数 sh000001 / 深证成指 sz399001: sina daily kline.
中证全指 000985 (all-A proxy, 5117 constituents): official CSIndex API.
Saves data/index_daily.csv aligned to the POC-02.1 trading calendar.
Visualization input only — no ETF flow recalculation.
"""
import datetime

import akshare as ak
import pandas as pd

LO, HI = datetime.date(2020, 1, 1), datetime.date(2026, 10, 27)
OUT = "data/index_daily.csv"


def main():
    out = {}
    for sym, col in (("sh000001", "sse"), ("sz399001", "szse")):
        d = ak.stock_zh_index_daily(symbol=sym)
        d = d[(d["date"] >= LO) & (d["date"] <= HI)][["date", "close"]]
        d["date"] = d["date"].astype(str)
        out[col] = d.set_index("date")["close"]
    d = ak.stock_zh_index_hist_csindex(
        symbol="000985", start_date="20200101", end_date="20261027")
    d = d[["日期", "收盘"]].rename(columns={"日期": "date", "收盘": "all_a"})
    d["date"] = d["date"].astype(str)
    out["all_a"] = d.set_index("date")["all_a"].astype(float)
    m = pd.DataFrame(out).sort_index()
    m.index.name = "date"
    m.to_csv(OUT)
    print("saved", OUT, m.shape)


if __name__ == "__main__":
    main()
