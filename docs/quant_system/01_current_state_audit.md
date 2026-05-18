# 当前量化系统审计

本文基于当前仓库 `/Users/xiwei/stock_research` 的真实文件结构进行审计，不访问真实 PostgreSQL，不对外部仓库进行 clone。数据库现状部分以 `src/stock_research/schema.py`、CLI、测试用例和本地文档为依据，描述的是“代码已声明并已接线的能力”，不是对线上库内容量的实测结论。

## 1. 当前仓库已有能力总览

当前仓库已经不是原型脚手架，而是一个已经具备研究闭环雏形的 A 股中低频研究系统，主骨架包括：

- 数据层与 schema：
  `src/stock_research/schema.py`、
  `src/stock_research/db.py`、
  `src/stock_research/core_data.py`、
  `src/stock_research/corporate_actions.py`、
  `src/stock_research/dimensions.py`
- CLI 总入口与批处理：
  `src/stock_research/cli.py`、
  `src/stock_research/ingest_jobs.py`、
  `src/stock_research/backfill_runs.py`
- 因子与评分：
  `src/stock_research/factor_pipeline.py`、
  `src/stock_research/factor_store.py`、
  `src/stock_research/factor_config.py`、
  `src/stock_research/scoring/`
- 标签与基础特征：
  `src/stock_research/features.py`、
  `src/stock_research/labels.py`、
  `src/stock_research/technical_feature_store.py`、
  `src/stock_research/technical_features.py`
- 因子评估与 gate：
  `src/stock_research/factor_eval/`、
  `src/stock_research/factor_eval_batch.py`、
  `src/stock_research/factor_eval_store.py`
- 回测：
  `src/stock_research/backtest.py`、
  `src/stock_research/vectorized_topn_backtest.py`、
  `src/stock_research/portfolio_backtest.py`、
  `src/stock_research/retention_backtest.py`
- 行业/市场状态研究：
  `src/stock_research/industry_focus_score.py`、
  `src/stock_research/industry_focus_v2.py`、
  `src/stock_research/industry_mainline_regime.py`、
  `src/stock_research/industry_regime_gated_backtest.py`、
  `src/stock_research/industry_exposure_risk_control.py`
- 龙虎榜/龙头研究：
  `src/stock_research/lhb_data.py`、
  `src/stock_research/dragon_case_library.py`、
  `src/stock_research/dragon_strategy_research.py`
- 日报与工作流：
  `src/stock_research/reports/`、
  `src/stock_research/daily_pipeline.py`、
  `src/stock_research/daily_incremental.py`、
  `src/stock_research/research_workflow.py`
- 测试：
  `tests/` 下已有大量模块化测试，覆盖 schema、因子、回测、日报、行业研究、分钟线、技术特征等。

结论：当前仓库适合继续演进，不建议拆新仓库重写。

## 2. 数据层现状

### 2.1 数据接入与标准化

已有数据接入与标准化模块如下：

- 资产与核心维表：
  `src/stock_research/assets.py`、
  `src/stock_research/core_data.py`、
  `src/stock_research/dimensions.py`
- 日线/指数/行业：
  `src/stock_research/market_data.py`、
  `src/stock_research/loaders/baostock_ingestion.py`
- 财务：
  `src/stock_research/loaders/baostock_finance_ingestion.py`、
  `src/stock_research/loaders/akshare_finance_loader.py`、
  `src/stock_research/loaders/akshare_finance_statements.py`、
  `src/stock_research/services/point_in_time_finance.py`
- 分钟线：
  `src/stock_research/minute_data.py`、
  `src/stock_research/minute_backfill.py`、
  `src/stock_research/minute_backfill_adapter.py`
- 公司行为：
  `src/stock_research/corporate_actions.py`
- 行业/指数成分：
  `src/stock_research/services/index_universe_service.py`、
  `src/stock_research/services/industry_membership_service.py`

### 2.2 数据层已经具备的特征

- 已经采用 PostgreSQL 作为研究主库，代码通过 `service=stock_research` 连接，不在代码里硬编码密码：
  `src/stock_research/config.py`
- 已区分原始层、核心层、市场层、财务层、因子层、回测层、ingest 层：
  `src/stock_research/schema.py`
