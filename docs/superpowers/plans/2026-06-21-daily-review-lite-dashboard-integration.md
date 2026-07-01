# Daily Review Lite Dashboard Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate `Daily Review Lite` into the existing `5174` dashboard as a new peer workspace between `复盘队列` and `市场监控`, while keeping the existing review queue in place and preserving Lite’s dedicated read-only data flow.

**Architecture:** Introduce a lightweight dashboard shell that owns workspace navigation and URL state, then render the existing large workbench and the Lite review page as separate workspace views. Keep `DailyReviewLiteWorkspace` thin: it reads dashboard-level `trade_date` state and delegates the actual review rendering to the existing Lite page and API contract. Add dashboard-level Vitest coverage plus a browser smoke that enters Lite from the real dashboard shell.

**Tech Stack:** React 19, TypeScript, Vite, Vitest, Testing Library, Playwright

---

## File Map

- `dashboard/src/main.tsx`
  Responsibility: keep the single dashboard entrypoint mounted to the unified shell instead of mounting a standalone page.
- `dashboard/src/App.tsx`
  Responsibility: remain the current “workbench workspace” view only; do not keep growing it with shell responsibilities if a dedicated shell component is introduced.
- `dashboard/src/shell/DashboardShell.tsx`
  Responsibility: own left navigation, current workspace selection, URL synchronization, and workspace content switching.
- `dashboard/src/workspaces/WorkbenchWorkspace.tsx`
  Responsibility: wrap the existing `App` workbench content as one workspace under the new shell.
- `dashboard/src/workspaces/DailyReviewLiteWorkspace.tsx`
  Responsibility: read dashboard-level `trade_date`, keep it in sync with the URL, and render `DailyReviewLitePage` inside the dashboard workspace frame.
- `dashboard/src/pages/DailyReviewLitePage.tsx`
  Responsibility: continue owning Lite page fetch/state/section rendering; accept an externally controlled initial/default date input if needed for dashboard integration.
- `dashboard/src/styles.css`
  Responsibility: add shell-level navigation/workspace styles and any incremental Lite-in-dashboard adjustments without regressing the existing workbench CSS.
- `dashboard/tests/dashboard-shell.test.tsx`
  Responsibility: verify left-nav presence, workspace switching, URL synchronization, and direct URL entry into Lite workspace.
- `dashboard/tests/app-smoke.spec.ts`
  Responsibility: stay intact unless a minimal update is needed to account for the new shell wrapper.
- `dashboard/tests/daily-review-lite.spec.ts`
  Responsibility: continue Lite-specific smoke coverage.
- `dashboard/tests/dashboard-lite-workspace.spec.ts`
  Responsibility: verify entering the Lite workspace from the real dashboard shell at `/` and seeing the expected Lite content.

## Implementation Notes

- `5174` dashboard currently mounts [dashboard/src/App.tsx](/Users/xiwei/stock_research/dashboard/src/App.tsx), which already contains both data fetching and layout responsibilities.
- `DailyReviewLitePage` already exists in the merged `main` history, with dedicated Vitest coverage and a dedicated Lite Playwright smoke.
- The new integration should not reintroduce the old standalone-Lite `main.tsx` mounting pattern.
- Avoid introducing a full router package in this first pass. A lightweight query-param approach is sufficient and aligns with the approved design.
- Keep `复盘队列` intact. `Daily Review Lite` is additive in the navigation and should not replace or rename the existing review queue yet.

### Task 1: Introduce Dashboard Shell And Workspace URL State

**Files:**
- Create: `dashboard/src/shell/DashboardShell.tsx`
- Create: `dashboard/src/workspaces/WorkbenchWorkspace.tsx`
- Modify: `dashboard/src/main.tsx`
- Modify: `dashboard/src/App.tsx`
- Test: `dashboard/tests/dashboard-shell.test.tsx`

- [ ] **Step 1: Write the failing shell test**

