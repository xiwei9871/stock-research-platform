"""M1 data extraction: emotion daily (recomputed PIT), index bars, breadth extras.

Chunks market_daily_bar by year-with-overlap so limit-streak logic stays
correct while peak memory stays bounded. Read-only on production DB.
"""
import sys
sys.path.insert(0, "/Users/xiwei/stock_research/.worktrees/etf-poc/src")
import pandas as pd
import numpy as np
from stock_research.market_emotion_state_v1 import (
    load_market_emotion_source_frames,
    build_market_emotion_state_from_frames,
)
from stock_research.db import connect, fetch_all
from stock_research.config import SETTINGS

OUT = "data"
CHUNKS = [("2019-11-01", "2021-06-30"), ("2021-05-01", "2022-12-31"),
          ("2022-11-01", "2024-06-30"), ("2024-05-01", "2025-12-31"),
          ("2025-11-01", "2026-10-28")]
WARM = "2020-01-01"


def breadth_extra(bars: pd.DataFrame) -> pd.DataFrame:
    """Per-day share of stocks above MA20/MA60 and at 20d high."""
    b = bars[["trade_date", "asset_id", "close"]].copy()
    b["trade_date"] = pd.to_datetime(b["trade_date"])
    b = b.sort_values(["asset_id", "trade_date"])
    g = b.groupby("asset_id")["close"]
    b["ma20"] = g.transform(lambda s: s.rolling(20, min_periods=10).mean())
    b["ma60"] = g.transform(lambda s: s.rolling(60, min_periods=30).mean())
    b["hi20"] = g.transform(lambda s: s.rolling(20, min_periods=10).max())
    agg = b.groupby("trade_date").agg(
        n=("close", "size"),
        pct_above_ma20=("close", lambda s: np.nan),
    )
    tmp = b.groupby("trade_date")
    out = pd.DataFrame({
        "n": tmp.size(),
        "pct_above_ma20": tmp.apply(
            lambda x: (x.close > x.ma20).mean(), include_groups=False),
        "pct_above_ma60": tmp.apply(
            lambda x: (x.close > x.ma60).mean(), include_groups=False),
        "pct_at_hi20": tmp.apply(
            lambda x: (x.close >= x.hi20).mean(), include_groups=False),
    }).reset_index()
    return out


def main():
    import pathlib
    pathlib.Path(OUT).mkdir(exist_ok=True)
    emos, breads = [], []
    for s, e in CHUNKS:
        bars, status = load_market_emotion_source_frames(s, e)
        daily = build_market_emotion_state_from_frames(bars, status)
        daily["trade_date"] = pd.to_datetime(daily["trade_date"])
        emos.append(daily[daily.trade_date >= max(pd.Timestamp(WARM),
                        pd.Timestamp(s) + pd.Timedelta(days=60))])
        bx = breadth_extra(bars)
        breads.append(bx[bx.trade_date >= max(pd.Timestamp(WARM),
                        pd.Timestamp(s) + pd.Timedelta(days=60))])
        del bars, status
        print("chunk done", s, e, flush=True)
    emo = pd.concat(emos).drop_duplicates("trade_date").sort_values(
        "trade_date")
    br = pd.concat(breads).drop_duplicates("trade_date").sort_values(
        "trade_date")
    emo.to_parquet(f"{OUT}/emotion_daily.parquet")
    br.to_parquet(f"{OUT}/breadth_daily.parquet")
    print("emotion days:", len(emo), emo.trade_date.min(), emo.trade_date.max())
    with connect(SETTINGS.research_service) as c:
        idx = pd.DataFrame(fetch_all(c, """
            SELECT index_id, trade_date, close, amount FROM market.index_daily_bar
            WHERE index_id IN ('SSE_COMPOSITE','SZSE_COMPONENT','CHINEXT','CSI_300')
              AND trade_date BETWEEN '2019-01-01' AND '2026-10-28' ORDER BY 1,2"""))
    idx["trade_date"] = pd.to_datetime(idx["trade_date"])
    idx.to_parquet(f"{OUT}/index_daily.parquet")
    print(idx.groupby("index_id").size())


if __name__ == "__main__":
    main()
