import { useEffect, useMemo, useState } from 'react';
import { App } from './App';
import { fetchCurrentUser, login } from './api/client';
import type { CurrentUser } from './api/types';
import { LoginView } from './views/LoginView';

type ViewDefinition = {
  id: string;
  label: string;
  section: '官方' | '我的' | '管理';
  adminOnly?: boolean;
  render: () => JSX.Element;
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
        setAuthChecked(true);
      })
      .catch(() => {
        if (cancelled) {
          return;
        }
        setCurrentUser(null);
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
    } catch (error: unknown) {
      setLoginError(error instanceof Error ? error.message : String(error));
    } finally {
      setLoginPending(false);
      setAuthChecked(true);
    }
  }

  if (!authChecked) {
    return <p className="muted">Loading dashboard...</p>;
  }

  if (!currentUser) {
    return <LoginView error={loginError} isSubmitting={loginPending} onSubmit={handleLogin} />;
  }

  return (
    <div className="workbench">
      <aside className="sidebar">
        <div className="panel-title">Dashboard</div>
        {(['官方', '我的', '管理'] as const).map((section) => {
          const items = allowedViews.filter((view) => view.section === section);
          if (items.length === 0) {
            return null;
          }
          return (
            <section key={section}>
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
      <section className="workspace">{activeView?.render()}</section>
    </div>
  );
}
