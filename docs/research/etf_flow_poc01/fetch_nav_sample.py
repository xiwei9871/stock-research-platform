"""ETF-FLOW-POC-01 — unit-NAV history for the 10 sample ETFs.

Source: 天天基金 F10 历史净值 api.fund.eastmoney.com/f10/lsjz
(daily DWJZ 单位净值, paged 49/page). Used to reconcile the sina
close-price valuation against real NAV.

data/nav/<code>.csv — resumable by earliest date already fetched.
"""
import time
from pathlib import Path

import pandas as pd
import requests

OUT = Path("data/nav")
OUT.mkdir(exist_ok=True)
SAMPLE = ["510300", "510050", "510500", "159915", "512880",
          "515790", "588000", "159919", "510880", "512170"]
TARGET_START = "2019-12-01"


def earliest(p: Path) -> str | None:
    if not p.exists():
        return None
    d = pd.read_csv(p, dtype={"date": str})
    return d["date"].min() if len(d) else None


for code in SAMPLE:
    p = OUT / f"{code}.csv"
    have = earliest(p)
    if have and have <= "2020-01-10":
        print(code, "complete")
        continue
    rows = []
    if have:  # keep existing tail, fetch only the older part
        rows = pd.read_csv(p, dtype={"date": str}).to_dict("records")
        end = have
    else:
        end = "2026-10-27"
    for page in range(1, 60):
        d = None
        for att in range(4):
            try:
                r = requests.get(
                    "https://api.fund.eastmoney.com/f10/lsjz",
                    params={"fundCode": code, "pageIndex": page,
                            "pageSize": 49, "startDate": TARGET_START,
                            "endDate": end},
                    headers={"Referer": "https://fundf10.eastmoney.com/"},
                    timeout=25)
                d = r.json()["Data"]["LSJZList"]
                break
            except Exception as e:  # noqa: BLE001
                if att == 3:
                    print(code, "page", page, "FAIL", str(e)[:80])
                else:
                    time.sleep(4 * (att + 1))
        if not d:
            break
        rows += [{"date": x["FSRQ"], "nav": x["DWJZ"]} for x in d]
        if min(x["FSRQ"] for x in d) <= "2020-01-05":
            break
        time.sleep(0.6)
    out = (pd.DataFrame(rows).drop_duplicates("date")
           .sort_values("date", ascending=False))
    out.to_csv(p, index=False)
    print(code, len(out), out["date"].min(), "->", out["date"].max())
