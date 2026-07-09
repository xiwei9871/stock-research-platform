# Stock Workspace Market Context Heatmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only same-industry market context heatmap inside Stock Workspace so an operator can see where the selected stock sits among peers on a trade date.

**Architecture:** Reuse the P0 stock heatmap concepts, but scope the payload to one selected asset and its industry peers. Add a backend read model/API, frontend client/types, a compact Canvas panel, and integrate it into the existing `个股市场环境` section without touching trading, research delivery, publication, Agent/RAG, or strategy code.

**Tech Stack:** Python FastAPI, existing Postgres helpers, React, TypeScript, Canvas 2D, pytest, Vitest.

---

## Constraints

- Do not introduce external realtime quote APIs.
- Do not create buy/sell recommendations or trading signals.
- Do not change research queue, external delivery, publication, v7, signal, admission, or strategy pipelines.
- Do not write database schema.
- Do not require dashboard write token; this is read-only.
- Keep API output white-listed.
- Do not commit automatically because the current working tree contains unrelated changes.

## File Map

- Create: `src/stock_research/dashboard/stock_market_context_heatmap.py`
  - Builds the selected-stock peer heatmap payload.
  - Normalizes asset IDs where possible.
  - Computes peer ranks and percentiles.
  - Provides a white-listed read model.

- Modify: `src/stock_research/dashboard/app.py`
  - Add `GET /api/stocks/{asset_id:path}/market-context/heatmap`.

- Test: `tests/test_dashboard_stock_market_context_heatmap.py`
  - Covers service, missing data, API path IDs, and whitelist behavior.

- Modify: `dashboard/src/api/types.ts`
  - Add Stock Workspace market context heatmap types.

- Modify: `dashboard/src/api/client.ts`
  - Add `fetchStockMarketContextHeatmap(assetId, tradeDate)`.

- Test: `dashboard/tests/client.test.ts`
  - Covers URL encoding and query params.

- Create: `dashboard/src/components/stock-workspace/StockMarketContextHeatmap.tsx`
  - Compact Canvas peer heatmap, selected-stock highlight, summary, accessible peer list.

- Test: `dashboard/tests/stock-market-context-heatmap.test.tsx`
  - Covers loading, empty, error, selected highlight, peer click.

- Modify: `dashboard/src/components/StockWorkspace.tsx`
  - Fetch market context heatmap for the current asset/trade date.
  - Render it in the existing `个股市场环境` article.
  - Clear stale payload when asset/trade date changes.

- Modify: `dashboard/src/styles.css`
  - Add compact panel styles.

- Test: `dashboard/tests/stock-workspace.test.tsx`
  - Covers fetch orchestration, stale clearing, click peer behavior, and existing market context text.

## Task 1: Backend Read Model Tests

**Files:**
- Create: `tests/test_dashboard_stock_market_context_heatmap.py`

- [ ] **Step 1: Add failing service tests**

Create tests with a fake row loader so they do not need a real database:

```python
from fastapi.testclient import TestClient

from stock_research.dashboard.app import create_app
from stock_research.dashboard.stock_market_context_heatmap import (
    build_stock_market_context_heatmap,
    stock_market_context_heatmap_read_model,
)


def test_build_stock_market_context_heatmap_ranks_selected_peer(monkeypatch):
    rows = [
        {
            "asset_id": "CN:SZ:000001",
            "symbol": "000001",
            "name": "平安银行",
            "trade_date": "2026-07-07",
            "close": 12.5,
            "pct_chg": 2.0,
            "amount": 3000000000,
            "industry_id": "bank",
            "industry_name": "银行",
            "industry_system": "csrc",
        },
        {
            "asset_id": "CN:SH:600000",
            "symbol": "600000",
            "name": "浦发银行",
            "trade_date": "2026-07-07",
            "close": 9.0,
            "pct_chg": -1.0,
            "amount": 1000000000,
            "industry_id": "bank",
            "industry_name": "银行",
            "industry_system": "csrc",
        },
    ]
    monkeypatch.setattr(
        "stock_research.dashboard.stock_market_context_heatmap.load_peer_heatmap_rows",
        lambda asset_id, trade_date, service=None: rows,
    )

    payload = build_stock_market_context_heatmap("000001.SZ", "2026-07-07")

    assert payload["data_status"] == "completed"
    assert payload["industry"]["industry_name"] == "银行"
    assert payload["summary"]["peer_count"] == 2
    assert payload["summary"]["selected_in_peer_set"] is True
    assert payload["selected"]["asset_id"] == "CN:SZ:000001"
    assert payload["selected"]["amount_rank"] == 1
    assert payload["selected"]["change_rank"] == 1
    assert payload["selected"]["amount_percentile"] == 1.0
    assert payload["selected"]["change_percentile"] == 1.0
    assert payload["peers"][0]["is_selected"] is True
    assert payload["peers"][0]["change_pct"] == 0.02
```

