# Dashboard Account Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the authenticated username in the canonical dashboard top bar and provide a reliable logout control that revokes the session and returns to the login view without reloading.

**Architecture:** `DashboardAuthRoot` continues to own authentication state and calls the existing `logoutDashboardUser()` client. `AppShell` receives `currentUser` plus an asynchronous `onLogout` callback, renders the account controls, and owns only the pending/error presentation for the button. The existing backend endpoint and cookie contract remain unchanged.

**Tech Stack:** React 19, TypeScript, Vitest, Testing Library, Vite, CSS, existing FastAPI cookie-session API, canonical dashboard release scripts.

---

## File Structure

- Modify `dashboard/src/components/DashboardAuthRoot.tsx`: connect the existing logout API to authenticated root state.
- Modify `dashboard/src/components/AppShell.tsx`: accept `onLogout`, render the username and logout control, and handle pending/error UI.
- Modify `dashboard/src/styles.css`: lay out search and account controls responsively.
- Modify `dashboard/tests/auth-root.test.tsx`: prove successful logout calls the API and returns to login.
- Modify `dashboard/tests/app-shell.test.tsx`: prove username, pending state, single invocation, and retryable failure presentation.
- Use `deploy/sync_dashboard_release.sh`: publish only after the feature branch is fast-forwarded into the clean canonical release root.

### Task 1: Specify AppShell Account-Control Behavior

**Files:**
- Test: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Add failing tests for username and successful logout invocation**

Add a focused test near the existing admin-navigation test:

```tsx
it('shows the authenticated username and invokes logout once', async () => {
  const onLogout = vi.fn().mockResolvedValue(undefined);

  render(<AppShell currentUser={TEST_ADMIN_USER} onLogout={onLogout} />);

  expect(screen.getByText(TEST_ADMIN_USER.username)).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: '退出登录' }));

  expect(await screen.findByRole('button', { name: '退出登录' })).toBeEnabled();
  expect(onLogout).toHaveBeenCalledTimes(1);
});
```

- [ ] **Step 2: Add a failing test for pending and failed logout states**

```tsx
it('disables repeated logout and shows a retryable error when logout fails', async () => {
  let rejectLogout: ((reason?: unknown) => void) | undefined;
  const onLogout = vi.fn(
    () =>
      new Promise<void>((_resolve, reject) => {
        rejectLogout = reject;
      })
  );

  render(<AppShell currentUser={TEST_ADMIN_USER} onLogout={onLogout} />);

  fireEvent.click(screen.getByRole('button', { name: '退出登录' }));
  const pendingButton = screen.getByRole('button', { name: '退出中…' });
  expect(pendingButton).toBeDisabled();
  fireEvent.click(pendingButton);
  expect(onLogout).toHaveBeenCalledTimes(1);

  rejectLogout?.(new Error('network_failure'));

  expect(await screen.findByRole('alert')).toHaveTextContent('退出失败，请重试');
  expect(screen.getByRole('button', { name: '退出登录' })).toBeEnabled();
});
```

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```bash
rtk pnpm --dir dashboard exec vitest run tests/app-shell.test.tsx -t 'authenticated username|repeated logout'
```

Expected: FAIL because `AppShellProps` has no `onLogout` property and no account controls are rendered.

- [ ] **Step 4: Commit the failing specification tests**

```bash
rtk git add dashboard/tests/app-shell.test.tsx
rtk git commit -m "test: specify dashboard account controls"
```

### Task 2: Implement AppShell Account Controls

**Files:**
- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Extend the AppShell interface and add interaction state**

Change the props and component start to:

```tsx
type AppShellProps = {
  currentUser?: CurrentUser;
  onLogout?: () => Promise<void>;
};

export function AppShell({ currentUser: _currentUser, onLogout }: AppShellProps = {}) {
  const currentUser = _currentUser;
  const [logoutPending, setLogoutPending] = useState(false);
  const [logoutError, setLogoutError] = useState('');
```

Add the handler inside `AppShell`:

```tsx
  async function handleLogout() {
    if (!onLogout || logoutPending) return;
    setLogoutError('');
    setLogoutPending(true);
    try {
      await onLogout();
    } catch {
      setLogoutError('退出失败，请重试');
    } finally {
      setLogoutPending(false);
    }
  }
```

