# Cross-Linking Deep Links Phase 9 Design

## Goal

Complete the dashboard's research loop by making News, Research Reports, Market Monitor, Stock Detail, Watchlist, and Global Search preserve row-level context when users move between workspaces.

Phase 8 made Stock Detail the stock evidence hub. Phase 9 makes the path into and out of that hub explicit, so users can answer:

- Which news item, research report, monitor list, or search result led me here?
- Can I return to that source without losing the selected record?
- Can I open the same stock from another evidence source and see the new context immediately?

## Scope

Phase 9 includes:

- Pass rich News context into Stock Detail: source workspace, asset id, news id, and title/query.
- Add Research Reports to Stock Detail entry points from report rows and report detail.
- Add Market Monitor to Stock Detail entry points from EOD stock lists.
- Preserve return context from Stock Detail back to News, Research Reports, and Market Monitor.
- Extend shared frontend handoff types only as needed for source row identity, trade date, and monitor tab.
- Add focused tests for cross-workspace navigation and stale-context prevention.

Phase 9 excludes:

- New realtime fetching, polling, or websocket behavior.
- A new backend relationship graph or cross-linking aggregation endpoint.
- New research/news analysis models.
- Full-text ranking changes beyond preserving existing Global Search targets.
- Broad dashboard redesign or unrelated style cleanup.
- Cleaning unrelated dirty worktree changes.

## Product Behavior

Users should be able to move through the dashboard in a reversible evidence trail:

- Global Search result -> target workspace.
- News row stock button -> Stock Detail with News context.
- Research report row/detail -> Stock Detail with Research context.
- Market Monitor EOD stock row -> Stock Detail with Market context.
- Stock Detail actions -> return to News, Research Reports, or Market Monitor with the original source record restored when possible.

Stock Detail should show entry context as visible text. If the user opened a stock from a news item, it should show the source as News and expose the `newsId` when available. If the user opened the stock from a monitor tab, it should show the monitor tab and trade date.

Plain navigation to Stock Workspace should clear previous source context. Opening the same stock from a new source should replace the old context.

## Recommended Approach

Use frontend handoff state as the Phase 9 implementation boundary.

This is the recommended approach because the dashboard already has:

- `AppShell` as the central workspace router.
- `StockEntryContext` as the stock-level handoff contract.
- Workspace-specific handoff state for News and Research Reports.
- Deep-link behavior in Research Reports and News.

Phase 9 should extend these existing patterns instead of introducing a backend cross-linking service before the product loop is proven.

## Alternatives Considered

### Backend Cross-Link Endpoint

A backend endpoint could return all source links for an asset across news, reports, monitor lists, search, and generated reports. This would become useful later for automatic source recommendations and evidence scoring.

It is not the right Phase 9 default because it would add schema and ranking decisions before the core navigation behavior is complete.

### Simple Asset-Only Links

Every workspace could open Stock Detail with only `assetId`.

This would be faster to implement, but it repeats the current weakness: users arrive at Stock Detail without knowing which source row created the decision path, and returning to the original row becomes unreliable.

## Architecture

`AppShell` remains the owner of cross-workspace navigation.

The main contracts are:

- `WorkspaceHandoff`: used when opening News, Research Reports, Market Monitor, and Generated Reports.
- `StockHandoff`: used when opening Stock Detail.
- `StockEntryContext`: passed into `StockWorkspace` and displayed in Stock Detail.

Phase 9 should keep these contracts explicit and small:

- `assetId`
- `sourceWorkspace`
- `query`
- `matchReason`
- `newsId`
- `eventKey`
- `reportId`
- `tradeDate`
- `monitorTab`
- `version`

The `version` field remains important. Opening the same workspace with new context should remount or refresh the target so stale selected rows do not remain visible.

## Data Flow

### News to Stock Detail

News stock buttons should call `onOpenAsset(assetId, context)` rather than passing only `assetId`.

The context should include:

- `sourceWorkspace: 'news'`
- `assetId`
- `newsId` when available
- `query` from the row title, user query, or stock code fallback

When Stock Detail opens News from that context, `AppShell` should set News handoff state with `initialQuery` and `initialNewsId`.

### Research Reports to Stock Detail

Research Reports should receive an `onOpenAsset` prop.

Report rows and the selected report detail should expose a stock-detail action when the report has an asset id. The context should include:

- `sourceWorkspace: 'researchReports'`
- `assetId`
- `reportId`
- `eventKey`
- `query` from report title, stock name, or stock code fallback

