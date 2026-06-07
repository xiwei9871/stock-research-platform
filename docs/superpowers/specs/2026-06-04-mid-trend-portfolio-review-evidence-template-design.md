# Mid Trend Portfolio Review Evidence Template Design

## 1. Goal

在现有 `mid_trend_portfolio_review` 基础上，把单票证据从“轻量文本摘要”提纯为“可统计、可验证、可追溯”的结构化证据模板。

本轮范围只覆盖：

- `Top5/Top10`
- `mid_trend_portfolio_review` 这条链

本轮不做：

- 通用跨策略证据框架
- 龙虎榜 / short-term / failure event 共用抽象
- 新评分系统

## 2. Why

当前报告已经能看，但两个问题仍然明显：

1. `main_positive_evidence / main_risk_evidence` 仍偏展示层文本，不利于后续统计“哪类证据最有用”。
2. 每只股票的“为什么持有 / 为什么调入 / 为什么调出 / 为什么只讨论”还没有拆成稳定的证据类别，后面难以做复盘归因。

因此本轮目标不是把文案写得更像投研报告，而是先把证据模板标准化，让后续 review、分层统计、规则验证都能复用。

## 3. Design Principles

### 3.1 Evidence first

所有结论必须来自项目内已有结构化数据或项目生成的公开研报摘要。

不允许引入：

- 临时网页搜索
- 当日外部新闻
- 人工主观补句

### 3.2 Structured detail + summary text

每类证据同时保留两层：

1. `structured detail`
   - 标签
   - 原始值
2. `summary text`
   - 供 Markdown 直接展示

### 3.3 Mid-trend only

字段命名和规则先服务于 `mid_trend_portfolio_review`。

允许未来扩展，但本轮不为了未来抽象牺牲当前清晰度。

### 3.4 No new score

本轮只是把证据拆开，不增加新的综合分数，不改现有排序逻辑，不改 `final_label` 规则。

## 4. Chosen Approach

采用“直接扩展 `review_rows` 表头”的方案，不新建独立 evidence 长表。

原因：

- 改动小
- 与现有 `Markdown + CSV` 产物兼容
- 最快形成可统计基础
- 后续若确实需要跨策略复用，再从这套字段抽象出去

## 5. Evidence Categories

新增 4 类证据，每类都含：

- 标签字段
- 原始值字段
- 汇总文本字段

### 5.1 Trend Evidence

解释该股票为什么在当前环境下表现为 mid-trend 候选。

字段：

- `trend_market_regime_tag`
- `trend_mainline_status_tag`
- `trend_layer_tag`
- `trend_score_band_tag`
- `trend_market_regime_value`
- `trend_mainline_status_value`
- `trend_layer_value`
- `trend_funnel_score_value`
- `trend_evidence_summary`

### 5.2 Research Evidence

解释该股票是否有研报/PDF 支撑，以及支撑强弱。

字段：

- `research_support_band_tag`
- `research_report_coverage_tag`
- `research_target_price_coverage_tag`
- `research_profit_forecast_coverage_tag`
- `research_support_score_value`
- `research_report_count_90d_value`
- `research_target_price_count_value`
- `research_profit_forecast_count_value`
- `research_evidence_summary`

### 5.3 Risk Evidence

解释该股票当前的硬风险、研报风险披露、环境/覆盖缺口。

字段：

- `risk_fundamental_hard_risk_tag`
- `risk_pdf_risk_coverage_tag`
- `risk_regime_warning_tag`
- `risk_research_gap_tag`
- `risk_fundamental_hard_risk_value`
- `risk_pdf_risk_count_value`
- `risk_research_support_score_value`
- `risk_pdf_risk_excerpt_value`
- `risk_evidence_summary`

### 5.4 Rebalance Reason Evidence

解释该股票为什么调入、调出、继续持有、或仅讨论。

字段：

- `rebalance_action_tag`
- `rebalance_membership_tag`
- `rebalance_rank_bucket_tag`
- `rebalance_trade_reason_tag`
- `rebalance_is_current_holding_value`
- `rebalance_is_new_buy_value`
- `rebalance_is_candidate_sell_value`
- `rebalance_candidate_rank_value`
- `rebalance_trade_reason_value`
- `rebalance_reason_evidence_summary`

## 6. Tagging Rules

### 6.1 Trend tags

#### `trend_market_regime_tag`

直接映射：

- `mainline`
- `rotation`
- `broad_market`
- `weak`
- `unknown`

#### `trend_mainline_status_tag`

直接映射 `mainline_status`，缺失时为 `unknown`。

#### `trend_layer_tag`

直接映射 `mid_trend_layer`，缺失时为 `unknown`。

#### `trend_score_band_tag`

基于 `mid_trend_funnel_score` 分桶：

- `elite`：`>= 85`
- `strong`：`>= 80 and < 85`
- `borderline`：`>= score_floor and < 80` 或存在但低于 80
- `unknown`：缺失

### 6.2 Research tags

#### `research_support_band_tag`

基于 `research_support_score_pit`：

- `high_support`：`>= 20`
- `mid_support`：`> 0 and < 20`
- `no_support`：`<= 0`
- `unknown`：缺失

#### `research_report_coverage_tag`

基于 `broker_report_count_90d`：

