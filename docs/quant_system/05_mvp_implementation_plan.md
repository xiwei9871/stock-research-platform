# Stock Research MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在当前 `stock_research` 仓库基础上，把已有散装研究能力升级为可审计、可回测、可复盘、可解释、可扩展的 A 股中低频量化研究与交易建议系统。

**Architecture:** 继续沿用 `PostgreSQL + factor pipeline + factor eval + backtest + reports` 主链，不新建仓库，不重写 Qlib/RQAlpha，不接自动下单。MVP 的重点是补统一层：Universe、Factor Registry、run_card / evidence trail、回测质量、watchlist、Agent 报告层和报告接口。

**Tech Stack:** Python 3.11、PostgreSQL、pandas、现有 `stock_research` CLI、后续可接 TA-Lib / pandas-ta、OpenClaw / Feishu。

---

## 实施原则

- 只在当前仓库内扩展，不新建平行项目。
- 优先复用 `src/stock_research/` 现有能力，不先做大重构。
- 所有新增模块都应有可调用函数或 CLI。
- 每个新流程都必须能产出 Markdown / JSON / CSV 证据。
- 所有回测和因子验证都必须纳入 `run_card`。
- AI Agent 只做投研助理，不做自动交易。

## Phase 0：文档与现状冻结

### 目标

- 冻结当前架构判断与建设边界。
- 明确系统以当前 `stock_research` 仓库为主线。
- 明确当前阶段不接真实自动交易。

### 当前已有基础

- 已生成：
  `docs/quant_system/01_current_state_audit.md`
  `docs/quant_system/02_external_research_map.md`
  `docs/quant_system/03_gap_matrix.md`
  `docs/quant_system/04_target_architecture.md`
- 本轮将补齐：
  `docs/quant_system/05_mvp_implementation_plan.md`
  `docs/quant_system/06_no_reinvent_wheel_policy.md`
  `docs/quant_system/07_agent_team_design.md`
  `docs/quant_system/08_backtest_quality_checklist.md`

### 缺口

- 还没有把 01-08 文档正式作为后续开发基线。
- 还没有把“禁止事项”和“优先级”转化为开发准入标准。

### 外部参考项目

- 无新增外部代码参考，本阶段主要依赖前 4 份文档的结论。

### 建议实现方式

- 将 `docs/quant_system/01-08` 视为当前开发冻结面。
- 后续开发一律优先对照这 8 份文档，避免目标漂移。

### 建议新增/修改文件

- 本阶段仅维护：
  `docs/quant_system/`

### CLI 建议

- 无需新增 CLI。

### 测试建议

- 无代码测试。
- 每次进入新 Phase 前，先检查本目录文档是否与当前实现一致。

### 预期产物

- 8 份量化系统设计与治理文档齐全。

### 优先级

- P0

### 风险

- 如果文档冻结不明确，后续容易重新回到“散点加功能”。

## Phase 1：Universe 统一规则层

### 目标

建立统一 Universe Layer，作为全市场扫描、回测、watchlist 和报告的共同入口。

### 当前已有基础

- 指数成分股 universe 能力：
  `src/stock_research/services/index_universe_service.py`
- 行业归属相关服务：
  `src/stock_research/services/industry_membership_service.py`
- 资产状态数据基础：
  `src/stock_research/core_data.py`
  `src/stock_research/schema.py` 中的 `core.asset_status_daily`
- 回测中已有局部过滤：
  `src/stock_research/backtest.py`
  `src/stock_research/retention_backtest.py`

### 缺口

- 当前没有统一的 A 股 Universe Builder。
- 过滤规则散落在回测和选股逻辑中。
- 没有统一解释“某只股票为什么被纳入或剔除”。

### 外部参考项目

- AlphaSift：全市场扫描和可审计机会发现
- Qlib：统一数据入口和可复用研究 universe

### 建议实现方式

- 在当前仓库内新增独立 Universe 模块。
- 统一支持以下规则：
  - 主板/创业板纳入
  - 排除科创板
  - 排除北交所
  - 排除 ST / *ST
  - 排除低流动性
  - 排除长期停牌
  - 支持上市天数过滤
  - 支持次新股可配置
  - 支持人工 watchlist 单独 universe
- 输出两类结果：
  - `full_market_universe_snapshot`
  - `watchlist_universe_snapshot`

### 建议新增/修改文件

