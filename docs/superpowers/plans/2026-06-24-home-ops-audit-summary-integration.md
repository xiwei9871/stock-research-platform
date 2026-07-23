# Home Ops Audit Summary Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate Ops Snapshot into the current `5174` home page and replace the old strategy-score warning block with a Chinese `运行审计摘要` that explains whether the current display trade date is trustworthy.

**Architecture:** Port the main-repo Ops Snapshot backend contract into the current `v0.1-local-eod-web` backend, expose three read-only APIs, then update the home cockpit to combine ops snapshot, readiness, and strategy score audit into one compact trust summary. Keep `Public Snapshot` as an independent `/public` route and public-only build target rather than merging it into the internal home page body.

**Tech Stack:** FastAPI, Python, React, TypeScript, Vite, Vitest, pytest

---

### Task 1: Port Ops Snapshot backend contract into the current branch

**Files:**
- Create: `src/stock_research/dashboard/ops_snapshot.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_ops_snapshot.py`
- Test: `tests/test_dashboard_app.py`

- [ ] **Step 1: Write failing backend tests for ops snapshot builders**

Create `tests/test_dashboard_ops_snapshot.py` with focused tests that prove:
- internal snapshot returns `run_window`, `pipeline`, `health`, `intervention`, `readiness`, `snapshot_preview`
- public snapshot returns only release-safe fields
- stage loader returns normalized items

```python
from datetime import date

from stock_research.dashboard.ops_snapshot import (
    build_internal_ops_snapshot,
    build_public_snapshot,
)


def test_build_internal_ops_snapshot_shapes_payload(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._load_pipeline_status_context",
        lambda service, trade_date: {
            "data_status": {
                "latest_ready_trade_date": "2026-06-23",
                "current_trade_date": "2026-06-23",
                "pipeline_status": "READY",
                "daily_status": "success",
                "minute5_status": "success",
                "deps_status": "success",
                "failed_jobs": [],
                "warnings": [],
                "last_updated_at": "2026-06-23T20:43:10+08:00",
            },
            "requested_trade_date": "2026-06-23",
            "status_trade_date": "2026-06-23",
            "latest_available_trade_date": "2026-06-23",
            "matches_requested_trade_date": True,
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_intraday_status",
        lambda service, trade_date: {"market_state": {"state": "warm", "score": 74.2}},
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.summarize_operational_health",
        lambda trade_date, service: {"status": "ok", "alert_count": 0, "last_error_summary": None},
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_ops_stage_details",
        lambda service, trade_date: [{"stage": "daily", "status": "success", "started_at": None, "updated_at": None, "error_summary": None}],
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._now_in_timezone",
        lambda timezone_name: "2026-06-24T10:00:00+08:00",
    )

    payload = build_internal_ops_snapshot("stock_research", trade_date=date(2026, 6, 23))

    assert sorted(payload.keys()) == ["health", "intervention", "pipeline", "readiness", "run_window", "snapshot_preview"]
    assert payload["pipeline"]["overall_status"] == "ready"
    assert payload["readiness"]["ready_status"] == "ready"


def test_build_public_snapshot_uses_release_safe_shape(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.build_internal_ops_snapshot",
        lambda service="stock_research", trade_date=None: {
            "readiness": {"latest_ready_trade_date": "2026-06-23", "ready_for_publication": True, "ready_status": "ready"},
            "snapshot_preview": {
                "market_state": {"state": "warm", "score": 74.2, "internal_reason": "hidden"},
                "topn_preview": [{"asset_id": "000001.SZ", "stock_name": "平安银行", "score_total": 88.5, "debug": "drop"}],
                "coverage_summary": {"core": "daily/minute ready", "internal": "drop"},
                "factor_gate_summary": {"approved_count": 5, "raw_count": 30},
                "published_at": "2026-06-23T20:43:10+08:00",
            },
        },
    )

    payload = build_public_snapshot("stock_research", trade_date=date(2026, 6, 23))

    assert sorted(payload.keys()) == [
        "coverage_summary",
        "factor_gate_summary",
        "latest_ready_trade_date",
        "market_state",
        "notes",
        "published_at",
        "status",
        "status_text",
        "topn_preview",
        "trade_date",
    ]
    assert payload["market_state"] == {"state": "warm", "score": 74.2}
    assert payload["topn_preview"] == [{"asset_id": "000001.SZ", "stock_name": "平安银行", "score_total": 88.5}]
```

