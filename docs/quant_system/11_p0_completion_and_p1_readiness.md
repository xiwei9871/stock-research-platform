# P0 Completion And P1 Readiness

## 一、阶段结论

### 1. P0 是否可以认为基本完成

可以。

更准确地说，`stock_research` 的 **P0 主链能力已经基本完成并可冻结**。  
目前已经具备：

- 统一 Universe 口径
- 统一 Data Quality 入口与 contract
- Factor Registry / metadata 单一真相源
- `quality + value` 基本面因子接入主 `factor.factor_daily`
- PIT snapshot / TTM / share-cap 口径
- `watchlist` schema / workflow / report / CLI
- `TopN / retention` 统一交易约束
- `run_card / evidence trail`
- `CLI / watchdog / technical feature` 收口
- 直接相关回归测试

### 2. P0 当前完成到什么程度

从能力建设角度看，P0 已达到 **“主链闭环、可冻结、可进入 P1”** 的状态。

从工程交付角度看，当前还存在两类收尾动作：

- 建议在进入 P1 前打一个 P0 baseline tag
- `docs/superpowers/*` 仍是未跟踪工作笔记，不属于 P0 baseline

因此当前更准确的说法是：

- **P0 基线能力已完成**
- **P0 工程冻结条件基本满足**
- **可进入 P1**

### 3. 当前系统的定位是什么

当前系统更适合被定位为：

> 一个面向 A 股量化研究的 P0 MVP 研究平台。

它已经具备：

- 数据质量检查
- 因子写入与评分主链
- Universe / Watchlist / Backtest / Report / Evidence 的基础闭环
- 统一交易约束与研究证据归档

它还不是一个自动投研代理平台，也不是自动交易系统。

### 4. 当前系统还不能做什么

当前系统仍然不能：

- 自动生成并分发完整 P1 报告交付链路
- 提供 AI Agent Research Layer
- 提供成熟的 portfolio / simulation 层
- 宣称 `quality + value` 因子已经具备稳定 alpha
- 直接给出实盘买卖结论
- 直接用于自动下单或自动交易

### 5. 是否建议进入 P1

建议进入 P1。

建议顺序是：

1. 冻结 P0 baseline
2. 可选打 tag：`p0-quant-research-mvp`
3. 进入 P1-1 `Report Delivery Adapter`

---

## 二、P0 已完成模块清单

### 1. Universe Layer

- 目标
  统一 A 股研究样本口径，让回测、筛选、报告、watchlist 使用一致的 universe 规则。
- 已完成能力
  - 统一 universe builder
  - CLI 入口
  - Top score 读取时支持 universe 过滤
  - 相关回测/上层工作流可复用同一服务
- 关键 commit
  - `ef49dfb`
  - `bc3d1fc`
  - `3378455`
- 关键文件
  - [src/stock_research/services/universe_service.py](/Users/xiwei/stock_research/src/stock_research/services/universe_service.py)
  - [src/stock_research/cli.py](/Users/xiwei/stock_research/src/stock_research/cli.py)
  - [src/stock_research/factor_store.py](/Users/xiwei/stock_research/src/stock_research/factor_store.py)
- 关键测试
  - [tests/test_universe.py](/Users/xiwei/stock_research/tests/test_universe.py)
  - [tests/test_factor_store.py](/Users/xiwei/stock_research/tests/test_factor_store.py)
- 当前状态
  P0 完成。
- 仍有限制
  - 更高层 portfolio / agent 层统一消费仍属于后续工作
  - 真实业务侧 universe 策略仍可持续演进

### 2. Data Quality Layer

- 目标
  将 `data_audit`、`finance_audit`、`research_preflight` 收敛成统一入口、统一状态语义和统一输出 contract。
- 已完成能力
  - 新增 `data_quality.py`
  - 统一 `ok / warning / blocked`
  - `data-quality` CLI
  - JSON / text 双输出
  - blocked window / derived window / industry-membership 失败路径统一 contract
