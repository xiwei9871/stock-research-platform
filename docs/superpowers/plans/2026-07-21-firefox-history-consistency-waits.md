# Firefox History Consistency Waits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make route-context acceptance assertions wait for asynchronous same-document history traversal so Chromium and Firefox evaluate Back/Forward journeys with the same contract.

**Architecture:** Do not change product routing until a retrying assertion proves a real product defect remains. Reuse the existing bounded `waitForConsistency` polling primitive inside `expectRouteContext`; after the expected location is observed, retain the current exact path/asset/source mismatch diagnostics.

**Tech Stack:** Playwright, TypeScript, Chromium, Firefox.

---

## File Structure

- `dashboard/tests/e2e/assertions/consistency.ts`: adds bounded route synchronization without weakening exact checks.
- `dashboard/tests/e2e/p0/consistency-contract.spec.ts`: proves delayed history traversal and final mismatch evidence.
- `dashboard/tests/e2e/p0/search-stock.spec.ts`: existing Firefox reproduction.
- `dashboard/tests/e2e/p0/research-handoffs.spec.ts`: existing theme/tech Firefox reproductions.

### Task 1: Reproduce The Timing Boundary In A Contract Test

**Files:**
- Modify: `dashboard/tests/e2e/p0/consistency-contract.spec.ts`

- [ ] **Step 1: Add a delayed same-document history test**

Use the existing contract-page helper, then execute:

```typescript
await page.evaluate(() => {
  window.history.replaceState({}, '', '/');
  window.history.pushState({}, '', '/stock/300203.SZ?source=search');
  window.setTimeout(() => window.history.back(), 50);
});

await expectRouteContext(page, { path: /^\/$/ });
```

The assertion must pass only after the delayed traversal reaches `/`.

- [ ] **Step 2: Preserve a terminal mismatch test**

Call `expectRouteContext` for an impossible route and assert the final error still contains:

```text
Route context mismatch:
- path: expected /^\/expected$/, rendered /actual
```

- [ ] **Step 3: Run the contract and verify RED**

```bash
cd dashboard
PLAYWRIGHT_PROFILE=mock pnpm exec playwright test tests/e2e/p0/consistency-contract.spec.ts \
  --grep "delayed same-document history"
```

Expected: FAIL because `expectRouteContext` samples `page.url()` once.

### Task 2: Add A Bounded Route Wait

**Files:**
- Modify: `dashboard/tests/e2e/assertions/consistency.ts`

- [ ] **Step 1: Extract a route snapshot reader**

```typescript
function routeSnapshot(page: Page) {
  const url = new URL(page.url());
  const pathname = decodedPathname(url);
  const assetMatch = pathname.match(/(?:^|\/)stock\/([^/]+)$/);
  return {
    pathname,
    assetId: assetMatch?.[1] ?? '',
    source: url.searchParams.get('source') ?? ''
  };
}
```

- [ ] **Step 2: Poll for the complete expected tuple**

At the start of `expectRouteContext`, call `waitForConsistency` with a predicate that requires path, optional asset ID, and optional source all to match. Then read one final snapshot and run the existing mismatch builder unchanged.

Do not increase the global timeout, catch product errors, or replace exact route matching with substring matching.

- [ ] **Step 3: Run focused Mock contracts**

```bash
cd dashboard
PLAYWRIGHT_PROFILE=mock pnpm exec playwright test \
  tests/e2e/p0/consistency-contract.spec.ts \
  tests/e2e/p0/search-stock.spec.ts \
  tests/e2e/p0/research-handoffs.spec.ts \
  --project=chromium-desktop
```

Expected: PASS.

- [ ] **Step 4: Commit the synchronization helper**

```bash
git add dashboard/tests/e2e/assertions/consistency.ts dashboard/tests/e2e/p0/consistency-contract.spec.ts
git commit -m "test: wait for cross-browser history context"
```

### Task 3: Prove Or Reclassify The Firefox Root

**Files:**
- Modify product routing only if this task still fails after Task 2.

- [ ] **Step 1: Run the exact Firefox reproductions**

```bash
cd dashboard
PLAYWRIGHT_PROFILE=audit \
PLAYWRIGHT_DASHBOARD_PORT=5374 \
PLAYWRIGHT_API_PORT=8966 \
pnpm exec playwright test \
  tests/e2e/p0/search-stock.spec.ts \
  tests/e2e/p0/research-handoffs.spec.ts \
  --grep "global search restores|theme company handoff preserves|technology-bottleneck review universe hands" \
  --project=firefox-desktop
```

Expected: PASS. If it passes, close the root as test synchronization and do not change `AppShell.tsx`.

- [ ] **Step 2: If a failure remains, capture history state before product changes**

Attach `window.location.href`, `window.history.length`, and `window.history.state` before the handoff, after the handoff, after reload, and after Back. Open a new product plan only when the trace proves the location itself does not traverse; do not fold such a fix into this test-helper commit.

- [ ] **Step 3: Run the full P0 Mock and Firefox audit subset**

```bash
cd dashboard
rtk pnpm test:e2e:p0
PLAYWRIGHT_PROFILE=audit pnpm exec playwright test tests/e2e/p0 --project=firefox-desktop
```

Expected: all P0 tests pass on both engines.