- Create: `src/stock_research/universe/rules.py`
- Create: `src/stock_research/universe/builder.py`
- Create: `src/stock_research/universe/explain.py`
- Modify: `src/stock_research/cli.py`
- Modify: `src/stock_research/schema.py`
- Reuse: `src/stock_research/services/index_universe_service.py`

### CLI 入口建议

- `stock-research build-universe --trade-date YYYY-MM-DD --profile full_market`
- `stock-research build-universe --trade-date YYYY-MM-DD --profile watchlist`
- `stock-research explain-universe --trade-date YYYY-MM-DD --asset-id 000001.SZ`

### 测试建议

- Add: `tests/test_universe_rules.py`
- Add: `tests/test_universe_builder.py`
- Add: `tests/test_universe_cli.py`
- 必测场景：
  - 科创板排除
  - 北交所排除
  - ST 排除
  - 上市不足 N 天排除
  - 次新股在配置允许时纳入
  - 低流动性和长期停牌排除
  - watchlist 单独 universe 输出

### 预期产物

- 统一 universe 规则模块
- 可解释的纳入/剔除原因
- 可供 screener/backtest/watchlist 共用的 universe 快照

### 优先级

- P0

### 风险

- 如果继续把 universe 逻辑散落在回测和选股文件中，后续口径会彻底漂移。

## Phase 2：Factor Registry / Metadata

### 目标

把当前因子体系从“可计算”升级为“可管理、可解释、可追溯”。

### 当前已有基础

- 因子配置：
  `src/stock_research/factor_config.py`
- 因子计算与写入：
  `src/stock_research/factor_pipeline.py`
  `src/stock_research/factor_store.py`
- 因子实现：
  `src/stock_research/factors/`
- 因子审批表：
  `factor.factor_approval`

### 缺口

- 缺统一 registry。
- 缺 metadata 单一真相源。
- 基本面因子未完整接入主因子流水线。

### 外部参考项目

- Vibe-Trading：Alpha Zoo、registry、factor bench 组织方式
- Qlib：Alpha158/360、因子表达式和研究流

### 建议实现方式

- 把 `factor_config.py` 拆成：
  - `factor registry`
  - `score config`
- 每个因子至少包含以下 metadata：
  - `factor_id`
  - `factor_name`
  - `category`
  - `description`
  - `formula`
  - `input_fields`
  - `frequency`
  - `direction`
  - `neutralization_method`
  - `winsorize_method`
  - `standardize_method`
  - `lookback_window`
  - `author_source`
  - `status`
  - `evidence_path`

### 建议新增/修改文件

- Create: `src/stock_research/factor_registry.py`
- Modify: `src/stock_research/factor_config.py`
- Modify: `src/stock_research/factor_pipeline.py`
- Modify: `src/stock_research/factor_store.py`
- Optional Create: `src/stock_research/factors/metadata.py`

### CLI 建议

- `stock-research list-factors`
- `stock-research show-factor --factor-id <id>`
- `stock-research export-factor-registry`

### 测试建议

- Add: `tests/test_factor_registry.py`
- Expand: `tests/test_factor_config.py`
- Expand: `tests/test_factor_pipeline.py`
- 必测场景：
  - metadata 完整性
  - factor_id 唯一性
  - 注册因子与 `factor.factor_daily` 写入一致
  - deprecated/candidate/validated 状态校验

### 预期产物

- 统一因子注册表
- 因子 metadata 导出
- 主因子流水线与因子评估共享同一 registry

### 优先级

- P0

### 风险

- 若 registry 设计过重，会拖慢接入；应先满足治理字段，再逐步丰富。

## Phase 3：run_card / evidence trail

### 目标

让每次因子验证、回测、日报、策略实验都可复现、可审计。

### 当前已有基础

- 报告记录能力：
  `src/stock_research/report_run_store.py`
- 报表输出能力：
  `src/stock_research/reporting.py`
  `src/stock_research/performance_tearsheet.py`
- 专题证据链雏形：
  `src/stock_research/dragon_case_library.py`
  `src/stock_research/technical_method_validation.py`

### 缺口

- 当前没有统一 `run_card.md` / `run_card.json` 规范。
- 因子验证、回测、日报的输出风格不一致。

### 外部参考项目

- Vibe-Trading：run_card
- AlphaEvo：evidence trail

### 建议实现方式

