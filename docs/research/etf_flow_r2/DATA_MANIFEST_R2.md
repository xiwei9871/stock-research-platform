# DATA_MANIFEST_R2 — 数据版本与来源

## 输入（复用，未重抓）

| 文件 | 哈希/来源 |
|---|---|
| `../etf_flow_r1/data/fund_day.parquet` | R1.1 基金×日（公司行为分层掩码，sha 见该目录 git 记录） |
| `../etf_flow_r1/data/factors_*.parquet` | R1.1 组级因子（F1/F5-F60/z20/fwd_*） |
| `../etf_flow_r1/ETF_UNIVERSE_AND_GROUPS.csv` | G2 修正后分组（510050→G9） |
| `../etf_flow_r1/data/sector_index_real.csv` | 上证50/科创50（全期）+中证主题（至2024-06） |
| `../etf_flow_poc02/data/index_daily.csv` | sha f6f852ba…（沪深300/全A） |

## R2 生成

`POLICY_EVENTS.csv`（人工整理，含 URL/置信度）、`data/factors_*.parquet`（追加 pos/neg_streak、accel、policy_on）、`LAG_RESPONSE_RESULTS.csv`、`FLOW_EVENT_RESULTS.csv`、`POLICY_REGIME_RESULTS.csv`、`OOS_SEGMENTS.csv`、`FALSE_POSITIVE_AUDIT.csv`、7 PNG、`etf_flow_r2_interactive.html`（5.6MB 自含 plotly）。

## 复现

`.venv` 下依序：`../etf_flow_r1/detect_corp_actions.py` → `build_dataset.py` → `analyze_r1.py` → 本目录 `analyze_r2.py` → `plot_r2.py` → `build_html.py`。
