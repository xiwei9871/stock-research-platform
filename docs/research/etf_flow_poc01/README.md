# ETF-FLOW-POC-01 — ETF 累计净申购双曲线可行性实验

独立研究实验：尝试用免 Wind 的真实数据复现国金证券"个人/机构持有
为主 ETF 累计净申购"双曲线（资金跟踪系列周报 图54）。

## 结论

**FEASIBLE** —— 见 `POC_CONCLUSION.md`。
全区间 2020-01-02 ~ 2026-10-27 日频复现完成，外部锚点吻合度 ~95%。

## 文件

| 文件 | 内容 |
|---|---|
| `etf_cumulative_net_creation_poc.png` | 双曲线主图 |
| `ETF_SOURCE_TEST.csv` | 数据源实测记录 |
| `ETF_DAILY_SAMPLE.csv` | 10 只样本 ETF 的日度份额/净值/流量 |
| `ETF_HOLDER_CLASSIFICATION.csv` | 1431 只基金分类明细与披露日 |
| `ETF_FLOW_VALIDATION.md` | 对账与锚点验证 |
| `POC_CONCLUSION.md` | 结论、假设清单、复现方式 |
| `raw_sample/` | 可追溯原始样本（单日交易所全量+样本文件） |
| `data/` | gitignored 工作区（约 314MB 原始数据） |

## 脚本执行顺序

```
python fetch_sse_shares.py     # 上交所每日份额 → data/sse_daily/
python fetch_szse_shares.py    # 深交所每日份额 → data/szse_etf_shares.csv
python fetch_nav_all.py        # 全宇宙单位净值 → data/naval/
python fetch_prices.py         # 收盘价备援（腾讯 kline，可跳过）
python fetch_holders.py        # 持有人结构 → data/holder_structure/
python fetch_nav_sample.py     # 样本 NAV 对账（可选）
python compute_net_creation.py # 计算净申购 → data/etf_daily_flows.csv
python validate_and_report.py  # 验证 → ETF_*.{csv,md}
python plot_curve.py           # 出图
```

## 边界

研究实验，不修改平台正式代码、不写生产库、不部署、不接信号。
不使用 Tushare。所有数据为公开可追溯来源。
