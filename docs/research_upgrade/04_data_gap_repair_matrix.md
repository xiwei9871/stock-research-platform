# DATA-01-R1 数据缺口核实与修复矩阵（2026-10-20，只读核查）

时间口径：host=DB=Asia/Shanghai，业务日 2026-10-20（盘点文档日期已更正）。

## 任务一：2026Q2 利润表缺失 — 已定位

**真实缺口**（report_period='2026-06-30'）：

| 表 | Q1-2026 覆盖 | Q2-2026 覆盖 | 缺口 |
|---|---|---|---|
| income_statement | 5,211 股 / 5,244 行 | **0 股 / 0 行** | ~5,211 全市场 |
| balance_sheet | 5,212 股 | 1,131 股 (21.7%) | ~4,081 |
| cash_flow | 5,212 股 | 1,131 股 (21.7%) | ~4,081 |
| indicator_quarter | →03-31 | 0 | ~5,211 |

**断链取证**：
- `balance_sheet`/`cash_flow` 最后写入 2026-08-28 01:05–02:19（akshare_em 1,128 + akshare_sina 90）——一次**跑到 22% 中断**的采集
- `income_statement` 最后写入 2026-08-03（baostock 小额 37 行）；主批次 akshare_em_profit_sheet 写于 07-09（Q1 5,207 股）
- 采集器：`sync-baostock-finance --year --quarter`（income+indicator+share_capital）；`akshare_finance_statements`（balance+cash）；`sync_em_profit_sheet_gap_assets`（EM 利润表，逐股全历史）
- `ingest.backfill_task` / `ops.data_run_manifest` 均无财报采集记录 → **Q2 采集从未被调度**，纯遗漏非源端问题

**源端能力**：baostock 登录正常（20:47 实测），支持 `query_profit_data(code, year, quarter)`；EM 端点可用。补录范围：year=2026, quarter=2，全量 ~5,211 股。

## 任务二：复权因子 — 确认已产生错误价格 ⚠️ P0 实锤

**结构**：`market.adjustment_factor` 是派生表（`qfq.close/raw.close`），08-28 后停建；但**底层 `market_daily_bar` 的 qfq/hfq 行本身也是按日写入、从不回头修订** → 真正的缺口在底层价格。

**源端对拍实证**（baostock live vs 库存）：
- 600016 民生银行 09-15 除权：live qfq(09-14)=**3.59**，库存=**3.71==raw**（未调整）→ **3.3% 价格误差已落库**
- 601898 10-20 除权：hfq 当日收益 = raw 朴素收益 −2.54%（应为 −1.39%），除权未被吸收（当日属供应商正常延迟窗口，可后验）
- **窗口内探测到 369 只股票发生除权事件**（preclose≠prev_raw_close 法）→ 每只股票自除权日起的 qfq/hfq 历史在库内均为未调整旧值

**影响面**：
- `load_latest_adjustment_factors`（daily_close_pipeline 动态路径）基于库存日线 → 因子=1.0 → **qfq 分钟线 derive 在 369 股上实际=raw**，跨除权日收益断档
- 技术因子/回测若直接读库存 qfq 同样失真；raw 价格链不受影响
- `corporate_action`（派生自因子跳变）结构性缺 369 事件，随因子重建自动补齐
- `adjustment_factor` 表本身只需 `build_adjustment_factors(08-28→10-20)` 重跑（纯 SQL 派生、幂等）

**修复路径（待批准，写库）**：
1. 对 369 股按各自除权日重拉 baostock qfq+hfq 日线（单 session，~15-25min）
2. `build-adjustment-factors --start-date 2026-08-28`
3. `build-corporate-actions-from-factors`（自动捕获 369 事件）
4. 系统性防再发：日线任务加**滚动重写窗口**（如近 60 交易日），吸收供应商的滞后修订 —— 这才是根治，单次补录只是止血

## 任务二补充：R2 执行核验结论（2026-10-20 晚更新）

