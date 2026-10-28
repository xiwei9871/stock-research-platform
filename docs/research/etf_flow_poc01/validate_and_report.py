"""ETF-FLOW-POC-01 step 5 — validation checks + deliverable CSVs.

Produces:
  ETF_SOURCE_TEST.csv          — per-source download evidence
  ETF_DAILY_SAMPLE.csv         — daily shares/nav/flow for sample ETFs
  ETF_FLOW_VALIDATION.md       — reconciliation + spot checks +
                                 comparison vs 国金证券图54 anchors
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = Path(__file__).parent
DATA = HERE / "data"

SAMPLE = ["510300", "510050", "510500", "159915", "512880",
          "515790", "588000", "159919", "510880", "512170"]

# External anchors for sanity comparison (publicly reported figures):
# - 2026-10-23 stock-ETF net inflow ~587.63亿 (银河证券基金研究中心,
#   cited by 21经济网/环球网; 宽基 ~555亿, 沪深300系 +244.5亿)
# - 2024-2025: 中央汇金大规模宽基申购期 (announced 2024-02, 2025-04)
ANCHORS = {"2026-10-23": {"stock_etf_inflow_yi": 587.63}}


def main() -> None:
    shares_sse = pd.read_csv(DATA / "sse_etf_shares.csv",
                             dtype={"fund_code": str})
    shares_szse = pd.read_csv(DATA / "szse_etf_shares.csv",
                              dtype={"fund_code": str})
    shares = pd.concat([shares_sse, shares_szse], ignore_index=True)
    flows = pd.read_csv(DATA / "etf_daily_flows.csv",
                        parse_dates=["date"], dtype={"fund_code": str})
    holders = pd.read_csv(HERE / "ETF_HOLDER_CLASSIFICATION.csv",
                          dtype={"fund_code": str})

    # ---- 1. source test record
    src_rows = [
        {"source": "上交所ETF产品列表 query.sse.com.cn (akshare fund_etf_scale_sse)",
         "item": "每日全市场基金份额", "dates": shares_sse["date"].nunique(),
         "rows": len(shares_sse), "funds": shares_sse["fund_code"].nunique(),
         "range": f"{shares_sse['date'].min()}~{shares_sse['date'].max()}",
         "status": "ok"},
        {"source": "深交所基金规模日频 (akshare fund_scale_daily_szse)",
         "item": "每日全市场基金份额", "dates": shares_szse["date"].nunique(),
         "rows": len(shares_szse), "funds": shares_szse["fund_code"].nunique(),
         "range": f"{shares_szse['date'].min()}~{shares_szse['date'].max()}",
         "status": "ok"},
        {"source": "新浪财经 fund_etf_hist_sina",
         "item": "每日收盘价(估值基准)",
         "dates": "", "rows": "",
         "funds": len(list((DATA / 'prices').glob('*.csv'))),
         "range": "上市~2026-10", "status": "ok"},
        {"source": "天天基金F10 api.fund.eastmoney.com/f10/lsjz",
         "item": "每日单位净值(样本对账)",
         "dates": "", "rows": "",
         "funds": len(list((DATA / 'nav').glob('*.csv'))),
         "range": "2019-12~2026-10", "status": "ok(分页限流,仅样本)"},
        {"source": "天天基金F10 FundArchivesDatas.aspx?type=cyrjg",
         "item": "基金半年度持有人结构",
         "dates": "", "rows": "",
         "funds": len(list((DATA / 'holder_structure').glob('*.csv'))),
         "range": "各报告期", "status": "ok"},
    ]
    pd.DataFrame(src_rows).to_csv(HERE / "ETF_SOURCE_TEST.csv", index=False)

    cls_map = holders.set_index("fund_code")["holder_class"]
    flows["holder_class"] = flows["fund_code"].map(cls_map)

    # ---- 2. sample reconciliation: shares + nav + close for ≥5 ETFs
    sample = flows[flows["fund_code"].isin(SAMPLE)].copy()
    nav_frames = []
    for code in SAMPLE:
        p = DATA / "nav" / f"{code}.csv"
        if p.exists():
            d = pd.read_csv(p, dtype={"date": str})
            d["fund_code"] = code
            nav_frames.append(d)
    nav = (pd.concat(nav_frames) if nav_frames
           else pd.DataFrame(columns=["date", "nav", "fund_code"]))
    nav["date"] = pd.to_datetime(nav["date"])
    sample = sample.merge(nav, on=["fund_code", "date"], how="left")
    sample["nav_close_gap_pct"] = (
        sample["valuation"] / sample["nav"] - 1) * 100
    out_cols = ["date", "fund_code", "name", "shares", "d_shares",
                "valuation", "nav", "nav_close_gap_pct", "flow_yi",
                "corp_action_suspect", "holder_class"]
    sample[out_cols].sort_values(["fund_code", "date"]).to_csv(
        HERE / "ETF_DAILY_SAMPLE.csv", index=False)

    recon = (sample.dropna(subset=["nav_close_gap_pct"])
             .groupby("fund_code")["nav_close_gap_pct"]
             .agg(["median", lambda s: s.abs().quantile(0.95), "count"]))
    recon.columns = ["median_gap_pct", "p95_abs_gap_pct", "n_days"]

    # ---- 3. spot-check cumulative values at ≥3 dates
    cum = pd.read_csv(DATA / "cum_flow_by_class.csv",
                      parse_dates=["date"], index_col="date")
    checks = ["2021-12-31", "2024-02-08", "2024-12-31",
              "2026-04-08", "2026-10-23"]
    spot = {d: cum.loc[:d].iloc[-1].round(1).to_dict()
            for d in checks if len(cum.loc[:d])}

    # ---- 4. anchor day comparison (2026-10-23)
    anchor_day = flows[flows["date"] == "2026-10-23"]
    day_total = anchor_day["flow_yi"].sum()
    day_by_cls = (anchor_day.groupby("holder_class")["flow_yi"]
                  .sum().round(1).to_dict())

    # ---- 5. anomaly counts
    corp = flows["corp_action_suspect"].sum()
    n_nan = flows["flow_yi"].isna().sum()

    lines = [
        "# ETF_FLOW_VALIDATION",
        "",
        "## 数据源实测（详见 ETF_SOURCE_TEST.csv）",
        f"- SSE 份额 {shares_sse['date'].nunique()} 交易日 / "
        f"{shares_sse['fund_code'].nunique()} 只 / {len(shares_sse):,} 行",
        f"- SZSE 份额 {shares_szse['date'].nunique()} 交易日 / "
        f"{shares_szse['fund_code'].nunique()} 只 / {len(shares_szse):,} 行",
        "",
        "## 净值 vs 收盘价对账（样本，中位/95分位绝对差）",
        "```",
        recon.round(3).to_string(),
        "```",
        "",
        "## 关键日期累计净申购（亿元）",
        "```",
        pd.DataFrame(spot).to_string(),
        "```",
        "",
        "## 外部锚点对账：2026-10-23",
        f"- 本实验当日全口径合计：**{day_total:.1f} 亿**"
        f"（个人 {day_by_cls.get('personal', 0):.1f} / "
        f"机构 {day_by_cls.get('institution', 0):.1f} / "
        f"混合 {day_by_cls.get('mixed', 0):.1f} / "
        f"未知 {day_by_cls.get('unknown', 0):.1f}）",
        "- 外部报道（银河证券基金研究中心口径）：股票ETF 当日净流入 "
        "**~587.63 亿**，宽基 ~555 亿，沪深300系 +244.5 亿",
        "- 注意口径差：本实验为 A股股票ETF全集，银河为股票ETF(含/不含"
        "跨境与窄基口径未明)且为申赎口径，数值不可期望完全一致",
        "",
        "## 质量标记",
        f"- 疑似公司行为（单日份额降幅>40%，疑折算/合并/退市尾）："
        f"{corp} 条，已置空并单列 corp_action_suspects.csv",
        f"- 无估值（缺价格）flow 记 NaN：{n_nan} 条",
        "",
    ]
    (HERE / "ETF_FLOW_VALIDATION.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
