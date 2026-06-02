# P19 Final Platform Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the final P19 release readiness package for the completed P0-P18 stock research platform foundation.

**Architecture:** P19 is documentation-first. It reads existing P0-P18 docs, tests, CLI routes, schema/read-model surfaces, and dashboard smoke coverage, then writes final closure documents without adding runtime behavior.

**Tech Stack:** Markdown documentation, pytest, Vitest, Vite, Playwright, git worktrees.

---

## File Structure

- Create `docs/quant_system/65_p19_platform_phase_index.md`: final P0-P18 phase map and artifact links.
- Create `docs/quant_system/66_p19_release_readiness_audit.md`: platform readiness checklist with pass/gap/out-of-scope classification.
- Create `docs/quant_system/67_p19_final_smoke_matrix.md`: exact verification commands and expected evidence.
- Create `docs/quant_system/68_p19_final_release_runbook.md`: safe operator run order and failure handling.
- Create `docs/quant_system/69_p19_final_platform_closure_completion.md`: final completion conclusion and backlog split.

## Task 1: Phase Index

**Files:**
- Create: `docs/quant_system/65_p19_platform_phase_index.md`

- [ ] **Step 1: Write the phase index**

Create a Markdown table with:

- phase id,
- purpose,
- primary artifacts,
- operational state,
- completion document.

Use the existing `docs/quant_system/` filenames from P0-P18. Do not invent missing phases.

- [ ] **Step 2: Verify phase links**

Run:

```bash
for f in docs/quant_system/{09_p0_universe_layer.md,11_p0_completion_and_p1_readiness.md,13_p1_completion_review.md,16_p2_completion_review.md,19_p3_completion_review.md,22_p4_completion_review.md,25_p5_completion_review.md,27_p6_completion_review.md,30_p7_completion_review.md,33_p8_decision_outcome_review_completion.md,36_p9_decision_outcome_analytics_completion.md,39_p10_experiment_promotion_governance_completion.md,42_p11_experiment_execution_sandbox_completion.md,45_p12_shadow_watchlist_completion.md,48_p13_shadow_outcome_tracking_completion.md,51_p14_shadow_outcome_analytics_completion.md,54_p15_shadow_analytics_operational_review_completion.md,57_p16_shadow_review_decision_packet_completion.md,60_p17_shadow_decision_follow_up_queue_completion.md,63_p18_shadow_follow_up_resolution_review_completion.md}; do test -f "$f" || exit 1; done
```

Expected: exit code 0.

- [ ] **Step 3: Commit**

```bash
git add docs/quant_system/65_p19_platform_phase_index.md
git commit -m "docs: add p19 platform phase index"
```

## Task 2: Release Readiness Audit

**Files:**
- Create: `docs/quant_system/66_p19_release_readiness_audit.md`

- [ ] **Step 1: Write the readiness audit**

Document these sections:

- data and schema readiness,
- daily operations readiness,
- dashboard readiness,
- operator review readiness,
- experiment/shadow readiness,
- P18 resolution readiness,
- safety boundaries,
- known out-of-scope items.

Every row must be classified as `Pass`, `Intentional Out Of Scope`, or `Backlog`.

- [ ] **Step 2: Sanity check key commands exist**

Run:

```bash
rg -n "p18-shadow-follow-up-resolution|p18-import-shadow-follow-up-resolution|dashboard-api|p17-shadow-follow-up-queue|p16-shadow-review-decisions" src/stock_research/cli.py
```

Expected: all listed command strings appear.

- [ ] **Step 3: Commit**

```bash
git add docs/quant_system/66_p19_release_readiness_audit.md
git commit -m "docs: add p19 release readiness audit"
```

## Task 3: Final Smoke Matrix

**Files:**
- Create: `docs/quant_system/67_p19_final_smoke_matrix.md`

- [ ] **Step 1: Write the smoke matrix**

Include exact commands for:

- P17/P18 backend focused pytest,
- CLI parser and dispatch focused pytest,
- schema presence tests,
- dashboard API route tests,
- dashboard Vitest client/app shell,
- dashboard build,
- Playwright smoke,
- `git diff --check`.

- [ ] **Step 2: Run backend focused smoke**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_follow_up_resolution.py tests/test_operator_shadow_follow_up_resolution_read_model.py tests/test_p18_shadow_follow_up_resolution_smoke.py tests/test_p17_shadow_follow_up_queue_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_shadow_follow_up_resolution.py tests/test_dashboard_app.py -k 'shadow_follow_up_resolution or p18_shadow_follow_up_resolution or p18_import_shadow_follow_up_resolution or p17_shadow_follow_up_queue or dashboard' -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Commit**

```bash
git add docs/quant_system/67_p19_final_smoke_matrix.md
git commit -m "docs: add p19 final smoke matrix"
```

## Task 4: Final Release Runbook

**Files:**
- Create: `docs/quant_system/68_p19_final_release_runbook.md`

- [ ] **Step 1: Write the final runbook**

Document safe operating order:

- apply schema,
- run daily pipeline/orchestration checks,
- generate/import operator artifacts where applicable,
- run dashboard API,
- inspect dashboard review panels,
- treat shadow and P18 resolution as review-only,
- handle missing tables, stale imports, and failed smoke tests.

- [ ] **Step 2: Verify referenced P17/P18 runbooks exist**

Run:

```bash
test -f docs/quant_system/59_p17_shadow_decision_follow_up_queue_runbook.md && test -f docs/quant_system/62_p18_shadow_follow_up_resolution_review_runbook.md
```

Expected: exit code 0.

- [ ] **Step 3: Commit**

```bash
git add docs/quant_system/68_p19_final_release_runbook.md
git commit -m "docs: add p19 final release runbook"
```

## Task 5: Final Completion Review

**Files:**
- Create: `docs/quant_system/69_p19_final_platform_closure_completion.md`

- [ ] **Step 1: Run final verification**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_operator_shadow_follow_up_resolution.py tests/test_operator_shadow_follow_up_resolution_read_model.py tests/test_p18_shadow_follow_up_resolution_smoke.py tests/test_p17_shadow_follow_up_queue_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_shadow_follow_up_resolution.py tests/test_dashboard_app.py -k 'shadow_follow_up_resolution or p18_shadow_follow_up_resolution or p18_import_shadow_follow_up_resolution or p17_shadow_follow_up_queue or dashboard' -q && git diff --check
```

Run in `dashboard/`:

```bash
pnpm test -- --run tests/client.test.ts tests/app-shell.test.tsx
pnpm build
pnpm exec playwright test tests/app-smoke.spec.ts
```

Expected: all commands pass.

- [ ] **Step 2: Write the completion review**

Record:

- P19 delivered artifacts,
- final verification evidence,
- final platform foundation status,
- safety boundaries,
- future backlog outside this foundation.

- [ ] **Step 3: Commit**

```bash
git add docs/quant_system/69_p19_final_platform_closure_completion.md
git commit -m "docs: complete p19 final platform closure"
```

## Safety Checklist

- P19 does not add runtime production behavior.
- P19 does not touch unrelated main-worktree dirty changes.
- P19 does not push or merge unless explicitly requested.
- P19 keeps P18 resolution review-only.