- [ ] **Step 2: Add missing-data test**

```python
def test_build_stock_market_context_heatmap_returns_missing_when_no_rows(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.stock_market_context_heatmap.load_peer_heatmap_rows",
        lambda asset_id, trade_date, service=None: [],
    )

    payload = build_stock_market_context_heatmap("000001.SZ", "2026-07-07")

    assert payload["data_status"] == "missing"
    assert payload["summary"]["peer_count"] == 0
    assert payload["selected"] is None
    assert payload["peers"] == []
    assert "peer heatmap rows are unavailable" in payload["warnings"]
```

- [ ] **Step 3: Add read-model whitelist test**

```python
def test_stock_market_context_heatmap_read_model_filters_internal_fields(monkeypatch):
    payload = {
        "asset_id": "000001.SZ",
        "canonical_asset_id": "CN:SZ:000001",
        "trade_date": "2026-07-07",
        "industry": {"industry_id": "bank", "industry_name": "银行", "industry_system": "csrc", "payload": {"raw": True}},
        "selected": {
            "asset_id": "CN:SZ:000001",
            "symbol": "000001",
            "name": "平安银行",
            "price": 12.5,
            "change_pct": 0.02,
            "amount": 3000000000,
            "amount_rank": 1,
            "change_rank": 1,
            "amount_percentile": 1.0,
            "change_percentile": 1.0,
            "raw_payload": {"secret": True},
        },
        "summary": {
            "peer_count": 1,
            "up_count": 1,
            "flat_count": 0,
            "down_count": 0,
            "total_amount": 3000000000,
            "selected_in_peer_set": True,
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
                "is_selected": True,
                "metadata": {"raw": True},
            }
        ],
        "data_status": "completed",
        "warnings": [],
        "metadata": {"raw": True},
    }

    model = stock_market_context_heatmap_read_model(payload)

    assert "metadata" not in model
    assert "payload" not in model["industry"]
    assert "raw_payload" not in model["selected"]
    assert "metadata" not in model["peers"][0]
```

- [ ] **Step 4: Add API route tests**

```python
def test_stock_market_context_heatmap_api_accepts_colon_asset_id(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.app.build_stock_market_context_heatmap",
        lambda asset_id, trade_date: {
            "asset_id": asset_id,
            "canonical_asset_id": "CN:SZ:000001",
            "trade_date": trade_date,
            "industry": {"industry_id": "bank", "industry_name": "银行", "industry_system": "csrc"},
            "selected": None,
            "summary": {"peer_count": 0, "up_count": 0, "flat_count": 0, "down_count": 0, "total_amount": 0, "selected_in_peer_set": False},
            "peers": [],
            "data_status": "missing",
            "warnings": ["peer heatmap rows are unavailable"],
        },
    )
    app = create_app()
    app.state.eod_response_cache.clear()
    client = TestClient(app)

    response = client.get("/api/stocks/CN:SZ:000001/market-context/heatmap?trade_date=2026-07-07")

    assert response.status_code == 200
    assert response.json()["asset_id"] == "CN:SZ:000001"
    assert response.json()["trade_date"] == "2026-07-07"
```

