# 不重复造轮子原则

本文定义当前 `stock_research` 仓库在后续建设中的“复用边界”。原则不是偷懒，而是避免在已有成熟开源能力前重复建设低价值基础设施，同时把真正必须自建的部分集中在你自己的 A 股 PostgreSQL 数据库、研究工作流和交易约束上。

## 1. 数据采集

### 1.1 应复用什么

- `baostock`
  - 当前仓库已经正式接入：
    `src/stock_research/loaders/baostock_ingestion.py`
    `src/stock_research/loaders/baostock_finance_ingestion.py`
    `src/stock_research/minute_data.py`
    `src/stock_research/minute_backfill.py`
  - 原则：继续保留为正式数据源之一。

- `AKShare`
  - 当前仓库已作为补充源使用：
    `src/stock_research/loaders/akshare_finance_loader.py`
    `src/stock_research/loaders/akshare_finance_statements.py`
    `src/stock_research/lhb_data.py`
  - 原则：适合补充行情、财务、行业、龙虎榜、未来的资金流、公告新闻等。

- `tushare`
  - 当前仓库已有局部预留和 LHB 导入入口：
    `src/stock_research/lhb_data.py`
    `src/stock_research/schema.py`
  - 原则：只在必要时接入，不作为默认主源。

### 1.2 不重复造轮子原则

- 不自己重写一套第三方行情/财务抓取 SDK。
- 不把外部 API 结果直接散用在业务逻辑中。
- 所有外部数据必须先落 PostgreSQL，再进入研究层。

### 1.3 必须自己做的部分

- 统一 PostgreSQL 数据模型
- 原始 payload 落库
- 增量更新逻辑
- 数据质量检查
- PIT 约束与时间可用性控制

## 2. 技术指标

### 2.1 应复用什么

- TA-Lib / pandas-ta
  - MACD
  - RSI
  - BOLL
  - ATR
  - ADX
  - KDJ
  - 均线
  - 波动率
  - 蜡烛图形态

### 2.2 当前仓库现状

- 当前技术特征已有大量自研实现：
  `src/stock_research/technical_features.py`
  `src/stock_research/technical_feature_store.py`
  `src/stock_research/factor_pipeline.py`
  `src/stock_research/factors/trend.py`
  `src/stock_research/factors/risk.py`
  `src/stock_research/factors/volume_price.py`

### 2.3 不重复造轮子原则

- 不要自己手写整套基础技术指标库。
- 未来新增基础技术指标时，优先复用 TA-Lib / pandas-ta。
- 自己只做：
  - 统一封装
  - metadata
  - 落库适配
  - 验证与回测

## 3. Alpha 因子

### 3.1 应复用什么

- Vibe-Trading
  - Alpha Zoo
  - `qlib158`
  - `Alpha101`
  - `GTJA191`
  - academic alpha 组织方式
- Qlib
  - Alpha158 / Alpha360 思路
  - 因子表达式
  - 因子分析流程
- QuantsPlaybook
  - 券商金工研报复现策略
  - RSRS、QRS、筹码分布、凸显性因子、多因子模型等候选素材

### 3.2 当前仓库现状

- 已有：
  `src/stock_research/factors/alpha101.py`
  `src/stock_research/factors/gtja191.py`
  `src/stock_research/factors/qlib_alpha.py`
  以及 `momentum.py`、`trend.py`、`value.py`、`growth.py`、`quality.py`

### 3.3 不重复造轮子原则

- 只迁移因子思想、公式、组织方式。
- 所有外部 alpha 都必须在你自己的 PostgreSQL A 股库里重算和重验。
- 不直接相信外部项目的收益结论。

### 3.4 必须自己做的部分

- Factor Registry
- 因子 metadata
- 因子落库适配
- 因子验证产物
- 与你自己的 universe / regime / risk 体系对接

## 4. 回测框架

### 4.1 应复用什么

- RQAlpha
  - 账户模型
  - 订单模型
  - 持仓模型
  - 手续费
  - 滑点
  - 停牌
  - 涨跌停等真实交易约束
- Qlib
  - 研究流程
  - 回测评估思路

### 4.2 当前仓库现状