- `dense_coverage`：`>= 3`
- `light_coverage`：`1-2`
- `no_coverage`：`0`
- `unknown`：缺失

#### `research_target_price_coverage_tag`

基于 `pdf_target_price_count_90d`：

- `target_price_available`：`>= 1`
- `target_price_missing`：`0`
- `unknown`：缺失

#### `research_profit_forecast_coverage_tag`

基于 `pdf_profit_forecast_count_90d`：

- `forecast_available`：`>= 1`
- `forecast_missing`：`0`
- `unknown`：缺失

### 6.3 Risk tags

#### `risk_fundamental_hard_risk_tag`

规则：

- 若 `fundamental_hard_risk` 为空或 `no_clear_hard_risk`，则为 `no_clear_hard_risk`
- 否则直接使用原值

#### `risk_pdf_risk_coverage_tag`

基于 `pdf_risk_section_count_90d`：

- `risk_disclosed`：`>= 1`
- `risk_not_disclosed`：`0`
- `unknown`：缺失

#### `risk_regime_warning_tag`

规则：

- 若 `market_regime != mainline`，或 `mainline_status` 含 `weak`，则为 `regime_warning`
- 否则为 `no_regime_warning`

#### `risk_research_gap_tag`

基于 `research_support_score_pit`：

- `research_gap`：`<= 0`
- `limited_support`：`> 0 and < 20`
- `supported`：`>= 20`
- `unknown`：缺失

### 6.4 Rebalance tags

#### `rebalance_action_tag`

规则：

- `new_buy`
- `candidate_sell`
- `hold_no_trade`
- `discussion_only`

#### `rebalance_membership_tag`

规则：

- `current_holding`
- `not_holding`

#### `rebalance_rank_bucket_tag`

基于 `candidate_rank`：

- `top3`
- `top5`
- `top10`
- `out_of_scope`

#### `rebalance_trade_reason_tag`

规则：

- 若 `trade.reason` 有值，取其值
- 若无值且 `rebalance_action_tag == hold_no_trade`，则为 `carry_forward_hold`
- 若无值且 `rebalance_action_tag == discussion_only`，则为 `no_trade_signal`

## 7. Summary Text Rules

### 7.1 Trend summary

必须只引用：

- `market_regime`
- `mainline_status`
- `mid_trend_layer`
- `mid_trend_funnel_score`

示例：

- `主线环境: mainline; 趋势结构: stable_trend_watch / score=84.7`

### 7.2 Research summary

必须只引用：

- `research_support_score_pit`
- `broker_report_count_90d`
- `pdf_target_price_count_90d`
- `pdf_profit_forecast_count_90d`

示例：

- `研报/PDF覆盖: support=33, reports=3, target=3, forecast=2`

### 7.3 Risk summary

必须只引用：

- `fundamental_hard_risk`
- `pdf_risk_section_count_90d`
- 清洗后的 `latest_pdf_risk_summary`
- regime/support warning

### 7.4 Rebalance summary

必须只引用：

- 是否持仓
- 是否新买
- 是否候选卖出
- 候选排名
- trade reason

示例：

- `动作: new_buy; 排名: top5; reason=weekly_rebalance`
- `动作: hold_no_trade; 排名: top3; reason=carry_forward_hold`

## 8. Interaction With Existing Fields

保留现有字段：

- `main_positive_evidence`
- `main_risk_evidence`
- `why_hold_or_change`

但语义调整为展示层聚合字段：

- `main_positive_evidence`
  - 由 `trend_evidence_summary` + `research_evidence_summary` 组合
- `main_risk_evidence`
  - 由 `risk_evidence_summary` 为主，必要时拼入 `rebalance_reason_evidence_summary`
- `why_hold_or_change`
  - 保留现有动作语义，不承担完整证据表达职责

## 9. Output Changes

### 9.1 CSV

新增字段直接进入 `mid_trend_portfolio_review_<date>.csv`。

CSV 目标：

- 单票分析
- 后续批量统计
- Top5/Top10 讨论时横向对比

### 9.2 Markdown

Markdown 不必把所有结构化字段全部铺开。

展示层原则：

- 保留摘要文本
- 需要时可追加一小行关键 tag
- 不让报告因为字段爆炸而失去可读性

## 10. Testing Requirements

至少覆盖：

1. 新增 4 类 evidence 字段能生成。
2. 各类 tag 在典型输入下分桶正确。
3. `rebalance_reason_evidence` 在非调仓持仓日也不为空。
4. `main_positive_evidence` / `main_risk_evidence` 与新 summary 聚合逻辑一致。
5. 没有 research 覆盖时仍能输出 trend/risk/rebalance 证据。
6. 不改变现有 `final_label` 逻辑。
7. 不破坏现有 CLI 和 Markdown/CSV 基本产物。

## 11. Non-goals

本轮不做：

- 证据有效性统计报告
- 跨 trade_date 聚合分析 CLI
- 通用 evidence 长表 schema
- 把这套 evidence 直接接入策略排序

## 12. Next Step

实现阶段按最小改动原则：

1. 在 `review_rows` 扩字段；
2. 增加 tag/value/summary helper；
3. 保持现有 CLI 不变；
4. 先补测试，再改实现。