- [ ] **Step 2: Run backend test target to verify failure**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_ops_snapshot.py -q
```

Expected: FAIL with `ModuleNotFoundError` or import failure because `stock_research.dashboard.ops_snapshot` does not exist yet in this branch.

- [ ] **Step 3: Copy and adapt the ops snapshot backend module**

Create `src/stock_research/dashboard/ops_snapshot.py` by porting the main-repo builder, keeping the same public functions:

```python
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from stock_research.config import SETTINGS
from stock_research.daily_health import summarize_operational_health
from stock_research.db import connect, fetch_all
from stock_research.intraday_pipeline import load_intraday_status


def build_internal_ops_snapshot(
    service: str = SETTINGS.research_service,
    trade_date: date | None = None,
) -> dict[str, Any]:
    ...


def build_public_snapshot(
    service: str = SETTINGS.research_service,
    trade_date: date | None = None,
) -> dict[str, Any]:
    ...


def load_ops_stage_details(
    service: str = SETTINGS.research_service,
    trade_date: date | None = None,
) -> list[dict[str, Any]]:
    ...
```

Port the helper functions from the main repository too:

```python
def _load_pipeline_status_context(service: str, trade_date: date) -> dict[str, Any]:
    ...


def _build_pipeline_summary(
    data_status: dict[str, Any],
    stages: list[dict[str, Any]],
    now_text: str,
    status_context: dict[str, Any],
) -> dict[str, Any]:
    ...


def _build_readiness(
    data_status: dict[str, Any],
    health_block: dict[str, Any],
    pipeline: dict[str, Any],
    status_context: dict[str, Any],
) -> dict[str, Any]:
    ...
```

Keep the allow-list behavior for public payload:

```python
_PUBLIC_COVERAGE_SUMMARY_KEYS = ("core",)
_PUBLIC_MARKET_STATE_KEYS = ("state", "score")
_PUBLIC_TOPN_PREVIEW_KEYS = ("asset_id", "stock_name", "score_total")
_PUBLIC_FACTOR_GATE_SUMMARY_KEYS = ("approved_count",)
```

- [ ] **Step 4: Add the three routes to the current dashboard API**

Modify `src/stock_research/dashboard/app.py` imports:

```python
from stock_research.dashboard.ops_snapshot import (
    build_internal_ops_snapshot,
    build_public_snapshot,
    load_ops_stage_details,
)
```

Add routes near the platform/display-date area:

```python
from stock_research.intraday_pipeline import IntradayConfig, parse_trade_date


def _resolve_dashboard_trade_date(raw_date: str | None):
    config = IntradayConfig.from_env()
    return parse_trade_date(raw_date, config.timezone)


@app.get("/api/ops/snapshot")
def ops_snapshot(date: str | None = None):
    return build_internal_ops_snapshot(trade_date=_resolve_dashboard_trade_date(date))


@app.get("/api/ops/stages")
def ops_stages(date: str | None = None):
    return {"items": load_ops_stage_details(trade_date=_resolve_dashboard_trade_date(date))}


@app.get("/api/public/snapshot")
def public_snapshot():
    return build_public_snapshot()
```

- [ ] **Step 5: Add route tests**

Append focused tests to `tests/test_dashboard_app.py`:

```python
def test_ops_snapshot_route_returns_aggregated_payload(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "build_internal_ops_snapshot",
        lambda trade_date=None: {"pipeline": {"overall_status": "ready"}, "readiness": {"ready_status": "ready"}},
    )
    client = TestClient(dashboard_app.create_app())
    response = client.get("/api/ops/snapshot")
    assert response.status_code == 200
    assert response.json()["pipeline"]["overall_status"] == "ready"


