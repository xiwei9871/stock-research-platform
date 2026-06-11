# Research Dashboard Redesign Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the dashboard shell into the V2 research cockpit foundation: new navigation, EOD Market Monitor, Generated Reports naming, News auto-refresh, redesigned Home, and a denser professional UI style.

**Architecture:** Keep the current FastAPI + React/Vite dashboard. Add one backend read model for EOD market monitor, add frontend types/client methods, then introduce focused workspace components and a shared shell/top bar. Keep Research Reports and Stock Workspace as navigable placeholder workspaces in Phase 1 so the information architecture is visible without pretending the data adapters exist.

**Tech Stack:** FastAPI, Python read models under `src/stock_research/dashboard/`, React + TypeScript, Vitest, Testing Library, pytest.

---

## Scope

This plan implements Phase 1 from `docs/superpowers/specs/2026-06-11-research-dashboard-product-redesign-v2-design.md`.

Included:

- New navigation labels and workspace shell.
- `Generated Reports` rename for the existing local artifact browser.
- EOD-only `Market Monitor` backend API and frontend page.
- `News` auto-refresh and last-updated state.
- Home cockpit redesign using existing summary/news/market monitor data.
- UI style refresh for a denser workstation look.

Not included:

- Real external broker/institution research report adapter.
- Full single-stock workspace data aggregation.
- Watchlist persistence or editing.
- Intraday/real-time market data.
- Global search backend.

## Existing Dirty Worktree Warning

The worktree currently has unrelated backtest changes:

- `dashboard/src/api/types.ts`
- `dashboard/src/components/BacktestLabWorkspace.tsx`
- `dashboard/tests/backtest-lab-workspace.test.tsx`
- `dashboard/tests/client.test.ts`
- `src/stock_research/dashboard/backtests.py`
- `src/stock_research/vectorized_topn_backtest.py`
- `tests/test_dashboard_backtests.py`
- `tests/test_vectorized_topn_backtest.py`

Before executing this plan, inspect those files. Do not revert them. If this plan must edit `dashboard/src/api/types.ts` or `dashboard/tests/client.test.ts`, merge carefully with the existing changes and stage only the relevant hunks.

## File Structure

Create:

- `src/stock_research/dashboard/market_monitor.py`
  - Builds an EOD-only market monitor payload from local dashboard data.
- `tests/test_dashboard_market_monitor.py`
  - Unit tests for latest-date fallback and payload shape.
- `dashboard/src/components/MarketMonitorWorkspace.tsx`
  - EOD monitor page.
- `dashboard/src/components/GeneratedReportsWorkspace.tsx`
  - Renamed wrapper/replacement for current Reports workspace.
- `dashboard/src/components/ResearchReportsWorkspace.tsx`
  - Phase 1 placeholder explaining external research report page boundary.
- `dashboard/src/components/StockWorkspace.tsx`
  - Phase 1 placeholder for future single-stock hub.
- `dashboard/src/components/WatchlistWorkspace.tsx`
  - Phase 1 read-only queue-style wrapper using existing overview watchlist rows if practical.
- `dashboard/src/components/StrategyLabWorkspace.tsx`
  - Phase 1 wrapper that exposes Backtest Lab and Strategy Validation as tabs.

Modify:

- `src/stock_research/dashboard/app.py`
  - Add `/api/market-monitor/eod`.
- `dashboard/src/api/types.ts`
  - Add `MarketMonitor*` DTOs.
- `dashboard/src/api/client.ts`
  - Add `fetchMarketMonitorEod`.
- `dashboard/src/components/AppShell.tsx`
  - Add top bar, new navigation, new workspaces.
- `dashboard/src/components/HomeCockpit.tsx`
  - Redesign summary into cockpit layout.
- `dashboard/src/components/NewsWorkspace.tsx`
  - Add 60-second auto-refresh, last updated, failure behavior.
- `dashboard/src/components/ReportsWorkspace.tsx`
  - Either rename to `GeneratedReportsWorkspace` or leave as implementation detail and export wrapper.
- `dashboard/src/styles.css`
  - Apply V2 workstation visual system.
- `dashboard/tests/app-shell.test.tsx`
  - Add navigation and workspace tests.
- `dashboard/tests/client.test.ts`
  - Add market monitor client test.
- `tests/test_dashboard_app.py`
  - Add route test for `/api/market-monitor/eod`.

---

### Task 1: Add EOD Market Monitor Backend Read Model

**Files:**

- Create: `src/stock_research/dashboard/market_monitor.py`
- Test: `tests/test_dashboard_market_monitor.py`
- Modify: `src/stock_research/dashboard/app.py`
- Modify test: `tests/test_dashboard_app.py`

- [ ] **Step 1: Write failing unit tests for market monitor payload**

Create `tests/test_dashboard_market_monitor.py`:

```python
from stock_research.dashboard import market_monitor


def test_build_market_monitor_eod_uses_latest_complete_date(monkeypatch):
    monkeypatch.setattr(
        market_monitor,
        "load_platform_summary",
        lambda score_version="manual_v1", top_n=5: {
            "latest_market_date": "2026-06-10",
            "latest_factor_date": "2026-06-10",
            "latest_score_date": "2026-06-10",
            "market_asset_count": 5300,
            "score_asset_count": 3100,
            "factor_count": 42,
            "topn_preview": [
                {
                    "trade_date": "2026-06-10",
                    "asset_id": "000001.SZ",
                    "rank": 1,
                    "score_total": 91.2,
                    "score_version": "manual_v1",
                    "score_components": {},
                }
            ],
        },
    )
    monkeypatch.setattr(
        market_monitor,
        "load_report_links",
        lambda trade_date: [
            {
                "report_type": "daily_topn_report",
                "title": "daily_topn_2026-06-10_manual_v1.md",
                "path": "/reports/topn.md",
                "format": "md",
                "trade_date": trade_date,
            }
        ],
    )

    payload = market_monitor.build_market_monitor_eod()

    assert payload["trade_date"] == "2026-06-10"
    assert payload["freshness"]["mode"] == "eod"
    assert payload["freshness"]["is_realtime"] is False
    assert payload["coverage"]["market_assets"] == 5300
    assert payload["strategy_signal_summary"]["topn_preview_count"] == 1
    assert payload["generated_reports"][0]["report_type"] == "daily_topn_report"


def test_build_market_monitor_eod_returns_warning_without_market_date(monkeypatch):
    monkeypatch.setattr(
        market_monitor,
        "load_platform_summary",
        lambda score_version="manual_v1", top_n=5: {
            "latest_market_date": None,
            "latest_factor_date": None,
            "latest_score_date": None,
            "market_asset_count": 0,
            "score_asset_count": 0,
            "factor_count": 0,
            "topn_preview": [],
        },
    )
    monkeypatch.setattr(market_monitor, "load_report_links", lambda trade_date: [])

    payload = market_monitor.build_market_monitor_eod()

    assert payload["trade_date"] == ""
    assert "latest complete market date is unavailable" in payload["warnings"]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_market_monitor.py -q
```

