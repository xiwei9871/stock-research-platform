# User Management Autofill White-Screen Fix Design

**Goal:** Prevent the admin user-management workspace from crashing when a browser or password manager autofills a reset-password input.

## Confirmed Root Cause

The production browser console reports `TypeError: Cannot read properties of null (reading 'value')` while rendering `UserManagementView`. Each reset-password input currently reads `event.currentTarget.value` inside the functional state updater passed to `setResetPasswords`.

React may execute that updater after the change handler returns. At that point the synthetic event's `currentTarget` has been cleared to `null`. Password-manager autofill triggers this path immediately when the admin workspace mounts, so the uncaught render-time exception blanks the application.

The `/api/admin/users` response and admin session are healthy; the failure occurs entirely in the frontend event lifecycle.

## Approved Fix

Capture the input value synchronously inside the `onChange` handler, before scheduling the state update:

```tsx
onChange={(event) => {
  const password = event.currentTarget.value;
  setResetPasswords((current) => ({ ...current, [user.user_id]: password }));
}}
```

The functional updater remains in place so edits to different users cannot overwrite one another. Only the event-derived string is captured early. API contracts, navigation, authentication, autofill attributes, and user-management behavior remain unchanged.

## Rejected Alternatives

- Disabling autofill is not reliable across browsers and password managers and would only hide the unsafe event access.
- Adding an error boundary would reduce the visual impact but would not repair the broken password input.

## Testing

- Add a regression test that models a deferred state updater: the event target becomes unavailable after the handler returns, but the captured password is still applied without throwing.
- Keep the existing user-management create, enable, disable, and reset-password tests passing.
- Run the complete dashboard Vitest suite and production build.
- After deployment, log in as `admin`, open `用户管理`, confirm the workspace remains rendered, and confirm no `currentTarget.value` console error appears.

## Deployment

Publish through the clean canonical release root and existing dashboard release gate. No database migration, API restart behavior change, or credential change is required.
