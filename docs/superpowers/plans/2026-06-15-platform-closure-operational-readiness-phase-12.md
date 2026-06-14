# Platform Closure And Operational Readiness Phase 12 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the dashboard build-out with a deterministic local EOD readiness contract, a Home readiness strip, a short runbook, and a verified daily Review Queue to Stock evidence path.

**Architecture:** Add a small backend readiness read model behind `GET /api/platform/readiness`; add a typed frontend client and render it in `HomeCockpit` independently from existing widgets; keep all source workspace behavior read-only and EOD. Finish with runbook documentation and focused unit/e2e verification.

**Tech Stack:** FastAPI/TestClient, pytest, React, TypeScript, Vite, Vitest, Playwright.

---

## File Structure

Backend:

- Create `src/stock_research/dashboard/readiness.py`
  - Owns deterministic readiness aggregation.
  - Calls lightweight existing read helpers only.
  - Converts source failures into warnings/check details.
- Modify `src/stock_research/dashboard/app.py`
  - Import `build_platform_readiness`.
  - Add `GET /api/platform/readiness`.
- Add `tests/test_dashboard_readiness.py`
  - Unit tests for status aggregation and endpoint behavior.

Frontend:

- Modify `dashboard/src/api/types.ts`
  - Add `PlatformReadiness`, `PlatformReadinessCheck`, and status union types.
- Modify `dashboard/src/api/client.ts`
  - Add `fetchPlatformReadiness()`.
- Modify `dashboard/src/components/HomeCockpit.tsx`
  - Fetch readiness once on mount.
  - Render a compact `Platform Readiness` strip above the existing status strip.
  - Show readiness warnings locally without blocking existing Home sections.
- Modify `dashboard/tests/client.test.ts`
  - Cover readiness client URL.
- Modify `dashboard/tests/home-cockpit.test.tsx`
  - Mock readiness client and cover ready/error states.
- Modify `dashboard/tests/app-shell.test.tsx`
  - Add readiness mock defaults so App tests remain isolated.
- Modify `dashboard/tests/platform-full-flow.spec.ts`
  - Mock `/api/platform/readiness`.
  - Assert Home readiness and daily Review Queue path.

Docs:

- Create `docs/dashboard-local-runbook.md`
  - Localhost startup, EOD assumptions, verification commands, and source troubleshooting.

Worktree discipline:

- There are existing unrelated dirty files in this branch. Stage only Phase 12 hunks with `git add -p` when a file already has unrelated edits.
- Do not revert or clean unrelated changes.

---

## Task 1: Backend Readiness Endpoint

**Files:**
- Create: `src/stock_research/dashboard/readiness.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_readiness.py`

- [ ] **Step 1: Write failing backend readiness tests**

Create `tests/test_dashboard_readiness.py`:

```python
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard.readiness import aggregate_readiness_status, build_platform_readiness


def test_aggregate_readiness_status_prioritizes_missing_data():
    assert aggregate_readiness_status(
        [
            {"key": "platform", "status": "ready"},
            {"key": "review_queue", "status": "missing_data"},
            {"key": "news", "status": "partial"},
        ]
    ) == "missing_data"


def test_aggregate_readiness_status_reports_partial_for_optional_gaps():
    assert aggregate_readiness_status(
        [
            {"key": "platform", "status": "ready"},
            {"key": "review_queue", "status": "ready"},
            {"key": "news", "status": "partial"},
        ]
    ) == "partial"


def test_build_platform_readiness_returns_eod_local_payload(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.readiness.load_platform_summary",
        lambda score_version="manual_v1", top_n=1: {
            "latest_market_date": "2026-06-12",
            "latest_score_date": "2026-06-12",
            "latest_factor_date": "2026-06-12",
            "market_asset_count": 5300,
            "score_asset_count": 3100,
            "factor_count": 42,
            "score_versions": ["manual_v1"],
            "topn_preview": [{"asset_id": "000001.SZ"}],
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.readiness.build_review_queue",
        lambda trade_date=None, score_version="manual_v1", limit=1, lookback_days=90: {
            "trade_date": trade_date or "2026-06-12",
            "groups": [{"bucket": "strong", "count": 1, "items": [{"asset_id": "000001.SZ"}]}],
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.readiness.load_public_news_for_dashboard",
        lambda source="sina_finance", limit=1: {"items": [{"news_id": "n1"}], "warnings": []},
    )
    monkeypatch.setattr(
        "stock_research.dashboard.readiness.load_research_report_summary",
        lambda: {"total_reports": 12, "warnings": []},
    )
    monkeypatch.setattr(
        "stock_research.dashboard.readiness.load_report_links",
        lambda: [{"title": "Daily", "path": "/reports/daily.md"}],
    )

    payload = build_platform_readiness()

    assert payload["mode"] == "eod_local"
    assert payload["status"] == "ready"
    assert payload["latest_market_date"] == "2026-06-12"
    checks = {check["key"]: check for check in payload["checks"]}
    assert checks["platform_summary"]["status"] == "ready"
    assert checks["review_queue"]["status"] == "ready"
    assert checks["news"]["status"] == "ready"
    assert checks["research_reports"]["status"] == "ready"
    assert checks["generated_reports"]["status"] == "ready"
    assert payload["warnings"] == []


def test_build_platform_readiness_converts_optional_source_failures_to_partial(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.readiness.load_platform_summary",
        lambda score_version="manual_v1", top_n=1: {
            "latest_market_date": "2026-06-12",
            "latest_score_date": "2026-06-12",
            "latest_factor_date": "2026-06-12",
            "market_asset_count": 5300,
            "score_asset_count": 3100,
            "factor_count": 42,
            "score_versions": ["manual_v1"],
            "topn_preview": [{"asset_id": "000001.SZ"}],
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.readiness.build_review_queue",
        lambda trade_date=None, score_version="manual_v1", limit=1, lookback_days=90: {
            "trade_date": trade_date or "2026-06-12",
            "groups": [{"bucket": "strong", "count": 0, "items": []}],
            "warnings": ["thin queue"],
        },
    )
    monkeypatch.setattr(
        "stock_research.dashboard.readiness.load_public_news_for_dashboard",
        lambda source="sina_finance", limit=1: (_ for _ in ()).throw(RuntimeError("news source down")),
    )
    monkeypatch.setattr(
        "stock_research.dashboard.readiness.load_research_report_summary",
        lambda: {"total_reports": 0, "warnings": []},
    )
    monkeypatch.setattr(
        "stock_research.dashboard.readiness.load_report_links",
        lambda: [],
    )

    payload = build_platform_readiness()

    assert payload["status"] == "partial"
    checks = {check["key"]: check for check in payload["checks"]}
    assert checks["news"]["status"] == "partial"
    assert checks["research_reports"]["status"] == "partial"
    assert checks["generated_reports"]["status"] == "partial"
    assert any("news source down" in warning for warning in payload["warnings"])


def test_platform_readiness_route(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "build_platform_readiness",
        lambda: {
            "mode": "eod_local",
            "status": "ready",
            "as_of": "2026-06-15T00:00:00+08:00",
            "latest_market_date": "2026-06-12",
            "checks": [],
            "warnings": [],
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/platform/readiness")

    assert response.status_code == 200
    assert response.json()["mode"] == "eod_local"
```

- [ ] **Step 2: Run backend tests and verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_readiness.py -q
```

Expected: FAIL because `stock_research.dashboard.readiness` does not exist.

- [ ] **Step 3: Implement readiness module**

Create `src/stock_research/dashboard/readiness.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from stock_research.dashboard.news import load_public_news_for_dashboard
from stock_research.dashboard.platform import load_platform_summary
from stock_research.dashboard.reports import load_report_links
from stock_research.dashboard.research_reports import load_research_report_summary
from stock_research.dashboard.review_queue import build_review_queue

CHECK_READY = "ready"
CHECK_PARTIAL = "partial"
CHECK_MISSING = "missing_data"
CHECK_UNKNOWN = "unknown"


