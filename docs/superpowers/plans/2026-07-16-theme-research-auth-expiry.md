# Theme Research Authentication Expiry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route expired Theme Research sessions back to dashboard login instead of showing a misleading data-load failure.

**Architecture:** Keep the existing backend authentication middleware and `DashboardAuthRoot` event listener. Extend the isolated Theme Research GET client to include credentials and dispatch the shared authentication-expired event only for HTTP 401 responses.

**Tech Stack:** React 19, TypeScript, Vitest, Testing Library, Vite.

---

### Task 1: Add The Authentication-Expiry Regression Test

**Files:**

- Create: `dashboard/tests/theme-research-api.test.ts`
- Modify: `dashboard/src/api/themeResearch.ts`

- [ ] **Step 1: Write the failing 401 test**

Mock `fetch` to return HTTP 401, listen for `dashboard-auth-expired`, call `fetchThemeResearchThemes()`, and assert the event fires once. Also assert the request was made with `{ credentials: 'include' }`.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
rtk pnpm test -- theme-research-api.test.ts
```

Expected: the event-count assertion fails because `themeResearch.ts` currently only throws `not_authenticated`; the credentials assertion also shows the request has no options object.

- [ ] **Step 3: Implement the minimal client change**

Import `DASHBOARD_AUTH_EXPIRED_EVENT`, call:

```ts
fetch(path, { credentials: 'include' })
```

and dispatch the shared event before parsing/throwing the 401 error.

- [ ] **Step 4: Add and pass the non-401 guard test**

Return HTTP 500 and assert no authentication-expired event is emitted while the request still rejects.

- [ ] **Step 5: Run focused tests and verify GREEN**

```bash
rtk pnpm test -- theme-research-api.test.ts auth-root.test.tsx theme-research-workspace.test.tsx
```

Expected: all focused tests pass.

### Task 2: Full Verification And Port 5174 Acceptance

**Files:**

- No additional production files expected.

- [ ] **Step 1: Run the full frontend suite**

```bash
rtk pnpm test
```

- [ ] **Step 2: Build the dashboard**

```bash
rtk pnpm build
```

- [ ] **Step 3: Verify the live expired-session behavior**

Reload `/theme-research` on port 5174. Confirm the login view appears and the old Theme Research failure card is absent.

- [ ] **Step 4: Run repository checks**

```bash
rtk git diff --check
rtk git status --short
```

- [ ] **Step 5: Commit only task-owned files**

```bash
rtk git add \
  dashboard/src/api/themeResearch.ts \
  dashboard/tests/theme-research-api.test.ts \
  docs/superpowers/specs/2026-07-16-theme-research-auth-expiry-design.md \
  docs/superpowers/plans/2026-07-16-theme-research-auth-expiry.md
rtk git commit -m "fix: handle expired theme research sessions"
```

