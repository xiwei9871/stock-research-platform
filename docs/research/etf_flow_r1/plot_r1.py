"""Generate the five required R1 research PNGs from factor parquets."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

plt.rcParams["font.family"] = "Hiragino Sans GB"
plt.rcParams["axes.unicode_minus"] = False
P = "../etf_flow_poc02/data"
ix = pd.read_csv(f"{P}/index_daily.csv", index_col="date")
ix.index = pd.to_datetime(ix.index)


def f(g):
    d = pd.read_parquet(f"data/factors_{g}.parquet")
    d.index = pd.to_datetime(d.index)
    return d


# 01 broad ETF flow vs market
g2 = f("G2_hs300_head")
g1 = f("G1_all_equity")
fig, ax = plt.subplots(3, 1, figsize=(13, 9), sharex=True,
                       gridspec_kw={"height_ratios": [2, 1, 1]})
ax[0].plot(g2.index, (1 + g2.ret_mkt.fillna(0)).cumprod() / 0.99,
           color="k", lw=1, label="沪深300 (2020=1)")
ax[0].set_ylabel("指数净值"); ax[0].legend(loc="upper left")
ax[0].set_title("01 宽基ETF资金流 vs 沪深300 | G2头部300ETF")
ax[1].bar(g2.index, g2.flow, width=1, color=np.where(g2.flow >= 0, "r", "g"))
ax[1].set_ylabel("G2日净申购(亿)")
ax[2].plot(g2.index, g2.z20, color="navy", lw=0.8)
ax[2].axhline(-2, color="r", ls="--", lw=0.8); ax[2].axhline(2, color="r", ls="--", lw=0.8)
ax[2].axhline(0, color="gray", lw=0.5); ax[2].set_ylabel("z20强度")
fig.tight_layout(); fig.savefig("01_broad_etf_flow_vs_market.png", dpi=140); plt.close(fig)

# 02 forward drawdown after outflow events (G2 & G1_all)
ev = pd.read_csv("EVENT_STUDY_RESULTS.csv")
fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
for j, (g, t) in enumerate([("G2_hs300_head", "G2头部300ETF"),
                            ("G1_all_equity", "G1全部股票ETF")]):
    s = ev[(ev.kind == "H1_outflow") & (ev.group == g) & (ev.thr == "-2")]
    if not len(s):
        s = ev[(ev.kind == "H1_outflow") & (ev.group == g) & (ev.thr == -2.0)]
    s = ev[(ev.kind == "H1_outflow") & (ev.group == g)]
    s = s[s.thr.astype(str).str.startswith("-2") & ~s.thr.astype(str).str.contains("2.5")]
    x = np.arange(len(s))
    ax[j].bar(x - 0.2, s.ev_mdd_mean, 0.4, label="事件后", color="r")
    ax[j].bar(x + 0.2, s.ctrl_mdd_mean, 0.4, label="匹配对照", color="gray")
    ax[j].bar(x + 0.6, s.all_mdd_mean, 0.4, label="全样本", color="b", alpha=0.4)
    ax[j].set_xticks(x + 0.1); ax[j].set_xticklabels([f"{w}日" for w in s.window])
    ax[j].set_title(f"{t} 异常流出(z20<=-2, n={int(s.n_events.iloc[0])})后最大回撤")
    ax[j].axhline(-0.05, color="k", ls=":", lw=0.8); ax[j].legend(fontsize=8)
fig.tight_layout(); fig.savefig("02_flow_event_forward_drawdown.png", dpi=140); plt.close(fig)

# 03 reversal event study: index path around z5>=0 reversals (G2)
d = f("G2_hs300_head")
z20 = d.z20.values; i5 = d.i5.values; dates = d.index
evs = []
for t in range(80, len(dates)):
    win = z20[max(0, t - 10):t]
    if i5[t] >= 0 and np.isfinite(win).any() and np.nanmin(win) <= -1:
        if not evs or (dates[t] - evs[-1]).days >= 32:
            evs.append(dates[t])
px = (1 + d.ret_mkt.fillna(0)).cumprod()
paths = []
for e in evs:
    i = px.index.get_loc(e)
    if i - 20 >= 0 and i + 60 < len(px):
        paths.append(px.iloc[i - 20:i + 60].values / px.iloc[i])
paths = np.array(paths)
fig, ax = plt.subplots(figsize=(10, 5))
for p in paths:
    ax.plot(range(-20, 60), p, color="gray", alpha=0.25, lw=0.6)
ax.plot(range(-20, 60), np.nanmean(paths, 0), color="r", lw=2,
        label=f"均值 n={len(paths)}")
ax.axvline(0, color="k", ls="--", lw=0.8); ax.axhline(1, color="k", ls=":", lw=0.6)
ax.set_title("03 G2净流出转流入(z5>=0 反转)前后沪深300路径 | 事件点=0")
ax.set_xlabel("相对交易日"); ax.set_ylabel("指数相对值"); ax.legend()
fig.tight_layout(); fig.savefig("03_flow_reversal_event_study.png", dpi=140); plt.close(fig)

# 04 tech subthemes flow + index proxy
fig, axes = plt.subplots(5, 1, figsize=(13, 12), sharex=True)
names = [("G5_semiconductor", "半导体"), ("G6_ai_compute", "AI/算力"),
         ("G7_robot", "机器人"), ("G8_softinfo", "软件信息"), ("G4k_star", "科创")]
for a, (g, lab) in zip(axes, names):
    d = f(g)
    px = (1 + d.ret_idx.fillna(0)).cumprod()
    a.plot(d.index, px / px.dropna().iloc[0], color="k", lw=0.8)
    a2 = a.twinx()
    a2.bar(d.index, d.flow, width=1, color=np.where(d.flow >= 0, "r", "g"), alpha=0.5)
    a2.plot(d.index, d.z20, color="navy", lw=0.6, alpha=0.8)
    a2.axhline(-2, color="r", ls="--", lw=0.5)
    a.set_ylabel(f"{lab}\n指数", fontsize=9)
    a.axvspan(pd.Timestamp("2026-06-01"), pd.Timestamp("2026-08-31"),
              color="orange", alpha=0.15)
axes[0].set_title("04 科技子主题ETF资金流(柱)与z20(蓝线) vs 板块代理指数(黑线) | 橙带=2026.6-8")
fig.tight_layout(); fig.savefig("04_technology_etf_flow.png", dpi=140); plt.close(fig)

# 05 risk management comparison
g2d = f("G2_hs300_head")
ret = g2d.ret_mkt.fillna(0).values
px = (1 + ret).cumprod()
mom = g2d.ret_mkt.rolling(20).sum().values
ma = g2d._px.rolling(200).mean().values
z = g2d.z20.values
posB = ((mom > 0) & (g2d._px.values > ma)).astype(float)
posC = posB.copy()
for t in range(1, len(g2d)):
    if z[t - 1] <= -2:
        posC[t] = 0.0
    elif posB[t] == 1 and posC[t - 1] == 0:
        posC[t] = 1.0
posB = np.roll(posB, 1); posB[0] = 0
posC = np.roll(posC, 1); posC[0] = 0
COST = 0.0005
eqA = np.cumprod(1 + ret)
eqB = np.cumprod(1 + posB * ret - np.abs(np.diff(np.concatenate([[0], posB]))) * COST)
eqC = np.cumprod(1 + posC * ret - np.abs(np.diff(np.concatenate([[0], posC]))) * COST)
fig, ax = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                       gridspec_kw={"height_ratios": [2, 1]})
ax[0].plot(g2d.index, eqA, label="A 始终持有", color="gray")
ax[0].plot(g2d.index, eqB, label="B 价格风控(动量+MA200)", color="b")
ax[0].plot(g2d.index, eqC, label="C 价格+ETF资金流", color="r")
ax[0].set_title("05 风险管理模拟净值 | 标的=沪深300, T+1执行, 成本5bp")
ax[0].legend()
for a in ax[0:1]:
    pass
ax[1].plot(g2d.index, eqA / np.maximum.accumulate(eqA) - 1, color="gray", lw=0.8)
ax[1].plot(g2d.index, eqB / np.maximum.accumulate(eqB) - 1, color="b", lw=0.8)
ax[1].plot(g2d.index, eqC / np.maximum.accumulate(eqC) - 1, color="r", lw=0.8)
ax[1].set_ylabel("回撤")
fig.tight_layout(); fig.savefig("05_risk_management_comparison.png", dpi=140); plt.close(fig)
print("pngs done")
