# P6 Dashboard Frontend Review

Date: 2026-05-30

## Status

P6-2 frontend workbench hardening is complete on `dashboard-workbench`.

Reviewed branch head before this review:

- `cb21732 docs: add p6 dashboard branch review`

## Scope

This review covers the dashboard frontend workbench only:

- loading states
- empty states
- desktop smoke layout
- mobile smoke layout
- frontend unit/build/e2e verification

It does not merge the dashboard branch into main.

## Changes

Frontend shell:

- `dashboard/src/App.tsx`
  - tracks overview loading state
  - tracks selected-asset loading state
  - shows chart empty state when no bars are available

Panels:

- `dashboard/src/components/TopNList.tsx`
  - shows `Loading TopN...`
  - shows empty state for selected date
- `dashboard/src/components/WatchlistList.tsx`
  - shows `Loading watchlist...`
  - shows empty state for selected date
- `dashboard/src/components/ReportPanel.tsx`
  - shows `Loading reports...`
  - shows empty state for selected date

Tests:

- `dashboard/tests/app-shell.test.tsx`
  - adds loading-state coverage
  - adds empty-state coverage
- `dashboard/tests/app-smoke.spec.ts`
  - extracts API route mocks
  - checks desktop horizontal overflow
  - adds mobile viewport smoke without horizontal overflow

## TDD Notes

The first frontend tests intentionally failed because the existing UI rendered
empty containers without visible loading or empty states:

- missing `Loading overview...`
- missing `Loading asset review...`
- missing `No TopN rows for selected date.`

After implementation, a second build failure exposed an incorrect Playwright
helper type in the smoke test. The helper now uses the official `Page` type from
`@playwright/test`.

## Verification

Frontend unit tests:

```bash
pnpm test
```

Result:

```text
Test Files  3 passed (3)
Tests  13 passed (13)
```

Frontend build:

```bash
pnpm build
```

Result:

```text
dist/index.html
dist/assets/index-k9wGPCTl.css
dist/assets/index-f0KHb724.js
built in 411ms
```

Browser smoke:

```bash
pnpm test:e2e
```

Result:

```text
2 passed
```

Backend dashboard regression:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_*.py -q
```

Result:

```text
27 passed, 2 warnings
```

## Generated Artifact Check

No generated frontend artifacts are tracked:

- `dashboard/dist/`
- `dashboard/test-results/`
- `dashboard/playwright-report/`
- `dashboard/node_modules/`

## Remaining P6 Items

Continue with P6-3/P6-4:

- rebase or merge dashboard branch onto latest P5 mainline
- resolve `src/stock_research/cli.py` intentionally
- keep Alpha191 work separate unless explicitly merged by its owner
- rerun integrated Python and frontend verification after rebase

## Merge Recommendation

Do not merge yet.

The frontend workbench is now hardened for loading, empty, desktop, and mobile
smoke states. Merge readiness still depends on mainline rebase, CLI conflict
resolution, and integrated regression evidence.
