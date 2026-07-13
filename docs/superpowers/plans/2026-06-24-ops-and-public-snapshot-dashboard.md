# Ops And Public Snapshot Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal browser-visible internal operations page and public snapshot page so the operator can see workflow status, intervention need, latest ready trade date, and released daily summary without reading logs or database tables directly.

**Architecture:** Reuse the existing FastAPI dashboard backend and React dashboard frontend. Add one backend aggregation module that converts existing pipeline, health, and dashboard summary sources into two stable read models, then add three API endpoints plus one internal and one public UI surface that consume only those read models.

**Tech Stack:** Python 3.11, FastAPI, existing `stock_research.dashboard` modules, pytest, React 19, TypeScript, Vitest, pnpm

---

## File Map

- `/Users/xiwei/stock_research/src/stock_research/dashboard/ops_snapshot.py`
  - New backend aggregation module for internal and public snapshots plus stage details.
- `/Users/xiwei/stock_research/src/stock_research/dashboard/app.py`
  - Add three read-only routes for ops snapshot, ops stages, and public snapshot.
- `/Users/xiwei/stock_research/tests/test_dashboard_ops_snapshot.py`
  - New backend unit tests for aggregation and rule evaluation.
- `/Users/xiwei/stock_research/tests/test_dashboard_app.py`
  - Add API route coverage for the new endpoints.
- `/Users/xiwei/stock_research/dashboard/src/api/types.ts`
  - Add TypeScript types for the new snapshot payloads.
- `/Users/xiwei/stock_research/dashboard/src/api/client.ts`
  - Add fetch helpers for the new APIs.
- `/Users/xiwei/stock_research/dashboard/src/components/OpsSnapshotPanel.tsx`
  - New internal operations summary panel.
- `/Users/xiwei/stock_research/dashboard/src/components/OpsStagesPanel.tsx`
  - New internal stage timeline panel.
- `/Users/xiwei/stock_research/dashboard/src/components/PublicSnapshotPage.tsx`
  - New public read-only page component.
- `/Users/xiwei/stock_research/dashboard/src/App.tsx`
  - Add internal page layout and fetch lifecycle for ops snapshot data.
- `/Users/xiwei/stock_research/dashboard/src/main.tsx`
  - Select internal app or public page by pathname.
- `/Users/xiwei/stock_research/dashboard/src/styles.css`
  - Add intentional styles for the new panels and public page.
- `/Users/xiwei/stock_research/dashboard/tests/client.test.ts`
  - Add client-side request tests.
- `/Users/xiwei/stock_research/dashboard/tests/app-shell.test.tsx`
  - Add render tests for internal and public views.
- `/Users/xiwei/stock_research/docs/dashboard-ops-snapshot-runbook.md`
  - New operator-facing runbook for routes, meanings, and escalation handling.
- `/Users/xiwei/stock_research/tests/test_dashboard_app.py`
  - Extend existing dashboard API coverage with a lightweight runbook existence assertion.

### Task 1: Build The Backend Snapshot Aggregator

**Files:**
- Create: `/Users/xiwei/stock_research/src/stock_research/dashboard/ops_snapshot.py`
- Create: `/Users/xiwei/stock_research/tests/test_dashboard_ops_snapshot.py`

- [ ] **Step 1: Write the failing backend aggregation tests**