- **真实候选范围**：preclose 跳变检测（|preclose−prev_close|/prev>0.1%）2026-01-01→10-20 共 4,042 事件 / 3,317 股；其中 06-01 起 2,991 事件 / 2,643 股，1-5 月另有 1,054 事件 / 675 只窗口外独有股。
- **SQL 预筛**（除权日前 qfq==raw ⇒ 铁证污染）：3,318 事件股中 **3,043 CONFIRMED_DIRTY**、275 REVIEW；另有 50 只全年无事件对照股待 live 抽验。
- **修复窗口（5 股样本实证）**：qfq 需**全历史重写**（自上市日起，600016 首日行偏差 ~5%）；hfq 仅需自最早漏采事件日前向修（600016→07-02、600380→06-26、000568→08-28、600028→09-30、301237→09-01）。
- **漏采早于探测窗**：600016 另有 07-02 事件、600380 有 06-26 事件——探测窗必须从 01-01（或更早）起算，不能用 adjustment_factor 停建日。
- **架构归因**：库存 qfq/hfq 为 `derived:tushare_raw_latest_factor`（raw×因子快照），因子快照在漏采事件后=1.0 → 新写入行退化为 raw；同时底层行从不回头修订。
- **修复口径**：差异驱动只写变动行；raw 严禁改（`assert_no_raw_rows` 硬约束 + 测试）；`source='baostock_revision_r2'` 标记；`backup.market_daily_bar_r2_<batch>` 批次快照 + `r2_rollback_batch.py` 可回滚；后置 live 对拍必须 diff=0。
- **执行**：5 股样本已修（commit f206de1d 前的 ad-hoc 脚本）；首批 50 股分层批次 b1 已启动；live 分类脚本 `r2_classify_batch.py` 断点续跑兜底 REVIEW/对照组。
- **下游待重建**（修复完成后按序）：`adjustment_factor`（已随批 scoped 重建）→ `corporate_action`（已随批）→ 除权日前 qfq 分钟线分区 → `stock_technical_features_daily`；未完成前标记 DEGRADED。

## 任务三：Intraday 特征 — 方案已验证待批准

见 `03_intraday_recovery_validation.md`：隔离 compute 验证 PASS（两日 51,890/51,860 行，分布同量级、字节级幂等）；staging 08-04/05 试写 PASS。
**可执行范围**：2026-08-04 → 最新收盘日约 55 交易日，~52k 行/日 ×2 表，估算 <30min；建议先批 8-04→8-31（~20 日）验收一周再续。**待批准生产写**。

## 任务四：事件型数据 — 已逐表核实

| 表 | 判定 | 证据 |
|---|---|---|
| `asset_lifecycle_event` | **真漏 4 个上市事件** | 301583/001248/001399/688797（06-24→07-10 上市）不在表内；退市在 `asset_master.delist_date` 正常（13 起 04-30 后已标） |
| `corporate_action` | 派生表，369 事件缺失 | 随因子重建自动补齐，无独立采集器 |
| `share_capital_event` | 随 `sync-baostock-finance` Q2 一并补 | 同任务一 |

## 修复矩阵

| 数据集 | 缺失量 | 消费者 | 源端 | 成本 | 风险 | 优先级 | 补录范围 |
|---|---|---|---|---|---|---|---|
| income_statement | ~5,211 股 Q2 | 财务证据/护城河/打分 | baostock+EM 已验证 | ~1-2h 单 session | 低（upsert 幂等） | **P0** | 2026Q2 全量 |
| market_daily_bar qfq/hfq | 369 股 × 除权后历史 | 复权/分钟 derive/回测 | baostock 已验证 | ~25min | 中（改写历史行，需对拍验收） | **P0** | 369 股各自窗口 |
| adjustment_factor | 08-28→10-20 全日 | minute derive/Gate | 纯 SQL 派生 | ~min | 低 | P0(随上项) | 同上窗口 |
| intraday_features | ~55 交易日 | 盘中策略 | 已验证 | <30min | 低（staging 已验） | **P0(待批)** | 先批 08-04→08-31 |
| balance/cash_flow | ~4,081 股 Q2 | 财务证据 | akshare 已验证 | ~1h | 低 | P1 | 2026Q2 缺口股 |
| lifecycle_event | 4 上市事件 | 证券池 PIT | 源端核对即可 | 分钟级 | 低 | P1 | 4 行 |
| indicator_quarter | ~5,211 Q2 | 基本面指标 | 随 baostock finance | 同任务一 | 低 | P1 | 2026Q2 |
| share_capital_event | 同 Q2 | 股本证据 | 随 baostock finance | 同任务一 | 低 | P1 | 2026Q2 |
| stock_report_feature_daily | 07-23→今 ~3 月 | 研报特征 | 待查（派生） | 待定 | 中 | P1 | 评估后增量 |
| concept_membership | 历史仅 7 周 | 概念归属 | 待评估 | 待定 | 中 | P2 | 待定 |
| index_daily_bar | 仅 8 指数 | 指数对比 | 待评估 | 待定 | 低 | P2 | 待定 |