- 关键 commit
  - `1626c79`
  - `6c2e9ad`
  - `cd1089a`
  - `fc13838`
  - `0f9a5f3`
  - `3e8f0b5`
  - `9e24f2b`
  - `84b9ce2`
  - `abe7a79`
- 关键文件
  - [src/stock_research/data_quality.py](/Users/xiwei/stock_research/src/stock_research/data_quality.py)
  - [src/stock_research/cli.py](/Users/xiwei/stock_research/src/stock_research/cli.py)
  - [src/stock_research/research_preflight.py](/Users/xiwei/stock_research/src/stock_research/research_preflight.py)
- 关键测试
  - [tests/test_data_quality.py](/Users/xiwei/stock_research/tests/test_data_quality.py)
  - [tests/test_factor_cli.py](/Users/xiwei/stock_research/tests/test_factor_cli.py)
  - [tests/test_data_audit.py](/Users/xiwei/stock_research/tests/test_data_audit.py)
  - [tests/test_finance_audit.py](/Users/xiwei/stock_research/tests/test_finance_audit.py)
  - [tests/test_research_preflight.py](/Users/xiwei/stock_research/tests/test_research_preflight.py)
- 当前状态
  P0 完成。
- 仍有限制
  - 真实数据库覆盖率与实际数据口径仍需持续 audit
  - `quality.py` 的日常写库检查尚未并入统一层

### 3. Factor Registry

- 目标
  建立因子 metadata 单一真相源，统一 `factor_group`、`direction`、`source`、availability 等约束。
- 已完成能力
  - 新 registry 文件
  - registry-driven `candidate_factor_names()`
  - mapping 校验
  - fundamentals metadata 补齐到 `quality + value`
- 关键 commit
  - `ee52387`
  - `38e072f`
- 关键文件
  - [src/stock_research/factor_registry.py](/Users/xiwei/stock_research/src/stock_research/factor_registry.py)
  - [src/stock_research/factor_config.py](/Users/xiwei/stock_research/src/stock_research/factor_config.py)
- 关键测试
  - [tests/test_factor_registry.py](/Users/xiwei/stock_research/tests/test_factor_registry.py)
  - [tests/test_factor_config.py](/Users/xiwei/stock_research/tests/test_factor_config.py)
- 当前状态
  P0 完成。
- 仍有限制
  - fundamentals 已注册不等于已进入当前 `manual_v1` 配权
  - 更广泛的 growth / validation lifecycle 仍在后续阶段

### 4. Factor Store Fundamentals

- 目标
  把 `quality + value` 以 PIT-safe 方式接入 `factor.factor_daily` 主写入链路。
- 已完成能力
  - `quality + value` registry 接入
  - batched PIT snapshot
  - share-cap 走 `finance.share_capital_event`
  - TTM 走 `finance_ttm`
  - restated filing 优先
  - merged row validation before upsert
  - 缺失 fundamentals 不阻断 technical/sector 因子构建
- 关键 commit
  - `12fad92`
  - `97edbf2`
  - `c4411b2`
  - `0edb9e1`
  - `3fea2e0`
  - `b4eb995`
  - `38e072f`
  - `a2af05c`
  - `8a4b22d`
- 关键文件
  - [src/stock_research/factor_pipeline.py](/Users/xiwei/stock_research/src/stock_research/factor_pipeline.py)
  - [src/stock_research/services/point_in_time_finance.py](/Users/xiwei/stock_research/src/stock_research/services/point_in_time_finance.py)
  - [src/stock_research/services/finance_ttm.py](/Users/xiwei/stock_research/src/stock_research/services/finance_ttm.py)
  - [src/stock_research/factor_registry.py](/Users/xiwei/stock_research/src/stock_research/factor_registry.py)
