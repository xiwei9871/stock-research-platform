# ETF-FLOW-POC-02 — 历史资金流口径校准与图表复验

独立研究实验（基线 POC-01 `f0e1532`）。不修改平台代码、不写生产库。

## 复现步骤

```bash
# 依赖 POC-01 原始数据：docs/research/etf_flow_poc01/data/（gitignored，
# 本地保留；如需重建先跑 poc01 的 fetch_* 脚本）
cd docs/research/etf_flow_poc02
.venv/bin/python compute_v2.py   # 重算流量面板 + 双分类 + 覆盖率 → data/
.venv/bin/python plot_v2.py      # 两张 PNG
# 交付 CSV 由 README 内联脚本或 compute 产物生成：
#   HOLDER_PIT_COMPARISON.csv / CORPORATE_ACTION_REVIEW.csv /
#   HISTORICAL_RECONCILIATION.csv
```

## 交付物

| 文件 | 内容 |
|---|---|
| `ETF_FLOW_POC02_AUDIT.md` | P0 四项口径修正、覆盖率、复核结论、P4 判断 |
| `METHODOLOGY_SENSITIVITY.md` | 国金图54 口径网格与最可能组合（推断标注） |
| `HOLDER_PIT_COMPARISON.csv` | 每基金 POC-01分类 / v2-fixed / v2-PIT 三列对照 |
| `CORPORATE_ACTION_REVIEW.csv` | 1003 条大额份额变动逐条 NAV 连续性判定 |
| `HISTORICAL_RECONCILIATION.csv` | 4 只沪深300ETF × 5 时点官方份额/净值/累计流量对账 |
| `etf_flow_poc02.png` | 主图：2020 起累计 × PIT 滚动分类双曲线 |
| `etf_flow_method_comparison.png` | 六宫格：窗口×分类口径对照（含 POC-01 原线） |
| `compute_v2.py` / `plot_v2.py` | 可重复脚本 |
| `data/` | 中间产物（gitignored）：流量面板、覆盖率、日度/累计分车道 |

## 相对 POC-01 的修正

1. 持有人分类取**真实最新**披露（修复 iloc[-1] 取到最早一期的缺陷），
   新增 PIT-rolling（披露截止日+90天生效）。
2. IPO 首日按上市核查判定，存量 5547 亿单列不入曲线；227 只
   数据缺失首现单独标记。
3. 1003 条大额变动经 NAV 连续性鉴别：746 真实申赎（POC-01 误删）、
   257 数据问题、0 公司行为。
4. 零流量与缺失值分列，缺失金额上界 ±15 亿。
