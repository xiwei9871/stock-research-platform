"""R3 capital withdrawal cycle research. Flow-only cycle detection
(frozen in CYCLE_DEFINITION.md); price used only for evaluation."""
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "../etf_flow_r1")
R21D = "../etf_flow_r21/data"
GROUPS = ["G1_all_equity", "G2_hs300_head", "G9_sse50_head", "G3_other_broad",
          "G4k_star", "G5_semiconductor", "G6_ai_compute", "G7_robot",
          "G8_softinfo"]
DEPTH_BINS = [0, .10, .20, .35, .50, np.inf]
FWIN = [20, 40, 60, 120]


def load_groups():
    g = {}
    for k in GROUPS:
        d = pd.read_parquet(f"{R21D}/factors_{k}.parquet")
        d.index = pd.to_datetime(d.index)
        g[k] = d
    return g


def flow_cycles_A(df, lookback=120):
    """Balance-drawdown cycles (Algorithm A)."""
    flow = df.flow.fillna(0).values
    B = np.cumsum(flow)
    out = df.outshare20.fillna(0).values
    s20 = pd.Series(flow).rolling(20).sum().fillna(0).values
    f20 = df.F20.fillna(0).values
    acc = df.accel.fillna(0).values
    aum_safe = df.aum.replace(0, np.nan).ffill().fillna(df.aum.max())
    v20 = s20 / aum_safe.values
    state = ["NEUTRAL"] * len(df)
    cyc_id = [""] * len(df)
    cycles = []
    confirm = 0
    i = 0
    n = len(df)
    while i < n:
        cond = s20[i] < 0 and out[i] >= 0.55
        confirm = confirm + 1 if cond else 0
        if confirm >= 10:
            # confirmed at i; cycle start = argmax B over [i-120, i]
            lo = max(0, i - lookback)
            s = lo + int(np.argmax(B[lo:i + 1]))
            aum0 = df.aum.iloc[max(0, s - 1)] if s > 0 else df.aum.iloc[0]
            # advance until B recovers
            j = i
            while j < n and B[j] < B[s]:
                j += 1
            end = j if j < n else n - 1
            depth = np.maximum(0, B[s] - np.minimum.accumulate(
                np.concatenate([B[s:end + 1]])))
            cycles.append({"cycle_id": f"A{len(cycles):02d}", "i_s": s,
                           "i_open": i, "i_end": end,
                           "start": df.index[s], "open_confirm": df.index[i],
                           "end_live": df.index[end] if j < n else "",
                           "status": "CLOSED" if j < n else "OPEN",
                           "aum0": aum0,
                           "depth_max": float((B[s] - B[s:end + 1].min())
                                              / max(aum0, 1e-9)),
                           "amt_max": float(B[s] - B[s:end + 1].min()),
                           "dur_days": end - s})
            for k in range(s, end + 1):
                cyc_id[k] = cycles[-1]["cycle_id"]
                dpt = max(0., B[s] - B[k]) / max(aum0, 1e-9)
                if v20[k] > 0 and f20[k] > 0:
                    st = "REACCUMULATING"
                elif abs(v20[k]) < 0.0005:
                    st = "FLOW_STABILIZING"
                elif v20[k] < 0 and acc[k] > 0:
                    st = "WITHDRAWAL_DECELERATING"
                elif v20[k] < 0:
                    st = "WITHDRAWING"
                else:
                    st = "FLOW_STABILIZING"
                state[k] = st
            i = max(j, i + 1)
        else:
            i += 1
    df2 = df.copy()
    df2["fcycle"] = cyc_id
    df2["fstate"] = state
    df2["B"] = B
    return df2, cycles


def milestones(df2, cyc):
    """First-touch dates of depth bins + per-day depth within cycle."""
    s, e, aum0 = cyc["i_s"], cyc["i_end"], cyc["aum0"]
    dpt = np.maximum(0., cyc["B0"] - df2.B.values[s:e + 1]) / max(aum0, 1e-9)
    ms = {}
    for th in [.10, .20, .35, .50]:
        hit = np.flatnonzero(dpt >= th)
        ms[th] = s + int(hit[0]) if len(hit) else None
    return dpt, ms


def main():
    G = load_groups()
    cyc_rows, daily_rows = [], []
    for gname, df in G.items():
        df2, cycs = flow_cycles_A(df)
        for c in cycs:
            c["B0"] = df2.B.values[c["i_s"]]
            dpt, ms = milestones(df2, c)
            df2.loc[df2.index[c["i_s"]:c["i_end"] + 1], "depth"] = dpt
            row = {k: c[k] for k in ["cycle_id", "start", "open_confirm",
                                     "end_live", "status", "depth_max",
                                     "amt_max", "dur_days", "aum0"]}
            row["group"] = gname
            for th, v in ms.items():
                row[f"d{int(th*100)}_date"] = (str(df.index[v])[:10]
                                              if v is not None else "")
            # fwd risk at open_confirm
            o = c["i_open"]
            for w in FWIN:
                row[f"fwd_ret{w}"] = df2[f"fwd_ret{w}"].iloc[o]
                row[f"fwd_mdd{w}"] = df2[f"fwd_mdd{w}"].iloc[o]
            # state shares
            seg = df2.iloc[c["i_s"]:c["i_end"] + 1]
            row["pct_withdrawing"] = (seg.fstate == "WITHDRAWING").mean()
            row["pct_reacc"] = (seg.fstate == "REACCUMULATING").mean()
            row["breadth_med"] = seg.breadth_out.median()
            # price at cycle start
            row["px_dd_at_start"] = round(
                seg.idx_level.iloc[0] / seg.idx_level.rolling(
                    120, min_periods=20).max().iloc[0] - 1, 4)
            cyc_rows.append(row)
        sub = df2[["fcycle", "fstate", "flow", "aum", "F20", "vel20"
                   if "vel20" in df2 else "F20", "accel", "breadth_out",
                   "outshare20", "idx_level", "policy_on"]].copy()
        sub["depth"] = df2.depth if "depth" in df2 else np.nan
        sub["group"] = gname
        sub.index = sub.index.strftime("%Y-%m-%d")
        daily_rows.append(sub.reset_index().rename(columns={"index": "date"}))
    pd.DataFrame(cyc_rows).to_csv("FUND_FLOW_CYCLES.csv", index=False)
    pd.concat(daily_rows).to_csv("FUND_FLOW_CYCLE_DAILY.csv", index=False)
    print(pd.DataFrame(cyc_rows)[
        ["cycle_id", "group", "start", "end_live", "status",
         "depth_max", "dur_days", "fwd_ret60", "fwd_mdd60"]].to_string(index=False))


if __name__ == "__main__":
    main()