- 为以下流程统一定义 run_card：
  - 单因子验证
  - 批量因子 gate
  - TopN 回测
  - Retention 回测
  - Portfolio 回测
  - 日报生成
  - 策略实验
- 每次运行至少产出：
  - `run_card.md`
  - `run_card.json`
  - `metrics.json`
  - `evidence/`

### 建议新增/修改文件

- Create: `src/stock_research/run_card.py`
- Modify: `src/stock_research/report_run_store.py`
- Modify: `src/stock_research/performance_tearsheet.py`
- Modify: `src/stock_research/factor_eval_store.py`
- Modify: `src/stock_research/reports/daily_research_report_workflow.py`

### CLI 建议

- `stock-research backtest-topn ... --with-run-card`
- `stock-research eval-factor ... --with-run-card`
- `stock-research run-daily-research-report ... --with-run-card`

### 测试建议

- Add: `tests/test_run_card.py`
- Expand: `tests/test_report_run_store.py`
- Expand: `tests/test_factor_eval_store.py`
- 必测场景：
  - run_card 文件齐全
  - config snapshot 与 CLI 参数一致
  - 数据覆盖信息被记录
  - warnings 能被记录

### 预期产物

- 统一 run_card 规范
- 可复现实验记录
- 后续 Agent 报告可直接引用 evidence trail

### 优先级

- P0

### 风险

- 若每个模块自己发明 run_card 格式，后续很难整合。

## Phase 4：回测质量增强

### 目标

在不重写完整事件驱动引擎的前提下，提高现有回测可信度。

### 当前已有基础

- TopN：
  `src/stock_research/vectorized_topn_backtest.py`
- Retention：
  `src/stock_research/retention_backtest.py`
- Portfolio：
  `src/stock_research/portfolio_backtest.py`
- 历史规则回测：
  `src/stock_research/backtest.py`

### 缺口

- 交易约束尚不完整。
- 不同回测模块之间成本口径和风险约束口径不统一。

### 外部参考项目

- RQAlpha：账户/持仓/交易约束
- Vibe-Trading：可复现实验与质量门禁

### 建议实现方式

- 不重写完整事件驱动引擎。
- 先增强：
  - `vectorized_topn_backtest.py`
  - `retention_backtest.py`
  - `portfolio_backtest.py`
- 必须补齐的真实交易约束：
  - 手续费
  - 印花税
  - 滑点
  - 涨停买不进
  - 跌停卖不出
  - 停牌不可交易
  - 下一交易日开盘执行
  - 收盘生成信号
  - 流动性过滤
  - 单票最大仓位
  - 单行业最大仓位
  - 止损
  - MA20 破位退出

### 建议新增/修改文件

- Modify: `src/stock_research/vectorized_topn_backtest.py`
- Modify: `src/stock_research/retention_backtest.py`
- Modify: `src/stock_research/portfolio_backtest.py`
- Create: `src/stock_research/backtest_constraints.py`
- Create: `src/stock_research/backtest_artifacts.py`

### CLI 建议

- 在现有回测 CLI 上扩展参数，不新增平行回测入口：
  - `--commission-bps`
  - `--stamp-duty-bps`
  - `--slippage-bps`
  - `--max-position-weight`
  - `--max-industry-weight`
  - `--stop-loss-pct`
  - `--ma20-exit`

### 测试建议

- Expand: `tests/test_vectorized_topn_backtest.py`
- Expand: `tests/test_retention_backtest.py`
- Expand: `tests/test_portfolio_backtest.py`
- Add: `tests/test_backtest_constraints.py`
- 必测场景：
  - 涨停开盘买不进
  - 跌停不可卖出
  - 停牌不可成交
  - 成本扣减正确
  - 信号日与执行日错开
  - 行业和个股权重上限生效

### 预期产物

- 更可信的 TopN / Retention / Portfolio 回测
- 统一回测约束模块
- 与 `08_backtest_quality_checklist.md` 对齐的验收门禁

### 优先级

- P0

### 风险

- 若不统一约束层，三个回测模块会继续各自漂移。

## Phase 5：watchlist 盯盘工作流

### 目标

建立面向人工精选池 100-150 只股票的日常盯盘体系。

### 当前已有基础

- 观察池和持仓留存骨架：
  `src/stock_research/retention_backtest.py`
- watchlist readiness 线索：
  `src/stock_research/technical_feature_promotion_audit.py`
