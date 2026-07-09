# Market Monitor Heatmap To Stock Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Market Monitor's stock heatmap a clear entry point into Stock Workspace peer context.

**Architecture:** Reuse the existing stock heatmap API and `StockHeatmapPanel`. Add clearer hot-stock list semantics and verify AppShell carries market context into `StockWorkspace`.

**Tech Stack:** React, TypeScript, Vitest, Testing Library.

---

### Task 1: Market Monitor Hot Stock List Semantics

**Files:**
- Modify: `dashboard/src/components/market-monitor/StockHeatmapPanel.tsx`
- Modify: `dashboard/tests/stock-heatmap-panel.test.tsx`

- [ ] **Step 1: Write the failing test**

Add a test asserting that the panel renders a "热区个股 Top N" region and shows amount/change/group fields from the existing payload.

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
rtk pnpm --dir dashboard test -- tests/stock-heatmap-panel.test.tsx
```

Expected: fails because the hot-stock region label does not exist yet.

- [ ] **Step 3: Implement the minimal UI copy**

Update `StockHeatmapPanel` list label from generic sample wording to "热区个股 Top N", and include amount in each item.

- [ ] **Step 4: Run the test to verify it passes**

Run the same Vitest command.

### Task 2: Market Monitor To Stock Workspace Handoff

**Files:**
- Modify: `dashboard/tests/market-monitor-workspace.test.tsx`
- Modify: `dashboard/tests/app-shell.test.tsx` if AppShell coverage needs one explicit assertion.

- [ ] **Step 1: Write or tighten the failing test**

Assert that clicking a heatmap hot stock calls `onOpenAsset` with:

```ts
{
  sourceWorkspace: 'market',
  monitorTab: 'stock_heatmap',
  tradeDate: '2026-06-12',
  matchReason: 'stock_heatmap'
}
```

- [ ] **Step 2: Run the test to verify the current behavior**

Run:

```bash
rtk pnpm --dir dashboard test -- tests/market-monitor-workspace.test.tsx
```

Expected: should pass if current behavior already exists; if not, implement the missing handler.

- [ ] **Step 3: Keep implementation minimal**

If needed, update only `MarketMonitorWorkspace.handleSelectStockFromHeatmap`.

### Task 3: Verification

**Files:**
- No production file changes expected beyond Task 1 unless Task 2 finds a gap.

- [ ] **Step 1: Run frontend tests**

```bash
rtk pnpm --dir dashboard test
```

- [ ] **Step 2: Run dashboard build**

```bash
rtk pnpm --dir dashboard build
```

- [ ] **Step 3: Report outcome**

Report changed files, test results, and whether the remaining Vite chunk size warning is unchanged.
