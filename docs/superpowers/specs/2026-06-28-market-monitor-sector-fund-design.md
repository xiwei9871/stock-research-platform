# Market Monitor Sector Fund Design

**Goal**

Refocus the existing `市场监控 / Market Monitor` tab in the local dashboard served from `http://127.0.0.1:5174/` into a post-close sector and fund-flow workspace. The homepage `市场环境` section stays largely as-is; the tab becomes the richer place to answer, within 30 seconds, which sectors led, where money flowed, and whether price strength matched fund strength.

**Working Baseline**

- This design applies to the local dashboard worktree at `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web`.
- It does **not** target the main branch dashboard.
- Existing homepage `市场环境` in `HomeCockpit.tsx` remains available as the short summary layer.
- Existing `MarketMonitorWorkspace.tsx` is currently an EOD market-emotion page and will be repositioned instead of duplicated.

**Product Positioning**

The two surfaces should have different jobs:

- Homepage `市场环境`: quick market temperature snapshot.
- `市场监控` tab: post-close sector and capital review workspace.

This removes the current duplication where both pages mainly render the same EOD emotion payload at different lengths.

Although the tab name remains `市场监控 / Market Monitor` for navigation continuity, v1 is explicitly a post-close review workspace, not an intraday real-time monitor.

## Scope

**In scope for v1**

- Replace the `市场监控` tab main body with a sector/fund-flow oriented layout.
- Keep the page focused on post-close review and historical date switching.
- Add:
  - market overview cards,
  - sector heatmap,
  - sector fund-flow rankings,
  - sector detail panel,
  - a compact emotion summary side panel.
- Start with mock data, then wire to real APIs.
- Preserve current dashboard shell, navigation, spacing rhythm, and card language.

**Out of scope for v1**

- Intraday real-time monitoring.
- News event stream on the Market Monitor page.
- Stock anomaly leaderboard as a primary section.
- LLM explanations.
- Reworking the homepage `市场环境` section beyond minor polish if needed.

Do not duplicate the full EOD emotion analysis in the Market Monitor main body. Only reuse it as a compact side summary.

## Reuse And Mature References

The implementation should explicitly avoid reinventing core interaction patterns.

**Primary local reuse**

- Reuse the existing dashboard shell and workspace layout from `AppShell.tsx`.
- Reuse current card, status-chip, loading, error, and empty-state patterns from `HomeCockpit.tsx` and the current workspace files.
- Reuse the existing `/api/market-monitor/eod` payload as the compact emotion-summary source instead of rebuilding that logic.

**External borrowing direction**

Use mature patterns inspired by the supplied Market Monitor brief and established market-cockpit layouts:

- Finviz-style sector heatmap principles:
  - color encodes return direction and magnitude,
  - area encodes economic weight, but in this project use traded amount rather than market cap.
- Single-screen market cockpit structure similar to the supplied `easyup-platform` reference:
  - top market summary,
  - central visual market structure,
  - adjacent ranking/support panel.

**Guardrails**

- Borrow the interaction model and information hierarchy, not visual clutter.
- Do not turn this project into a news big-screen dashboard.
- Do not replace the existing shell or navigation model.
- Prefer existing project patterns over importing a new design language.

## Information Architecture

### 1. Top: Market Overview

Purpose: summarize the day before the user interprets sectors.

Fields:

- trade date,
- updated time,
- Shanghai Composite,
- Shenzhen Component,
- ChiNext,
- STAR 50,
- Beijing 50,
- total market amount,
- up count / down count,
- limit up / limit down count,
- data status.

`data_status` is the core state field for this page, not live trading-session state.

Allowed values:

- `completed`
- `partial`
- `missing`
- `stale`

The overview should feel short and scan-friendly. It should not become another long emotion analysis block.

### 2. Main Left: Sector Heatmap

Purpose: show which sector groups actually led or lagged.

Tabs:

- `行业`
- `概念`

Each tile shows:

- sector name,
- change percent,
- amount,
- up/down stock counts.

Encoding:

- color: return, red up and green down for A-share convention,
- area: traded amount,
- tooltip: fuller sector statistics,
- click: selects the sector and updates the detail panel and ranking highlight.

Heatmap-specific rules:

- Use sector traded amount as tile value.
- Apply a minimum tile size so small but highly volatile sectors remain visible.
- Do not compare industry and concept sectors in the same heatmap because concept sectors overlap heavily and should not be interpreted as market-share partitions.

### 3. Main Right: Sector Fund Ranking

Purpose: reveal where capital concentrated and whether it matched price action.

Controls:

- one shared `行业 / 概念` toggle placed above the heatmap and ranking area,
- `净流入 Top 10`,
- `净流出 Top 10`.

Each row shows:

- rank,
- sector name,
- change percent,
- main net inflow,
- net inflow ratio to amount,
- leading stock name when available, else `--`.

Clicking a row selects the same sector as the heatmap.

Fund-flow metrics are treated as third-party indicative signals, not official exchange settlement data. The UI should present them as directional reference indicators rather than audited capital movement.

### 4. Bottom: Sector Detail Panel

Purpose: make the selected sector actionable without forcing another page jump.

Empty state:

- `点击热力图或资金榜查看板块详情`

Selected state:

- sector name,
- sector type,
- change percent,
- amount,
- up/down counts,
- main net inflow,
- main net inflow ratio.

Reserve a skeleton region for future stock constituents/ranking, but do not make that a blocking v1 dependency.

### 5. Compact Side/Bottom Panel: Emotion Summary

Purpose: retain old market-emotion context without letting it dominate the page.

This panel should reuse the existing EOD emotion pipeline and show only a compact summary:

- 综合强度,
- 涨跌家数,
- 涨停/跌停,
- 炸板率,
- 最高连板 or a similarly high-signal field.

The full old emotion workspace should not remain the page’s primary content.

## Interaction Model

### Date model

This page is post-close first.

- Default to the latest completed display date.
- Allow explicit date selection using the existing date control pattern.
- All main panels switch together on date change.

### Selection model

- `selectedSector` becomes the shared state between heatmap, ranking, and detail panel.
- Clicking a heatmap tile updates ranking highlight and detail panel.
- Clicking a ranking row updates heatmap selection and detail panel.
- The compact emotion panel is read-only and does not own selection state.

### Loading and failure behavior

Every main module must have:

- loading state,
- error state,
- empty state,
- updated-at label when available.

Failures in heatmap or fund-flow data should not crash the entire page. The emotion-summary panel can still render if sector data fails, and vice versa.

## Frontend Design Approach

Use a mature charting library for treemap rather than manually computing layout.

The current dashboard does not yet include ECharts, but the Market Monitor brief explicitly calls for treemap behavior. The recommended path is to add a small, focused ECharts integration for the heatmap only, while keeping existing project styles and cards elsewhere.

This is the one place where adding a library is justified because:

- treemap layout is not worth custom-building,
- tooltip and selection behavior are mature,
- the required interaction model maps directly to established treemap patterns.

`SectorHeatmap` must use ECharts treemap. Do not implement custom treemap layout.

### Proposed component structure

- `MarketMonitorWorkspace`
  - page container and shared state
- `MarketOverviewCards`
  - top summary cards
- `SectorHeatmapPanel`
  - industry/concept switch
  - treemap
- `SectorFundRankingPanel`
  - inflow/outflow ranking
- `SectorDetailPanel`
  - selected sector detail
- `MarketEmotionMiniPanel`
  - compact reuse of old EOD emotion summary

### Proposed type additions

In frontend API types:

- `MarketOverview`
- `MarketOverviewIndex`
- `SectorHeatmapItem`
- `SectorFundFlowItem`
- `SectorDetail`
- `SectorType = "industry" | "concept"`

The existing `MarketMonitorPayload` should remain for the emotion-summary fallback and backward compatibility during transition.

## Backend Design Approach

### Keep old endpoint, add new endpoints

Do not overload `/api/market-monitor/eod` with sector/fund-flow concerns. Keep it for the compact emotion panel and add dedicated endpoints for the new page body.

Proposed endpoints:

- `GET /api/market-monitor/overview?trade_date=YYYY-MM-DD`
- `GET /api/market-monitor/sectors/heatmap?trade_date=YYYY-MM-DD&type=industry|concept`
- `GET /api/market-monitor/sectors/fund-flow?trade_date=YYYY-MM-DD&type=industry|concept&period=1d`
- `GET /api/market-monitor/sectors/{sector_id}?trade_date=YYYY-MM-DD`