Expected: fail with `ImportError` or missing `market_monitor`.

- [ ] **Step 3: Implement minimal market monitor read model**

Create `src/stock_research/dashboard/market_monitor.py`:

```python
from __future__ import annotations

from typing import Any

from stock_research.dashboard.platform import load_platform_summary
from stock_research.dashboard.reports import load_report_links


def build_market_monitor_eod(
    *,
    trade_date: str | None = None,
    score_version: str = "manual_v1",
    top_n: int = 5,
) -> dict[str, Any]:
    summary = load_platform_summary(score_version=score_version, top_n=top_n)
    latest_market_date = str(summary.get("latest_market_date") or "")
    selected_trade_date = trade_date or latest_market_date
    warnings: list[str] = []
    if not selected_trade_date:
        warnings.append("latest complete market date is unavailable")

    topn_preview = list(summary.get("topn_preview") or [])
    reports = load_report_links(selected_trade_date) if selected_trade_date else []

    return {
        "trade_date": selected_trade_date,
        "freshness": {
            "mode": "eod",
            "label": "Last Completed Trading Day",
            "is_realtime": False,
            "latest_market_date": latest_market_date,
            "latest_factor_date": summary.get("latest_factor_date") or "",
            "latest_score_date": summary.get("latest_score_date") or "",
        },
        "coverage": {
            "market_assets": int(summary.get("market_asset_count") or 0),
            "score_assets": int(summary.get("score_asset_count") or 0),
            "factor_count": int(summary.get("factor_count") or 0),
        },
        "market_breadth": {
            "advancers": None,
            "decliners": None,
            "limit_up": None,
            "limit_down": None,
            "advancing_ratio": None,
            "turnover_change_pct": None,
            "status": "pending_source",
        },
        "index_snapshot": [],
        "sector_strength": {"strongest": [], "weakest": [], "status": "pending_source"},
        "unusual_moves": [],
        "watchlist_alerts": [],
        "strategy_signal_summary": {
            "topn_preview_count": len(topn_preview),
            "topn_preview": topn_preview,
            "risk_filter_counts": {},
        },
        "generated_reports": reports[:8],
        "warnings": warnings,
    }
```

- [ ] **Step 4: Run unit tests and verify they pass**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_market_monitor.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Write failing FastAPI route test**

Append to `tests/test_dashboard_app.py`:

```python
def test_market_monitor_eod_route_returns_payload(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "build_market_monitor_eod",
        lambda trade_date=None, score_version="manual_v1", top_n=5: {
            "trade_date": trade_date or "2026-06-10",
            "freshness": {"mode": "eod", "is_realtime": False},
            "coverage": {"market_assets": 5300, "score_assets": 3100, "factor_count": 42},
            "market_breadth": {"status": "pending_source"},
            "index_snapshot": [],
            "sector_strength": {"strongest": [], "weakest": [], "status": "pending_source"},
            "unusual_moves": [],
            "watchlist_alerts": [],
            "strategy_signal_summary": {"topn_preview_count": 0, "topn_preview": [], "risk_filter_counts": {}},
            "generated_reports": [],
            "warnings": [],
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/market-monitor/eod?trade_date=2026-06-10&top_n=3")

    assert response.status_code == 200
    assert response.json()["trade_date"] == "2026-06-10"
    assert response.json()["freshness"]["is_realtime"] is False
```

- [ ] **Step 6: Run route test and verify it fails**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_app.py::test_market_monitor_eod_route_returns_payload -q
```

Expected: fail because `dashboard_app.build_market_monitor_eod` or route is missing.

- [ ] **Step 7: Add FastAPI route**

Modify `src/stock_research/dashboard/app.py`:

```python
from stock_research.dashboard.market_monitor import build_market_monitor_eod
```

Add after `/api/platform/summary`:

```python
    @app.get("/api/market-monitor/eod")
    def market_monitor_eod(
        trade_date: str | None = None,
        score_version: str = "manual_v1",
        top_n: int = 5,
    ):
        return build_market_monitor_eod(
            trade_date=trade_date,
            score_version=score_version,
            top_n=top_n,
        )
```

- [ ] **Step 8: Run backend focused tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_market_monitor.py tests/test_dashboard_app.py -q
```

Expected: all tests pass.

- [ ] **Step 9: Commit backend market monitor**

Run:

```bash
git add src/stock_research/dashboard/market_monitor.py src/stock_research/dashboard/app.py tests/test_dashboard_market_monitor.py tests/test_dashboard_app.py
git commit -m "feat: add eod market monitor api"
```

---

### Task 2: Add Frontend Market Monitor Types and API Client

**Files:**

- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify test: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Write failing client test**

Append to `dashboard/tests/client.test.ts`:

```typescript
import { fetchMarketMonitorEod } from '../src/api/client';

it('fetches EOD market monitor with optional trade date', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      trade_date: '2026-06-10',
      freshness: { mode: 'eod', label: 'Last Completed Trading Day', is_realtime: false },
      coverage: { market_assets: 5300, score_assets: 3100, factor_count: 42 },
      market_breadth: { status: 'pending_source' },
      index_snapshot: [],
      sector_strength: { strongest: [], weakest: [], status: 'pending_source' },
      unusual_moves: [],
      watchlist_alerts: [],
      strategy_signal_summary: { topn_preview_count: 0, topn_preview: [], risk_filter_counts: {} },
      generated_reports: [],
      warnings: []
    })
  });
  vi.stubGlobal('fetch', fetchMock);

  const result = await fetchMarketMonitorEod({ tradeDate: '2026-06-10', topN: 3 });

  expect(fetchMock).toHaveBeenCalledWith('/api/market-monitor/eod?trade_date=2026-06-10&top_n=3');
  expect(result.freshness.is_realtime).toBe(false);
});
```

If `fetchMarketMonitorEod` is already imported in the grouped import block, add it there instead of using a second import.

- [ ] **Step 2: Run client test and verify it fails**

