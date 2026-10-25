# P1D_TRADEABILITY_AUDIT — 历史可交易池与回测资格 Gate

**契约版本**：`tradeability_pit_v1` ｜ **范围**：只读审计层；未修改任何生产策略成交/准入逻辑。

## 复用而非重建（任务书硬性约束核验）

| 需求 | 复用的既有设施 | 未新建 |
|---|---|---|
| 交易日历 | `market.trading_calendar`（SH/SZ 1990→2027-02，8,928 行/所） | ✓ |
| 股票状态 PIT | `core.asset_status_daily`（17,294,002 行 / 5,213 资产 / 1990→2026-10-23；is_trade/is_st/is_suspended/is_limit_*/限价，477,509 停牌日、588,139 ST 日） | ✓ |
| 上市/退市窗口 | `core.asset_master.list_date/delist_date`（13 只真实退市股含摘牌日）+ `core.asset_lifecycle_event` | ✓ |
| 执行门 | `backtest_constraints.can_open_long/can_close_long`（suspended/limit-up-buy/limit-down-sell 阻断，可配置 min_amount） | ✓ |
| 板块/涨跌停分类 | `lhb_eligibility` regime  taxonomy（star/chinext/beijing/st/main + listing_no_limit） | ✓ |
| 复权/因子缺口 | `factor_gap_155_reconciliation.json` 终态清单 → `data_quality_blocks` | ✓ |

**新增的唯一层**：`src/stock_research/tradeability.py` —— 只读编排层 + 按生效日期解析的 `LIMIT_RULES` 规则表（`historical_rule_sources.csv` 为官方来源索引）。`asset_status_daily` 的 `is_limit_*` 用静态现行阈值构建（`core_data.py:467-472`），无日期感知 → 必须由生效规则重算，存储标志只作对照（见 `REGRESSION_DIFF.md`）。

## `tradeability_at` 接口（P0-4）

`tradeability_at(ctx, side, data_version, policy)` / `load_tradeability_context(conn, asset_id, trade_date)`（只读 SQL）。输出 8 个要求维度 + 附加字段：

- `eligible_for_universe` — 上市窗口内且交易所开市（list_date ≤ d ≤ delist_date；**PIT 用 list/delist 日期，不用 `is_active` 当前态回写历史**，存活偏差防护）
- `data_ready_daily` / `data_ready_minute` — 与该日 bar/分钟行存在性 + `data_quality_blocks`（如 `minute_factor_gap`）挂钩，与池资格互相独立
- `can_attempt_buy` / `can_attempt_sell` — 复用现有执行门，输入为**生效规则重算的** limit 状态
- `restriction_reasons` / `status_source` / `effective_date` / `rule_version` + `limit_regime` / `limit_rule_id` / `stored_flag_disagrees` / details

**保守成交假设（可配置 `ExecutionPolicy`）**：涨停日阻断买、跌停日阻断卖、停牌阻断双向；排队成交能力无法证实时输出受限而非默认可成交；不把"到价"等同"必然零成交"，也不假设涨停挂单必然成交。

## 历史规则核验（P0-2/P0-3）

`historical_rule_sources.csv` —— 9 条规则全部带官方文号/链接/生效日期：

- 创业板 ±10%（→2020-08-21）→ ±20%（2020-08-24 起，深证上〔2020〕515 号，新股前5日无涨跌幅）
- 科创板 ±20%（2019-07-22 开市，上证发〔2019〕23 号，新股前5日无涨跌幅）
- 北交所 ±30%（2021-11-15 开市，首日无涨跌幅）
- 主板 ST ±5%（风险警示板）；**创业板/科创板 ST 股适用板块 20% 而非 5%**
- 主板注册制分界 2023-04-10：此前新股首日 +44%/-36% 上限；此后**前5日无涨跌幅**（DB 实证：001312 首日 +66.32%）
- 停牌/退市整理期规则行

**已审计的 PIT 覆盖**：13 只真实退市股（688287 退市观典 2026-06-10、000638 *ST万方 2026-06-03 等）list/delist 齐全；`asset_status_daily` is_st 按日 PIT（同日 LHB 名或 bar is_st，不回写）；停牌 = `trade_status<>'1'`（区分"非交易日无 bar"与"停牌日有状态行"）。

## 对抗验收（P0-5）—— 全过

`tests/test_tradeability_p1d.py` **22 PASS**：上市前/退市后/ST按当时日/停牌/涨停买/跌停卖/制度变更前后/IPO窗口/幂等/FACTOR_GAP不自动解封/存活偏差/维度独立性。

`tradeability_edge_cases.json` —— **真实 DB 案例 12/12 pass**，含：
- 688287 上市前一日 eligible=false / 摘牌后一日 eligible=false / 窗口内 eligible=true
- 600815 2018-01-02 → `st_main_5pct`
- 600126 2019-06-03 停牌 → 双向 can_attempt=false
- 600519 2015-04-16 涨停 → buy=false；2018-10-29 跌停 → sell=false
- **300001 2019-03-11 +10.02% → 历史规则判涨停 buy=false 且 stored_flag_disagrees=true（存储说非涨停）**；2020-08-25 同幅度 → 非涨停 buy=true
- 688808 STAR IPO +875.82% / 001312 主板注册制 IPO +66.32% → `ipo_no_limit_window`，不误套普通规则
- 603213（终态因子缺口）→ `data_ready_minute=false` + `residual_factor_gap_minute`，features pinned 不解封

## 已知边界（诚实声明）

1. `asset_status_daily.is_limit_*` 静态阈值缺陷已量化但**未修复**（只读约束）——28,205 + 1,305 行分歧见 REGRESSION_DIFF；下游审计应以重算结果为准。
2. 退市整理期 ±10% 规则已入表，但"处于退市整理期"的判定依赖 status 表 is_st/名称与 master delist 窗口近似——无专门整理期标志列，个股在整理期内的特殊可成交性需要逐案复核。
3. 临停（盘中临时停牌）粒度为分钟级，本层以日频状态判定；日内部分时段可成交的精修属 P2。
4. `listing_age_trading_days` 由调用方传入（IPO 案例显式置 1）；批量回测接入时按日历会话数计算。
5. 队列微观成交（排队位置/封单量）平台无数据——一律按受限处理，这正是保守假设存在的意义。

## 结论：**P1d = PASS（限定）**

- 统一 PIT 资格能力已建（复用现有设施，非平行机制）
- 三维度分离、规则按生效日期、保守可配置、对抗测试全过、真实案例全过
- "限定"：存储 limit 标志的历史缺陷未修（属下游 P2 修复项，非本任务书范围）；退市整理期/临停粒度有上述边界
