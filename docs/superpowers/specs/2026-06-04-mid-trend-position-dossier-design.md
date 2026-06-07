# Mid Trend Position Dossier Design

## 1. Goal

新增一个上层正式报告模块，用于在 `mid_trend_portfolio_review` 之上生成“给人读的正式持仓/调仓报告”。

该模块的目标不是替代现有结构化 review，而是消费现有：

- `portfolio_review`
- `research_packet`
- `stock_report_feature_daily / PDF 提取`
- 行业/公司资料字段

并输出一份更适合人工决策讨论的正式报告。

## 2. Positioning

这个模块是：

- 人类可读的持仓报告
- 决策支持层
- Top5/调仓候选深度说明层

这个模块不是：

- 排序引擎
- 回测模块
- 自动交易信号模块
- 全市场批量选股模块

## 3. Why A New Module

不直接继续扩展 `mid_trend_portfolio_review`，原因是职责已经不同。

`mid_trend_portfolio_review` 当前承担的是：

- 持仓状态
- 调仓状态
- 结构化证据
- Markdown/CSV 底座输出

而新的正式报告需要承担的是：

- 决策结论
- 投研论证
- 调入/调出替代讨论
- 人读的叙事结构

因此它应当是上层产品，消费现有结构化底座，而不是继续压在同一个渲染模块里。

## 4. Modes

模块第一版支持双模式。

### 4.1 replay mode

严格使用 `as-of trade_date` 可以获得的信息。

用途：

- 研究回放
- 历史复盘
- 避免后视偏差

要求：

- 不允许使用 `trade_date` 之后的公开研报
- 不允许使用之后补到的外部增强资料

### 4.2 live mode

允许在 `Top5/Top10` 生成之后，补当天最新可得的公开资料。

用途：

- 每日模拟盘
- 人工交易辅助
- 盘前/盘后讨论

第一版允许补充：

- 公开研报摘要
- 目标价 / 盈利预测 / 风险摘要
- 行业/公司资料

第一版不引入：

- 新闻舆情
- 实时公告增强

## 5. Scope

第一版聚焦三个对象：

1. `当前持仓 Top5`
2. `候选调入名单`
3. `候选调出名单`

不再默认把 `Top6-10` 全部平铺成讨论池。

## 6. Inputs

### 6.1 Required

- `mid_trend_portfolio_review_<date>.csv`
- `mid_trend_research_packet_candidates.csv`

### 6.2 Optional / preferred

- `stock_report_feature_daily` 的 PIT 输出
- PDF 提取字段
- 行业/公司资料字段：
  - `industry_position_note`
  - `product_position_note`
  - `moat_or_scarcity_note`
  - `negative_research_note`
  - `institution_names`
  - `target_price`
  - `target_upside`
  - `latest_rating`

### 6.3 Not in v1

- 新闻舆情
- 公告事件
- 临时网页搜索作为默认输入

## 7. Outputs

第一版标准产物：

1. `Markdown` 正式报告
2. `CSV` 摘要表

## 8. Report Structure

正式报告结构固定为：

1. `组合级执行摘要`
2. `当前持仓 Top5`
3. `候选调入名单`
4. `候选调出名单`
5. `附录：结构化证据摘要表`

## 9. Combination-Level Executive Summary

这一节回答组合层面最重要的问题。

字段/内容：

- 当前组合结论
- 是否建议调仓
- 建议调入名单
- 建议调出名单
- 当前组合的主线暴露
- 当前组合最强支持点
- 当前组合最大风险点

展示目标：

- 让读者在不读单票之前，先知道今天组合层面的态度

## 10. Current Holdings Top5

每只股票使用“双层结构”。

### 10.1 Execution Conclusion Layer

字段：

- `当前结论`
  - 高确信持有
  - 中性持有
  - 低确信持有
  - 不建议继续持有
- `一句话判断`
- `支持持有的 3 条核心证据`
- `反对持有的 2 条核心证据`
- `今天最关键观察点`

这一层回答：

- 我今天对这只票的态度是什么
- 为什么不是别的态度

### 10.2 Research Reasoning Layer

小节：

1. `它在涨什么`
2. `行业/主线位置`
3. `行业地位与产品地位`
4. `机构支持逻辑与分歧点`
5. `技术与趋势状态`
6. `主要风险与反例`
7. `证伪条件 / 继续跟踪点`

这一层回答：

- 这个逻辑是否站得住
- 这个逻辑会因为什么失效

### 10.3 Structured Evidence Appendix

每只股票最后附简洁的结构化证据块：

- trend evidence
- research evidence
- risk evidence
- rebalance evidence

这部分用于：

- 追溯
- 核字段
- 辅助横向比较

## 11. Candidate Additions

候选调入名单只写最值得讨论的候选，不需要平铺所有 `Top10`。

每只候选至少回答：

- 当前结论：`候选调入` 或 `继续观察`
- 为什么它值得替代现有持仓
- 最大短板是什么
- 如果调入，替代谁更合理

## 12. Candidate Reductions

候选调出名单只列当前持仓中最弱的 1-3 只。

每只至少回答：

- 当前结论：中性持有 / 低确信持有 / 不建议继续持有
- 为什么它进入候选调出
- 是趋势走弱、逻辑走弱，还是证据缺失
- 如果不调出，接下来要看什么条件

## 13. Appendix Table

附录使用紧凑表格，支持快速对照。

建议列：

- `stock_name`
- `ts_code`
- `current_decision`
- `trend tags`
- `research tags`
- `risk tags`
- `rebalance tags`

## 14. Data Usage Rules

### 14.1 replay mode

只能使用 `trade_date` 当时可得数据。

### 14.2 live mode

允许补当天定向增强资料，但必须在报告头部明确标注：

- `mode = live`
- `enhanced_sources_used = yes/no`

## 15. Readability Principles

报告的主叙事必须按人的阅读顺序组织：

1. 先给结论
2. 再给支持与反对证据
3. 再展开投研论证
4. 最后附结构化字段

禁止直接把大量机器字段堆成正文。

## 16. CSV Summary

CSV 摘要表只保留对比最有用的字段，不复制整份 `portfolio_review`。

建议包括：

- 股票标识
- 当前结论
- 一句话判断
- 3 条支持证据摘要
- 2 条反对证据摘要
- 候选调入/调出标签
- trend/research/risk/rebalance tags

## 17. Likely Module Boundary

新增独立模块，例如：

- `src/stock_research/mid_trend_position_dossier.py`

职责：

- 读取上游结构化输入
- 组装人读报告对象
- 输出 Markdown + CSV

不修改现有：

- `mid_trend_portfolio_review` 的底层结构化职责

## 18. Testing Requirements

至少覆盖：

1. `replay` / `live` 两种模式均能运行。
2. 正式报告包含 5 个大章节。
3. `当前持仓 Top5` 使用双层结构。
4. `候选调入名单` 能生成。
5. `候选调出名单` 能生成。
6. 附录结构化表能生成。
7. 无行业/公司增强资料时不崩溃，退化为较浅版本。
8. 不改变现有 `portfolio_review` CSV 结构。

## 19. Non-goals

第一版不做：

- 新闻舆情增强
- 公告增强
- 自动外部搜索默认流程
- 新的评分系统
- 自动交易建议

## 20. Next Step

先进入 implementation plan，明确：

1. 上游输入契约
2. 双模式数据选择规则
3. Markdown/CSV 结构
4. 测试用例
