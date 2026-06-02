# “我 + AI Agent”投研团队设计

本文定义的投研团队不是招人方案，而是当前 `stock_research` 仓库未来要支持的“你本人 + AI Agent”协作模型。所有 Agent 都是研究助理，不是交易执行者。

## 1. 你的角色

你的角色是系统里的唯一最终责任人：

- 最终确认人
- 投资偏好设定者
- 风险承受边界设定者
- 交易纪律负责人
- 最终买卖决策人

AI Agent 只能给出：

- 观察
- 候选
- 谨慎
- 剔除

AI Agent 不能给出：

- 必须买入
- 直接下单
- 跳过回测与风控的结论

## 2. 全局约束

所有 Agent 共用以下约束：

- 必须引用数据证据。
- 必须区分事实与推理。
- 未验证内容必须显式标注。
- 不能绕过 Risk Agent。
- 不能绕过 Review Agent。
- 不能输出自动交易指令。

## 3. Agent 清单

### 3.1 Data Quality Agent

**职责**

- 检查数据完整性
- 检查异常价格
- 检查缺失交易日
- 检查停牌 / ST / 涨跌停状态
- 检查财报披露日期，避免未来函数

**输入**

- `market.*`
- `finance.*`
- `core.asset_status_daily`
- `raw_*`
- 数据质量巡检结果

**输出**

- `data_quality_report`
- `coverage_report`
- `missing_data_report`
- `pit_warnings`

**可调用工具/模块**

- `src/stock_research/quality.py`
- `src/stock_research/data_audit.py`
- `src/stock_research/finance_audit.py`
- `src/stock_research/research_preflight.py`

**禁止行为**

- 不允许把“缺数据”解释成投资观点
- 不允许忽略 future-function 风险

**审核规则**

- 每个结论必须对应检查项
- 每个风险必须对应数据表或字段来源

**报告模板**

- 数据事实
- 异常项
- 影响范围
- 是否阻断后续流程

**对应当前代码位置**

- `src/stock_research/quality.py`
- `src/stock_research/data_audit.py`

**参考外部项目**

- Vibe-Trading
- Qlib

### 3.2 Universe Agent

**职责**

- 执行统一股票池规则
- 解释股票为何被纳入或排除
- 维护全市场 universe 和 watchlist universe

**输入**

- 资产主表
- 资产状态
- 流动性数据
- 上市日期
- watchlist

**输出**

- `universe_snapshot`
- `watchlist_universe_snapshot`
- 纳入/排除解释

**可调用工具/模块**

- 当前可复用：
  `src/stock_research/services/index_universe_service.py`
  `src/stock_research/services/industry_membership_service.py`
- 未来应新增：
  `src/stock_research/universe/`

**禁止行为**

- 不允许在不同流程里使用不同 universe 口径

**审核规则**

- 每只被剔除股票必须能给出明确规则原因

**报告模板**

- 规则版本
- 纳入数量
- 剔除数量
- 典型剔除原因

**对应当前代码位置**

- `src/stock_research/services/index_universe_service.py`

**参考外部项目**

- AlphaSift
- Qlib

### 3.3 Factor Research Agent

**职责**

- 管理因子 metadata
- 提出新因子候选
- 标记因子来源
- 解释因子含义
- 调用因子验证流程

**输入**

- 因子 registry
- 因子实现模块
- 外部因子来源映射

**输出**

- 新因子候选清单
- 因子 metadata
- 因子来源说明
- 验证请求

**可调用工具/模块**

- `src/stock_research/factor_config.py`
- `src/stock_research/factor_pipeline.py`
- `src/stock_research/factors/`
- 未来 `src/stock_research/factor_registry.py`

**禁止行为**

- 不允许无来源地发明因子名称
- 不允许跳过 metadata 直接把因子接入评分

**审核规则**

- 每个候选因子必须有来源、公式、方向、输入字段

**报告模板**

- 因子概述
- 来源
- 公式/近似实现
- 预期作用
- 需验证事项

**对应当前代码位置**

- `src/stock_research/factor_config.py`
- `src/stock_research/factors/`

**参考外部项目**

- Vibe-Trading
- Qlib
- QuantsPlaybook

### 3.4 Factor Validation Agent

**职责**

- 运行单因子 IC / RankIC / 分组收益
- 识别因子失效
- 标记过拟合风险
- 输出因子证据

**输入**

- `factor.factor_daily`
- 标签数据
- 分段/多周期配置

**输出**

- `factor_validation_report`
- `metrics`
- `approval / reject` 建议
- `factor_evidence`

**可调用工具/模块**

- `src/stock_research/factor_eval/`
- `src/stock_research/factor_eval_batch.py`
- `src/stock_research/factor_eval_store.py`

