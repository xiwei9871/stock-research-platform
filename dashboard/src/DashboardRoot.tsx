import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { fetchCurrentUser, login, logout } from './api/client';
import type { CurrentUser } from './api/types';
import { DashboardShell } from './shell/DashboardShell';
import { LoginView } from './views/LoginView';
import { MyReviewsView } from './views/MyReviewsView';
import { MyWatchlistView } from './views/MyWatchlistView';
import { UserManagementView } from './views/UserManagementView';

type ErrorWithStatus = {
  message?: string;
  status?: number;
};

type ViewDefinition = {
  id: string;
  label: string;
  section: '官方' | '我的' | '管理';
  adminOnly?: boolean;
  render: (currentUser: CurrentUser | null) => ReactNode;
};

const VIEW_DEFINITIONS: ViewDefinition[] = [
  {
    id: 'official',
    label: '官方工作台',
    section: '官方',
    render: () => <DashboardShell />
  },
  {
    id: 'my-watchlist',
    label: '我的观察池',
    section: '我的',
    render: () => <MyWatchlistView />
  },
  {
    id: 'my-reviews',
    label: '我的复盘',
    section: '我的',
    render: () => <MyReviewsView />
  },
  {
    id: 'user-management',
    label: '用户管理',
    section: '管理',
    adminOnly: true,
    render: (currentUser) => <UserManagementView currentUserId={currentUser?.id ?? null} />
  }
];

function getRequestedViewId() {
  return new URLSearchParams(window.location.search).get('view');
}

function getErrorStatus(error: unknown) {
  if (typeof error === 'object' && error !== null && 'status' in error) {
    const status = (error as ErrorWithStatus).status;
    return typeof status === 'number' ? status : null;
  }
  if (typeof error === 'object' && error !== null && 'message' in error) {
    const message = (error as ErrorWithStatus).message;
    if (typeof message === 'string') {
      const match = message.match(/\bfailed with (\d{3})\b/);
      if (match) {
        return Number(match[1]);
      }
    }
  }
  return null;
}

function getErrorMessage(error: unknown) {
  if (typeof error === 'object' && error !== null && 'message' in error) {
    const message = (error as ErrorWithStatus).message;
    if (typeof message === 'string' && message.length > 0) {
      return message;
    }
  }
  return 'Unexpected error';
}

function getAllowedViews(user: CurrentUser | null) {
  return VIEW_DEFINITIONS.filter((view) => !view.adminOnly || user?.role === 'admin');
}

function pickInitialView(user: CurrentUser) {
  const allowedViews = getAllowedViews(user);
  const requestedViewId = getRequestedViewId();
  return allowedViews.find((view) => view.id === requestedViewId)?.id ?? allowedViews[0]?.id ?? 'official';
}

export function DashboardRoot() {
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [currentViewId, setCurrentViewId] = useState('official');
  const [authChecked, setAuthChecked] = useState(false);
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loginPending, setLoginPending] = useState(false);
  const [logoutPending, setLogoutPending] = useState(false);
  const [shellError, setShellError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetchCurrentUser()
      .then((user) => {
        if (cancelled) {
          return;
        }
        setCurrentUser(user);
        setCurrentViewId(pickInitialView(user));
        setBootstrapError(null);
        setShellError(null);
        setAuthChecked(true);
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        if (getErrorStatus(error) === 401) {
          setCurrentUser(null);
          setBootstrapError(null);
        } else {
          setBootstrapError(getErrorMessage(error));
        }
        setAuthChecked(true);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const allowedViews = useMemo(() => getAllowedViews(currentUser), [currentUser]);
  const activeView = allowedViews.find((view) => view.id === currentViewId) ?? allowedViews[0];

  useEffect(() => {
    if (!currentUser || !activeView) {
      return;
    }
    const searchParams = new URLSearchParams(window.location.search);
    searchParams.set('view', activeView.id);
    const query = searchParams.toString();
    window.history.replaceState({}, '', query ? `${window.location.pathname}?${query}` : window.location.pathname);
  }, [activeView, currentUser]);

  async function handleLogin(identifier: string, password: string) {
    setLoginPending(true);
    setLoginError(null);
    try {
      const user = await login(identifier, password);
      setCurrentUser(user);
      setCurrentViewId(pickInitialView(user));
      setBootstrapError(null);
      setShellError(null);
    } catch (error: unknown) {
      setLoginError(getErrorMessage(error));
    } finally {
      setLoginPending(false);
      setAuthChecked(true);
    }
  }

  async function handleLogout() {
    setLogoutPending(true);
    setShellError(null);
    try {
      await logout();
      setCurrentUser(null);
      setCurrentViewId('official');
      setBootstrapError(null);
      setLoginError(null);
    } catch (error: unknown) {
      setShellError(getErrorMessage(error));
    } finally {
      setLogoutPending(false);
      setAuthChecked(true);
    }
  }

  if (!authChecked) {
    return <p className="muted">Loading dashboard...</p>;
  }

  if (bootstrapError) {
    return (
      <main
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '24px',
          boxSizing: 'border-box'
        }}
      >
        <section
          style={{
            width: '100%',
            maxWidth: '560px',
            padding: '24px',
            border: '1px solid rgba(248, 113, 113, 0.35)',
            borderRadius: '16px',
            backgroundColor: '#ffffff'
          }}
        >
          <h1>Unable to load dashboard.</h1>
          <p className="error-text">{bootstrapError}</p>
        </section>
      </main>
    );
  }

  if (!currentUser) {
    return <LoginView error={loginError} isSubmitting={loginPending} onSubmit={handleLogin} />;
  }

  return (
    <main className="dashboard-root-shell">
      <aside className="dashboard-root-sidebar">
        <div className="panel-title">Dashboard</div>
        <div style={{ display: 'grid', gap: '8px' }}>
          <div className="muted">{currentUser.display_name}</div>
          <button className="secondary-button" type="button" disabled={logoutPending} onClick={() => void handleLogout()}>
            {logoutPending ? '退出中...' : '退出登录'}
          </button>
          {shellError ? (
            <p className="error-text" role="alert">
              {shellError}
            </p>
          ) : null}
        </div>
        {(['官方', '我的', '管理'] as const).map((section) => {
          const items = allowedViews.filter((view) => view.section === section);
          if (items.length === 0) {
            return null;
          }
          return (
            <section key={section} className="dashboard-root-nav-section">
              <h2>{section}</h2>
              {items.map((view) => (
                <button
                  key={view.id}
                  type="button"
                  className="segment-button"
                  aria-pressed={activeView?.id === view.id}
                  onClick={() => setCurrentViewId(view.id)}
                >
                  {view.label}
                </button>
              ))}
            </section>
          );
        })}
      </aside>
      <section className="dashboard-root-content">{activeView?.render(currentUser)}</section>
    </main>
  );
}
