import { useEffect, useState } from 'react';
import { fetchCurrentUser, loginDashboardUser } from '../api/client';
import type { CurrentUser } from '../api/types';
import { AppShell } from './AppShell';
import { LoginView } from './LoginView';

export function DashboardAuthRoot() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    fetchCurrentUser()
      .then((payload) => {
        if (!cancelled) setUser(payload.user);
      })
      .catch(() => {
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return <main className="login-shell">加载中</main>;
  }

  if (!user) {
    return (
      <LoginView
        error={error}
        onSubmit={(username, password) => {
          setError('');
          loginDashboardUser({ username, password })
            .then((payload) => setUser(payload.user))
            .catch((err) => setError(`登录失败：${err instanceof Error ? err.message : 'unknown'}`));
        }}
      />
    );
  }

  return <AppShell currentUser={user} />;
}