When Stock Detail opens Research Reports from that context, `AppShell` should set Research Reports handoff state with `initialQuery`, `initialEventKey`, and `initialReportId`.

### Market Monitor to Stock Detail

Market Monitor should receive:

- `onOpenAsset`
- optional `initialTradeDate`
- optional `initialMonitorTab`
- optional `initialAssetId`

EOD stock rows in auction, limit-up, broken-limit-up, and limit-down tabs should open Stock Detail with:

- `sourceWorkspace: 'market'`
- `assetId`
- `tradeDate`
- `monitorTab`
- `query` from stock name or stock code fallback

When Stock Detail opens Market Monitor from that context, `AppShell` should pass the saved trade date and tab back to Market Monitor. Market Monitor should load that EOD date and select the tab. Highlighting the selected stock is useful but not required for Phase 9 completion.

### Global Search

Global Search should keep its current behavior and continue using specific target workspaces. When a result opens Stock Detail, it should keep `sourceWorkspace: 'search'`, query, and match reason. When it opens News or Research Reports, those workspaces should still deep-link to the selected row when identifiers are available.

## Frontend Components

Expected edits are limited to:

- `dashboard/src/components/AppShell.tsx`
- `dashboard/src/components/NewsWorkspace.tsx`
- `dashboard/src/components/ResearchReportsWorkspace.tsx`
- `dashboard/src/components/MarketMonitorWorkspace.tsx`
- `dashboard/src/components/StockWorkspace.tsx`
- related frontend tests

`StockWorkspace` should not become the router. It should render and emit intent through callbacks:

- `onOpenNews(context)`
- `onOpenResearchReports(context)`
- `onOpenMarketMonitor(context)`

`AppShell` should translate those intents into workspace handoff state.

## Backend Design

No backend changes are required for the recommended v1 unless an existing response lacks an asset identifier needed by a row-level action.

If a missing field is discovered during implementation, the backend change should be small and contract-focused:

- add a canonical asset id to the affected response row, or
- normalize an existing stock code into the frontend's accepted asset id format.

Do not add a persistent cross-link table in Phase 9.

## Error Handling

Navigation should degrade safely:

- If a row lacks an asset id, hide or disable the Stock Detail action for that row.
- If a source row id is missing, still open Stock Detail with asset id and source workspace.
- If return deep-link data cannot find the original row after reload, keep the filtered workspace open and select the first available row.
- If Market Monitor cannot load the saved EOD date, show the existing workspace error and keep the date visible in the control.

Plain workspace navigation must reset stale stock source context.

## Accessibility

Cross-link actions should use real buttons, with clear labels such as:

- `Open Stock Detail for 000001.SZ`
- `Open Stock Detail from report`
- `Open Stock Detail from limit-up list`

Rows should not become mouse-only interactions. Keyboard users must be able to trigger the same navigation.

Selected source context in Stock Detail should be visible text, not only color or layout.

## Testing

Frontend tests should cover:

- News stock action opens Stock Detail with `sourceWorkspace: 'news'`, `newsId`, and query context.
- Research report row/detail opens Stock Detail with `sourceWorkspace: 'researchReports'`, `reportId`, and `eventKey`.
- Market Monitor stock row opens Stock Detail with `sourceWorkspace: 'market'`, trade date, and monitor tab.
- Stock Detail return action opens News with the saved `initialNewsId`.
- Stock Detail return action opens Research Reports with saved `initialEventKey` or `reportId`.
- Stock Detail return action opens Market Monitor with saved trade date and tab.
- Plain Stock Workspace navigation clears old source context.
- Opening the same stock from a different source replaces the displayed context.

Verification should include:

- `cd dashboard && npm test -- --run tests/app-shell.test.tsx tests/news-workspace.test.tsx tests/stock-workspace.test.tsx`
- Market Monitor and Research Reports focused tests if new test files or existing test coverage are extended.
- `cd dashboard && npm run build`
- `cd dashboard && npm run test:e2e`

## Success Criteria

Phase 9 is complete when:

- News, Research Reports, and Market Monitor can open Stock Detail with row-level context.
- Stock Detail can return to News, Research Reports, and Market Monitor while preserving the source identifiers available in the original handoff.
- Market Monitor remains EOD-only and does not introduce realtime refresh behavior.
- Stale context does not leak into plain Stock Workspace navigation or same-stock new-source navigation.
- Tests cover the main cross-workspace loops.
- Changes are committed separately from unrelated dirty worktree files.
