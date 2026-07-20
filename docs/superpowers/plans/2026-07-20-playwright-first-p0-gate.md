# Playwright-First P0 Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the shared Playwright projects, route model, runtime evidence, and deterministic P0 browser journeys that become the mandatory pull-request gate.

**Architecture:** Keep Vitest authoritative for pure route and state helpers, then exercise every critical user handoff in Playwright with deterministic API fixtures. Replace the current collection of unrelated top-level full-flow files with a shared fixture/assertion layer while retaining the existing tests until each covered behavior has migrated.

**Tech Stack:** React 19, TypeScript, Vitest, Playwright, Vite, GitHub Actions, FastAPI-compatible JSON fixtures.

---

## File Structure

- `dashboard/src/navigation/platformRoutes.ts`: canonical workspace paths, route parsing, stock-code normalization, and serialized handoff context.
- `dashboard/tests/platform-routes.test.ts`: pure route, legacy-code, query, and browser-state contracts.
- `dashboard/tests/e2e/fixtures/test.ts`: Playwright fixture that captures console, page, request, and API-route evidence.
- `dashboard/tests/e2e/fixtures/mockPlatformApi.ts`: small route-map based deterministic API installer.
- `dashboard/tests/e2e/fixtures/officialStrategies.ts`: the three official strategy fixtures and publication identities used by P0 tests.
- `dashboard/tests/e2e/assertions/runtime.ts`: fatal-console, critical-request, and horizontal-overflow assertions.
- `dashboard/tests/e2e/assertions/consistency.ts`: route, restoration, API/UI, and publication assertions.
- `dashboard/tests/e2e/p0/*.spec.ts`: user-journey tests grouped by authentication, search, research handoff, publication, history, failure isolation, and mobile behavior.
- `dashboard/playwright.config.ts`: project, profile, reporter, trace, and server configuration.
- `dashboard/package.json`: stable commands for P0 Mock, legacy, Real, Sandbox, Audit, and EOD profiles.
- `.github/workflows/platform-smoke.yml`: Chromium P0 browser gate and artifact upload.

### Task 1: Canonical Route Model

**Files:**
- Create: `dashboard/src/navigation/platformRoutes.ts`
- Create: `dashboard/tests/platform-routes.test.ts`
- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Write failing pure route tests**

Cover `/`, every primary workspace path, theme detail paths, the legacy technology-bottleneck path, stock codes with and without exchange suffixes, URL-encoded handoff fields, and an invalid path falling back to home.

```ts
expect(parsePlatformLocation('/review-queue', '')).toMatchObject({ workspace: 'reviewQueue' });
expect(parsePlatformLocation('/stock/600519.SH', '?source=search&q=600519')).toMatchObject({
  workspace: 'stock',
  assetId: '600519.SH',
  sourceWorkspace: 'search',
  query: '600519'
});
expect(parsePlatformLocation('/tech-bottleneck/stock/300760.SZ', '?source=theme_research')).toMatchObject({
  workspace: 'stock',
  assetId: '300760.SZ',
  sourceWorkspace: 'themeResearch'
});
expect(parsePlatformLocation('/tech-bottleneck/watchlist-review', '')).toMatchObject({
  workspace: 'techBottleneckReviewUniverse',
  canonicalPath: '/research/tech-bottleneck/review-universe'
});
expect(stockCodeToAssetId('600519')).toBe('600519.SH');
expect(stockCodeToAssetId('300760')).toBe('300760.SZ');
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `cd dashboard && rtk pnpm test -- platform-routes.test.ts`

Expected: FAIL because `src/navigation/platformRoutes.ts` does not exist.

- [ ] **Step 3: Implement the route module**

Define exported `WorkspaceMode`, `PlatformLocation`, `WORKSPACE_PATHS`, `parsePlatformLocation`, `pathForWorkspace`, `stockCodeToAssetId`, and `stockPath`. All primary workspaces receive canonical paths:

```ts
export const WORKSPACE_PATHS = {
  home: '/',
  reviewQueue: '/review-queue',
  dailyReview: '/daily-review',
  market: '/market-monitor',
  news: '/news',
  researchReports: '/research-reports',
  watchlist: '/watchlist',
  themeResearch: '/theme-research',
  techBottleneckReviewUniverse: '/research/tech-bottleneck/review-universe',
  dataToBriefDocling90: '/research/data-to-brief/docling-90',
  factors: '/factor-lab',
  strategyLab: '/strategy-lab',
  generatedReports: '/generated-reports',
  userManagement: '/admin/users'
} as const;
```

Keep the existing `/tech-bottleneck/stock/{code}` route as a supported compatibility route and add `/stock/{assetId}` as the canonical general stock route. Decode only known query fields and ignore unknown query fields.

- [ ] **Step 4: Integrate routes into AppShell**

Replace private route constants and `workspaceModeFromPath` with the shared module. Every workspace navigation uses `history.pushState`, the `popstate` handler reparses the complete location, and the legacy review path uses `replaceState` once.

- [ ] **Step 5: Run focused regression tests**

Run: `cd dashboard && rtk pnpm test -- platform-routes.test.ts app-shell.test.tsx tech-bottleneck-route.test.tsx theme-research-route.test.tsx`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/navigation/platformRoutes.ts dashboard/src/components/AppShell.tsx dashboard/tests/platform-routes.test.ts dashboard/tests/app-shell.test.tsx
git commit -m "feat: canonicalize dashboard workspace routes"
```

