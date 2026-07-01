# Dashboard Localhost 5174 Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the merged dashboard and `Daily Review Lite` integration up on `127.0.0.1:5174`, verify the real localhost flow end-to-end, and capture whether the branch is ready for broader internal testing.

**Architecture:** Use a fresh `main`-based worktree as the localhost validation environment so we do not test from the user’s unrelated feature branch. Treat validation in three layers: environment boot, automated smoke/regression checks, and manual in-browser review of the new `Daily Review Lite` workspace and existing dashboard surfaces.

**Tech Stack:** Git worktrees, pnpm, Vite, Playwright, Vitest, stock-research dashboard API

---

## File Map

- `docs/superpowers/plans/2026-06-22-dashboard-localhost-5174-validation.md`
  Responsibility: execution checklist for localhost validation on `127.0.0.1:5174`.
- `dashboard/package.json`
  Responsibility: source of dashboard scripts to use during validation (`dev`, `test`, `test:e2e`).
- `dashboard/playwright.config.ts`
  Responsibility: source of default Playwright localhost base URL and webServer behavior.
- `docs/dashboard-workbench-runbook.md`
  Responsibility: existing documented startup path for dashboard API and frontend.

## Implementation Notes

- Do **not** start localhost validation from the current root worktree if it is on an unrelated branch.
- Validate from a fresh `main` worktree, because `main` is where the dashboard/Lite integration was merged.
- Prefer reusing the existing `dashboard/node_modules` through a symlink if the fresh worktree does not have its own install yet.
- Use the dedicated Playwright scripts already present on merged `main` when validating the dashboard entry and Lite entry paths.
- Manual validation must cover both the new `Daily Review Lite` workspace and the existing shell/workbench entry so we do not regress the current dashboard.

### Task 1: Prepare A Clean `main` Validation Worktree

**Files:**
- Reference: `dashboard/package.json`
- Reference: `dashboard/playwright.config.ts`

- [ ] **Step 1: Create a fresh `main` worktree for localhost validation**

Run:

```bash
git -C /Users/xiwei/stock_research worktree add /Users/xiwei/stock_research/.worktrees/dashboard-5174-validation main
git -C /Users/xiwei/stock_research/.worktrees/dashboard-5174-validation rev-parse HEAD
```

Expected:
- Worktree is created successfully.
- `HEAD` resolves to the merged `main` history that contains the `Daily Review Lite` dashboard integration.

- [ ] **Step 2: Make sure the validation worktree can run dashboard tooling**

Run:

```bash
test -e /Users/xiwei/stock_research/.worktrees/dashboard-5174-validation/dashboard/node_modules || \
ln -s /Users/xiwei/stock_research/dashboard/node_modules \
  /Users/xiwei/stock_research/.worktrees/dashboard-5174-validation/dashboard/node_modules

git -C /Users/xiwei/stock_research/.worktrees/dashboard-5174-validation status --short
```

Expected:
- `dashboard/node_modules` exists in the validation worktree.
- The worktree stays effectively clean aside from the local symlink if it is not ignored.

- [ ] **Step 3: Verify the baseline automated checks before starting servers**

Run from `dashboard`:

```bash
pnpm exec vitest run tests/client.test.ts tests/daily-review-lite-page.test.tsx tests/dashboard-shell.test.tsx
pnpm build
```

Expected:
- Vitest subset passes.
- Build succeeds.

- [ ] **Step 4: Commit only if environment-prep scripts or ignore rules had to change**

```bash
git add <only-if-repo-files-were-modified>
git commit -m "chore: prepare dashboard localhost validation"
```

Expected:
- Usually **skip this step** because localhost validation should not need repo changes.

### Task 2: Boot The Dashboard API And Frontend On Localhost

**Files:**
- Reference: `docs/dashboard-workbench-runbook.md`
- Reference: `dashboard/package.json`

- [ ] **Step 1: Start the dashboard API on localhost**

Run in a dedicated terminal/session:

```bash
cd /Users/xiwei/stock_research/.worktrees/dashboard-5174-validation
stock-research dashboard-api --host 127.0.0.1 --port 8765
```

Expected:
- Process stays up.
- No immediate startup exception.

- [ ] **Step 2: Start the dashboard frontend on `127.0.0.1:5174`**

Run in a second terminal/session:

```bash
cd /Users/xiwei/stock_research/.worktrees/dashboard-5174-validation/dashboard
pnpm dev
```

