# Research Dashboard Product Redesign V2 Design

## 1. Goal

Redesign the local stock research dashboard into an operator-grade research
cockpit. The product should help a user move through the daily research loop:

1. Understand market state.
2. Read current news flow.
3. Search external research reports.
4. Investigate one stock.
5. Maintain a watchlist/research queue.
6. Inspect factors and strategy evidence.
7. Review generated local artifacts.

The dashboard remains a local research and review surface. It must not expose
broker, live order, or automatic trading controls.

## 2. Design References

The redesign should borrow product patterns, not copy visual skins.

- Bloomberg/FactSet-style workstation pattern: dense information hierarchy,
  persistent navigation, status strips, tables, and evidence links.
- Koyfin-style dashboard pattern: configurable widgets combining watchlists,
  charts, market data, and news.
- TradingView-style workflow: screener/watchlist first, then chart and detail
  inspection.
- Eastmoney-style research report center: research reports searchable by stock,
  institution, industry, date, and rating action.
- Sina Finance / Wallstreetcn-style news flow: time stream plus category tabs,
  with 7x24 updates separated from structured EOD market review.

Reference URLs used during design:

- https://www.koyfin.com/help/topic/functionality/
- https://www.tradingview.com/support/solutions/43000718885-tradingview-screeners-walkthrough/
- https://www.factset.com/why-factset
- https://data.eastmoney.com/report/
- https://finance.sina.com.cn/
- https://wallstreetcn.com/live

## 3. Product Boundary

The platform must separate three concepts that are currently easy to confuse:

- `News`: public news flow, time-first, near-real-time when source adapters
  allow it.
- `Research Reports`: external broker/institution reports, stock-first, with
  date, institution, rating, and keyword filters.
- `Generated Reports`: local artifacts produced by this project, date-first,
  including TopN, risk alerts, factor evaluation, backtest, and strategy
  validation reports.

The existing `Reports` page is not an external research report library. It is a
local generated artifact browser and should be renamed.

## 4. Information Architecture

Recommended primary navigation:

1. `Home`
2. `Market Monitor`
3. `News`
4. `Research Reports`
5. `Stock Workspace`
6. `Watchlist`
7. `Factor Lab`
8. `Strategy Lab`
9. `Data Explorer`
10. `Generated Reports`

Existing pages should map as follows:

- Existing `Backtest Lab` and `Strategy Validation` become `Strategy Lab` tabs.
- Existing `Reports` becomes `Generated Reports`.
- Existing `News` stays `News`.
- Existing data inspection panels move toward `Stock Workspace` and `Data
  Explorer` roles.

## 5. Home

Home is the daily command surface, not a list of modules.

It should answer:

- What is the latest complete data date?
- What market state should I assume today?
- Which stocks, news items, and watchlist rows need attention?
- Are strategy signals healthy enough to trust?
- Which generated reports are ready to review?

Required sections:

- Top status strip:
  - latest market date
  - latest factor date
  - latest news refresh time
  - latest generated report date
  - strategy validation freshness
  - warning count
- `Today Focus`:
  - top candidate stocks
  - watchlist alerts
  - high-priority risks
  - latest relevant generated reports
- `Market Pulse`:
  - EOD market state summary from Market Monitor
  - strongest/weakest sectors
  - unusual move count
- `News Flow`:
  - newest public news items
  - company/news category badges
  - link to full News workspace
- `Strategy Health`:
  - last backtest/validation status
  - sample count
  - recent risk or data warnings
- `Generated Reports`:
  - latest local artifacts by type

Home should be scan-first. It should use compact rows, numeric status chips,
small charts, and table summaries instead of large decorative cards.

## 6. Market Monitor

Market Monitor V1 is EOD only.

Page label:

`Market Monitor - Last Completed Trading Day`

It must not imply live market data. It should default to the latest complete
trading day available in local data. If today's EOD pipeline has not run, the
page should keep showing the previous complete trading day and display a small
freshness warning.

Required sections:

- `Market Breadth`:
  - up/down counts
  - limit up/down counts if available
  - advancing ratio
  - turnover or amount change
