"""ETF-FLOW-POC-02.1 — corrected dual curve + methodology comparison.

P0 fix: Guojin fig-54 axis is +15,000 / -9,000 yi over 2020-2026,
not +/-1,500. Primary chart = 2020-start cumulative, PIT-rolling,
binary lanes (institution vs non-institution) matching the original
dual-curve format.
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


def daily(csv):
    return pd.read_csv(DATA / csv, parse_dates=["date"], index_col="date")


def binary(d):
    """Guojin-style binary split: institution vs everything else."""
    out = pd.DataFrame(index=d.index)
    out["institution"] = d.get("institution", 0)
    others = [c for c in d.columns if c != "institution"]
    out["personal_all"] = d[others].sum(axis=1) if others else 0
    return out


def coverage_stats():
    cov = pd.read_csv(DATA / "daily_coverage.csv", parse_dates=["date"],
                      index_col="date")
    return cov["funds_priced"].sum() / max(cov["funds_reported"].sum(), 1)


def primary_chart():
    cum = binary(daily("daily_flow_class_pit.csv")).cumsum()
    fig, ax = plt.subplots(figsize=(11.5, 6.4))
    ax.plot(cum.index, cum["personal_all"], color="#1a1a2e", lw=2.2,
            label="个人持有为主/未分类 ETF(合计)")
    ax.plot(cum.index, cum["institution"], color="#a8b8d0", lw=2.2,
            label="机构持有为主 ETF")
    ax.axhline(0, color="#666", lw=0.6)
    ax.set_ylabel("累计净申购（亿元，估算）")
    ax.set_title("ETF 累计净申购：个人/机构持有为主"
                 "（POC-02.1 · 2020起累计 · PIT滚动分类 · 二元口径）",
                 fontsize=13)
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(alpha=0.25)
    d0, d1 = cum.index.min().date(), cum.index.max().date()
    ax.text(0.01, -0.11,
            f"累计起点 {d0}｜分类=PIT滚动(披露实际/假设生效日,"
            f"机构占比>50%入机构车道,其余合并入个人车道)｜股票型ETF 1431 只"
            f"｜估值覆盖率 {coverage_stats():.0%}｜单位:亿元(估算)",
            transform=ax.transAxes, fontsize=8.5, color="#333")
    ax.text(0.01, -0.155,
            "数据源：上交所/深交所每日份额 × 天天基金单位净值；持有人结构"
            "=天天基金F10历期披露；IPO首日与缺失段剔除；10条拆分/合并、"
            "105条数据毛刺、85条待核验已单列不入曲线",
            transform=ax.transAxes, fontsize=8, color="#666")
    fig.tight_layout()
    fig.savefig(HERE / "etf_flow_poc02.png", dpi=150)
    print("saved etf_flow_poc02.png")


def panel(ax, d, title, binary_mode=False, overlay_poc1=False):
    src = binary(d) if binary_mode else d
    cum = src.cumsum()
    if binary_mode:
        for lane, color, lab in (
                ("personal_all", "#1a1a2e", "个人/未分类合计"),
                ("institution", "#a8b8d0", "机构持有为主")):
            if lane in cum:
                ax.plot(cum.index, cum[lane], color=color, lw=1.8,
                        label=lab)
    else:
        for lane, color, lab in LANES:
            if lane in cum and cum[lane].abs().sum() > 0:
                lw = 1.8 if lane in ("personal", "institution") else 1.1
                ax.plot(cum.index, cum[lane], color=color, lw=lw,
                        label=lab)
    if overlay_poc1:
        p = pd.read_csv(POC1 / "cum_flow_by_class.csv",
                        parse_dates=["date"], index_col="date")
        for lane, color in (("personal", "#1a1a2e"),
                            ("institution", "#a8b8d0")):
            if lane in p:
                ax.plot(p.index, p[lane], color=color, lw=1.0, ls=":",
                        alpha=0.7, label=f"POC-01 {lane}")
    ax.axhline(0, color="#666", lw=0.5)
    for y in (-9000, 15000):
        ax.axhline(y, color="#c0392b", lw=0.7, ls=":", alpha=0.55)
    ax.set_title(title, fontsize=11)
    ax.legend(fontsize=7.5, loc="best")
    ax.grid(alpha=0.2)
    ax.set_ylabel("亿元(估算)")


def comparison_chart():
    fig, axes = plt.subplots(3, 2, figsize=(13.5, 13))
    panel(axes[0, 0], daily("daily_flow_class_pit.csv"),
          "a) 2020起累计 × PIT滚动(细分车道)")
    panel(axes[0, 1], daily("daily_flow_class_pit.csv"),
          "b) 2020起累计 × PIT滚动(二元,主图口径)", binary_mode=True)
    panel(axes[1, 0], daily("daily_flow_class_fixed.csv"),
          "c) 2020起累计 × latest-fixed(细分车道)")
    panel(axes[1, 1], daily("daily_flow_class_fixed.csv"),
          "d) 2020起累计 × latest-fixed(二元)", binary_mode=True)
    panel(axes[2, 0], daily("daily_flow_class_pit.csv"),
          "e) PIT二元 vs POC-01原算法", binary_mode=True,
          overlay_poc1=True)
    panel(axes[2, 1], daily("daily_flow_class_fixed.csv"),
          "f) fixed二元 vs POC-01原算法", binary_mode=True,
          overlay_poc1=True)
    fig.suptitle("POC-02.1 口径对照（红虚线=国金图54纵轴 +15000/−9000亿）",
                 fontsize=13)
    fig.tight_layout()
    fig.savefig(HERE / "etf_flow_method_comparison.png", dpi=140)
    print("saved etf_flow_method_comparison.png")


if __name__ == "__main__":
    primary_chart()
    comparison_chart()