```python
from datetime import date

from stock_research.dashboard.ops_snapshot import (
    build_internal_ops_snapshot,
    build_public_snapshot,
)


def test_build_internal_ops_snapshot_marks_not_started_as_critical(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_data_status_for_dashboard",
        lambda service, current_trade_date=None: {
            "latest_ready_trade_date": "2026-06-23",
            "current_trade_date": "2026-06-24",
            "pipeline_status": "NOT_READY",
            "daily_status": "pending",
            "minute5_status": "pending",
            "deps_status": "pending",
            "failed_jobs": [],
            "warnings": [],
            "last_updated_at": "2026-06-24T03:40:00+08:00",
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_intraday_status",
        lambda service, run_date: {
            "run_date": "2026-06-24",
            "jobs": [],
            "universe_count": 0,
            "universe": [],
            "market_sentiment": None,
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.summarize_operational_health",
        lambda **kwargs: {
            "trade_date": "2026-06-24",
            "status": "ok",
            "alert_count": 0,
            "ingest": {},
            "stale_ingest": {},
            "backfill": {},
            "stale_backfill": {},
            "daily_jobs": [],
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_ops_stage_details",
        lambda service, trade_date=None: [],
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._now_in_timezone",
        lambda tz_name: "2026-06-24T04:20:00+08:00",
    )

    snapshot = build_internal_ops_snapshot("stock_research", trade_date=date(2026, 6, 24))

    assert snapshot["intervention"]["needs_intervention"] is True
    assert snapshot["intervention"]["severity"] == "critical"
    assert snapshot["intervention"]["reason_code"] == "not_started"


def test_build_internal_ops_snapshot_marks_delayed_but_progressing_as_warning(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_data_status_for_dashboard",
        lambda service, current_trade_date=None: {
            "latest_ready_trade_date": "2026-06-23",
            "current_trade_date": "2026-06-24",
            "pipeline_status": "NOT_READY",
            "daily_status": "running",
            "minute5_status": "running",
            "deps_status": "pending",
            "failed_jobs": [],
            "warnings": [],
            "last_updated_at": "2026-06-24T08:06:00+08:00",
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_intraday_status",
        lambda service, run_date: {
            "run_date": "2026-06-24",
            "jobs": [],
            "universe_count": 0,
            "universe": [],
            "market_sentiment": {"sentiment_state": "neutral", "sentiment_score": 0.11},
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.summarize_operational_health",
        lambda **kwargs: {
            "trade_date": "2026-06-24",
            "status": "ok",
            "alert_count": 0,
            "ingest": {},
            "stale_ingest": {},
            "backfill": {},
            "stale_backfill": {},
            "daily_jobs": [],
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.load_ops_stage_details",
        lambda service, trade_date=None: [
            {
                "stage": "minute5",
                "status": "running",
                "started_at": "2026-06-24T07:10:00+08:00",
                "updated_at": "2026-06-24T08:06:00+08:00",
                "error_summary": None,
            }
        ],
    )
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot._now_in_timezone",
        lambda tz_name: "2026-06-24T08:10:00+08:00",
    )

    snapshot = build_internal_ops_snapshot("stock_research", trade_date=date(2026, 6, 24))

    assert snapshot["pipeline"]["overall_status"] == "delayed"
    assert snapshot["intervention"]["needs_intervention"] is True
    assert snapshot["intervention"]["severity"] == "warning"
    assert snapshot["health"]["stalled"] is False


def test_build_public_snapshot_hides_internal_errors_and_uses_release_status(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.ops_snapshot.build_internal_ops_snapshot",
        lambda service, trade_date=None: {
            "run_window": {},
            "pipeline": {"overall_status": "delayed"},
            "health": {"last_error_summary": "source timeout"},
            "intervention": {
                "needs_intervention": True,
                "severity": "warning",
                "reason_code": "deadline_risk",
                "reason_text": "deadline risk",
                "suggested_action": "check watchdog",
            },
            "readiness": {
                "latest_ready_trade_date": "2026-06-23",
                "ready_status": "degraded_ready",
                "ready_for_dashboard": True,
                "ready_for_publication": True,
                "blocking_issue_count": 0,
            },
            "snapshot_preview": {
                "market_state": {"state": "neutral"},
                "topn_preview": [{"asset_id": "000001.SZ", "stock_name": "Ping An Bank"}],
                "coverage_summary": {"core": "97.8%"},
                "factor_gate_summary": {"approved_count": 12},
                "published_at": "2026-06-24T08:12:00+08:00",
            },
        },
    )

    snapshot = build_public_snapshot("stock_research", trade_date=date(2026, 6, 24))

    assert snapshot["status"] == "delayed"
    assert snapshot["latest_ready_trade_date"] == "2026-06-23"
    assert "source timeout" not in str(snapshot)
    assert "suggested_action" not in str(snapshot)
```

- [ ] **Step 2: Run the backend aggregation tests to verify they fail**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_dashboard_ops_snapshot.py -q
```

Expected: FAIL with `ModuleNotFoundError` or `ImportError` because `stock_research.dashboard.ops_snapshot` does not exist yet.

- [ ] **Step 3: Implement the aggregation module**

```python
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from stock_research.config import SETTINGS
from stock_research.daily_close_pipeline import load_data_status_for_dashboard
from stock_research.daily_health import summarize_operational_health
from stock_research.intraday_pipeline import load_intraday_status


