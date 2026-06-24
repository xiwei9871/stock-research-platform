## Summary

Integrate the newer Ops Snapshot capability into the current `http://127.0.0.1:5174/` home page, but do not surface it as a separate English operational widget. Instead, absorb the operational signal into a Chinese home experience centered on one concise `运行审计摘要` section plus the existing compact top-line status row. Keep `Public Snapshot` as a separate public-only route and build target.

This change also replaces the current `策略打分审计处理建议` block with a more useful `运行审计摘要` block. The new block is not an action inbox. It is a trust-and-readiness summary for the current display trade date: what data is missing, stale, or not rerun yet, and whether the operator can trust today’s dashboard outputs.

## Problem

The current home page shows a warning-oriented strategy score audit panel that has three issues:

1. It reports anomaly labels without explaining their practical impact on today's use of the platform.
2. It shows only sample rows, which can hide the actual distribution of issues across strategies.
3. Its action buttons (`查看复盘队列`, `打开策略实验室`, `查看生成报告`) are weak navigation aids rather than meaningful remediation actions.

Separately, the newer Ops Snapshot / Public Snapshot capability exists in the main repository but is not integrated into the `v0.1-local-eod-web` home page. As a result, the user still lacks a single home-page answer to:

- Did daily bars arrive?
- Are minute bars available?
- Were the three official strategies rerun for the display date?
- Are review artifacts available?
- Is any source stale enough to weaken confidence today?

## Goals

1. Replace the current home-page audit action panel with a concise Chinese-language `运行审计摘要`.
2. Integrate the most useful Ops Snapshot signals into the current home page without adding a second competing operational panel.
3. Preserve the current top-line status strip and health-check expansion pattern.
4. Keep `Public Snapshot` as an independent `/public` route and public-only build target.
5. Make the home page answer whether the current display date is trustworthy for research and review.

## Non-Goals

1. Do not build a general remediation console with rerun buttons in this phase.
2. Do not merge the full public snapshot content into the internal home page.
3. Do not add write actions to the dashboard.
4. Do not redesign the entire home page information architecture beyond the status/audit area.

## User Experience

### Home Page Layout

The top of the current home page will be organized into three layers:

1. **Compact top-line status row**
   - Keep the existing concise row:
     - 平台日期
     - 数据健康
     - 策略就绪
     - 复盘就绪
     - 风险状态

2. **运行审计摘要**
   - Replace `策略打分审计处理建议`
   - Present a small number of operational trust sections with direct language
   - Focus on today’s display trade date, not historical sample rows

3. **健康检查**
   - Keep the existing expandable health-check section
   - Continue to hold detailed readiness groups and per-module status

### Running Audit Summary Content

The new `运行审计摘要` block should summarize the display trade date with five rows/cards:

1. **基础行情**
   - Answers whether daily bars and minute bars are available and fresh enough
   - Example statuses:
     - 正常
     - 缺少日K
     - 缺少分钟线
     - 分钟线未补齐

2. **评分链路**
   - Answers whether strategy score lineage is trustworthy
   - Includes anomaly rollups such as:
     - LHB 原始分缺失 5 条
     - Mid Trend 来源过期 3 条
   - No stock sample rows in the summary block

3. **策略执行**
   - Answers whether the three official strategies were rerun for the current display date
   - Example:
     - 正常，3/3 已完成
     - 需关注，2/3 已完成
     - 阻塞，今日策略尚未重跑

4. **复盘产物**
   - Answers whether core internal review outputs exist for the display date
   - Includes:
     - Review Queue
     - Evidence Digest snapshots
     - Daily Review artifact if available in this branch

5. **内容链路**
   - Answers whether news/report content is materially usable
   - Show key staleness only when relevant enough to affect confidence
   - Example:
     - 正常
     - 需关注，研报最新发布日期 2026-06-03

### Summary Style

Each section in `运行审计摘要` must contain:

1. A section label
2. A normalized status chip:
   - 正常
   - 需关注
   - 阻塞
3. One short plain-language sentence

Example:

- `评分链路 · 需关注`
- `LHB 原始分缺失 5 条，Mid Trend 来源过期 3 条，今日分数可看但可信度下降。`

### Buttons

Remove the current three weak navigation buttons from the audit block.

Replace them with at most two lightweight links/buttons:

1. `查看健康检查`
   - Scroll or navigate to the existing health-check section

2. `查看审计明细`
   - Opens the existing strategy score audit detail route or the most specific existing page/route available in this branch
   - If no richer dedicated detail page exists, this may temporarily navigate to the strategy score audit source view indirectly, but the label must still reflect that it is a detail view, not a “fix” action

No “处理建议”, “重跑”, or other operationally misleading buttons should appear in this phase.

## Ops Snapshot Integration

