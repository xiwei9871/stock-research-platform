# Market Stock Heatmap P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only stock-level market heatmap to Market Monitor, inspired by `wenyuanw/a-share-heatmap`, while keeping the existing sector heatmap unchanged.

**Architecture:** Build a backend read model from existing Postgres market data and expose it through FastAPI under `/api/market-monitor/stocks/heatmap`. Add a React/Vite `StockHeatmapPanel` that renders a Canvas treemap grouped by industry, with loading/empty/error states and click-through to the existing stock workspace. Do not import the external Next.js app, do not fetch remote quote APIs, and do not touch strategy/trading/research delivery.

**Tech Stack:** Python FastAPI, existing Postgres helpers, React, TypeScript, Canvas 2D, Vitest, pytest.

---

## Scope

### P0 Includes

- Backend read model for stock-level heatmap.
- API: `GET /api/market-monitor/stocks/heatmap?trade_date=YYYY-MM-DD&market=all&period=1d&group=industry&size_by=amount`.
- Initial supported options:
  - `market=all`
  - `period=1d`
  - `group=industry`
  - `size_by=amount`
- White-listed API output only.
- Frontend tab inside `MarketMonitorWorkspace`: `板块热力 / 个股云图`.
- Canvas treemap grouped by industry.
- Hover inspector with stock name, asset id, change pct, amount, industry.
- Click stock to use the existing stock selection path.
- Loading, empty, error states.
- Tests for backend service/API and frontend rendering states.

### P0 Excludes

- External realtime quote fetch from Eastmoney/Sina.
- Next.js, Tailwind, or direct import of `wenyuanw/a-share-heatmap`.
- Zoom, drag, fullscreen, screenshot, sharing.
- Multi-period support beyond `1d`.
- Market filters beyond `all`.
- Size mode beyond `amount`.
- Trading signals, research queue, delivery, Agent/RAG.

## Files

- Create: `src/stock_research/dashboard/stock_heatmap_service.py`
  - Loads stock daily bars and industry membership.
  - Builds grouped stock heatmap payload.
  - Clamps `limit` internally if later added.
  - Returns only read-model fields.

- Modify: `src/stock_research/dashboard/app.py`
  - Add `/api/market-monitor/stocks/heatmap`.

- Modify: `dashboard/src/api/types.ts`
  - Add stock heatmap API types.

- Modify: `dashboard/src/api/client.ts`
  - Add `fetchStockHeatmap`.

- Create: `dashboard/src/components/market-monitor/StockHeatmapPanel.tsx`
  - Canvas treemap rendering.
  - Hover and click behavior.
  - Loading/empty/error states.

- Modify: `dashboard/src/components/MarketMonitorWorkspace.tsx`
  - Add view toggle.
  - Fetch stock heatmap when the stock tab is active.
  - Keep sector heatmap behavior unchanged.

- Modify: `dashboard/src/styles.css`
  - Add stock heatmap layout and inspector styling.

- Test: `tests/test_dashboard_market_monitor_stock_heatmap.py`
  - Service normalization.
  - Empty data.
  - Unsupported params return controlled API error.
  - API shape is white-listed.

- Test: `dashboard/tests/stock-heatmap-panel.test.tsx`
  - Canvas panel empty/error/loaded states.
  - Hover/click callback.

- Test: update `dashboard/tests/market-monitor-workspace.test.tsx`
  - Toggle between sector heatmap and stock heatmap.

## Task 1: Backend Read Model

- [ ] Write failing tests in `tests/test_dashboard_market_monitor_stock_heatmap.py`:
  - `test_build_stock_heatmap_payload_groups_stocks_by_industry`
  - `test_build_stock_heatmap_payload_returns_missing_when_no_rows`
  - `test_stock_heatmap_api_rejects_unsupported_options`
  - `test_stock_heatmap_api_returns_whitelisted_fields`