def test_ops_stages_route_returns_stage_list(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "load_ops_stage_details",
        lambda trade_date=None: [{"stage": "daily", "status": "success"}],
    )
    client = TestClient(dashboard_app.create_app())
    response = client.get("/api/ops/stages")
    assert response.status_code == 200
    assert response.json()["items"][0]["stage"] == "daily"


def test_public_snapshot_route_returns_public_payload(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "build_public_snapshot",
        lambda: {"trade_date": "2026-06-23", "status": "ready", "status_text": "ready"},
    )
    client = TestClient(dashboard_app.create_app())
    response = client.get("/api/public/snapshot")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
```

- [ ] **Step 6: Run backend tests to verify pass**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_ops_snapshot.py tests/test_dashboard_app.py -k "ops_snapshot or public_snapshot or ops_stages" -q
```

Expected: PASS

- [ ] **Step 7: Commit backend port**

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
git add src/stock_research/dashboard/ops_snapshot.py src/stock_research/dashboard/app.py tests/test_dashboard_ops_snapshot.py tests/test_dashboard_app.py
git commit -m "feat: port ops snapshot APIs into local dashboard branch"
```

### Task 2: Add client/types support for ops and public snapshot

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Test: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Write failing client tests**

Append tests to `dashboard/tests/client.test.ts`:

```ts
it('fetches ops snapshot from the internal ops endpoint', async () => {
  fetchMock.mockResolvedValueOnce(
    new Response(JSON.stringify({ pipeline: { overall_status: 'ready' }, readiness: { ready_status: 'ready' } }))
  );

  const result = await fetchOpsSnapshot();

  expect(fetchMock).toHaveBeenCalledWith('/api/ops/snapshot');
  expect(result.pipeline.overall_status).toBe('ready');
});

it('fetches ops stages rows from the internal ops endpoint', async () => {
  fetchMock.mockResolvedValueOnce(
    new Response(JSON.stringify({ items: [{ stage: 'daily', status: 'success' }] }))
  );

  const result = await fetchOpsStages();

  expect(fetchMock).toHaveBeenCalledWith('/api/ops/stages');
  expect(result[0].stage).toBe('daily');
});

it('fetches public snapshot from the release-safe endpoint', async () => {
  fetchMock.mockResolvedValueOnce(
    new Response(JSON.stringify({ trade_date: '2026-06-23', status: 'ready', status_text: 'ready', latest_ready_trade_date: '2026-06-23', published_at: null, market_state: {}, topn_preview: [], coverage_summary: {}, factor_gate_summary: {}, notes: [] }))
  );

  const result = await fetchPublicSnapshot();

  expect(fetchMock).toHaveBeenCalledWith('/api/public/snapshot');
  expect(result.trade_date).toBe('2026-06-23');
});
```

- [ ] **Step 2: Run targeted client tests to verify failure**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- --run tests/client.test.ts
```

Expected: FAIL because `fetchOpsSnapshot`, `fetchOpsStages`, and `fetchPublicSnapshot` are not defined yet.

- [ ] **Step 3: Add API types**

Append to `dashboard/src/api/types.ts`:

```ts
export type OpsStageRow = {
  stage: string;
  status: string;
  started_at: string | null;
  updated_at: string | null;
  error_summary: string | null;
};

export type OpsSnapshot = {
  run_window: {
    requested_trade_date: string;
    trade_date: string;
    status_trade_date: string | null;
    latest_available_trade_date: string | null;
    status_matches_requested_trade_date: boolean;
    current_trade_date: string | null;
    latest_ready_trade_date: string | null;
    last_updated_at: string | null;
    now: string;
    stage_count: number;
  };
  pipeline: {
    overall_status: string;
    pipeline_status: string;
    daily_status: string | null;
    minute5_status: string | null;
    deps_status: string | null;
    latest_ready_trade_date: string | null;
    last_updated_at: string | null;
    evaluated_at: string;
    stage_statuses: string[];
  };
  health: Record<string, unknown>;
  intervention: {
    severity: string;
    needs_intervention: boolean;
    reason_text: string;
    suggested_action?: string | null;
  };
  readiness: {
    ready_status: string;
    latest_ready_trade_date: string | null;
    ready_for_dashboard: boolean;
    ready_for_publication: boolean;
    blocking_issue_count: number;
  };
  snapshot_preview: {
    market_state: Record<string, unknown>;
    topn_preview: Array<Record<string, unknown>>;
    coverage_summary: Record<string, unknown>;
    factor_gate_summary: Record<string, unknown>;
    published_at: string | null;
  };
};

export type PublicSnapshot = {
  trade_date: string;
  published_at: string | null;
  latest_ready_trade_date: string | null;
  status: string;
  status_text: string;
  market_state: Record<string, unknown>;
  topn_preview: Array<Record<string, unknown>>;
  coverage_summary: Record<string, unknown>;
  factor_gate_summary: Record<string, unknown>;
  notes: string[];
};
```

- [ ] **Step 4: Add client fetchers**

Modify `dashboard/src/api/client.ts`:

```ts
import type { OpsSnapshot, OpsStageRow, PublicSnapshot } from './types';

export async function fetchPublicSnapshot(): Promise<PublicSnapshot> {
  return getJson('/api/public/snapshot');
}

export async function fetchOpsSnapshot(): Promise<OpsSnapshot> {
  return getJson('/api/ops/snapshot');
}

export async function fetchOpsStages(): Promise<OpsStageRow[]> {
  const payload = await getJson<{ items: OpsStageRow[] }>('/api/ops/stages');
  return payload.items;
}
```

- [ ] **Step 5: Re-run client tests**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- --run tests/client.test.ts
```

Expected: PASS

- [ ] **Step 6: Commit client contract changes**

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
git add dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/tests/client.test.ts
git commit -m "feat: add ops snapshot client contracts"
```

### Task 3: Keep `/public` support and public-only build parity

**Files:**
- Create: `dashboard/src/components/PublicSnapshotPage.tsx`
- Create: `dashboard/src/public-main.tsx`
- Create: `dashboard/public.html`
- Modify: `dashboard/src/main.tsx`
- Modify: `dashboard/vite.config.ts`
- Test: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Write failing app-shell tests for `/public`**

Append tests to `dashboard/tests/app-shell.test.tsx`:

```tsx
it('renders the public page from main.tsx when the route is /public', async () => {
  vi.resetModules();
  window.history.pushState({}, '', '/public');
  document.body.innerHTML = '<div id="root"></div>';

  vi.doMock('../src/App', () => ({ App: () => <div>internal app shell</div> }));
  vi.doMock('../src/components/PublicSnapshotPage', () => ({
    PublicSnapshotPage: () => <div>public snapshot route</div>
  }));

  await import('../src/main');

  await waitFor(() => {
    expect(screen.getByText('public snapshot route')).toBeInTheDocument();
  });
});

it('renders the public page from public-main.tsx on a non-public path', async () => {
  vi.resetModules();
  window.history.pushState({}, '', '/ops');
  document.body.innerHTML = '<div id="root"></div>';

  vi.doMock('../src/components/PublicSnapshotPage', () => ({
    PublicSnapshotPage: () => <div>public snapshot route</div>
  }));

  await import('../src/public-main');

  await waitFor(() => {
    expect(screen.getByText('public snapshot route')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run app-shell tests to verify failure**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- --run tests/app-shell.test.tsx
```

Expected: FAIL because `PublicSnapshotPage`, `public-main.tsx`, or route switching does not exist yet.

