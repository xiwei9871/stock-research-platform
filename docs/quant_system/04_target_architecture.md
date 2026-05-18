# 目标架构设计

## 1. 总体目标

目标是在当前 `stock_research` 仓库基础上，建设一个“由你本人 + AI Agent 组成”的 A 股中低频研究与半自动交易建议系统。系统负责：

- 全市场扫描
- 股票池维护
- 因子打分
- 单因子与组合验证
- TopN / watchlist / portfolio 模拟
- 行业与市场状态判断
- 每日/每周研究报告
- 交易建议与风险提示

最终原则：

- 系统只输出研究结论、建议和证据
- 人工确认后才允许进入交易动作
- 当前阶段不接真实自动下单

## 2. 非目标

本架构明确不做以下事项：

- 不做高频交易系统
- 不做 Tick 级撮合研究系统
- 不直接自动下单
- 不把当前仓库重写成 Qlib
- 不把当前仓库重写成 RQAlpha
- 不新建平行仓库
- 不推翻现有 PostgreSQL 中心架构

## 3. 分层架构

建议采用以下分层：

1. Data Layer
2. Data Quality Layer
3. Universe Layer
4. Factor Layer
5. Factor Validation Layer
6. Backtest Layer
7. Stock Screener Layer
8. Regime Layer
9. Watchlist Layer
10. AI Agent Research Layer
11. Report Layer
12. OpenClaw / Feishu Integration Layer
13. Future Semi-Auto Trading Layer

## 4. 各层设计

### 4.1 Data Layer

| 项 | 说明 |
| --- | --- |
| 目标 | 统一承载 A 股研究主数据、原始 payload、因子输入数据和研究中间产物 |
| 输入 | baostock、akshare、tushare 局部接口、已有 PostgreSQL 原始表、手工 seed 数据 |
| 输出 | `core.*`、`market.*`、`finance.*`、`factor.*`、`ingest.*` 等 schema 下的标准表 |
| 当前已有文件 | `src/stock_research/schema.py`、`core_data.py`、`corporate_actions.py`、`dimensions.py`、`loaders/`、`minute_data.py`、`minute_backfill.py` |
| 外部参考 | AKShare、Qlib |
| P0 建议 | 继续扩展当前 schema；新表优先落在新 schema，不再扩展 `public.*` |
| P1 建议 | 增加 `watchlist`、`portfolio_position`、`trade_log`、`valuation_daily` 等表 |
| P2 建议 | 为未来半自动交易建议预留 advice / simulation 相关表 |

当前层的落点不应改到新仓库，应继续落在：

- `src/stock_research/schema.py`
- `src/stock_research/loaders/`
- `src/stock_research/services/`

### 4.2 Data Quality Layer

| 项 | 说明 |
| --- | --- |
| 目标 | 对数据完整性、覆盖率、异常值、PIT 约束进行统一巡检 |
| 输入 | `market.*`、`finance.*`、`factor.*`、`raw_*` 数据表 |
| 输出 | `data_quality_report`、`coverage_report`、`missing_data_report`、`abnormal_price_report` |
| 当前已有文件 | `src/stock_research/quality.py`、`data_audit.py`、`finance_audit.py`、`research_preflight.py` |
| 外部参考 | Vibe-Trading、Qlib |
| P0 建议 | 把已有巡检能力收敛为统一 Data Quality Layer，不改变底层存储方向 |
| P1 建议 | 加入财报公告日、ST 状态、停牌时序、行业缺失等专项报告 |
| P2 建议 | 将质量报告接入 Agent / 推送层 |

### 4.3 Universe Layer

| 项 | 说明 |
| --- | --- |
| 目标 | 统一定义“哪些股票有资格进入研究、回测、筛选、盯盘” |
| 输入 | `core.asset_master`、`core.asset_status_daily`、`market.trading_calendar`、行业/指数成分、流动性信息 |
| 输出 | 标准化 `universe_snapshot` 或可复用的 universe selection 结果 |
| 当前已有文件 | `src/stock_research/services/index_universe_service.py`、`industry_membership_service.py`、回测中的 ST/流动性过滤逻辑 |
| 外部参考 | AlphaSift、Qlib |
| P0 建议 | 新增统一 universe builder，覆盖主板/创业板/科创板排除/北交所排除/ST/上市天数/停牌/低流动性 |
| P1 建议 | 增加主题池、指数池、次新可选池等配置 |
| P2 建议 | 与组合层联动做动态 universe 版本追踪 |

