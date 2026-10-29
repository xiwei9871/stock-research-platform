"""R1.1 flagship figures: 06 normalized flow vs index; 07 0-120d response
curves; refresh 01/02/05 under corrected methodology."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

plt.rcParams["font.family"] = "Hiragino Sans GB"
plt.rcParams["axes.unicode_minus"] = False


def f(g):
    d = pd.read_parquet(f"data/factors_{g}.parquet")
    d.index = pd.to_datetime(d.index)
    return d


# 06 normalized flow (F20 window intensity) vs index — G2, G1, G9
fig, axes = plt.subplots(3, 1, figsize=(13, 10), sharex=True)
for a, (g, lab) in zip(axes, [("G2_hs300_head", "G2头部沪深300ETF"),
                              ("G1_all_equity", "G1全部股票ETF"),
                              ("G9_sse50_head", "G9上证50ETF(510050)")]):
    d = f(g)
    px = d.idx_level / d.idx_level.dropna().iloc[0]
    a.plot(d.index, px, color="k", lw=0.9)
    a.set_ylabel("指数(归一)", fontsize=9)
    a2 = a.twinx()
    a2.fill_between(d.index, d.F20 * 100, 0,
                    where=d.F20 >= 0, color="r", alpha=0.35)
    a2.fill_between(d.index, d.F20 * 100, 0,
                    where=d.F20 < 0, color="g", alpha=0.35)
    a2.axhline(0, color="gray", lw=0.5)
    a2.set_ylabel("F20窗口净流强度 %", fontsize=9)
    a.set_title(f"{lab} | 黑线=指数, 红/绿=20日净申购/净赎回占期初规模%",
                fontsize=10)
    a.axvline(pd.Timestamp("2024-09-24"), color="b", ls="--", lw=0.8)
    a.axvspan(pd.Timestamp("2026-06-01"), pd.Timestamp("2026-08-31"),
              color="orange", alpha=0.15)
axes[0].annotate("924", xy=(pd.Timestamp("2024-09-24"), 1), fontsize=8,
                 color="b")
fig.suptitle("06 规模归一化资金流(F20)与指数历史叠加 | 蓝虚线=2024-09-24政策, 橙带=2026.6-8")
fig.tight_layout(); fig.savefig("06_normalized_flow_vs_index.png", dpi=140)
plt.close(fig)

# 07 response curves 0-120d: outflow & inflect clusters, G2 + G1
rc = pd.read_csv("RESPONSE_CURVES.csv")
fig, axes = plt.subplots(2, 3, figsize=(15, 8))
specs = [("outflow", "ev_ret", "ctrl_ret", "前向累计收益", 0),
         ("outflow", "ev_mdd", "ctrl_mdd", "前向峰谷最大回撤", 1),
         ("outflow", "ev_vol", None, "前向已实现波动率", 2)]
for j, (kind, ec, cc, lab, col) in enumerate(specs):
    for i, g in enumerate(["G2_hs300_head", "G1_all_equity"]):
        ax = axes[i, j]
        s = rc[(rc.group == g) & (rc.kind == kind)]
        ax.plot(s.h, s[ec] * 100, color="r", lw=1.5, label="流出事件簇")
        if cc:
            ax.plot(s.h, s[cc] * 100, color="gray", lw=1.2,
                    label="匹配对照")
        ax.axhline(0, color="k", ls=":", lw=0.6)
        ax.set_title(f"{g} {lab} (n簇={int(s.n_ev.max())})", fontsize=9)
        ax.set_xlabel("事件后交易日 h")
        if j == 0:
            ax.legend(fontsize=8)
# inflect row overlay on ret panel
for i, g in enumerate(["G2_hs300_head", "G1_all_equity"]):
    s = rc[(rc.group == g) & (rc.kind == "inflect_up")]
    axes[i, 0].plot(s.h, s.ev_ret * 100, color="b", lw=1.2, ls="--",
                    label="拐点事件")
    axes[i, 0].legend(fontsize=8)
fig.suptitle("07 资金事件后0-120交易日条件响应曲线(均值)")
fig.tight_layout(); fig.savefig("07_forward_120d_response.png", dpi=140)
plt.close(fig)

# refresh 01 G2 (4 funds now)
g2 = f("G2_hs300_head")
fig, ax = plt.subplots(3, 1, figsize=(13, 9), sharex=True,
                       gridspec_kw={"height_ratios": [2, 1, 1]})
ax[0].plot(g2.index, g2.hs300 / g2.hs300.iloc[0], color="k", lw=1)
ax[0].set_ylabel("沪深300(归一)")
ax[1].bar(g2.index, g2.flow, width=1, color=np.where(g2.flow >= 0, "r", "g"))
ax[1].set_ylabel("日净申购(亿)")
ax[2].plot(g2.index, g2.F20 * 100, color="navy", lw=0.8)
ax[2].axhline(-1, color="r", ls="--", lw=0.8); ax[2].axhline(1, color="r", ls="--", lw=0.8)
ax[2].axhline(0, color="gray", lw=0.5); ax[2].set_ylabel("F20 %")
ax[0].set_title("01 宽基ETF资金流 vs 沪深300 | G2=4只纯沪深300ETF(510050已移出)")
fig.tight_layout(); fig.savefig("01_broad_etf_flow_vs_market.png", dpi=140)
plt.close(fig)

# refresh 05 backtest with corrected positions
ret = g2.ret_mkt.fillna(0).values
px = g2._px.values
mom = g2.ret_mkt.rolling(20).sum().values
ma = g2._px.rolling(200).mean().values
sig = ((g2.F20 <= -0.01) & (g2.outshare20 >= 0.6)).fillna(False).values
posB_raw = ((mom > 0) & (px > ma)).astype(float)
posC_raw = np.zeros(len(g2)); posC_raw[0] = posB_raw[0]
for t in range(1, len(g2)):
    if sig[t]:
        posC_raw[t] = 0.0
    elif posB_raw[t] == 1:
        posC_raw[t] = 1.0
    else:
        posC_raw[t] = posC_raw[t - 1]
posB = np.roll(posB_raw, 1); posB[0] = 0
posC = np.roll(posC_raw, 1); posC[0] = 0
COST = 0.0005
eq = lambda p: np.cumprod(1 + p * ret - np.abs(np.diff(np.concatenate([[0], p]))) * COST)
fig, ax = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                       gridspec_kw={"height_ratios": [2, 1]})
for p, lab, c in [(np.ones(len(g2)), "A 始终持有", "gray"),
                  (posB, "B 价格风控", "b"),
                  (posC, "C 价格+ETF流(F20持续流出)", "r")]:
    e = eq(p)
    ax[0].plot(g2.index, e, label=lab, color=c)
    ax[1].plot(g2.index, e / np.maximum.accumulate(e) - 1, color=c, lw=0.8)
ax[0].set_title("05 风险管理模拟 | 沪深300, 信号T日生成T+1执行, 成本5bp")
ax[0].legend(); ax[1].set_ylabel("回撤")
fig.tight_layout(); fig.savefig("05_risk_management_comparison.png", dpi=140)
plt.close(fig)

# refresh 02 event fwd drawdown bars (new metrics, outflow)
ev = pd.read_csv("EVENT_STUDY_RESULTS.csv")
fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
for j, g in enumerate(["G2_hs300_head", "G1_all_equity"]):
    s = ev[(ev.group == g) & (ev.kind == "outflow")]
    x = np.arange(len(s))
    ax[j].bar(x - 0.22, s.ev_low, 0.42, label="事件后(到最低点)", color="r")
    ax[j].bar(x + 0.22, s.all_low, 0.42, label="全样本", color="gray")
    ax[j].set_xticks(x); ax[j].set_xticklabels([f"{w}日" for w in s.window])
    ax[j].set_title(f"{g} 持续流出簇后窗口最低跌幅 (n簇={int(s.n_clusters.iloc[0])})", fontsize=9)
    ax[j].axhline(-0.05, color="k", ls=":", lw=0.8); ax[j].legend(fontsize=8)
fig.tight_layout(); fig.savefig("02_flow_event_forward_drawdown.png", dpi=140)
plt.close(fig)
print("pngs done")
