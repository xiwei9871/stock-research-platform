"""ETF-FLOW-POC-01 step 1d — fetch per-fund holder structure.

Source: 天天基金 F10 持有人结构
(fundf10.eastmoney.com/FundArchivesDatas.aspx?type=cyrjg&code=XXXXXX)
— disclosure rows from fund annual/semi-annual reports:
公告日期, 机构持有比例, 个人持有比例, 内部持有比例, 总份额(亿份).

Concurrent (8 workers). data/holder_structure/<code>.csv. Resumable.
"""
import re
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from pathlib import Path

import pandas as pd
import requests

warnings.filterwarnings("ignore")

HERE = Path(__file__).parent
OUTDIR = HERE / "data" / "holder_structure"
OUTDIR.mkdir(parents=True, exist_ok=True)

URL = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
HEADERS = {"Referer": "https://fundf10.eastmoney.com/",
           "User-Agent": "Mozilla/5.0"}


def fetch_one(code: str) -> list[tuple[str, ...]]:
    r = requests.get(URL, params={"type": "cyrjg", "code": code},
                     headers=HEADERS, timeout=25)
    r.raise_for_status()
    rows = re.findall(r"<tr>(.*?)</tr>", r.text, re.S)
    out = []
    for row in rows:
        cells = [unescape(re.sub(r"<[^>]+>", "", c)).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) >= 5 and cells[0][:4].isdigit():
            out.append(tuple(cells[:5]))
    return out


def work(code: str) -> int:
    rows = None
    for attempt in range(3):
        try:
            rows = fetch_one(code)
            break
        except Exception:  # noqa: BLE001
            time.sleep(2 * (attempt + 1))
    if rows is None:
        return -1
    pd.DataFrame(rows, columns=[
        "disclosure_date", "inst_pct", "indiv_pct",
        "internal_pct", "total_shares_yi",
    ]).to_csv(OUTDIR / f"{code}.csv", index=False)
    return len(rows)


def main() -> None:
    codes = [c.strip() for c in
             (HERE / "data" / "current_universe.txt")
             .read_text().split() if c.strip()]
    todo = [c for c in codes if not (OUTDIR / f"{c}.csv").exists()]
    print(f"holders: {len(codes)-len(todo)} done, {len(todo)} todo",
          flush=True)
    fails = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(work, c): c for c in todo}
        for i, fut in enumerate(as_completed(futs)):
            if fut.result() < 0:
                fails.append(futs[fut])
            if i % 100 == 0 or i == len(todo) - 1:
                print(f"holders {i+1}/{len(todo)} fails={len(fails)}",
                      flush=True)
    if fails:
        print("FAILED:", fails, flush=True)


if __name__ == "__main__":
    main()