### Task 2: Browser History And Search-State Restoration

**Files:**
- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/src/components/GlobalSearchBox.tsx`
- Modify: `dashboard/tests/global-search-box.test.tsx`
- Modify: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Write failing state-restoration tests**

Prove that search query and highlighted result are restored after entering a stock and navigating back, and that refresh reconstructs the stock entity and source context from the URL.

```ts
expect(window.location.pathname).toBe('/stock/CN%3ASH%3A600519');
expect(window.location.search).toContain('source=search');
window.history.back();
window.dispatchEvent(new PopStateEvent('popstate'));
expect(screen.getByLabelText('Global search')).toHaveValue('600519');
```

- [ ] **Step 2: Verify RED**

Run: `cd dashboard && rtk pnpm test -- global-search-box.test.tsx app-shell.test.tsx`

Expected: FAIL because the search component clears local state and the existing stock handoff is not canonicalized in the URL.

- [ ] **Step 3: Make search state controlled**

Add `query`, `onQueryChange`, and `onResultOpened` props to `GlobalSearchBox`. Store `{ searchQuery }` in the current home history entry before pushing the stock path. On `popstate`, restore `window.history.state.searchQuery ?? ''`. Do not persist API payloads or passwords in history state.

- [ ] **Step 4: Reconstruct stock handoff from URL**

Use `parsePlatformLocation` on initial render, refresh, and `popstate`. The parsed URL is the source of truth for asset ID and source workspace; in-memory state may only add non-serializable UI details.

- [ ] **Step 5: Re-run focused tests**

Run: `cd dashboard && rtk pnpm test -- global-search-box.test.tsx app-shell.test.tsx platform-routes.test.ts`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/components/AppShell.tsx dashboard/src/components/GlobalSearchBox.tsx dashboard/tests/global-search-box.test.tsx dashboard/tests/app-shell.test.tsx
git commit -m "feat: restore dashboard navigation state"
```

### Task 3: Logout And Authentication Journey