- 已支持批量 ingest/backfill/job 跟踪：
  `src/stock_research/ingest_jobs.py`、
  `src/stock_research/backfill_runs.py`
- 已支持分钟线分区表：
  `src/stock_research/schema.py`

### 2.3 数据层当前不足

- 没有形成统一的 “Data Layer contract” 文档化接口。
- `public.*` 旧表与 `core/market/factor/...` 新 schema 并存，存在双轨结构。
- watchlist、portfolio_position、trade_log、announcement、news、northbound_flow、capital_flow 等目标表尚未形成统一数据层设计与实现。

## 3. 数据库 schema 现状

### 3.1 已声明的核心 schema

`src/stock_research/schema.py` 已声明并维护以下主要 schema：

- `core`
- `market`
- `finance`
- `factor`
- `backtest`
- `ingest`
- `raw_akshare`
- `raw_baostock`
- `staging`

### 3.2 已声明的主要表

代码中已经明确声明的主要表包括：

- `core.asset_master`
- `core.asset_status_daily`
- `core.asset_lifecycle_event`
- `core.industry_membership`
- `market.index_daily_bar`
- `market.index_constituent`
- `market.trading_calendar`
- `market.adjustment_factor`
- `market.corporate_action`
- `market.industry_daily_bar`
- `market.stock_minute_bar`
- `market.minute_bar_backfill_job`
- `finance.income_statement`
- `finance.balance_sheet`
- `finance.cash_flow`
- `finance.indicator_quarter`
- `finance.share_capital_event`
- `raw_akshare.finance_payload`
- `raw_baostock.finance_payload`
- `raw_baostock.daily_bar_payload`
- `raw_baostock.industry_snapshot_payload`
- `ingest.batch_job`
- `ingest.batch_event`
- `ingest.backfill_run`
- `ingest.backfill_task`
- `factor.factor_daily`
- `factor.stock_score_daily`
- `factor.stock_technical_features_daily`
- `factor.stock_intraday_features_daily`
- `factor.industry_intraday_features_daily`
- `factor.factor_eval_run`
- `factor.factor_approval`
- `market.lhb_top_list_daily`
- `market.lhb_top_inst_daily`
- `factor.lhb_event_features_daily`

### 3.3 PIT 相关优点

当前 schema 已经开始考虑 point-in-time 约束：

- 财务表显式保存 `report_period` 与 `announcement_date`：
  `src/stock_research/schema.py`
- `services/point_in_time_finance.py`、`services/finance_ttm.py` 说明仓库已在向 PIT-safe fundamentals 靠拢。
- `README.md` 已明确写出 “announcement_date <= trade_date” 的 future-function 约束。

### 3.4 schema 层当前不足

- 还缺少目标架构中提到的独立表：
  `watchlist`、`portfolio_position`、`trade_log`、`valuation_daily`、`news`、`announcement`、`northbound_flow`、`capital_flow`、`limit_status`、`suspension`、`st_status` 等。
- 现有 `core.asset_status_daily` 已经承载了部分 ST/停牌/涨跌停状态，但尚未拆出更完整、可追溯的状态层。
- `public.asset_master`、`public.market_daily_bar`、`public.feature_snapshot`、`public.label_snapshot` 等旧研究表仍在系统内使用，未来需要减少新功能继续落在 `public`。

## 4. 数据源现状：baostock、akshare、tushare 预留情况

### 4.1 baostock

当前仓库对 `baostock` 的依赖最深，属于正式接入数据源：

- 日线、指数、行业成分：
  `src/stock_research/loaders/baostock_ingestion.py`
- 财务：
  `src/stock_research/loaders/baostock_finance_ingestion.py`
- 分钟线：
  `src/stock_research/minute_data.py`、
  `src/stock_research/minute_backfill.py`
- 原始 payload 落库：
  `raw_baostock.*` 表定义位于 `src/stock_research/schema.py`

结论：`baostock` 是当前主数据源之一。

### 4.2 akshare

当前仓库对 `akshare` 的接入主要在“补充数据”和“原始财务/龙虎榜样本导入”侧：