- [ ] **Step 2: Render the account controls beside global search**

Replace the current top-bar body with:

```tsx
<header className="platform-topbar">
  <GlobalSearchBox onOpenResult={openGlobalSearchResult} />
  {currentUser ? (
    <div className="platform-account-controls" aria-label="当前账号">
      <span className="platform-account-username">{currentUser.username}</span>
      <button type="button" onClick={handleLogout} disabled={logoutPending || !onLogout}>
        {logoutPending ? '退出中…' : '退出登录'}
      </button>
      {logoutError ? <span role="alert" className="platform-account-error">{logoutError}</span> : null}
    </div>
  ) : null}
</header>
```

- [ ] **Step 3: Add responsive styles**

Update the top-bar styles and add the account classes:

```css
.platform-topbar {
  position: sticky;
  top: 0;
  z-index: 3;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
  border-bottom: 1px solid #cfd8e3;
  background: rgba(251, 252, 254, 0.96);
  padding: 10px 14px;
}

.global-search-box {
  position: relative;
  flex: 1 1 320px;
  width: min(480px, 100%);
  min-width: 0;
}

.platform-account-controls {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-left: auto;
  white-space: nowrap;
}

.platform-account-username {
  color: #263241;
  font-weight: 600;
}

.platform-account-controls button {
  border: 1px solid #c4cbd6;
  border-radius: 6px;
  background: #ffffff;
  color: #263241;
  padding: 7px 10px;
  font: inherit;
  cursor: pointer;
}

.platform-account-controls button:disabled {
  cursor: wait;
  opacity: 0.65;
}

.platform-account-error {
  color: #b42318;
  font-size: 12px;
}
```

In the existing `@media (max-width: 640px)` block, make the top bar wrap and keep both areas usable:

```css
.platform-topbar {
  align-items: stretch;
  justify-content: stretch;
  flex-wrap: wrap;
  padding: 8px 10px;
}

.global-search-box {
  flex-basis: 100%;
  width: 100%;
}

.platform-account-controls {
  width: 100%;
}
```

- [ ] **Step 4: Run the focused AppShell tests and verify GREEN**

Run:

```bash
rtk pnpm --dir dashboard exec vitest run tests/app-shell.test.tsx -t 'authenticated username|repeated logout'
```

Expected: both focused tests PASS.

- [ ] **Step 5: Commit the AppShell implementation**

```bash
rtk git add dashboard/src/components/AppShell.tsx dashboard/src/styles.css
rtk git commit -m "feat: add dashboard account controls"
```

### Task 3: Wire Logout Through DashboardAuthRoot

**Files:**
- Modify: `dashboard/tests/auth-root.test.tsx`
- Modify: `dashboard/src/components/DashboardAuthRoot.tsx`

- [ ] **Step 1: Make the AppShell test double expose the logout callback**

Replace the existing `AppShell` mock with:

```tsx
vi.mock('../src/components/AppShell', () => ({
  AppShell: ({ currentUser, onLogout }: { currentUser?: { username: string }; onLogout?: () => Promise<void> }) => (
    <div>
      Official Dashboard {currentUser?.username}
      <button type="button" onClick={() => void onLogout?.()}>退出登录</button>
    </div>
  )
}));
```

- [ ] **Step 2: Add the failing successful-logout test**

```tsx
it('revokes the session and returns to login after logout', async () => {
  apiMocks.fetchCurrentUser.mockResolvedValueOnce({
    user: { user_id: 'user:1', username: 'xiwei', display_name: 'Xiwei', role: 'user', is_active: true }
  });
  apiMocks.logoutDashboardUser.mockResolvedValueOnce({ status: 'logged_out' });

  render(<DashboardAuthRoot />);

  expect(await screen.findByText('Official Dashboard xiwei')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: '退出登录' }));

  expect(await screen.findByRole('heading', { name: '登录' })).toBeVisible();
  expect(apiMocks.logoutDashboardUser).toHaveBeenCalledTimes(1);
});
```

- [ ] **Step 3: Run the focused auth-root test and verify RED**