Run:

```bash
pnpm test -- --run tests/client.test.ts
```

Expected: fail because `fetchMarketMonitorEod` is not exported.

- [ ] **Step 3: Add DTO types**

Append to `dashboard/src/api/types.ts`:

```typescript
export type MarketMonitorFreshness = {
  mode: 'eod' | string;
  label: string;
  is_realtime: boolean;
  latest_market_date?: string;
  latest_factor_date?: string;
  latest_score_date?: string;
};

export type MarketMonitorCoverage = {
  market_assets: number;
  score_assets: number;
  factor_count: number;
};

export type MarketBreadth = {
  advancers: number | null;
  decliners: number | null;
  limit_up: number | null;
  limit_down: number | null;
  advancing_ratio: number | null;
  turnover_change_pct: number | null;
  status: string;
};

export type MarketMonitorPayload = {
  trade_date: string;
  freshness: MarketMonitorFreshness;
  coverage: MarketMonitorCoverage;
  market_breadth: MarketBreadth;
  index_snapshot: Array<Record<string, unknown>>;
  sector_strength: {
    strongest: Array<Record<string, unknown>>;
    weakest: Array<Record<string, unknown>>;
    status: string;
  };
  unusual_moves: Array<Record<string, unknown>>;
  watchlist_alerts: Array<Record<string, unknown>>;
  strategy_signal_summary: {
    topn_preview_count: number;
    topn_preview: ScoreRow[];
    risk_filter_counts: Record<string, number>;
  };
  generated_reports: ReportLink[];
  warnings: string[];
};
```

- [ ] **Step 4: Add API client method**

Modify `dashboard/src/api/client.ts` import list:

```typescript
  MarketMonitorPayload,
```

Add near `OverviewParams`:

```typescript
type MarketMonitorParams = {
  tradeDate?: string;
  scoreVersion?: string;
  topN?: number;
};
```

Add after `fetchOverview`:

```typescript
export async function fetchMarketMonitorEod(params: MarketMonitorParams = {}): Promise<MarketMonitorPayload> {
  const searchParams = new URLSearchParams();
  if (params.tradeDate) searchParams.set('trade_date', params.tradeDate);
  if (params.scoreVersion) searchParams.set('score_version', params.scoreVersion);
  searchParams.set('top_n', String(params.topN ?? 5));
  return getJson(`/api/market-monitor/eod?${searchParams.toString()}`);
}
```

- [ ] **Step 5: Run client tests**

Run:

```bash
pnpm test -- --run tests/client.test.ts
```

Expected: pass.

- [ ] **Step 6: Commit frontend API**

Run:

```bash
git add dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/tests/client.test.ts
git commit -m "feat: add market monitor dashboard client"
```

---

### Task 3: Rework Shell Navigation and Add Placeholder Workspaces

**Files:**

- Modify: `dashboard/src/components/AppShell.tsx`
- Create: `dashboard/src/components/ResearchReportsWorkspace.tsx`
- Create: `dashboard/src/components/StockWorkspace.tsx`
- Create: `dashboard/src/components/WatchlistWorkspace.tsx`
- Create: `dashboard/src/components/StrategyLabWorkspace.tsx`
- Create: `dashboard/src/components/GeneratedReportsWorkspace.tsx`
- Modify test: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Write failing navigation test**

Append to `dashboard/tests/app-shell.test.tsx`:

```typescript
it('exposes the redesigned research cockpit navigation', async () => {
  render(<App />);

  expect(screen.getByRole('button', { name: 'Open Market Monitor workspace' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Open Research Reports workspace' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Open Stock Workspace workspace' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Open Watchlist workspace' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Open Strategy Lab workspace' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Open Generated Reports workspace' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Open Reports workspace' })).not.toBeInTheDocument();
});

it('opens phase one placeholder workspaces from the redesigned navigation', async () => {
  render(<App />);

  fireEvent.click(screen.getByRole('button', { name: 'Open Research Reports workspace' }));
  expect(await screen.findByRole('heading', { name: 'Research Reports' })).toBeInTheDocument();
  expect(screen.getByText('External broker and institution reports will be stock-first in Phase 3.')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Open Stock Workspace workspace' }));
  expect(await screen.findByRole('heading', { name: 'Stock Workspace' })).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Open Watchlist workspace' }));
  expect(await screen.findByRole('heading', { name: 'Watchlist' })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run app-shell tests and verify they fail**

Run:

```bash
pnpm test -- --run tests/app-shell.test.tsx
```

Expected: fail because the new nav items/components do not exist.

- [ ] **Step 3: Add placeholder workspace components**

Create `dashboard/src/components/ResearchReportsWorkspace.tsx`:

```tsx
export function ResearchReportsWorkspace() {
  return (
    <section className="workspace-stack" aria-label="Research Reports workspace">
      <header className="workspace-header">
        <h1>Research Reports</h1>
        <p className="muted">External broker and institution reports will be stock-first in Phase 3.</p>
      </header>
      <section className="workspace-panel">
        <div className="section-heading">
          <h2>Planned Search Model</h2>
          <span className="status-chip neutral">stock-first</span>
        </div>
        <div className="placeholder-grid">
          <span>Stock code/name</span>
          <span>Institution</span>
          <span>Rating action</span>
          <span>Date range</span>
        </div>
      </section>
    </section>
  );
}
```

Create `dashboard/src/components/StockWorkspace.tsx`:

```tsx
export function StockWorkspace() {
  return (
    <section className="workspace-stack" aria-label="Stock Workspace workspace">
      <header className="workspace-header">
        <h1>Stock Workspace</h1>
        <p className="muted">Single-stock evidence hub for price, factors, news, research reports, and strategy history.</p>
      </header>
      <section className="workspace-panel">
        <div className="section-heading">
          <h2>Phase 2 Scope</h2>
          <span className="status-chip neutral">planned</span>
        </div>
        <p className="muted">This page will become the primary deep-dive destination from news, watchlist, factors, and strategy evidence.</p>
      </section>
    </section>
  );
}
```

Create `dashboard/src/components/WatchlistWorkspace.tsx`:

```tsx
export function WatchlistWorkspace() {
  return (
    <section className="workspace-stack" aria-label="Watchlist workspace">
      <header className="workspace-header">
        <h1>Watchlist</h1>
        <p className="muted">Research queue view for status, priority, signal, risk, and next action.</p>
      </header>
      <section className="workspace-panel">
        <div className="section-heading">
          <h2>Queue Model</h2>
          <span className="status-chip neutral">read-only foundation</span>
        </div>
        <div className="placeholder-grid">
          <span>Observe</span>
          <span>Candidate</span>
          <span>Holding</span>
          <span>Review</span>
        </div>
      </section>
    </section>
  );
}
```

Create `dashboard/src/components/GeneratedReportsWorkspace.tsx`:

```tsx
import { ReportsWorkspace } from './ReportsWorkspace';

