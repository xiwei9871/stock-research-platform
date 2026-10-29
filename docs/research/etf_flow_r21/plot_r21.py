import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

C = {"NORMAL": "#e8f5e9", "WATCH": "#fff9c4", "ELEVATED": "#ffe0b2",
     "HIGH_PRESSURE": "#ffcdd2", "RECOVERING": "#e1f5fe"}
g2 = pd.read_parquet("data/factors_G2_hs300_head.parquet")
g2.index = pd.to_datetime(g2.index)
pe = pd.read_csv("../etf_flow_r2/POLICY_EVENTS.csv")
fr = pd.read_csv("FORWARD_RISK_BY_STATE.csv")
lt = pd.read_csv("ALERT_LEAD_TIME.csv")
fa = pd.read_csv("FALSE_ALERT_AUDIT.csv")
iv = pd.read_csv("INCREMENTAL_VALUE_VS_PRICE.csv")
te = pd.read_csv("TECHNOLOGY_WARNING_RESULTS.csv")


def shade(ax, df):
    prev, st = 0, df.state.iloc[0]
    for i, s in enumerate(df.state):
        if s != st or i == len(df) - 1:
            if st in C and st != "NORMAL":
                ax.axvspan(df.index[prev], df.index[i - 1], color=C[st],
                           alpha=.6, lw=0)
            prev, st = i, s


def pol(ax, yl):
    for _, r in pe.iterrows():
        if r.category in ("official_action", "official_document"):
            ax.axvline(pd.Timestamp(r.event_date), color="purple",
                       ls=":", lw=.8, alpha=.5)


fig, ax = plt.subplots(2, 1, figsize=(14, 7), sharex=True,
                       gridspec_kw={"height_ratios": [2, 1]})
ax[0].plot(g2.index, g2.hs300, "k", lw=1); ax[0].set_ylabel("CSI300")
ax2 = ax[0].twinx(); ax2.plot(g2.index, g2.F20 * 100, "tab:blue", lw=.8, alpha=.6)
ax2.set_ylabel("F20 %"); ax2.axhline(0, color="gray", lw=.4); pol(ax[0], None)
shade(ax[0], g2)
ax[1].plot(g2.index, g2.WP, "tab:red", lw=1); ax[1].axhline(70, ls="--", c="r", lw=.6)
ax[1].set_ylabel("Withdrawal Pressure"); ax[1].set_ylim(0, 100)
for a, t in zip(ax, ["CSI300 + F20 + warning states", "Withdrawal Pressure (0-100)"]):
    a.set_title(t)
fig.tight_layout(); fig.savefig("01_broad_withdrawal_pressure.png", dpi=110); plt.close()

fig, ax = plt.subplots(2, 1, figsize=(14, 7), sharex=True,
                       gridspec_kw={"height_ratios": [2, 1]})
ax[0].plot(g2.index, g2.hs300, "k", lw=1); ax[0].set_ylabel("CSI300"); pol(ax[0], None)
ax2 = ax[0].twinx(); ax2.plot(g2.index, g2.F40 * 100, "tab:green", lw=.8, alpha=.6)
ax2.set_ylabel("F40 %"); ax2.axhline(0, color="gray", lw=.4)
ax[1].plot(g2.index, g2.AS, "tab:green", lw=1); ax[1].axhline(65, ls="--", c="g", lw=.6)
ax[1].set_ylabel("Absorption Strength"); ax[1].set_ylim(0, 100)
ax[0].set_title("CSI300 + F40"); ax[1].set_title("Absorption Strength (0-100)")
fig.tight_layout(); fig.savefig("02_broad_absorption_strength.png", dpi=110); plt.close()

d26 = g2["2025-12":]
fig, ax = plt.subplots(2, 1, figsize=(14, 7), sharex=True,
                       gridspec_kw={"height_ratios": [2, 1]})
shade(ax[0], d26)
ax[0].plot(d26.index, d26.hs300, "k", lw=1.2); ax[0].set_ylabel("CSI300")
for _, r in pd.read_csv("WARNING_TRANSITIONS.csv").iterrows():
    if r.date >= "2025-12-01":
        ax[0].annotate(r["to"], (pd.Timestamp(r.date), d26.hs300.asof(
            pd.Timestamp(r.date))), fontsize=7, rotation=30)
ax[1].plot(d26.index, d26.WP, "tab:red", lw=1, label="WP")
ax[1].plot(d26.index, d26.AS, "tab:green", lw=1, label="AS")
ax[1].legend(); ax[1].set_ylim(0, 100)
ax[0].set_title("2026 warning replay (states shaded)")
fig.tight_layout(); fig.savefig("03_warning_timeline_2026.png", dpi=110); plt.close()