**Files:**
- Modify: `dashboard/src/components/DashboardAuthRoot.tsx`
- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/tests/auth-root.test.tsx`
- Modify: `dashboard/tests/app-shell.test.tsx`
- Create: `dashboard/tests/e2e/p0/auth.spec.ts`

- [ ] **Step 1: Write failing unit tests**

Add tests proving the signed-in shell shows the current display name and a `退出登录` button, a successful logout returns to `LoginView`, and a failed logout keeps the user signed in with an alert.

- [ ] **Step 2: Verify RED**

Run: `cd dashboard && rtk pnpm test -- auth-root.test.tsx app-shell.test.tsx`

Expected: FAIL because `DashboardAuthRoot` does not call `logoutDashboardUser` and `AppShell` exposes no logout control.

- [ ] **Step 3: Implement the explicit logout contract**

Pass `currentUser`, `onLogout`, and `logoutPending` into `AppShell`. Render the user name and logout button in `.platform-topbar`. `DashboardAuthRoot` calls `logoutDashboardUser`, clears user state only on success, and renders a role alert on failure.

- [ ] **Step 4: Add deterministic Playwright auth coverage**

The Playwright spec intercepts `/api/auth/me`, `/api/auth/login`, and `/api/auth/logout`; it tests unauthenticated login, invalid login, successful login, logout, session-expiry event behavior, and the absence of the admin navigation item for a normal user.

- [ ] **Step 5: Run unit and browser tests**

Run: `cd dashboard && rtk pnpm test -- auth-root.test.tsx app-shell.test.tsx && rtk pnpm exec playwright test tests/e2e/p0/auth.spec.ts`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/components/DashboardAuthRoot.tsx dashboard/src/components/AppShell.tsx dashboard/tests/auth-root.test.tsx dashboard/tests/app-shell.test.tsx dashboard/tests/e2e/p0/auth.spec.ts
git commit -m "feat: add explicit dashboard logout flow"
```

### Task 4: Playwright Projects, Profiles, And CI Gate

**Files:**
- Create: `dashboard/playwright.projects.ts`
- Create: `dashboard/tests/playwright-projects.test.ts`
- Modify: `dashboard/playwright.config.ts`
- Modify: `dashboard/package.json`
- Modify: `.github/workflows/platform-smoke.yml`
- Modify: `.gitignore`

- [ ] **Step 1: Write failing project-configuration tests**

Test that Mock projects are Chromium desktop plus a mobile project restricted to tests tagged `@mobile`, Audit adds Firefox and selective WebKit, EOD contains only Chromium desktop, and only profiles that need real APIs start the uvicorn server.

- [ ] **Step 2: Verify RED**

Run: `cd dashboard && rtk pnpm test -- playwright-projects.test.ts`

Expected: FAIL because the project builder does not exist.

- [ ] **Step 3: Implement profile-aware configuration**

Export `buildProjects(profile)` and `profileNeedsApi(profile)`. Configure `forbidOnly` in CI, `trace: 'retain-on-failure'`, `screenshot: 'only-on-failure'`, `video: 'retain-on-failure'`, HTML plus JSON reporters, and `dashboard/test-results/<profile>` as the output directory.

Add scripts:

```json
{
  "test:e2e": "PLAYWRIGHT_PROFILE=legacy playwright test tests/*.spec.ts",
  "test:e2e:p0": "PLAYWRIGHT_PROFILE=mock playwright test tests/e2e/p0",
  "test:e2e:real": "PLAYWRIGHT_PROFILE=real playwright test tests/e2e/real",
  "test:e2e:sandbox": "PLAYWRIGHT_PROFILE=sandbox playwright test tests/e2e/sandbox",
  "test:e2e:audit": "PLAYWRIGHT_PROFILE=audit playwright test tests/e2e/p0 tests/e2e/real tests/e2e/audit tests/e2e/visual",
  "test:e2e:eod": "PLAYWRIGHT_PROFILE=eod playwright test tests/e2e/eod"
}
```

- [ ] **Step 4: Add the PR browser job**

Install Chromium with `pnpm exec playwright install --with-deps chromium`, run `pnpm test:e2e:p0`, and upload `dashboard/playwright-report` plus `dashboard/test-results/mock` on failure. The Mock profile starts Vite only and must not require Python or a database.

- [ ] **Step 5: Run configuration, P0, and build checks**

Run: `cd dashboard && rtk pnpm test -- playwright-projects.test.ts && rtk pnpm test:e2e:p0 && rtk pnpm build`

Expected: all commands exit 0.

- [ ] **Step 6: Commit**

```bash
git add dashboard/playwright.projects.ts dashboard/playwright.config.ts dashboard/package.json dashboard/tests/playwright-projects.test.ts .github/workflows/platform-smoke.yml .gitignore
git commit -m "test: add playwright p0 project gate"
```

