# Mid Trend Portfolio Review Markdown Layout Design

## 1. Goal

优化 `mid_trend_portfolio_review` 的 Markdown 展示层，使其更适合每日持仓/调仓讨论。

本轮范围只改：

- Markdown 渲染结构

本轮不改：

- CSV 字段口径
- 证据分类逻辑
- 排序逻辑
- `final_label` 逻辑

## 2. Why

当前 `mid_trend_portfolio_review` 的 CSV 已经具备：

- `Top5/Top10`
- 4 类结构化证据
- 聚合后的正面/风险摘要

但 Markdown 仍以大表为主。大表适合导出，不适合日常讨论，因为：

1. `Top5` 需要按单票逐只读，而不是横向扫大表。
2. 证据已经被拆成 4 类，继续塞在一个表里不利于阅读。
3. `Top6-10` 仍适合简表，不需要和 `Top5` 一样展开。

因此展示层需要分化：

- `Top5`：单票小节
- `Top6-10`：简表

## 3. Chosen Approach

采用方案 A：

- `Top5` 改成“每只股票一个小节 + 4 个证据块”
- `Top6-10` 保留简表

原因：

- 最符合每日 review 的工作流
- 只改 Markdown，不会影响 CSV 的可统计性
- `Top5` 深读，`Top6-10` 速览，职责清晰

## 4. Final Markdown Structure

完整结构调整为：

1. `# Mid Trend Portfolio Review <trade_date>`
2. `## Portfolio Summary`
3. `## Top5 Overview`
4. `## Evidence Snapshot`
5. `## Top5 Execution Pool`
6. `## Top6-10 Discussion Pool`

## 5. Section Design

### 5.1 Portfolio Summary

保留现有组合级摘要字段：

- `strategy_variant`
- `top5_count`
- `top6_10_count`
- `holding_count`
- `buy_count`
- `sell_count`
- `rebalance_triggered`
- `rebalance_reason_summary`

仍采用短列表展示。

### 5.2 Top5 Overview

新增一个很短的全局概览，内容只服务于快速扫一眼：

- 当前 `Top5` 名单
- 调入名单（若有）
- 调出名单（若有）

目标：

- 让人不用往下翻，也知道今天的执行池是谁

### 5.3 Evidence Snapshot

新增一个很短的统计摘要，基于当前 `Top5`：

- `high_support` 数量
- `research_gap` 数量
- `regime_warning` 数量
- `new_buy` 数量
- `hold_no_trade` 数量

目标：

- 快速感知今天执行池的证据结构

### 5.4 Top5 Execution Pool

不再用大表，而是每只股票一个小节。

每只股票展示格式：

```markdown
### 1. 生益科技 / 600183.SH
- 最终标签：高优先级持有
- 当前角色：持有
- 排名/分数：Top1 / 84.7
- 主线状态：mainline / sustained_mainline
- 调仓动作：hold_no_trade

**Trend Evidence**
- tags: mainline / sustained_mainline / stable_trend_watch / strong
- summary: 主线环境: mainline; 趋势结构: stable_trend_watch / score=84.7

**Research Evidence**
- tags: high_support / dense_coverage / target_price_available / forecast_available
- summary: 研报/PDF覆盖: support=33, reports=3, target=3, forecast=3

**Risk Evidence**
- tags: no_clear_hard_risk / risk_disclosed / no_regime_warning / supported
- summary: 风险段: count=3, 下游需求不及预期风险

**Rebalance Reason Evidence**
- tags: hold_no_trade / current_holding / top3 / carry_forward_hold
- summary: 动作: hold_no_trade; 排名: top3; reason=carry_forward_hold

**结论**
- positive: <main_positive_evidence>
- risk: <main_risk_evidence>
```

### 5.5 Top6-10 Discussion Pool

继续保留简表，不展开成单票小节。

简表列固定为：

- `candidate_rank`
- `stock_name`
- `ts_code`
- `mid_trend_funnel_score`
- `final_label`
- `trend_score_band_tag`
- `research_support_band_tag`
- `risk_research_gap_tag`
- `rebalance_action_tag`
- `why_hold_or_change`

目标：

- 快速回答“为什么它只在讨论池，不在执行池”

## 6. Rendering Rules

### 6.1 Top5 raw values do not expand

Markdown 中不直接展开所有 `*_value` 原始值。

这些值继续保留在 CSV 中，供后续统计和横向对比使用。

Markdown 只展示：

- 每类 evidence 的 `tags`
- 每类 evidence 的 `summary`

### 6.2 Empty summary fallback

若某类 summary 为空：

- 展示 `summary: <empty>`

不要整块省略。原因：

- 讨论时“没有证据”本身就是信息

### 6.3 Stable ordering

`Top5` 小节顺序严格按 `candidate_rank` 升序。

`Top6-10` 简表顺序也严格按 `candidate_rank` 升序。

### 6.4 Consistent terminology

展示层统一使用：

- `最终标签`
- `当前角色`
- `排名/分数`
- `主线状态`
- `调仓动作`

不要混用旧文案。

## 7. Data Dependencies

本轮只依赖当前 `review_rows` 已有字段：

- 基础字段
- 4 类 evidence 的 `tag` / `summary`
- `main_positive_evidence`
- `main_risk_evidence`

不新增新的数据输入。

## 8. Testing Requirements

至少覆盖：

1. Markdown 中出现 `Top5 Overview`。
2. Markdown 中出现 `Evidence Snapshot`。
3. `Top5` 渲染为单票小节而不是表格。
4. 每只 `Top5` 股票都展示 4 个 evidence block。
5. `Top6-10` 仍然渲染为简表。
6. 不改变 CSV 输出。

## 9. Non-goals

本轮不做：

- Markdown 样式美化
- HTML 报告
- 折叠式布局
- 额外图表
- cross-trade-date 统计摘要

## 10. Next Step

实现时优先改 `_render_markdown()` 及其辅助函数：

1. 新增 `Top5 Overview` / `Evidence Snapshot`
2. 新增 `Top5` 单票小节渲染函数
3. 保留 `Top6-10` 简表渲染函数
4. 用最小测试覆盖新版版式