w60 = fr[fr.window == 60]
fig, ax = plt.subplots(1, 2, figsize=(11, 4))
x = np.arange(len(w60))
ax[0].bar(x - .2, -w60.ev_mdd, .4, label="warning")
ax[0].bar(x + .2, -w60.all_mdd, .4, label="all")
ax[0].set_xticks(x, w60.state, rotation=15); ax[0].set_title("60d strict MDD")
ax[0].legend()
ax[1].bar(x - .2, w60.p_dd10, .4, label="warning")
ax[1].bar(x + .2, w60.all_p_dd10, .4, label="all")
ax[1].set_xticks(x, w60.state, rotation=15)
ax[1].set_title("P(60d low < -10%)")
for a in ax:
    for i, n in enumerate(w60.n):
        a.text(i, a.get_ylim()[1] * .95, f"n={n}", ha="center", fontsize=8)
fig.tight_layout(); fig.savefig("04_forward_risk_by_warning_level.png", dpi=110)
plt.close()

fig, ax = plt.subplots(1, 2, figsize=(11, 4))
ltd = lt[lt.event == "dd10"].dropna(subset=["lead_days"])
ax[0].hist(ltd.lead_days, bins=15, color="tab:blue")
ax[0].set_title(f"Lead days (covered {ltd.shape[0]}/{len(lt[lt.event=='dd10'])})")
ax[0].set_xlabel("days")
fa["type"] = np.where(fa.false_alert, "missed/false", "confirmed")
fa.boxplot(column="fwd_low120", by="type", ax=ax[1])
ax[1].set_title("120d low after warning"); ax[1].set_xlabel("")
fig.suptitle(""); fig.tight_layout()
fig.savefig("05_warning_lead_time.png", dpi=110); plt.close()

fig, ax = plt.subplots(1, 2, figsize=(11, 4))
x = np.arange(3)
ax[0].bar(x - .15, iv.precision, .3, label="precision")
ax[0].bar(x + .15, iv.recall, .3, label="recall")
ax[0].set_xticks(x, iv.model); ax[0].legend(); ax[0].set_title("dd10-in-60d")
ax[1].bar(x - .15, iv.ap, .3, label="avg precision")
ax[1].bar(x + .15, 1 - iv.brier / iv.brier.max(), .3, label="1-norm brier")
ax[1].set_xticks(x, iv.model); ax[1].legend()
ax[1].set_title("Prob scoring")
fig.tight_layout(); fig.savefig("06_price_vs_etf_incremental_value.png", dpi=110)
plt.close()

fig, ax = plt.subplots(2, 1, figsize=(14, 7), sharex=True)
for g in ["G5_semiconductor", "G6_ai_compute", "G7_robot", "G8_softinfo",
          "G4k_star"]:
    d = pd.read_parquet(f"data/factors_{g}.parquet")
    d.index = pd.to_datetime(d.index)
    ax[0].plot(d.index, d.WP, lw=.7, label=g.replace("G", "").split("_")[0])
ax[0].legend(fontsize=7, ncol=5); ax[0].set_ylabel("tech WP"); ax[0].set_ylim(0, 100)
x = np.arange(len(te))
ax[1].bar(x - .2, te.corr_ownWP_ownMDD.abs(), .4, label="|corr own WP|")
ax[1].bar(x + .2, te.corr_G2WP_ownMDD.abs(), .4, label="|corr G2 WP|")
ax[1].set_xticks(x, te.group, rotation=15, fontsize=8); ax[1].legend()
ax[1].set_title("WP vs own-index 60d MDD")
fig.tight_layout(); fig.savefig("07_technology_warning_timeline.png", dpi=110)
plt.close()

po = pd.read_csv("POLICY_REGIME_RESULTS.csv")
fig, ax = plt.subplots(1, 2, figsize=(11, 4))
x = np.arange(2)
ax[0].bar(x, po.corr_WP_fwdmdd60, .5, color=["tab:purple", "tab:gray"])
ax[0].set_xticks(x, po.segment); ax[0].axhline(0, c="k", lw=.5)
ax[0].set_title("corr(WP, 60d MDD)")
ax[1].bar(x, po.warn_days / po.n, .5, color=["tab:purple", "tab:gray"])
ax[1].set_xticks(x, po.segment); ax[1].set_title("warning-day share")
fig.tight_layout(); fig.savefig("08_policy_regime_comparison.png", dpi=110)
plt.close()

fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
ok = fa[~fa.false_alert].head(3)
for _, r in ok.iterrows():
    w = g2[r.start:r.end]
    ax[0].plot((w.index - pd.Timestamp(r.start)).days, w.hs300 / w.hs300.iloc[0],
               label=f"{r.start[:7]}")
ax[0].legend(fontsize=7); ax[0].set_title("confirmed warnings"); ax[0].axhline(1, c="k", lw=.5)
fl = fa[fa.false_alert]
for _, r in fl.iterrows():
    w = g2[r.start:r.end]
    ax[1].plot((w.index - pd.Timestamp(r.start)).days, w.hs300 / w.hs300.iloc[0],
               label=f"{r.start[:7]}")
ax[1].legend(fontsize=7); ax[1].set_title("false alerts"); ax[1].axhline(1, c="k", lw=.5)
fig.tight_layout(); fig.savefig("09_success_failure_cases.png", dpi=110); plt.close()
print("9 pngs done")