### Task 5: Shared Mock API And Runtime Evidence

**Files:**
- Create: `dashboard/tests/e2e/fixtures/test.ts`
- Create: `dashboard/tests/e2e/fixtures/mockPlatformApi.ts`
- Create: `dashboard/tests/e2e/assertions/runtime.ts`
- Create: `dashboard/tests/e2e/p0/runtime-contract.spec.ts`

- [ ] **Step 1: Write the failing runtime-contract spec**

The spec intentionally emits a page error, a critical request failure, and an unhandled `/api/**` request in separate tests, then marks each expected failure with `test.fail`. A clean control test must pass.

- [ ] **Step 2: Verify RED**

Run: `cd dashboard && rtk pnpm test:e2e:p0 --grep @runtime-contract`

Expected: the clean control demonstrates that the shared fixture is not yet installed and the expected-failure tests do not fail for the intended structured reasons.

- [ ] **Step 3: Implement the fixture and ledger**

Create an extended `test` fixture that records:

```ts
type RuntimeEvidence = {
  consoleErrors: string[];
  pageErrors: string[];
  failedRequests: Array<{ method: string; url: string; failure: string }>;
  unhandledApiRoutes: string[];
};
```

`installMockPlatformApi(page, routes)` accepts a map from `METHOD pathname` to `{ status, json }`; unmatched `/api/**` requests receive status 599 and are appended to `unhandledApiRoutes`. Known tests may register an explicit expected-error allowlist.

- [ ] **Step 4: Add reusable runtime assertions**

Implement `expectNoFatalRuntimeErrors`, `expectNoUnhandledApiRoutes`, and `expectNoHorizontalOverflow`. Include expected failure evidence in `testInfo.attach` as `runtime-evidence.json`.

- [ ] **Step 5: Re-run the runtime contract**

Run: `cd dashboard && rtk pnpm test:e2e:p0 --grep @runtime-contract`

Expected: clean control passes and all `test.fail` cases fail for the named runtime contract.

- [ ] **Step 6: Commit**

```bash
git add dashboard/tests/e2e/fixtures dashboard/tests/e2e/assertions/runtime.ts dashboard/tests/e2e/p0/runtime-contract.spec.ts
git commit -m "test: capture playwright runtime evidence"
```

### Task 6: Shared Consistency Assertions

**Files:**
- Create: `dashboard/tests/e2e/fixtures/officialStrategies.ts`
- Create: `dashboard/tests/e2e/assertions/consistency.ts`
- Create: `dashboard/tests/e2e/p0/consistency-contract.spec.ts`

- [ ] **Step 1: Write contract tests for all four assertions**

Use a small static test page and deterministic JSON to prove success and failure messages for route context, restored state, API/UI values, and publication identity.

- [ ] **Step 2: Verify RED**

Run: `cd dashboard && rtk pnpm test:e2e:p0 --grep @consistency-contract`

Expected: FAIL because the assertion module is missing.

- [ ] **Step 3: Implement the assertions**

Required signatures:

```ts
expectRouteContext(page, expected: { path: RegExp; assetId?: string; source?: string }): Promise<void>;
expectStateRestored(page, expected: { searchQuery?: string; selectedText?: string }): Promise<void>;
expectApiUiConsistency(actual: number | string | null, locator: Locator, rule: 'number' | 'ratio-as-percent' | 'percent'): Promise<void>;
expectPublicationConsistency(card: Locator, expected: { contractId: string; publishId: string; tradeDate: string; totalReturnPct: number }): Promise<void>;
```

For `ratio-as-percent`, multiply by 100 exactly once. Failure messages include the raw value, rendered text, rule, strategy ID, and publish ID.

- [ ] **Step 4: Create official strategy fixtures**

Include `lhb_shortline`, `mid_trend`, and `tech_bottleneck`, each with a distinct contract ID, publish ID, artifact version, performance date, and total return. Set LHB to `52.40%`; no fixture may use `175.29%`.

- [ ] **Step 5: Run assertion contracts**

