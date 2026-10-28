"""ETF-FLOW-POC-01 step 1c — fetch daily close history per ETF.

Source: 腾讯行情 web.ifzq.gtimg.cn fqkline (one call = full daily
history per fund, raw JSON, thread-safe). Close price is the bulk
valuation basis; premium/discount vs unit NAV is reconciled in
validation via sample lsjz NAVs.

Usage: fetch_prices.py [code ...]   (no args = current_universe.txt)
data/prices/<code>.csv per fund. Concurrent (6 workers). Resumable.
"""
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

warnings.filterwarnings("ignore")

HERE = Path(__file__).parent
OUTDIR = HERE / "data" / "prices"
OUTDIR.mkdir(parents=True, exist_ok=True)
URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

SAMPLE_FIRST = [
    "510300", "510050", "510500", "159915", "512880",
    "515790", "588000", "159919", "510880", "512170",
]


def work(code: str) -> int:
    sym = ("sh" if code.startswith("5") else "sz") + code
    for attempt in range(4):
        try:
            r = requests.get(
                URL,
                params={"param": f"{sym},day,2019-11-01,2026-10-27,2000,"},
                headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            d = r.json()["data"][sym]["day"]
            if not d:
                return 0
            df = pd.DataFrame(
                [row[:6] for row in d],
                columns=["date", "open", "close", "high", "low",
                         "volume"])
            df.to_csv(OUTDIR / f"{code}.csv", index=False)
            return len(df)
        except Exception:  # noqa: BLE001
            time.sleep(2 * (attempt + 1))
    return -1


def main() -> None:
    args = sys.argv[1:]
    codes = args or [c.strip() for c in
                     (HERE / "data" / "current_universe.txt")
                     .read_text().split() if c.strip()]
    ordered = [c for c in SAMPLE_FIRST if c in codes] + \
              [c for c in codes if c not in SAMPLE_FIRST]
    todo = [c for c in ordered
            if not (OUTDIR / f"{c}.csv").exists()
            or (OUTDIR / f"{c}.csv").stat().st_size < 200]
    print(f"prices: {len(codes)-len(todo)} done, {len(todo)} todo",
          flush=True)
    fails = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(work, c): c for c in todo}
        for i, fut in enumerate(as_completed(futs)):
            if fut.result() < 0:
                fails.append(futs[fut])
            if i % 150 == 0 or i == len(todo) - 1:
                print(f"prices {i+1}/{len(todo)} fails={len(fails)}",
                      flush=True)
    if fails:
        print("FAILED:", fails[:50], flush=True)


if __name__ == "__main__":
    main()
