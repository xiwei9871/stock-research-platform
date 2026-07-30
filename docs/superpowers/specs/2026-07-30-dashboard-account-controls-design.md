# Dashboard Account Controls Design

Date: 2026-07-30

## Goal

Add visible session controls to the authenticated dashboard so every signed-in user can see the username attached to the current session and can explicitly sign out without clearing browser cookies manually.

## Scope

In scope:

- Show the authenticated `username` in the canonical dashboard top bar.
- Add a visible `退出登录` button beside the username.
- Revoke the server-side session through the existing `/api/auth/logout` endpoint.
- Return immediately to the existing login view after a successful logout.
- Show an inline retryable error when logout fails.
- Keep the controls usable on narrow screens.

Out of scope:

- Changing user roles or promoting `xiwei` to `admin`.
- Adding an account profile page or dropdown menu.
- Password changes, account switching, or remember-me behavior.
- Changing the backend logout contract or session storage schema.

## Chosen Architecture

`DashboardAuthRoot` remains the owner of authenticated session state. It imports and calls the existing `logoutDashboardUser` API client, clears its current-user state only after the server confirms logout, and thereby renders the existing login view without a page reload.

`AppShell` remains a presentation and workspace-navigation component. It receives the current user and an `onLogout` callback, renders the username and logout control in the top bar, and reports the asynchronous interaction state to the user. It does not import the authentication API client or mutate session state directly.

This keeps authentication ownership in one component while allowing the canonical shell to render session controls.

## UI Design

The sticky top bar contains two areas:

1. The existing global search control, which keeps the available flexible width.
2. A compact account-control group containing the current `username` and a `退出登录` button.

During logout, the button is disabled and displays `退出中…` to prevent duplicate submissions. If logout fails, the dashboard remains visible and the account-control group displays `退出失败，请重试` as an accessible alert. On narrow screens, the top bar may wrap so the controls do not cover or compress the search field beyond usability.

## Data Flow

1. `DashboardAuthRoot` loads the current user through the existing `/api/auth/me` flow.
2. It renders `AppShell` with `currentUser` and an asynchronous `onLogout` callback.
3. The user clicks `退出登录` in `AppShell`.
4. `AppShell` disables the button and invokes `onLogout`.
5. `DashboardAuthRoot` calls `logoutDashboardUser()`.
6. The backend revokes the server-side session and clears authentication cookies.
7. `DashboardAuthRoot` sets its user state to `null`, causing the existing login view to render immediately.

If step 5 fails, the user state is not cleared. `AppShell` re-enables the button and shows the retryable error.

## Error Handling

- Duplicate logout requests are prevented while one request is pending.
- A failed request does not pretend the session ended and does not discard the current dashboard state.
- The error is visible in the top bar with alert semantics and is cleared when the user retries.
- Existing global authentication-expiry behavior remains unchanged.

## Testing

Use test-driven development with focused frontend tests:

- `AppShell` displays the supplied username.
- Clicking `退出登录` invokes the supplied callback once and shows the pending state.
- `DashboardAuthRoot` calls the logout client and returns to the login view after success.
- A rejected logout remains on the dashboard and shows `退出失败，请重试`.
- Existing auth-root and AppShell tests continue to pass.
- The dashboard production build succeeds.

## Deployment And Verification

Build the canonical dashboard static bundle, deploy it through the existing external-dashboard hosting path, and verify against `https://stock.manqiaotechnology.com` that:

- the deployed bundle contains the account controls;
- an authenticated session shows the correct username;
- clicking `退出登录` returns to the login page;
- a logged-out request to `/api/auth/me` is rejected;
- the rest of the dashboard shell still loads after signing in again.