export function GeneratedReportsWorkspace() {
  return <ReportsWorkspace title="Generated Reports" description="Local generated artifacts from TopN, risk, factor, backtest, and validation jobs." />;
}
```

Create `dashboard/src/components/StrategyLabWorkspace.tsx`:

```tsx
import { useState } from 'react';
import { BacktestLabWorkspace } from './BacktestLabWorkspace';
import { StrategyValidationWorkspace } from './StrategyValidationWorkspace';

type StrategyLabTab = 'backtest' | 'validation';

export function StrategyLabWorkspace() {
  const [tab, setTab] = useState<StrategyLabTab>('backtest');

  return (
    <section className="workspace-stack" aria-label="Strategy Lab workspace">
      <header className="workspace-header">
        <h1>Strategy Lab</h1>
        <p className="muted">Run local backtests and inspect existing strategy validation evidence.</p>
      </header>
      <div className="segmented-control" role="tablist" aria-label="Strategy Lab sections">
        <button type="button" role="tab" aria-selected={tab === 'backtest'} onClick={() => setTab('backtest')}>
          Run Backtest
        </button>
        <button type="button" role="tab" aria-selected={tab === 'validation'} onClick={() => setTab('validation')}>
          Validation Replay
        </button>
      </div>
      {tab === 'backtest' ? <BacktestLabWorkspace embedded /> : <StrategyValidationWorkspace embedded />}
    </section>
  );
}
```

- [ ] **Step 4: Allow generated reports props**

Modify `dashboard/src/components/ReportsWorkspace.tsx` signature:

```tsx
type ReportsWorkspaceProps = {
  title?: string;
  description?: string;
};