### What To Reuse

From the newer Ops Snapshot implementation, reuse only the signals needed for the internal home page:

- workflow overall state
- current stage
- intervention required or not
- latest ready trade date
- feed states:
  - daily
  - minute5
  - deps

### How To Present It

Do not render an English `Ops Snapshot` card on the home page.

Instead, fold the information into Chinese home semantics:

- `运行状态：正常 / 延迟 / 阻塞`
- `当前阶段：daily / minute5 / deps`
- `人工介入：需要 / 不需要`
- `就绪交易日：YYYY-MM-DD`

These values should influence:

1. the top-line row where appropriate
2. the `运行审计摘要` conclusions
3. the health-check detail section if extended detail is needed

### Public Snapshot

`Public Snapshot` remains separate:

- Keep `/public` route support
- Keep `VITE_PUBLIC_SNAPSHOT_ONLY=true pnpm build`
- Do not add a large public snapshot block to the internal home page
- Optional future work may add a tiny link in a secondary location, but not in this phase

## Data Mapping Rules

### Display Date Authority

All home audit summary judgments must be anchored to the current dashboard `display_trade_date`, not simply the latest available market date.

### Foundation Market Data

Base this section on the integrated Ops Snapshot feed statuses plus readiness information:

- If daily feed is missing or blocked for display date -> `阻塞`
- If minute5 feed is missing, stale, or still pending when it should be ready -> `需关注` or `阻塞` depending on severity
- If both are ready for display date -> `正常`

### Score Lineage

Base this section on `fetchStrategyScoreAudit(displayTradeDate)`.

Rules:

- `overall_status = ok` -> `正常`
- `warning` with only `mapped_score_without_raw_score` on LHB -> `需关注`
- any stale-source issue on official strategies -> `需关注`
- future mismatch anomalies like published/display/raw inconsistency -> escalate to `阻塞` only if they materially invalidate the displayed score trust

The summary text should roll up by anomaly type and impacted strategy, not by sample asset.

### Strategy Execution

Use home readiness/manifest data for the display date:

- all three official strategy modules success -> `正常，3/3 已完成`
- partial success -> `需关注`
- no valid rerun for display date -> `阻塞`

### Review Artifacts

Check display-date availability of:

- review queue manifest
- evidence digest snapshots
- daily review artifact if available in this branch

Summarize as:

- `正常`
- `需关注`
- `阻塞`

### Content Chain

Use a conservative materiality rule:

- show stale research report dates only if they are materially older than the display trade date and therefore meaningfully weaken the platform’s content freshness perception
- do not clutter the summary with every minor lag

This section is intended for trust, not exhaustive diagnostics.

## Implementation Outline

### Backend

Port or adapt the following from the main repository into the current `v0.1-local-eod-web` stack:

- Ops snapshot aggregation module
- routes:
  - `/api/ops/snapshot`
  - `/api/ops/stages`
  - `/api/public/snapshot`

`/public` support is retained, but only internal home page consumption of ops snapshot is required for this phase.

### Frontend

Modify the current home cockpit implementation to:

1. remove the current `策略打分审计处理建议` region
2. add a new `运行审计摘要` region
3. pull in ops snapshot data
4. combine:
   - ops status
   - readiness
   - strategy score audit
   into a compact trust summary

### Routing

Internal home page:

- continue to load via normal `/`

Public route:

- keep `/public`

Public-only build:

- keep `public.html` and `public-main.tsx` behavior

## Testing

Add or update tests for:

1. backend routes:
   - `/api/ops/snapshot`
   - `/api/ops/stages`
   - `/api/public/snapshot`

2. home cockpit rendering:
   - renders `运行审计摘要`
   - does not render old `策略打分审计处理建议`
   - summarizes score-line anomalies without listing stock sample rows
   - shows ops-backed status text
   - preserves top-line summary and health-check section

3. route/build behavior:
   - `/public` still renders public snapshot page
   - public-only build still emits `dist/public.html`

## Risks

1. The current branch and main repository have diverged, so porting Ops Snapshot may involve contract reconciliation.
2. Mixing too much operational detail into the home page could make it noisy; the summary must stay compact.
3. Some underlying readiness sources may disagree with strategy score audit sources; summary logic must prefer display-date trust over generic “all green” signals.

## Success Criteria

This phase is successful when:

1. The current `5174` home page shows a Chinese `运行审计摘要` instead of `策略打分审计处理建议`.
2. The summary tells the user what is missing, stale, or not rerun yet for the display trade date.
3. The home page no longer shows sample anomaly stocks as if they were actionable guidance.
4. Ops Snapshot APIs are available in the current branch and are consumed by the home page.
5. `Public Snapshot` remains available as `/public` and through public-only build mode.
