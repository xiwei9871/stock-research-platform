"""ETF-FLOW-POC-01 step 1a — fetch SSE-listed ETF daily share counts.

Source: 上交所 ETF 产品列表 (query.sse.com.cn) via
akshare.fund_etf_scale_sse(date). One call returns every SSE-listed
ETF's 基金份额 for that trading date — authoritative exchange data.

Concurrent (4 workers, polite jitter); per-date files under
data/sse_daily/<date>.csv — resumable. Run merge_sse() afterwards to
produce data/sse_etf_shares.csv.
"""
import random
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import akshare as ak
import pandas as pd

warnings.filterwarnings("ignore")

HERE = Path(__file__).parent
DATES = (HERE / "data" / "trading_dates.txt").read_text().split()
OUTDIR = HERE / "data" / "sse_daily"
OUTDIR.mkdir(parents=True, exist_ok=True)
OUT = HERE / "data" / "sse_etf_shares.csv"


def fetch_date(d: str) -> tuple[str, int]:
    ymd = d.replace("-", "")
    for attempt in range(5):
        try:
            df = ak.fund_etf_scale_sse(date=ymd)
            if df is None or df.empty:
                return d, 0
            out = pd.DataFrame({
                "date": df["统计日期"].astype(str).str[:10],
                "fund_code": df["基金代码"].astype(str).str.zfill(6),
                "name": df["基金简称"].astype(str),
                "etf_type": df["ETF类型"].astype(str),
                "shares": pd.to_numeric(df["基金份额"], errors="coerce"),
            })
            out.to_csv(OUTDIR / f"{d}.csv", index=False)
            return d, len(out)
        except Exception:  # noqa: BLE001
            time.sleep(2 * (attempt + 1) + random.random() * 2)
    return d, -1


def main() -> None:
    todo = [d for d in DATES if not (OUTDIR / f"{d}.csv").exists()]
    print(f"sse_shares: {len(DATES)-len(todo)} done, {len(todo)} todo",
          flush=True)
    fails = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(fetch_date, d): d for d in todo}
        for i, fut in enumerate(as_completed(futs)):
            d, n = fut.result()
            if n < 0:
                fails.append(d)
            if i % 50 == 0 or i == len(todo) - 1:
                print(f"sse_shares {i+1}/{len(todo)} fails={len(fails)}",
                      flush=True)
            time.sleep(random.random() * 0.3)
    if fails:
        print("FAILED DATES:", fails, flush=True)


if __name__ == "__main__":
    sys.exit(main())
