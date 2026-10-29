"""R3.1 PIT cycle engine + statistics. Only day-t information enters features."""
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "../etf_flow_r1")
from analyze_r1 import clusters  # noqa

R21D = "../etf_flow_r21/data"
GROUPS = ["G1_all_equity", "G2_hs300_head", "G9_sse50_head", "G3_other_broad",
          "G4k_star", "G5_semiconductor", "G6_ai_compute", "G7_robot",
          "G8_softinfo"]
FWIN = [20, 40, 60, 120]
THS = [.10, .20, .35, .50]


def engine(df, lookback=120):
    """Online flow-cycle engine. Returns per-day PIT fields + cycle registry."""
    flow = df.flow.fillna(0).values
    B = np.cumsum(flow)
    n = len(df)
    s20 = pd.Series(flow).rolling(20).sum().fillna(0).values
    out20 = df.outshare20.fillna(0).values
    f20 = df.F20.fillna(0).values
    aum = df.aum.ffill().fillna(0).values
    acc5 = (pd.Series(flow).rolling(5).sum() / df.aum.replace(
        0, np.nan).ffill()).fillna(0).values
    acc20 = s20 / np.where(aum > 0, aum, np.nan)
    acc20 = np.nan_to_num(acc20)
    v5 = pd.Series(flow).rolling(5).sum().fillna(0).values / 5
    aum_safe = np.where(aum > 0, aum, np.nanmax(aum))
    vel5 = v5 / aum_safe            # pct of AUM per day
    vel20 = s20 / 20 / aum_safe
    vel_prev = pd.Series(vel20).shift(20).fillna(0).values
    accel = vel5 - vel_prev
    state = ["NEUTRAL"] * n
    cyc = [""] * n
    depth = np.full(n, np.nan)
    ddur = np.zeros(n)
    eelap = np.zeros(n)
    cycles, act, streak = [], None, 0
    for i in range(n):
        cond = s20[i] < 0 and out20[i] >= 0.55
        streak = streak + 1 if cond else 0
        if act is None:
            if streak >= 10:
                lo = max(0, i - lookback)
                s = lo + int(np.argmax(B[lo:i + 1]))
                act = {"id": f"C{len(cycles):02d}", "s": s, "open_i": i,
                       "B0": B[s], "aum0": (aum[s - 1] if s > 0 else aum[0]),
                       "detected": df.index[i], "econ": df.index[s]}
        if act is not None:
            cyc[i] = act["id"]
            d = max(0., act["B0"] - B[i]) / max(act["aum0"], 1e-9)
            depth[i] = d
            ddur[i] = i - act["open_i"]
            eelap[i] = i - act["s"]
            if vel20[i] > 0 and f20[i] > 0:
                state[i] = "REACCUMULATING"
            elif abs(vel20[i]) < 0.0005:
                state[i] = "FLOW_STABILIZING"
            elif vel20[i] < 0 and accel[i] > 0:
                state[i] = "WITHDRAWAL_DECELERATING"
            elif vel20[i] < 0:
                state[i] = "WITHDRAWING"
            else:
                state[i] = "FLOW_STABILIZING"
            if B[i] >= act["B0"]:
                act["end_i"] = i
                act["status"] = "CLOSED"
                cycles.append(act)
                act = None
    if act is not None:
        act["end_i"] = n - 1
        act["status"] = "OPEN"
        cycles.append(act)
    out = df.copy()
    out["B"] = B
    out["pcyc"] = cyc
    out["pstate"] = state
    out["pdepth"] = depth
    out["ddur"] = ddur
    out["eelap"] = eelap
    out["vel5"] = vel5 * 100       # %/day
    out["vel20"] = vel20 * 100
    out["accel_v"] = accel * 100
    return out, cycles


