# DATA_MANIFEST — R1 数据版本与来源清单

## 输入数据（复用 POC-02.1/03 已验证产物，未重新抓取）

| 文件 | SHA256(前16) | 说明 |
|---|---|---|
| `../etf_flow_poc02/data/etf_daily_flows_v2.csv` | 6852cce22c7c257a | 1,096,214 行基金×日份额/NAV/流量主表（2020-01-02~2026-10-27）。源：上交所/深交所 ETF 日份额 + 天天基金单位净值 |
| `../etf_flow_poc02/data/index_daily.csv` | f6f852ba73a35fb5 | 上证/深成/中证全指日线，1,650 交易日对齐 |
| `../etf_flow_poc02/data/corp_review_raw.csv` | 794bda17a48cd479 | POC-02.1 异常审核底表 |

## R1 生成数据

| 文件 | 说明 |
|---|---|
| `ETF_UNIVERSE_AND_GROUPS.csv` | 1,431 只基金→互斥主题组（G1_sector_other/G2/G3/G4k/G5/G6/G7/G8/non_equity），按名称关键词归类，可追溯 |
| `data/corp_action_audit.csv` | 148 个份额/NAV 跳变候选事件审计（份额比率、NAV 比率、跨日/同日类型、处置字段） |
| `data/fund_day.parquet` | 基金×日明细（flow_yi 原始 / flow_use 修正 / mv / nav_ret / corp 掩码 281 行） |
| `data/group_daily_raw.parquet`、`data/group_idx_ret.parquet` | 组级流量/AUM 与板块代理收益 |
| `data/factors_*.parquet` | 9 组因子帧（i1/i5/i10/i20/z20/z20_mad/acc/fwd_ret*/fwd_mdd*/状态变量） |

## 获取方法可复现性

- 份额/NAV/持有人：POC-01/02 抓取管线（仓库 `docs/research/etf_flow_poc02/` 历史脚本），本轮未重抓。
- 指数：`../etf_flow_poc02/fetch_index.py`（新浪 + 中证指数官网接口）。
- R1 全链路：`build_dataset.py` → `analyze_r1.py` → `plot_r1.py`，在 `.venv` 下按序执行可重建全部 CSV/PNG。

## 外部核实来源（非数据文件）

- 510310 份额合并公告：易方达公告（2024-09-18 前后）+ 上交所披露 `510310_20240923_G18B.pdf`（合并结果：比例 0.49977589，场内 62,347,244,017 份，净值 3.2021 元）。

## 大小说明

fund_day.parquet 约 49MB 为最大中间产物；未向 Git 重复提交数百 MB 原始抓取数据，主表以 POC-02 目录既有文件为准，本目录仅存派生与审计数据。