- 关键测试
  - [tests/test_factor_pipeline.py](/Users/xiwei/stock_research/tests/test_factor_pipeline.py)
  - [tests/test_point_in_time_finance.py](/Users/xiwei/stock_research/tests/test_point_in_time_finance.py)
  - [tests/test_finance_ttm.py](/Users/xiwei/stock_research/tests/test_finance_ttm.py)
  - [tests/test_factor_value.py](/Users/xiwei/stock_research/tests/test_factor_value.py)
  - [tests/test_factor_fundamental.py](/Users/xiwei/stock_research/tests/test_factor_fundamental.py)
- 当前状态
  P0 完成。
- 仍有限制
  - 因子能入库不等于已有稳定 alpha
  - `manual_v1` 仍未对 fundamentals 加权

### 5. Watchlist Workflow

- 目标
  建立独立 watchlist schema、signal/risk/workflow、report 与 CLI 主线。
- 已完成能力
  - watchlist storage schema / store
  - signal / risk / workflow
  - report writer
  - `watchlist-build` / `watchlist-report` / `watchlist-explain`
- 关键 commit
  - `fa47baf`
  - `7003ed6`
  - `869b6e8`
  - `659cd77`
  - `a6a834b`
  - `3787cfd`
  - `a39626d`
  - `267a0ea`
  - `14b56ff`
  - `b466723`
  - `9d4e688`
- 关键文件
  - [src/stock_research/watchlist/store.py](/Users/xiwei/stock_research/src/stock_research/watchlist/store.py)
  - [src/stock_research/watchlist/signals.py](/Users/xiwei/stock_research/src/stock_research/watchlist/signals.py)
  - [src/stock_research/watchlist/risk.py](/Users/xiwei/stock_research/src/stock_research/watchlist/risk.py)
  - [src/stock_research/watchlist/workflow.py](/Users/xiwei/stock_research/src/stock_research/watchlist/workflow.py)
  - [src/stock_research/reports/watchlist_report.py](/Users/xiwei/stock_research/src/stock_research/reports/watchlist_report.py)
- 关键测试
  - [tests/test_watchlist_store.py](/Users/xiwei/stock_research/tests/test_watchlist_store.py)
  - [tests/test_watchlist_signals.py](/Users/xiwei/stock_research/tests/test_watchlist_signals.py)
  - [tests/test_watchlist_workflow.py](/Users/xiwei/stock_research/tests/test_watchlist_workflow.py)
  - [tests/test_watchlist_report.py](/Users/xiwei/stock_research/tests/test_watchlist_report.py)
  - [tests/test_watchlist_cli.py](/Users/xiwei/stock_research/tests/test_watchlist_cli.py)
- 当前状态
  P0 完成。
- 仍有限制
  - 交付层仍停留在本地 artifacts / CLI
  - Agent 层解释与审阅尚未接入

### 6. TopN / retention constraints

- 目标
  统一回测交易约束，减少旧/新回测口径分叉。
- 已完成能力
  - shared `backtest_constraints.py`
  - vectorized TopN 接线
  - retention 接线
  - 成本/停牌/涨跌停/流动性/最终日处理一致化
- 关键 commit
  - `f025c0d`
  - `011fac2`
  - `19ef932`
  - `926c3b7`
  - `017656f`
  - `15e402f`
  - `0923abf`
  - `ec0ba30`
  - `c3e2510`
  - `85a2dfa`
  - `159f9c4`
- 关键文件
  - [src/stock_research/backtest_constraints.py](/Users/xiwei/stock_research/src/stock_research/backtest_constraints.py)
  - [src/stock_research/vectorized_topn_backtest.py](/Users/xiwei/stock_research/src/stock_research/vectorized_topn_backtest.py)
  - [src/stock_research/retention_backtest.py](/Users/xiwei/stock_research/src/stock_research/retention_backtest.py)
