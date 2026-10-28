"""ETF-FLOW-POC-02.1 final charts — display only, no recomputation.

Reads existing POC-02.1 outputs (data/*.csv) and renders:
  fig1_cumulative_2020_2026.png  dual curve, PIT-rolling, strict lanes
  fig2_classification_compare.png PIT vs latest-fixed, same axes
  fig3_csi300_four_funds.png     510300/510310/510330/159919 cumulative
"""
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

warnings.filterwarnings("ignore")
plt.rcParams["font.sans-serif"] = [
    "PingFang SC", "Hiragino Sans GB", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).parent
DATA = HERE / "data"
DPI = 220

C_PERSONAL = "#1a1a2e"     # dark
C_INST = "#7ea6d8"         # light blue


def daily(csv):
    return pd.read_csv(DATA / csv, parse_dates=["date"], index_col="date")


def cov_ratio():
    cov = pd.read_csv(DATA / "daily_coverage.csv",
                      parse_dates=["date"], index_col="date")
    return cov["funds_priced"].sum() / max(cov["funds_reported"].sum(), 1)


def fig1():
    cum = daily("daily_flow_class_pit.csv").cumsum()
    fig, ax = plt.subplots(figsize=(12, 6.6))
    ax.plot(cum.index, cum["personal"], color=C_PERSONAL, lw=2.3,
            label="个人持有为主 ETF")
    ax.plot(cum.index, cum["institution"], color=C_INST, lw=2.3,
            label="机构持有为主 ETF")
    ax.axhline(0, color="#666", lw=0.6)

    pk = cum["institution"].idxmax()
    tr = cum["institution"].idxmin()
    ax.annotate(f"机构峰 {cum['institution'].max():,.0f}亿\n{pk.date()}",
                xy=(pk, cum.loc[pk, "institution"]),
                xytext=(pk, cum.loc[pk, "institution"] + 2200),
                fontsize=8.5, color="#33597f",
                arrowprops=dict(arrowstyle="->", color="#33597f", lw=0.8))
    ax.annotate(f"机构谷 {cum['institution'].min():,.0f}亿\n{tr.date()}",
                xy=(tr, cum.loc[tr, "institution"]),
                xytext=(tr - pd.Timedelta(days=520),
                        cum.loc[tr, "institution"] - 2200),
                fontsize=8.5, color="#33597f",
                arrowprops=dict(arrowstyle="->", color="#33597f", lw=0.8))
    ax.text(0.01, -0.21,
            "注：510310 于 2024-09-19/20 发生跨日 1:2 份额合并"
            "（NAV 19日翻倍、份额20日减半），当前规则记为 −1,906 亿"
            "单日流出，已列入待核验清单（未改计算数据）",
            transform=ax.transAxes, fontsize=8, color="#a04030")

    ax.set_ylabel("累计净申购（亿元，估算）")
    ax.set_title("ETF 累计净申购：个人 / 机构持有为主"
                 "（2020-01 ~ 2026-10 · PIT 滚动分类）", fontsize=13)
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(alpha=0.25)
    d0, d1 = cum.index.min().date(), cum.index.max().date()
    ax.text(0.01, -0.12,
            f"累计起点 {d0}｜样本池=沪深交易所股票型ETF 1431只｜"
            f"分类=PIT滚动(机构占比>50%入机构车道,披露截止日+90天生效,"
            f"混合/未知不并入)｜估值覆盖率 {cov_ratio():.0%}",
            transform=ax.transAxes, fontsize=8.5, color="#333")
    ax.text(0.01, -0.165,
            "数据源：上交所/深交所每日份额 × 天天基金单位净值；"
            "持有人结构=天天基金F10历期披露；IPO首日/缺失段/拆分合并/"
            "数据毛刺/待核验行已剔除（见 CORPORATE_ACTION_REVIEW.csv）",
            transform=ax.transAxes, fontsize=8, color="#666")
    fig.tight_layout()
    fig.savefig(HERE / "fig1_cumulative_2020_2026.png", dpi=DPI)
    print("saved fig1")