Run:

```bash
rtk pnpm --dir dashboard exec vitest run tests/auth-root.test.tsx -t 'revokes the session'
```

Expected: FAIL because `DashboardAuthRoot` does not pass `onLogout` to `AppShell` and does not call `logoutDashboardUser`.

- [ ] **Step 4: Implement authentication-root logout ownership**

Import the existing client:

```tsx
import { DASHBOARD_AUTH_EXPIRED_EVENT, fetchCurrentUser, loginDashboardUser, logoutDashboardUser } from '../api/client';
```

Replace the authenticated render with:

```tsx
return (
  <AppShell
    currentUser={user}
    onLogout={async () => {
      await logoutDashboardUser();
      setUser(null);
      setError('');
    }}
  />
);
```

- [ ] **Step 5: Run auth-root and AppShell tests and verify GREEN**

Run:

```bash
rtk pnpm --dir dashboard exec vitest run tests/auth-root.test.tsx tests/app-shell.test.tsx
```

Expected: both files PASS with zero failures.

- [ ] **Step 6: Commit auth-root wiring**

```bash
rtk git add dashboard/tests/auth-root.test.tsx dashboard/src/components/DashboardAuthRoot.tsx
rtk git commit -m "feat: wire dashboard logout session flow"
```

### Task 4: Verify, Promote, Deploy, And Smoke-Test

**Files:**
- Verify: `dashboard/src/components/DashboardAuthRoot.tsx`
- Verify: `dashboard/src/components/AppShell.tsx`
- Verify: `dashboard/src/styles.css`
- Deploy with: `/Users/xiwei/stock_research_release_20260727/deploy/sync_dashboard_release.sh`

- [ ] **Step 1: Run the complete relevant frontend verification**

```bash
rtk pnpm --dir dashboard test
rtk pnpm --dir dashboard build
```

Expected: Vitest exits with zero failures and Vite creates `dashboard/dist` successfully.

- [ ] **Step 2: Verify the feature branch is clean and inspect its commits**

```bash
rtk git status --short
rtk git log -6 --oneline
```

Expected: no uncommitted files; the account-control test and implementation commits are present above the canonical release commit.

- [ ] **Step 3: Fast-forward the clean canonical release root**

From `/Users/xiwei/stock_research_release_20260727`:

```bash
rtk git merge --ff-only feat/dashboard-account-controls
rtk git status --short
```

Expected: fast-forward succeeds and the release root remains clean.

- [ ] **Step 4: Publish through the only supported release entry point**

Use the latest validated strategy snapshot already present in the release root:

```bash
STOCK_RESEARCH_RELEASE_ROOT=/Users/xiwei/stock_research_release_20260727 \
EXPECTED_TRADE_DATE=2026-07-28 \
BASE_URL=https://stock.manqiaotechnology.com \
DASHBOARD_REMOTE_ENV_FILE=.env \
rtk /Users/xiwei/stock_research_release_20260727/deploy/sync_dashboard_release.sh
```

Expected: frontend build metadata matches the new Git release ID, backend/frontend containers restart, and the external release gate passes.

- [ ] **Step 5: Verify external provenance and deployed UI strings**

```bash
rtk curl -sS https://stock.manqiaotechnology.com/api/platform/readiness \
  | rtk jq '{latest_market_date,runtime_provenance}'
rtk curl -sS https://stock.manqiaotechnology.com/ \
  | rtk rg -o '/assets/index-[A-Za-z0-9_-]+\.js'
```

Fetch the returned JavaScript asset and verify it contains `退出登录`, `退出中…`, `退出失败，请重试`, and `当前账号`.

Expected: runtime provenance equals the new release commit and all four UI strings are present in the deployed bundle.

- [ ] **Step 6: Verify logout behavior with an authenticated browser session**

Open `https://stock.manqiaotechnology.com` using the existing signed-in session and verify:

1. The top bar displays `xiwei`.
2. The `退出登录` button is visible.
3. Clicking it returns immediately to the login view.
4. A subsequent `/api/auth/me` request in that browser session returns `401 not_authenticated`.

Expected: all four observations pass without clearing cookies manually or reloading the page.