- 关键测试
  - [tests/test_backtest_constraints.py](/Users/xiwei/stock_research/tests/test_backtest_constraints.py)
  - [tests/test_vectorized_topn_backtest.py](/Users/xiwei/stock_research/tests/test_vectorized_topn_backtest.py)
  - [tests/test_retention_backtest.py](/Users/xiwei/stock_research/tests/test_retention_backtest.py)
  - [tests/test_strategy_lifecycle.py](/Users/xiwei/stock_research/tests/test_strategy_lifecycle.py)
- 当前状态
  P0 完成。
- 仍有限制
  - 更完整的 portfolio 层和更多样本外验证属于后续工作

### 7. run_card / evidence trail

- 目标
  为因子、回测、报告提供统一 evidence bundle / run_card 产物，提升可追溯性。
- 已完成能力
  - evidence bundle 强化
  - 多条主线输出统一 `run_card.*`
  - reports/backtests 可引用一致 evidence 结构
- 关键 commit
  - `e2243ed`
- 关键文件
  - [src/stock_research/run_card.py](/Users/xiwei/stock_research/src/stock_research/run_card.py)
  - [src/stock_research/report_run_store.py](/Users/xiwei/stock_research/src/stock_research/report_run_store.py)
- 关键测试
  - [tests/test_run_card.py](/Users/xiwei/stock_research/tests/test_run_card.py)
  - [tests/test_daily_research_report_cli.py](/Users/xiwei/stock_research/tests/test_daily_research_report_cli.py)
- 当前状态
  P0 完成。
- 仍有限制
  - 更高层 report delivery / agent 引用还未进入 P1

### 8. CLI / watchdog / technical feature 收口

- 目标
  收敛技术特征构建策略、watchdog 批处理优先级、CLI 暴露和调度行为。
- 已完成能力
  - technical feature watchdog 强化
  - 更快构建策略入口
  - CLI flag 暴露
  - launch interval 收紧
  - 研究窗口优先处理
- 关键 commit
  - `802ab1a`
  - `8e719b0`
  - `d2fdcd1`
  - `a82622f`
  - `c21f8dd`
- 关键文件
  - [src/stock_research/technical_feature_watchdog.py](/Users/xiwei/stock_research/src/stock_research/technical_feature_watchdog.py)
  - [src/stock_research/cli.py](/Users/xiwei/stock_research/src/stock_research/cli.py)
  - [docs/quant_system/10_technical_feature_performance_plan.md](/Users/xiwei/stock_research/docs/quant_system/10_technical_feature_performance_plan.md)
- 关键测试
  - [tests/test_technical_feature_watchdog.py](/Users/xiwei/stock_research/tests/test_technical_feature_watchdog.py)
  - [tests/test_technical_feature_store.py](/Users/xiwei/stock_research/tests/test_technical_feature_store.py)
  - [tests/test_factor_cli.py](/Users/xiwei/stock_research/tests/test_factor_cli.py)
- 当前状态
  P0 完成。
- 仍有限制
  - 算法层性能优化仍属于后续专项

### 9. tests / regression

- 目标
  让上述主链变更有稳定回归保护，避免只靠功能直觉推进。
- 已完成能力
  - 每个主线模块都有对应 targeted regression
  - 直接相关 full regression 已多轮通过
- 关键文件
  - [tests/test_data_quality.py](/Users/xiwei/stock_research/tests/test_data_quality.py)
  - [tests/test_factor_pipeline.py](/Users/xiwei/stock_research/tests/test_factor_pipeline.py)
  - [tests/test_watchlist_workflow.py](/Users/xiwei/stock_research/tests/test_watchlist_workflow.py)
  - [tests/test_backtest_constraints.py](/Users/xiwei/stock_research/tests/test_backtest_constraints.py)
- 关键测试
  - `112 passed` Data Quality closing regression
  - `145 passed` fundamentals / pipeline / CLI direct regression set
  - `131 passed` watchlist / pipeline / CLI regression set
- 当前状态
  P0 完成。
- 仍有限制
  - 仍以 mocked / unit-level regression 为主
  - 未覆盖真实 PostgreSQL 端到端全量场景

---