def aggregate_readiness_status(checks: list[dict[str, Any]]) -> str:
    statuses = {str(check.get("status") or CHECK_UNKNOWN) for check in checks}
    if CHECK_MISSING in statuses:
        return CHECK_MISSING
    if CHECK_PARTIAL in statuses or CHECK_UNKNOWN in statuses:
        return CHECK_PARTIAL
    return CHECK_READY


def build_platform_readiness(score_version: str = "manual_v1") -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    latest_market_date = ""

    try:
        summary = load_platform_summary(score_version=score_version, top_n=1)
        latest_market_date = str(summary.get("latest_market_date") or "")
        topn_count = len(summary.get("topn_preview") or [])
        if latest_market_date and topn_count > 0:
            checks.append(_check("platform_summary", "Platform Summary", CHECK_READY, f"EOD data available for {latest_market_date}"))
        else:
            checks.append(_check("platform_summary", "Platform Summary", CHECK_MISSING, "No latest market date or TopN preview available"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("platform_summary", "Platform Summary", CHECK_MISSING, "Platform summary unavailable"))
        warnings.append(f"Platform summary unavailable: {exc}")

    try:
        queue = build_review_queue(
            trade_date=latest_market_date or None,
            score_version=score_version,
            limit=1,
            lookback_days=90,
        )
        item_count = sum(len(group.get("items") or []) for group in queue.get("groups") or [])
        queue_date = str(queue.get("trade_date") or latest_market_date or "")
        queue_warnings = [str(warning) for warning in queue.get("warnings") or []]
        warnings.extend(queue_warnings)
        if item_count > 0:
            checks.append(_check("review_queue", "Review Queue", CHECK_READY, f"Queue available for {queue_date}"))
        else:
            checks.append(_check("review_queue", "Review Queue", CHECK_PARTIAL, f"No review candidates for {queue_date or 'selected EOD date'}"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("review_queue", "Review Queue", CHECK_PARTIAL, "Review Queue unavailable"))
        warnings.append(f"Review Queue unavailable: {exc}")

    try:
        news = load_public_news_for_dashboard(source="sina_finance", limit=1)
        news_items = news.get("items") or []
        warnings.extend(str(warning) for warning in news.get("warnings") or [])
        if news_items:
            checks.append(_check("news", "News", CHECK_READY, "Public news source returned items"))
        else:
            checks.append(_check("news", "News", CHECK_PARTIAL, "Public news source returned no items"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("news", "News", CHECK_PARTIAL, "Public news source unavailable"))
        warnings.append(f"News unavailable: {exc}")

    try:
        research_summary = load_research_report_summary()
        total_reports = int(research_summary.get("total_reports") or 0)
        warnings.extend(str(warning) for warning in research_summary.get("warnings") or [])
        if total_reports > 0:
            checks.append(_check("research_reports", "Research Reports", CHECK_READY, f"{total_reports} reports indexed"))
        else:
            checks.append(_check("research_reports", "Research Reports", CHECK_PARTIAL, "No research reports indexed"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("research_reports", "Research Reports", CHECK_PARTIAL, "Research report index unavailable"))
        warnings.append(f"Research Reports unavailable: {exc}")

    try:
        report_links = load_report_links()
        if report_links:
            checks.append(_check("generated_reports", "Generated Reports", CHECK_READY, f"{len(report_links)} local reports available"))
        else:
            checks.append(_check("generated_reports", "Generated Reports", CHECK_PARTIAL, "No local generated reports found"))
    except Exception as exc:  # noqa: BLE001
        checks.append(_check("generated_reports", "Generated Reports", CHECK_PARTIAL, "Generated report links unavailable"))
        warnings.append(f"Generated Reports unavailable: {exc}")

    return {
        "mode": "eod_local",
        "status": aggregate_readiness_status(checks),
        "as_of": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "latest_market_date": latest_market_date,
        "checks": checks,
        "warnings": _unique(warnings),
    }


def _check(key: str, label: str, status: str, detail: str) -> dict[str, str]:
    return {"key": key, "label": label, "status": status, "detail": detail}


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
```

- [ ] **Step 4: Wire FastAPI route**

Modify `src/stock_research/dashboard/app.py`.

Add import:

```python
from stock_research.dashboard.readiness import build_platform_readiness
```

Add route after `/api/platform/summary`:

```python
    @app.get("/api/platform/readiness")
    def platform_readiness():
        return build_platform_readiness()
```

- [ ] **Step 5: Run backend tests and verify GREEN**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_readiness.py tests/test_dashboard_app.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit backend readiness**

Stage only these files:

```bash
git add src/stock_research/dashboard/readiness.py src/stock_research/dashboard/app.py tests/test_dashboard_readiness.py
git commit -m "feat: add platform readiness endpoint"
```

---

## Task 2: Frontend Readiness Client And Home Strip

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/src/components/HomeCockpit.tsx`
- Modify: `dashboard/tests/client.test.ts`
- Modify: `dashboard/tests/home-cockpit.test.tsx`
- Modify: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Write failing client test**

In `dashboard/tests/client.test.ts`, import `fetchPlatformReadiness` and add:

```ts
  it('fetches platform readiness', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        mode: 'eod_local',
        status: 'ready',
        as_of: '2026-06-15T00:00:00+08:00',
        latest_market_date: '2026-06-12',
        checks: [{ key: 'review_queue', label: 'Review Queue', status: 'ready', detail: 'Queue available' }],
        warnings: []
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchPlatformReadiness();

    expect(fetchMock).toHaveBeenCalledWith('/api/platform/readiness');
    expect(result.mode).toBe('eod_local');
    expect(result.checks[0].key).toBe('review_queue');
  });
```

- [ ] **Step 2: Write failing Home tests**

In `dashboard/tests/home-cockpit.test.tsx`, add `fetchPlatformReadiness` to the `vi.mock('../src/api/client', ...)` object:

```ts
  fetchPlatformReadiness: vi.fn(),
```

In `beforeEach`, add:

```ts
    vi.mocked(api.fetchPlatformReadiness).mockResolvedValue({
      mode: 'eod_local',
      status: 'ready',
      as_of: '2026-06-15T00:00:00+08:00',
      latest_market_date: '2026-06-12',
      checks: [
        { key: 'review_queue', label: 'Review Queue', status: 'ready', detail: 'Queue available for 2026-06-12' },
        { key: 'news', label: 'News', status: 'partial', detail: 'Public news source returned no items' }
      ],
      warnings: ['News source is thin']
    });
```

Add tests:

```ts
  it('renders platform readiness without blocking cockpit sections', async () => {
    render(<AppShell />);

    expect(await screen.findByRole('heading', { name: 'Research Cockpit' })).toBeVisible();
    expect(screen.getByRole('region', { name: 'Platform Readiness' })).toBeVisible();
    expect(screen.getByText('EOD local')).toBeVisible();
    expect(screen.getByText('Ready')).toBeVisible();
    expect(screen.getByText('Review Queue')).toBeVisible();
    expect(screen.getByText('Queue available for 2026-06-12')).toBeVisible();
    expect(screen.getByText('News source is thin')).toBeVisible();
    expect(screen.getByText('Today Focus')).toBeVisible();
  });

  it('keeps home usable when platform readiness fails', async () => {
    vi.mocked(api.fetchPlatformReadiness).mockRejectedValueOnce(new Error('readiness unavailable'));

    render(<AppShell />);

    expect(await screen.findByRole('heading', { name: 'Research Cockpit' })).toBeVisible();
    expect(screen.getByText('Platform readiness unavailable: readiness unavailable')).toBeVisible();
    expect(screen.getByText('Today Focus')).toBeVisible();
    expect(screen.getByText('Market Pulse')).toBeVisible();
  });
```

In `dashboard/tests/app-shell.test.tsx`, add `fetchPlatformReadiness: vi.fn()` to the API mock and set a default resolved value in the app shell `beforeEach` block:

```ts
    apiMocks.fetchPlatformReadiness.mockResolvedValue({
      mode: 'eod_local',
      status: 'ready',
      as_of: '2026-06-15T00:00:00+08:00',
      latest_market_date: '2026-06-12',
      checks: [{ key: 'review_queue', label: 'Review Queue', status: 'ready', detail: 'Queue available' }],
      warnings: []
    });
```

- [ ] **Step 3: Run frontend tests and verify RED**

Run:

```bash
cd dashboard && npm test -- --run tests/client.test.ts tests/home-cockpit.test.tsx tests/app-shell.test.tsx
```

Expected: FAIL because `fetchPlatformReadiness` and the Home readiness strip do not exist.

- [ ] **Step 4: Add frontend types**

In `dashboard/src/api/types.ts`, add near `PlatformSummary`:

```ts
export type PlatformReadinessStatus = 'ready' | 'partial' | 'missing_data';

export type PlatformReadinessCheckStatus = PlatformReadinessStatus | 'unknown';

export type PlatformReadinessCheck = {
  key: string;
  label: string;
  status: PlatformReadinessCheckStatus;
  detail: string;
};

export type PlatformReadiness = {
  mode: 'eod_local' | string;
  status: PlatformReadinessStatus;
  as_of: string;
  latest_market_date: string;
  checks: PlatformReadinessCheck[];
  warnings: string[];
};
```

- [ ] **Step 5: Add frontend client**

In `dashboard/src/api/client.ts`, import `PlatformReadiness` and add after `fetchPlatformSummary`:

```ts
export async function fetchPlatformReadiness(): Promise<PlatformReadiness> {
  return getJson<PlatformReadiness>('/api/platform/readiness');
}
```

- [ ] **Step 6: Render Home readiness strip**

In `dashboard/src/components/HomeCockpit.tsx`, update imports:

```ts
  fetchPlatformReadiness,
```

and types:

```ts
  PlatformReadiness,
```

Add helpers above `HomeCockpit`:

```ts
function formatReadinessMode(mode: string | undefined) {
  return mode === 'eod_local' ? 'EOD local' : mode || '-';
}

function formatReadinessStatus(status: string | undefined) {
  if (status === 'ready') return 'Ready';
  if (status === 'partial') return 'Partial';
  if (status === 'missing_data') return 'Missing data';
  return '-';
}
```

Add state:

```ts
  const [readiness, setReadiness] = useState<PlatformReadiness | null>(null);
```

In the main `useEffect`, reset readiness and add a non-blocking request:

```ts
    setReadiness(null);

    void fetchPlatformReadiness().then(
      (payload) => {
        if (!ignore) setReadiness(payload);
      },
      (err: unknown) => {
        if (!ignore) {
          setReadiness(null);
          addWidgetWarning(`Platform readiness unavailable: ${errorMessage(err)}`);
        }
      }
    );
```

Render the readiness strip after warnings and before the existing `Dashboard status` section:

```tsx
      <section className="status-strip readiness-strip" aria-label="Platform Readiness">
        <div>
          <span>Mode</span>
          <strong>{formatReadinessMode(readiness?.mode)}</strong>
        </div>
        <div>
          <span>Status</span>
          <strong>{formatReadinessStatus(readiness?.status)}</strong>
        </div>
        <div>
          <span>Latest EOD</span>
          <strong>{readiness?.latest_market_date || summary?.latest_market_date || '-'}</strong>
        </div>
        <div>
          <span>Warnings</span>
          <strong>{formatCount(readiness?.warnings.length)}</strong>
        </div>
        {(readiness?.checks ?? []).slice(0, 4).map((check) => (
          <div key={check.key}>
            <span>{check.label}</span>
            <strong>{formatReadinessStatus(check.status)}</strong>
            <small className="muted">{check.detail}</small>
          </div>
        ))}
      </section>
      {(readiness?.warnings ?? []).map((warning) => (
        <p className="error-text" key={`readiness:${warning}`}>
          {warning}
        </p>
      ))}
```

If existing CSS makes `small` cramped, add a focused style in `dashboard/src/styles.css`:

```css
.readiness-strip small {
  display: block;
  margin-top: 4px;
}
```

- [ ] **Step 7: Run frontend tests and verify GREEN**

Run:

```bash
cd dashboard && npm test -- --run tests/client.test.ts tests/home-cockpit.test.tsx tests/app-shell.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit frontend readiness strip**

Stage only Phase 12 hunks. Use `git add -p` for files with unrelated edits:

```bash
git add -p dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/src/components/HomeCockpit.tsx dashboard/src/styles.css dashboard/tests/client.test.ts dashboard/tests/home-cockpit.test.tsx dashboard/tests/app-shell.test.tsx
git commit -m "feat: show platform readiness on home"
```

---

## Task 3: Local Dashboard Runbook

**Files:**
- Create: `docs/dashboard-local-runbook.md`

- [ ] **Step 1: Create runbook**

Create `docs/dashboard-local-runbook.md`:

```markdown
# Dashboard Local Runbook

## Operating Mode

The dashboard is a local EOD research cockpit. It uses local database tables and local generated artifacts. It does not promise realtime market data, broker connectivity, or automatic trading.

## Start Backend

From the repository root:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/uvicorn stock_research.dashboard.app:create_app --factory --host 127.0.0.1 --port 8000
```

Backend API health surfaces:

- `http://127.0.0.1:8000/api/platform/summary`
- `http://127.0.0.1:8000/api/platform/readiness`
- `http://127.0.0.1:8000/api/review-queue`

## Start Frontend

From `dashboard/`:

```bash
npm install
npm run dev
```

Open the Vite URL printed by the command, usually:

- `http://localhost:5173`

## Daily EOD Path

1. Open Home and check `Platform Readiness`.
2. Open `Review Queue`.
3. Choose a candidate and click `Review Stock`.
4. Review `Evidence Digest` in Stock Workspace.
5. Open News, Research Reports, or Market Monitor from the stock context.
6. Return to Stock Workspace and confirm the asset/date context is preserved.

## Verification Commands

Backend focused checks:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_readiness.py tests/test_dashboard_review_queue.py tests/test_dashboard_evidence_digest.py tests/test_dashboard_app.py -q
```

Frontend focused checks:

```bash
cd dashboard
npm test -- --run tests/client.test.ts tests/home-cockpit.test.tsx tests/app-shell.test.tsx tests/review-queue-workspace.test.tsx tests/stock-workspace.test.tsx
npm run build
npm run test:e2e
```

## Empty Source Checklist

If Review Queue is empty:

- Check `/api/platform/readiness`.
- Confirm latest score date and market date exist in `/api/platform/summary`.
- Confirm `/api/review-queue` returns groups for the selected EOD date.

If News is empty:

- Check `/api/public-news/status`.
- Check active source/category/date filters.
- Remember quality filtering can hide low-quality rows.

If Research Reports is empty:

- Check active query and date filters.
- Check `/api/research-reports/summary`.

If Market Monitor is empty:

- Check selected EOD date.
- Check `/api/market-monitor/eod`.
- Empty auction or emotion lists may be valid when source coverage is pending.

## Known Boundaries

- No realtime market data.
- No websocket or polling guarantee.
- No persistent review state.
- No broker/order integration.
- No AI-generated recommendations.
```

- [ ] **Step 2: Self-check runbook**

Run:

```bash
rg -n "localhost|readiness|Review Queue|EOD" docs/dashboard-local-runbook.md
```

Expected: The command shows real runbook content for localhost, readiness, Review Queue, and EOD behavior.

- [ ] **Step 3: Commit runbook**

Run:

```bash
git add docs/dashboard-local-runbook.md
git commit -m "docs: add dashboard local runbook"
```

---

## Task 4: E2E Readiness And Final Verification

**Files:**
- Modify: `dashboard/tests/platform-full-flow.spec.ts`

- [ ] **Step 1: Add failing e2e readiness assertions**

In `dashboard/tests/platform-full-flow.spec.ts`, add a mocked route near existing platform routes:

```ts
    if (url.pathname === '/api/platform/readiness') {
      await route.fulfill({
        json: {
          mode: 'eod_local',
          status: 'ready',
          as_of: '2026-06-15T00:00:00+08:00',
          latest_market_date: '2026-06-08',
          checks: [
            { key: 'review_queue', label: 'Review Queue', status: 'ready', detail: 'Queue available for 2026-06-08' },
            { key: 'news', label: 'News', status: 'ready', detail: 'Public news source returned items' }
          ],
          warnings: []
        }
      });
      return;
    }
```

In the main full-flow test, after Home loads, add:

```ts
  await expect(page.getByRole('region', { name: 'Platform Readiness' })).toBeVisible();
  await expect(page.getByText('EOD local')).toBeVisible();
  await expect(page.getByText('Queue available for 2026-06-08')).toBeVisible();
```

Extend the Review Queue path to assert stock context after `Review Stock`:

```ts
  await page.getByRole('button', { name: 'Open Review Queue workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Review Queue' })).toBeVisible();
  await page.getByRole('button', { name: 'Review Stock' }).click();
  await expect(page.getByRole('heading', { name: /Fixture Stock|平安银行|Stock Workspace/ })).toBeVisible();
  await expect(page.getByText(/Opened from Search|Trade Date 2026-06-08/)).toBeVisible();
```

- [ ] **Step 2: Run e2e and verify RED if route/client not wired**

Run:

```bash
cd dashboard && npm run test:e2e
```

Expected before earlier tasks: FAIL because Home does not render `Platform Readiness`. Expected after Tasks 1-2: PASS or expose fixture gaps to fix.

- [ ] **Step 3: Fix fixture gaps only**

If e2e fails because a mocked response lacks Phase 12 fields, update the fixture, not production behavior. Keep changes in `dashboard/tests/platform-full-flow.spec.ts`.

- [ ] **Step 4: Run full Phase 12 verification**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_readiness.py tests/test_dashboard_review_queue.py tests/test_dashboard_evidence_digest.py tests/test_dashboard_app.py -q
cd dashboard && npm test -- --run tests/client.test.ts tests/home-cockpit.test.tsx tests/app-shell.test.tsx tests/review-queue-workspace.test.tsx tests/stock-workspace.test.tsx
cd dashboard && npm run build
cd dashboard && npm run test:e2e
```

Expected:

- backend focused tests pass;
- frontend focused tests pass;
- TypeScript/Vite build passes;
- Playwright e2e passes.

- [ ] **Step 5: Inspect Phase 12 diff and dirty worktree**

Run:

```bash
git log --oneline --reverse 5e4724d..HEAD
git status --short
git diff --stat 5e4724d..HEAD
```

Confirm:

- Phase 12 commits only include readiness endpoint, Home readiness strip, runbook, e2e/test updates, and any small empty/error state polish required by tests.
- Unrelated dirty files remain unstaged.

- [ ] **Step 6: Commit e2e readiness fixture**

Run:

```bash
git add -p dashboard/tests/platform-full-flow.spec.ts
git commit -m "test: cover platform readiness daily path"
```

- [ ] **Step 7: Final review**

Review:

- `src/stock_research/dashboard/readiness.py`
- `src/stock_research/dashboard/app.py`
- `dashboard/src/components/HomeCockpit.tsx`
- `dashboard/src/api/client.ts`
- `dashboard/src/api/types.ts`
- `docs/dashboard-local-runbook.md`
- test files touched in Phase 12

Check for:

- readiness endpoint accidentally triggering expensive ingestion or backfills;
- unhandled optional-source errors;
- misleading realtime wording;
- lost Review Queue `tradeDate` handoff;
- unstaged Phase 12 changes.

---

## Final Completion Checklist

- [ ] Design committed: `docs: add phase 12 platform closure design`
- [ ] Plan committed.
- [ ] Backend readiness endpoint committed.
- [ ] Home readiness strip committed.
- [ ] Runbook committed.
- [ ] E2E readiness path committed.
- [ ] Full verification commands pass.
- [ ] Final review finds no blocking issues.
- [ ] Phase 12 commits are separated from unrelated dirty worktree changes.
