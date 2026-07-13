# Stock Workspace Review Design

## Goal

Redesign the existing stock workspace so a human user can enter the page and answer the primary question:

`What should I do with this stock tomorrow?`

The page must remain a shared stock workspace for multiple entry points, but when opened from the Tech Bottleneck review flow it must also surface whether the bottleneck thesis is still credible enough to support continued review attention.

## Scope

This design covers the stock workspace page structure, reading order, information grouping, and source-aware emphasis rules.

This design does not cover:

- strategy logic changes
- score formula changes outside existing displayed inputs
- new external data adapters
- new writeback model changes
- full F10 replacement

## Current Problem

The current stock workspace in [dashboard/src/components/StockWorkspace.tsx](/Users/xiwei/stock_research/dashboard/src/components/StockWorkspace.tsx) behaves like a data container instead of a review workspace.

Main issues:

- It leads with raw blocks such as `行情快照`, `策略复盘摘要`, and `Evidence Digest` without first presenting a review conclusion.
- Tech Bottleneck entry data is split across two separate panels, `技术瓶颈候选上下文` and `Tech Bottleneck Report`, which creates duplication and breaks the reading flow.
- The right-side decision rail is structurally useful, but the page does not build enough context before asking the user to act.
- News, reports, market environment, and digest evidence are presented as peers instead of as evidence supporting a decision.

The result is that a user must manually synthesize the page instead of being guided through a repeatable review workflow.

## User Intent

The page is not primarily a行情 page and not primarily a long-form research archive.

It is a review decision page.

The expected reading order is:

1. Understand tomorrow's likely action.
2. Understand whether the reason for tracking the stock is still valid.
3. Understand what happened today in price and volume.
4. Understand what evidence supports or weakens the thesis.
5. Record a review decision and follow-up note.

## Chosen Direction

Use a single stock workspace with source-aware emphasis.

This is the selected approach over:

- `行情优先页`: familiar, but too trading-terminal-like and not review-first
- `研究档案页`: complete, but too slow to answer tomorrow's action

Chosen approach:

- Keep one common stock workspace for all sources.
- Make the top of the page always answer `明天怎么处理这只票`.
- When the source is `techBottleneck`, elevate thesis credibility and evidence-gap information directly below the action summary.
- Keep all other sections available, but reorganize them around the review decision flow.

## Source-Aware Behavior

The page must detect whether the user entered from Tech Bottleneck review context using existing `entryContext` signals such as:

- `sourceWorkspace === "techBottleneck"`
- existing tech bottleneck fields already carried into `StockEntryContext`

Behavior by mode:

### Generic review mode

- Top area focuses on tomorrow's handling decision.
- Standard context is shown in a compact source strip.
- Evidence sections remain generic.

### Tech Bottleneck enhanced mode

- Top area still focuses on tomorrow's handling decision.
- The next section becomes a `科技卡脖子 thesis` review block.
- This block must summarize whether the bottleneck thesis remains worth tracking, what evidence is missing, and whether the stock should remain in the bottleneck review universe.

The enhanced mode must not create a separate page. It is a layout emphasis change on the same workspace.

## Proposed Page Structure

### 1. Top Review Conclusion Band

Purpose:

- Answer the page's primary question in 5 to 10 seconds.

Content:

- stock name + code + review date
- `明日处理建议`
- `一句话结论`
- `结论置信度`
- top three decision drivers
- current review state badge such as `继续跟踪`, `等待确认`, `证据不足`, `降级观察`, `排除`

Behavior:

- This becomes the top-most content block after the workspace header.
- It replaces the current pattern where `行情快照` and `策略复盘摘要` appear before a decision summary.

### 2. Source Thesis Band

Purpose:

- Explain why this stock deserves attention from the current workflow.

Generic mode:

- compact `来源上下文`
- source workspace
- source object ids
- original match reason

Tech Bottleneck enhanced mode:

- merged replacement for the current `技术瓶颈候选上下文` and `Tech Bottleneck Report`
- section title should read as a thesis review block rather than a raw metadata block

Content for Tech Bottleneck mode:

- candidate source
- previous tier
- evidence strength
- bottleneck relevance
- research priority
- bottleneck confidence score
- evidence quality score
- report status
- report review decision
- evidence gap note
- next required validation step
- one rationale paragraph
- primary source link if present