def first_touch(d, cycs):
    rows = []
    for c in cycs:
        for th in THS:
            seg = d.iloc[c["open_i"]:c["end_i"] + 1]
            hit = np.flatnonzero((seg.pdepth >= th).values)
            if not len(hit):
                continue
            i = c["open_i"] + int(hit[0])
            r = {"cycle_id": c["id"], "threshold": th,
                 "date": str(d.index[i])[:10],
                 "depth": round(d.pdepth.iloc[i], 4),
                 "ddur": int(d.ddur.iloc[i]),
                 "eelap": int(d.eelap.iloc[i]),
                 "vel5": round(d.vel5.iloc[i], 4),
                 "vel20": round(d.vel20.iloc[i], 4),
                 "accel": round(d.accel_v.iloc[i], 4),
                 "fstate": d.pstate.iloc[i],
                 "breadth": d.breadth_out.iloc[i]
                 if "breadth_out" in d else np.nan,
                 "idx_dd": round(float(
                     d.idx_level.iloc[i] /
                     d.idx_level.iloc[max(0, i - 119):i + 1].max() - 1), 4)}
            for w in FWIN:
                r[f"fwd_ret{w}"] = d[f"fwd_ret{w}"].iloc[i]
                r[f"fwd_mdd{w}"] = d[f"fwd_mdd{w}"].iloc[i]
                r[f"fwd_low{w}"] = d[f"fwd_low{w}"].iloc[i]
            rows.append(r)
    return rows


def replay_test(df):
    """Truncate at 3 dates; engine output at T-1 must match full run."""
    full, _ = engine(df)
    ok = True
    for T in [400, 900, 1400]:
        part, _ = engine(df.iloc[:T])
        for col in ["pcyc", "pstate", "pdepth", "ddur"]:
            a, b = full[col].iloc[:T].values, part[col].values
            if col == "pdepth":
                same = np.allclose(a, b, equal_nan=True)
            else:
                same = (a == b).all()
            ok &= same
    return ok