def build_internal_ops_snapshot(
    service: str = SETTINGS.research_service,
    trade_date: date | None = None,
) -> dict[str, Any]:
    target_date = trade_date or date.today()
    data_status = load_data_status_for_dashboard(service, current_trade_date=target_date)
    intraday = load_intraday_status(service, target_date)
    health = summarize_operational_health(trade_date=target_date.isoformat(), service=service)
    stages = load_ops_stage_details(service, target_date)
    now_text = _now_in_timezone("Asia/Shanghai")

    run_window = _build_run_window(target_date, data_status, stages, now_text)
    pipeline = _build_pipeline_summary(data_status, stages, now_text)
    health_block = _build_health_summary(health, data_status, stages, now_text)
    readiness = _build_readiness(data_status)
    intervention = _build_intervention(run_window, pipeline, health_block, readiness)

    return {
        "run_window": run_window,
        "pipeline": pipeline,
        "health": health_block,
        "intervention": intervention,
        "readiness": readiness,
        "snapshot_preview": {
            "market_state": _market_state_preview(intraday),
            "topn_preview": [],
            "coverage_summary": {
                "pipeline_status": data_status["pipeline_status"],
                "failed_jobs": len(data_status.get("failed_jobs") or []),
                "warnings": data_status.get("warnings") or [],
            },
            "factor_gate_summary": {},
            "published_at": data_status.get("last_updated_at"),
        },
    }


def build_public_snapshot(
    service: str = SETTINGS.research_service,
    trade_date: date | None = None,
) -> dict[str, Any]:
    internal = build_internal_ops_snapshot(service=service, trade_date=trade_date)
    readiness = internal["readiness"]
    preview = internal["snapshot_preview"]
    status = _public_status_from_internal(internal)
    return {
        "trade_date": (trade_date or date.today()).isoformat(),
        "published_at": preview.get("published_at"),
        "latest_ready_trade_date": readiness.get("latest_ready_trade_date"),
        "status": status,
        "status_text": _public_status_text(status, readiness.get("latest_ready_trade_date")),
        "market_state": preview.get("market_state"),
        "topn_preview": preview.get("topn_preview"),
        "coverage_summary": preview.get("coverage_summary"),
        "factor_gate_summary": preview.get("factor_gate_summary"),
        "notes": [],
    }
```

- [ ] **Step 4: Run the backend aggregation tests to verify they pass**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_dashboard_ops_snapshot.py -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research && git add src/stock_research/dashboard/ops_snapshot.py tests/test_dashboard_ops_snapshot.py && git commit -m "feat: add ops and public snapshot aggregation"
```

### Task 2: Expose Snapshot APIs Through The Existing Dashboard Service

**Files:**
- Modify: `/Users/xiwei/stock_research/src/stock_research/dashboard/app.py`
- Modify: `/Users/xiwei/stock_research/tests/test_dashboard_app.py`

- [ ] **Step 1: Write the failing API tests**

```python
from fastapi.testclient import TestClient

from stock_research.dashboard.app import create_app


def test_ops_snapshot_route_returns_aggregated_payload(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.app.build_internal_ops_snapshot",
        lambda: {"intervention": {"needs_intervention": False}, "pipeline": {"overall_status": "running"}},
    )
    client = TestClient(create_app())

    response = client.get("/api/ops/snapshot")

    assert response.status_code == 200
    assert response.json()["pipeline"]["overall_status"] == "running"


def test_ops_stages_route_returns_stage_list(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.app.load_ops_stage_details",
        lambda service=None, trade_date=None: [{"stage": "daily", "status": "success"}],
    )
    client = TestClient(create_app())

    response = client.get("/api/ops/stages")

    assert response.status_code == 200
    assert response.json()["items"] == [{"stage": "daily", "status": "success"}]


def test_public_snapshot_route_returns_public_payload(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.app.build_public_snapshot",
        lambda: {"status": "ready", "latest_ready_trade_date": "2026-06-24"},
    )
    client = TestClient(create_app())

    response = client.get("/api/public/snapshot")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
```

- [ ] **Step 2: Run the API tests to verify they fail**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_dashboard_app.py -k "ops_snapshot_route or ops_stages_route or public_snapshot_route" -q
```

Expected: FAIL because the new route handlers and imports do not exist yet.

- [ ] **Step 3: Add the new routes to the FastAPI app**

```python
from stock_research.dashboard.ops_snapshot import (
    build_internal_ops_snapshot,
    build_public_snapshot,
    load_ops_stage_details,
)


@app.get("/api/ops/snapshot")
def ops_snapshot():
    return build_internal_ops_snapshot()


@app.get("/api/ops/stages")
def ops_stages():
    return {"items": load_ops_stage_details()}


