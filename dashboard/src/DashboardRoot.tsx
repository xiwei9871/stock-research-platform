import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { App } from './App';
import { fetchCurrentUser, login } from './api/client';
import type { CurrentUser } from './api/types';
import { LoginView } from './views/LoginView';

type ErrorWithStatus = {
  message?: string;
  status?: number;
};

type ViewDefinition = {
  id: string;
  label: string;
  section: '官方' | '我的' | '管理';
  adminOnly?: boolean;
  render: () => ReactNode;
};

const VIEW_DEFINITIONS: ViewDefinition[] = [
  {
    id: 'official',
    label: '官方工作台',
    section: '官方',
    render: () => <App />
  },
  {
    id: 'my-reviews',
    label: '我的复盘',
    section: '我的',
    render: () => (
      <section className="chart-panel">
        <h1>我的复盘</h1>
        <p className="muted">个人复盘视图将在后续任务中补充。</p>
      </section>
    )
  },
  {
    id: 'admin-users',
    label: '用户管理',
    section: '管理',
    adminOnly: true,
    render: () => (
      <section className="chart-panel">
        <h1>用户管理</h1>
        <p className="muted">管理视图将在后续任务中补充。</p>
      </section>
    )
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
    window.history.replaceState({}, '', query ? `?${query}` : window.location.pathname);
  }, [activeView, currentUser]);

  async function handleLogin(identifier: string, password: string) {
    setLoginPending(true);
    setLoginError(null);
    try {
      const user = await login(identifier, password);
      setCurrentUser(user);
      setCurrentViewId(pickInitialView(user));
      setBootstrapError(null);
    } catch (error: unknown) {
      setLoginError(getErrorMessage(error));
    } finally {
      setLoginPending(false);
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
    <main
      style={{
        minHeight: '100vh',
        display: 'grid',
        gridTemplateColumns: '220px minmax(0, 1fr)',
        gap: '24px',
        padding: '24px',
        boxSizing: 'border-box'
      }}
    >
      <aside
        style={{
          alignSelf: 'start',
          display: 'grid',
          gap: '20px',
          padding: '20px',
          border: '1px solid rgba(148, 163, 184, 0.35)',
          borderRadius: '16px',
          backgroundColor: '#ffffff'
        }}
      >
        <div className="panel-title">Dashboard</div>
        {(['官方', '我的', '管理'] as const).map((section) => {
          const items = allowedViews.filter((view) => view.section === section);
          if (items.length === 0) {
            return null;
          }
          return (
            <section key={section} style={{ display: 'grid', gap: '10px' }}>
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
      <section style={{ minWidth: 0 }}>{activeView?.render()}</section>
    </main>
  );
}
