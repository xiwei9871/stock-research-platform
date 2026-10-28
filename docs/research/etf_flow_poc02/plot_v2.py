"""ETF-FLOW-POC-02 — dual curve + methodology-comparison charts.

Outputs:
  etf_flow_poc02.png              primary: cumulative since 2020-01,
                                  PIT-rolling classification.
  etf_flow_method_comparison.png  grid of candidate windows x
                                  classification rules vs POC-01.
"""
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

warnings.filterwarnings("ignore")
plt.rcParams["font.sans-serif"] = [
    "PingFang SC", "Hiragino Sans GB", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).parent
DATA = HERE / "data"
POC1 = HERE.parent / "etf_flow_poc01" / "data"

LANES = [
    ("personal", "#1a1a2e", "个人持有为主 ETF"),
    ("institution", "#a8b8d0", "机构持有为主 ETF"),
    ("mixed", "#c9a227", "混合(两侧均≤50%)"),
    ("pre_disclosure", "#7fc8a9", "尚无生效披露"),
    ("unknown", "#999999", "分类未知"),
]


def cum_frame(csv, start=None, since=None, roll=None):
    d = pd.read_csv(DATA / csv, parse_dates=["date"], index_col="date")
    if since is not None:
        d = d[d.index >= since]
        d = d.cumsum()
    elif start is not None:
        d = d[d.index >= start].cumsum()
    elif roll:
        d = d.rolling(roll, min_periods=20).sum()
    else:
        d = d.cumsum()
    return d


def coverage_stats():
    cov = pd.read_csv(DATA / "daily_coverage.csv", parse_dates=["date"],
                      index_col="date")
    priced = cov["funds_priced"].sum()
    reported = cov["funds_reported"].sum()
    return priced / max(reported, 1)


def primary_chart():
    cum = cum_frame("daily_flow_class_pit.csv")
    cov_ratio = coverage_stats()
    n_funds = 1431
    fig, ax = plt.subplots(figsize=(11.5, 6.4))
    for lane, color, label in LANES:
        if lane in cum and cum[lane].abs().sum() > 0:
            ls = "-" if lane in ("personal", "institution") else "--"
            lw = 2.2 if lane in ("personal", "institution") else 1.2
            ax.plot(cum.index, cum[lane], color=color, lw=lw, ls=ls,
                    label=label)
    ax.axhline(0, color="#666", lw=0.6)
    ax.set_ylabel("累计净申购（亿元，估算）")
    ax.set_title("ETF 累计净申购：个人/机构持有为主"
                 "（POC-02 · PIT 滚动分类 · 非国金原始数据）", fontsize=13)
    ax.legend(loc="upper left", fontsize=9.5)
    ax.grid(alpha=0.25)
    d0, d1 = cum.index.min().date(), cum.index.max().date()
    ax.text(0.01, -0.11,
            f"累计起点 {d0}｜分类=PIT滚动(持有人披露截止日+90天生效,"
            f"机构占比>50%为机构类)｜股票型ETF {n_funds} 只｜"
            f"估值覆盖率 {cov_ratio:.0%}｜单位:亿元(估算)",
            transform=ax.transAxes, fontsize=8.5, color="#333")
    ax.text(0.01, -0.155,
            "数据源：上交所/深交所每日份额 × 天天基金单位净值；持有人结构"
            "=天天基金F10历期披露；首日IPO与缺失段已剔除、746条大额变动"
            "经净值连续性核验为真实申赎", transform=ax.transAxes,
            fontsize=8, color="#666")
    fig.tight_layout()
    fig.savefig(HERE / "etf_flow_poc02.png", dpi=150)
    print("saved etf_flow_poc02.png")


def comparison_chart():
    poc1 = pd.read_csv(POC1 / "cum_flow_by_class.csv",
                       parse_dates=["date"], index_col="date")
    panels = [
        ("a) 2020起累计 × latest-fixed", "daily_flow_class_fixed.csv",
         dict(since="2020-01-01")),
        ("b) 2020起累计 × PIT滚动", "daily_flow_class_pit.csv",
         dict(since="2020-01-01")),
        ("c) 2024起累计 × latest-fixed", "daily_flow_class_fixed.csv",
         dict(since="2024-01-01")),
        ("d) 2024起累计 × PIT滚动", "daily_flow_class_pit.csv",
         dict(since="2024-01-01")),
        ("e) 2026YTD累计 × latest-fixed", "daily_flow_class_fixed.csv",
         dict(since="2026-01-01")),
        ("f) 滚动12个月 × latest-fixed", "daily_flow_class_fixed.csv",
         dict(roll=244)),
    ]
    fig, axes = plt.subplots(3, 2, figsize=(13.5, 13))
    for ax, (title, csv, kw) in zip(axes.flat, panels):
        cum = cum_frame(csv, **kw)
        for lane, color, label in LANES[:2] + [LANES[2]]:
            if lane in cum and cum[lane].abs().sum() > 0:
                ax.plot(cum.index, cum[lane], color=color, lw=1.8,
                        label=label)
        if "since" in kw and kw["since"] == "2020-01-01" \
                and "fixed" in csv:
            for lane, color in (("personal", "#1a1a2e"),
                                ("institution", "#a8b8d0")):
                if lane in poc1:
                    ax.plot(poc1.index, poc1[lane], color=color, lw=1.0,
                            ls=":", alpha=0.7, label=f"POC-01 {lane}")
        ax.axhline(0, color="#666", lw=0.5)
        for y in (-1500, 1500):
            ax.axhline(y, color="#c0392b", lw=0.6, ls=":", alpha=0.5)
        ax.set_title(title, fontsize=11)
        ax.legend(fontsize=7.5, loc="best")
        ax.grid(alpha=0.2)
        ax.set_ylabel("亿元(估算)")
    fig.suptitle("POC-02 口径敏感性：累计窗口 × 持有人分类"
                 "（红虚线±1500亿=国金图54纵轴量级参考）", fontsize=13)
    fig.tight_layout()
    fig.savefig(HERE / "etf_flow_method_comparison.png", dpi=140)
    print("saved etf_flow_method_comparison.png")


if __name__ == "__main__":
    primary_chart()
    comparison_chart()
