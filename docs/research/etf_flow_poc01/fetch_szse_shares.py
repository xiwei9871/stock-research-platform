"""ETF-FLOW-POC-01 step 1b — fetch SZSE-listed ETF daily share counts.

Source: 深交所基金规模日频 via akshare.fund_scale_daily_szse
(start_date,end_date,symbol='ETF'). The endpoint accepts multi-day
ranges; we pull calendar-month chunks (measured ~7s/call).

Writes data/szse_etf_shares.csv (date,fund_code,name,etf_type,szse,
shares). Resumable by month chunk.
"""
import calendar
import sys
import time
import warnings
from pathlib import Path

import akshare as ak
import pandas as pd

warnings.filterwarnings("ignore")

HERE = Path(__file__).parent
DATES = (HERE / "data" / "trading_dates.txt").read_text().split()
OUT = HERE / "data" / "szse_etf_shares.csv"


def month_chunks() -> list[tuple[str, str]]:
    first, last = DATES[0], DATES[-1]
    y, m = int(first[:4]), int(first[5:7])
    chunks = []
    while (y, m) <= (int(last[:4]), int(last[5:7])):
        dim = calendar.monthrange(y, m)[1]
        lo = f"{y}{m:02d}01"
        hi = f"{y}{m:02d}{dim:02d}"
        chunks.append((lo, hi))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return chunks


def main() -> None:
    done = set()
    if OUT.exists():
        d = pd.read_csv(OUT, dtype={"date": str})
        done = set(d["date"].str[:7].unique())  # finished months
    todo = [(lo, hi) for lo, hi in month_chunks() if lo[:6] not in done]
    print(f"szse_shares: {len(done)} months done, {len(todo)} todo", flush=True)
    for i, (lo, hi) in enumerate(todo):
        for attempt in range(4):
            try:
                df = ak.fund_scale_daily_szse(start_date=lo, end_date=hi,
                                              symbol="ETF")
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 3:
                    print(f"{lo}-{hi} FAIL {e!r:.120}", flush=True)
                    df = None
                else:
                    time.sleep(5 * (attempt + 1))
        if df is None or df.empty:
            continue
        out = pd.DataFrame({
            "date": df["日期"].astype(str).str[:10],
            "fund_code": df["基金代码"].astype(str).str.zfill(6),
            "name": df["基金简称"].astype(str),
            "etf_type": "szse",
            "shares": pd.to_numeric(df["基金份额"], errors="coerce"),
        })
        out.to_csv(OUT, mode="a", header=not OUT.exists() or OUT.stat().st_size == 0,
                   index=False)
        print(f"szse_shares {i+1}/{len(todo)} {lo}-{hi} rows={len(out)}",
              flush=True)
        time.sleep(1.0)


if __name__ == "__main__":
    sys.exit(main())
