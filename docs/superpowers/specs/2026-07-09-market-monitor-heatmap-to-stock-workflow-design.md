# Market Monitor Heatmap To Stock Workflow Design

## Goal

Turn the existing Market Monitor stock heatmap into a clear read-only workflow:

`Market Monitor -> stock heatmap hot stocks -> Stock Workspace -> same-industry market context heatmap`.

## Scope

This is a UI/workflow refinement, not a new data project.

In scope:
- Reuse the existing `/api/market-monitor/stocks/heatmap` payload.
- Add a clearly named hot-stock list in `MarketMonitorWorkspace`.
- Preserve click-through to `StockWorkspace` with market context.
- Ensure the Stock Workspace receives `sourceWorkspace=market`, `monitorTab=stock_heatmap`, and `tradeDate`.
- Keep the Stock Workspace same-industry heatmap as the downstream peer context.

Out of scope:
- No new realtime feed.
- No trading signal.
- No strategy/admission/scoring work.
- No research publication or external delivery work.
- No Agent/RAG.

## UX

In the Market Monitor stock view, the user should see:
- Existing full-market stock heatmap canvas.
- A compact "热区个股 Top N" list, sorted by the stock heatmap payload order.
- Each item shows stock name, symbol, percentage change, group name, and amount.
- Clicking an item opens the Stock Workspace for that asset.

The Stock Workspace then shows its existing "同业市场定位" heatmap for the selected stock.

## Data Flow

`MarketMonitorWorkspace` calls `fetchStockHeatmap(activeTradeDate)` only when the stock heatmap tab is active.

`StockHeatmapPanel` renders the heatmap and hot-stock list from the existing payload only.

On click:

```ts
onOpenAsset(assetId, {
  sourceWorkspace: 'market',
  monitorTab: 'stock_heatmap',
  tradeDate: activeTradeDate,
  matchReason: 'stock_heatmap'
});
```

`AppShell` opens `StockWorkspace`, which uses the carried context and loads:
- stock profile
- evidence digest
- stock market context heatmap

## Testing

Tests should cover:
- Market Monitor stock tab shows "热区个股 Top N".
- Clicking a hot stock sends the expected market context.
- AppShell handoff from Market Monitor opens Stock Workspace with market context.
- Existing frontend test suite and build continue to pass.