- 日报与风险提醒能力：
  `src/stock_research/reports/`

### 缺口

- 当前没有真实 watchlist 表。
- 没有独立 watchlist 信号、风险和报告流程。

### 外部参考项目

- daily-stock-analysis：自选股日更结构
- TradingAgents-CN：报告组织方式

### 建议实现方式

- 让 watchlist 作为独立层，不再附着于专题审计文件。
- 支持每日输出：
  - 今日必须看
  - 启动信号
  - 回踩信号
  - 破位信号
  - 过热信号
  - 行业转弱
  - 风险剔除

### 建议新增/修改文件

- Create: `src/stock_research/watchlist/store.py`
- Create: `src/stock_research/watchlist/signals.py`
- Create: `src/stock_research/watchlist/risk.py`
- Create: `src/stock_research/watchlist/workflow.py`
- Create: `src/stock_research/reports/watchlist_report.py`
- Modify: `src/stock_research/cli.py`
- Modify: `src/stock_research/schema.py`

### CLI 入口建议

- `stock-research watchlist-build --trade-date YYYY-MM-DD`
- `stock-research watchlist-report --trade-date YYYY-MM-DD`
- `stock-research watchlist-explain --trade-date YYYY-MM-DD --asset-id 000001.SZ`

### 测试建议

- Add: `tests/test_watchlist_signals.py`
- Add: `tests/test_watchlist_workflow.py`
- Add: `tests/test_watchlist_report.py`
- 必测场景：
  - 启动/回踩/破位/过热信号互斥与共存规则
  - 行业转弱传导到个股
  - 今日必须看列表排序
  - 风险剔除生效

### 报告产物

- `watchlist_report.md`
- `watchlist_report.json`
- `watchlist_signals.csv`
- `must_watch.csv`

### 优先级

- P0

### 风险

- 若 watchlist 仍嵌在 retention 或技术审计里，后续无法成为稳定业务层。

## Phase 6：AI Agent 投研报告层

### 目标

让系统具备“我 + AI Agent”的投研协作层，但不触碰自动交易边界。

### 当前已有基础

- 报告底座：
  `src/stock_research/reports/`
- 风险提醒：
  `src/stock_research/reports/risk_alert_report.py`
- 市场状态与 TopN 报告：
  `market_state_report.py`
  `daily_topn_report.py`

### 缺口

- 当前没有 Agent 层、角色分工和审稿链。
- 现有报告还没有明确区分“数据事实 / 因子结果 / 回测结论 / AI 推理 / 未验证假设”。

### 外部参考项目

- TradingAgents-CN：中文多 Agent 结构
- daily-stock-analysis：日常分析报告组织
- Anthropic finance agents 思路：skills + connectors + subagents 的组织方式

### 建议实现方式

- 先定义 Agent 角色与报告 contract，再做自动化编排。
- 所有 Agent 输出都必须：
  - 基于数据证据
  - 不输出“必须买入”
  - 只输出：
    - 观察
    - 候选
    - 谨慎
    - 剔除
- 报告必须区分：
  - 数据事实
  - 因子结果
  - 回测结论
  - AI 推理
  - 未验证假设

### 建议新增/修改文件

- Create: `src/stock_research/agents/`
- Create: `src/stock_research/agents/contracts.py`
- Create: `src/stock_research/agents/review.py`
- Create: `src/stock_research/reports/agent_research_report.py`
- Reuse: `src/stock_research/reports/`

### CLI 建议

- `stock-research agent-report --trade-date YYYY-MM-DD --mode topn`
- `stock-research agent-report --trade-date YYYY-MM-DD --mode watchlist`

### 测试建议

- Add: `tests/test_agent_contracts.py`
- Add: `tests/test_agent_report_review.py`
- 必测场景：
  - 报告必须含证据引用
  - 未验证项必须被标注
  - Review Agent 能拦截“必须买入”类表达
  - 事实与推理分层输出

### 预期产物

- Agent 报告模板
- Agent 审核规则
- 可审查的投研输出分层

### 优先级

- P1

### 风险

- 如果在缺少证据层之前就做 Agent 文案层，会变成高幻觉风险功能。

## Phase 7：OpenClaw / 飞书 / 每日报告接口预留

### 目标

把当前已有的日报和通知能力收敛为标准输出接口，但不做复杂前端。