建议落点：

- `src/stock_research/universe/`
- 或扩展 `src/stock_research/services/`

### 4.4 Factor Layer

| 项 | 说明 |
| --- | --- |
| 目标 | 统一计算、注册、落库和追踪所有因子 |
| 输入 | `market_daily_bar`、`industry_daily_bar`、`finance.*`、分钟线特征、事件特征 |
| 输出 | `factor.factor_daily`、`factor.stock_score_daily`、因子 metadata |
| 当前已有文件 | `factor_config.py`、`factor_pipeline.py`、`factor_store.py`、`factors/`、`technical_feature_store.py` |
| 外部参考 | Vibe-Trading、Qlib、TA-Lib / pandas-ta、QuantsPlaybook |
| P0 建议 | 建 Factor Registry；保留当前计算器和落库接口；优先把 metadata 建起来 |
| P1 建议 | 引入 Alpha158/360 思路和外部 alpha zoo 的标准适配层 |
| P2 建议 | 视需要输出 qlib-compatible export |

此层的关键原则是：

- 基础技术指标优先复用成熟库
- 自己维护统一接口、metadata、落库与 lineage
- 不重复造技术指标轮子

### 4.5 Factor Validation Layer

| 项 | 说明 |
| --- | --- |
| 目标 | 对候选因子做 IC、RankIC、分组收益、多空收益、换手、样本外、未来函数审计 |
| 输入 | `factor.factor_daily`、标签数据、市场分段、行业/市值暴露数据 |
| 输出 | `factor_validation_report.md`、`metrics.csv`、`factor_evidence.json`、`factor_approval` |
| 当前已有文件 | `factor_eval/`、`factor_eval_batch.py`、`factor_eval_store.py` |
| 外部参考 | Vibe-Trading、Qlib、AlphaEvo |
| P0 建议 | 保留现有 `factor_eval/` 架构，统一 artifacts 输出规范 |
| P1 建议 | 加强样本外、市场状态分层、中性化与 decay 检测 |
| P2 建议 | 接到策略演化与 Agent 研究层 |

### 4.6 Backtest Layer

| 项 | 说明 |
| --- | --- |
| 目标 | 用统一、可复现的方式验证 TopN、Retention、Portfolio 策略 |
| 输入 | 因子打分、Universe、Regime、交易约束参数 |
| 输出 | `backtest_report.md`、`equity_curve.csv`、`trades.csv`、`positions.csv`、`metrics.json`、`run_card.*` |
| 当前已有文件 | `backtest.py`、`vectorized_topn_backtest.py`、`portfolio_backtest.py`、`retention_backtest.py`、`performance_metrics.py` |
| 外部参考 | RQAlpha、Vibe-Trading |
| P0 建议 | 以 `vectorized_topn_backtest.py`、`retention_backtest.py`、`portfolio_backtest.py` 为主；补统一交易约束和 run_card |
| P1 建议 | 增加更细的行业/仓位/止盈止损/市场过滤 |
| P2 建议 | 再评估是否抽象事件驱动层 |

建议的层内分工：

- `vectorized_topn_backtest.py`：
  用于全市场 TopN 日/周调仓验证
- `retention_backtest.py`：
  用于观察池/持仓保留/规则退出
- `portfolio_backtest.py`：
  用于组合资金曲线与仓位模拟
- `backtest.py`：
  逐步退居兼容层或规则样本层

### 4.7 Stock Screener Layer

| 项 | 说明 |
| --- | --- |
| 目标 | 对全市场做日常扫描，输出 TopN、连续上榜、评分变化、风险剔除名单 |
| 输入 | Universe、因子分数、Regime、风险标签 |
| 输出 | Top200 / Top100 / Top50 / Top20、候选池变化、风险剔除列表 |
| 当前已有文件 | `selection.py`、`factor_store.py`、`research_workflow.py`、`reports/daily_topn_report.py` |
| 外部参考 | AlphaSift、daily-stock-analysis |
| P0 建议 | 从现有 TopN 工作流演进，不另起平行选股框架 |
| P1 建议 | 增加 LLM 参与的 explain/ranking，但不得替代规则分数 |
| P2 建议 | 与 Agent 层联动形成机会发现闭环 |

