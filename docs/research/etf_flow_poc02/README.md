# ETF-FLOW-POC-02.1 — 原图口径纠偏与最终曲线校准

独立研究实验（基线 POC-02 `17fa470d`）。不修改平台代码、不写生产库。

POC-02.1 修正：图54 实际为 **2020–2026 长期累计、纵轴 +15000/−9000亿**
（POC-02 误识为 ±1500 亿）；异常处理改为四级鉴别（拆分/毛刺/待核验剔除）；
四只沪深300ETF 披露改用实际公告日期核验。

## 复现步骤

```bash
cd docs/research/etf_flow_poc02
.venv/bin/python compute_v2.py   # 重算流量面板 + 双分类 + 四级异常鉴别
.venv/bin/python plot_v2.py      # 两张 PNG（红虚线已改为+15000/−9000）
```

## 交付物

| 文件 | 内容 |
|---|---|
| `ETF_FLOW_POC02_AUDIT.md` | POC-02.1 纠偏审计：原图识别、四级异常鉴别、披露实际日期、未决清单、最终判断 |
| `METHODOLOGY_SENSITIVITY.md` | 按正确轴重估的口径敏感性（原 ±1500 推断作废） |
| `etf_flow_poc02.png` | 主图：2020起累计 × PIT滚动 × 二元口径 |
| `etf_flow_method_comparison.png` | 六宫格：fixed/PIT × 细分/二元 × POC-01 |
| `PEAK_VALLEY_COMPARISON.csv` | 各口径峰谷 vs 原图轴量级对照 |
| `CORPORATE_ACTION_REVIEW.csv` | 1003 条大额变动四级判定（10公司行为/105毛刺/85待核验/803申赎） |
| `REDEMPTION_2026_REVIEW.csv` | 四只沪深300ETF 2026 净赎回专项核验 |
| `HISTORICAL_RECONCILIATION.csv` | 5 时点份额/净值/累计流量对账（diff=0） |
| `HOLDER_PIT_COMPARISON.csv` | POC-01/fixed/PIT 三分类对照 |
| `ACTUAL_DISCLOSURE_DATES.csv` | 4 只基金历期报告实际公告日（天天基金公告 API） |
| `compute_v2.py` / `plot_v2.py` | 可重复脚本 |
| `data/` | 中间产物（gitignored） |

## 关键结论

- 机构持有为主 ETF：PIT 口径 2024-10 峰 +10,751 亿 → 2026-07 谷 −6,594 亿
  （摆动 17,345 亿），最接近原图 −9,000 轴量级；latest-fixed 谷 −3,269 偏浅。
- 个人/未分类车道 PIT 二元终点 +11,515 亿；与原图 +15,000 轴的剩余缺口
  归因于样本池/阈值（标注为未决差异）。
- 2026 年机构类大额净赎回为数据事实；**不得表述为特定机构主体减持**
  （主体无官方披露）。
