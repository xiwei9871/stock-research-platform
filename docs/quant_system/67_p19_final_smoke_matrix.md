# P19 Final Smoke Matrix

## Purpose

This smoke matrix is the final verification set for the completed platform
foundation. It is intentionally focused: it verifies the platform closure
surfaces without running unrelated strategy research or dirty worktree changes.

Run these commands from the repository root unless a command says otherwise.

## Backend Focused Platform Smoke

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_operator_shadow_follow_up_resolution.py \
  tests/test_operator_shadow_follow_up_resolution_read_model.py \
  tests/test_p18_shadow_follow_up_resolution_smoke.py \
  tests/test_p17_shadow_follow_up_queue_smoke.py \
  tests/test_schema.py \
  tests/test_factor_cli.py \
  tests/test_dashboard_shadow_follow_up_resolution.py \
  tests/test_dashboard_app.py \
  -k 'shadow_follow_up_resolution or p18_shadow_follow_up_resolution or p18_import_shadow_follow_up_resolution or p17_shadow_follow_up_queue or dashboard' \
  -q
```

Expected evidence:

- P17 smoke still builds a follow-up queue.
- P18 smoke builds resolution artifacts from the P17 queue.
- P18 read-model import behavior is covered.
- P18 schema table presence is covered.
- P18 CLI build and import commands are covered.
- Dashboard API routes are covered.

Known P19 run evidence:

```text
40 passed, 216 deselected, 2 warnings
```

## CLI And Schema Presence Smoke

```bash
rg -n \
  "p18-shadow-follow-up-resolution|p18-import-shadow-follow-up-resolution|dashboard-api|p17-shadow-follow-up-queue|p16-shadow-review-decisions" \
  src/stock_research/cli.py
```

Expected evidence:

- `dashboard-api`
- `p16-shadow-review-decisions`
- `p17-shadow-follow-up-queue`
- `p18-shadow-follow-up-resolution`
- `p18-import-shadow-follow-up-resolution`

```bash
rg -n \
  "operator_shadow_follow_up_resolution|operator_shadow_follow_up|operator_shadow_review_decision|operator_shadow_analytics_review" \
  src/stock_research/schema.py
```

Expected evidence:

- P15 shadow analytics review tables.
- P16 shadow review decision tables.
- P17 shadow follow-up queue tables.
- P18 shadow follow-up resolution tables.

## Dashboard Unit Smoke

Run from `dashboard/`:

```bash
pnpm test -- --run tests/client.test.ts tests/app-shell.test.tsx
```

Expected evidence:

- API client builds P17/P18 shadow follow-up URLs.
- App shell renders P17 and P18 dashboard panels.
- Loading and empty states remain stable.
- No production action buttons are exposed.

Known P19 run evidence:

```text
Test Files  3 passed (3)
Tests  33 passed (33)
```

## Dashboard Build Smoke

Run from `dashboard/`:

```bash
pnpm build
```

Expected evidence:

- TypeScript compiles.
- Vite production build completes.

Known P19 run evidence:

```text
54 modules transformed.
built successfully
```

## Dashboard Browser Smoke

Run from `dashboard/`:

```bash
pnpm exec playwright test tests/app-smoke.spec.ts
```

Expected evidence:

- Desktop dashboard smoke renders mocked API responses.
- Mobile dashboard smoke stacks without horizontal overflow.
- P18 `Shadow Follow-up Resolution` panel is visible.

Known P19 run evidence:

```text
2 passed
```

## Whitespace And Diff Smoke

```bash
git diff --check
```

Expected evidence:

- No whitespace errors.

## Optional Full Closure Review

After running all required smoke commands, review:

```bash
git status --short
git log --oneline -8
```

Expected evidence:

- Only intended P19 files are dirty before commit.
- Commit history shows P19 scope/design/plan and P19 task commits.

## Out-Of-Scope Smokes

Do not run these as part of P19 unless separately requested:

- unrelated mid-trend research tests,
- strong-winner research tests,
- alpha191 tests,
- live scheduler jobs,
- live notification sends,
- broker or execution checks.