Run: `cd dashboard && rtk pnpm test:e2e:p0 --grep @consistency-contract`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard/tests/e2e/fixtures/officialStrategies.ts dashboard/tests/e2e/assertions/consistency.ts dashboard/tests/e2e/p0/consistency-contract.spec.ts
git commit -m "test: add browser consistency assertions"
```

### Task 7: P0 Search And Research Handoffs

**Files:**
- Create: `dashboard/tests/e2e/p0/search-stock.spec.ts`
- Create: `dashboard/tests/e2e/p0/research-handoffs.spec.ts`
- Modify: `dashboard/tests/theme-research-full-flow.spec.ts`
- Modify: `dashboard/tests/theme-research-workflow-integration.spec.ts`

- [ ] **Step 1: Write failing P0 journeys**

Add `@p0 @mock` tests for global search to stock and back; theme to company to stock and back; technology-bottleneck review universe to stock; supported legacy/current security code routes; direct deep-link refresh; and browser back/forward.

- [ ] **Step 2: Verify RED**

Run: `cd dashboard && rtk pnpm test:e2e:p0 --grep @handoff`

Expected: failures identify missing canonical routes or state restoration rather than unhandled APIs.

- [ ] **Step 3: Register minimal deterministic APIs**

Use `installMockPlatformApi` for authentication, readiness, platform summary, search, asset profile/bars/news/reports, theme decomposition, and technology-bottleneck universe. Do not copy the 800-line `mockDashboardApi`; only register endpoints observed in each journey.

- [ ] **Step 4: Assert context and history**

Use `expectRouteContext` after every handoff and `expectStateRestored` after every return. Verify refresh produces the same asset and source labels.

- [ ] **Step 5: Retire duplicated assertions from legacy specs**

Keep non-P0 visual and deep-research checks in the existing files, but remove only the exact handoff assertions now covered by the new P0 specs.

- [ ] **Step 6: Run the P0 and affected legacy specs**

Run: `cd dashboard && rtk pnpm test:e2e:p0 --grep @handoff && PLAYWRIGHT_PROFILE=legacy rtk pnpm exec playwright test tests/theme-research-full-flow.spec.ts tests/theme-research-workflow-integration.spec.ts`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add dashboard/tests/e2e/p0/search-stock.spec.ts dashboard/tests/e2e/p0/research-handoffs.spec.ts dashboard/tests/theme-research-full-flow.spec.ts dashboard/tests/theme-research-workflow-integration.spec.ts
git commit -m "test: cover p0 dashboard handoffs"
```

### Task 8: P0 Review Queue And Strategy Publication

**Files:**
- Modify: `src/stock_research/dashboard/backtests.py`
- Modify: `tests/test_dashboard_backtests.py`
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/components/HomeCockpit.tsx`
- Modify: `dashboard/src/components/ReviewQueueWorkspace.tsx`
- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/src/components/StrategyLabWorkspace.tsx`
- Modify: `dashboard/tests/home-cockpit.test.tsx`
- Modify: `dashboard/tests/review-queue-workspace.test.tsx`
- Modify: `dashboard/tests/app-shell.test.tsx`
- Modify: `dashboard/tests/backtest-lab-workspace.test.tsx`
- Create: `dashboard/tests/e2e/p0/review-publication.spec.ts`

- [ ] **Step 1: Write failing backend and frontend tests for `publish_id`**

Prove that strategy catalog `latest_metrics.publish_id`, home cards, and selected review-queue items expose the same explicit publish ID. Do not infer identity from a filesystem path in browser code.

- [ ] **Step 2: Verify RED**

Run: `rtk .venv/bin/pytest tests/test_dashboard_backtests.py -q && cd dashboard && rtk pnpm test -- home-cockpit.test.tsx review-queue-workspace.test.tsx`

Expected: frontend/backend assertions fail because `_publication_metadata_metrics` currently drops `publish_id` and the UI does not render it.

- [ ] **Step 3: Project and render publication identity**

Add `publish_id` to `_publication_metadata_metrics`, `StrategyCatalogItem.latest_metrics`, the home formal-contract region, and the review-queue formal-contract region. Render the label `发布编号`.

- [ ] **Step 4: Add the P0 publication journey**