## Data And API Contract

Market Monitor v1 is a post-close workspace. All APIs must be keyed by `trade_date`.

Every response should include, where applicable:

- `trade_date`
- `updated_at`
- `source`
- `data_status`
- `warnings`
- `items` or a detail payload

Allowed `data_status` values:

- `completed`
- `partial`
- `missing`
- `stale`

The frontend must not depend directly on raw AKShare field names. The backend service layer should normalize external data into stable project-level fields.

For v1, only `period=1d` is required. `3d` / `5d` may exist in future API types or UI placeholders but must not block delivery.

### Service split

Add simple dashboard-oriented services rather than burying all logic in one file:

- `market_overview_service`
- `sector_heatmap_service`
- `sector_fund_flow_service`
- `sector_detail_service`

### Data strategy

For v1, prioritize stable post-close data over intraday freshness.

- Use historical/day-level data for the selected trade date.
- Allow fallback to the most recent completed trade date if the requested date is unavailable.
- Add small response caching appropriate for post-close browsing.
- Treat fund-flow values as third-party directional signals, not official exchange-confirmed capital movement.

### Output stability

- Always return stable JSON shape.
- Use `null` or `--`-friendly nullable fields when upstream data is missing.
- Return warnings and source status without breaking the page.

## Implementation Phasing

### Step 1: Preserve navigation and existing shell

Keep the current tab name and dashboard shell structure.

### Step 2: Reposition `MarketMonitorWorkspace.tsx`

Refactor the existing workspace instead of creating a duplicate page.

### Step 3: Mock-first UI

Build the new page with mock data first:

- overview mock,
- industry heatmap mock,
- concept heatmap mock,
- fund-flow ranking mock,
- selected-sector detail mock.

The mock data should explicitly cover:

- strong up sectors,
- down sectors,
- flat sectors,
- high return but mediocre inflow,
- modest return but strong inflow,
- outflow leaders.

### Step 4: Reuse old endpoint only for the compact emotion panel

`/api/market-monitor/eod` remains only for the emotion mini panel and must not drive the main body layout.

### Step 5: Add normalized sector and fund-flow endpoints

Add the new post-close API contracts with normalized fields.

### Step 6: Real API integration

Wire the page to the new endpoints while preserving:

- page-level resilience,
- date switching,
- independent panel error handling.

### Step 7: Add empty, error, partial, and stale states

Every main panel must render gracefully under missing or stale data.

### Step 8: Emotion panel minimization

Shrink the current broad EOD emotion content into the compact summary module and remove the old stock-list-heavy layout from the tab’s primary flow.

## Testing Expectations

At minimum:

- the Market Monitor page renders with mock data,
- industry/concept switching updates the visual and rankings,
- clicking a heatmap item updates `selectedSector`,
- clicking a ranking row updates `selectedSector`,
- empty API responses show empty state,
- API errors show localized error states,
- the compact emotion panel still renders when sector APIs fail,
- date switching reloads the coordinated page state.

## Acceptance Criteria

- The homepage `市场环境` still renders normally.
- The `市场监控` tab no longer duplicates the full EOD emotion page.
- The Market Monitor page works with mock data without backend changes.
- Historical `trade_date` switching changes all major panels consistently.
- Industry / concept switching updates both heatmap and fund-flow ranking.
- Clicking a heatmap sector updates the sector detail panel.
- Clicking a fund-flow ranking row updates the same selected sector state.
- EOD emotion content appears only as a compact side panel.
- Missing sector data shows partial or empty states instead of crashing.
- Real API wiring uses normalized backend fields, not raw AKShare column names.
- No news stream, LLM explanation, or full stock anomaly leaderboard is added in v1.

## Open Constraints And Decisions

- Homepage `市场环境` remains mostly unchanged by user request.
- The Market Monitor tab becomes a post-close review surface, not a real-time trading monitor.
- Mature patterns should be reused wherever possible:
  - existing shell and component conventions locally,
  - established treemap and ranking interaction models externally.
- The new page should feel more useful, not merely longer.
