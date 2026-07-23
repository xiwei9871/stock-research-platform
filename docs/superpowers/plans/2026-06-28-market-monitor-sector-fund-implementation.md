# Market Monitor Sector Fund Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the local dashboard `市场监控 / Market Monitor` tab into a post-close sector and fund-flow review workspace while keeping the homepage market summary intact.

**Architecture:** Keep the existing `MarketMonitorWorkspace` route and shell, but split its responsibilities into a new top-level overview layer, a sector heatmap and fund ranking main body, a selected-sector detail panel, and a compact emotion-summary side panel that continues to reuse `/api/market-monitor/eod`. Add normalized backend endpoints under `/api/market-monitor/*` for overview, heatmap, fund-flow, and sector detail so the frontend never consumes raw AKShare field names.

**Tech Stack:** React 19, TypeScript, Vite, Vitest, ECharts treemap, FastAPI, Python dashboard services, pytest.

---

### Task 1: Add frontend dependency and contract tests for the new Market Monitor API surface

**Files:**
- Modify: `dashboard/package.json`
- Modify: `dashboard/pnpm-lock.yaml`
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Test: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Add failing client tests for the new endpoints and types**

Add tests in `dashboard/tests/client.test.ts` that assert the client calls:

```ts
expect(fetchMock).toHaveBeenCalledWith('/api/market-monitor/overview?trade_date=2026-06-26');
expect(fetchMock).toHaveBeenCalledWith(
  '/api/market-monitor/sectors/heatmap?trade_date=2026-06-26&type=industry'
);
expect(fetchMock).toHaveBeenCalledWith(
  '/api/market-monitor/sectors/fund-flow?trade_date=2026-06-26&type=concept&period=1d'
);
expect(fetchMock).toHaveBeenCalledWith(
  '/api/market-monitor/sectors/BK0428?trade_date=2026-06-26'
);
```

- [ ] **Step 2: Run the client test file and confirm the new tests fail**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- client.test.ts
```

Expected: FAIL because the new fetch helpers and types do not exist yet.

- [ ] **Step 3: Add the dependency and minimal API contracts**

Update `dashboard/package.json` to add `echarts` as a runtime dependency:

```json
"dependencies": {
  "echarts": "^6.0.0",
  "lightweight-charts": "^5.0.0",
  "lucide-react": "^0.468.0",
  "react": "^19.0.0",
  "react-dom": "^19.0.0"
}
```

Add these frontend types in `dashboard/src/api/types.ts`:

```ts
export type MarketDataStatus = 'completed' | 'partial' | 'missing' | 'stale' | string;
export type SectorType = 'industry' | 'concept';

export type MarketOverviewIndex = {
  code: string;
  name: string;
  close: number | null;
  change_pct: number | null;
};

export type MarketOverview = {
  trade_date: string;
  updated_at: string | null;
  source: string;
  data_status: MarketDataStatus;
  warnings: string[];
  indices: MarketOverviewIndex[];
  total_amount: number | null;
  up_count: number | null;
  down_count: number | null;
  limit_up_count: number | null;
  limit_down_count: number | null;
};

export type SectorHeatmapItem = {
  sector_id: string;
  sector_name: string;
  sector_type: SectorType;
  change_pct: number | null;
  amount: number | null;
  up_count: number | null;
  down_count: number | null;
  main_net_inflow: number | null;
  stock_count: number | null;
};

export type SectorFundFlowItem = {
  rank: number;
  sector_id: string;
  sector_name: string;
  sector_type: SectorType;
  change_pct: number | null;
  amount: number | null;
  main_net_inflow: number | null;
  main_net_inflow_ratio: number | null;
  leading_stock_name: string | null;
};

export type SectorDetail = {
  trade_date: string;
  updated_at: string | null;
  source: string;
  data_status: MarketDataStatus;
  warnings: string[];
  sector_id: string;
  sector_name: string;
  sector_type: SectorType;
  change_pct: number | null;
  amount: number | null;
  up_count: number | null;
  down_count: number | null;
  main_net_inflow: number | null;
  main_net_inflow_ratio: number | null;
  leading_stocks: Array<{ asset_id: string; name: string; change_pct: number | null }> | [];
};
```

Add the new fetchers in `dashboard/src/api/client.ts`:

```ts
export async function fetchMarketOverview(tradeDate: string): Promise<MarketOverview> {
  return getJson(`/api/market-monitor/overview?trade_date=${encodeURIComponent(tradeDate)}`);
}

