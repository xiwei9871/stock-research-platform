"""R3 statistics: depth/duration/velocity/breadth vs fwd risk, dual clock,
rotation, failed cases, monthly 2026 ledger, OOS."""
import numpy as np
import pandas as pd

cyc = pd.read_csv("FUND_FLOW_CYCLES.csv")
daily = pd.read_csv("FUND_FLOW_CYCLE_DAILY.csv", parse_dates=["date"])
daily = daily.rename(columns={"date": "date"})
G2D = "../etf_flow_r21/data"
FWIN = [20, 40, 60, 120]

g2 = pd.read_parquet(f"{G2D}/factors_G2_hs300_head.parquet")
g2.index = pd.to_datetime(g2.index)
dd = pd.read_csv("FUND_FLOW_CYCLE_DAILY.csv", parse_dates=["date"])
dd = dd.rename(columns={"date": "date"})

# depth>100% flag + current-AUM sensitivity
cyc["depth_flag"] = np.where(cyc.depth_max > 1.0, "DEPTH_GT_100",
                    np.where(cyc.aum0 < cyc.aum0.median() * 0.3,
                             "DENOM_SMALL", "OK"))
cyc["depth_max_pctAUM_cur"] = np.nan
for i, r in cyc.iterrows():
    g = pd.read_parquet(f"{G2D}/factors_{r.group}.parquet")
    g.index = pd.to_datetime(g.index)
    seg = g.loc[pd.Timestamp(r.start):]
    aum_end = g.aum.loc[:pd.Timestamp(r.end_live) if pd.notna(r.end_live)
                        and r.end_live else g.index[-1]].iloc[-1]
    cyc.loc[i, "depth_max_pctAUM_cur"] = r.amt_max / max(aum_end, 1e-9)
cyc.to_csv("FUND_FLOW_CYCLES.csv", index=False)

# ---------- H1: depth bins -> fwd risk (G2 primary, all groups pool) ----------
rows = []
cyc["depth_bin"] = pd.cut(cyc.depth_max.clip(upper=1.0),
                        [0, .10, .20, .35, .50, 1.001],
                        labels=["0-10", "10-20", "20-35", "35-50", ">50"])
for b, sub in cyc.groupby("depth_bin", observed=True):
    row = {"bin": str(b), "n_cycles": len(sub)}
    for w in FWIN:
        row[f"mdd{w}"] = round(sub[f"fwd_mdd{w}"].mean(), 4)
        row[f"ret{w}"] = round(sub[f"fwd_ret{w}"].mean(), 4)
        row[f"p_dd10_{w}"] = round((sub[f"fwd_mdd{w}"] <= -0.10).mean(), 3)
    rows.append(row)
# baseline: all days not in any withdrawal cycle
g2d = dd[dd.group == "G2_hs300_head"].set_index("date")
base = g2[~g2.index.isin(g2d[g2d.fcycle.notna()].index)]
row = {"bin": "baseline(no cycle)", "n_cycles": len(base)}
for w in FWIN:
    row[f"mdd{w}"] = round(base[f"fwd_mdd{w}"].mean(), 4)
    row[f"ret{w}"] = round(base[f"fwd_ret{w}"].mean(), 4)
    row[f"p_dd10_{w}"] = round((base[f"fwd_mdd{w}"] <= -0.10).mean(), 3)
rows.append(row)
pd.DataFrame(rows).to_csv("DEPTH_DURATION_RISK_RESULTS.csv", index=False)

# ---------- H2: duration given depth ----------
mid = cyc[cyc.depth_max >= 0.10]
dur_rows = []
for lab, sub in [("dur<90d", mid[mid.dur_days < 90]),
                 ("dur>=90d", mid[mid.dur_days >= 90])]:
    r = {"group": lab, "n": len(sub)}
    for w in FWIN:
        r[f"mdd{w}"] = round(sub[f"fwd_mdd{w}"].mean(), 4)
    dur_rows.append(r)
pd.DataFrame(dur_rows).to_csv("VELOCITY_BREADTH_RESULTS.csv", index=False)

