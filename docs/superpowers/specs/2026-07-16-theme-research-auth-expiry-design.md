# Theme Research Authentication Expiry Design

**Date:** 2026-07-16

## Problem

The dashboard session expires after 12 hours. The backend then returns `401 not_authenticated` for the Theme Research API. `dashboard/src/api/themeResearch.ts` throws a local request error but does not notify `DashboardAuthRoot`, so the authenticated shell remains mounted and Theme Research renders “主题研究加载失败” instead of returning the user to the login view.

## Approved Behavior

When any Theme Research GET request receives HTTP 401:

1. Dispatch the existing `dashboard-auth-expired` window event.
2. Let `DashboardAuthRoot` clear the current user and render the login view.
3. Preserve existing handling for non-401 failures so genuine data or server errors still render the Theme Research retry panel.
4. Keep dashboard authentication required and keep the 12-hour session policy unchanged.

## Implementation Boundary

- Modify only the Theme Research API client and its focused frontend tests.
- Reuse `DASHBOARD_AUTH_EXPIRED_EVENT` from the shared API client rather than adding a second event name.
- Send credentials explicitly with `credentials: 'include'` for clarity and consistency with authenticated API calls.
- Do not exempt research routes from authentication.
- Do not restart the backend or create a session on behalf of the user.

## Acceptance

- A focused API test observes the event on HTTP 401.
- The same test confirms the request uses `credentials: 'include'`.
- Non-401 failures do not emit the authentication-expired event.
- Theme Research workspace tests, auth-root tests, frontend suite and build pass.
- On port 5174, retrying or reloading with an expired session renders the login screen instead of “主题研究加载失败”.

