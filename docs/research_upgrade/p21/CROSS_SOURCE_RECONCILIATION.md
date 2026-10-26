# P2.1-A 跨源对账精确核销（全量，无抽样冒充）

复现：`scripts/p21_reconciliation_audit.py` → `docs/research_upgrade/p21/cross_source_census.json`

## 更正此前报告

P2 报告的 "188,171 键跨源 revenue 不一致" 口径=收入字段存在**任何**差异（含 NULL 不对称与精度差）。全量精确分类如下：

## 全量口径（income_statement，akshare_em_profit_sheet × baostock）

- **双源键总数：230,363**（asset × report_period × report_type，两源均有行）
- 逐键最差类别：**conflict 227,321 / null_conflict 2,343 / unit_scale 699 / equal 0 / precision 0**

## 逐指标分类（关键归因）

| 指标 | equal | precision | unit_scale | conflict | null_conflict |
|---|---|---|---|---|---|
| revenue | 42,192 | 2,778 | 19 | **66,788** | **118,586** |
| net_profit | 211,223 | 1,425 | 28 | 17,653 | 34 |
| eps_basic | 114 | 4,536 | 819 | **224,449** | 445 |
| operating_profit | 5 | 0 | 0 | 0 | **230,358** |
| total_profit | 3 | 0 | 0 | 0 | 230,360 |
| np_parent | 60 | 1 | 0 | 65 | 230,237 |
| np_parent_deducted | 481 | 0 | 0 | 0 | 229,882 |

## 归因结论

1. **conflict 主体 = eps_basic 系统性差异**（224,449 键）：两源 EPS 口径/股本基数不同（如 0.12 vs 0.12225），非财报数值更正。
2. **revenue 66,788 真冲突**抽样归因（`PUBLICATION_ANOMALY_SAMPLES` 同级样本）：
   - 单位错标：akshare 元 vs baostock 百万元（比例≈10⁶，如 600016：42,060,000,000 vs 42,060）；
   - 零值/负号不对称（301419：2.0 亿 vs 0；600816：+22.8 亿 vs −8.5 亿）；
   - baostock 早期字段错位（2007–2011 期高比例出现，值与收入无合理比例关系）。
3. **null_conflict 118,586**：revenue 单源缺失——baostock 未覆盖该期收入字段（覆盖差异非冲突）。
4. **net_profit 一致率 91.7%**——两源底线科目基本相符；operating_profit/total_profit/np_parent* 几乎全为单源缺失（baostock 不填这些列）。

## 消费端含义

- `point_in_time_finance` 无 source 优先序 → 同键取行随 ann/period 排序漂移；**revenue/EPS 类因子不可复现**（net_profit 类因子基本稳定）。
- 建议契约：三表首选 `akshare_em`（含 profit_sheet 端点），baostock 仅作 indicator_quarter 来源。

## ann>period+180d 异常分层（不启动修正）

分层见 `PUBLICATION_ANOMALY_SAMPLES.csv`：`akshare_em_profit_sheet` 独占该异常（baostock 无），FY+Q 混合，ann 集中于**次年**（period 2009→ann 2010 峰值 5,284）。抽样样品的 `all_versions` 显示同键仅这一条 akshare 行——**EM 端点记录的是该期数字最近一次再披露日，非初始披露日**。语义坐实：这些行的 announcement_date 是再披露时间，初始披露时间已丢失 → 属 `historical_version_missing` 类，不应作"披露极晚"解读，不批量修正。

## Q2 14 只证据等级（`q2_evidence_levels.json`）

- 13 只：`L2_db_delist_plus_source_absent`（asset_master 退市日坐实 + EM 断供事实 + recon 记录）；**未独立核实公告事实**——不声称披露与否；
- 002731：`L3_external_announcement`（公司未按期披露公告 + 深交所终止上市决定，recon 存档证据）。