### 4.8 Regime Layer

| 项 | 说明 |
| --- | --- |
| 目标 | 标准化输出市场环境和行业主线判断，供回测、选股、watchlist、报告共用 |
| 输入 | 行业价格、成交额、候选密度、行业得分、未来不用作输入的诊断数据 |
| 输出 | `regime snapshot`、行业强弱排序、允许追涨/低吸/降仓的状态标记 |
| 当前已有文件 | `industry_focus_score.py`、`industry_focus_v2.py`、`industry_mainline_regime.py`、`industry_regime_gated_backtest.py` |
| 外部参考 | Vibe-Trading、Qlib |
| P0 建议 | 将现有研究模块封装为标准 regime 输出，而不是继续散点调用 |
| P1 建议 | 引入更完整的市场广度、炸板率、高位亏钱效应等状态指标 |
| P2 建议 | 与模拟组合和仓位建议联动 |

### 4.9 Watchlist Layer

| 项 | 说明 |
| --- | --- |
| 目标 | 面向人工精选池输出启动、回踩、破位、过热、放量异动、行业变化、大盘变化提醒 |
| 输入 | 手工 watchlist、技术特征、Regime、行业状态、风险标签 |
| 输出 | watchlist 日报、今日必须看、观察/候选/谨慎/剔除分层 |
| 当前已有文件 | `retention_backtest.py` 的观察池结构；`technical_feature_promotion_audit.py` 的 `watchlist_readiness` |
| 外部参考 | daily-stock-analysis、TradingAgents-CN |
| P0 建议 | 建独立 watchlist 层和 watchlist 报告，不再把这类逻辑塞进专题审计文件 |
| P1 建议 | 接入 Agent 个股分析模板 |
| P2 建议 | 与模拟组合联动，形成建议单草稿 |

### 4.10 AI Agent Research Layer

| 项 | 说明 |
| --- | --- |
| 目标 | 让 Agent 成为投研助理，而不是交易决策者 |
| 输入 | Data Quality 报告、因子评估结果、回测结果、Regime、TopN、watchlist、公告新闻等 |
| 输出 | 带证据引用的研究报告，分类为观察 / 候选 / 谨慎 / 剔除 |
| 当前已有文件 | 目前无独立 Agent 层；已有 `reports/` 和 `risk_alert_report.py` 可复用为输出底座 |
| 外部参考 | TradingAgents-CN、daily-stock-analysis、AlphaSift、AlphaEvo |
| P0 建议 | 先定义角色、输入、输出、证据规则，不急于写复杂 Agent orchestration |
| P1 建议 | 实现 Data Quality Agent / Factor Research Agent / Risk Agent / Portfolio Manager Agent 等 |
| P2 建议 | 再与 OpenClaw Skill、飞书推送、Web 看板连接 |

核心约束：

- Agent 不给“必须买入”结论
- 所有结论必须可追溯到数据、因子、回测或外部已验证来源
- 未验证内容必须明确标记

### 4.11 Report Layer

| 项 | 说明 |
| --- | --- |
| 目标 | 将数据事实、因子结果、回测结论、AI 推理、未验证假设分层输出 |
| 输入 | Screener、Watchlist、Regime、Backtest、Factor Validation、Risk Alerts |
| 输出 | Markdown、CSV、JSON 报告包 |
| 当前已有文件 | `src/stock_research/reports/`、`reporting.py`、`research_workflow.py` |
| 外部参考 | daily-stock-analysis、Vibe-Trading、AlphaEvo |
| P0 建议 | 沿用现有 `reports/` 结构，补 watchlist / weekly factor / weekly strategy / monthly health 模板 |
| P1 建议 | 标准化 report bundle 与 run_card 关联 |
| P2 建议 | 接入多渠道分发 |

### 4.12 OpenClaw / Feishu Integration Layer