Key rule:

- This section must answer `why is this stock in the Tech Bottleneck review universe, and does that still hold?`

### 3. Today's Market Behavior Band

Purpose:

- Explain what happened today in the tape before showing broad evidence.

Content:

- latest price
- change percent
- open, high, low, previous close
- turnover ratio
- volume ratio
- amount
- chart
- short behavior summary such as `放量突破`, `缩量整理`, `冲高回落`, `弱势承压`

Design rule:

- Raw quote data remains visible.
- Add a short machine-generated behavior interpretation line using already available derived metrics.
- This section keeps the current chart but reframes the surrounding metrics toward review interpretation rather than quote listing.

### 4. Evidence and Explanation Band

Purpose:

- Answer `why might tomorrow's action be justified?`

Structure:

- two-column evidence zone on desktop

Left column:

- `相关新闻 / 公告 / 研报摘要`
- only high-signal summary items should appear first

Right column:

- `Evidence Digest`
- strategy signal summary
- market environment hits

Design rule:

- These are not equal peer blocks anymore.
- They become supporting evidence for the decision in the top band.
- The page should prefer concise summaries and status cues over full raw dumps.

### 5. Business and Valuation Band

Purpose:

- Help decide whether the stock deserves continued research time.

Content:

- total market cap
- float market cap
- PE
- PB
- listing board
- exchange
- list date
- region
- concise company profile

Tech Bottleneck mode adds:

- industry-chain role
- key product or capability clue
- scarcity or substitution clue

Design rule:

- This sits below the decision-driving sections.
- It supports conviction and prioritization rather than leading the page.

### 6. Review Action Rail

Purpose:

- Let the user record the conclusion after reading.

Content:

- operator decision panel
- review notes
- follow-up requirement
- historical review log
- links out to news and reports workspace

Design rule:

- Keep the current right-rail pattern because it is useful for decision entry.
- Rename action labels and helper copy to match review workflow language.
- The rail must feel like the last step of a reasoning sequence, not the first task on the page.

## Information Hierarchy Rules

The page should consistently follow this hierarchy:

1. Action conclusion
2. Thesis validity
3. Today's behavior
4. Supporting evidence
5. Long-lived background context
6. Decision recording

This hierarchy applies even if some sections have sparse data.

When a section has little data, it should still explain the implication instead of only saying data is missing.

Example:

- Instead of only `No digest available`, say the digest is unavailable and the page should rely more heavily on chart, news, and manual review.

## Reuse and Refactoring Guidance

The redesign should reuse existing data-fetching behavior where possible.

Expected structural changes:

- Merge the two Tech Bottleneck top panels into one thesis-oriented block.
- Convert the current `策略复盘摘要` into the top review conclusion band.
- Reframe `行情快照` as the today-behavior band.
- Regroup `Evidence Digest`, `相关新闻`, `研报覆盖`, `个股市场环境`, and `策略信号` into a decision-support evidence zone.

This design should avoid adding parallel components that duplicate existing content with different labels.

## Decision Language

The page should use explicit review language rather than generic dashboard language.

Preferred labels:

- `明日处理建议`
- `今日价格行为`
- `支撑证据`
- `thesis 风险`
- `下一步验证`
- `复盘结论记录`

Avoid top-level labels that feel like passive archives:

- `Report panel`
- `Context metrics`
- `Signal summary`

These can still exist internally, but should not define the user's reading experience.

## Desktop and Mobile Behavior

Desktop:

- top conclusion band spans full width
- thesis band spans full width below it
- action rail remains on the right
- evidence zone uses two columns

Mobile:

- stack in the same reasoning order
- action rail collapses into a normal bottom section
- top conclusion band and thesis band remain first and visually dominant

The same reading order must survive both layouts.

## Testing Expectations

Design validation should cover:

- generic stock workspace path still renders a usable action-first page
- tech bottleneck entry path surfaces thesis review content near the top
- no duplicated thesis metadata remains in separate top panels
- key headings follow the intended reading order
- decision rail still works after layout regrouping

## Success Criteria

The redesign is successful when a user can open a stock page and answer:

- what should I do with this stock tomorrow
- what are the two or three strongest reasons
- if this came from Tech Bottleneck review, is the bottleneck thesis still credible enough to continue tracking

without needing to scan the entire page first.