- [ ] **Step 3: Add public route/page and public-only build switch**

Create `dashboard/src/components/PublicSnapshotPage.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { fetchPublicSnapshot } from '../api/client';
import type { PublicSnapshot } from '../api/types';

export function PublicSnapshotPage() {
  const [snapshot, setSnapshot] = useState<PublicSnapshot | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchPublicSnapshot()
      .then((payload) => {
        if (!cancelled) {
          setSnapshot(payload);
          setLoadFailed(false);
        }
      })
      .catch(() => {
        if (!cancelled) setLoadFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loadFailed) return <main className="public-shell">Public snapshot unavailable</main>;
  if (!snapshot) return <main className="public-shell">Loading public snapshot...</main>;
  return <main className="public-shell"><h1>Daily A-share Snapshot</h1><p>{snapshot.status_text}</p></main>;
}
```

Modify `dashboard/src/main.tsx`:

```tsx
import { App } from './App';
import { PublicSnapshotPage } from './components/PublicSnapshotPage';
import './styles.css';

const path = window.location.pathname.replace(/\/+$/, '') || '/';

root.render(
  <React.StrictMode>
    {path === '/public' ? <PublicSnapshotPage /> : <App />}
  </React.StrictMode>
);
```

Create `dashboard/src/public-main.tsx`:

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { PublicSnapshotPage } from './components/PublicSnapshotPage';
import './styles.css';

const root = ReactDOM.createRoot(document.getElementById('root') as HTMLElement);
root.render(
  <React.StrictMode>
    <PublicSnapshotPage />
  </React.StrictMode>
);
```

Create `dashboard/public.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Public Snapshot</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/public-main.tsx"></script>
  </body>
</html>
```

Modify `dashboard/vite.config.ts`:

```ts
const publicSnapshotOnly =
  String(runtime.process?.env?.VITE_PUBLIC_SNAPSHOT_ONLY ?? '').toLowerCase() === 'true';
const buildInput = new URL(publicSnapshotOnly ? './public.html' : './index.html', import.meta.url).pathname;

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: buildInput,
    },
  },
  ...
});
```

- [ ] **Step 4: Run route/build tests**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- --run tests/app-shell.test.tsx
pnpm build
VITE_PUBLIC_SNAPSHOT_ONLY=true pnpm build
```

Expected:
- tests PASS
- normal build emits `dist/index.html`
- public-only build emits `dist/public.html`

