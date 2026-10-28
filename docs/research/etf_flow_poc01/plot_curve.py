"""ETF-FLOW-POC-01 step 4 — draw the dual cumulative net-creation curve.

Output: etf_cumulative_net_creation_poc.png
Dark line = personal-holder-led ETFs; light line = institution-led.
Coverage, sample size and data-coverage annotations are drawn on the
chart; sources + method are noted below it.
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


def main() -> None:
    cum = pd.read_csv(DATA / "cum_flow_by_class.csv",
                      parse_dates=["date"], index_col="date")
    holders = pd.read_csv(HERE / "ETF_HOLDER_CLASSIFICATION.csv")
    counts = holders["holder_class"].value_counts().to_dict()
    flows = pd.read_csv(DATA / "etf_daily_flows.csv", parse_dates=["date"])
    priced_days = flows.dropna(subset=["flow_yi"])
    coverage = len(priced_days) / max(len(flows), 1)

    fig, ax = plt.subplots(figsize=(11, 6))
    if "personal" in cum:
        ax.plot(cum.index, cum["personal"], color="#1a1a2e",
                lw=2.2, label="个人持有为主 ETF")
    if "institution" in cum:
        ax.plot(cum.index, cum["institution"], color="#a8b8d0",
                lw=2.2, label="机构持有为主 ETF")
    if "mixed" in cum and cum["mixed"].abs().sum() > 0:
        ax.plot(cum.index, cum["mixed"], color="#c9a227", lw=1.4,
                ls="--", label="混合型(50%两侧接近)")
    if "unknown" in cum and cum["unknown"].abs().sum() > 0:
        ax.plot(cum.index, cum["unknown"], color="#888888", lw=1.2,
                ls=":", label="分类未知")
    ax.axhline(0, color="#666", lw=0.6)
    ax.set_ylabel("累计净申购（亿元，估算）")
    ax.set_title("ETF 累计净申购：个人/机构持有为主（POC 复现，非国金原始数据）",
                 fontsize=13)
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(alpha=0.25)

    d0, d1 = cum.index.min().date(), cum.index.max().date()
    note = (f"覆盖区间 {d0} ~ {d1}｜股票型ETF {sum(counts.values())} 只"
            f"（个人 {counts.get('personal', 0)} / 机构 {counts.get('institution', 0)}"
            f" / 混合 {counts.get('mixed', 0)} / 未知 {counts.get('unknown', 0)}）"
            f"｜估值覆盖率 {coverage:.0%}")
    ax.text(0.01, -0.11, note, transform=ax.transAxes, fontsize=8.5,
            color="#333")
    ax.text(0.01, -0.155,
            "数据源：上交所/深交所每日基金份额 × 天天基金单位净值估算"
            "（估值缺口的基金以新浪/腾讯收盘价补充）；持有人结构=天天基金"
            "F10最新半年报；口径详见 POC_CONCLUSION.md",
            transform=ax.transAxes, fontsize=8, color="#666")
    fig.tight_layout()
    fig.savefig(HERE / "etf_cumulative_net_creation_poc.png", dpi=150)
    print("saved", HERE / "etf_cumulative_net_creation_poc.png")


if __name__ == "__main__":
    sys.exit(main())