- [ ] **Step 5: Run tests to verify RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_stock_market_context_heatmap.py -q
```

Expected: fail because `stock_market_context_heatmap.py` and the route do not exist yet.

## Task 2: Backend Implementation

**Files:**
- Create: `src/stock_research/dashboard/stock_market_context_heatmap.py`
- Modify: `src/stock_research/dashboard/app.py`

- [ ] **Step 1: Create service module**

Implement these functions:

```python
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import fetch_all

DEFAULT_INDUSTRY_SYSTEM = "csrc"


def build_stock_market_context_heatmap(
    asset_id: str,
    trade_date: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    rows = load_peer_heatmap_rows(asset_id, trade_date, service=service)
    if not rows:
        return _missing_payload(asset_id, trade_date, ["peer heatmap rows are unavailable"])

    normalized_rows = [_normalize_row(row) for row in rows]
    selected = _find_selected(normalized_rows, asset_id)
    selected_id = selected["asset_id"] if selected else _canonical_input(asset_id)
    industry = _industry_from_rows(normalized_rows)
    peers = _rank_peers(normalized_rows, selected_id)
    selected_peer = next((peer for peer in peers if peer["is_selected"]), None)

    return {
        "asset_id": asset_id,
        "canonical_asset_id": selected_id,
        "trade_date": trade_date,
        "industry": industry,
        "selected": _selected_model(selected_peer),
        "summary": _summary(peers, selected_peer is not None),
        "peers": peers,
        "data_status": "completed" if selected_peer else "partial",
        "warnings": [] if selected_peer else ["selected stock is not present in peer daily bars"],
    }
```

Implement helpers:

```python
def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _change_pct(value: Any) -> float | None:
    numeric = _number(value)
    if numeric is None:
        return None
    return numeric / 100.0


def _canonical_input(asset_id: str) -> str:
    raw = asset_id.strip()
    if raw.startswith("CN:"):
        return raw
    if raw.endswith(".SZ"):
        return f"CN:SZ:{raw[:6]}"
    if raw.endswith(".SH"):
        return f"CN:SH:{raw[:6]}"
    return raw
```

Use rank helpers:

```python
def _percentile(rank: int | None, total: int) -> float | None:
    if rank is None or total <= 0:
        return None
    if total == 1:
        return 1.0
    return round((total - rank) / (total - 1), 4)
```

For selected rank, use descending amount/change ranks. Rank `1` means strongest.

- [ ] **Step 2: Implement SQL loader**

Use the same local DB helper style as `stock_heatmap_service.py`. The SQL should:

- Resolve the selected asset to industry membership.
- Return all peer daily rows in that industry for the trade date.
- Join asset names where possible.
- Use `adjust_type='qfq'`.

Keep fallback name behavior:

```python
name = row.get("name") or row.get("symbol") or row.get("asset_id")
```

- [ ] **Step 3: Implement read-model whitelist**

Return exactly:

```python
{
    "asset_id": ...,
    "canonical_asset_id": ...,
    "trade_date": ...,
    "industry": {"industry_id": ..., "industry_name": ..., "industry_system": ...},
    "selected": ...,
    "summary": ...,
    "peers": [...],
    "data_status": ...,
    "warnings": [...],
}
```

Peer fields are exactly:

```python
{
    "asset_id": ...,
    "symbol": ...,
    "name": ...,
    "price": ...,
    "change_pct": ...,
    "amount": ...,
    "value": ...,
    "is_selected": ...,
}
```

- [ ] **Step 4: Add FastAPI route**

In `src/stock_research/dashboard/app.py`, import:

```python
from stock_research.dashboard.stock_market_context_heatmap import (
    build_stock_market_context_heatmap,
    stock_market_context_heatmap_read_model,
)
```

Add route near existing stock/profile or market-monitor routes:

```python
@app.get("/api/stocks/{asset_id:path}/market-context/heatmap")
def stock_market_context_heatmap(asset_id: str, trade_date: str):
    return app.state.eod_response_cache.get_or_set(
        ("stock_market_context_heatmap", asset_id, trade_date),
        lambda: stock_market_context_heatmap_read_model(
            build_stock_market_context_heatmap(asset_id, trade_date)
        ),
    )
```

- [ ] **Step 5: Run backend tests to verify GREEN**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_stock_market_context_heatmap.py -q
```

Expected: all tests pass.

## Task 3: Frontend API Types and Client

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Add failing client test**

In `dashboard/tests/client.test.ts`, add `fetchStockMarketContextHeatmap` to imports and add:

```typescript
it('fetches stock market context heatmap with encoded asset id', async () => {
  const payload = {
    asset_id: 'CN:SZ:000001',
    canonical_asset_id: 'CN:SZ:000001',
    trade_date: '2026-07-07',
    industry: { industry_id: 'bank', industry_name: '银行', industry_system: 'csrc' },
    selected: null,
    summary: { peer_count: 0, up_count: 0, flat_count: 0, down_count: 0, total_amount: 0, selected_in_peer_set: false },
    peers: [],
    data_status: 'missing',
    warnings: []
  };
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(payload), { status: 200 }));

  const result = await fetchStockMarketContextHeatmap('CN:SZ:000001', '2026-07-07');

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/stocks/CN%3ASZ%3A000001/market-context/heatmap?trade_date=2026-07-07'
  );
  expect(result).toEqual(payload);
});
```

- [ ] **Step 2: Run client test to verify RED**

Run:

```bash
rtk pnpm --dir dashboard test -- tests/client.test.ts
```

Expected: fail because client function/types do not exist.

- [ ] **Step 3: Add TypeScript types**

In `dashboard/src/api/types.ts`, add:

```typescript
export type StockMarketContextIndustry = {
  industry_id: string;
  industry_name: string;
  industry_system: string;
};

export type StockMarketContextSelected = {
  asset_id: string;
  symbol: string;
  name: string;
  price: number | null;
  change_pct: number | null;
  amount: number | null;
  amount_rank: number | null;
  change_rank: number | null;
  amount_percentile: number | null;
  change_percentile: number | null;
};

export type StockMarketContextPeer = {
  asset_id: string;
  symbol: string;
  name: string;
  price: number | null;
  change_pct: number | null;
  amount: number | null;
  value: number | null;
  is_selected: boolean;
};

export type StockMarketContextHeatmapPayload = {
  asset_id: string;
  canonical_asset_id: string;
  trade_date: string;
  industry: StockMarketContextIndustry | null;
  selected: StockMarketContextSelected | null;
  summary: {
    peer_count: number;
    up_count: number;
    flat_count: number;
    down_count: number;
    total_amount: number | null;
    selected_in_peer_set: boolean;
  };
  peers: StockMarketContextPeer[];
  data_status: 'completed' | 'partial' | 'missing' | string;
  warnings: string[];
};
```

- [ ] **Step 4: Add client function**

In `dashboard/src/api/client.ts`, import `StockMarketContextHeatmapPayload` and add:

```typescript
export async function fetchStockMarketContextHeatmap(
  assetId: string,
  tradeDate: string
): Promise<StockMarketContextHeatmapPayload> {
  return getJson(
    `/api/stocks/${encodeURIComponent(assetId)}/market-context/heatmap?trade_date=${encodeURIComponent(tradeDate)}`
  );
}
```

- [ ] **Step 5: Run client test to verify GREEN**

Run:

```bash
rtk pnpm --dir dashboard test -- tests/client.test.ts
```

Expected: client tests pass.

## Task 4: Stock Workspace Heatmap Component

**Files:**
- Create: `dashboard/src/components/stock-workspace/StockMarketContextHeatmap.tsx`
- Create: `dashboard/tests/stock-market-context-heatmap.test.tsx`
- Modify: `dashboard/src/styles.css`

- [ ] **Step 1: Add failing component tests**

Create `dashboard/tests/stock-market-context-heatmap.test.tsx`:

```typescript
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StockMarketContextHeatmap } from '../src/components/stock-workspace/StockMarketContextHeatmap';
import type { StockMarketContextHeatmapPayload } from '../src/api/types';

class TestResizeObserver {
  observe = vi.fn();
  disconnect = vi.fn();
}

const canvasContext = {
  clearRect: vi.fn(),
  fillRect: vi.fn(),
  strokeRect: vi.fn(),
  fillText: vi.fn(),
  measureText: vi.fn((text: string) => ({ width: text.length * 8 })),
  save: vi.fn(),
  restore: vi.fn(),
  scale: vi.fn()
};

function makePayload(): StockMarketContextHeatmapPayload {
  return {
    asset_id: '000001.SZ',
    canonical_asset_id: 'CN:SZ:000001',
    trade_date: '2026-07-07',
    industry: { industry_id: 'bank', industry_name: '银行', industry_system: 'csrc' },
    selected: {
      asset_id: 'CN:SZ:000001',
      symbol: '000001',
      name: '平安银行',
      price: 12.5,
      change_pct: 0.02,
      amount: 3000000000,
      amount_rank: 1,
      change_rank: 1,
      amount_percentile: 1,
      change_percentile: 1
    },
    summary: {
      peer_count: 2,
      up_count: 1,
      flat_count: 0,
      down_count: 1,
      total_amount: 4000000000,
      selected_in_peer_set: true
    },
    peers: [
      {
        asset_id: 'CN:SZ:000001',
        symbol: '000001',
        name: '平安银行',
        price: 12.5,
        change_pct: 0.02,
        amount: 3000000000,
        value: 3000000000,
        is_selected: true
      },
      {
        asset_id: 'CN:SH:600000',
        symbol: '600000',
        name: '浦发银行',
        price: 9,
        change_pct: -0.01,
        amount: 1000000000,
        value: 1000000000,
        is_selected: false
      }
    ],
    data_status: 'completed',
    warnings: []
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  globalThis.ResizeObserver = TestResizeObserver as unknown as typeof ResizeObserver;
  Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
    configurable: true,
    value: vi.fn((contextId: string) => (contextId === '2d' ? canvasContext : null)) as unknown as HTMLCanvasElement['getContext']
  });
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 460 });
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 240 });
});

afterEach(() => cleanup());

describe('StockMarketContextHeatmap', () => {
  it('renders loading and empty states', () => {
    const { rerender } = render(<StockMarketContextHeatmap payload={null} loading error={null} onSelectStock={vi.fn()} />);
    expect(screen.getByText('同业热力加载中')).toBeInTheDocument();

    rerender(
      <StockMarketContextHeatmap
        payload={{ ...makePayload(), selected: null, peers: [], data_status: 'missing', summary: { peer_count: 0, up_count: 0, flat_count: 0, down_count: 0, total_amount: 0, selected_in_peer_set: false } }}
        loading={false}
        error={null}
        onSelectStock={vi.fn()}
      />
    );

    expect(screen.getByText('暂无同业市场定位数据')).toBeInTheDocument();
  });

  it('renders selected stock summary and canvas', () => {
    render(<StockMarketContextHeatmap payload={makePayload()} loading={false} error={null} onSelectStock={vi.fn()} />);

    expect(screen.getByRole('img', { name: '同业市场定位热力图' })).toBeInTheDocument();
    expect(screen.getByText('银行')).toBeInTheDocument();
    expect(screen.getByText('同业 2')).toBeInTheDocument();
    expect(screen.getByText('涨跌排名 #1')).toBeInTheDocument();
    expect(screen.getByText('成交额排名 #1')).toBeInTheDocument();
    expect(screen.getByText('平安银行')).toBeInTheDocument();
    expect(canvasContext.strokeRect).toHaveBeenCalled();
  });

  it('calls onSelectStock when a peer is selected', () => {
    const onSelectStock = vi.fn();
    render(<StockMarketContextHeatmap payload={makePayload()} loading={false} error={null} onSelectStock={onSelectStock} />);

    fireEvent.click(screen.getByRole('button', { name: /打开同业 浦发银行/ }));

    expect(onSelectStock).toHaveBeenCalledWith('CN:SH:600000');
  });

  it('renders local error state', () => {
    render(<StockMarketContextHeatmap payload={null} loading={false} error="GET failed" onSelectStock={vi.fn()} />);
    expect(screen.getByText('GET failed')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run component tests to verify RED**

Run:

```bash
rtk pnpm --dir dashboard test -- tests/stock-market-context-heatmap.test.tsx
```

Expected: fail because component does not exist.

- [ ] **Step 3: Implement component**

Create `StockMarketContextHeatmap.tsx` with:

- A compact binary treemap helper.
- Color scale matching existing red/up and green/down convention.
- Selected peer rendered with a thicker border.
- Summary strip and peer list.

Use this public prop type:

```typescript
type StockMarketContextHeatmapProps = {
  payload: StockMarketContextHeatmapPayload | null;
  loading: boolean;
  error: string | null;
  onSelectStock: (assetId: string) => void;
};
```

- [ ] **Step 4: Add styles**

In `dashboard/src/styles.css`, add classes:

```css
.stock-market-context-heatmap { display: grid; gap: 10px; min-width: 0; }
.stock-market-context-heatmap-summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(118px, 1fr)); gap: 8px; }
.stock-market-context-heatmap-canvas { width: 100%; height: 260px; border: 1px solid #d7dee8; border-radius: 8px; background: #f8fafc; }
.stock-market-context-peer-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; max-height: 130px; overflow-y: auto; }
.stock-market-context-state { display: grid; min-height: 160px; place-items: center; border: 1px dashed #cfd8e3; border-radius: 8px; background: #fbfcfe; color: #667085; padding: 14px; }
```

Adapt naming/spacing to local style if equivalent patterns already exist.

- [ ] **Step 5: Run component tests to verify GREEN**

Run:

```bash
rtk pnpm --dir dashboard test -- tests/stock-market-context-heatmap.test.tsx
```

Expected: tests pass.

## Task 5: Stock Workspace Integration

**Files:**
- Modify: `dashboard/src/components/StockWorkspace.tsx`
- Modify: `dashboard/tests/stock-workspace.test.tsx`

- [ ] **Step 1: Add failing integration test**

In `dashboard/tests/stock-workspace.test.tsx`, add `fetchStockMarketContextHeatmap` to API mocks and import expectations. Add test:

```typescript
it('loads same-industry market context heatmap for the selected stock', async () => {
  apiMocks.fetchStockMarketContextHeatmap.mockResolvedValue(makeStockMarketContextHeatmapPayload());
  const onOpenMarketMonitor = vi.fn();
  const onOpenAsset = vi.fn();

  render(<StockWorkspace initialAssetId="000001.SZ" onOpenMarketMonitor={onOpenMarketMonitor} />);

  await waitFor(() =>
    expect(apiMocks.fetchStockMarketContextHeatmap).toHaveBeenCalledWith('000001.SZ', '2026-06-18')
  );

  expect(await screen.findByRole('region', { name: '同业市场定位' })).toBeInTheDocument();
  expect(screen.getByText('涨跌排名 #1')).toBeInTheDocument();
  expect(screen.getByText('成交额排名 #1')).toBeInTheDocument();
});
```

Add click behavior test:

```typescript
it('opens a peer stock from the same-industry heatmap context', async () => {
  const onOpenAsset = vi.fn();
  apiMocks.fetchStockMarketContextHeatmap.mockResolvedValue(makeStockMarketContextHeatmapPayload());

  render(<StockWorkspace initialAssetId="000001.SZ" onOpenAsset={onOpenAsset} />);

  fireEvent.click(await screen.findByRole('button', { name: /打开同业 浦发银行/ }));

  expect(onOpenAsset).toHaveBeenCalledWith('CN:SH:600000', {
    sourceWorkspace: 'market',
    monitorTab: 'stock_peer_heatmap',
    tradeDate: '2026-06-18',
    matchReason: 'peer_heatmap'
  });
});
```

If `StockWorkspace` does not currently expose `onOpenAsset`, use its existing navigation callback pattern instead. Keep the context fields exactly as shown.

- [ ] **Step 2: Run integration test to verify RED**

Run:

```bash
rtk pnpm --dir dashboard test -- tests/stock-workspace.test.tsx -t "market context heatmap|same-industry"
```

Expected: fail because fetch/component integration does not exist.

- [ ] **Step 3: Integrate client call**

In `StockWorkspace.tsx`:

- Import `fetchStockMarketContextHeatmap`.
- Import `StockMarketContextHeatmap`.
- Add state:

```typescript
const [marketContextHeatmap, setMarketContextHeatmap] = useState<StockMarketContextHeatmapPayload | null>(null);
const [marketContextHeatmapLoading, setMarketContextHeatmapLoading] = useState(false);
const [marketContextHeatmapError, setMarketContextHeatmapError] = useState<string | null>(null);
```

- Add effect keyed on current asset and trade date:

```typescript
useEffect(() => {
  const targetAssetId = currentAssetId || assetId;
  if (!targetAssetId || !tradeDate) return undefined;
  let cancelled = false;
  setMarketContextHeatmap(null);
  setMarketContextHeatmapError(null);
  setMarketContextHeatmapLoading(true);

  void fetchStockMarketContextHeatmap(targetAssetId, tradeDate)
    .then((payload) => {
      if (!cancelled) setMarketContextHeatmap(payload);
    })
    .catch((error: unknown) => {
      if (!cancelled) setMarketContextHeatmapError(error instanceof Error ? error.message : String(error));
    })
    .finally(() => {
      if (!cancelled) setMarketContextHeatmapLoading(false);
    });

  return () => {
    cancelled = true;
  };
}, [assetId, currentAssetId, tradeDate]);
```

If `currentAssetId` is declared after hooks in the existing component, derive a stable `marketContextAssetId` from currently available state instead, such as `profile?.canonical_asset_id ?? assetId`.

- [ ] **Step 4: Render in `个股市场环境`**

Inside the current article with `aria-label="Market Monitor State"`, add:

```tsx
<div role="region" aria-label="同业市场定位">
  <StockMarketContextHeatmap
    payload={marketContextHeatmap}
    loading={marketContextHeatmapLoading}
    error={marketContextHeatmapError}
    onSelectStock={handleSelectPeerFromMarketContext}
  />
</div>
```

Keep existing market facts/risk flags below or above this panel. Do not remove current evidence digest facts.

- [ ] **Step 5: Add click handler**

```typescript
const handleSelectPeerFromMarketContext = (nextAssetId: string) => {
  onOpenAsset?.(nextAssetId, {
    sourceWorkspace: 'market',
    monitorTab: 'stock_peer_heatmap',
    tradeDate,
    matchReason: 'peer_heatmap'
  });
};
```

If `onOpenAsset` is not available in the component props, add it consistently with other workspaces and AppShell patterns, then update tests.

- [ ] **Step 6: Run integration tests to verify GREEN**

Run:

```bash
rtk pnpm --dir dashboard test -- tests/stock-workspace.test.tsx
```

Expected: StockWorkspace tests pass.

## Task 6: Verification

- [ ] **Step 1: Backend regression**

Run:

```bash
rtk .venv/bin/pytest \
  tests/test_dashboard_stock_market_context_heatmap.py \
  tests/test_dashboard_market_monitor_stock_heatmap.py \
  tests/test_dashboard_app.py \
  -q
```

Expected: all pass. Existing py_mini_racer deprecation warnings are non-blocking if unchanged.

- [ ] **Step 2: Frontend regression**

Run:

```bash
rtk pnpm --dir dashboard test
```

Expected: all Vitest tests pass.

- [ ] **Step 3: Build**

Run:

```bash
rtk pnpm --dir dashboard build
```

Expected: TypeScript and Vite build pass. Existing Vite chunk size warning is non-blocking if unchanged.

- [ ] **Step 4: Optional local runtime smoke**

If local API and dashboard are running, use an authenticated browser session or local test client to verify:

```bash
rtk curl -s "http://127.0.0.1:8765/api/stocks/000001.SZ/market-context/heatmap?trade_date=2026-07-07" | head
```

If API auth blocks direct curl, record that runtime smoke needs authenticated session and do not bypass auth.

## Self-Review Checklist

- The plan implements every requirement in `docs/superpowers/specs/2026-07-09-stock-workspace-market-context-heatmap-design.md`.
- It does not add external realtime data.
- It does not touch trading, publication, research delivery, Agent/RAG, or strategy code.
- It keeps the backend read model white-listed.
- It uses TDD for backend service/API, frontend client, component, and integration.
- It avoids commits because the working tree has unrelated changes.