- 财务：
  `src/stock_research/loaders/akshare_finance_loader.py`
  `src/stock_research/loaders/akshare_finance_statements.py`
- 龙虎榜：
  `src/stock_research/lhb_data.py`
- 依赖声明：
  `pyproject.toml`

结论：`akshare` 已经是正式依赖，但更多用作补充而非唯一主源。

### 4.3 tushare

当前仓库对 `tushare` 处于“部分预留和局部使用”状态：

- `market.stock_minute_bar.source` 枚举中已预留 `tushare`：
  `src/stock_research/schema.py`
- `src/stock_research/lhb_data.py` 中存在 `build_tushare_client()`，并通过环境变量 `TUSHARE_TOKEN` 使用 Tushare Pro 做龙虎榜样本导入。

结论：`tushare` 目前不是全仓库主数据源，更像局部接口预留和 LHB 辅助源。

## 5. 因子层现状

### 5.1 因子实现结构

当前仓库已经形成“因子计算模块 + 因子落库 + 评分”的主结构：

- 因子配置：
  `src/stock_research/factor_config.py`
- 因子流水线：
  `src/stock_research/factor_pipeline.py`
- 因子存储与评分：
  `src/stock_research/factor_store.py`
- 因子实现目录：
  `src/stock_research/factors/`

### 5.2 当前已有因子类别

`src/stock_research/factors/` 下已经存在：

- `momentum.py`
- `trend.py`
- `volume_price.py`
- `risk.py`
- `sector.py`
- `growth.py`
- `quality.py`
- `value.py`
- `alpha101.py`
- `gtja191.py`
- `qlib_alpha.py`

### 5.3 当前评分与配置方式

当前评分主要基于手工配置：

- `manual_v1_config()` 中定义了：
  `factor_groups`、`factor_directions`、`weights`
- `candidate_factor_names()` 给出候选因子名列表
- `factor.stock_score_daily` 保存截面打分结果

相关文件：

- `src/stock_research/factor_config.py`
- `src/stock_research/factor_store.py`
- `src/stock_research/scoring/`

### 5.4 因子层优点

- 已经具备多类技术面/量价/行业/外部 alpha 因子。
- 已经具备因子落库和评分落库，而不是只停留在 notebook。
- 已经有 `factor.factor_approval` 机制，为“候选因子 -> 审批通过 -> 纳入评分”提供了雏形。

### 5.5 因子层明显缺口

- 还没有统一的 factor registry / metadata registry。
- 因子元数据还散落在 `factor_config.py`、模块命名、测试文件中，没有单一真相源。
- `growth.py`、`quality.py`、`value.py` 已存在，但主流水线 `build_and_store_factor_daily()` 当前主要接了 technical、sector、external alpha，基本面因子尚未完整接入主日频因子流。
- 尚未接入 TA-Lib / pandas-ta 统一技术指标接口，现有技术指标多为手写。

## 6. 因子评估现状

### 6.1 已有评估能力

当前仓库已具备较完整的因子评估雏形：

- 基础合并与准备：
  `src/stock_research/factor_eval/base.py`
- IC / RankIC：
  `src/stock_research/factor_eval/ic.py`
- 分组收益：
  `src/stock_research/factor_eval/quantile_return.py`
- 换手：
  `src/stock_research/factor_eval/turnover.py`
- 暴露分析：
  `src/stock_research/factor_eval/exposure.py`
- 多周期：
  `src/stock_research/factor_eval/multi_horizon.py`
- 阶段/分段：
  `src/stock_research/factor_eval/period.py`
  `src/stock_research/factor_eval/segment.py`
- 报告组装：
  `src/stock_research/factor_eval/report.py`
- gate 与审批：
  `src/stock_research/factor_eval/gate.py`
  `src/stock_research/factor_eval_batch.py`
  `src/stock_research/factor_eval_store.py`

### 6.2 已有持久化能力

- `factor.factor_eval_run`
- `factor.factor_approval`

相关定义：

- `src/stock_research/schema.py`
- `src/stock_research/factor_eval_store.py`

### 6.3 当前不足