# ---------- H3: accel vs decel inside cycles (G2 daily) ----------
inc = g2d[g2d.fstate.isin(["WITHDRAWING", "WITHDRAWAL_DECELERATING"])]
va = inc.assign(dec=inc.fstate == "WITHDRAWAL_DECELERATING")
vr = []
for lab, sub in [("decelerating", va[va.dec]), ("accelerating", va[~va.dec])]:
    j = sub.join(g2[["fwd_mdd60", "fwd_ret60"]])
    vr.append({"state": lab, "n": len(sub),
               "mdd60": round(j.fwd_mdd60.mean(), 4),
               "ret60": round(j.fwd_ret60.mean(), 4)})
print(pd.DataFrame(vr).to_string(index=False))

# ---------- H4: breadth (all-equity group) ----------
g1d = dd[dd.group == "G1_all_equity"].set_index("date")
g1d = g1d[g1d.fcycle.notna() & g1d.breadth_out.notna()]
bmed = g1d.breadth_out.median()
br = []
g1 = pd.read_parquet(f"{G2D}/factors_G1_all_equity.parquet")
g1.index = pd.to_datetime(g1.index)
for lab, m in [("high_breadth", g1d.breadth_out > bmed),
               ("low_breadth", g1d.breadth_out <= bmed)]:
    sub = g1d[m].join(g1[["fwd_mdd60", "fwd_ret60"]])
    br.append({"breadth": lab, "n": len(sub),
               "mdd60": round(sub.fwd_mdd60.mean(), 4),
               "ret60": round(sub.fwd_ret60.mean(), 4)})
pd.DataFrame(br).to_csv("VELOCITY_BREADTH_RESULTS.csv",
                        index=False, mode="a", header=False)

# ---------- H5: cycle close -> fwd risk ----------
close = cyc[cyc.status == "CLOSED"]
endr = []
for w in FWIN:
    endr.append({"window": w, "n": len(close)})
# also REACCUMULATING days inside cycles (G2)
re = g2d[g2d.fstate == "REACCUMULATING"]
re_f = g2.loc[re.index.intersection(g2.index)]
h5 = {"reacc_days": len(re),
      "mdd60": round(re_f.fwd_mdd60.mean(), 4),
      "ret60": round(re_f.fwd_ret60.mean(), 4),
      "base_mdd60": round(base.fwd_mdd60.mean(), 4)}

# ---------- H6: rotation (G2 outflow days vs other groups' flow) ----------
rot = []
g2_flow = g2.flow
for g in ["G1_all_equity", "G3_other_broad", "G9_sse50_head", "G4k_star",
          "G5_semiconductor", "G6_ai_compute", "G7_robot", "G8_softinfo"]:
    o = pd.read_parquet(f"{G2D}/factors_{g}.parquet")
    o.index = pd.to_datetime(o.index)
    j = pd.concat([g2_flow.rename("x"), o.flow.rename("y")], axis=1).dropna()
    out_days = j[j.x < 0]
    rot.append({"vs": g,
                "corr_all": round(j.x.corr(j.y), 3),
                "corr_G2_outflow_days": round(out_days.x.corr(out_days.y), 3),
                "G2_out_others_in_share": round((out_days.y > 0).mean(), 3)})
pd.DataFrame(rot).to_csv("FLOW_ROTATION.csv", index=False)

# ---------- dual clock ----------
clk = []
ddser = (g2.idx_level / g2.idx_level.rolling(120, min_periods=20).max() - 1)
for _, r in cyc[cyc.group == "G2_hs300_head"].iterrows():
    s = pd.Timestamp(r.start)
    # price dd10 onset after cycle start
    after = ddser[s:]
    dd10 = after[after <= -0.10]
    oi = dd10.index[0] if len(dd10) else None
    clk.append({"cycle": r.cycle_id, "start": str(s)[:10],
                "depth_max": r.depth_max, "status": r.status,
                "px_dd_at_start": round(float(ddser.loc[s]), 4),
                "dd10_onset": str(oi)[:10] if oi is not None else "",
                "flow_lead_days": (oi - s).days if oi is not None else np.nan,
                "px_dd_at_depth_max": round(float(ddser.loc[
                    g2.index[ddser.loc[s:].idxmin() == ddser.loc[s:].idxmin()].index[0]
                    ]) if False else float(ddser.loc[s:].min()), 4)})
    # price dd when depth hit 20/35/50
    for th in [10, 20, 35, 50]:
        dcol = r.get(f"d{th}_date")
        if isinstance(dcol, str) and dcol:
            clk[-1][f"px_dd_at_d{th}"] = round(float(ddser.loc[dcol]), 4)
