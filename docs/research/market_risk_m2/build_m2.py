"""M2 pipeline: historical episode library + three-module features/models."""
import sys
sys.path.insert(0, "../market_risk_m1")
import numpy as np
import pandas as pd
import build_m1
build_m1.D = "../market_risk_m1/data"
from build_m1 import (load_all, features, fwd_labels, cycles_from_dd,
                      logit_fit, logit_pred, ap, A_COLS, B_EXTRA)

IDXMAP = {"SSE_COMPOSITE": "sse", "SZSE_COMPONENT": "szse",
          "CHINEXT": "cyb", "CSI_300": "hs300"}
TR_END = "2023-12-31"


def px_full():
    """Index closes 2014-07..2026-10."""
    a = pd.read_parquet("index_2014_2018.parquet")
    b = pd.read_parquet("../market_risk_m1/data/index_daily.parquet")
    d = pd.concat([a, b]).drop_duplicates(["index_id", "trade_date"])
    d["trade_date"] = pd.to_datetime(d["trade_date"])
    d["close"] = d["close"].astype(float)
    px = d.pivot(index="trade_date", columns="index_id",
                 values="close").rename(columns=IDXMAP)
    aa = pd.read_csv("../etf_flow_poc02/data/index_daily.csv",
                     parse_dates=["date"])
    px["alla"] = aa.set_index("date")["all_a"].reindex(px.index).ffill()
    return px.sort_index()


def episodes_table(px):
    """Level-B episodes per index + systemic merge by overlap."""
    rows = []
    for k in ["sse", "szse", "cyb", "alla"]:
        p = px[k].ffill()
        dd = p / p.rolling(120, min_periods=30).max() - 1
        for c in cycles_from_dd(dd):
            seg = dd.iloc[c["start_i"]:c["end_i"] + 1]
            rows.append({"obj": k, "cycle_id": c["cycle_id"],
                "start": c["first_cross"], "end": c["end"],
                "trough": seg.idxmin(), "max_dd": round(float(seg.min()), 4),
                "status": c["status"],
                "tier": "full" if c["first_cross"] >= pd.Timestamp("2020-01-01")
                        else "price_only"})
    ep = pd.DataFrame(rows).sort_values("start")
    # systemic merge: greedy overlap on (start,end)
    ep["sys_id"] = ""
    sid = 0
    for obj in ep.obj.unique():
        pass
    used = set()
    for i, r in ep.iterrows():
        if i in used:
            continue
        grp = ep[(ep.start <= r["end"]) & (ep.end >= r["start"])
                 & (ep.obj != r.obj) | (ep.index == i)]
        grp = grp[~grp.index.isin(used)]
        ep.loc[grp.index, "sys_id"] = f"S{sid:02d}"
        used |= set(grp.index)
        sid += 1
    return ep


def mcclellan(emo):
    na = emo.up_count - emo.down_count
    osc = na.ewm(span=19, adjust=False).mean() - \
          na.ewm(span=39, adjust=False).mean()
    return pd.DataFrame({"mcc_osc": osc,
                         "mcc_sum": osc.cumsum()}, index=emo.index)


def main():
    px = px_full()
    ep = episodes_table(px)
    ep.to_csv("HISTORICAL_RISK_EPISODES.csv", index=False)
    sys_rows = ep.groupby("sys_id").agg(
        objs=("obj", lambda s: "+".join(sorted(s))),
        start=("start", "min"), end=("end", "max"),
        max_dd=("max_dd", "min"), n_idx=("obj", "size"),
        status=("status", "first"))
    sys_rows.to_csv("SYSTEMIC_RISK_EPISODES.csv")
    ep[["sys_id", "obj", "cycle_id"]].to_csv("INDEX_EPISODE_MAPPING.csv",
                                            index=False)
    print("episodes:", ep.groupby("obj").size().to_dict())
    print("systemic:", len(sys_rows),
          "| 2020+:", (ep.tier == "full").sum())
    # feature table = M1 features + mcclellan + g1 fixed breadth
    emo, br, _ = load_all()
    F = features(emo, br, px)
    F = F.join(mcclellan(emo.reindex(F.index)))
    F.to_parquet("M2_TEMPORAL_FEATURES.parquet")
    print("features:", F.shape)


if __name__ == "__main__":
    main()
