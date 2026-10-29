import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt

cyc = pd.read_csv("FUND_FLOW_CYCLES.csv")
dd = pd.read_csv("FUND_FLOW_CYCLE_DAILY.csv", parse_dates=["date"])
g2d = dd[dd.group=="G2_hs300_head"].set_index("date")
g2 = pd.read_parquet("../etf_flow_r21/data/factors_G2_hs300_head.parquet")
g2.index = pd.to_datetime(g2.index)
bal = g2.flow.cumsum()
ddr = g2.idx_level/g2.idx_level.rolling(120,min_periods=20).max()-1
mon = pd.read_csv("CASE_A_2026_MONTHLY.csv")
dr = pd.read_csv("DEPTH_DURATION_RISK_RESULTS.csv")
rot = pd.read_csv("FLOW_ROTATION.csv")
clk = pd.read_csv("FLOW_PRICE_LEAD_LAG.csv")
SC = {"WITHDRAWING":"#ef9a9a","WITHDRAWAL_DECELERATING":"#ffe0b2",
      "FLOW_STABILIZING":"#fff9c4","REACCUMULATING":"#a5d6a7","NEUTRAL":"#f0f0f0"}

def shade(ax, d):
    prev, st = 0, d.fstate.iloc[0]
    for i, s in enumerate(d.fstate):
        if s != st or i == len(d)-1:
            if st != "NEUTRAL" and st in SC:
                ax.axvspan(d.index[prev], d.index[i-1], color=SC[st], alpha=.5, lw=0)
            prev, st = i, s

# 01 depth vs index
fig, ax = plt.subplots(3,1,figsize=(14,9),sharex=True,gridspec_kw={"height_ratios":[2,1,1]})
shade(ax[0], g2d)
ax[0].plot(g2.index, g2.idx_level, "k", lw=1); ax[0].set_ylabel("CSI300")
g2c = cyc[cyc.group=="G2_hs300_head"]
for _,r in g2c.iterrows():
    t = pd.Timestamp(r.start)
    if t in g2.index:
        ax[0].annotate(r.cycle_id, (t.to_pydatetime(),
                                    float(g2.idx_level.loc[t])), fontsize=7)
ax[1].plot(g2.index, bal, "tab:blue", lw=1); ax[1].set_ylabel("cum flow 亿")
ax[2].plot(g2d.index, g2d.depth*100, "tab:red", lw=1); ax[2].set_ylabel("depth %")
ax[2].set_ylim(0,110)
ax[0].set_title("Flow cycles (shaded) + index | mid: cumulative balance | bottom: withdrawal depth")
fig.tight_layout(); fig.savefig("01_capital_withdrawal_depth_vs_index.png",dpi=110); plt.close()

# 02 2026 timeline
d26 = g2d["2025-12":]; s26 = g2["2025-12":]
fig, ax = plt.subplots(3,1,figsize=(14,8),sharex=True)
shade(ax[0], d26)
ax[0].plot(s26.index, s26.idx_level, "k", lw=1.2)
axm = ax[1]; axm.bar(mon.month, mon.net_flow_yi, color=np.where(mon.net_flow_yi<0,"#c33","#2a7"))
axm.set_xticks(mon.month); axm.set_xticklabels([f"2026-{m:02d}" for m in mon.month], fontsize=8)
axm.set_ylabel("monthly net flow 亿")
ax[2].plot(d26.index, d26.depth*100, "tab:red", lw=1.2); ax[2].set_ylabel("cum depth %")
ax[0].set_title("2026 withdrawal timeline (flow states + monthly flow + cumulative depth)")
fig.tight_layout(); fig.savefig("02_2026_withdrawal_timeline.png",dpi=110); plt.close()

# 03 depth-duration heatmap (G2 cycles as scatter on depth x duration, color= fwd mdd60)
fig, ax = plt.subplots(1,2,figsize=(12,4.5))
c = cyc[cyc.depth_max<1.2].dropna(subset=["fwd_mdd60"])
sc = ax[0].scatter(c.depth_max*100, c.dur_days, c=-c.fwd_mdd60*100, cmap="RdYlGn_r", s=60, edgecolor="k", lw=.5)
for _,r in c.iterrows():
    if r.group=="G2_hs300_head": ax[0].annotate(r.cycle_id,(r.depth_max*100,r.dur_days),fontsize=7)
plt.colorbar(sc,ax=ax[0],label="fwd60 MDD %"); ax[0].set_xlabel("depth %"); ax[0].set_ylabel("duration days")
b = dr[dr.bin.str.contains("-")|dr.bin.str.contains(">")]
ax[1].bar(b.bin, -b.mdd60*100, color="tab:red", alpha=.7)
ax[1].axhline(-dr[dr.bin.str.contains("baseline")].mdd60.iloc[0]*100, ls="--", c="k", label="baseline")
ax[1].set_ylabel("mean fwd60 MDD %"); ax[1].legend(); ax[1].set_title("depth bin vs fwd risk")
fig.tight_layout(); fig.savefig("03_depth_duration_risk_heatmap.png",dpi=110); plt.close()

# 04 velocity & accel
fig, ax = plt.subplots(2,1,figsize=(14,7),sharex=True)
v = g2d.accel*10000
ax[0].plot(g2d.index, g2d.F20*100, "tab:blue", lw=.8, label="F20 %")
ax[0].plot(g2d.index, g2d.accel.rolling(10).mean()*100, "tab:orange", lw=.8, label="accel(10d avg)")
ax[0].axhline(0,c="gray",lw=.5); ax[0].legend(fontsize=8); shade(ax[0],g2d)
ax[1].plot(g2.index, g2.idx_level, "k", lw=1)
ax[0].set_title("withdrawal velocity & acceleration vs index")
fig.tight_layout(); fig.savefig("04_velocity_and_acceleration.png",dpi=110); plt.close()