export async function fetchSectorHeatmap(
  tradeDate: string,
  sectorType: SectorType
): Promise<{ trade_date: string; updated_at: string | null; source: string; data_status: MarketDataStatus; warnings: string[]; items: SectorHeatmapItem[] }> {
  return getJson(
    `/api/market-monitor/sectors/heatmap?trade_date=${encodeURIComponent(tradeDate)}&type=${encodeURIComponent(sectorType)}`
  );
}

export async function fetchSectorFundFlow(
  tradeDate: string,
  sectorType: SectorType
): Promise<{ trade_date: string; updated_at: string | null; source: string; data_status: MarketDataStatus; warnings: string[]; inflow: SectorFundFlowItem[]; outflow: SectorFundFlowItem[] }> {
  return getJson(
    `/api/market-monitor/sectors/fund-flow?trade_date=${encodeURIComponent(tradeDate)}&type=${encodeURIComponent(sectorType)}&period=1d`
  );
}

export async function fetchSectorDetail(tradeDate: string, sectorId: string): Promise<SectorDetail> {
  return getJson(
    `/api/market-monitor/sectors/${encodeURIComponent(sectorId)}?trade_date=${encodeURIComponent(tradeDate)}`
  );
}
```

- [ ] **Step 4: Run the client tests again and confirm they pass**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- client.test.ts
```

Expected: PASS.

### Task 2: Add backend normalized schemas and service tests for post-close sector/fund data

**Files:**
- Create: `src/stock_research/dashboard/market_overview_service.py`
- Create: `src/stock_research/dashboard/sector_heatmap_service.py`
- Create: `src/stock_research/dashboard/sector_fund_flow_service.py`
- Create: `src/stock_research/dashboard/sector_detail_service.py`
- Modify: `src/stock_research/dashboard/schemas.py`
- Test: `tests/test_dashboard_market_monitor_sector_services.py`

- [ ] **Step 1: Write failing backend service tests for normalized payload shapes**

Create `tests/test_dashboard_market_monitor_sector_services.py` with tests that assert:

```python
def test_build_market_overview_payload_normalizes_status_and_indices():
    payload = build_market_overview_payload(...)
    assert payload["data_status"] == "completed"
    assert payload["trade_date"] == "2026-06-26"
    assert payload["indices"][0]["name"] == "上证指数"


def test_build_sector_heatmap_payload_normalizes_items():
    payload = build_sector_heatmap_payload(...)
    assert payload["items"][0]["sector_type"] == "industry"
    assert "warnings" in payload


def test_build_sector_fund_flow_payload_marks_source_as_third_party():
    payload = build_sector_fund_flow_payload(...)
    assert payload["source"]
    assert payload["data_status"] in {"completed", "partial", "missing", "stale"}


def test_build_sector_detail_payload_handles_missing_leading_stocks():
    payload = build_sector_detail_payload(...)
    assert payload["leading_stocks"] == []
```

- [ ] **Step 2: Run the new backend service tests and confirm they fail**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_market_monitor_sector_services.py -q
```

Expected: FAIL because the new service modules do not exist yet.

- [ ] **Step 3: Implement the minimal normalized service layer**

Add simple service modules that return stable payloads shaped like:

```python
{
    "trade_date": trade_date,
    "updated_at": updated_at,
    "source": "akshare" or "normalized_market_monitor",
    "data_status": "completed",
    "warnings": [],
    "items": [...]
}
```

Define lightweight typed payload helpers in `src/stock_research/dashboard/schemas.py` for:

```python
class MarketOverviewPayload(TypedDict): ...
class SectorHeatmapPayload(TypedDict): ...
class SectorFundFlowPayload(TypedDict): ...
class SectorDetailPayload(TypedDict): ...
```

The implementation should:

- normalize external fields into project names,
- never expose raw AKShare column names to the frontend,
- keep `data_status` within `completed | partial | missing | stale`,
- treat fund-flow as a third-party signal in the payload metadata or warnings.

- [ ] **Step 4: Run the backend service tests again and confirm they pass**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_market_monitor_sector_services.py -q
```

Expected: PASS.

### Task 3: Expose the new FastAPI routes without breaking the old EOD endpoint

**Files:**
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_app.py`

- [ ] **Step 1: Add failing route tests for the new Market Monitor endpoints**

Extend `tests/test_dashboard_app.py` with tests like:

```python
def test_market_monitor_overview_route_returns_payload(monkeypatch):
    monkeypatch.setattr(dashboard_app, "build_market_overview_payload", lambda trade_date: {"trade_date": trade_date, "data_status": "completed", "warnings": [], "indices": []})
    client = TestClient(dashboard_app.create_app())
    response = client.get("/api/market-monitor/overview?trade_date=2026-06-26")
    assert response.status_code == 200
    assert response.json()["trade_date"] == "2026-06-26"