- [ ] Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_market_monitor_stock_heatmap.py -q
```

Expected: fail because module/API do not exist.

- [ ] Implement `src/stock_research/dashboard/stock_heatmap_service.py`:
  - Query `market_daily_bar` for `trade_date` and `adjust_type='qfq'`.
  - Join asset names from existing asset master source if available in current code; otherwise return `asset_id` as fallback display name.
  - Join `core.industry_membership` level 1 with `industry_system='csrc'`.
  - Compute:
    - stock `change_pct` from `pct_chg / 100` if pct_chg is percentage points.
    - stock `amount`.
    - group `value=sum(amount)`.
    - group weighted `change_pct` by amount.
    - summary up/flat/down counts.
  - Return:

```python
{
    "trade_date": trade_date,
    "market": "all",
    "period": "1d",
    "group": "industry",
    "size_by": "amount",
    "updated_at": "...",
    "source": "market_daily_bar,core.industry_membership",
    "data_status": "completed|missing",
    "warnings": [],
    "summary": {...},
    "groups": [...]
}
```

- [ ] Add route in `src/stock_research/dashboard/app.py`:

```python
@app.get("/api/market-monitor/stocks/heatmap")
def market_monitor_stock_heatmap(...):
    ...
```

- [ ] Run backend test until green:

```bash
rtk .venv/bin/pytest tests/test_dashboard_market_monitor_stock_heatmap.py -q
```

## Task 2: Frontend API Types and Client

- [ ] Add failing tests in `dashboard/tests/client.test.ts` for `fetchStockHeatmap`.

- [ ] Run:

```bash
rtk pnpm --dir dashboard test -- tests/client.test.ts
```

Expected: fail because client function/types do not exist.

- [ ] Add types in `dashboard/src/api/types.ts`:
  - `StockHeatmapStock`
  - `StockHeatmapGroup`
  - `StockHeatmapSummary`
  - `StockHeatmapPayload`

- [ ] Add `fetchStockHeatmap` in `dashboard/src/api/client.ts`.

- [ ] Run client tests until green.

## Task 3: Canvas Stock Heatmap Panel

- [ ] Add failing tests in `dashboard/tests/stock-heatmap-panel.test.tsx`:
  - empty state.
  - loaded state renders summary and canvas.
  - click calls `onSelectStock`.

- [ ] Run:

```bash
rtk pnpm --dir dashboard test -- tests/stock-heatmap-panel.test.tsx
```

Expected: fail because component does not exist.

- [ ] Implement `dashboard/src/components/market-monitor/StockHeatmapPanel.tsx`:
  - Binary treemap layout based on group and child `value`.
  - Canvas render with red/green color scale.
  - Top summary strip.
  - Fallback textual list for accessibility/tests.
  - Hover inspector.
  - Click maps pointer to stock rect and calls `onSelectStock(assetId)`.

- [ ] Add focused styles in `dashboard/src/styles.css`.

- [ ] Run component tests until green.

## Task 4: Market Monitor Workspace Integration

- [ ] Add failing test in `dashboard/tests/market-monitor-workspace.test.tsx`:
  - user can switch from `板块热力` to `个股云图`.
  - stock heatmap loading/error/empty states do not break existing sector heatmap.

- [ ] Run:

```bash
rtk pnpm --dir dashboard test -- tests/market-monitor-workspace.test.tsx
```

Expected: fail because toggle/panel do not exist.

- [ ] Modify `dashboard/src/components/MarketMonitorWorkspace.tsx`:
  - Add state `heatmapView: 'sector' | 'stock'`.
  - Fetch stock heatmap only when stock tab is active.
  - Pass click handler to existing stock selection path.
  - Keep existing sector heatmap fetch and UI unchanged.

- [ ] Run workspace test until green.

## Task 5: Verification

- [ ] Backend:

```bash
rtk .venv/bin/pytest \
  tests/test_dashboard_market_monitor_stock_heatmap.py \
  tests/test_dashboard_market_monitor_sector_services.py \
  tests/test_dashboard_app.py \
  -q
```

- [ ] Frontend:

```bash
rtk pnpm --dir dashboard test
rtk pnpm --dir dashboard build
```

- [ ] Runtime smoke if local dashboard is running:

```bash
rtk curl -s "http://127.0.0.1:5174/api/market-monitor/stocks/heatmap?trade_date=2026-07-07&market=all&period=1d&group=industry&size_by=amount" | head
```

## Self-Review

- This plan keeps the external project as design inspiration only.
- P0 is read-only and does not introduce external data dependencies.
- Existing sector heatmap remains intact.
- API fields are white-listed.
- Tests cover service, route, client, component, and workspace integration.