pd.DataFrame(clk).to_csv("FLOW_PRICE_LEAD_LAG.csv", index=False)

# ---------- failed cases (fixed rules) ----------
fc = []
for _, r in cyc.iterrows():
    if r.depth_max >= 0.20 and r.fwd_ret60 > 0.05:
        fc.append({"type": "deep_withdrawal_mkt_up", "cycle": r.cycle_id,
                   "group": r.group, "start": r.start, "depth": r.depth_max,
                   "fwd_ret60": r.fwd_ret60})
    if r.depth_max >= 0.35 and r.fwd_mdd60 > -0.08:
        fc.append({"type": "deep_withdrawal_no_dd", "cycle": r.cycle_id,
                   "group": r.group, "start": r.start, "depth": r.depth_max,
                   "fwd_mdd60": r.fwd_mdd60})
# accumulation + market down: REACC days fwd_mdd60 < -10%
acc_fail = re_f[re_f.fwd_mdd60 <= -0.10]
fc.append({"type": "reaccum_then_dd10", "cycle": "G2_REACC_days",
           "group": "G2_hs300_head", "start": f"{len(acc_fail)} days",
           "depth": np.nan, "fwd_ret60": np.nan})
pd.DataFrame(fc).to_csv("FAILED_CASES.csv", index=False)

# ---------- 2026 monthly ledger (G2) ----------
d26 = g2d["2026-01-01":"2026-10-27"]
a06 = cyc[(cyc.group == "G2_hs300_head") & (cyc.cycle_id == "A06")].iloc[0]
mon = []
for m, sub in d26.groupby(d26.index.month):
    cum_out = (a06.amt_max and (a06.amt_max -
               max(0, a06.amt_max - 0)))  # placeholder
    b_seg = g2.loc[sub.index]
    depth = float((a06.amt_max - (g2.B if "B" in g2 else 0)) if False else 0)
    mon.append({"month": m, "net_flow_yi": round(b_seg.flow.sum(), 1),
                "state_days": (sub.fstate == "WITHDRAWING").sum(),
                "F20_end": round(sub.F20.iloc[-1], 4)})
# proper cumulative depth to month end
bal = g2.flow.cumsum()
b0 = bal.loc[pd.Timestamp(a06.start)]
for r in mon:
    mend = d26[d26.index.month == r["month"]].index[-1]
    r["cum_withdraw_yi"] = round(b0 - bal.loc[mend], 1)
    r["cum_depth_pct"] = round((b0 - bal.loc[mend]) / a06.aum0 * 100, 1)
pd.DataFrame(mon).to_csv("CASE_A_2026_MONTHLY.csv", index=False)
print(pd.DataFrame(mon).to_string(index=False))

# ---------- OOS depth->risk ----------
oos = []
for lab, m in [("2020-23", cyc.start < "2024"), ("2024-25", (cyc.start >= "2024") & (cyc.start < "2026")), ("2026", cyc.start >= "2026")]:
    sub = cyc[m]
    oos.append({"seg": lab, "n": len(sub),
                "corr_depth_mdd60": round(sub.depth_max.corr(sub.fwd_mdd60), 3),
                "corr_depth_ret60": round(sub.depth_max.corr(sub.fwd_ret60), 3)})
pd.DataFrame(oos).to_csv("OOS_DEPTH_RELATION.csv", index=False)
print(pd.DataFrame(oos).to_string(index=False))
print("h5:", h5)
print("done r3b")