### 当前已有基础

- 飞书发送：
  `src/stock_research/feishu_notify.py`
- watchdog 已接通知：
  `minute_backfill_watchdog.py`
  `technical_feature_watchdog.py`
  `factor_gate_watchdog.py`
- 日报编排：
  `src/stock_research/reports/daily_research_report_workflow.py`

### 缺口

- 当前推送更偏运维告警，不是完整投研报告分发。
- 报告产物和通知内容没有统一协议。

### 外部参考项目

- daily-stock-analysis：推送结构与日报编排

### 建议实现方式

- 当前阶段先把所有输出标准化为：
  - Markdown
  - JSON
  - CSV
- 后续再接：
  - OpenClaw Skill
  - 飞书投递
- 不做复杂前端。

### 建议新增/修改文件

- Modify: `src/stock_research/reports/daily_research_report_workflow.py`
- Modify: `src/stock_research/feishu_notify.py`
- Create: `src/stock_research/report_delivery.py`

### CLI 建议

- `stock-research run-daily-research-report --output-formats md,json,csv`
- `stock-research deliver-report --channel feishu`

### 测试建议

- Add: `tests/test_report_delivery.py`
- Expand: `tests/test_daily_research_report_workflow.py`
- 必测场景：
  - 报告 bundle 路径完整
  - delivery payload 不混淆报告与告警
  - 同一报告可重复投递

### 预期产物

- 报告交付协议
- 可复用 delivery adapter

### 优先级

- P1

### 风险

- 如果先做推送、不先做标准报告产物，会形成输出层反复返工。

## Phase 8：模拟组合与半自动交易预留

### 目标

只做模拟组合与交易建议预留，不做自动交易。

### 当前已有基础

- 账户模拟：
  `src/stock_research/portfolio_backtest.py`
- 留存与持仓规则：
  `src/stock_research/retention_backtest.py`

### 缺口

- 没有长期虚拟组合状态表。
- 没有建议单和人工确认单结构。

### 外部参考项目

- RQAlpha：账户、持仓、交易对象模型
- AlphaEvo：策略实验到建议层的证据链

### 建议实现方式

- 只做：
  - 模拟组合
  - 交易建议
  - 人工确认接口预留
- 不做：
  - 实盘自动下单
  - 券商接口启用

### 建议新增/修改文件

- Future Create: `src/stock_research/simulation/`
- Future Create: `src/stock_research/trade_advice/`
- Future Modify: `src/stock_research/schema.py`

### CLI 建议

- `stock-research simulate-portfolio ...`
- `stock-research generate-trade-advice ...`

### 测试建议

- Add: `tests/test_simulation_portfolio.py`
- Add: `tests/test_trade_advice.py`
- 必测场景：
  - 建议单只输出建议，不执行下单
  - 人工确认状态机完整

### 预期产物

- 模拟组合状态
- 建议仓位区间
- 建议买卖清单

### 优先级

- P2

### 风险

- 任何真实下单耦合都违反当前项目边界。

## P0 任务清单前 10 项

1. 冻结 `docs/quant_system/01-08` 为当前实施基线。
2. 建立统一 Universe Layer。
3. 扩展 schema 以支持 watchlist 数据结构。
4. 建立 Factor Registry / Metadata。
5. 让 `factor_pipeline.py` 接入 registry 校验。
6. 建立统一 run_card / evidence trail。
7. 为因子验证输出标准 artifacts。
8. 增强 `vectorized_topn_backtest.py` 交易约束。
9. 增强 `retention_backtest.py` 成为 watchlist 规则回测骨架。
10. 建立 watchlist workflow 与 watchlist 报告。

## P1 任务清单

1. 增强 `portfolio_backtest.py` 的仓位与行业约束。
2. 建立 AI Agent Research Layer。
3. 建立 report delivery adapter。
4. 将 OpenClaw / 飞书从告警用途扩展到研究报告用途。
5. 引入外部 alpha zoo / Alpha158 思路适配。

## 暂时不要做的任务清单

1. 不重写完整事件驱动回测引擎。
2. 不新建仓库。
3. 不做高频 Tick 系统。
4. 不接实盘自动下单。
5. 不先做复杂 Web 前端。
6. 不让 Agent 绕过回测和证据层直接给买卖结论。
7. 不继续扩张旧 `public.*` 研究表作为新功能落点。
