# User Management Autofill White-Screen Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the admin user-management workspace rendered when password-manager autofill triggers a reset-password change event.

**Architecture:** Move reset-password event handling into a focused handler factory that synchronously captures the input value before scheduling the React state updater. Preserve the existing password map and API behavior, then publish through the canonical dashboard release gate.

**Tech Stack:** React 19, TypeScript, Vitest, Testing Library, Vite, canonical dashboard release scripts.

---

### Task 1: Add the Autofill Regression Test

**Files:**
- Modify: `dashboard/tests/user-management-view.test.tsx`

- [ ] **Step 1: Write a failing deferred-updater test**

Import `buildResetPasswordChangeHandler` from `UserManagementView`. Invoke the handler with a change event whose `currentTarget.value` is `autofilled-secret`, retain the state updater passed to the setter, clear `event.currentTarget`, and then execute the retained updater. Assert that it does not throw and produces `{ 'user:2': 'autofilled-secret' }`.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
rtk pnpm --dir dashboard exec vitest run tests/user-management-view.test.tsx -t 'captures autofilled password'
```

Expected: FAIL because `buildResetPasswordChangeHandler` is not exported.

### Task 2: Capture the Password Before the Deferred Update

**Files:**
- Modify: `dashboard/src/components/UserManagementView.tsx`
- Test: `dashboard/tests/user-management-view.test.tsx`

- [ ] **Step 1: Add the minimal handler factory**

Add a typed `buildResetPasswordChangeHandler(userId, setResetPasswords)` function. Its returned change handler must assign `const password = event.currentTarget.value` before calling the setter, then use only `password` inside the functional updater.

- [ ] **Step 2: Wire the reset-password input to the handler**

Replace the inline `onChange` callback with `buildResetPasswordChangeHandler(user.user_id, setResetPasswords)`.

- [ ] **Step 3: Run the focused test and verify GREEN**

Run:

```bash
rtk pnpm --dir dashboard exec vitest run tests/user-management-view.test.tsx
```

Expected: all user-management tests PASS.

- [ ] **Step 4: Commit the implementation**

Commit the test and implementation together with message `fix: prevent user management autofill crash`.

### Task 3: Verify and Publish

**Files:**
- Verify all modified files.
- Use: `deploy/sync_dashboard_release.sh`

- [ ] Run `rtk git diff --check`.
- [ ] Run the complete dashboard test suite.
- [ ] Run the dashboard production build.
- [ ] Fast-forward the clean canonical release root to the fix commit.
- [ ] Publish with expected trade date `2026-07-29` and production environment file `.env`.
- [ ] Confirm the external release gate identifies the new commit.
- [ ] Log in as `admin`, open `用户管理`, confirm the form and user table remain visible, and confirm the console has no new `currentTarget.value` error.
