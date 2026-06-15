# Operator Decision UI v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal Stock Workspace decision panel that writes local operator decisions through the Batch F API and shows snapshot linkage status.

**Architecture:** Build a standalone `OperatorDecisionPanel` that owns form state and calls `createOperatorDecision`. Mount it in Stock Workspace near Evidence Digest, and extend Review Queue stock handoff context with candidate lineage fields so the panel can persist run/digest/source context.

**Tech Stack:** React, TypeScript, Vitest, Testing Library, existing dashboard API client.

---

### Task 1: Operator Decision Panel Tests

**Files:**
- Create: `dashboard/src/components/OperatorDecisionPanel.tsx`
- Create: `dashboard/tests/operator-decision-panel.test.tsx`

- [ ] **Step 1: Write failing tests**

Create tests that mock `createOperatorDecision`, render the panel, assert allowed actions, assert forbidden trading words are absent, submit a note, and verify linked/missing/error states.

- [ ] **Step 2: Run red test**

Run:

```bash
cd dashboard && pnpm exec vitest run --exclude "**/*.spec.ts" tests/operator-decision-panel.test.tsx
```

Expected: fails because `OperatorDecisionPanel` does not exist.

- [ ] **Step 3: Implement panel**

Implement action select, note textarea, optional follow-up date, submit state, success/error/warnings display, and `onDecisionCreated`.

- [ ] **Step 4: Run green test**

Run the same Vitest command. Expected: pass.

### Task 2: Stock Workspace Integration

**Files:**
- Modify: `dashboard/src/components/StockWorkspace.tsx`
- Modify: `dashboard/src/api/types.ts`
- Test: `dashboard/tests/stock-workspace.test.tsx`

- [ ] **Step 1: Write failing integration tests**

Add tests that render Stock Workspace with Evidence Digest lineage, submit a note, verify `createOperatorDecision` receives `run_id` and `digest_key`, and verify the workspace reloads profile after success.

- [ ] **Step 2: Run red test**

Run:

```bash
cd dashboard && pnpm exec vitest run --exclude "**/*.spec.ts" tests/stock-workspace.test.tsx
```

Expected: fails because Stock Workspace does not render the panel.

- [ ] **Step 3: Implement integration**

Import `OperatorDecisionPanel`, extend `StockEntryContext` with optional lineage fields, derive panel props from Evidence Digest first and entry context second, and call `loadProfile` after successful creation.

- [ ] **Step 4: Run green test**

Run the same Vitest command. Expected: pass.

### Task 3: Review Queue Handoff Lineage

**Files:**
- Modify: `dashboard/src/components/ReviewQueueWorkspace.tsx`
- Test: `dashboard/tests/review-queue-workspace.test.tsx`

- [ ] **Step 1: Write failing test**

Update the "Review Stock" action test to expect selected item `runId`, `digestKey`, `sourceType`, `sourceName`, `scoreVersion`, and rank fields in the Stock Workspace handoff.

- [ ] **Step 2: Run red test**

Run:

```bash
cd dashboard && pnpm exec vitest run --exclude "**/*.spec.ts" tests/review-queue-workspace.test.tsx
```

Expected: fails because lineage is not passed.

- [ ] **Step 3: Implement lineage handoff**

Merge selected item lineage into the context created by `actionContext`.

- [ ] **Step 4: Run green test**

Run the same Vitest command. Expected: pass.

### Task 4: Documentation And Verification

**Files:**
- Modify: `docs/dashboard-local-runbook.md`

- [ ] **Step 1: Update runbook**

Add UI smoke steps for opening Stock Workspace, submitting watch/note, checking linked/missing status, and reading decision history.

- [ ] **Step 2: Run focused tests**

Run:

```bash
cd dashboard && pnpm exec vitest run --exclude "**/*.spec.ts" \
  tests/operator-decision-panel.test.tsx \
  tests/stock-workspace.test.tsx \
  tests/review-queue-workspace.test.tsx \
  tests/client.test.ts
```

Expected: all pass.

- [ ] **Step 3: Run build**

Run:

```bash
cd dashboard && pnpm build
```

Expected: TypeScript and Vite build pass.

- [ ] **Step 4: Run backend smoke**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_operator_decision_write_service.py \
  tests/test_dashboard_app.py -q
```

Expected: pass.

- [ ] **Step 5: Commit relevant hunks only**

Use hunk-level staging where files have unrelated dirty changes. Commit message:

```bash
git commit -m "feat: add minimal operator decision ui"
```

## Self Review

- Scope is limited to Stock Workspace panel plus Review Queue lineage handoff.
- No HomeCockpit, Strategy Command Center, Backtest Lab, strategy, data-source, broker, or trading UI work.
- Every behavior has a focused test and red/green command.
