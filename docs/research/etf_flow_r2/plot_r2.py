"""R2 seven PNGs + data for interactive HTML."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np, json

plt.rcParams["font.family"] = "Hiragino Sans GB"
plt.rcParams["axes.unicode_minus"] = False
PE = pd.read_csv("POLICY_EVENTS.csv")
EV_D = pd.to_datetime(PE[PE.category.str.startswith("official")].event_date)


def f(g):
    d = pd.read_parquet(f"data/factors_{g}.parquet")
    d.index = pd.to_datetime(d.index)
    return d


g2 = f("G2_hs300_head")

# 01 normalized flow vs index (F5/20/40/60)
fig, ax = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
ax[0].plot(g2.index, g2.hs300 / g2.hs300.iloc[0], "k", lw=1)
ax[0].set_ylabel("沪深300")
for e in EV_D:
    ax[0].axvline(e, color="b", ls="--", lw=0.7, alpha=0.7)
for w, c in [(5, "lightcoral"), (20, "r"), (40, "darkred"), (60, "purple")]:
    ax[1].plot(g2.index, g2[f"F{w}"] * 100, lw=0.8, label=f"F{w}", color=c)
ax[1].axhline(0, color="gray", lw=0.5); ax[1].legend(ncol=4, fontsize=8)
ax[1].set_ylabel("窗口净流强度 %")
ax[0].set_title("01 规模归一化资金流 vs 沪深300 | 蓝虚线=官方政策事件")
fig.tight_layout(); fig.savefig("01_normalized_flow_vs_index.png", dpi=140)
plt.close(fig)

# 02 price -> flow response
l = pd.read_csv("LAG_RESPONSE_RESULTS.csv")
fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
for j, g in enumerate(["G2_hs300_head", "G1_all_equity"]):
    s = l[l.group == g]
    order = ["0-5", "6-10", "11-20", "21-40", "41-60"]
    dn = s[s.ret_bucket == "dn"].set_index("lag").loc[order]
    up = s[s.ret_bucket == "up"].set_index("lag").loc[order]
    x = np.arange(5)
    ax[j].bar(x - 0.2, dn.mean_fwd_i1_bp, 0.4, label="过去20日下跌后", color="r")
    ax[j].bar(x + 0.2, up.mean_fwd_i1_bp, 0.4, label="过去20日上涨后", color="g")
    ax[j].set_xticks(x); ax[j].set_xticklabels(order)
    ax[j].axhline(0, color="k", lw=0.6); ax[j].set_title(f"{g} 未来日均净申购强度(bp)", fontsize=9)
    ax[j].set_xlabel("滞后期"); ax[j].legend(fontsize=8)
fig.suptitle("02 价格→资金滞后响应：下跌后资金持续流入，上涨后流出")
fig.tight_layout(); fig.savefig("02_price_to_flow_lag.png", dpi=140)
plt.close(fig)

# 03 flow-event 120d response w/ CI vs controls (recompute curves from factors)
def paths(df, ev_pos, ctrl_pool_df, boot=200):
    seg_ret, seg_low = [], []
    for p in ev_pos:
        if p + 120 >= len(df):
            continue
        s = df._px.values[p + 1:p + 121] / df._px.values[p]
        seg_ret.append(s - 1)
        seg_low.append(s / np.maximum.accumulate(s) - 1)
    ctrl = df[~np.isin(np.arange(len(df)), ev_pos) & df.F20.notna()]
    cidx = ctrl_pool_df.index.get_indexer(ctrl.index)
    rng = np.random.default_rng(0)
    c_ret, c_low = [], []
    picks = rng.choice(cidx[cidx >= 0], size=min(300, len(cidx[cidx >= 0])), replace=False)
    for p in picks:
        if p + 120 < len(df):
            s = df._px.values[p + 1:p + 121] / df._px.values[p]
            c_ret.append(s - 1); c_low.append(s / np.maximum.accumulate(s) - 1)
    er = np.array(seg_ret); cr = np.array(c_ret)
    lo = np.nanpercentile(er, [5, 95], axis=0) if len(er) else None
    return np.nanmean(er, 0), np.nanmean(cr, 0), lo


fig, axes = plt.subplots(1, 2, figsize=(13, 5))
for j, (kind, lab) in enumerate([("inflow", "持续流入簇"), ("outflow", "持续流出簇")]):
    for g, c, ls in [("G2_hs300_head", "r", "-"), ("G1_all_equity", "b", "--")]:
        df = f(g)
        if kind == "inflow":
            m = (df.F20 >= 0.01) & (df.inshare20 >= 0.6)
        else:
            m = (df.F20 <= -0.01) & (df.outshare20 >= 0.6)
        pos = np.flatnonzero(m.fillna(False).values)
        # cluster
        cls = []
        for p in sorted(set(pos)):
            if not cls or p - cls[-1][-1] >= 20:
                cls.append([p])
            else:
                cls[-1].append(p)
        ev = [c2[0] for c2 in cls]
        bad = np.zeros(len(df), bool)
        for p in ev:
            bad[max(0, p - 40):p + 60] = True
        pool = df[~bad]
        er, cr, lo = paths(df, ev, pool)
        axes[j].plot(range(1, 121), er * 100, color=c, ls=ls, label=g)
        axes[j].plot(range(1, 121), cr * 100, color="gray", ls=ls, lw=0.9,
                     label="对照" if g == "G2_hs300_head" else None)
        if lo is not None:
            axes[j].fill_between(range(1, 121), lo[0] * 100, lo[1] * 100,
                                 color=c, alpha=0.12)
    axes[j].axhline(0, color="k", ls=":", lw=0.6)
    axes[j].set_title(f"{lab}后前向累计收益% (阴影=5-95分位)", fontsize=9)
    axes[j].set_xlabel("交易日 h"); axes[j].legend(fontsize=8)
fig.suptitle("03 资金事件后0-120日条件响应")
fig.tight_layout(); fig.savefig("03_flow_to_market_response_120d.png", dpi=140)
plt.close(fig)

# 04 policy regime comparison
pr = pd.read_csv("POLICY_REGIME_RESULTS.csv")
fig, ax = plt.subplots(figsize=(10, 5))
gs = pr.group.tolist(); x = np.arange(len(gs))
ax.bar(x - 0.2, pr.corr_on, 0.4, label="政策窗口期(事件后60日)", color="r")
ax.bar(x + 0.2, pr.corr_off, 0.4, label="非政策期", color="gray")
ax.set_xticks(x); ax.set_xticklabels(gs, rotation=30, fontsize=8)
ax.axhline(0, color="k", lw=0.6); ax.legend()
ax.set_title("04 corr(F20, 未来40日收益) 政策窗口 vs 非政策窗口")
fig.tight_layout(); fig.savefig("04_policy_regime_comparison.png", dpi=140)
plt.close(fig)

# 05 2024 case
fig, ax = plt.subplots(2, 1, figsize=(13, 8), sharex=True)
w = g2.loc["2024-01-01":"2024-12-31"]
ax[0].plot(w.index, w.hs300, "k", lw=1); ax[0].set_ylabel("沪深300")
ax[0].axvline(pd.Timestamp("2024-09-24"), color="b", ls="--", lw=1)
ax[0].annotate("924政策", xy=(pd.Timestamp("2024-09-24"), w.hs300.max()), fontsize=9, color="b")
ax[1].bar(w.index, w.flow, width=1, color=np.where(w.flow >= 0, "r", "g"))
axb = ax[1].twinx(); axb.plot(w.index, w.F20 * 100, "navy", lw=1.2, label="F20%")
axb.set_ylabel("F20 %"); axb.legend(fontsize=8)
ax[0].set_title("05 2024年案例：924前G2资金流改善已可观察（柱=日流量亿，蓝线=F20）")
fig.tight_layout(); fig.savefig("05_2024_924_case.png", dpi=140)
plt.close(fig)

# 06 2026 jan/jul case
fig, ax = plt.subplots(2, 1, figsize=(13, 8), sharex=True)
w = g2.loc["2025-10-01":"2026-10-27"]
ax[0].plot(w.index, w.hs300, "k", lw=1); ax[0].set_ylabel("沪深300")
ax[0].axvspan(pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-31"), color="g", alpha=0.2)
ax[0].axvspan(pd.Timestamp("2026-06-15"), pd.Timestamp("2026-07-31"), color="r", alpha=0.15)
ax[0].annotate("1月净赎回", xy=(pd.Timestamp("2026-01-15"), w.hs300.max()), fontsize=9)
ax[0].annotate("7月回补", xy=(pd.Timestamp("2026-07-20"), w.hs300.max() * 0.95), fontsize=9)
ax[1].bar(w.index, w.flow, width=1, color=np.where(w.flow >= 0, "r", "g"))
axb = ax[1].twinx(); axb.plot(w.index, w.F20 * 100, "navy", lw=1.2)
axb.set_ylabel("F20 %")
ax[0].set_title("06 2026年案例：1月撤离与7月回补（绿/橙带），F20口径")
fig.tight_layout(); fig.savefig("06_2026_january_july_case.png", dpi=140)
plt.close(fig)

# 07 tech subthemes normalized flow
fig, axes = plt.subplots(5, 1, figsize=(13, 12), sharex=True)
for a, (g, lab) in zip(axes, [("G5_semiconductor", "半导体"), ("G6_ai_compute", "AI算力"),
                              ("G7_robot", "机器人"), ("G8_softinfo", "软件信息"),
                              ("G4k_star", "科创(真实科创50)")]):
    d = f(g)
    px = d.idx_level / d.idx_level.dropna().iloc[0]
    a.plot(d.index, px, "k", lw=0.8)
    a2 = a.twinx()
    a2.fill_between(d.index, d.F20 * 100, 0, where=d.F20 >= 0, color="r", alpha=0.35)
    a2.fill_between(d.index, d.F20 * 100, 0, where=d.F20 < 0, color="g", alpha=0.35)
    a.set_ylabel(lab, fontsize=9)
    a.axvspan(pd.Timestamp("2026-06-01"), pd.Timestamp("2026-08-31"), color="orange", alpha=0.15)
axes[0].set_title("07 科技子主题 F20归一化资金流(填充) vs 板块指数(黑) | G5-8为代理指数 橙带=2026.6-8")
fig.tight_layout(); fig.savefig("07_technology_flow_intensity.png", dpi=140)
plt.close(fig)
print("7 pngs done")