## 三、P0 Commit Baseline

| 模块 | commit hash | commit message | 作用 | 是否 P0 baseline |
|---|---|---|---|---|
| Universe Layer | `ef49dfb` | `feat: add unified universe layer` | 引入统一 universe 服务与口径 | 是 |
| Universe Layer | `bc3d1fc` | `fix: apply universe filtering before top score limit` | 修正 universe 过滤顺序 | 是 |
| Universe Layer | `3378455` | `feat: wire universe CLI commands` | CLI 接入 universe 工作流 | 是 |
| run_card / evidence trail | `e2243ed` | `feat: harden run card evidence bundle` | 强化统一 evidence bundle | 是 |
| Factor Registry | `ee52387` | `feat: add factor metadata registry` | 引入 metadata registry 主骨架 | 是 |
| Factor Registry | `38e072f` | `feat: register quality and value factors` | 为 fundamentals 注册 metadata | 是 |
| Data Quality Layer | `1626c79` | `feat: add unified data quality layer` | 新增统一 Data Quality 模块 | 是 |
| Data Quality Layer | `6c2e9ad` | `fix: align data quality report contract` | 对齐统一输出 contract | 是 |
| Data Quality Layer | `cd1089a` | `fix: harden data quality preflight checks` | 强化 preflight 路径 | 是 |
| Data Quality Layer | `fc13838` | `feat: add data quality CLI aggregation` | 新增 `data-quality` CLI | 是 |
| Data Quality Layer | `0f9a5f3` | `fix: align data quality CLI defaults` | 对齐 CLI 默认窗口行为 | 是 |
| Data Quality Layer | `3e8f0b5` | `fix: route blocked data quality windows through unified layer` | blocked path 回收统一层 | 是 |
| Data Quality Layer | `9e24f2b` | `fix: preserve data quality aggregation on blocked windows` | blocked 时仍保留 data/finance 聚合 | 是 |
| Data Quality Layer | `84b9ce2` | `fix: guard derived data quality windows` | 保护派生窗口失败路径 | 是 |
| Data Quality Layer | `abe7a79` | `fix: preserve industry checks in blocked data quality windows` | blocked 时仍保留 industry check | 是 |
| Factor Store Fundamentals | `12fad92` | `feat: wire fundamentals into factor daily pipeline` | 首次接通 fundamentals 主链 | 是 |
| Factor Store Fundamentals | `97edbf2` | `fix: harden fundamentals factor pipeline` | 补 snapshot / row validation | 是 |
| Factor Store Fundamentals | `c4411b2` | `fix: harden pit fundamentals factor rows` | 修复 stale asset / fallback / negative ratios | 是 |
| Factor Store Fundamentals | `0edb9e1` | `fix: batch pit fundamentals loading` | 去掉 N+1 PIT 查询 | 是 |
| Factor Store Fundamentals | `3fea2e0` | `fix: correct pit value factor inputs` | share-cap / TTM 口径改正 | 是 |
| Factor Store Fundamentals | `b4eb995` | `fix: prefer latest restated ttm filings` | 优先最新 restated filing | 是 |
| Factor Store Fundamentals | `38e072f` | `feat: register quality and value factors` | fundamentals registry 基线的一部分 | 是 |
| Factor Store Fundamentals | `a2af05c` | `test: tighten fundamentals pipeline regressions` | 回归 tightening | 是 |
| Factor Store Fundamentals | `8a4b22d` | `test: harden fundamentals factor pipeline coverage` | score-stability / shape regression | 是 |
| Watchlist | `fa47baf` | `feat: add watchlist storage schema` | watchlist schema 起点 | 是 |
| Watchlist | `7003ed6` | `fix: tighten watchlist schema constraints` | schema 约束收紧 | 是 |
| Watchlist | `869b6e8` | `fix: default watchlist items to active only` | active-only 默认语义 | 是 |
| Watchlist | `659cd77` | `fix: harden watchlist store row shaping` | store shape 稳定化 | 是 |
| Watchlist | `a6a834b` | `feat: add watchlist signal workflow` | signal/risk/workflow 主线 | 是 |
| Watchlist | `3787cfd` | `fix: normalize watchlist signal payloads` | signal payload 规范化 | 是 |
| Watchlist | `a39626d` | `fix: decouple watchlist sector ranking` | sector ranking 解耦 | 是 |
| Watchlist | `267a0ea` | `feat: add watchlist report workflow` | report 工作流接入 | 是 |
| Watchlist | `14b56ff` | `test: strengthen watchlist report assertions` | report assertions 强化 | 是 |
| Watchlist | `b466723` | `test: tighten watchlist report partitioning` | report partitioning 回归 | 是 |
| Watchlist | `9d4e688` | `fix: normalize typed watchlist report payloads` | typed payload 规范化 | 是 |
| TopN / retention constraints | `f025c0d` | `feat: add shared backtest execution constraints` | shared constraints 模块 | 是 |
| TopN / retention constraints | `011fac2` | `fix: harden backtest constraint parsing` | 解析收紧 | 是 |
| TopN / retention constraints | `19ef932` | `fix: tighten backtest constraint semantics` | 语义收紧 | 是 |
| TopN / retention constraints | `926c3b7` | `feat: unify vectorized topn execution constraints` | TopN 接线 | 是 |
| TopN / retention constraints | `017656f` | `fix: retry blocked topn sells on later dates` | blocked sell 重试 | 是 |
| TopN / retention constraints | `15e402f` | `fix: account for final-day topn execution costs` | 最后一日成本处理 | 是 |
| TopN / retention constraints | `0923abf` | `fix: merge final topn execution row` | 最终执行行合并 | 是 |
| TopN / retention constraints | `ec0ba30` | `fix: align final drawdown with visible curve` | drawdown 对齐 | 是 |
| TopN / retention constraints | `c3e2510` | `feat: unify retention execution constraints` | retention 接线 | 是 |
| TopN / retention constraints | `85a2dfa` | `fix: restore retention buy safety` | retention buy safety 修复 | 是 |
| TopN / retention constraints | `159f9c4` | `fix: block missing amount as low liquidity` | 低流动性规则修复 | 是 |
| CLI / watchdog / technical feature 收口 | `802ab1a` | `feat: harden technical feature backfill watchdog` | watchdog 主骨架强化 | 是 |
| CLI / watchdog / technical feature 收口 | `8e719b0` | `feat: add faster technical feature build strategies` | 技术特征构建策略增强 | 是 |
| CLI / watchdog / technical feature 收口 | `d2fdcd1` | `fix: expose technical feature build strategy flags` | CLI flag 暴露 | 是 |
| CLI / watchdog / technical feature 收口 | `a82622f` | `fix: tighten technical feature watchdog launch interval` | 调度间隔收紧 | 是 |
| CLI / watchdog / technical feature 收口 | `c21f8dd` | `feat: prioritize technical feature watchdog research window` | 研究窗口优先级 | 是 |

