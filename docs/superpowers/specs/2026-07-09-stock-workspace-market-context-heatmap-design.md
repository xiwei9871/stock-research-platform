# Stock Workspace Market Context Heatmap Design

## Goal

Add a read-only "同业市场定位" heatmap inside the existing Stock Workspace market context section. The feature helps an operator answer one question: where does the current stock sit among its industry peers on the selected trade date?

## Scope

This is a Stock Workspace feature, not a Market Monitor replacement. Market Monitor keeps the full-market stock heatmap. Stock Workspace gets a smaller peer-context heatmap focused on the selected asset.

Included in P1:

- Backend read API for one asset and one trade date.
- Industry peer set from existing asset/industry data.
- Daily bar metrics from existing market data.
- Peer heatmap payload with current stock highlighted.
- Rank and percentile fields for the selected stock.
- Frontend panel inside the existing `个股市场环境` area.
- Hover inspector, accessible stock list, loading, empty, and error states.
- Click peer stock to reopen Stock Workspace with the selected peer.

Excluded:

- External realtime quote APIs.
- Buy/sell recommendations.
- Trading signals.
- Agent/RAG.
- Zoom, drag, fullscreen, screenshot, or sharing.
- Changes to research queue, external delivery, publication, v7, signal, admission, or strategy pipelines.

## Backend Design

Add a focused read model module:

- `src/stock_research/dashboard/stock_market_context_heatmap.py`

The module exposes:

- `build_stock_market_context_heatmap(asset_id: str, trade_date: str, service=...) -> dict`
- `stock_market_context_heatmap_read_model(payload: dict) -> dict`

The API route is:

```http
GET /api/stocks/{asset_id}/market-context/heatmap?trade_date=YYYY-MM-DD
```

The route is read-only and does not require a write token. It returns only white-listed fields.

The read model uses existing data sources:

- `market_daily_bar` for price, change percentage, amount, turnover if present.
- `asset_master` / `core.asset_master` for stock name and symbol.
- `core.industry_membership` for peer grouping, defaulting to `industry_system='csrc'`.

The selected asset may arrive as `000001.SZ`, `CN:SZ:000001`, or another existing canonical form. The service should normalize using existing local conventions where available and be tolerant of suffix/canonical variants.

If the selected asset has no industry membership or no peers for the date, the API returns `data_status="missing"` or `data_status="partial"` with warnings rather than failing.

## API Shape

```json
{
  "asset_id": "000001.SZ",
  "canonical_asset_id": "CN:SZ:000001",
  "trade_date": "2026-07-07",
  "industry": {
    "industry_id": "bank",
    "industry_name": "银行",
    "industry_system": "csrc"
  },
  "selected": {
    "asset_id": "CN:SZ:000001",
    "symbol": "000001",
    "name": "平安银行",
    "price": 12.5,
    "change_pct": 0.02,
    "amount": 3000000000,
    "amount_rank": 3,
    "change_rank": 8,
    "amount_percentile": 0.82,
    "change_percentile": 0.64
  },
  "summary": {
    "peer_count": 42,
    "up_count": 21,
    "flat_count": 2,
    "down_count": 19,
    "total_amount": 58000000000,
    "selected_in_peer_set": true
  },
  "peers": [
    {
      "asset_id": "CN:SZ:000001",
      "symbol": "000001",
      "name": "平安银行",
      "price": 12.5,
      "change_pct": 0.02,
      "amount": 3000000000,
      "value": 3000000000,
      "is_selected": true
    }
  ],
  "data_status": "completed",
  "warnings": []
}
```

`change_pct` is a decimal ratio in API output. If source `pct_chg` is stored as percentage points, the service divides by `100`.

## Frontend Design

Add a small Stock Workspace component:

- `dashboard/src/components/stock-workspace/StockMarketContextHeatmap.tsx`

The component accepts:

- `payload`
- `loading`
- `error`
- `onSelectStock(assetId)`

UI behavior:

- Render a compact Canvas treemap sized for the existing evidence grid.
- Size tiles by `amount`.
- Color tiles by `change_pct`.
- Highlight the selected stock with a clear border.
- Show summary chips: peer count, up/down count, selected change rank, selected amount rank.
- Show hover inspector for the current tile.
- Show an accessible peer list so tests and keyboard users can select stocks without Canvas interaction.
- Empty and error states stay local to the module.

Integration point:

- `dashboard/src/components/StockWorkspace.tsx`
- Replace or extend the current `个股市场环境` article content with the new heatmap plus existing evidence digest market facts.
- Do not move the feature to HomeCockpit or Market Monitor.

Click behavior:

- Clicking a peer calls the existing stock-opening path, using `sourceWorkspace: 'market'`, `monitorTab: 'stock_peer_heatmap'`, and the current `tradeDate`.

## Error Handling

Backend:

- Unsupported or unresolvable asset returns a controlled `missing` payload when possible.
- Actual service/database errors remain API errors.
- API output never includes raw DB rows or internal metadata.

Frontend:

- Loading: `同业热力加载中`
- Empty: `暂无同业市场定位数据`
- Error: show local error text and leave the rest of Stock Workspace usable.

## Testing

Backend tests:

- Build peer heatmap grouped by industry.
- Selected stock is highlighted and ranked.
- Missing industry membership returns partial/missing payload with warnings.
- API returns only white-listed fields.
- Colon-containing canonical IDs work.

Frontend tests:

- Panel renders loading, empty, error states.
- Panel renders selected stock highlight and summary metrics.
- Hover or accessible list exposes stock details.
- Click peer calls `onSelectStock`.
- StockWorkspace fetches market context heatmap for current asset/trade date.
- Switching stock clears stale market context data.

## Acceptance Criteria

- A stock page shows its same-industry heatmap in `个股市场环境`.
- The selected stock is visually distinguishable.
- Operators can see whether the stock is strong/weak versus peers by change and amount rank.
- Clicking a peer opens that peer in the existing Stock Workspace flow.
- No external data dependency is introduced.
- No trading, publication, research delivery, Agent, or RAG behavior changes.