Make each home strategy card expose an accessible `打开策略 <name>` control. The control navigates to `/strategy-lab?strategy_id=<id>`; `AppShell` parses the query and passes `initialStrategyId` to `StrategyLabWorkspace`, which selects the matching official strategy without starting a backtest. Mock all three official strategies and a review queue using the same publish IDs. Assert total return, contract ID, publish ID, artifact version, performance date, and contract status across home, the selected strategy page, and review queue. Add a negative fixture where LHB raw ratio `0.524` is rendered as `+52.40%`; assert `+175.29%` is absent.

- [ ] **Step 5: Run focused backend, frontend, and Playwright tests**

Run: `rtk .venv/bin/pytest tests/test_dashboard_backtests.py tests/test_dashboard_review_queue.py -q && cd dashboard && rtk pnpm test -- home-cockpit.test.tsx review-queue-workspace.test.tsx app-shell.test.tsx backtest-lab-workspace.test.tsx && rtk pnpm test:e2e:p0 --grep @publication`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/dashboard/backtests.py tests/test_dashboard_backtests.py dashboard/src/api/types.ts dashboard/src/components/HomeCockpit.tsx dashboard/src/components/ReviewQueueWorkspace.tsx dashboard/src/components/AppShell.tsx dashboard/src/components/StrategyLabWorkspace.tsx dashboard/tests/home-cockpit.test.tsx dashboard/tests/review-queue-workspace.test.tsx dashboard/tests/app-shell.test.tsx dashboard/tests/backtest-lab-workspace.test.tsx dashboard/tests/e2e/p0/review-publication.spec.ts
git commit -m "test: enforce browser publication consistency"
```

### Task 9: P0 Failure Isolation, Mobile, And Final Gate

**Files:**
- Create: `dashboard/tests/e2e/p0/history-errors-mobile.spec.ts`
- Modify: `dashboard/tests/app-smoke.spec.ts`
- Modify: `dashboard/tests/platform-full-flow.spec.ts`
- Modify: `docs/ops/platform-hardening-runbook.md`

- [ ] **Step 1: Write failure-isolation tests**

Test one failed strategy alongside two valid strategies, one noncritical API returning 503, a critical API returning 500 with a retry path, direct refresh of every P0 deep route, and the mobile P0 subset with no page-level horizontal overflow.

- [ ] **Step 2: Verify RED**

Run: `cd dashboard && rtk pnpm test:e2e:p0 --grep @failure-isolation`

Expected: any whole-app failure or unclassified critical request appears in structured runtime evidence.

- [ ] **Step 3: Make only proven minimal UI fixes**

For each failure, first add or retain the failing component test. Do not add blanket `catch` blocks; render the existing workspace-specific error or degraded state and keep unrelated official strategy cards usable.

- [ ] **Step 4: Reduce legacy smoke duplication**

Keep the broad workspace exploration in `platform-full-flow.spec.ts`, but change `app-smoke.spec.ts` to shell and responsive smoke only. Both files import shared runtime assertions and stop writing ad hoc screenshots to repository-absolute paths.

- [ ] **Step 5: Run the full Phase 1 gate**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_backtests.py tests/test_dashboard_review_queue.py -q
cd dashboard
rtk pnpm test
rtk pnpm build
rtk pnpm test:e2e:p0
PLAYWRIGHT_PROFILE=legacy rtk pnpm exec playwright test tests/app-smoke.spec.ts tests/platform-full-flow.spec.ts
```

Expected: all commands exit 0, no unhandled API route remains, and the P0 suite passes on Chromium desktop and mobile.

- [ ] **Step 6: Update the runbook**

Document the profile commands, evidence locations, CI gate, tag policy, and rule that P0 Mock is mandatory even when affected-test selection is introduced later.

- [ ] **Step 7: Commit**

```bash
git add dashboard/tests/e2e/p0/history-errors-mobile.spec.ts dashboard/tests/app-smoke.spec.ts dashboard/tests/platform-full-flow.spec.ts docs/ops/platform-hardening-runbook.md
git commit -m "test: complete playwright p0 gate"
```