**禁止行为**

- 不允许只看单一 IC 均值就批准因子
- 不允许忽略样本外或未来函数风险

**审核规则**

- 必须给出 IC、RankIC、分组收益、换手等核心证据

**报告模板**

- 因子名称
- 验证窗口
- 关键指标
- 风险结论
- 最终分级

**对应当前代码位置**

- `src/stock_research/factor_eval/`

**参考外部项目**

- Vibe-Trading
- Qlib
- AlphaEvo

### 3.5 Backtest Agent

**职责**

- 运行 TopN / Retention / Portfolio 回测
- 检查手续费、滑点、涨跌停、停牌等约束
- 生成 run_card
- 识别不可信回测

**输入**

- 因子分数
- Universe
- Regime
- 回测配置

**输出**

- `run_card`
- `metrics.json`
- `equity_curve.csv`
- `trades.csv`
- 回测结论分级

**可调用工具/模块**

- `src/stock_research/vectorized_topn_backtest.py`
- `src/stock_research/retention_backtest.py`
- `src/stock_research/portfolio_backtest.py`
- `src/stock_research/performance_tearsheet.py`
- `src/stock_research/strategy_lifecycle.py`

**禁止行为**

- 不允许忽略交易成本
- 不允许信号日当天生成信号又当天成交
- 不允许没有 run_card 的结果进入策略池

**审核规则**

- 必须通过 `08_backtest_quality_checklist.md`

**报告模板**

- 策略配置
- 数据覆盖
- 关键指标
- 风险与警告
- 分级结论

**对应当前代码位置**

- `src/stock_research/vectorized_topn_backtest.py`
- `src/stock_research/retention_backtest.py`
- `src/stock_research/portfolio_backtest.py`

**参考外部项目**

- RQAlpha
- Vibe-Trading

### 3.6 Regime Agent

**职责**

- 判断市场状态
- 判断行业热度
- 判断是否允许追涨
- 判断是否只适合低吸
- 判断是否应降低仓位

**输入**

- 行业强度
- 市场状态
- 行业主线诊断

**输出**

- `regime_snapshot`
- 市场状态标签
- 行业强弱排序
- 仓位环境建议

**可调用工具/模块**

- `src/stock_research/industry_focus_v2.py`
- `src/stock_research/industry_mainline_regime.py`
- `src/stock_research/industry_regime_gated_backtest.py`
- `src/stock_research/industry_exposure_risk_control.py`

**禁止行为**

- 不允许使用未来收益字段做当日判断

**审核规则**

- 每个结论都必须标明是市场事实、行业事实还是规则推理

**报告模板**

- 市场状态
- 行业主线
- 可追涨/低吸/降仓建议
- 风险提示

**对应当前代码位置**

- `src/stock_research/industry_focus_v2.py`
- `src/stock_research/industry_mainline_regime.py`

**参考外部项目**

- Vibe-Trading
- Qlib

### 3.7 Watchlist Agent

**职责**

- 监控人工股票池
- 识别启动、回踩、破位、过热、行业转弱
- 输出今日必须看股票

**输入**

- watchlist
- 技术特征
- Regime
- 风险标签

**输出**

- `must_watch`
- watchlist 信号分类
- 风险剔除名单

**可调用工具/模块**

- 当前基础：
  `src/stock_research/retention_backtest.py`
  `src/stock_research/technical_feature_promotion_audit.py`
- 未来主落点：
  `src/stock_research/watchlist/`

**禁止行为**

- 不允许把 watchlist 直接等同于买入清单

**审核规则**

- 每个“今日必须看”都必须对应触发条件

**报告模板**

- 今日必须看
- 启动/回踩/破位/过热
- 行业与市场上下文
- 风险说明

**对应当前代码位置**

- `src/stock_research/retention_backtest.py`
- `src/stock_research/technical_feature_promotion_audit.py`

**参考外部项目**

- daily-stock-analysis
- TradingAgents-CN

### 3.8 Stock Analyst Agent

**职责**

- 对 Top20 / watchlist 个股生成分析
- 覆盖技术面、基本面、行业、资金、风险
- 不直接给“必须买入”

**输入**

- Top20 或 watchlist 结果
- 行业与市场状态
- 财务与技术特征
- LHB / 资金面补充信息

**输出**

- 个股分析卡
- 观察 / 候选 / 谨慎 / 剔除分类

**可调用工具/模块**

- `src/stock_research/reports/daily_topn_report.py`
- `src/stock_research/reports/risk_alert_report.py`
- `src/stock_research/lhb_data.py`
- `src/stock_research/dragon_strategy_research.py`

**禁止行为**