export function ReportsWorkspace({
  title = 'Reports',
  description = 'Local research artifacts and generated reports.'
}: ReportsWorkspaceProps = {}) {
```

Replace hard-coded header text:

```tsx
<h1>{title}</h1>
<p className="muted">{description}</p>
```

- [ ] **Step 5: Allow embedded strategy components**

If `BacktestLabWorkspace` and `StrategyValidationWorkspace` do not accept props, add optional props:

```tsx
type BacktestLabWorkspaceProps = {
  embedded?: boolean;
};

export function BacktestLabWorkspace({ embedded = false }: BacktestLabWorkspaceProps = {}) {
```

Wrap the existing header so it is hidden when embedded:

```tsx
{embedded ? null : (
  <header className="workspace-header">
    <h1>Backtest Lab</h1>
    <p className="muted">Run local strategy backtests with explicit parameters and review generated evidence.</p>
  </header>
)}
```

Apply the same pattern to `StrategyValidationWorkspace`.

- [ ] **Step 6: Update AppShell navigation**

Modify `dashboard/src/components/AppShell.tsx`:

```tsx
import { GeneratedReportsWorkspace } from './GeneratedReportsWorkspace';
import { MarketMonitorWorkspace } from './MarketMonitorWorkspace';
import { ResearchReportsWorkspace } from './ResearchReportsWorkspace';
import { StockWorkspace } from './StockWorkspace';
import { StrategyLabWorkspace } from './StrategyLabWorkspace';
import { WatchlistWorkspace } from './WatchlistWorkspace';
```

Use:

```tsx
type WorkspaceMode =
  | 'home'
  | 'market'
  | 'news'
  | 'researchReports'
  | 'stock'
  | 'watchlist'
  | 'factors'
  | 'strategyLab'
  | 'data'
  | 'generatedReports';

const NAV_ITEMS: Array<{ mode: WorkspaceMode; label: string }> = [
  { mode: 'home', label: 'Home' },
  { mode: 'market', label: 'Market Monitor' },
  { mode: 'news', label: 'News' },
  { mode: 'researchReports', label: 'Research Reports' },
  { mode: 'stock', label: 'Stock Workspace' },
  { mode: 'watchlist', label: 'Watchlist' },
  { mode: 'factors', label: 'Factor Lab' },
  { mode: 'strategyLab', label: 'Strategy Lab' },
  { mode: 'data', label: 'Data Explorer' },
  { mode: 'generatedReports', label: 'Generated Reports' }
];
```

Render:

```tsx
{workspaceMode === 'market' ? <MarketMonitorWorkspace /> : null}
{workspaceMode === 'researchReports' ? <ResearchReportsWorkspace /> : null}
{workspaceMode === 'stock' ? <StockWorkspace /> : null}
{workspaceMode === 'watchlist' ? <WatchlistWorkspace /> : null}
{workspaceMode === 'strategyLab' ? <StrategyLabWorkspace /> : null}
{workspaceMode === 'generatedReports' ? <GeneratedReportsWorkspace /> : null}
```

Temporarily import `MarketMonitorWorkspace` even before Task 4 by creating a minimal file:

```tsx
export function MarketMonitorWorkspace() {
  return (
    <section className="workspace-stack" aria-label="Market Monitor workspace">
      <header className="workspace-header">
        <h1>Market Monitor</h1>
        <p className="muted">EOD market state for the latest completed trading day.</p>
      </header>
    </section>
  );
}
```

- [ ] **Step 7: Run app-shell tests**

Run:

```bash
pnpm test -- --run tests/app-shell.test.tsx
```

Expected: pass.

- [ ] **Step 8: Commit shell/navigation**

Run:

```bash
git add dashboard/src/components/AppShell.tsx dashboard/src/components/ResearchReportsWorkspace.tsx dashboard/src/components/StockWorkspace.tsx dashboard/src/components/WatchlistWorkspace.tsx dashboard/src/components/StrategyLabWorkspace.tsx dashboard/src/components/GeneratedReportsWorkspace.tsx dashboard/src/components/MarketMonitorWorkspace.tsx dashboard/src/components/ReportsWorkspace.tsx dashboard/src/components/BacktestLabWorkspace.tsx dashboard/src/components/StrategyValidationWorkspace.tsx dashboard/tests/app-shell.test.tsx
git commit -m "feat: redesign dashboard navigation shell"
```

---

### Task 4: Build Market Monitor Workspace UI

**Files:**

- Modify: `dashboard/src/components/MarketMonitorWorkspace.tsx`
- Modify test: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Add failing Market Monitor UI test**

Append to `dashboard/tests/app-shell.test.tsx`:

```typescript
it('renders EOD market monitor data without implying realtime data', async () => {
  apiMocks.fetchMarketMonitorEod.mockResolvedValueOnce({
    trade_date: '2026-06-10',
    freshness: {
      mode: 'eod',
      label: 'Last Completed Trading Day',
      is_realtime: false,
      latest_market_date: '2026-06-10',
      latest_factor_date: '2026-06-10',
      latest_score_date: '2026-06-10'
    },
    coverage: { market_assets: 5300, score_assets: 3100, factor_count: 42 },
    market_breadth: {
      advancers: null,
      decliners: null,
      limit_up: null,
      limit_down: null,
      advancing_ratio: null,
      turnover_change_pct: null,
      status: 'pending_source'
    },
    index_snapshot: [],
    sector_strength: { strongest: [], weakest: [], status: 'pending_source' },
    unusual_moves: [],
    watchlist_alerts: [],
    strategy_signal_summary: {
      topn_preview_count: 1,
      topn_preview: [{ trade_date: '2026-06-10', asset_id: '000001.SZ', rank: 1, score_total: 91.2, score_version: 'manual_v1', score_components: {} }],
      risk_filter_counts: {}
    },
    generated_reports: [{ report_type: 'daily_topn_report', title: 'daily_topn.md', path: '/reports/topn.md', format: 'md', trade_date: '2026-06-10' }],
    warnings: ['market breadth source pending']
  });

  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Open Market Monitor workspace' }));

  expect(await screen.findByRole('heading', { name: 'Market Monitor' })).toBeInTheDocument();
  expect(screen.getByText('Last Completed Trading Day')).toBeInTheDocument();
  expect(screen.getByText('2026-06-10')).toBeInTheDocument();
  expect(screen.getByText('5,300')).toBeInTheDocument();
  expect(screen.getByText('000001.SZ')).toBeInTheDocument();
  expect(screen.getByText('market breadth source pending')).toBeInTheDocument();
});
```

Add `fetchMarketMonitorEod: vi.fn(),` to the `apiMocks` object if missing.

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
pnpm test -- --run tests/app-shell.test.tsx
```

Expected: fail because workspace still renders placeholder.

- [ ] **Step 3: Implement MarketMonitorWorkspace**

Replace `dashboard/src/components/MarketMonitorWorkspace.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { fetchMarketMonitorEod } from '../api/client';
import type { MarketMonitorPayload } from '../api/types';

function formatCount(value: number | null | undefined) {
  return typeof value === 'number' ? value.toLocaleString() : '-';
}

function formatScore(value: number | null | undefined) {
  return typeof value === 'number' ? value.toFixed(1) : '-';
}

export function MarketMonitorWorkspace() {
  const [payload, setPayload] = useState<MarketMonitorPayload | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadLatest() {
    setIsLoading(true);
    setError(null);
    try {
      setPayload(await fetchMarketMonitorEod({ topN: 5 }));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadLatest();
  }, []);

  return (
    <section className="workspace-stack" aria-label="Market Monitor workspace">
      <header className="workspace-header workspace-header-row">
        <div>
          <h1>Market Monitor</h1>
          <p className="muted">EOD market state for the latest completed trading day.</p>
        </div>
        <button type="button" onClick={loadLatest} disabled={isLoading}>
          {isLoading ? 'Loading...' : 'Load Latest EOD'}
        </button>
      </header>

      {error ? <p className="error-text">{error}</p> : null}
      {payload?.warnings.map((warning) => <p className="warning-text" key={warning}>{warning}</p>)}

      <section className="status-strip" aria-label="Market monitor freshness">
        <div>
          <span>Mode</span>
          <strong>{payload?.freshness.label ?? 'Last Completed Trading Day'}</strong>
        </div>
        <div>
          <span>Trade Date</span>
          <strong>{payload?.trade_date || '-'}</strong>
        </div>
        <div>
          <span>Realtime</span>
          <strong>{payload?.freshness.is_realtime ? 'Yes' : 'No'}</strong>
        </div>
      </section>

      <section className="cockpit-grid">
        <div className="metric-card compact">
          <span>Market Assets</span>
          <strong>{formatCount(payload?.coverage.market_assets)}</strong>
        </div>
        <div className="metric-card compact">
          <span>Score Assets</span>
          <strong>{formatCount(payload?.coverage.score_assets)}</strong>
        </div>
        <div className="metric-card compact">
          <span>Factor Count</span>
          <strong>{formatCount(payload?.coverage.factor_count)}</strong>
        </div>
        <div className="metric-card compact">
          <span>TopN Preview</span>
          <strong>{formatCount(payload?.strategy_signal_summary.topn_preview_count)}</strong>
        </div>
      </section>

      <section className="workspace-panel">
        <div className="section-heading">
          <h2>Strategy Signal Summary</h2>
          <span className="status-chip neutral">EOD</span>
        </div>
        <div className="data-table">
          <div className="data-table-header three-col">
            <span>Rank</span>
            <span>Asset</span>
            <span>Score</span>
          </div>
          {(payload?.strategy_signal_summary.topn_preview ?? []).map((row) => (
            <div className="data-table-row three-col" key={`${row.trade_date}-${row.asset_id}`}>
              <span>{row.rank}</span>
              <strong>{row.asset_id}</strong>
              <span>{formatScore(row.score_total)}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="workspace-panel">
        <div className="section-heading">
          <h2>Generated Reports</h2>
          <span className="status-chip neutral">local artifacts</span>
        </div>
        <div className="report-list compact">
          {(payload?.generated_reports ?? []).map((report) => (
            <a href={report.path} key={report.path}>
              <span>{report.report_type}</span>
              <strong>{report.title}</strong>
            </a>
          ))}
        </div>
      </section>
    </section>
  );
}
```

- [ ] **Step 4: Run app-shell tests**

Run:

```bash
pnpm test -- --run tests/app-shell.test.tsx
```

Expected: pass.

- [ ] **Step 5: Commit Market Monitor UI**

Run:

```bash
git add dashboard/src/components/MarketMonitorWorkspace.tsx dashboard/tests/app-shell.test.tsx
git commit -m "feat: add eod market monitor workspace"
```

---

### Task 5: Add News Auto-Refresh and Last Updated State

**Files:**

- Modify: `dashboard/src/components/NewsWorkspace.tsx`
- Modify test: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Write failing auto-refresh test**

Append to `dashboard/tests/app-shell.test.tsx`:

```typescript
it('auto-refreshes news and preserves visible rows on refresh failure', async () => {
  vi.useFakeTimers();
  apiMocks.fetchPublicNews
    .mockResolvedValueOnce({
      items: [{
        news_id: 'news-1',
        source: 'sina_finance',
        source_channel: '7x24',
        category: 'live',
        title: '首条快讯',
        summary: '',
        url: '',
        published_at: '2026-06-11 10:00:00',
        collected_at: '2026-06-11T02:00:00Z',
        raw_id: '',
        raw_payload: {},
        status: 'available'
      }],
      warnings: []
    })
    .mockResolvedValueOnce({
      items: [{
        news_id: 'news-1',
        source: 'sina_finance',
        source_channel: '7x24',
        category: 'live',
        title: '首条快讯',
        summary: '',
        url: '',
        published_at: '2026-06-11 10:00:00',
        collected_at: '2026-06-11T02:00:00Z',
        raw_id: '',
        raw_payload: {},
        status: 'available'
      }],
      warnings: []
    });
  apiMocks.refreshPublicNews.mockRejectedValueOnce(new Error('source timeout'));

  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Open News workspace' }));

  expect(await screen.findByText('首条快讯')).toBeInTheDocument();
  await vi.advanceTimersByTimeAsync(60000);

  expect(apiMocks.refreshPublicNews).toHaveBeenCalled();
  expect(await screen.findByText('source timeout')).toBeInTheDocument();
  expect(screen.getByText('首条快讯')).toBeInTheDocument();
  vi.useRealTimers();
});
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
pnpm test -- --run tests/app-shell.test.tsx
```

Expected: fail because News does not auto-refresh.

- [ ] **Step 3: Refactor NewsWorkspace load helpers and interval**

Modify `dashboard/src/components/NewsWorkspace.tsx`:

```tsx
const NEWS_REFRESH_INTERVAL_MS = 60000;
```

Add state:

```tsx
const [lastUpdatedAt, setLastUpdatedAt] = useState<string>('');
```

Replace initial `useEffect` and `handleRefresh` with:

```tsx
async function loadCachedNews(ignoreUpdate = false) {
  const payload = await fetchPublicNews({ source: 'sina_finance', limit: 200 });
  if (!ignoreUpdate) {
    setItems(payload.items);
    setWarnings(payload.warnings ?? []);
    setLastUpdatedAt(new Date().toLocaleTimeString());
  }
}

async function refreshNews() {
  const refreshResult = await refreshPublicNews();
  const payload = await fetchPublicNews({ source: 'sina_finance', limit: 200 });
  setItems(payload.items);
  setWarnings([...(refreshResult.warnings ?? []), ...(payload.warnings ?? [])]);
  setLastUpdatedAt(new Date().toLocaleTimeString());
}

useEffect(() => {
  let ignore = false;
  setIsLoading(true);
  fetchPublicNews({ source: 'sina_finance', limit: 200 })
    .then((payload) => {
      if (!ignore) {
        setItems(payload.items);
        setWarnings(payload.warnings ?? []);
        setLastUpdatedAt(new Date().toLocaleTimeString());
      }
    })
    .catch((err: unknown) => {
      if (!ignore) {
        setWarnings([err instanceof Error ? err.message : String(err)]);
      }
    })
    .finally(() => {
      if (!ignore) setIsLoading(false);
    });

  const timer = window.setInterval(() => {
    refreshNews().catch((err: unknown) => {
      if (!ignore) {
        setWarnings([err instanceof Error ? err.message : String(err)]);
      }
    });
  }, NEWS_REFRESH_INTERVAL_MS);

  return () => {
    ignore = true;
    window.clearInterval(timer);
  };
}, []);

async function handleRefresh() {
  setIsRefreshing(true);
  try {
    await refreshNews();
  } catch (err: unknown) {
    setWarnings([err instanceof Error ? err.message : String(err)]);
  } finally {
    setIsRefreshing(false);
  }
}
```

Add in the header/section heading:

```tsx
{lastUpdatedAt ? <span className="muted">Last updated {lastUpdatedAt}</span> : null}
```

- [ ] **Step 4: Run app-shell tests**

Run:

```bash
pnpm test -- --run tests/app-shell.test.tsx
```

Expected: pass. If fake timers cause cleanup issues, ensure the test calls `vi.useRealTimers()` in `finally`.

- [ ] **Step 5: Commit News auto-refresh**

Run:

```bash
git add dashboard/src/components/NewsWorkspace.tsx dashboard/tests/app-shell.test.tsx
git commit -m "feat: auto refresh public news workspace"
```

---

### Task 6: Redesign Home Cockpit for Phase 1

**Files:**

- Modify: `dashboard/src/components/HomeCockpit.tsx`
- Modify test: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Write failing Home layout test**

Append to `dashboard/tests/app-shell.test.tsx`:

```typescript
it('renders the redesigned home cockpit sections', async () => {
  apiMocks.fetchMarketMonitorEod.mockResolvedValueOnce({
    trade_date: '2026-06-10',
    freshness: { mode: 'eod', label: 'Last Completed Trading Day', is_realtime: false },
    coverage: { market_assets: 5300, score_assets: 3100, factor_count: 42 },
    market_breadth: { advancers: null, decliners: null, limit_up: null, limit_down: null, advancing_ratio: null, turnover_change_pct: null, status: 'pending_source' },
    index_snapshot: [],
    sector_strength: { strongest: [], weakest: [], status: 'pending_source' },
    unusual_moves: [],
    watchlist_alerts: [],
    strategy_signal_summary: { topn_preview_count: 1, topn_preview: [{ trade_date: '2026-06-10', asset_id: '000001.SZ', rank: 1, score_total: 91.2, score_version: 'manual_v1', score_components: {} }], risk_filter_counts: {} },
    generated_reports: [],
    warnings: []
  });
  apiMocks.fetchPublicNews.mockResolvedValueOnce({
    items: [{
      news_id: 'news-home-1',
      source: 'sina_finance',
      source_channel: '7x24',
      category: 'live',
      title: '首页新闻',
      summary: '',
      url: '',
      published_at: '2026-06-11 10:00:00',
      collected_at: '2026-06-11T02:00:00Z',
      raw_id: '',
      raw_payload: {},
      status: 'available'
    }],
    warnings: []
  });

  render(<App />);

  expect(await screen.findByRole('heading', { name: 'Research Cockpit' })).toBeInTheDocument();
  expect(screen.getByText('Today Focus')).toBeInTheDocument();
  expect(screen.getByText('Market Pulse')).toBeInTheDocument();
  expect(screen.getByText('News Flow')).toBeInTheDocument();
  expect(screen.getByText('Strategy Health')).toBeInTheDocument();
  expect(screen.getByText('首页新闻')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
pnpm test -- --run tests/app-shell.test.tsx
```

Expected: fail because Home does not render the new sections.

- [ ] **Step 3: Update HomeCockpit data fetching**

Modify imports:

```tsx
import { fetchBacktestStrategies, fetchMarketMonitorEod, fetchPlatformSummary, fetchPublicNews } from '../api/client';
import type { MarketMonitorPayload, PlatformSummary, PublicNewsItem, ScoreRow, StrategyCatalogItem } from '../api/types';
```

Add state:

```tsx
const [marketMonitor, setMarketMonitor] = useState<MarketMonitorPayload | null>(null);
const [newsItems, setNewsItems] = useState<PublicNewsItem[]>([]);
```

Replace `Promise.all`:

```tsx
Promise.all([
  fetchPlatformSummary(),
  fetchBacktestStrategies(),
  fetchMarketMonitorEod({ topN: 5 }),
  fetchPublicNews({ source: 'sina_finance', limit: 5 })
])
  .then(([summaryPayload, strategyRows, marketPayload, newsPayload]) => {
    if (!ignore) {
      setSummary(summaryPayload);
      setStrategies(strategyRows);
      setMarketMonitor(marketPayload);
      setNewsItems(newsPayload.items);
      setIsLoading(false);
    }
  })
```

- [ ] **Step 4: Replace Home markup with cockpit sections**

Keep the `Research Cockpit` heading, then render:

```tsx
<section className="status-strip" aria-label="Dashboard status">
  <div><span>Market Date</span><strong>{summary?.latest_market_date ?? '-'}</strong></div>
  <div><span>Factor Date</span><strong>{summary?.latest_factor_date ?? '-'}</strong></div>
  <div><span>EOD Monitor</span><strong>{marketMonitor?.trade_date || '-'}</strong></div>
  <div><span>Strategies</span><strong>{formatCount(strategies.length)}</strong></div>
</section>

<section className="cockpit-layout">
  <section className="workspace-panel">
    <div className="section-heading"><h2>Today Focus</h2><span className="status-chip neutral">candidate pool</span></div>
    <div className="data-table">
      {(summary?.topn_preview ?? []).slice(0, 5).map((row) => (
        <div className="data-table-row three-col" key={`${row.trade_date}-${row.asset_id}`}>
          <span>{row.rank}</span><strong>{row.asset_id}</strong><span>{formatScore(row)}</span>
        </div>
      ))}
    </div>
  </section>

  <section className="workspace-panel">
    <div className="section-heading"><h2>Market Pulse</h2><span className="status-chip neutral">EOD</span></div>
    <div className="metric-row"><span>Market Assets</span><strong>{formatCount(marketMonitor?.coverage.market_assets)}</strong></div>
    <div className="metric-row"><span>Score Assets</span><strong>{formatCount(marketMonitor?.coverage.score_assets)}</strong></div>
    <div className="metric-row"><span>Factor Count</span><strong>{formatCount(marketMonitor?.coverage.factor_count)}</strong></div>
  </section>

  <section className="workspace-panel">
    <div className="section-heading"><h2>News Flow</h2><button type="button" onClick={() => onNavigate('news')}>Open</button></div>
    <div className="compact-news-list">
      {newsItems.map((item) => <span key={item.news_id}>{item.title}</span>)}
    </div>
  </section>
</section>

<section className="workspace-panel">
  <div className="section-heading"><h2>Strategy Health</h2><button type="button" onClick={() => onNavigate('strategyLab')}>Open Strategy Lab</button></div>
  <div className="strategy-card-grid">
    {strategies.slice(0, 4).map((strategy) => (
      <article className="strategy-summary-card" key={strategy.strategy_id}>
        <div className="strategy-card-header"><strong>{strategy.strategy_name}</strong></div>
        <p>{strategy.description}</p>
      </article>
    ))}
  </div>
</section>
```

Update `WorkspaceMode` in `HomeCockpit.tsx` to match AppShell:

```tsx
type WorkspaceMode =
  | 'market'
  | 'news'
  | 'researchReports'
  | 'stock'
  | 'watchlist'
  | 'factors'
  | 'strategyLab'
  | 'data'
  | 'generatedReports';
```

Update quick actions to the new labels.

- [ ] **Step 5: Run app-shell tests**

Run:

```bash
pnpm test -- --run tests/app-shell.test.tsx
```

Expected: pass.

- [ ] **Step 6: Commit Home redesign**

Run:

```bash
git add dashboard/src/components/HomeCockpit.tsx dashboard/tests/app-shell.test.tsx
git commit -m "feat: redesign research cockpit home"
```

---

### Task 7: Apply V2 Workstation Visual System

**Files:**

- Modify: `dashboard/src/styles.css`
- Modify test if needed: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Run existing frontend tests before style-only work**

Run:

```bash
pnpm test -- --run tests/app-shell.test.tsx
```

Expected: pass before style edits.

- [ ] **Step 2: Replace core shell styles**

Modify `dashboard/src/styles.css` core tokens and shell styles:

```css
:root {
  color: #17202a;
  background: #eef2f6;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 14px;
}

.platform-shell {
  display: grid;
  grid-template-columns: 216px minmax(0, 1fr);
  min-height: 100vh;
  background: #eef2f6;
  color: #17202a;
}

.platform-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  border-right: 1px solid #cfd8e3;
  background: #fbfcfe;
  padding: 12px;
}

.platform-nav button {
  min-height: 32px;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  color: #263241;
  padding: 6px 8px;
  text-align: left;
  font: inherit;
  cursor: pointer;
}

.platform-nav button.active {
  border-color: #2563eb;
  background: #eaf1ff;
  color: #174ea6;
  font-weight: 700;
}

.platform-workspace {
  min-width: 0;
  padding: 14px;
  overflow-x: clip;
}
```

- [ ] **Step 3: Add shared dense UI styles**

Append or replace equivalent styles:

```css
.workspace-stack {
  display: grid;
  gap: 12px;
}

.workspace-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.workspace-header h1 {
  margin: 0 0 3px;
  font-size: 22px;
  line-height: 1.15;
}

.workspace-panel {
  display: grid;
  gap: 8px;
  border: 1px solid #d7dee8;
  border-radius: 6px;
  background: #ffffff;
  padding: 10px;
}

.status-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1px;
  overflow: hidden;
  border: 1px solid #d7dee8;
  border-radius: 6px;
  background: #d7dee8;
}

.status-strip div {
  display: grid;
  gap: 2px;
  background: #ffffff;
  padding: 8px 10px;
}

.status-strip span,
.metric-row span {
  color: #667085;
  font-size: 12px;
}

.status-strip strong,
.metric-row strong {
  color: #17202a;
  font-size: 14px;
}

.status-chip {
  border: 1px solid #cfd8e3;
  border-radius: 999px;
  padding: 2px 7px;
  font-size: 12px;
  line-height: 1.4;
}

.status-chip.neutral {
  background: #f5f7fa;
  color: #475467;
}

.cockpit-layout {
  display: grid;
  grid-template-columns: minmax(260px, 1.15fr) minmax(220px, 0.85fr) minmax(260px, 1fr);
  gap: 12px;
}

.data-table {
  display: grid;
  border: 1px solid #edf1f5;
  border-radius: 5px;
  overflow: hidden;
}

.data-table-header,
.data-table-row {
  display: grid;
  gap: 8px;
  align-items: center;
  min-height: 30px;
  padding: 0 8px;
}

.data-table-header {
  background: #f6f8fb;
  color: #667085;
  font-size: 12px;
  font-weight: 700;
}

.data-table-row {
  border-top: 1px solid #edf1f5;
  background: #ffffff;
}

.three-col {
  grid-template-columns: 56px minmax(0, 1fr) 80px;
}

.metric-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  min-height: 28px;
  border-bottom: 1px solid #edf1f5;
}

.compact-news-list {
  display: grid;
  gap: 6px;
}

.compact-news-list span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.placeholder-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px;
}

.placeholder-grid span {
  border: 1px solid #edf1f5;
  border-radius: 5px;
  background: #f8fafc;
  padding: 8px;
  color: #475467;
}

.warning-text {
  margin: 0;
  color: #a15c00;
}
```

- [ ] **Step 4: Add responsive layout guardrails**

Append:

```css
@media (max-width: 980px) {
  .platform-shell {
    grid-template-columns: 1fr;
  }

  .platform-nav {
    position: sticky;
    top: 0;
    z-index: 2;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  }

  .cockpit-layout {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 5: Run frontend tests and build**

Run:

```bash
pnpm test -- --run tests/app-shell.test.tsx
pnpm build
```

Expected: tests pass and build succeeds.

- [ ] **Step 6: Commit UI style refresh**

Run:

```bash
git add dashboard/src/styles.css dashboard/tests/app-shell.test.tsx
git commit -m "style: apply research cockpit visual system"
```

---

### Task 8: Final Verification on Localhost

**Files:**

- No planned code changes.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_market_monitor.py tests/test_dashboard_app.py tests/test_public_news_backend.py -q
```

Expected: pass.

- [ ] **Step 2: Run frontend focused tests**

Run:

```bash
pnpm test -- --run tests/client.test.ts tests/app-shell.test.tsx
```

Expected: pass.

- [ ] **Step 3: Run frontend build**

Run:

```bash
pnpm build
```

Expected: `tsc && vite build` succeeds.

- [ ] **Step 4: Restart backend if needed**

If `8765` is still running old code, stop and restart it:

```bash
lsof -Pan -iTCP:8765 -sTCP:LISTEN
kill -TERM "$(lsof -tiTCP:8765 -sTCP:LISTEN)"
PYTHONPATH=/Users/xiwei/stock_research/.worktrees/strategy-validation-visualization/src /Users/xiwei/stock_research/.venv/bin/python -m uvicorn stock_research.dashboard.app:app --host 127.0.0.1 --port 8765 --http h11 --log-level info
```

Expected: backend listens on `127.0.0.1:8765`.

- [ ] **Step 5: Confirm API endpoints**

Run:

```bash
curl -sS 'http://127.0.0.1:5174/api/market-monitor/eod' | jq '{trade_date, realtime:.freshness.is_realtime, mode:.freshness.mode}'
curl -sS 'http://127.0.0.1:5174/api/public-news?limit=3' | jq '{count:(.items|length), warnings}'
```

Expected:

- market monitor returns `mode: "eod"` and `realtime: false`
- news returns JSON with `items`

- [ ] **Step 6: Manual browser check**

Open:

```text
http://127.0.0.1:5174/
```

Verify:

- Navigation includes `Market Monitor`, `Research Reports`, `Stock Workspace`, `Watchlist`, `Strategy Lab`, `Generated Reports`.
- Old `Reports` nav label is gone.
- Home shows `Today Focus`, `Market Pulse`, `News Flow`, `Strategy Health`.
- Market Monitor shows `Last Completed Trading Day` and does not imply realtime.
- News shows last-updated state and keeps rows visible during refresh failures.
- Generated Reports loads the existing local artifact browser.

- [ ] **Step 7: Final status check**

Run:

```bash
git status --short
```

Expected:

- No uncommitted files from this plan.
- Existing unrelated backtest changes may still appear if they were present before execution; mention them explicitly in the final response.

---

## Self-Review

Spec coverage:

- Home redesign: Task 6.
- Market Monitor EOD: Tasks 1, 2, 4.
- News auto-refresh: Task 5.
- Research Reports boundary: Task 3 placeholder.
- Stock Workspace boundary: Task 3 placeholder.
- Watchlist navigation/foundation: Task 3 placeholder.
- Strategy Lab merge: Task 3.
- Generated Reports rename: Task 3.
- UI style direction: Task 7.
- Verification: Task 8.

Intentional gaps for later phases:

- External research report adapter/store/API.
- Full Stock Workspace data integration.
- Watchlist queue persistence and editing.
- Global search.
- Real market breadth/sector strength source adapter.

Placeholder scan:

- Phase 1 placeholder pages are intentional product placeholders for future phases and contain explicit scope text.
- No implementation step contains unresolved `TBD` or undefined commands.

Type consistency:

- Backend route returns `MarketMonitorPayload` fields used by the frontend.
- `strategy_signal_summary.topn_preview` uses existing `ScoreRow`.
- `generated_reports` uses existing `ReportLink`.