@app.get("/api/public/snapshot")
def public_snapshot():
    return build_public_snapshot()
```

- [ ] **Step 4: Run the API tests to verify they pass**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_dashboard_app.py -k "ops_snapshot_route or ops_stages_route or public_snapshot_route" -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research && git add src/stock_research/dashboard/app.py tests/test_dashboard_app.py && git commit -m "feat: expose ops and public snapshot APIs"
```

### Task 3: Add The Internal Ops Dashboard View

**Files:**
- Modify: `/Users/xiwei/stock_research/dashboard/src/api/types.ts`
- Modify: `/Users/xiwei/stock_research/dashboard/src/api/client.ts`
- Create: `/Users/xiwei/stock_research/dashboard/src/components/OpsSnapshotPanel.tsx`
- Create: `/Users/xiwei/stock_research/dashboard/src/components/OpsStagesPanel.tsx`
- Modify: `/Users/xiwei/stock_research/dashboard/src/App.tsx`
- Modify: `/Users/xiwei/stock_research/dashboard/src/styles.css`
- Modify: `/Users/xiwei/stock_research/dashboard/tests/client.test.ts`
- Modify: `/Users/xiwei/stock_research/dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Write the failing frontend tests for ops snapshot loading and rendering**

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';

import { App } from '../src/App';


vi.stubGlobal(
  'fetch',
  vi.fn((input: string) => {
    if (input.includes('/api/ops/snapshot')) {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            pipeline: { overall_status: 'running', current_stage: 'minute5', progress_pct: 72 },
            intervention: {
              needs_intervention: true,
              severity: 'warning',
              reason_text: 'Deadline risk',
              suggested_action: 'Watch heartbeat',
            },
            readiness: {
              latest_ready_trade_date: '2026-06-23',
              ready_status: 'degraded_ready',
            },
            snapshot_preview: {
              market_state: { state: 'neutral' },
              topn_preview: [{ asset_id: '000001.SZ', stock_name: 'Ping An Bank', score_total: 93.1 }],
              coverage_summary: { pipeline_status: 'NOT_READY' },
              factor_gate_summary: {},
              published_at: '2026-06-24T08:08:00+08:00',
            },
          }),
          { status: 200 },
        ),
      );
    }
    if (input.includes('/api/ops/stages')) {
      return Promise.resolve(
        new Response(JSON.stringify({ items: [{ stage: 'daily', status: 'success' }] }), { status: 200 }),
      );
    }
    return Promise.resolve(new Response(JSON.stringify({ items: [] }), { status: 200 }));
  }),
);


test('renders ops hero status and intervention guidance', async () => {
  render(<App />);

  await waitFor(() => {
    expect(screen.getByText('running')).toBeInTheDocument();
    expect(screen.getByText('Deadline risk')).toBeInTheDocument();
    expect(screen.getByText('Watch heartbeat')).toBeInTheDocument();
    expect(screen.getByText('Ping An Bank')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the frontend tests to verify they fail**

Run:
```bash
cd /Users/xiwei/stock_research/dashboard && pnpm test -- --run tests/client.test.ts tests/app-shell.test.tsx
```

Expected: FAIL because the new fetch helpers, types, and components are missing.

- [ ] **Step 3: Add types, fetch helpers, and the internal ops panels**

```ts
export type OpsSnapshot = {
  run_window: {
    trade_date: string;
    expected_start_at: string | null;
    expected_done_by: string | null;
    started: boolean;
    started_at: string | null;
    completed: boolean;
    completed_at: string | null;
    on_time: boolean | null;
    lateness_minutes: number | null;
  };
  pipeline: {
    overall_status: string;
    current_stage: string | null;
    stage_started_at: string | null;
    stage_elapsed_minutes: number | null;
    completed_stage_count: number;
    total_stage_count: number;
    progress_pct: number;
    latest_heartbeat_at: string | null;
  };
  intervention: {
    needs_intervention: boolean;
    severity: string;
    reason_code: string | null;
    reason_text: string;
    suggested_action: string | null;
  };
  readiness: {
    latest_ready_trade_date: string | null;
    ready_status: string;
  };
  snapshot_preview: {
    market_state: Record<string, unknown> | null;
    topn_preview: Array<Record<string, unknown>>;
    coverage_summary: Record<string, unknown> | null;
    factor_gate_summary: Record<string, unknown> | null;
    published_at: string | null;
  };
};