def main():
    all_d, all_ev, reg_rows = [], [], []
    for g in GROUPS:
        d = pd.read_parquet(f"{R21D}/factors_{g}.parquet")
        d.index = pd.to_datetime(d.index)
        assert replay_test(d), f"replay mismatch {g}"
        d2, cycs = engine(d)
        for c in cycs:
            reg_rows.append({"cycle_id": c["id"], "group": g,
                             "econ_start": str(c["econ"])[:10],
                             "detected": str(c["detected"])[:10],
                             "end_i": c["end_i"], "status": c["status"],
                             "aum0": c["aum0"]})
        ev = first_touch(d2, cycs)
        for r in ev:
            r["group"] = g
        all_ev += ev
        sub = d2[["pcyc", "pstate", "pdepth", "ddur", "eelap", "vel5",
                  "vel20", "accel_v", "flow", "aum", "F20", "outshare20",
                  "breadth_out", "idx_level"]].copy()
        sub["group"] = g
        sub.index = sub.index.strftime("%Y-%m-%d")
        all_d.append(sub.reset_index().rename(columns={"index": "date"}))
    pd.concat(all_d).to_csv("PIT_CYCLE_DAILY.csv", index=False)
    pd.DataFrame(reg_rows).to_csv("PIT_CYCLE_EVENTS.csv", index=False)
    ev = pd.DataFrame(all_ev)
    ev.to_csv("FIRST_TOUCH_EVENTS.csv", index=False)
    print("replay test: all groups PASS")
    print("events:", len(ev), "by threshold:",
          ev.groupby("threshold").size().to_dict())

    # ---- H1: first-touch by threshold (G2 primary, all pooled) ----
    h1 = []
    for th in THS:
        sub = ev[ev.threshold == th]
        row = {"th": th, "n": len(sub),
               "n_cycles": sub[["group", "cycle_id"]].drop_duplicates().shape[0]}
        for w in FWIN:
            row[f"mdd{w}"] = round(sub[f"fwd_mdd{w}"].mean(), 4)
            row[f"ret{w}"] = round(sub[f"fwd_ret{w}"].mean(), 4)
            row[f"p_dd10_{w}"] = round((sub[f"fwd_low{w}"] <= -0.10).mean(), 3)
        h1.append(row)
    g2 = pd.read_parquet(f"{R21D}/factors_G2_hs300_head.parquet")
    g2.index = pd.to_datetime(g2.index)
    row = {"th": "baseline_all", "n": len(g2)}
    for w in FWIN:
        row[f"mdd{w}"] = round(g2[f"fwd_mdd{w}"].mean(), 4)
        row[f"ret{w}"] = round(g2[f"fwd_ret{w}"].mean(), 4)
        row[f"p_dd10_{w}"] = round((g2[f"fwd_low{w}"] <= -0.10).mean(), 3)
    h1.append(row)
    h1df = pd.DataFrame(h1)

    # ---- H2: duration at event ----
    dur_rows = []
    ev_d = ev.dropna(subset=["fwd_mdd60"])
    for lab, m in [("ddur<30", ev_d.ddur < 30),
                   ("30<=ddur<90", (ev_d.ddur >= 30) & (ev_d.ddur < 90)),
                   ("ddur>=90", ev_d.ddur >= 90)]:
        s = ev_d[m]
        dur_rows.append({"band": lab, "n": len(s),
                         "depth_med": round(s.depth.median(), 3),
                         "mdd60": round(s.fwd_mdd60.mean(), 4),
                         "ret60": round(s.fwd_ret60.mean(), 4)})

    # ---- H3: accelerating vs stopped at deep depth ----
    deep = ev[ev.depth >= 0.35]
    h3 = []
    for lab, m in [("accel_neg", deep.vel5 < -0.001),
                   ("stopped", deep.vel5 >= -0.001)]:
        s = deep[m]
        h3.append({"state": lab, "n": len(s),
                   "mdd60": round(s.fwd_mdd60.mean(), 4),
                   "ret60": round(s.fwd_ret60.mean(), 4)})

    # ---- H5: reaccum events (PIT: F20>0 & state REACC first day) ----
    g2d = pd.concat(all_d)
    g2d["date"] = pd.to_datetime(g2d["date"])
    g2g = g2d[g2d.group == "G2_hs300_head"].set_index("date")
    re = g2g[(g2g.pstate == "REACCUMULATING") &
             (g2g.pstate.shift(1) != "REACCUMULATING")]
    re_j = re.join(g2[["fwd_mdd60", "fwd_ret60", "fwd_low60"]])
    h5 = {"n_reacc_starts": len(re_j),
          "mdd60": round(re_j.fwd_mdd60.mean(), 4),
          "ret60": round(re_j.fwd_ret60.mean(), 4),
          "p_dd10": round((re_j.fwd_low60 <= -0.10).mean(), 3)}

    # ---- A/B/C with embargo ----
    g2p = g2g.join(g2[["fwd_mdd60", "vol60", "ret_idx", "hs300"]],
                   rsuffix="_g")
    y = (g2p.fwd_mdd60 <= -0.10).astype(float)
    y[g2p.index > g2p.index[-60]] = np.nan
    Xp = np.c_[g2p.idx_level.rolling(20).apply(
        lambda a: a.iloc[-1] / a.max() - 1, raw=False).fillna(0).values,
        g2p.vol60.fillna(0).values]
    Xf = np.c_[g2p.pdepth.fillna(0).values, g2p.vel20.fillna(0).values,
               np.log1p(g2p.ddur.values), g2p.accel_v.fillna(0).values]
    Xc = np.c_[Xp, Xf]

    def logit(Xtr, ytr, Xte):
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
        w = np.zeros(Xtr.shape[1] + 1)
        Xb = np.c_[np.ones(len(Xtr)), (Xtr - mu) / sd]
        for _ in range(800):
            p = 1 / (1 + np.exp(-Xb @ w))
            w -= 0.05 * Xb.T @ (p - ytr) / len(ytr)
        return 1 / (1 + np.exp(-np.c_[np.ones(len(Xte)),
                                     (Xte - mu) / sd] @ w))

    vs = g2p.index.searchsorted(pd.Timestamp("2024-01-01"))
    trm = np.zeros(len(g2p), bool)
    trm[:vs - 60] = True
    trm &= ~np.isnan(y.values) & (g2p.index > "2021-01-01")
    def ap(y_, s_):
        o = np.argsort(-s_); yv = np.asarray(y_)[o]
        tp = np.cumsum(yv); pr = tp / np.arange(1, len(yv) + 1)
        return float((pr * yv).sum() / max(1, yv.sum()))
    oos_rows = []
    for nm, X in [("A_price", Xp), ("B_flow4", Xf), ("C_both", Xc)]:
        pr = logit(X[trm], y[trm], X)
        for seg, m in [("valid_24_25",
                        (g2p.index >= "2024-01-01") & (g2p.index < "2026-01-01")),
                       ("touched_26", g2p.index >= "2026-01-01")]:
            sel = np.asarray(m) & ~np.isnan(y.values)
            if sel.sum() < 20:
                continue
            yv, pv = y[sel], pr[sel]
            oos_rows.append({"model": nm, "seg": seg, "n": int(sel.sum()),
                "ap": round(ap(yv, pv), 3),
                "brier": round(float(np.mean((pv - yv) ** 2)), 4)})
    oosdf = pd.DataFrame(oos_rows)

    # merge all H results
    out_rows = [{"sec": "H1", **r} for r in h1]
    pd.DataFrame(out_rows).to_csv("H1_H6_PIT_RESULTS.csv", index=False)
    pd.DataFrame(dur_rows + [{"band": "H3_" + r["state"], "n": r["n"],
                 "mdd60": r["mdd60"], "ret60": r["ret60"]} for r in h3]
                 + [{"band": "H5_reacc", "n": h5["n_reacc_starts"],
                     "mdd60": h5["mdd60"], "ret60": h5["ret60"],
                     "p_dd10": h5["p_dd10"]}]).to_csv(
        "PIT_DIM_RESULTS.csv", index=False)
    oosdf.to_csv("PRICE_BASELINE_COMPARISON.csv", index=False)
    oosdf.to_csv("OOS_VALIDATION.csv", index=False)
    print(h1df.to_string(index=False))
    print(pd.DataFrame(dur_rows).to_string(index=False))
    print(pd.DataFrame(h3).to_string(index=False))
    print("H5:", h5)
    print(oosdf.to_string(index=False))

    # ---- 2026 monthly PIT ledger ----
    a06 = [c for c in reg_rows if c["group"] == "G2_hs300_head"
           and c["status"] == "OPEN"
           and str(c["detected"]) < "2026"][0]
    d26 = g2g["2026-01-01":]
    mon = []
    for m, sub in d26.groupby(d26.index.month):
        t = sub.index[-1]
        r = {"month": m, "net_flow": round(sub.flow.sum(), 1),
             "depth_pct": round(sub.pdepth.iloc[-1] * 100, 1),
             "ddur": int(sub.ddur.iloc[-1]),
             "eelap": int(sub.eelap.iloc[-1]),
             "vel5": round(sub.vel5.iloc[-1], 3),
             "vel20": round(sub.vel20.iloc[-1], 3),
             "fstate": sub.pstate.iloc[-1],
             "idx_dd": round(float(g2.idx_level.loc[t] /
                g2.idx_level.loc[:t].rolling(120, min_periods=20).max()
                .iloc[-1] - 1), 3)}
        r["cum_wd_yi"] = round((sub.pdepth.iloc[-1]) * a06["aum0"], 0)
        mon.append(r)
    pd.DataFrame(mon).to_csv("2026_MONTHLY_PIT_LEDGER.csv", index=False)
    print(pd.DataFrame(mon).to_string(index=False))
    print("done")


if __name__ == "__main__":
    main()