def fig2():
    pit = daily("daily_flow_class_pit.csv").cumsum()
    fix = daily("daily_flow_class_fixed.csv").cumsum()
    lanes = [("personal", "个人持有为主 ETF"),
             ("institution", "机构持有为主 ETF"),
             ("mixed", "混合"), ("pre_disclosure", "尚无生效披露"),
             ("unknown", "分类未知")]
    colors = {"personal": C_PERSONAL, "institution": C_INST,
              "mixed": "#c9a227", "pre_disclosure": "#7fc8a9",
              "unknown": "#999999"}
    fig, axes = plt.subplots(2, 1, figsize=(12, 9), sharex=True,
                             sharey=True)
    for ax, cum, tag in ((axes[0], pit, "PIT-rolling 历史滚动分类"),
                         (axes[1], fix, "latest-fixed 最新固定分类")):
        for lane, lab in lanes:
            if lane in cum and cum[lane].abs().sum() > 0:
                lw = 2.1 if lane in ("personal", "institution") else 1.1
                ls = "-" if lane in ("personal", "institution") else "--"
                ax.plot(cum.index, cum[lane], color=colors[lane],
                        lw=lw, ls=ls, label=lab)
        ax.axhline(0, color="#666", lw=0.6)
        ax.set_title(tag, fontsize=11.5)
        ax.legend(fontsize=8.5, loc="upper left")
        ax.grid(alpha=0.25)
        ax.set_ylabel("累计净申购（亿元，估算）")
    axes[1].set_xlabel("日期")
    fig.suptitle("同一资金流 · 两种持有人分类口径对照"
                 "（2020-01 ~ 2026-10 · 相同坐标轴）", fontsize=13)
    fig.tight_layout()
    fig.savefig(HERE / "fig2_classification_compare.png", dpi=DPI)
    print("saved fig2")


def fig3():
    f = pd.read_csv(DATA / "etf_daily_flows_v2.csv",
                    usecols=["date", "fund_code", "name", "flow_yi"],
                    dtype={"fund_code": str}, parse_dates=["date"],
                    low_memory=False)
    targets = {"510300": "沪深300ETF(华泰柏瑞)", "510310": "沪深300ETF易方达",
               "510330": "沪深300ETF华夏", "159919": "沪深300ETF嘉实"}
    colors = {"510300": "#1a1a2e", "510310": "#c0392b",
              "510330": "#2e86c1", "159919": "#27ae60"}
    fig, ax = plt.subplots(figsize=(12, 6.6))
    for code, label in targets.items():
        d = (f[f.fund_code == code]
             .set_index("date")["flow_yi"].dropna())
        d = d[d.index >= "2024-01-01"].cumsum()
        ax.plot(d.index, d, color=colors[code], lw=1.9,
                label=f"{code} {label}")
    ax.axhline(0, color="#666", lw=0.6)
    ax.set_ylabel("累计净申购（亿元，估算 · 2024-01 起）")
    ax.set_title("四只沪深300ETF 累计净申购（2024-01 ~ 2026-10）"
                 "——2026年集中净赎回", fontsize=13)
    ax.legend(loc="upper right", fontsize=9.5)
    ax.grid(alpha=0.25)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.annotate("510310 跨日1:2份额合并\n(算法记为单日流出,待核验)",
                xy=(pd.Timestamp("2024-09-20"), -300),
                xytext=(pd.Timestamp("2024-11-15"), -1900),
                fontsize=8.5, color="#a04030",
                arrowprops=dict(arrowstyle="->", color="#a04030", lw=0.8))
    ax.text(0.01, -0.12,
            "单基金口径：Δ份额×当日单位净值，累计起点 2024-01-02｜"
            "2026年1月为集中净赎回窗口(NAV连续+份额持续=真实申赎)｜"
            "数据源：交易所日份额×天天基金净值",
            transform=ax.transAxes, fontsize=8.5, color="#333")
    fig.tight_layout()
    fig.savefig(HERE / "fig3_csi300_four_funds.png", dpi=DPI)
    print("saved fig3")


if __name__ == "__main__":
    fig1()
    fig2()
    fig3()
