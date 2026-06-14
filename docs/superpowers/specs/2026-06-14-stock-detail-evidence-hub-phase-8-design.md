# Stock Detail Evidence Hub Phase 8 Design

## Goal

Turn the existing Stock Workspace into a unified Stock Detail evidence hub. The page should answer why a stock is worth looking at by connecting price, score, EOD monitor state, news, research reports, strategy signals, review history, and the workspace that sent the user there.

## Scope

Phase 8 includes:

- Redesign the current `StockWorkspace` layout into an evidence-hub first screen.
- Preserve existing data sources: asset profile, bars, score, signals, decisions, outcomes, related news, research reports, and asset search matches.
- Add stock handoff context from Global Search, News, Research Reports, Market Monitor, Watchlist, and future strategy views.
- Show the entry context in Stock Detail so users know whether they arrived from a news item, research report, monitor list, or search result.
- Add deep-link affordances back to News, Research Reports, Market Monitor, and Generated/Strategy evidence where existing targets are available.
- Keep the implementation EOD-oriented and local-dashboard friendly. Do not introduce realtime polling or websocket behavior.

Phase 8 excludes:

- A new stock scoring model.
- A new research narrative generator.
- A new complex backend aggregation service unless the current endpoint boundaries prove insufficient during planning.
- Intraday or realtime market monitor state.
- Large Backtest Lab or Strategy Validation refactors.
- Cleaning unrelated dirty worktree changes, except for explicitly separating them from Phase 8 staging.

## Product Behavior

Stock Detail becomes the stock-level center of the dashboard.

Users may enter it from:

- Global Search stock result.
- News stock link.
- Research report stock link.
- Market Monitor stock list.
- Watchlist row.
- Future Strategy Validation evidence links.

The page should preserve the selected asset and expose the context that opened it. For example, when a user opens a stock from News, the Stock Detail page should show that it came from News and surface related news near the top. When a user opens a stock from Market Monitor, the page should surface the EOD monitor status for the selected trade date.

## Layout

Use the approved Evidence Hub layout.

Top identity band:

- Stock name, canonical asset id, symbol, exchange/board when available.
- Trade date and date range.
- Score, rank, latest close.
- Entry context label: Search, News, Research Report, Market Monitor, Watchlist, or manual load.

Primary evidence area:

- Price chart with room for future event markers.
- EOD monitor state card: whether the stock appears in limit-up, broken limit-up, limit-down, or auction-pending lists for the selected date when data is available.
- Strategy signal card: TopN rank, watchlist primary signal, priority, signal tags, and risk tags.
- Research coverage card: 30d/90d report counts, broker coverage, latest rating, latest target price.

Evidence grid:

- Related News: latest stock-linked news, source, publish date, and link back to News workspace when possible.
- Research Reports: latest stock research reports, broker, rating, target price, and link back to Research Reports workspace when possible.
- Factor / Score Breakdown: current factor values and score components in a compact table.
- Review / Outcomes: review decisions, evidence path, follow-up note, and outcomes.

Right context rail:

- Actions: open News, open Research Reports, open Market Monitor, copy asset id.
- Entry Context: selected source object such as `newsId`, `eventKey`, `reportId`, or monitor list tab.
- Evidence Timeline: compact chronological list of recent news, research reports, strategy/review events, and monitor events.
- Search Matches: existing asset search matches moved from the main grid into the context rail.

## Data Flow

The current frontend already calls:

- `fetchAssetProfile(assetId, tradeDate, startDate, endDate, scoreVersion, adjustType)`
- `fetchAssetNews(assetId, { limit, lookbackDays })`
- `fetchAssetResearchReports(assetId, { limit, lookbackDays })`
- `searchAssets(q, limit)`

Phase 8 should keep these calls for v1 and avoid inventing a large new endpoint unless needed.

The handoff object from `AppShell` should be extended for stock:

- `assetId`
- `query`
- `sourceWorkspace`
- `tradeDate`
- `newsId`
- `eventKey`
- `reportId`
- `monitorTab`
- `version`

`StockWorkspace` should accept this handoff as props and remount or refresh when the same stock is opened again from a different context.

## Backend Design

Phase 8 v1 should prefer existing backend endpoints.

Backend work is only needed if the frontend cannot answer a required page section from existing endpoints. Likely additions are small and targeted:

- Add optional asset id to Market Monitor stock-list rows if not already present in response.
- Add enough fields to asset news/research responses to link back to source workspace and selected row.
- Normalize asset id handling consistently between `CN:SH:600519`, `600519.SH`, and six-digit user input.

No new persistent store is required for v1.

## Frontend Design

`dashboard/src/components/StockWorkspace.tsx` remains the main implementation boundary, but should be decomposed if it becomes hard to reason about.

Candidate components:

- `StockIdentityBand`
- `StockEvidenceSummary`
- `StockEntryContextPanel`
- `StockEvidenceTimeline`
- `StockRelatedNewsPanel`
- `StockResearchReportsPanel`
- `StockFactorBreakdownPanel`
- `StockReviewOutcomesPanel`

Keep the first implementation conservative. Split components only when the edit becomes unwieldy or repeated UI logic appears.

`AppShell` should preserve stock handoff context similarly to existing News, Research Reports, and Generated Reports handoffs.

## Error Handling

Failures should be local to each section where possible:

- Asset profile failure blocks the main page and shows the profile error.
- News failure shows a Related News error but keeps the profile visible.
- Research report failure shows a Research Reports error but keeps the profile visible.
- Asset search failure shows a context-rail search error but keeps the profile visible.

Stale request handling should preserve the existing request-id pattern so older responses do not overwrite newer stock selections.

## Accessibility

The page should use:

- One clear page heading containing stock name and canonical asset id.
- Section headings for Price, Monitor State, Strategy Signal, News, Research, Factor Breakdown, and Review/Outcomes.
- Buttons for workspace navigation actions.
- Links for external news/report URLs.
- Stable dimensions for context cards, action buttons, and compact evidence rows to avoid layout shifts.

Entry context should be visible text, not only visual styling.

## Testing

Frontend tests should cover:

- Global Search opens Stock Detail with asset id and source context.
- News `onOpenAsset` opens Stock Detail with News context.
- Watchlist opens Stock Detail with Watchlist context.
- Stock Detail renders identity band, EOD/strategy/research summary cards, news, research reports, factor rows, review/outcomes, and search matches.
- Same stock opened from a new context refreshes/remounts and updates the entry context.
- News and research section failures do not remove the profile view.
- Stale profile/news/research/search responses do not overwrite newer selections.

Backend tests are needed only for targeted endpoint contract additions.

Verification should include:

- `cd dashboard && npm test -- --run tests/stock-workspace.test.tsx tests/app-shell.test.tsx`
- `cd dashboard && npm run build`
- Relevant backend pytest if endpoint contracts are changed.
- `cd dashboard && npm run test:e2e`

## Success Criteria

Phase 8 is complete when:

- Stock Detail acts as a stock-level evidence hub rather than a long unstructured page.
- Entry context from Search, News, Research, Market Monitor, and Watchlist is represented in the Stock page contract, even if some sources initially carry only asset id and source label.
- Existing StockWorkspace data still loads.
- News and research failures degrade locally.
- The implementation is committed separately from unrelated dirty worktree changes.
- Focused frontend tests, build, and e2e verification pass.