Expected:
- Vite binds `127.0.0.1:5174`.
- Browser entry is available at `http://127.0.0.1:5174`.

- [ ] **Step 3: Perform a quick localhost reachability check**

Run:

```bash
curl -I http://127.0.0.1:5174
```

Expected:
- HTTP response returns successfully from the frontend server.

- [ ] **Step 4: Keep both processes running during browser validation**

Expected:
- Do **not** terminate the API or frontend until Tasks 3 and 4 complete.

### Task 3: Run Automated Browser Validation Against Localhost

**Files:**
- Reference: `dashboard/package.json`
- Reference: `dashboard/playwright.config.ts`

- [ ] **Step 1: Run the baseline dashboard shell smoke**

Run from `dashboard`:

```bash
pnpm run test:e2e
```

Expected:
- Existing dashboard entry smoke passes.
- Confirms the shell/workbench path is intact under the merged architecture.

- [ ] **Step 2: Run the standalone Lite smoke**

Run from `dashboard`:

```bash
pnpm run test:e2e:lite
```

Expected:
- Lite smoke passes on its dedicated port.
- Confirms the page still works directly with the current API contract.

- [ ] **Step 3: Run the dashboard-entry Lite smoke**

Run from `dashboard`:

```bash
pnpm run test:e2e:dashboard-lite
```

Expected:
- Dashboard-entry Lite smoke passes on its dedicated port.
- Confirms shell navigation into `Daily Review Lite` works end-to-end.

- [ ] **Step 4: Re-run the full targeted matrix if any smoke exposes a flake**

Run:

```bash
pnpm exec vitest run tests/client.test.ts tests/daily-review-lite-page.test.tsx tests/dashboard-shell.test.tsx
pnpm run test:e2e
pnpm run test:e2e:lite
pnpm run test:e2e:dashboard-lite
pnpm build
```

Expected:
- All commands pass in one final matrix.

### Task 4: Perform Manual In-Browser Localhost Validation

**Files:**
- Reference: `dashboard/src/shell/DashboardShell.tsx`
- Reference: `dashboard/src/pages/DailyReviewLitePage.tsx`

- [ ] **Step 1: Verify shell navigation and default landing behavior**

Open:

```text
http://127.0.0.1:5174
```

Check:
- Left navigation renders.
- `复盘队列` is selected by default.
- Existing workbench content still appears.

- [ ] **Step 2: Verify the new `Daily Review Lite` workspace entry**

From the browser:
- Click `Daily Review Lite`.

Check:
- URL includes `workspace=daily-review-lite`.
- `Daily Review Lite` heading appears.
- Lite page sections render.
- Old workbench path remains reachable by clicking `复盘队列`.

- [ ] **Step 3: Verify URL-backed `trade_date` behavior**

Open and test:

```text
http://127.0.0.1:5174/?workspace=daily-review-lite&trade_date=2026-06-19
```

Check:
- Date input shows `2026-06-19`.
- Changing the date updates the URL.
- Browser back/forward updates the rendered Lite date.
- Reload preserves the selected Lite date.

- [ ] **Step 4: Verify empty / partial / failed operator readability on real data**

Use recent real dates and inspect whether:
- `ready` dates look complete
- `partial` warnings are understandable
- `empty` state does not claim a resolved run
- `failed` state keeps safe artifact visibility when applicable

Record concrete dates tested and which state each one produced.

- [ ] **Step 5: Capture findings in a short validation note**

Create a short note locally with:

```text
- validation date
- worktree path
- tested URLs
- tested trade dates
- pass/fail summary
- blockers or follow-ups
```

Expected:
- A concise artifact exists for handoff or follow-up fixes.

## Self-Review

### Spec coverage

- Fresh `main` worktree for localhost validation: covered by Task 1
- Bring up real `127.0.0.1:5174` frontend and localhost API: covered by Task 2
- Preserve both existing dashboard path and new Lite path during automated checks: covered by Task 3
- Manual in-browser validation of navigation, URL state, and real data behavior: covered by Task 4

### Placeholder scan

- No `TODO`, `TBD`, or deferred placeholders remain.
- Each task contains exact commands and explicit expected outcomes.

### Type consistency

- Host/port references are consistent:
  - dashboard API: `127.0.0.1:8765`
  - frontend dev server: `127.0.0.1:5174`
- Browser smoke scripts align with the existing package-script naming:
  - `test:e2e`
  - `test:e2e:lite`
  - `test:e2e:dashboard-lite`