---

## 四、P0 验收结果

### 1. 已通过的关键测试集合

- Data Quality 直接相关回归：
  - `tests/test_data_quality.py`
  - `tests/test_data_audit.py`
  - `tests/test_finance_audit.py`
  - `tests/test_research_preflight.py`
  - `tests/test_factor_cli.py`
- Fundamentals / pipeline / PIT:
  - `tests/test_factor_pipeline.py`
  - `tests/test_factor_registry.py`
  - `tests/test_factor_config.py`
  - `tests/test_factor_value.py`
  - `tests/test_factor_fundamental.py`
  - `tests/test_point_in_time_finance.py`
  - `tests/test_finance_ttm.py`
  - `tests/test_daily_pipeline.py`
  - `tests/test_factor_backfill.py`
  - `tests/test_factor_cli.py`
- Watchlist:
  - `tests/test_watchlist_store.py`
  - `tests/test_watchlist_signals.py`
  - `tests/test_watchlist_workflow.py`
  - `tests/test_watchlist_report.py`
  - `tests/test_watchlist_cli.py`
- Backtest constraints:
  - `tests/test_backtest_constraints.py`
  - `tests/test_vectorized_topn_backtest.py`
  - `tests/test_retention_backtest.py`
  - `tests/test_strategy_lifecycle.py`

