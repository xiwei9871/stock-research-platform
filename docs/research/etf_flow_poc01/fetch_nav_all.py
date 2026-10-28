"""ETF-FLOW-POC-01 — unit NAV history for the whole universe.

Source: 天天基金 pingzhongdata/<code>.js → Data_netWorthTrend
(one call = full daily DWJZ history per fund). Real unit NAV —
closer to the likely Wind basis than close price.

Universe = current_universe.txt + every code seen in share files
(covers delisted funds). data/naval/<code>.csv. 6 workers. Resumable.
"""
import json
import re
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

warnings.filterwarnings("ignore")

HERE = Path(__file__).parent
OUTDIR = HERE / "data" / "naval"
OUTDIR.mkdir(parents=True, exist_ok=True)
HEADERS = {"Referer": "https://fund.eastmoney.com/",
           "User-Agent": "Mozilla/5.0"}
RE = re.compile(r"Data_netWorthTrend\s*=\s*(\[.*?\])\s*;")


def universe() -> list[str]:
    codes = set(c.strip() for c in
                (HERE / "data" / "current_universe.txt")
                .read_text().split() if c.strip())
    for f in ("sse_daily",):
        for p in (HERE / "data" / f).glob("*.csv"):
            d = pd.read_csv(p, dtype={"fund_code": str})
            codes.update(d["fund_code"].str.zfill(6))
    p = HERE / "data" / "szse_etf_shares.csv"
    if p.exists():
        d = pd.read_csv(p, dtype={"fund_code": str})
        codes.update(d["fund_code"].str.zfill(6))
    return sorted(codes)


def work(code: str) -> int:
    for attempt in range(4):
        try:
            r = requests.get(
                f"https://fund.eastmoney.com/pingzhongdata/{code}.js",
                headers=HEADERS, timeout=20)
            m = RE.search(r.text)
            arr = json.loads(m.group(1)) if m else []
            if not arr:
                (OUTDIR / f"{code}.empty").write_text("")
                return 0
            df = pd.DataFrame({
                "date": [pd.to_datetime(x["x"], unit="ms").date()
                         for x in arr],
                "nav": [x.get("y") for x in arr]})
            df.to_csv(OUTDIR / f"{code}.csv", index=False)
            return len(df)
        except Exception:  # noqa: BLE001
            time.sleep(2 * (attempt + 1))
    return -1


def main() -> None:
    codes = universe()
    todo = [c for c in codes
            if not (OUTDIR / f"{c}.csv").exists()
            and not (OUTDIR / f"{c}.empty").exists()]
    print(f"naval: {len(codes)-len(todo)} done, {len(todo)} todo",
          flush=True)
    fails = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(work, c): c for c in todo}
        for i, fut in enumerate(as_completed(futs)):
            if fut.result() < 0:
                fails.append(futs[fut])
            if i % 200 == 0 or i == len(todo) - 1:
                print(f"naval {i+1}/{len(todo)} fails={len(fails)}",
                      flush=True)
    if fails:
        print("FAILED:", fails[:60], flush=True)


if __name__ == "__main__":
    sys.exit(main())