```tsx
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DashboardShell } from '../src/shell/DashboardShell';

vi.mock('../src/workspaces/WorkbenchWorkspace', () => ({
  WorkbenchWorkspace: () => <div>Workbench workspace content</div>
}));

vi.mock('../src/workspaces/DailyReviewLiteWorkspace', () => ({
  DailyReviewLiteWorkspace: () => <div>Daily Review Lite workspace content</div>
}));

afterEach(() => {
  cleanup();
  window.history.replaceState({}, '', '/');
});

describe('DashboardShell', () => {
  it('renders the new Daily Review Lite navigation item between 复盘队列 and 市场监控 and switches workspace via URL state', async () => {
    render(<DashboardShell />);

    const buttons = screen.getAllByRole('button');
    const labels = buttons.map((button) => button.textContent);

    expect(labels).toContain('复盘队列');
    expect(labels).toContain('Daily Review Lite');
    expect(labels).toContain('市场监控');

    const reviewQueueIndex = labels.indexOf('复盘队列');
    const liteIndex = labels.indexOf('Daily Review Lite');
    const monitorIndex = labels.indexOf('市场监控');

    expect(reviewQueueIndex).toBeGreaterThanOrEqual(0);
    expect(liteIndex).toBe(reviewQueueIndex + 1);
    expect(monitorIndex).toBe(liteIndex + 1);

    fireEvent.click(screen.getByRole('button', { name: 'Daily Review Lite' }));

    await waitFor(() => {
      expect(screen.getByText('Daily Review Lite workspace content')).toBeInTheDocument();
    });

    expect(new URL(window.location.href).searchParams.get('workspace')).toBe('daily-review-lite');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm exec vitest run tests/dashboard-shell.test.tsx -t "renders the new Daily Review Lite navigation item between 复盘队列 and 市场监控 and switches workspace via URL state"`

Expected: FAIL with `Cannot find module '../src/shell/DashboardShell'` or equivalent missing-export failure.

- [ ] **Step 3: Write minimal implementation**

`dashboard/src/shell/DashboardShell.tsx`

```tsx
import { WorkbenchWorkspace } from '../workspaces/WorkbenchWorkspace';
import { DailyReviewLiteWorkspace } from '../workspaces/DailyReviewLiteWorkspace';

const WORKSPACES = [
  { key: 'home', label: '首页' },
  { key: 'review-queue', label: '复盘队列' },
  { key: 'daily-review-lite', label: 'Daily Review Lite' },
  { key: 'market-monitor', label: '市场监控' }
] as const;

type WorkspaceKey = (typeof WORKSPACES)[number]['key'];

export function DashboardShell() {
  const currentWorkspace = readWorkspaceFromUrl();

  function updateWorkspace(workspace: WorkspaceKey) {
    const url = new URL(window.location.href);
    url.searchParams.set('workspace', workspace);
    window.history.replaceState({}, '', `${url.pathname}?${url.searchParams.toString()}`);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }

  return (
    <main className="dashboard-shell">
      <aside className="dashboard-shell-nav" aria-label="Workspace navigation">
        {WORKSPACES.map((workspace) => (
          <button key={workspace.key} type="button" onClick={() => updateWorkspace(workspace.key)}>
            {workspace.label}
          </button>
        ))}
      </aside>
      <section className="dashboard-shell-content">
        {currentWorkspace === 'daily-review-lite' ? <DailyReviewLiteWorkspace /> : <WorkbenchWorkspace />}
      </section>
    </main>
  );
}

function readWorkspaceFromUrl(): WorkspaceKey {
  const workspace = new URL(window.location.href).searchParams.get('workspace');
  return workspace === 'daily-review-lite' ? 'daily-review-lite' : 'home';
}
```

`dashboard/src/workspaces/WorkbenchWorkspace.tsx`

```tsx
import { App } from '../App';

export function WorkbenchWorkspace() {
  return <App />;
}
```

`dashboard/src/main.tsx`

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { DashboardShell } from './shell/DashboardShell';
import './styles.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <DashboardShell />
  </React.StrictMode>
);
```

`dashboard/src/App.tsx`

```tsx
// No behavioral change in this task. Keep the current workbench implementation intact.
// Only ensure the exported component stays suitable for rendering inside WorkbenchWorkspace.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm exec vitest run tests/dashboard-shell.test.tsx -t "renders the new Daily Review Lite navigation item between 复盘队列 and 市场监控 and switches workspace via URL state"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/main.tsx \
  dashboard/src/shell/DashboardShell.tsx \
  dashboard/src/workspaces/WorkbenchWorkspace.tsx \
  dashboard/tests/dashboard-shell.test.tsx