| 项 | 说明 |
| --- | --- |
| 目标 | 将研究报告、异常告警、日常状态输出到 OpenClaw / 飞书 |
| 输入 | 报告路径、简版摘要、运维告警、研究快照 |
| 输出 | 飞书消息、OpenClaw Skill 调用、计划任务入口 |
| 当前已有文件 | `feishu_notify.py`、`minute_backfill_watchdog.py`、`technical_feature_watchdog.py`、`factor_gate_watchdog.py`、`reports/daily_research_cron.py` |
| 外部参考 | daily-stock-analysis、TradingAgents-CN |
| P0 建议 | 先把报告产物标准化，再决定消息模板 |
| P1 建议 | 形成“报告推送”和“运维告警”两类不同通道 |
| P2 建议 | 接 OpenClaw Skill / Web 看板 |

### 4.13 Future Semi-Auto Trading Layer

| 项 | 说明 |
| --- | --- |
| 目标 | 仅预留半自动交易建议接口，不接实盘自动下单 |
| 输入 | Screener、Watchlist、Regime、Portfolio 模拟、风险约束 |
| 输出 | 进池规则、买入观察规则、卖出/剔除规则、仓位建议 |
| 当前已有文件 | 当前无独立层；可复用 `portfolio_backtest.py`、`retention_backtest.py` 的规则骨架 |
| 外部参考 | RQAlpha、AlphaEvo |
| P0 建议 | 不开发真实交易接口，只在架构中定义建议单结构 |
| P1 建议 | 增加模拟组合与建议仓位输出 |
| P2 建议 | 为未来券商接口预留 adapter，但默认关闭 |

## 5. 分层数据流

建议的数据流如下：

1. Data Layer 负责把所有源数据标准化落库。
2. Data Quality Layer 对落库结果做完整性和 PIT 审计。
3. Universe Layer 基于资产状态和规则输出可研究股票池。
4. Factor Layer 计算并落库因子及总分。
5. Factor Validation Layer 审核候选因子是否进入主评分体系。
6. Regime Layer 输出市场和行业环境状态。
7. Backtest Layer 用 Universe + Factor + Regime 做可复现验证。
8. Stock Screener Layer 生成全市场候选池。
9. Watchlist Layer 生成人工精选池观察结果。
10. AI Agent Research Layer 基于证据生成结构化研究结论。
11. Report Layer 输出日报、周报、复盘、健康报告。
12. OpenClaw / Feishu Integration Layer 负责投递。
13. Future Semi-Auto Trading Layer 只生成建议单和人工确认材料。

## 6. 当前仓库与目标架构的对应关系

当前仓库已经能直接承载目标架构的核心层：

- Data Layer：
  已有
- Data Quality Layer：
  有基础实现，需增强
- Universe Layer：
  有局部实现，需统一
- Factor Layer：
  已有
- Factor Validation Layer：
  已有较好雏形
- Backtest Layer：
  已有多条骨架
- Stock Screener Layer：
  有基础能力，需系统化
- Regime Layer：
  已有较深研究
- Watchlist Layer：
  基本缺失
- AI Agent Research Layer：
  结构缺失
- Report Layer：
  已有
- Integration Layer：
  已有部分能力
- Semi-Auto Trading Layer：
  仅应做预留

## 7. 建设顺序建议

### P0

优先建设这些层，不改变仓库主骨架：

1. Data Quality Layer
2. Universe Layer
3. Factor Registry within Factor Layer
4. Factor Validation artifacts
5. Backtest Layer quality constraints
6. Stock Screener Layer
7. Watchlist Layer
8. Report Layer 的标准化输出

### P1

在 P0 稳定后建设：

1. AI Agent Research Layer
2. OpenClaw / Feishu report delivery
3. Portfolio / simulation 增强
4. 外部 alpha zoo / Alpha158 思路适配

### P2

最后再建设：

1. Future Semi-Auto Trading Layer
2. 券商接口预留
3. Web 看板

## 8. 架构结论

当前最佳路径不是：

- 另起新仓库
- 重写 Qlib
- 重写 RQAlpha
- 全面重构旧代码

当前最佳路径是：

1. 继续以现有 `stock_research` 为主仓。
2. 把已有能力抽象成统一层。
3. 只补关键缺口，不大面积改动成熟模块。
4. 所有新功能都围绕 `PostgreSQL + factor eval + backtest + report` 主链建设。

这样才能最快把当前仓库推进到“可持续迭代的 A 股半自动研究系统”，而不是重新掉回平台重写周期。
