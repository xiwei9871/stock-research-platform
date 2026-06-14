# EOD Market Monitor Phase 7 Design

## Goal

Build the first usable EOD Market Monitor workspace for the dashboard. The page should summarize the latest completed trading day, let users inspect historical EOD dates, and connect market emotion, limit-up behavior, strategy signal previews, and generated reports without requiring realtime data.

## Scope

Phase 7 includes:

- Worktree triage for current uncommitted changes, separating Market Monitor work from Backtest, Strategy Validation, and strategy experiment work.
- Backend EOD monitor payloads for market emotion, breadth, liquidity, limit-up behavior, profit effect, drawdown pressure, selected stock lists, strategy TopN preview, generated reports, freshness, and warnings.
- Frontend Market Monitor UI for a readable EOD cockpit with date selection, market emotion summary, component cards, stock-list tabs, strategy signal preview, and generated report links.
- Tests for backend payload mapping, historical-date behavior, JSON-safe numeric conversion, missing-source fallbacks, frontend rendering, date loading, and tab accessibility.

Phase 7 excludes:

- Realtime streaming, websockets, minute-level abnormal-move detection, and automatic polling.
- Intraday auction data unless a stable existing source is already available. The UI may reserve an auction tab and mark it as `pending_source`.
- Large Backtest Lab, Strategy Validation, and new strategy-file changes. Those remain separate worktree groups.
- New industry rotation models or discretionary narrative analysis.

## Product Behavior

The workspace is an EOD dashboard, not a realtime trading screen.

At the top, the user sees the current monitor mode, selected trade date, and whether the page is realtime. The default mode loads the latest completed trading day. If the user chooses a date, the workspace switches to historical EOD mode and fetches data for that specific trade date.

The primary monitor area shows:

- Comprehensive market emotion score and state.
- Risk state, style hint, and position-budget hint when available.
- Breadth: traded count, up count, down count, strong-up count, and strong-down count.
- Liquidity: total amount and 5-day versus 20-day amount ratio.
- Limit performance: limit-up count, limit-down count, broken limit-up count, broken limit-up rate, first-board count, second-board count, third-board-plus count, and high-board height.
- Profit effect: yesterday limit-up success/profit, relay success/profit, and broken-board repair/profit.
- Drawdown pressure: strong-down count, limit-down count, broken-board pressure, and yesterday limit-up-to-limit-down pressure.
- Weight performance as a reserved `pending_source` section.

The stock-list area provides tabs for:

- Auction: reserved and marked pending until a stable source exists.
- Limit up.
- Broken limit up.
- Limit down.

Each populated stock row shows asset name, symbol, amount, percentage change, board, and stable asset id in the API payload.

The lower area keeps the existing strategy and report affordances:

- TopN strategy signal preview for the selected trade date.
- Generated report links for the selected trade date.

## Backend Design

`src/stock_research/dashboard/market_monitor.py` remains the EOD payload assembly boundary.

Responsibilities:

- Load platform freshness and latest TopN summary through existing dashboard helpers.
- If no trade date is supplied, use the latest completed market date from platform summary.
- If a trade date is supplied, label the response as historical EOD and load TopN rows for that date instead of reusing the latest preview.
- Load persisted `research.market_emotion_state_daily` when available.
- If the emotion table or schema is missing, compute the selected day from existing market emotion source frames.
- Convert `Decimal`, `NaN`, and nullable values into JSON-safe numbers or nulls.
- Build a stable `market_emotion` object with explicit status fields.
- Derive the legacy `market_breadth` payload from `market_emotion` for existing consumers.
- Load stock lists from daily bar and asset status tables for limit-up, broken limit-up, and limit-down tabs.
- Return empty lists and `pending_source` statuses rather than raising when optional sources are absent.

The backend payload should stay backward compatible with existing monitor consumers while adding these fields:

- `market_emotion`
- `emotion_stock_lists`

## Frontend Design

`dashboard/src/components/MarketMonitorWorkspace.tsx` remains the primary UI component.

Responsibilities:

- Fetch `/api/market-monitor/eod` on mount with `topN=5`.
- Support explicit `tradeDate` loading through the existing API client.
- Keep stale visible data if a later fetch fails, while showing the error.
- Render freshness, warnings, market emotion summary, profit-effect cards, emotion components, stock-list tabs, TopN preview, and generated reports.
- Keep tab navigation accessible with `role="tablist"`, `role="tab"`, `role="tabpanel"`, `aria-selected`, arrow-key movement, Home, and End.
- Use compact, information-dense UI styling consistent with the redesigned dashboard rather than marketing-style cards.

`dashboard/src/api/types.ts` should define the new monitor response fields explicitly so later news analysis and stock-detail linking can depend on typed contracts.

## Worktree Triage

The current dirty worktree should be separated into:

- Phase 7 Market Monitor: market monitor backend, frontend, API types/client, related CSS, and related tests.
- Backtest and Strategy Validation: backtest UI, result-detail UI, vectorized TopN, strategy catalog, and related tests.
- Strategy experiments: `lhb_shortline_v1`, `mid_trend_v1`, `tech_bottleneck_v1`, and their tests.
- Planning documents: older plan drafts should remain untracked unless they are directly needed for this phase.

Only Phase 7 files should be staged and committed during this phase.

## Error Handling

Missing market date produces a warning and a payload with empty or pending sections.

Missing persisted emotion tables fall back to computation from source frames. Undefined columns or generic database errors should still surface because they indicate schema drift or a real failure.

Optional stock-list sources should degrade to empty lists where practical. The UI should render empty states instead of failing.

Historical-date mode should avoid freshness mismatch warnings that only apply to latest-EOD mode.

## Testing

Backend tests should cover:

- Latest completed trading day response.
- Explicit historical trade-date response.
- Emotion row mapping.
- Decimal and `NaN` JSON-safe conversion.
- Legacy breadth derivation.
- Missing emotion schema/table fallback.
- Generic database errors still raising.
- Stock-list mapping and list limits.
- Empty stock lists without trade date.

Frontend tests should cover:

- Initial EOD render with market emotion summary.
- Date input loading historical mode.
- Warning and error rendering.
- Stock tab switching by click and keyboard.
- Pending auction state.
- TopN preview and generated reports still rendering.

Integration verification should include:

- `pytest tests/test_dashboard_market_monitor.py -q`
- `pytest tests/test_dashboard_app.py -q`
- Focused Vitest files touching Market Monitor, App Shell, client types, and Home Cockpit.
- `npm run build`
- `npm run test:e2e`

## Success Criteria

Phase 7 is complete when:

- Market Monitor can be opened locally and shows a useful EOD dashboard without realtime dependencies.
- Latest-EOD and historical-EOD modes both work.
- Existing generated reports and strategy previews remain visible.
- Missing optional sources degrade cleanly.
- Phase 7 changes are committed separately from unrelated dirty worktree changes.
- Backend, frontend, build, and e2e verification pass.