git commit -m "feat: add dashboard shell for workspace switching"
```

### Task 2: Mount Daily Review Lite As A Real Dashboard Workspace

**Files:**
- Create: `dashboard/src/workspaces/DailyReviewLiteWorkspace.tsx`
- Modify: `dashboard/src/shell/DashboardShell.tsx`
- Modify: `dashboard/src/pages/DailyReviewLitePage.tsx`
- Modify: `dashboard/tests/dashboard-shell.test.tsx`
- Test: `dashboard/tests/daily-review-lite-page.test.tsx`

- [ ] **Step 1: Write the failing workspace-entry tests**

```tsx
it('opens Lite workspace directly from URL and passes through trade_date', async () => {
  window.history.replaceState({}, '', '/?workspace=daily-review-lite&trade_date=2026-06-19');
  render(<DashboardShell />);

  await waitFor(() => {
    expect(screen.getByRole('heading', { name: 'Daily Review Lite' })).toBeInTheDocument();
  });

  expect(screen.getByLabelText('Trade Date')).toHaveValue('2026-06-19');
});
```

```tsx
it('prefers dashboard trade_date query state when loading the Lite page', async () => {
  window.history.replaceState({}, '', '/?trade_date=2026-06-19');
  apiMocks.fetchDailyReviewLite.mockReturnValueOnce(createDeferred<DailyReviewLiteResponse>().promise);

  render(<DailyReviewLitePage />);

  expect(apiMocks.fetchDailyReviewLite).toHaveBeenCalledWith('2026-06-19', undefined);
  expect(screen.getByLabelText('Trade Date')).toHaveValue('2026-06-19');
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pnpm exec vitest run tests/dashboard-shell.test.tsx -t "opens Lite workspace directly from URL and passes through trade_date"
pnpm exec vitest run tests/daily-review-lite-page.test.tsx -t "prefers dashboard trade_date query state when loading the Lite page"
```

Expected:
- `dashboard-shell.test.tsx`: FAIL because `DailyReviewLiteWorkspace` does not exist or does not read `trade_date`.
- `daily-review-lite-page.test.tsx`: FAIL because the page is not yet explicitly integrated with dashboard entry semantics.

- [ ] **Step 3: Write minimal implementation**

`dashboard/src/workspaces/DailyReviewLiteWorkspace.tsx`

```tsx
import { DailyReviewLitePage } from '../pages/DailyReviewLitePage';

export function DailyReviewLiteWorkspace() {
  const tradeDate = new URL(window.location.href).searchParams.get('trade_date') ?? undefined;
  return <DailyReviewLitePage initialTradeDate={tradeDate} />;
}
```

`dashboard/src/shell/DashboardShell.tsx`

```tsx
import { useEffect, useState } from 'react';
import { DailyReviewLiteWorkspace } from '../workspaces/DailyReviewLiteWorkspace';

export function DashboardShell() {
  const [currentWorkspace, setCurrentWorkspace] = useState(readWorkspaceFromUrl());

  useEffect(() => {
    function handlePopState() {
      setCurrentWorkspace(readWorkspaceFromUrl());
    }

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // keep the rest of Task 1 implementation and render DailyReviewLiteWorkspace for the Lite branch
}
```

`dashboard/src/pages/DailyReviewLitePage.tsx`

```tsx
// Keep existing precedence logic, but make sure `initialTradeDate`
// remains the highest-priority source when passed by DashboardShell.
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pnpm exec vitest run tests/dashboard-shell.test.tsx -t "opens Lite workspace directly from URL and passes through trade_date"
pnpm exec vitest run tests/daily-review-lite-page.test.tsx -t "prefers dashboard trade_date query state when loading the Lite page"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/shell/DashboardShell.tsx \
  dashboard/src/workspaces/DailyReviewLiteWorkspace.tsx \
  dashboard/src/pages/DailyReviewLitePage.tsx \
  dashboard/tests/dashboard-shell.test.tsx \
  dashboard/tests/daily-review-lite-page.test.tsx
git commit -m "feat: mount daily review lite as dashboard workspace"
```

### Task 3: Add Shell Styles And Preserve Existing Workbench Layout

**Files:**
- Modify: `dashboard/src/styles.css`
- Modify: `dashboard/tests/dashboard-shell.test.tsx`

- [ ] **Step 1: Write the failing shell layout test**

```tsx
it('marks Daily Review Lite as selected in the shell and keeps the nav/content structure', async () => {
  window.history.replaceState({}, '', '/?workspace=daily-review-lite');
  render(<DashboardShell />);

  const nav = screen.getByLabelText('Workspace navigation');
  expect(nav).toBeInTheDocument();

  const liteButton = screen.getByRole('button', { name: 'Daily Review Lite' });
  expect(liteButton).toHaveAttribute('aria-pressed', 'true');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm exec vitest run tests/dashboard-shell.test.tsx -t "marks Daily Review Lite as selected in the shell and keeps the nav/content structure"`

Expected: FAIL because the shell buttons are not yet exposing selected-state semantics.

- [ ] **Step 3: Write minimal implementation**

`dashboard/src/shell/DashboardShell.tsx`

```tsx
<button
  key={workspace.key}
  type="button"
  aria-pressed={currentWorkspace === workspace.key}
  onClick={() => updateWorkspace(workspace.key)}
>
  {workspace.label}
</button>
```

`dashboard/src/styles.css`

```css
.dashboard-shell {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  min-height: 100vh;
}

.dashboard-shell-nav {
  display: grid;
  gap: 8px;
  align-content: start;
  padding: 16px;
  border-right: 1px solid #d9dee7;
  background: #ffffff;
}

.dashboard-shell-nav button[aria-pressed='true'] {
  background: #edf4ff;
  border-color: #9ab3d5;
}

.dashboard-shell-content {
  min-width: 0;
}

@media (max-width: 900px) {
  .dashboard-shell {
    grid-template-columns: 1fr;
  }

  .dashboard-shell-nav {
    border-right: 0;
    border-bottom: 1px solid #d9dee7;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm exec vitest run tests/dashboard-shell.test.tsx -t "marks Daily Review Lite as selected in the shell and keeps the nav/content structure"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/shell/DashboardShell.tsx \
  dashboard/src/styles.css \
  dashboard/tests/dashboard-shell.test.tsx
git commit -m "feat: style dashboard workspace shell"
```

### Task 4: Add Dashboard-Level Browser Smoke For Lite Entry

**Files:**
- Create: `dashboard/tests/dashboard-lite-workspace.spec.ts`
- Modify: `dashboard/package.json`
- Modify: `dashboard/playwright.config.ts`

- [ ] **Step 1: Write the failing browser smoke**

```ts
import { expect, test } from '@playwright/test';

test('enters Daily Review Lite from the dashboard shell', async ({ page }) => {
  await page.route('/api/daily-review-lite**', async (route) => {
    await route.fulfill({
      json: {
        trade_date: '2026-06-20',
        state: 'ready',
        selected_run: {
          run_id: 'daily_review_v1:2026-06-20:abc123',
          report_type: 'daily_review_v1',
          status: 'success',
          updated_at: '2026-06-20T22:00:00Z',
          source: 'fallback',
          artifact_health: 'healthy',
          artifact_health_detail: { daily_review_json: 'healthy' }
        },
        summary: {
          market_status: 'neutral',
          overall_position_bias: 'balanced',
          lhb_conclusion: 'observe',
          mid_trend_conclusion: 'hold',
          technical_bottleneck_conclusion: 'watch',
          must_review_asset_ids: [],
          warning_count: 0
        },
        warnings: [],
        missing_sources: [],
        sections: {
          data_readiness: { status: 'success', warnings: [], sources: {} },
          market_review: { status: 'success', warnings: [], payload: {} },
          strategy_summaries: {
            lhb: { strategy_id: 'lhb', status: 'success', warnings: [], summary: {}, top_items: [] },
            mid_trend: { strategy_id: 'mid_trend', status: 'success', warnings: [], summary: {}, top_items: [] },
            technical_bottleneck: {
              strategy_id: 'technical_bottleneck',
              status: 'success',
              warnings: [],
              summary: {},
              top_items: []
            }
          },
          holding_review: { status: 'empty', warnings: [], items: [] },
          operator_plan: { status: 'success', warnings: [], payload: {} },
          next_day_checklist: {
            status: 'success',
            warnings: [],
            must_review_items: [],
            forbidden_actions: [],
            data_warnings: []
          }
        },
        artifacts: []
      }
    });
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'Daily Review Lite' }).click();

  await expect(page.getByRole('heading', { name: 'Daily Review Lite' })).toBeVisible();
  await expect(page.getByText('Loaded from fallback package scan')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Strategy Summaries' })).toBeVisible();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm exec playwright test tests/dashboard-lite-workspace.spec.ts`

Expected: FAIL because the dashboard shell/browser entry path does not yet exist or the new spec/script wiring is missing.

- [ ] **Step 3: Write minimal implementation**

`dashboard/package.json`

```json
{
  "scripts": {
    "dev": "vite --host 127.0.0.1 --port ${PLAYWRIGHT_PORT:-5174}",
    "test:e2e": "playwright test tests/app-smoke.spec.ts",
    "test:e2e:lite": "CI=1 PLAYWRIGHT_PORT=4174 playwright test tests/daily-review-lite.spec.ts",
    "test:e2e:dashboard-lite": "CI=1 PLAYWRIGHT_PORT=4274 playwright test tests/dashboard-lite-workspace.spec.ts"
  }
}
```

`dashboard/playwright.config.ts`

```ts
const playwrightPort = process.env.PLAYWRIGHT_PORT ?? '5174';
const baseURL = `http://127.0.0.1:${playwrightPort}`;

export default defineConfig({
  use: {
    baseURL,
    trace: 'on-first-retry'
  },
  webServer: {
    command: `PLAYWRIGHT_PORT=${playwrightPort} pnpm dev`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120000
  }
});
```

The new Playwright spec from Step 1 is the browser-level implementation for this task.

- [ ] **Step 4: Run focused verification**

Run from `dashboard`:

```bash
pnpm exec vitest run tests/client.test.ts
pnpm exec vitest run tests/daily-review-lite-page.test.tsx
pnpm exec vitest run tests/dashboard-shell.test.tsx
pnpm run test:e2e:lite
pnpm run test:e2e:dashboard-lite
pnpm build
```

Expected:
- client tests: PASS
- Lite page tests: PASS
- dashboard shell tests: PASS
- Lite smoke: PASS
- dashboard-entry Lite smoke: PASS
- build: PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard/package.json \
  dashboard/playwright.config.ts \
  dashboard/tests/dashboard-lite-workspace.spec.ts
git commit -m "test: add dashboard lite workspace smoke"
```

## Self-Review

### Spec coverage

- New peer workspace and nav order: covered by Task 1 shell test and shell implementation
- Direct entry into Lite view: covered by Task 2
- URL-backed `workspace` and `trade_date`: covered by Tasks 1 and 2
- Keep old `复盘队列` intact and avoid deep coupling: preserved by shell/workspace split in Tasks 1 and 2
- Lite page remains dedicated read-only module: preserved by Task 2 architecture and existing page contract
- Dashboard-level tests and browser smoke: covered by Task 4
- Scoped styling and responsive behavior: covered by Task 3

### Placeholder scan

- No `TODO`, `TBD`, or “similar to Task N” placeholders remain.
- Every task includes exact file paths, concrete commands, and pass/fail expectations.

### Type consistency

- Workspace key used consistently as `daily-review-lite`
- Dashboard shell delegates Lite rendering to `DailyReviewLiteWorkspace`
- `DailyReviewLitePage` continues to accept `initialTradeDate`
- Browser smoke and Vitest plan both use the existing Lite response shape