- 不允许输出“必须买入”
- 不允许把未经验证新闻作为强结论

**审核规则**

- 必须明确哪些结论来自数据，哪些是 AI 推理

**报告模板**

- 个股事实
- 技术/行业/资金/财务观察
- 风险点
- 分类结论

**对应当前代码位置**

- `src/stock_research/reports/`

**参考外部项目**

- TradingAgents-CN
- daily-stock-analysis

### 3.9 Risk Agent

**职责**

- 检查高位风险
- 检查破位风险
- 检查财务风险
- 检查流动性风险
- 检查公告 / 减持 / ST 风险
- 给出风险等级

**输入**

- 技术特征
- 财务指标
- 市场状态
- LHB 与事件特征

**输出**

- 风险标签
- 风险等级
- 剔除建议

**可调用工具/模块**

- `src/stock_research/reports/risk_alert_report.py`
- `src/stock_research/technical_method_validation.py`
- `src/stock_research/lhb_data.py`
- `src/stock_research/dragon_case_library.py`

**禁止行为**

- 不允许忽略明显回撤、流动性和 ST 风险

**审核规则**

- 风险必须有字段或规则依据

**报告模板**

- 风险项
- 风险来源
- 等级
- 建议处理

**对应当前代码位置**

- `src/stock_research/reports/risk_alert_report.py`

**参考外部项目**

- TradingAgents-CN
- AlphaSift

### 3.10 Portfolio Manager Agent

**职责**

- 汇总因子分数、市场状态、行业状态、风险状态
- 输出观察 / 候选 / 谨慎 / 剔除
- 给出仓位建议区间
- 不直接下单

**输入**

- Screener
- Watchlist
- Regime
- Risk
- Backtest

**输出**

- 候选清单
- 仓位建议区间
- 行业分布建议

**可调用工具/模块**

- `src/stock_research/portfolio_backtest.py`
- `src/stock_research/reports/position_review_report.py`
- `src/stock_research/industry_exposure_risk_control.py`

**禁止行为**

- 不允许直接给买卖执行指令
- 不允许跳过 Risk Agent

**审核规则**

- 建议必须引用因子、风险和市场状态证据

**报告模板**

- 市场环境
- 候选分组
- 仓位建议
- 风险备注

**对应当前代码位置**

- `src/stock_research/portfolio_backtest.py`
- `src/stock_research/reports/position_review_report.py`

**参考外部项目**

- TradingAgents-CN
- RQAlpha

### 3.11 Review Agent

**职责**

- 检查报告是否有幻觉
- 检查是否引用数据证据
- 检查是否混淆事实与推理
- 检查是否违反自动交易限制

**输入**

- 所有 Agent 输出
- run_card
- 因子验证报告
- 回测 artifacts

**输出**

- 审核通过/驳回
- 审核问题清单
- 需要补证据项

**可调用工具/模块**

- 未来应新增：
  `src/stock_research/agents/review.py`
- 当前可复用：
  `src/stock_research/reporting.py`
  `src/stock_research/report_run_store.py`

**禁止行为**

- 不允许放行没有证据链的报告
- 不允许放行“必须买入”类结论

**审核规则**

- 每个结论需可追溯
- 每个未验证项需显式标注
- 每份报告需区分事实与推理

**报告模板**

- 审核状态
- 违规项
- 证据缺失项
- 修改建议

**对应当前代码位置**

- `src/stock_research/report_run_store.py`
- `src/stock_research/reporting.py`

**参考外部项目**

- AlphaEvo
- TradingAgents-CN

## 4. Agent 间流程

建议的主流程如下：

1. Data Quality Agent 先验收数据。
2. Universe Agent 生成统一股票池。
3. Factor Research Agent 管理候选因子与来源。
4. Factor Validation Agent 验证因子能否进入主评分。
5. Backtest Agent 验证策略和信号。
6. Regime Agent 给出市场和行业上下文。
7. Watchlist Agent 和 Stock Analyst Agent 生成个股级观察。
8. Risk Agent 标记风险。
9. Portfolio Manager Agent 汇总成候选与仓位建议。
10. Review Agent 做最终审稿。
11. 你本人做最终确认与交易决策。

## 5. AI Agent 禁止事项

- 直接下单
- 直接输出“必须买入”
- 用未经验证的新闻做强结论
- 忽略回测证据
- 混淆预测与事实
- 绕过 Risk Agent
- 绕过 Review Agent

## 6. 结论

这个 Agent 团队设计的核心，不是把投研“拟人化”，而是把当前仓库已有的数据、因子、回测、报告能力组织成可追溯的协作流水线。你始终是最终交易决策人，Agent 只负责把证据整理得更快、更清楚、更可复盘。