- 已有：
  `src/stock_research/vectorized_topn_backtest.py`
  `src/stock_research/retention_backtest.py`
  `src/stock_research/portfolio_backtest.py`
  `src/stock_research/backtest.py`

### 4.3 不重复造轮子原则

- 短期不整仓替换当前回测框架。
- 不重写完整事件驱动引擎。
- 先增强现有 TopN / Retention / Portfolio 回测的真实交易约束。

### 4.4 必须自己做的部分

- A 股日频/周频中低频交易约束
- 与你自己的 universe / factor / regime / watchlist 联动
- run_card / evidence trail
- 回测质量门禁

## 5. 日报与推送

### 5.1 应复用什么

- daily-stock-analysis
  - 日报结构
  - 自选股分析
  - 风险提示
  - 推送方式

### 5.2 当前仓库现状

- 已有日报和 bundle：
  `src/stock_research/reports/`
- 已有 OpenClaw / 飞书通知基础：
  `src/stock_research/feishu_notify.py`

### 5.3 不重复造轮子原则

- 先输出 Markdown / JSON / CSV。
- 后续再接 OpenClaw / 飞书。
- 不先做复杂前端和重复的消息分发框架。

## 6. 全市场扫描

### 6.1 应复用什么

- AlphaSift
  - A 股全市场扫描
  - LLM ranking
  - risk-aware scoring
  - auditable evaluation

### 6.2 当前仓库现状

- 当前已有 TopN 打分与日报工作流：
  `src/stock_research/factor_store.py`
  `src/stock_research/research_workflow.py`
  `src/stock_research/reports/daily_topn_report.py`

### 6.3 不重复造轮子原则

- 最终评分必须来自可验证因子和数据证据。
- LLM 只能解释、辅助排序和归因，不能替代主评分体系。

## 7. 策略进化

### 7.1 应复用什么

- AlphaEvo
  - 策略 DSL
  - 失败归因
  - 结构化改写
  - 复测
  - evidence trail

### 7.2 当前仓库现状

- 已有局部证据链与专题诊断：
  `src/stock_research/dragon_case_library.py`
  `src/stock_research/technical_method_validation.py`
  `src/stock_research/factor_eval/`

### 7.3 不重复造轮子原则

- 策略不能只生成，必须验证、诊断、留痕、剪枝。
- 在 Universe、Registry、run_card、回测质量稳定前，不提前做复杂策略 DSL。

## 8. Agent 投研

### 8.1 应复用什么

- TradingAgents-CN
  - 中文多 Agent 投研角色
  - 技术面 / 基本面 / 新闻 / 风险 / 组合经理 等报告结构

### 8.2 严格限制

- 不复制 `app/`、`frontend/` 等专有或受限代码。
- 只借鉴角色设计和报告结构。

### 8.3 不重复造轮子原则

- AI Agent 是研究助理，不是交易负责人。
- 不自己发明一套没有证据约束的“智能投顾话术系统”。
- Agent 层必须建立在数据、因子、回测和 run_card 之上。

## 9. 必须自己做的内容

以下内容不能外包给开源项目，必须围绕你自己的 A 股数据库与研究流程自建：

- PostgreSQL 数据模型与数据质量体系
- Universe 统一规则
- Factor Registry
- Factor Store 适配
- 因子验证产物
- run_card / evidence trail
- watchlist 盯盘
- A 股中低频策略约束
- 你自己的交易偏好和风控规则
- OpenClaw / 飞书内部工作流适配

## 10. 禁止事项

- 不直接复制外部项目大段代码。
- 不相信外部项目回测收益结论。
- 不无视 license。
- 不绕过自己的回测。
- 不直接自动下单。
- 不做高频 Tick。
- 不在代码里硬编码数据库密码、token、券商账号。

## 结论

本项目的复用策略应该是：

1. 外部项目负责提供方法、公式、接口和工作流灵感。
2. 当前仓库负责承载你自己的数据模型、研究逻辑、约束和证据链。
3. 所有进入策略池的东西，必须先在你自己的 PostgreSQL A 股库中落地、验证、留痕。

这就是“不重复造轮子”的真实含义：基础轮子尽量复用，关键约束和核心研究资产必须掌握在你自己的系统里。