- [ ] **Step 5: Commit public route/build parity**

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
git add dashboard/src/components/PublicSnapshotPage.tsx dashboard/src/public-main.tsx dashboard/public.html dashboard/src/main.tsx dashboard/vite.config.ts dashboard/tests/app-shell.test.tsx
git commit -m "feat: keep public snapshot route and build parity"
```

### Task 4: Replace the old home audit panel with `运行审计摘要`

**Files:**
- Modify: `dashboard/src/components/HomeCockpit.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/home-cockpit-score-audit.test.tsx`
- Test: `dashboard/tests/home-cockpit.test.tsx`

- [ ] **Step 1: Write failing home cockpit tests**

Update `dashboard/tests/home-cockpit-score-audit.test.tsx` to replace the current panel expectation with the new summary:

```tsx
it('shows a Chinese running audit summary instead of the old strategy score action panel', async () => {
  apiMocks.fetchStrategyScoreAudit.mockResolvedValue({
    trade_date: '2026-06-23',
    status: 'success',
    overall_status: 'warning',
    anomaly_row_count: 8,
    anomaly_counts_by_type: { mapped_score_without_raw_score: 5, stale_source: 3 },
    strategies: [
      { strategy_id: 'lhb_shortline', anomaly_count: 5, row_count: 5, selected_count: 5 },
      { strategy_id: 'mid_trend', anomaly_count: 3, row_count: 5, selected_count: 5 },
      { strategy_id: 'tech_bottleneck', anomaly_count: 0, row_count: 5, selected_count: 5 },
    ],
    sample_rows: [],
  });

  render(<HomeCockpit onNavigate={vi.fn()} />);

  const panel = await screen.findByRole('region', { name: '运行审计摘要' });
  expect(within(panel).getByText('评分链路')).toBeInTheDocument();
  expect(within(panel).getByText(/LHB 原始分缺失 5 条/)).toBeInTheDocument();
  expect(within(panel).getByText(/Mid Trend 来源过期 3 条/)).toBeInTheDocument();
  expect(screen.queryByRole('region', { name: '策略打分审计处理建议' })).not.toBeInTheDocument();
  expect(screen.queryByText('000070.SZ')).not.toBeInTheDocument();
});
```

Add a new integration-style test in `dashboard/tests/home-cockpit.test.tsx` for ops summary text:

```tsx
it('summarizes ops-backed trust signals for the display trade date', async () => {
  apiMocks.fetchOpsSnapshot.mockResolvedValue({
    run_window: { requested_trade_date: '2026-06-23', trade_date: '2026-06-23', status_trade_date: '2026-06-23', latest_available_trade_date: '2026-06-23', status_matches_requested_trade_date: true, current_trade_date: '2026-06-23', latest_ready_trade_date: '2026-06-23', last_updated_at: '2026-06-23T20:43:10+08:00', now: '2026-06-24T10:00:00+08:00', stage_count: 3 },
    pipeline: { overall_status: 'ready', pipeline_status: 'READY', daily_status: 'success', minute5_status: 'success', deps_status: 'success', latest_ready_trade_date: '2026-06-23', last_updated_at: '2026-06-23T20:43:10+08:00', evaluated_at: '2026-06-24T10:00:00+08:00', stage_statuses: ['success'] },
    health: {},
    intervention: { severity: 'normal', needs_intervention: false, reason_text: '无需人工介入', suggested_action: null },
    readiness: { ready_status: 'ready', latest_ready_trade_date: '2026-06-23', ready_for_dashboard: true, ready_for_publication: true, blocking_issue_count: 0 },
    snapshot_preview: { market_state: {}, topn_preview: [], coverage_summary: {}, factor_gate_summary: {}, published_at: '2026-06-23T20:43:10+08:00' },
  });

  render(<HomeCockpit onNavigate={vi.fn()} />);

  const panel = await screen.findByRole('region', { name: '运行审计摘要' });
  expect(within(panel).getByText(/运行状态/)).toBeInTheDocument();
  expect(within(panel).getByText(/正常/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run home cockpit tests to verify failure**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- --run tests/home-cockpit-score-audit.test.tsx tests/home-cockpit.test.tsx
```

Expected: FAIL because the old audit action panel is still rendered and ops snapshot is not loaded by the home cockpit.

- [ ] **Step 3: Add ops snapshot client usage and derived audit-summary helpers**

Modify `dashboard/src/components/HomeCockpit.tsx` imports:

```tsx
import {
  fetchBacktestStrategies,
  fetchMarketMonitorEod,
  fetchOpsSnapshot,
  fetchPlatformReadiness,
  fetchPlatformSummary,
  fetchPublicNews,
  fetchStrategyScoreAudit,
} from '../api/client';

import type { OpsSnapshot } from '../api/types';
```

Add state:

```tsx
const [opsSnapshot, setOpsSnapshot] = useState<OpsSnapshot | null>(null);
const [opsSnapshotError, setOpsSnapshotError] = useState<string | null>(null);
```

Add loader alongside existing readiness/audit requests:

```tsx
useEffect(() => {
  let cancelled = false;
  setOpsSnapshotError(null);
  void fetchOpsSnapshot().then(
    (payload) => {
      if (!cancelled) setOpsSnapshot(payload);
    },
    (err: unknown) => {
      if (!cancelled) {
        setOpsSnapshot(null);
        setOpsSnapshotError(errorMessage(err));
      }
    },
  );
  return () => {
    cancelled = true;
  };
}, [displayTradeDate]);
```

Add summary builder helpers:

```tsx
type AuditSummaryRow = {
  key: string;
  label: string;
  status: 'ready' | 'partial' | 'blocked';
  summary: string;
};

function buildRunningAuditRows(
  readiness: PlatformReadiness | null,
  audit: StrategyScoreAuditSummary | null,
  opsSnapshot: OpsSnapshot | null,
): AuditSummaryRow[] {
  return [
    buildFoundationAuditRow(readiness, opsSnapshot),
    buildScoreLineageRow(audit),
    buildStrategyExecutionRow(readiness),
    buildReviewArtifactRow(readiness),
    buildContentChainRow(readiness),
  ];
}
```

Make score-line summary roll up by anomaly type:

```tsx
function buildScoreLineageRow(audit: StrategyScoreAuditSummary | null): AuditSummaryRow {
  if (!audit) return { key: 'score', label: '评分链路', status: 'partial', summary: '审计结果读取中。' };
  if (audit.overall_status === 'ok') return { key: 'score', label: '评分链路', status: 'ready', summary: '评分链路正常。' };

  const mapped = audit.anomaly_counts_by_type?.mapped_score_without_raw_score ?? 0;
  const stale = audit.anomaly_counts_by_type?.stale_source ?? 0;
  const parts: string[] = [];
  if (mapped > 0) parts.push(`LHB 原始分缺失 ${mapped} 条`);
  if (stale > 0) parts.push(`Mid Trend 来源过期 ${stale} 条`);
  return {
    key: 'score',
    label: '评分链路',
    status: 'partial',
    summary: `${parts.join('，')}，今日分数可看但可信度下降。`,
  };
}
```

- [ ] **Step 4: Replace the old panel markup with the new summary region**

In `dashboard/src/components/HomeCockpit.tsx`, remove the old block:

```tsx
{scoreAudit?.overall_status === 'warning' ? (
  <section className="workspace-panel audit-action-panel" aria-label="策略打分审计处理建议">
    ...
  </section>
) : null}
```

Replace with:

```tsx
<section className="workspace-panel audit-summary-panel" aria-label="运行审计摘要">
  <div className="section-heading">
    <div>
      <h2>运行审计摘要</h2>
      <p className="muted">按当前展示日期汇总基础行情、评分链路、策略执行、复盘产物和内容链路状态。</p>
    </div>
    <span className={`status-chip ${opsSnapshotError ? 'warning' : 'neutral'}`}>
      {opsSnapshotError ? '需关注' : '摘要'}
    </span>
  </div>
  <div className="audit-summary-grid">
    {buildRunningAuditRows(readiness, scoreAudit, opsSnapshot).map((row) => (
      <article className="audit-summary-card" key={row.key}>
        <div className="audit-summary-card-head">
          <span>{row.label}</span>
          <span className={`status-chip ${row.status === 'ready' ? 'ready' : row.status === 'blocked' ? 'blocked' : 'warning'}`}>
            {row.status === 'ready' ? '正常' : row.status === 'blocked' ? '阻塞' : '需关注'}
          </span>
        </div>
        <p>{row.summary}</p>
      </article>
    ))}
  </div>
  <div className="compact-toolbar">
    <button type="button" onClick={() => document.getElementById('health-check-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
      查看健康检查
    </button>
    <button type="button" onClick={() => onNavigate('generatedReports')}>
      查看审计明细
    </button>
  </div>
</section>
```

Give the health-check section a stable id:

```tsx
<section className="workspace-panel health-check-panel" id="health-check-panel" aria-label="平台健康检查">
```

- [ ] **Step 5: Add styles for the new summary cards**

Append to `dashboard/src/styles.css`:

```css
.audit-summary-panel {
  display: grid;
  gap: 12px;
}

.audit-summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.audit-summary-card {
  border: 1px solid var(--border-color, #d8e1ef);
  border-radius: 8px;
  padding: 12px;
  background: #fff;
}

.audit-summary-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.audit-summary-card p {
  margin: 0;
  color: #516079;
  line-height: 1.5;
}
```

- [ ] **Step 6: Re-run home cockpit tests**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- --run tests/home-cockpit-score-audit.test.tsx tests/home-cockpit.test.tsx
```

Expected: PASS

- [ ] **Step 7: Commit home audit summary integration**

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
git add dashboard/src/components/HomeCockpit.tsx dashboard/src/styles.css dashboard/tests/home-cockpit-score-audit.test.tsx dashboard/tests/home-cockpit.test.tsx
git commit -m "feat: replace score action panel with home audit summary"
```

### Task 5: Run full branch verification and local browser validation

**Files:**
- Modify if needed after verification fallout:
  - `dashboard/src/components/HomeCockpit.tsx`
  - `src/stock_research/dashboard/app.py`
  - `dashboard/src/api/client.ts`
  - tests touched above

- [ ] **Step 1: Run backend verification suite**

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_ops_snapshot.py tests/test_dashboard_app.py -k "ops_snapshot or public_snapshot or ops_stages" -q
```

Expected: PASS

- [ ] **Step 2: Run frontend verification suite**

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm test -- --run tests/client.test.ts tests/app-shell.test.tsx tests/home-cockpit-score-audit.test.tsx tests/home-cockpit.test.tsx
pnpm build
VITE_PUBLIC_SNAPSHOT_ONLY=true pnpm build
```

Expected:
- Vitest PASS
- normal build success
- public-only build success with `dist/public.html`

- [ ] **Step 3: Start local services for manual validation**

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli dashboard-api --host 127.0.0.1 --port 8765
```

In another terminal:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/dashboard
pnpm dev
```

- [ ] **Step 4: Verify home page behavior in the browser**

Manual checks at `http://127.0.0.1:5174/`:

- top-line status row still visible
- `运行审计摘要` is visible
- old `策略打分审计处理建议` region is gone
- no sample anomaly stock rows shown in the summary
- `查看健康检查` scrolls to the health section
- summary reflects current display date anomalies in Chinese

- [ ] **Step 5: Verify public route**

Open:

```bash
http://127.0.0.1:5174/public
```

Check:
- page loads `PublicSnapshotPage`
- no internal app shell is rendered
- text is release-safe only

- [ ] **Step 6: Final integration commit**

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
git add src/stock_research/dashboard/ops_snapshot.py src/stock_research/dashboard/app.py tests/test_dashboard_ops_snapshot.py tests/test_dashboard_app.py dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/src/components/PublicSnapshotPage.tsx dashboard/src/public-main.tsx dashboard/public.html dashboard/src/main.tsx dashboard/vite.config.ts dashboard/src/components/HomeCockpit.tsx dashboard/src/styles.css dashboard/tests/client.test.ts dashboard/tests/app-shell.test.tsx dashboard/tests/home-cockpit-score-audit.test.tsx dashboard/tests/home-cockpit.test.tsx
git commit -m "feat: integrate ops snapshot and home audit summary"
```

---

## Self-Review

### Spec coverage

- Ops Snapshot backend integration: Task 1
- Public Snapshot route/build separation: Tasks 1, 2, 3
- Home-page `运行审计摘要`: Task 4
- Removal of old action-style audit block: Task 4
- Verification of browser/build behavior: Task 5

No spec gaps found.

### Placeholder scan

Search terms reviewed:
- `TBD`
- `TODO`
- `implement later`
- `appropriate error handling`
- `similar to`

No placeholder content intentionally left in the plan.

### Type consistency

The plan uses consistent names across tasks:
- `OpsSnapshot`
- `OpsStageRow`
- `PublicSnapshot`
- `fetchOpsSnapshot`
- `fetchOpsStages`
- `fetchPublicSnapshot`
- `运行审计摘要`

No cross-task naming conflict found.