# 05 breadth
fd = pd.read_parquet("../etf_flow_r1/data/fund_day.parquet")
uni = pd.read_csv("../etf_flow_r1/ETF_UNIVERSE_AND_GROUPS.csv", dtype={"fund_code":str})
f = fd[fd.fund_code.isin(set(uni.fund_code))].copy()
f["date"]=pd.to_datetime(f["date"])
f["omv"]=np.where(f.flow_use<0,f.mv,0)
br = f.groupby("date").agg(o=("omv","sum"),t=("mv","sum")); br["b"]=br.o/br.t
fig, ax = plt.subplots(2,1,figsize=(14,7),sharex=True)
ax[0].plot(br.index, br.b*100, "tab:purple", lw=.8); ax[0].set_ylabel("outflow AUM breadth %")
ax[1].plot(g2.index, g2.idx_level,"k",lw=1); shade(ax[1],g2d)
ax[0].set_title("all-equity ETF outflow breadth (AUM-weighted) vs index")
fig.tight_layout(); fig.savefig("05_etf_withdrawal_breadth.png",dpi=110); plt.close()

# 06 dual clock
fig, ax = plt.subplots(figsize=(13,5))
x = np.arange(len(clk))
ax.bar(x-0.2, clk.flow_lead_days, 0.4, label="flow cycle start -> price dd10 onset (days)", color="tab:blue")
ax.bar(x+0.2, -clk.px_dd_at_start*100, 0.4, label="price dd% at flow cycle start", color="tab:red")
ax.set_xticks(x, clk.cycle+" "+clk.start.str[:7], rotation=20, fontsize=8)
ax.legend(fontsize=8); ax.set_title("dual clock: flow cycles vs price drawdown (G2)")
fig.tight_layout(); fig.savefig("06_flow_cycle_vs_price_cycle.png",dpi=110); plt.close()

# 07 924 accumulation
seg = g2["2024-01":"2024-12"]; segd = g2d["2024-01":"2024-12"]
fig, ax = plt.subplots(2,1,figsize=(13,7),sharex=True)
ax[0].plot(seg.index, seg.idx_level,"k",lw=1.2); ax[0].axvline(pd.Timestamp("2024-09-24"),color="purple",ls="--")
ax[0].annotate("924",(pd.Timestamp("2024-09-24"),seg.idx_level.max()),fontsize=9); shade(ax[0],segd)
b24 = g2.flow.cumsum() - g2.flow.cumsum().loc["2024-01-02":].iloc[0]
ax[1].plot(b24["2024"].index, b24["2024"], "tab:blue", lw=1.2)
ax[1].set_ylabel("2024 cum flow 亿"); ax[0].set_title("2024 pre-924 accumulation")
fig.tight_layout(); fig.savefig("07_2024_924_accumulation.png",dpi=110); plt.close()

# 08 tech cycles
fig, ax = plt.subplots(2,1,figsize=(14,8),sharex=True)
for g in ["G5_semiconductor","G6_ai_compute","G7_robot","G8_softinfo","G4k_star"]:
    o = pd.read_parquet(f"../etf_flow_r21/data/factors_{g}.parquet"); o.index=pd.to_datetime(o.index)
    ax[0].plot(o.index, o.flow.cumsum()/o.aum.expanding().max()*100, lw=.8, label=g.split("_")[0])
ax[0].legend(fontsize=7,ncol=5); ax[0].set_ylabel("cum flow / max AUM %")
tc = cyc[cyc.group.str.startswith(("G5","G6","G7","G8","G4"))]
ax[1].bar(range(len(tc)), tc.depth_max*100, color="tab:red",alpha=.7)
ax[1].set_xticks(range(len(tc)), tc.group.str[:2]+tc.cycle_id, rotation=60, fontsize=7)
ax[1].set_ylabel("cycle depth %"); ax[1].axhline(100,ls="--",c="gray")
ax[0].set_title("technology ETF groups: cumulative flow (normalized) & cycle depths")
fig.tight_layout(); fig.savefig("08_technology_flow_cycles.png",dpi=110); plt.close()

# 09 success/failure
fc = pd.read_csv("FAILED_CASES.csv")
fig, ax = plt.subplots(1,2,figsize=(12,4.5))
ok = cyc[(cyc.depth_max>=0.2)&(cyc.fwd_mdd60<=-0.12)]
fa = cyc[(cyc.depth_max>=0.2)&(cyc.fwd_mdd60>-0.12)]
ax[0].bar(range(len(ok)), -ok.fwd_mdd60*100, color="tab:red",alpha=.7)
ax[0].set_title(f"depth>=20% & deep drawdown (n={len(ok)})"); ax[0].set_xticks(range(len(ok)),ok.group.str[:2]+ok.cycle_id,rotation=60,fontsize=7)
ax[1].bar(range(len(fa)), fa.fwd_ret60*100, color="tab:green",alpha=.7)
ax[1].set_title(f"depth>=20% but NO deep drawdown (n={len(fa)})")
ax[1].set_xticks(range(len(fa)),fa.group.str[:2]+fa.cycle_id,rotation=60,fontsize=7)
fig.tight_layout(); fig.savefig("09_success_failure_comparison.png",dpi=110); plt.close()
print("9 pngs done")