```

Repeat for:

- `/api/market-monitor/sectors/heatmap`
- `/api/market-monitor/sectors/fund-flow`
- `/api/market-monitor/sectors/{sector_id}`

- [ ] **Step 2: Run the targeted route tests and confirm they fail**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_app.py -k "market_monitor_overview_route or market_monitor_sectors" -q
```

Expected: FAIL because the routes do not exist yet.

- [ ] **Step 3: Add the routes to `app.py`**

Add route handlers in `src/stock_research/dashboard/app.py`:

```python
@app.get("/api/market-monitor/overview")
def market_monitor_overview(trade_date: str):
    return app.state.eod_response_cache.get_or_set(
        ("market_monitor_overview", trade_date),
        lambda: build_market_overview_payload(trade_date),
    )


@app.get("/api/market-monitor/sectors/heatmap")
def market_monitor_sectors_heatmap(trade_date: str, type: str):
    ...


@app.get("/api/market-monitor/sectors/fund-flow")
def market_monitor_sectors_fund_flow(trade_date: str, type: str, period: str = "1d"):
    ...


@app.get("/api/market-monitor/sectors/{sector_id}")
def market_monitor_sector_detail(sector_id: str, trade_date: str):
    ...
```

Keep `/api/market-monitor/eod` unchanged for the compact emotion panel.

- [ ] **Step 4: Run the targeted route tests and confirm they pass**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_app.py -k "market_monitor_overview_route or market_monitor_sectors" -q
```

Expected: PASS.

### Task 4: Rebuild the Market Monitor frontend with mock-first sector and fund-flow components

**Files:**
- Create: `dashboard/src/components/market-monitor/MarketOverviewCards.tsx`
- Create: `dashboard/src/components/market-monitor/SectorHeatmapPanel.tsx`
- Create: `dashboard/src/components/market-monitor/SectorFundRankingPanel.tsx`
- Create: `dashboard/src/components/market-monitor/SectorDetailPanel.tsx`
- Create: `dashboard/src/components/market-monitor/MarketEmotionMiniPanel.tsx`
- Create: `dashboard/src/components/market-monitor/mockData.ts`
- Modify: `dashboard/src/components/MarketMonitorWorkspace.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/market-monitor-workspace.test.tsx`

- [ ] **Step 1: Add failing workspace tests for the new information architecture**

Update `dashboard/tests/market-monitor-workspace.test.tsx` to assert:

```tsx
expect(screen.getByRole('heading', { name: '市场总览' })).toBeVisible();
expect(screen.getByRole('heading', { name: '板块热力图' })).toBeVisible();
expect(screen.getByRole('heading', { name: '板块资金排行' })).toBeVisible();
expect(screen.getByText('点击热力图或资金榜查看板块详情')).toBeVisible();
expect(screen.getByRole('button', { name: '行业' })).toHaveAttribute('aria-pressed', 'true');
```

Add tests for:

- switching `行业 / 概念`,
- clicking a fund-flow row updates selected sector detail,
- empty main data still leaves the compact emotion panel visible.

- [ ] **Step 2: Run the Market Monitor workspace tests and confirm they fail**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- market-monitor-workspace.test.tsx
```

Expected: FAIL because the current workspace still renders the old EOD emotion page.

- [ ] **Step 3: Implement mock-first component split**

Create `dashboard/src/components/market-monitor/mockData.ts` with mock payloads for:

```ts
export const mockMarketOverview: MarketOverview = { ... };
export const mockIndustryHeatmap: SectorHeatmapItem[] = [ ... ];
export const mockConceptHeatmap: SectorHeatmapItem[] = [ ... ];
export const mockSectorFundFlow = {
  inflow: [ ... ],
  outflow: [ ... ],
};
```

Refactor `MarketMonitorWorkspace.tsx` so its top-level state becomes:

```ts
const [tradeDate, setTradeDate] = useState(...)
const [sectorType, setSectorType] = useState<SectorType>('industry')
const [selectedSectorId, setSelectedSectorId] = useState<string | null>(null)
```

Render this component tree:

```tsx
<MarketOverviewCards ... />
<div className="market-monitor-main-grid">
  <SectorHeatmapPanel ... />
  <SectorFundRankingPanel ... />
</div>
<div className="market-monitor-detail-grid">
  <SectorDetailPanel ... />
  <MarketEmotionMiniPanel ... />
</div>
```

Use ECharts treemap in `SectorHeatmapPanel.tsx`; do not implement a custom rectangle layout.