- 缺少统一输出规范，例如固定的 `factor_validation_report.md`、`factor_evidence.json`、标准 run_card。
- 未来函数检测还没有上升为因子评估层统一门禁。
- 样本外、按市场状态分层、中性化方式的标准化流程还没有形成单一入口。

## 7. 回测层现状

### 7.1 TopN 规则回测

`src/stock_research/backtest.py` 提供了较早期的规则型 TopN 回测框架，已经考虑：

- `next_trade_date`
- `apply_buy_filter`
- `sell_bar_for_holding`
- ST / 停牌 / 流动性过滤
- 涨停开盘买不进的基础约束

### 7.2 向量化 TopN 回测

`src/stock_research/vectorized_topn_backtest.py` 提供了更现代化的向量化回测：

- `VectorizedTopNConfig`
- `VectorizedTopNResult`
- 支持 `daily` / `weekly` 调仓
- 支持 `transaction_cost_bps`
- 输出 `equity_curve`、`positions`、`trades`、`summary`

### 7.3 Portfolio 回测

`src/stock_research/portfolio_backtest.py` 已经具备账户级模拟：

- 初始资金
- 按 lot size 买入
- 分批建仓
- 资金曲线
- 回撤
- 交易明细

### 7.4 Retention 回测

`src/stock_research/retention_backtest.py` 当前是最接近“持仓跟踪/观察池逻辑”的模块：

- `RetentionConfig`
- `RetentionResult`
- entry topN / observe topN
- MA20 退出
- hard entry filters
- market/board entry filters
- stop loss
- open positions / pending buys / 持仓延续

### 7.5 回测层当前不足

- 还没有统一 run_card / reproducibility contract。
- 真实交易约束仍不完整：
  滑点、印花税、跌停卖不出、行业权重上限、单票权重上限、停牌跨日处理、涨跌停不可交易状态还没有统一收口到一个回测层规范。
- 旧 `backtest.py` 与 `vectorized_topn_backtest.py`、`portfolio_backtest.py`、`retention_backtest.py` 并行发展，边界还不够清晰。

## 8. 行业/市场状态研究现状

当前仓库在这部分已经形成明显的研究积累：

- 行业强度与 focus score v1：
  `src/stock_research/industry_focus_score.py`
- 行业 focus score v2、浓度/过热/候选密度诊断：
  `src/stock_research/industry_focus_v2.py`
- 市场 regime 诊断与主线行业打分：
  `src/stock_research/industry_mainline_regime.py`
- regime gated backtest：
  `src/stock_research/industry_regime_gated_backtest.py`
- 行业暴露与风控：
  `src/stock_research/industry_exposure_risk_control.py`
- 行业误差与诊断：
  `src/stock_research/industry_factor_audit.py`

当前已经覆盖的研究主题包括：

- 行业热度
- 行业集中度
- 候选池密度
- mainline / rotation / weak_market 等 regime 识别
- 行业权重调整与软门控回测

当前不足：

- 尚未沉淀为统一的 `Regime Layer` 接口。
- 市场状态指标与报告输出还未完全统一到 daily screener / watchlist 流程中。
- 大盘成交额、涨停数量、跌停数量、炸板率、连板高度等短线环境字段未见完整统一表层。

## 9. 龙虎榜/龙头研究现状

### 9.1 龙虎榜

`src/stock_research/lhb_data.py` 已经具备：

- Tushare / AkShare LHB 样本导入
- `market.lhb_top_list_daily`
- `market.lhb_top_inst_daily`
- `factor.lhb_event_features_daily`
- LHB 对齐审计
- LHB 风险特征诊断
- 失败规则覆盖计划

### 9.2 龙头/案例库

`src/stock_research/dragon_case_library.py` 已经不是小工具，而是独立研究子系统：

- seed 构建
- web seed 扩展
- source evidence
- case library build / diagnose
- failure event rule v2 / v2.1
- source backfill workpack / check report

### 9.3 龙头策略研究

`src/stock_research/dragon_strategy_research.py` 已经具备：

- `DragonResearchConfig`
- 龙头分数与角色划分
- 弱候选审计
- score bucket effectiveness
- entry window effectiveness
- role cross effectiveness
- 多个 v1.x 迭代输出

### 9.4 当前不足