export type OpsStageRow = {
  stage: string;
  status: string;
  started_at?: string | null;
  updated_at?: string | null;
  error_summary?: string | null;
};
```

```ts
export async function fetchOpsSnapshot(): Promise<OpsSnapshot> {
  return getJson('/api/ops/snapshot');
}

export async function fetchOpsStages(): Promise<OpsStageRow[]> {
  const payload = await getJson<{ items: OpsStageRow[] }>('/api/ops/stages');
  return payload.items;
}
```

```tsx
export function OpsSnapshotPanel({ snapshot }: { snapshot: OpsSnapshot }) {
  return (
    <section className="ops-panel">
      <div className="ops-hero-grid">
        <article className={`ops-card ops-card--${snapshot.pipeline.overall_status.toLowerCase()}`}>
          <h3>Workflow</h3>
          <strong>{snapshot.pipeline.overall_status}</strong>
          <p>Current stage: {snapshot.pipeline.current_stage ?? 'n/a'}</p>
          <p>Progress: {snapshot.pipeline.progress_pct}%</p>
        </article>
        <article className={`ops-card ops-card--${snapshot.intervention.severity}`}>
          <h3>Intervention</h3>
          <strong>{snapshot.intervention.needs_intervention ? 'Required' : 'Not required'}</strong>
          <p>{snapshot.intervention.reason_text}</p>
          <p>{snapshot.intervention.suggested_action ?? 'No action required'}</p>
        </article>
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Run the frontend tests to verify they pass**

Run:
```bash
cd /Users/xiwei/stock_research/dashboard && pnpm test -- --run tests/client.test.ts tests/app-shell.test.tsx
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research && git add dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/src/components/OpsSnapshotPanel.tsx dashboard/src/components/OpsStagesPanel.tsx dashboard/src/App.tsx dashboard/src/styles.css dashboard/tests/client.test.ts dashboard/tests/app-shell.test.tsx && git commit -m "feat: add internal ops dashboard view"
```

### Task 4: Add The Public Snapshot Page

**Files:**
- Modify: `/Users/xiwei/stock_research/dashboard/src/api/types.ts`
- Modify: `/Users/xiwei/stock_research/dashboard/src/api/client.ts`
- Create: `/Users/xiwei/stock_research/dashboard/src/components/PublicSnapshotPage.tsx`
- Modify: `/Users/xiwei/stock_research/dashboard/src/main.tsx`
- Modify: `/Users/xiwei/stock_research/dashboard/src/styles.css`
- Modify: `/Users/xiwei/stock_research/dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Write the failing public page render test**

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';

import { PublicSnapshotPage } from '../src/components/PublicSnapshotPage';


test('renders release-safe public snapshot fields only', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify({
        trade_date: '2026-06-24',
        published_at: '2026-06-24T08:15:00+08:00',
        latest_ready_trade_date: '2026-06-23',
        status: 'delayed',
        status_text: 'Showing the most recent ready release while today is still processing.',
        market_state: { state: 'neutral' },
        topn_preview: [{ asset_id: '000001.SZ', stock_name: 'Ping An Bank', score_total: 93.1 }],
        coverage_summary: { core: '97.8%' },
        factor_gate_summary: { approved_count: 12 },
        notes: [],
      }),
      { status: 200 },
    ),
  );

  render(<PublicSnapshotPage />);

  await waitFor(() => {
    expect(screen.getByText('delayed')).toBeInTheDocument();
    expect(screen.getByText('2026-06-23')).toBeInTheDocument();
    expect(screen.getByText('Ping An Bank')).toBeInTheDocument();
  });

  expect(screen.queryByText(/suggested action/i)).not.toBeInTheDocument();
  fetchMock.mockRestore();
});
```

- [ ] **Step 2: Run the public page test to verify it fails**

Run:
```bash
cd /Users/xiwei/stock_research/dashboard && pnpm test -- --run tests/app-shell.test.tsx
```

Expected: FAIL because `PublicSnapshotPage` and the new public snapshot fetch helper do not exist yet.

- [ ] **Step 3: Add the public snapshot fetcher, component, and route selection**

```ts
export type PublicSnapshot = {
  trade_date: string;
  published_at: string | null;
  latest_ready_trade_date: string | null;
  status: string;
  status_text: string;
  market_state: Record<string, unknown> | null;
  topn_preview: Array<Record<string, unknown>>;
  coverage_summary: Record<string, unknown> | null;
  factor_gate_summary: Record<string, unknown> | null;
  notes: string[];
};

export async function fetchPublicSnapshot(): Promise<PublicSnapshot> {
  return getJson('/api/public/snapshot');
}
```

```tsx
export function PublicSnapshotPage() {
  const [snapshot, setSnapshot] = useState<PublicSnapshot | null>(null);

  useEffect(() => {
    fetchPublicSnapshot().then(setSnapshot);
  }, []);

  if (!snapshot) {
    return <main className="public-shell">Loading public snapshot...</main>;
  }

  return (
    <main className="public-shell">
      <section className="public-hero">
        <span className={`public-badge public-badge--${snapshot.status}`}>{snapshot.status}</span>
        <h1>Daily A-share Snapshot</h1>
        <p>{snapshot.status_text}</p>
      </section>
    </main>
  );
}
```

```tsx
import { createRoot } from 'react-dom/client';

import { App } from './App';
import { PublicSnapshotPage } from './components/PublicSnapshotPage';
import './styles.css';

const path = window.location.pathname.replace(/\/+$/, '');
const root = createRoot(document.getElementById('root')!);

if (path === '/public') {
  root.render(<PublicSnapshotPage />);
} else {
  root.render(<App />);
}
```

- [ ] **Step 4: Run the public page test to verify it passes**

Run:
```bash
cd /Users/xiwei/stock_research/dashboard && pnpm test -- --run tests/app-shell.test.tsx
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research && git add dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/src/components/PublicSnapshotPage.tsx dashboard/src/main.tsx dashboard/src/styles.css dashboard/tests/app-shell.test.tsx && git commit -m "feat: add public snapshot page"
```

### Task 5: Add Operator Runbook And End-To-End Verification

**Files:**
- Create: `/Users/xiwei/stock_research/docs/dashboard-ops-snapshot-runbook.md`
- Modify: `/Users/xiwei/stock_research/README.md`
- Modify: `/Users/xiwei/stock_research/tests/test_dashboard_app.py`

- [ ] **Step 1: Write the failing documentation expectation check**

```python
from pathlib import Path


def test_dashboard_ops_snapshot_runbook_exists():
    path = Path("/Users/xiwei/stock_research/docs/dashboard-ops-snapshot-runbook.md")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "/api/ops/snapshot" in text
    assert "/api/public/snapshot" in text
    assert "needs_intervention" in text
```

- [ ] **Step 2: Run the runbook expectation check to verify it fails**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_dashboard_app.py -k dashboard_ops_snapshot_runbook_exists -q
```

Expected: FAIL because the runbook does not exist yet.

- [ ] **Step 3: Write the runbook and README entries**

```md
# Dashboard Ops Snapshot Runbook

## Endpoints

- `GET /api/ops/snapshot`
- `GET /api/ops/stages`
- `GET /api/public/snapshot`

## Internal Page Questions

- Did the workflow start on time?
- Is intervention required?
- What is the current stage?
- What is the latest ready trade date?

## Public Page Rules

- Public page never exposes raw source failures.
- Public page reads only release-safe fields from the public snapshot.
```

```md
## Ops Snapshot Pages

Internal ops status:

```bash
curl http://127.0.0.1:8765/api/ops/snapshot
curl http://127.0.0.1:8765/api/ops/stages
```

Public snapshot:

```bash
curl http://127.0.0.1:8765/api/public/snapshot
```
```

- [ ] **Step 4: Run full targeted verification**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_dashboard_ops_snapshot.py tests/test_dashboard_app.py -k "ops_snapshot or public_snapshot" -q
cd /Users/xiwei/stock_research/dashboard && pnpm test -- --run tests/client.test.ts tests/app-shell.test.tsx
cd /Users/xiwei/stock_research/dashboard && pnpm build
```

Expected:
- backend tests PASS
- frontend tests PASS
- `pnpm build` succeeds

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research && git add docs/dashboard-ops-snapshot-runbook.md README.md && git commit -m "docs: add ops snapshot dashboard runbook"
```

## Self-Review

- Spec coverage:
  - internal ops page: Tasks 1-4
  - public snapshot page: Tasks 1, 2, and 4
  - unified backend aggregation: Task 1
  - stable API layer: Task 2
  - runbook and operator usage: Task 5
- Placeholder scan:
  - removed `TODO`, `TBD`, and generic "add validation" wording
  - each task includes exact files, commands, and example code
- Type consistency:
  - backend uses `build_internal_ops_snapshot`, `build_public_snapshot`, and `load_ops_stage_details`
  - frontend consumes `OpsSnapshot`, `OpsStageRow`, and `PublicSnapshot`
  - route names match API usage across tasks