### 2. 已完成的 review gate

- 每条主线都经历了：
  - spec review
  - code quality review
- fundamentals 最终总 review 结论：
  - `NO FINDINGS`
- data quality 最终总 review 结论：
  - `NO FINDINGS`

### 3. 当前是否存在 blocker

当前没有 P0 blocker。

### 4. 当前是否还有未提交业务改动

没有未提交业务改动。

当前工作树只剩：

- 未跟踪 `docs/superpowers/*` 工作笔记

### 5. `docs/superpowers/*` 未跟踪文件是否属于 P0 范围

不属于 P0 baseline。

这些文件更接近：

- 规划草稿
- implementation plan
- 会话级 spec / notes

不应作为 P0 冻结成果的一部分。

---

## 五、P0 仍有限制与风险

1. 真实 PostgreSQL 全量覆盖率仍需定期 audit。  
2. technical features 算法层仍可继续优化。  
3. `quality / value` 因子入库不等于因子已经有稳定 alpha。  
4. 回测仍需持续做样本外、分市场状态、分行业状态验证。  
5. 当前不是自动交易系统。  
6. AI Agent Research Layer 尚未实现。  
7. portfolio / simulation 仍属于 P1/P2。  
8. report delivery adapter 尚未完成。  

---

## 六、P1 建议任务顺序

### P1-1：Report Delivery Adapter

- 输出 Markdown / JSON / CSV 到 OpenClaw / 飞书
- 先不做复杂 Web
- 支持日报、watchlist、TopN、risk alerts

### P1-2：AI Agent Research Layer

- Data Quality Agent
- Factor Research Agent
- Backtest Agent
- Watchlist Agent
- Risk Agent
- Review Agent
- 不允许直接给买卖结论
- 所有结论必须引用 evidence bundle

### P1-3：Portfolio / Simulation 增强

- 模拟组合
- 仓位建议
- 行业仓位约束
- 组合回撤监控
- 组合复盘

### P1-4：Factor Validation 增强

- 分市场状态
- 样本外
- 因子衰减
- 因子审批流

### P1-5：technical_features 算法层性能专项

- `_wilder_average`
- `RSI`
- `ADX`
- batch-level vectorization

---

## 七、是否建议进入 P1

### 1. 是否建议进入 P1

建议进入 P1。

### 2. 进入 P1 前是否需要 tag

建议。

### 3. 推荐 tag 名称

`p0-quant-research-mvp`

### 4. 推荐下一步任务

`P1-1：Report Delivery Adapter`

原因：

- P0 主链已完成并可冻结
- 当前最缺的是交付层，不是基础研究链路
- `Markdown / JSON / CSV` artifacts 已有基础，可顺势接 OpenClaw / 飞书
- 不需要先上复杂 Web，也不会提前引入 AI Agent 的额外边界

---

## 八、下一步操作建议

以下命令建议执行，但本轮不自动执行：

```bash
git -C /Users/xiwei/stock_research status --short
git -C /Users/xiwei/stock_research log --oneline -n 50
```

可选打 tag：

```bash
git -C /Users/xiwei/stock_research tag p0-quant-research-mvp
```

进入 P1 `Report Delivery Adapter` 的建议：

1. 先写 `Report Delivery Adapter` 设计 spec  
2. 定义本地 artifacts 到 OpenClaw / 飞书消息体的映射  
3. 先支持：
   - 日报
   - watchlist report
   - TopN report
   - risk alerts  
4. 暂不做复杂 Web / dashboard  