- 该子系统研究深度很高，但与主因子/主选股/主回测体系的接口仍偏松散。
- 目前更像专题研究模块，还没有抽象为主系统中的“事件特征层”或“龙头观察层”。

## 10. 日报与工作流现状

### 10.1 日频流水线

- `src/stock_research/daily_pipeline.py`
- `src/stock_research/daily_incremental.py`
- `src/stock_research/research_workflow.py`
- `src/stock_research/research_preflight.py`

这些文件说明仓库已经有：

- preflight
- 日增量执行
- 分步骤 runner
- 因子/标签/评分/研究报告串联

### 10.2 日报模块

`src/stock_research/reports/` 已包含：

- `daily_topn_report.py`
- `market_state_report.py`
- `sector_strength_report.py`
- `risk_alert_report.py`
- `position_review_report.py`
- `daily_report_bundle.py`
- `daily_research_report_workflow.py`
- `daily_research_report_cli.py`
- `daily_research_cron.py`

### 10.3 通知与调度

- Feishu / OpenClaw 通知：
  `src/stock_research/feishu_notify.py`
- 各类 watchdog：
  `src/stock_research/minute_backfill_watchdog.py`
  `src/stock_research/technical_feature_watchdog.py`
  `src/stock_research/factor_gate_watchdog.py`
  `src/stock_research/factor_backfill_watchdog.py`

### 10.4 当前不足

- 报告层已有 TopN、市场状态、风险提醒，但还没有独立的 watchlist 盯盘报告工作流。
- AI Agent 角色化报告还没有独立层。
- run_card / evidence trail 没有成为日报和回测的统一产物。

## 11. 测试覆盖现状

`tests/` 目录覆盖广度明显高于一般内部量化原型仓库，至少包括：

- schema 与数据层：
  `test_schema.py`、
  `test_assets.py`、
  `test_core_data.py`、
  `test_dimensions.py`
- 数据源与 ingest：
  `test_baostock_ingestion.py`、
  `test_baostock_finance_ingestion.py`、
  `test_akshare_finance_statements.py`、
  `test_ingest_jobs.py`
- 因子与评分：
  `test_factor_pipeline.py`、
  `test_factor_store.py`、
  `test_factor_config.py`、
  `test_alpha101_factors.py`、
  `test_gtja191_factors.py`、
  `test_qlib_alpha_factors.py`
- 因子评估：
  `test_factor_eval.py`、
  `test_factor_eval_gate.py`、
  `test_factor_eval_multi_horizon.py`、
  `test_factor_eval_exposure.py`、
  `test_factor_eval_store.py`
- 回测：
  `test_backtest.py`、
  `test_vectorized_topn_backtest.py`、
  `test_portfolio_backtest.py`、
  `test_retention_backtest.py`
- 行业研究：
  `test_industry_focus_v2.py`、
  `test_industry_mainline_regime.py`、
  `test_industry_regime_gated_backtest.py`
- 龙头/LHB：
  `test_dragon_case_library.py`、
  `test_dragon_strategy_research.py`、
  `test_lhb_data.py`
- 报告：
  `test_daily_topn_report.py`、
  `test_market_state_report.py`、
  `test_position_review_report.py`、
  `test_risk_alert_report.py`
- 日常工作流：
  `test_daily_pipeline.py`、
  `test_daily_incremental.py`、
  `test_research_workflow.py`

结论：测试覆盖“广度较好、深度不均衡”。当前缺的不是完全没有测试，而是缺少更统一的回测质量门禁、PIT 门禁和 run_card 级验收。

## 12. 当前系统最明显缺口

最明显的缺口不是“没有功能”，而是“缺少统一抽象与统一约束”：

1. 缺少统一 Universe 层。
2. 缺少统一 Factor Registry / metadata。
3. 缺少统一 run_card / evidence trail。
4. 缺少更完整的回测交易约束框架。
5. 缺少独立 watchlist 层和 watchlist 报告流程。
6. 缺少面向 “我 + AI Agent” 的角色化投研层。
7. 数据质量与 PIT 审计还偏分散，尚未形成标准报告体系。

## 13. 哪些模块建议保留

建议直接保留，并作为后续建设基座：

- schema 与 research DB 方向：
  `src/stock_research/schema.py`