- [ ] **Step 4: Run the workspace tests again and confirm they pass with mock data**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- market-monitor-workspace.test.tsx
```

Expected: PASS.

### Task 5: Wire the new page to real APIs while keeping the emotion panel on the old EOD endpoint

**Files:**
- Modify: `dashboard/src/components/MarketMonitorWorkspace.tsx`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/tests/market-monitor-workspace.test.tsx`
- Modify: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Add failing tests for real API orchestration**

Extend `dashboard/tests/market-monitor-workspace.test.tsx` to verify:

```tsx
expect(api.fetchMarketOverview).toHaveBeenCalledWith('2026-06-26');
expect(api.fetchSectorHeatmap).toHaveBeenCalledWith('2026-06-26', 'industry');
expect(api.fetchSectorFundFlow).toHaveBeenCalledWith('2026-06-26', 'industry');
expect(api.fetchMarketMonitorEod).toHaveBeenCalled();
```

Add a test that switching sector type reloads both heatmap and fund flow.

- [ ] **Step 2: Run the targeted workspace tests and confirm they fail**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- market-monitor-workspace.test.tsx
```

Expected: FAIL because the component still uses only the mock layer or old EOD fetch.

- [ ] **Step 3: Replace mock-only orchestration with real fetch orchestration**

Update `MarketMonitorWorkspace.tsx` to:

- fetch overview, heatmap, and fund-flow in parallel for the selected date and sector type,
- keep a separate request path for the compact `fetchMarketMonitorEod` emotion panel,
- default `selectedSectorId` to the first heatmap or inflow row when data arrives,
- preserve empty/error/partial/stale states per panel.

The loading model should resemble:

```ts
const [overviewState, setOverviewState] = useState(...)
const [heatmapState, setHeatmapState] = useState(...)
const [fundFlowState, setFundFlowState] = useState(...)
const [emotionState, setEmotionState] = useState(...)
```

- [ ] **Step 4: Run the workspace and shell tests again and confirm they pass**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- market-monitor-workspace.test.tsx app-shell.test.tsx
```

Expected: PASS.

### Task 6: Add sector detail API wiring, stale/partial states, and final acceptance coverage

**Files:**
- Modify: `dashboard/src/components/market-monitor/SectorDetailPanel.tsx`
- Modify: `dashboard/src/components/MarketMonitorWorkspace.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/market-monitor-workspace.test.tsx`
- Test: `tests/test_dashboard_market_monitor_sector_services.py`
- Test: `tests/test_dashboard_app.py`

- [ ] **Step 1: Add failing tests for selected-sector detail loading and degraded data states**

Add tests asserting:

```tsx
expect(screen.getByText('部分缺失')).toBeVisible()
expect(screen.getByText('数据过期')).toBeVisible()
expect(screen.getByText('点击热力图或资金榜查看板块详情')).toBeVisible()
```

Add a backend route/service test that `data_status="partial"` and `warnings=["fund flow source stale"]` round-trip unchanged.

- [ ] **Step 2: Run the stale/partial tests and confirm they fail**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- market-monitor-workspace.test.tsx

cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_market_monitor_sector_services.py tests/test_dashboard_app.py -k "partial or stale" -q
```

Expected: FAIL until the panel and route handling are complete.

- [ ] **Step 3: Implement the minimal stale/partial detail behavior**

Update `SectorDetailPanel.tsx` and `MarketMonitorWorkspace.tsx` so:

- selecting a sector triggers `fetchSectorDetail(tradeDate, sectorId)`,
- `data_status` renders localized badges,
- warnings render in a non-fatal panel state,
- empty details still preserve the page layout.

- [ ] **Step 4: Run final acceptance verification**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- market-monitor-workspace.test.tsx app-shell.test.tsx client.test.ts

cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_market_monitor_sector_services.py tests/test_dashboard_app.py -q
```

Expected: PASS.

## Self-Review

**Spec coverage:** This plan covers the post-close naming clarification, normalized API contract, ECharts-only treemap requirement, compact reuse of the old EOD emotion endpoint, mock-first UI, real API wiring, empty/error/partial/stale states, and the acceptance criteria around date switching, sector-type switching, and selected-sector linkage.

**Placeholder scan:** No task uses `TBD`, `TODO`, or “implement later.” Each task names exact files, concrete tests, and concrete commands.

**Type consistency:** The plan uses one consistent set of frontend types (`MarketOverview`, `SectorHeatmapItem`, `SectorFundFlowItem`, `SectorDetail`, `SectorType`) and one consistent backend route family rooted at `/api/market-monitor/`.