- `Index Snapshot`:
  - major index returns
  - volume/amount
  - volatility or range
- `Sector Strength`:
  - strongest sectors
  - weakest sectors
  - sector rotation notes if available
- `Unusual Moves`:
  - volume expansion
  - breakout/breakdown
  - extreme return/range
  - large factor score change
- `Watchlist Alerts`:
  - watched stocks with price, factor, news, or risk changes
- `Strategy Signal Summary`:
  - candidate counts
  - TopN changes
  - risk filter result counts

Refresh behavior:

- No high-frequency polling.
- Provide `Load Latest EOD`.
- Optional background reload every several minutes is acceptable only if it
  reads local cached EOD data and does not call external data sources.

## 7. News

News is the public news flow workspace.

Primary organization:

- time stream
- category tabs
- keyword search

Initial categories:

- all
- 7x24
- focus
- company
- market
- macro
- international
- opinion
- original
- other

Refresh behavior:

- The page may auto-refresh public news at a modest interval, for example 60
  seconds.
- Refresh failures must not clear existing news.
- Display last successful refresh time and warnings.
- News should remain separate from EOD Market Monitor.

Future behavior:

- entity extraction for stock names/codes
- link news items into Stock Workspace
- source adapters beyond Sina Finance

## 8. Research Reports

Research Reports is the external broker/institution report library.

Primary search is stock-first:

- stock code/name input
- latest reports for that stock
- institution
- analyst if available
- rating and rating action
- target price if available
- report date range
- keyword search

Secondary views:

- latest reports
- industry reports
- rating changes
- high-coverage stocks

This page should not reuse the generated local artifact model. It needs its own
adapter, store, and API because the data shape is different from local generated
reports.

## 9. Stock Workspace

Stock Workspace is the single-stock investigation page.

It should become the hub that links data, news, reports, factors, watchlist
state, and strategy evidence for one stock.

Required sections:

- stock search and identity header
- price chart and volume
- factor score and component breakdown
- latest public news related to the stock
- latest external research reports
- financial/fundamental summary where available
- watchlist status and notes
- strategy signal history
- generated evidence artifacts linked to this stock

The user should be able to start from News, Research Reports, Watchlist, Factor
Lab, or Strategy Lab and land on this page for deeper inspection.

## 10. Watchlist

Watchlist is a research queue, not just favorites.

Required fields:

- stock
- status: observe, candidate, holding, avoid, review
- priority
- reason
- latest signal
- latest news timestamp
- latest research report timestamp
- risk tags
- next action
- owner/manual notes if needed

Primary filters:

- status
- priority
- signal type
- risk tag
- updated date

## 11. Factor Lab

Factor Lab remains the factor research and scoring workspace.

It should focus on:

- factor library and coverage
- factor distribution
- factor IC or grouped return diagnostics where available
- custom recipe preview
- TopN candidate explanation
- selected stock factor breakdown

Visual style should be table-forward. Charts should be compact and diagnostic,
not decorative.

## 12. Strategy Lab

Strategy Lab should combine the current `Backtest Lab` and `Strategy
Validation` under one workspace with tabs.

Tabs:

- `Run Backtest`
- `Backtest Results`
- `Validation Replay`
- `Cohorts`
- `Risk`
- `Evidence`

This unifies:

- strategy selection
- parameterized runnable backtests
- existing validation runs
- asset replay charts
- cohort metrics
- portfolio risk
- artifact links

The page remains read-only except for local research computations such as
running a backtest.

## 13. Data Explorer

Data Explorer is the low-level data inspection and diagnostics page.

It should answer:

- What raw data do we have?
- Is it fresh?
- Is it missing?
- Which source produced it?
- Which derived tables depend on it?

Sections:

- asset master
- market bars
- factors
- scores
- news cache
- research report cache
- generated artifact index
- data quality warnings

Data Explorer should be useful for debugging and pipeline verification, not the
main daily research workflow.

## 14. Generated Reports

Generated Reports replaces the current `Reports` page.

Primary search is date-first:

- trade date
- report type
- strategy/factor group
- format
- keyword

Report types:

- daily_topn
- watchlist_report
- risk_alerts
- factor_eval
- backtest_report
- strategy_validation
- position_review
- generic_report

Each row should show:

- type
- title
- date
- format
- source path
- generated time if available
- primary action: open

## 15. Global Search

Add one persistent global search input in the top bar.

Search result groups:

- stocks
- news
- research reports
- generated reports
- strategy runs
- factors

Click behavior:

- stock -> Stock Workspace
- news -> News detail or Stock Workspace when entity-linked
- research report -> Research Reports detail
- generated report -> Generated Reports artifact
- strategy run -> Strategy Lab validation result
- factor -> Factor Lab

## 16. UI Style Direction

The current UI should move from loose card layout to a dense professional
research workstation.

Principles:

- compact, high-information density
- calm neutral base with restrained accent colors
- strong typographic hierarchy
- clear table alignment for numeric data
- persistent context: selected date, selected stock, data freshness
- narrow status chips for state, not large decorative cards
- charts embedded where they explain data
- page sections as full-width work areas, not nested cards
- no marketing hero layout
- no decorative gradients, blobs, or oversized empty panels

Recommended visual language:

- Background: off-white or very light cool gray.
- Surfaces: white panels with subtle borders.
- Text: near-black for primary, muted gray for secondary.
- Accents:
  - blue for navigation/selection
  - green/red for market movement
  - amber for warnings
  - violet only sparingly for strategy/model tags
- Density:
  - small top status bar
  - 12-14px table text
  - compact controls
  - 8px or smaller radius
  - fixed row heights where possible

Avoid:

- oversized dashboard cards as the default unit
- one-note dark blue/slate palette
- purple gradient theme
- decorative glassmorphism
- hero-style empty front page
- nested cards
- UI text that explains obvious controls

## 17. Layout Pattern

Use a consistent shell:

- left navigation rail
- top context/search bar
- page title row with date/source freshness
- main workspace with 2-3 resizable columns where appropriate
- right inspector only when selected row/detail context exists

Page density examples:

- Home: status strip + 3-column operator summary + lower tables.
- Market Monitor: EOD date selector + metric strip + sector and unusual move
  tables.
- News: category tabs + stream + source/freshness sidebar.
- Stock Workspace: stock header + chart + right evidence timeline.
- Strategy Lab: tabbed workspace + chart/table split.

## 18. Implementation Phases

### Phase 1: Navigation, UI Shell, and EOD Monitor Frame

- Rename `Reports` to `Generated Reports`.
- Add `Market Monitor` as EOD page.
- Add top context/search bar skeleton.
- Rework Home into daily cockpit layout.
- Apply new visual system to shell, nav, panels, tables, and status chips.
- Add modest News auto-refresh with last-updated display.

### Phase 2: Stock Workspace and Watchlist Queue

- Add stock search/detail hub.
- Link News and Factor rows to stock detail.
- Redesign Watchlist as status/priority research queue.
- Add selected-stock context shared across pages.

### Phase 3: Research Reports

- Add external research report adapter/store/API.
- Build stock-first Research Reports page.
- Add filters for institution, date, rating action, and keyword.
- Link reports to Stock Workspace.

### Phase 4: Global Search and Cross-Linking

- Implement global search groups.
- Add entity links from news/reports/artifacts.
- Add detail drawers where useful.

## 19. Testing and Verification

Each phase should include:

- API tests for new backend read models.
- Frontend client tests for new endpoints.
- Component tests for navigation, filtering, loading, and empty states.
- Build verification.
- Manual browser check on localhost.

For UI work, verify:

- desktop and mobile viewport layouts
- no text overlap
- tables remain readable
- stale/fresh data states are visible
- no existing workspace becomes unreachable

## 20. Open Decisions

These can be resolved during implementation planning:

- exact EOD source tables for market breadth and sector strength
- whether global search is client-side first or API-backed from day one
- which public research report source to implement first
- whether Stock Workspace should replace Data Explorer eventually or stay as a
  higher-level page