- data ingestion / backfill / job tracking：
  `src/stock_research/ingest_jobs.py`
  `src/stock_research/backfill_runs.py`
  `src/stock_research/minute_backfill.py`
- factor eval：
  `src/stock_research/factor_eval/`
  `src/stock_research/factor_eval_store.py`
- vectorized / portfolio / retention backtest：
  `src/stock_research/vectorized_topn_backtest.py`
  `src/stock_research/portfolio_backtest.py`
  `src/stock_research/retention_backtest.py`
- industry regime 研究链：
  `src/stock_research/industry_focus_v2.py`
  `src/stock_research/industry_mainline_regime.py`
  `src/stock_research/industry_regime_gated_backtest.py`
- reports 与 daily workflow：
  `src/stock_research/reports/`
  `src/stock_research/daily_incremental.py`
- dragon / LHB 专题研究资产：
  `src/stock_research/dragon_case_library.py`
  `src/stock_research/dragon_strategy_research.py`
  `src/stock_research/lhb_data.py`

## 14. 哪些模块建议重构

建议重构，但不是推倒重来：

### 14.1 `factor_config.py`

问题：

- 当前承担了候选因子、方向、权重、组别等多种职责。
- 更像“手工评分配置”，不是统一 registry。

建议：

- 重构为 `factor registry + score config` 双层结构。

### 14.2 `factor_pipeline.py`

问题：

- 已经形成核心流水线，但目前主连接线偏向 technical/sector/external alpha。
- 基本面因子接入不完整。

建议：

- 重构为更清晰的 `loaders / factor calculators / registry / writer` 结构。

### 14.3 `backtest.py`

问题：

- 历史职责较多，和后来的向量化/账户/retention 回测存在重叠。

建议：

- 保留旧能力，但不要继续把新回测规则都塞进这个文件。

### 14.4 `quality.py` 与 `data_audit.py`

问题：

- 当前更像“基础巡检工具”，不是完整 Data Quality Layer。

建议：

- 重构成统一的质量报告框架。

### 14.5 `selection.py`

问题：

- 当前仍保留 `baseline_rules_v1` 风格的选股逻辑。
- 与 `factor.stock_score_daily`、`manual_v1_config` 存在双路径评分感。

建议：

- 后续统一收敛到 “factor store / screener / watchlist rule engine”。

## 15. 哪些模块暂时不要扩展

以下模块或方向暂时不要继续横向扩展：

### 15.1 旧 `public.*` 研究表

不要继续把新功能主要落到：

- `public.feature_snapshot`
- `public.label_snapshot`
- `public.selection_result`
- `public.backtest_*`

新建设应优先落在 `core / market / factor / backtest / ingest` 的新 schema 体系。

### 15.2 `backtest.py` 作为总回测入口的继续膨胀

不建议再把更多策略变体、行业门控、仓位规则都直接继续堆进 `src/stock_research/backtest.py`。

### 15.3 手工权重继续硬编码到 `manual_v1_config()`

不建议把未来更多因子、更多规则继续以手工字典方式直接堆入 `src/stock_research/factor_config.py`。

### 15.4 龙头/LHB 专题进一步脱离主系统

`dragon_case_library.py` 和 `dragon_strategy_research.py` 已经很深，不应继续单独扩张成另一套平行架构；后续应强调与主因子层、watchlist 层、报告层的接口整理。

### 15.5 过早重写成完整 Qlib 或 RQAlpha 克隆

当前仓库已经有自己的数据库与工作流骨架，不应在现阶段转向“重写框架本身”。

## 审计结论

当前仓库最值得保留的是：

- 研究数据库方向已经正确
- 因子评估与行业研究已经具备深度
- 回测已经有多个可复用基座
- 报告与日常工作流已经开始产品化

当前最需要补的是统一层：

- Universe Layer
- Factor Registry
- Run Card / Evidence Trail
- Backtest Quality Layer
- Watchlist Layer
- AI Agent Research Layer
- Data Quality / PIT Audit Layer

这意味着下一阶段不应该新建项目，而应该围绕当前仓库做“统一抽象、补关键缺口、减少双轨结构”的建设。
