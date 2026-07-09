# Stock Workspace Dual-Mode Design

## Goal

Extend the stock workspace into one unified review page that serves two closely related use cases:

1. `普通看票`
2. `科技卡脖子看票`

The page must help a human reviewer answer the primary question:

`明天怎么处理这只票？`

At the same time, when the stock is opened from the Tech Bottleneck workflow, the page must also answer:

`这只票的科技卡脖子 thesis 还成立吗？`

## Chosen Direction

Use one shared stock workspace with source-aware enhancement.

This is the selected `方案 C`.

It keeps a common stock review skeleton for every entry point, while selectively elevating Tech Bottleneck thesis content when the page is opened from the Tech Bottleneck review flow.

This avoids splitting the product into:

- one generic stock page
- one separate Tech Bottleneck stock page

That split would duplicate logic, fragment review behavior, and make maintenance worse.

## Core Principle

The page must not be organized around data domains first.

It must be organized around review decisions first.

The reading order should be:

1. What should I do tomorrow?
2. Why does this stock deserve attention?
3. What happened today in price and volume?
4. What evidence supports or weakens the review thesis?
5. Is the company fundamentally worth more review time?
6. What decision do I record now?

## Two Modes On One Page

### Generic review mode

This is used when the user opens a stock from:

- search
- watchlist
- news
- research reports
- review queue
- market monitor

The page emphasizes:

- tomorrow's action
- company basics
- business structure
- today's price behavior
- supporting evidence

### Tech Bottleneck enhanced mode

This is used when the user opens a stock from:

- `entryContext.sourceWorkspace === "techBottleneck"`

The page keeps the same overall structure but adds an elevated thesis band near the top.

This mode emphasizes:

- bottleneck role
- key product or technical capability
- evidence quality
- evidence gaps
- next validation step
- whether the stock still deserves a place in the bottleneck review universe

## Unified Page Structure

The page should use one shared skeleton in this exact order.

### 1. 明日处理结论

Purpose:

- Answer the primary review question in 5 to 10 seconds.

Content:

- stock name
- code
- review date
- `明日处理建议`
- `一句话结论`
- `结论置信度`
- three strongest decision drivers

Examples of action labels:

- 继续观察
- 重点跟踪
- 等待确认
- 降级观察
- 排除

This section is required in both modes.

### 2. 公司基础信息

Purpose:

- Give the reviewer the minimum company identity context that all mainstream stock platforms expose.

This section is currently underpowered and must be expanded.

Required content:

- 行业
- 细分赛道
- 主营业务简介
- 主要产品 / 解决方案
- 上市板块
- 交易所
- 上市日期
- 地区
- 公司简况摘要

Design rule:

- This is not optional.
- A reviewer should not need to leave the page to understand what the company actually does.

### 3. 主营构成与经营质量

Purpose:

- Help a normal reviewer decide whether the stock deserves continued attention.

Required content:

- 产品营收分布
- 行业营收分布
- 地区营收分布
- recent revenue
- net profit
- gross margin
- ROE
- operating cash flow
- debt ratio

If some structure data is unavailable, the page should say that clearly and continue showing the available financial summary.

Design rule:

- This section is core for generic stock review.
- It should sit above pure evidence browsing because it answers `这家公司靠什么赚钱` and `这些业务是否有质量`.

### 4. 科技卡脖子 thesis 复盘

This section appears in both modes only if relevant data exists, but it must be elevated in Tech Bottleneck enhanced mode.

Purpose:

- Answer whether the bottleneck thesis is still credible.

Required content:

- thesis 判断
- bottleneck_confidence_score
- evidence_quality_score
- report_status
- review_decision
- evidence_gap_note
- next validation step
- source group
- previous tier
- manual approval category
- key rationale summary

Enhanced content when available:

- bottleneck chain position
- key product tied to the thesis
- evidence of customer, certification, order, capacity, or revenue trace
- route-around / substitutability risk

Design rule:

- In Tech Bottleneck mode this section must appear directly after the top decision band or directly after company basics, depending on final layout tuning.
- In generic mode it can remain visible but secondary when Tech Bottleneck source context is absent.

### 5. 今日价格行为

Purpose:

- Explain what happened today in the tape.

Required content:

- latest price
- change percent
- open
- high
- low
- previous close
- turnover
- volume ratio
- amount
- price chart
- behavior state label

Recommended interpretation layer:

- 放量突破
- 缩量整理
- 冲高回落
- 弱势承压
- 震荡

Design rule:

- The section should remain visually strong.
- It supports tomorrow's action, but it should not displace company basics in the information hierarchy.

### 6. 支撑证据

Purpose:

- Explain why tomorrow's action and any thesis judgment might be justified.

Required content:

- Evidence Digest
- relevant news
- announcements when available
- research report summary
- market environment hits
- strategy signal summary

Design rule:

- Evidence should be prioritized and summarized.
- High-signal evidence belongs first.
- The user should not need to scan full raw lists to know what matters.

### 7. 复盘操作

Purpose:

- Let the user record their conclusion after reviewing the page.

Required content:

- operator decision panel
- review notes
- follow-up requirement
- review log
- links out to news and reports workspaces

Design rule:

- This should remain persistently usable.
- It should feel like the final step in the review sequence, not the first.

## Mode-Specific Priorities

### Generic mode priority

The most important information order is:

1. 明日处理结论
2. 公司基础信息
3. 主营构成与经营质量
4. 今日价格行为
5. 支撑证据
6. 复盘操作

### Tech Bottleneck mode priority

The most important information order is:

1. 明日处理结论
2. 科技卡脖子 thesis 复盘
3. 公司基础信息
4. 主营构成与经营质量
5. 今日价格行为
6. 支撑证据
7. 复盘操作

The difference is emphasis, not a separate page.

## Required Data Expansion

The current stock workspace already exposes quote, valuation, decision, and some evidence content.

The biggest missing layer is company and business fundamentals.

This redesign therefore requires expanding the stock workspace data contract to support at least:

- industry
- sub-industry or theme lane
- business overview
- main products
- revenue structure
- financial summary

Potential data sources inside the current repository may include:

- existing `company_profile`
- existing valuation snapshot fields
- financial and revenue structure loaders already present in the broader codebase
- Tech Bottleneck source-backed research artifacts where generic company profile data is missing

This phase should not assume every field exists now, but the page design must reserve clear places for them.

## Styling Direction

The page should feel like a serious review desk, not a generic data dashboard.

Styling should reinforce reading order:

- bold, high-contrast decision band
- thesis band visually distinct in Tech Bottleneck mode
- company basics and business structure grouped cleanly with compact cards
- today's price behavior visually separate from background fundamentals
- evidence area denser but still scannable

Desktop:

- decision and thesis bands span full width
- evidence can use a two-column inner layout
- review action rail remains usable on the side

Mobile:

- keep the same reading order
- collapse side rail into bottom section
- decision and thesis sections remain visually dominant

## Success Criteria

The design is successful when a reviewer can open a stock page and quickly answer:

- what should I do with this stock tomorrow
- what does this company actually do
- what are its main products and business structure
- whether the business quality is worth further attention
- if opened from Tech Bottleneck review, whether the bottleneck thesis still stands

without switching to an external platform just to get basic company understanding.
